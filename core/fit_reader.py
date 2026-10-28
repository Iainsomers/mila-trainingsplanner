"""Small, dependency-free Garmin FIT reader for upload previews.

The preview intentionally keeps the raw message/field availability visible.  A
later Garmin model can consume the same normalized payload without coupling the
upload screen to training-slot writes.
"""

from __future__ import annotations

import datetime as dt
import struct
import zipfile
import io
import math
from collections import Counter, defaultdict


FIT_EPOCH = dt.datetime(1989, 12, 31, tzinfo=dt.timezone.utc)
MESSAGE_NAMES = {
    0: "file_id", 18: "session", 19: "lap", 20: "record", 21: "event",
    23: "device_info", 34: "activity", 49: "file_creator", 207: "field_description",
}

FIELD_NAMES = {
    0: {"file_id": "type", "session": "event", "lap": "event", "record": "position_lat"},
    1: {"file_id": "manufacturer", "session": "event_type", "record": "position_long"},
    2: {"file_id": "product", "session": "start_time", "lap": "start_time", "record": "altitude"},
    3: {"file_id": "time_created", "session": "start_position_lat", "record": "heart_rate"},
    4: {"file_id": "serial_number", "session": "start_position_long", "record": "cadence"},
    5: {"file_id": "number", "record": "distance"},
    6: {"record": "speed"},
    7: {"session": "total_elapsed_time", "lap": "elapsed_time", "record": "power"},
    8: {"session": "total_timer_time", "lap": "timer_time", "record": "compressed_speed_distance"},
    9: {"session": "total_distance", "lap": "distance", "record": "grade"},
    10: {"session": "total_cycles", "lap": "total_cycles"},
    11: {"session": "total_calories", "lap": "total_calories"},
    12: {"session": "total_fat_calories"},
    13: {"session": "avg_speed", "lap": "avg_speed"},
    14: {"session": "max_speed", "lap": "max_speed"},
    15: {"lap": "avg_heart_rate"},
    16: {"session": "avg_heart_rate", "lap": "max_heart_rate"},
    17: {"session": "max_heart_rate", "lap": "avg_speed"},
    18: {"session": "avg_speed", "lap": "max_speed"},
    19: {"session": "avg_power", "lap": "avg_power"},
    20: {"session": "max_power", "lap": "max_power"},
    21: {"session": "avg_cadence", "lap": "avg_cadence"},
    22: {"session": "max_cadence", "lap": "max_cadence"},
    24: {"session": "normalized_power", "lap": "intensity"},
    25: {"session": "training_stress_score"},
    28: {"session": "sport"},
    29: {"session": "sub_sport"},
    30: {"session": "avg_temperature", "lap": "normalized_power"},
    31: {"session": "max_temperature"},
    34: {"session": "first_lap_index"},
    35: {"session": "num_laps"},
    36: {"session": "normalized_power"},
    37: {"session": "training_stress_score"},
    41: {"session": "num_laps"},
    253: {"record": "timestamp"},
}

BASE_TYPES = {
    0x00: ("B", 1), 0x01: ("b", 1), 0x02: ("B", 1), 0x83: ("h", 2),
    0x84: ("H", 2), 0x85: ("i", 4), 0x86: ("I", 4), 0x07: ("s", 1),
    0x88: ("f", 4), 0x89: ("d", 8), 0x8A: ("B", 1), 0x8B: ("H", 2),
    0x8C: ("I", 4), 0x8E: ("q", 8), 0x8F: ("Q", 8), 0x90: ("Q", 8),
}


def fit_bytes_from_upload(filename: str, raw: bytes) -> tuple[str, bytes]:
    """Return the FIT payload from a direct FIT upload or Garmin ZIP export."""
    name = (filename or "").strip()
    if name.lower().endswith(".fit"):
        return name, raw
    if not name.lower().endswith(".zip"):
        raise ValueError("Only .fit files or Garmin .zip exports are supported.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            candidates = [
                item for item in archive.infolist()
                if not item.is_dir() and item.filename.lower().endswith(".fit")
            ]
            if not candidates:
                raise ValueError("The ZIP file does not contain a .fit file.")
            if len(candidates) > 1:
                raise ValueError("The ZIP file contains multiple .fit files. Upload one activity at a time.")
            item = candidates[0]
            if item.file_size > 12 * 1024 * 1024:
                raise ValueError("The FIT file inside the ZIP is too large (maximum 12 MB).")
            return item.filename, archive.read(item)
    except zipfile.BadZipFile as exc:
        raise ValueError("The ZIP file could not be opened.") from exc


