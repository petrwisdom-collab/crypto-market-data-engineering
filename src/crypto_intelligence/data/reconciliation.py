from __future__ import annotations

from dataclasses import dataclass

from .models import Candle


@dataclass(frozen=True)
class ReconciliationThresholds:
    minor_bps: float = 25.0
    significant_bps: float = 100.0


def reconcile(left: list[Candle], right: list[Candle], thresholds: ReconciliationThresholds = ReconciliationThresholds()) -> dict:
    """Compare aligned source datasets; it never selects or merges a 'correct' source."""
    left_by_time, right_by_time = {x.timestamp: x for x in left}, {x.timestamp: x for x in right}
    shared = sorted(set(left_by_time) & set(right_by_time))
    if len(shared) < 2:
        return {"classification": "INSUFFICIENT_DATA", "overlap_count": len(shared), "missing_from_left": len(set(right_by_time) - set(left_by_time)), "missing_from_right": len(set(left_by_time) - set(right_by_time))}
    fields, values = ("open", "high", "low", "close", "volume"), {field: [] for field in ("open", "high", "low", "close", "volume")}
    for stamp in shared:
        for field in fields:
            a, b = getattr(left_by_time[stamp], field), getattr(right_by_time[stamp], field)
            if a is not None and b is not None and a != 0:
                values[field].append(abs(a - b) / abs(a) * 10000)
    medians = {field: round(sorted(items)[len(items)//2], 4) if items else None for field, items in values.items()}
    price_max = max(value for field, value in medians.items() if field != "volume" and value is not None)
    classification = "CONSISTENT" if price_max <= thresholds.minor_bps else "MINOR_DISCREPANCY" if price_max <= thresholds.significant_bps else "SIGNIFICANT_DISCREPANCY"
    return {"classification": classification, "overlap_count": len(shared), "missing_from_left": len(set(right_by_time) - set(left_by_time)), "missing_from_right": len(set(left_by_time) - set(right_by_time)), "median_absolute_difference_bps": medians, "thresholds_bps": {"minor": thresholds.minor_bps, "significant": thresholds.significant_bps}}
