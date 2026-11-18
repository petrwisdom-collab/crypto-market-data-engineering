from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import median

from .models import Candle
from .timeframes import TIMEFRAME_SECONDS


class CandleValidator:
    """Strict validation: malformed/cadence/duplicate/order/severe-gap findings fail."""
    def validate(self, candles: list[Candle], timeframe: str, closed_only: bool = True, now: datetime | None = None) -> dict:
        if timeframe not in TIMEFRAME_SECONDS:
            return {"status": "FAIL", "findings": [{"severity": "FAIL", "code": "unsupported_timeframe", "message": f"Cannot validate fixed cadence for {timeframe}"}], "valid_candles": []}
        expected = TIMEFRAME_SECONDS[timeframe]
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        timestamps = [item.timestamp for item in candles]
        findings, valid = [], []
        duplicates = sum(count - 1 for count in Counter(timestamps).values() if count > 1)
        disorder = sum(1 for left, right in zip(timestamps, timestamps[1:]) if right <= left)
        if duplicates:
            findings.append({"severity": "FAIL", "code": "duplicate_timestamp", "count": duplicates})
        if disorder:
            findings.append({"severity": "FAIL", "code": "timestamp_disorder", "count": disorder})
        for item in candles:
            if min(item.open, item.high, item.low, item.close) <= 0 or item.high < item.low or not (item.low <= item.open <= item.high and item.low <= item.close <= item.high):
                findings.append({"severity": "FAIL", "code": "invalid_ohlc", "timestamp": item.timestamp.isoformat()})
                continue
            if item.volume is None:
                findings.append({"severity": "WARNING", "code": "missing_volume", "timestamp": item.timestamp.isoformat()})
            elif item.volume < 0:
                findings.append({"severity": "FAIL", "code": "invalid_volume", "timestamp": item.timestamp.isoformat()})
                continue
            valid.append(item)
        cadence = self._cadence_seconds(valid)
        if cadence is not None and abs(cadence - expected) > expected * 0.2:
            findings.append({"severity": "FAIL", "code": "wrong_cadence", "expected_seconds": expected, "observed_median_seconds": cadence})
        gaps = []
        for left, right in zip(valid, valid[1:]):
            seconds = (right.timestamp - left.timestamp).total_seconds()
            if seconds > expected * 1.5:
                gap = {"after": left.timestamp.isoformat(), "before": right.timestamp.isoformat(), "duration_seconds": seconds}
                gaps.append(gap)
                findings.append({"severity": "FAIL", "code": "severe_gap", **gap})
        incomplete = []
        if valid and valid[-1].timestamp + timedelta(seconds=expected) > now:
            incomplete.append(valid[-1].timestamp.isoformat())
            findings.append({"severity": "FAIL" if closed_only else "WARNING", "code": "incomplete_final_candle", "timestamp": valid[-1].timestamp.isoformat()})
        status = "FAIL" if any(item["severity"] == "FAIL" for item in findings) else "WARNING" if findings else "PASS"
        return {"status": status, "findings": findings, "valid_candles": valid, "expected_cadence_seconds": expected, "observed_cadence_seconds": cadence, "duplicates": duplicates, "missing_intervals": gaps, "incomplete_candles": incomplete}

    @staticmethod
    def _cadence_seconds(candles: list[Candle]) -> float | None:
        if len(candles) < 2:
            return None
        return median((right.timestamp - left.timestamp).total_seconds() for left, right in zip(candles, candles[1:]))


def aggregate_candles(candles: list[Candle], source_timeframe: str, target_timeframe: str) -> list[Candle]:
    """Aggregate closed UTC-aligned fixed-timeframe candles; never fills missing bars."""
    if source_timeframe not in TIMEFRAME_SECONDS or target_timeframe not in TIMEFRAME_SECONDS:
        raise ValueError("Only fixed timeframes can be aggregated; 1 Month requires a calendar-aware future implementation")
    source, target = TIMEFRAME_SECONDS[source_timeframe], TIMEFRAME_SECONDS[target_timeframe]
    if target <= source or target % source:
        raise ValueError("Target timeframe must be an integer multiple of source timeframe")
    grouped: dict[datetime, list[Candle]] = {}
    for candle in sorted(candles, key=lambda item: item.timestamp):
        bucket = datetime.fromtimestamp((int(candle.timestamp.timestamp()) // target) * target, tz=timezone.utc)
        grouped.setdefault(bucket, []).append(candle)
    needed, output = target // source, []
    for bucket, group in grouped.items():
        if len(group) != needed:
            continue
        if any((right.timestamp - left.timestamp).total_seconds() != source for left, right in zip(group, group[1:])):
            continue
        output.append(Candle(bucket, group[0].open, max(item.high for item in group), min(item.low for item in group), group[-1].close, sum(item.volume for item in group if item.volume is not None) if all(item.volume is not None for item in group) else None))
    return output


class DataQualityReporter:
    def build(self, provenance, dataset_version: str, candles: list[Candle], validation: dict, limitations: str, cross_source: dict | None = None) -> dict:
        expected_records = None
        if len(candles) >= 2 and validation.get("expected_cadence_seconds"):
            expected_records = int((candles[-1].timestamp - candles[0].timestamp).total_seconds() // validation["expected_cadence_seconds"]) + 1
        return {"provider": provenance.provider, "asset": provenance.asset, "market": provenance.market, "timeframe": provenance.timeframe, "earliest_timestamp": candles[0].timestamp.isoformat() if candles else None, "latest_timestamp": candles[-1].timestamp.isoformat() if candles else None, "record_count": len(candles), "expected_record_count": expected_records, "expected_cadence_seconds": validation.get("expected_cadence_seconds"), "observed_cadence_seconds": validation.get("observed_cadence_seconds"), "completeness_percentage": round(len(candles) / expected_records * 100, 2) if expected_records else None, "missing_intervals": validation.get("missing_intervals", []), "duplicates": validation.get("duplicates", 0), "invalid_ohlc": [x for x in validation.get("findings", []) if x["code"] == "invalid_ohlc"], "invalid_volume": [x for x in validation.get("findings", []) if x["code"] == "invalid_volume"], "incomplete_candles": validation.get("incomplete_candles", []), "findings": validation.get("findings", []), "cross_source_discrepancies": cross_source, "api_limitations": limitations, "dataset_version": dataset_version, "validation_status": validation["status"]}