def json_safe_fit_data(value):
    """Convert parsed FIT data to values safe for a JSONField."""
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): json_safe_fit_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_fit_data(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _timestamp(value):
    if value in (None, 0xFFFFFFFF):
        return None
    try:
        return FIT_EPOCH + dt.timedelta(seconds=int(value))
    except (TypeError, ValueError, OverflowError):
        return None


def _value(raw, base_type, endian):
    spec = BASE_TYPES.get(base_type) or BASE_TYPES.get(base_type & 0x1F)
    if not spec:
        return None
    fmt, size = spec
    if len(raw) < size:
        return None
    if fmt == "s":
        return raw.split(b"\0", 1)[0].decode("utf-8", "replace")
    try:
        value = struct.unpack(endian + fmt, raw[:size])[0]
    except struct.error:
        return None
    if value in (0xFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return None
    return value


def _display_name(global_num, field_num):
    message = MESSAGE_NAMES.get(global_num, f"message_{global_num}")
    return FIELD_NAMES.get(field_num, {}).get(message, f"field_{field_num}")


def _scale(message, field, value):
    if value is None:
        return None
    if message == 18:
        if field in {7, 8, 13, 14, 18, 19}:
            return float(value) / 1000.0
        if field == 9:
            return float(value) / 100.0
        if field == 25:
            return float(value) / 10.0
    if message == 19:
        if field in {7, 8, 13, 14, 17, 18}:
            return float(value) / 1000.0
        if field == 9:
            return float(value) / 100.0
    if message == 20 and field == 2:
        return float(value) / 5.0 - 500.0
    if message == 20 and field == 5:
        return float(value) / 100.0
    if message == 20 and field == 6:
        return float(value) / 1000.0
    return value


def parse_fit(raw: bytes) -> dict:
    if len(raw) < 14 or raw[8:12] != b".FIT":
        raise ValueError("This is not a valid FIT file.")
    header_size = raw[0]
    data_size = struct.unpack_from("<I", raw, 4)[0]
    end = min(len(raw), header_size + data_size)
    pos = header_size
    definitions = {}
    messages = []
    last_timestamps = {}
    while pos < end:
        header = raw[pos]
        pos += 1
        compressed_timestamp = bool(header & 0x80)
        if compressed_timestamp:
            local = (header >> 5) & 0x03
        elif header & 0x40:
            local = header & 0x0F
            if pos + 5 > end:
                break
            # Definition header: reserved byte, architecture byte, global
            # message number, then number of fields.
            architecture = raw[pos + 1]
            endian = ">" if architecture else "<"
            global_num = struct.unpack_from(endian + "H", raw, pos + 2)[0]
            count = raw[pos + 4]
            pos += 5
            fields = []
            for _ in range(count):
                if pos + 3 > end:
                    break
                field_num, size, base_type = raw[pos:pos + 3]
                fields.append((field_num, size, base_type))
                pos += 3
            developer_fields = []
            if header & 0x20 and pos < end:  # developer field definitions
                developer_count = raw[pos]
                pos += 1
                for _ in range(developer_count):
                    if pos + 3 > end:
                        break
                    _field_num, field_size, _developer_index = raw[pos:pos + 3]
                    developer_fields.append(field_size)
                    pos += 3
            definitions[local] = (global_num, endian, fields, developer_fields)
            continue
        if not compressed_timestamp:
            local = header & 0x0F
        definition = definitions.get(local)
        if not definition:
            break
        global_num, endian, fields, developer_fields = definition
        item = {"message": MESSAGE_NAMES.get(global_num, f"message_{global_num}")}
        if compressed_timestamp:
            previous = last_timestamps.get(local)
            if previous is None:
                break
            time_offset = header & 0x1F
            timestamp = (previous & ~0x1F) + time_offset
            if time_offset < (previous & 0x1F):
                timestamp += 0x20
            item["timestamp"] = timestamp
        for field_num, size, base_type in fields:
            # Compressed timestamp headers carry the timestamp in their header,
            # so the corresponding field bytes are omitted from the data message.
            if compressed_timestamp and field_num == 253:
                continue
            value = _value(raw[pos:pos + size], base_type, endian)
            pos += size
            if value is not None:
                item[_display_name(global_num, field_num)] = _scale(global_num, field_num, value)
        for size in developer_fields:
            pos += size
        if "timestamp" in item:
            last_timestamps[local] = item["timestamp"]
        messages.append((global_num, item))

    by_name = defaultdict(list)
    for global_num, item in messages:
        by_name[item["message"]].append(item)
    records = by_name.get("record", [])
    laps = by_name.get("lap", [])
    sessions = by_name.get("session", [])
    for collection in (records, laps, sessions, by_name.get("activity", []), by_name.get("file_id", [])):
        for item in collection:
            if "timestamp" in item:
                item["timestamp"] = _timestamp(item["timestamp"])
            if "start_time" in item:
                item["start_time"] = _timestamp(item["start_time"])
    session = sessions[0] if sessions else {}
    heart_rate_samples = [
        {"timestamp": record.get("timestamp"), "heart_rate": record.get("heart_rate")}
        for record in records
        if record.get("timestamp") is not None and record.get("heart_rate") is not None
    ]
    total_distance = session.get("total_distance")
    if total_distance is None and laps:
        total_distance = sum(float(lap.get("distance") or 0) for lap in laps)
    elapsed = session.get("total_elapsed_time")
    moving = session.get("total_timer_time")
    def duration(value):
        if value is None:
            return "—"
        seconds = max(0, int(round(float(value))))
        return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}" if seconds >= 3600 else f"{seconds // 60}:{seconds % 60:02d}"

    def distance(value):
        return "—" if value is None else f"{float(value) / 1000:.2f} km"

    def pace(distance_m, seconds):
        if not distance_m or not seconds:
            return "—"
        total = float(seconds) * 1000 / float(distance_m)
        return f"{int(total // 60)}:{int(round(total % 60)):02d}/km"

    lap_rows = []
    for index, lap in enumerate(laps, 1):
        lap_rows.append({
            "number": index,
            "distance": distance(lap.get("distance")),
            "duration": duration(lap.get("elapsed_time") or lap.get("timer_time")),
            "moving_time": duration(lap.get("timer_time")),
            "pace": pace(lap.get("distance"), lap.get("elapsed_time") or lap.get("timer_time")),
            "heart_rate": lap.get("avg_heart_rate", "—"),
            "max_heart_rate": lap.get("max_heart_rate", "—"),
            "power": lap.get("avg_power", "—"),
        })

    return {
        "message_count": len(messages),
        "message_types": dict(sorted(Counter(item["message"] for _, item in messages).items())),
        "available_fields": {
            name: sorted({key for item in items for key in item if key != "message"})
            for name, items in sorted(by_name.items())
        },
        "file_id": (by_name.get("file_id") or [{}])[0],
        "activity": (by_name.get("activity") or [{}])[0],
        "session": session,
        "laps": laps,
        "record_count": len(records),
        "heart_rate_samples": heart_rate_samples,
        "records_preview": records[:3] + (records[-3:] if len(records) > 6 else []),
        "total_distance_m": total_distance,
        "total_elapsed_s": elapsed,
        "total_timer_s": moving,
        "human": {
            "file_name": "",
            "activity_start": (session.get("start_time") or (by_name.get("activity") or [{}])[0].get("timestamp")),
            "distance": distance(total_distance),
            "elapsed": duration(elapsed),
            "moving": duration(moving),
            "paused": duration(float(elapsed or 0) - float(moving or 0)) if elapsed is not None and moving is not None else "—",
            "avg_hr": session.get("avg_heart_rate", "—"),
            "max_hr": session.get("max_heart_rate", "—"),
            "calories": session.get("total_calories", "—"),
            "sport": session.get("sport", "—"),
            "lap_rows": lap_rows,
        },
    }
