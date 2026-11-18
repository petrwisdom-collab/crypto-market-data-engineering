from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Iterable

from .models import Candle


@dataclass(frozen=True)
class QualityReport:
    input_count: int
    output_count: int
    duplicate_count: int
    invalid_ohlc_count: int
    invalid_volume_count: int
    out_of_order_count: int
    missing_periods: list[str]
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.invalid_ohlc_count == 0
            and self.invalid_volume_count == 0
            and self.duplicate_count == 0
            and self.out_of_order_count == 0
            and len(self.missing_periods) == 0
        )


@dataclass(frozen=True)
class CandleQualityResult:
    candles: list[Candle]
    report: QualityReport


def _is_valid_number(value: float | None) -> bool:
    return value is not None and isfinite(value)


def _is_valid_ohlc(candle: Candle) -> bool:
    values = (
        candle.open,
        candle.high,
        candle.low,
        candle.close,
    )

    if not all(_is_valid_number(value) for value in values):
        return False

    return (
        candle.high >= candle.low
        and candle.high >= candle.open
        and candle.high >= candle.close
        and candle.low <= candle.open
        and candle.low <= candle.close
    )


def _is_valid_volume(candle: Candle) -> bool:
    if candle.volume is None:
        return True

    return isfinite(candle.volume) and candle.volume >= 0


def normalize_candles(
    candles: Iterable[Candle],
    expected_interval: timedelta,
) -> CandleQualityResult:
    input_candles = list(candles)
    input_count = len(input_candles)

    duplicate_count = 0
    invalid_ohlc_count = 0
    invalid_volume_count = 0
    out_of_order_count = 0

    warnings: list[str] = []

    # Make sure all timestamps are timezone-aware and normalized to UTC.
    normalized: list[Candle] = []

    for candle in input_candles:
        if candle.timestamp.tzinfo is None:
            raise ValueError(
                "Candle timestamp must be timezone-aware"
            )

        timestamp = candle.timestamp.astimezone(timezone.utc)

        normalized.append(
            Candle(
                timestamp=timestamp,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
            )
        )

    # Detect whether the source data was originally out of order.
    for previous, current in zip(normalized, normalized[1:]):
        if current.timestamp < previous.timestamp:
            out_of_order_count += 1

    # Sort chronologically so downstream processing receives ordered data.
    normalized.sort(key=lambda candle: candle.timestamp)

    # Remove duplicate timestamps deterministically.
    unique: list[Candle] = []
    seen_timestamps: set[datetime] = set()

    for candle in normalized:
        if candle.timestamp in seen_timestamps:
            duplicate_count += 1
            continue

        seen_timestamps.add(candle.timestamp)
        unique.append(candle)

    # Validate OHLC and volume values.
    valid_candles: list[Candle] = []

    for candle in unique:
        ohlc_valid = _is_valid_ohlc(candle)
        volume_valid = _is_valid_volume(candle)

        if not ohlc_valid:
            invalid_ohlc_count += 1

        if not volume_valid:
            invalid_volume_count += 1

        # Do not silently repair bad market data.
        # Invalid candles remain excluded from the cleaned dataset.
        if ohlc_valid and volume_valid:
            valid_candles.append(candle)

    # Find missing expected periods using the cleaned chronological data.
    missing_periods: list[str] = []

    if len(valid_candles) >= 2:
        for previous, current in zip(
            valid_candles,
            valid_candles[1:],
        ):
            expected_next = previous.timestamp + expected_interval

            while expected_next < current.timestamp:
                missing_periods.append(
                    expected_next.isoformat()
                )
                expected_next += expected_interval

    if duplicate_count:
        warnings.append(
            f"{duplicate_count} duplicate timestamp(s) were removed."
        )

    if invalid_ohlc_count:
        warnings.append(
            f"{invalid_ohlc_count} candle(s) had invalid OHLC values."
        )

    if invalid_volume_count:
        warnings.append(
            f"{invalid_volume_count} candle(s) had invalid volume values."
        )

    if out_of_order_count:
        warnings.append(
            f"{out_of_order_count} out-of-order timestamp transition(s) were detected."
        )

    if missing_periods:
        warnings.append(
            f"{len(missing_periods)} expected period(s) are missing."
        )

    output_count = len(valid_candles)

    report = QualityReport(
        input_count=input_count,
        output_count=output_count,
        duplicate_count=duplicate_count,
        invalid_ohlc_count=invalid_ohlc_count,
        invalid_volume_count=invalid_volume_count,
        out_of_order_count=out_of_order_count,
        missing_periods=missing_periods,
        warnings=warnings,
    )

    return CandleQualityResult(
        candles=valid_candles,
        report=report,
    )