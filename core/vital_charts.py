from datetime import timedelta
from math import isfinite
from statistics import mean, pstdev

from core.models import AthleteDailyVital


VITAL_PERIODS = (2, 4, 6, 10)
VITAL_SERIES = (
    ("sleep_hours", "Sleep time", "h", 47, "end"),
    ("sleep_quality", "Sleep quality", "", 112, "end"),
    ("morning_hr", "Morning HR", "bpm", 788, "start"),
    ("hrv", "HRV", "ms", 853, "start"),
)
PLOT_LEFT, PLOT_RIGHT = 122, 778
PLOT_TOP, PLOT_BOTTOM = 38, 291


def daily_vital_chart(athlete, baseline_start, start, end):
    measurements = {field: {} for field, *_ in VITAL_SERIES}
    for row in AthleteDailyVital.objects.filter(
        athlete=athlete, date__range=(baseline_start, end),
    ).values("date", *measurements):
        for field, values in measurements.items():
            value = row[field]
            if value is not None and isfinite(value):
                values[row["date"]] = float(value)

    days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    series = []
    for field, title, unit, axis_x, axis_anchor in VITAL_SERIES:
        values = measurements[field]
        item = {
            "key": field, "title": title, "unit": unit, "axis_x": axis_x, "axis_anchor": axis_anchor,
            "sample_count": len(values), "points": [], "ticks": [],
        }
        series.append(item)
        if not values:
            continue
        average, deviation = mean(values.values()), pstdev(values.values())
        direction = -1 if field == "morning_hr" else 1
        standardized = {
            day: direction * (value - average) / deviation if deviation else 0
            for day, value in values.items() if start <= day <= end
        }
        item.update({"mean": average, "deviation": deviation, "direction": direction, "standardized": standardized})

    def x(index):
        return round(PLOT_LEFT + (PLOT_RIGHT - PLOT_LEFT) * index / (len(days) - 1), 2)

    def position_y(score):
        return round(PLOT_TOP + (PLOT_BOTTOM - PLOT_TOP) * (3 - score) / 6, 2)

    limits = [-3, -2, -1, 1, 2, 3]
    bands = [
        {"y": position_y(top), "height": round(position_y(bottom) - position_y(top), 2), "color": color}
        for bottom, top, color in zip(limits, limits[1:], ("very-low", "low", "normal", "high", "very-high"))
    ]
    tick_scores = (2, 1, 0.5, 0, -0.5, -1, -2)
    for item in series:
        if not item["sample_count"]:
            continue
        scores = item.pop("standardized")
        direction = item.pop("direction")
        commands = []
        previous = False
        for index, day in enumerate(days):
            if day not in scores:
                previous = False
                continue
            score = scores[day]
            y = PLOT_BOTTOM if score < -2 else PLOT_TOP if score > 2 else position_y(score)
            point = {"x": x(index), "y": y, "date": day, "value": measurements[item["key"]][day]}
            item["points"].append(point)
            commands.append(f"{'L' if previous else 'M'} {point['x']} {point['y']}")
            previous = True
        item["path"] = " ".join(commands)
        item["ticks"] = [
            {"y": position_y(score), "label": item["mean"] + direction * score * item["deviation"]}
            for score in (tick_scores if item["deviation"] else (0,))
        ]

    return {
        "series": series,
        "has_points": any(item["points"] for item in series),
        "bands": bands,
        "grid": [position_y(score) for score in tick_scores],
        "dates": [
            {"x": x(index), "date": days[index]}
            for index in (round((len(days) - 1) * step / 5) for step in range(6))
        ],
        "left": PLOT_LEFT,
        "right": PLOT_RIGHT,
        "width": PLOT_RIGHT - PLOT_LEFT,
        "top": PLOT_TOP,
        "bottom": PLOT_BOTTOM,
    }
