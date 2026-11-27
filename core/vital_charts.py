from datetime import timedelta
from math import isfinite
from statistics import mean, pstdev

from core.models import AthleteDailyVital


VITAL_PERIODS = (2, 4, 6, 10)
VITAL_COLUMNS = (
    (("sleep_hours", "Sleep time", "h"), ("sleep_quality", "Sleep quality", "")),
    (("morning_hr", "Morning HR", "bpm"), ("hrv", "HRV", "ms")),
)


def daily_vital_charts(athlete, baseline_start, start, end):
    fields = [field for column in VITAL_COLUMNS for field, _, _ in column]
    measurements = {field: {} for field in fields}
    for row in AthleteDailyVital.objects.filter(
        athlete=athlete, date__range=(baseline_start, end),
    ).values("date", *fields):
        for field in fields:
            value = row[field]
            if value is not None and isfinite(value):
                measurements[field][row["date"]] = float(value)

    days = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    return [
        [
            _chart(measurements[field], days, title, unit, axis_right=index == 1, reverse=field == "morning_hr")
            for field, title, unit in column
        ]
        for index, column in enumerate(VITAL_COLUMNS)
    ]


def _chart(values, days, title, unit, *, axis_right, reverse):
    chart = {"title": title, "unit": unit, "axis_right": axis_right, "reverse": reverse}
    if not values:
        return chart

    average = mean(values.values())
    deviation = pstdev(values.values())
    direction = -1 if reverse else 1
    center = average * direction
    boundaries = [center + offset * deviation for offset in (-2, -1, 1, 2)]
    visible = [values[day] * direction for day in days if day in values]
    low = min([boundaries[0], *visible])
    high = max([boundaries[-1], *visible])
    margin = (high - low) * .09 if high > low else max(abs(center) * .05, .5)
    low, high = low - margin, high + margin

    left, right = (10, 452) if axis_right else (48, 490)

    def x(index):
        return round(left + (right - left) * index / (len(days) - 1), 2)

    def y(value):
        return round(12 + 126 * (high - value) / (high - low), 2)

    bands = []
    if deviation:
        limits = [low, *boundaries, high]
        for bottom, top, color in zip(limits, limits[1:], ("very-low", "low", "normal", "high", "very-high")):
            bands.append({"y": y(top), "height": round(y(bottom) - y(top), 2), "color": color})
    points = []
    commands = []
    previous = False
    for index, day in enumerate(days):
        value = values.get(day)
        if value is None:
            previous = False
            continue
        point = {"x": x(index), "y": y(value * direction), "date": day, "value": value}
        points.append(point)
        commands.append(f"{'L' if previous else 'M'} {point['x']} {point['y']}")
        previous = True
    ticks = [high - (high - low) * index / 4 for index in range(5)]
    chart.update({
        "mean": average,
        "deviation": deviation,
        "sample_count": len(values),
        "left": left,
        "right": right,
        "axis_x": right + 5 if axis_right else left - 5,
        "axis_anchor": "start" if axis_right else "end",
        "bands": bands,
        "ticks": [{"y": y(value), "label": value * direction} for value in ticks],
        "dates": [
            {"x": x(index), "date": days[index]}
            for index in (round((len(days) - 1) * step / 3) for step in range(4))
        ],
        "points": points,
        "path": " ".join(commands),
    })
    return chart
