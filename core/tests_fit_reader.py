import datetime as dt
import struct
import unittest

from core.fit_reader import FIT_EPOCH, parse_fit


class FitRecordParsingTests(unittest.TestCase):
    def test_record_hr_and_compressed_timestamps_are_decoded(self):
        timestamp = 1_162_028_787
        data = bytearray()
        # Local message 0: record (global message 20), with standard FIT
        # timestamp and heart-rate fields.
        data.extend((0x40, 0, 0, 20, 0, 2))
        data.extend((253, 4, 0x86, 3, 1, 0x02))
        data.extend((0x00,))
        data.extend(struct.pack("<I", timestamp))
        data.extend((100,))
        # Compressed timestamp messages omit field 253's data bytes.
        for offset, heart_rate in ((timestamp + 1, 101), (timestamp + 6, 106)):
            data.append(0x80 | (offset & 0x1F))
            data.append(heart_rate)

        header = bytearray((14, 0x10, 0, 0))
        header.extend(struct.pack("<I", len(data)))
        header.extend(b".FIT")
        header.extend(b"\0\0")
        parsed = parse_fit(bytes(header + data))

        self.assertEqual(parsed["record_count"], 3)
        self.assertEqual([item["heart_rate"] for item in parsed["heart_rate_samples"]], [100, 101, 106])
        self.assertEqual(
            [item["timestamp"] for item in parsed["heart_rate_samples"]],
            [FIT_EPOCH + dt.timedelta(seconds=value) for value in (timestamp, timestamp + 1, timestamp + 6)],
        )

