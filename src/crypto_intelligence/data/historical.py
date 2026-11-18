from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models import Candle, ProviderFetch
from .validation import aggregate_candles


@dataclass(frozen=True)
class HistoricalCoverage:
    """Actual coverage returned by a historical acquisition."""

    requested_start: datetime
    requested_end: datetime
    actual_start: datetime | None
    actual_end: datetime | None
    record_count: int
    provider: str
    asset: str
    market: str
    timeframe: str
    limitations: str = ""

    def __post_init__(self) -> None:
        for value in (
            self.requested_start,
            self.requested_end,
            self.actual_start,
            self.actual_end,
        ):
            if value is not None and value.tzinfo is None:
                raise ValueError("historical coverage timestamps must be timezone-aware")

        if self.requested_start >= self.requested_end:
            raise ValueError("requested_start must be before requested_end")

        if self.actual_start is not None and self.actual_end is not None:
            if self.actual_start > self.actual_end:
                raise ValueError("actual_start must not be after actual_end")

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime | None) -> str | None:
            if value is None:
                return None
            return value.astimezone(timezone.utc).isoformat()

        return {
            "requested_start": iso(self.requested_start),
            "requested_end": iso(self.requested_end),
            "actual_start": iso(self.actual_start),
            "actual_end": iso(self.actual_end),
            "record_count": self.record_count,
            "provider": self.provider,
            "asset": self.asset,
            "market": self.market,
            "timeframe": self.timeframe,
            "limitations": self.limitations,
        }


@dataclass(frozen=True)
class HistoricalAcquisition:
    """Historical candles together with their source coverage."""

    fetch: ProviderFetch
    coverage: HistoricalCoverage
    warnings: list[str] = field(default_factory=list)

    @property
    def candles(self) -> list[Candle]:
        return self.fetch.candles


def build_historical_coverage(
    fetch: ProviderFetch,
    start: datetime,
    end: datetime,
    *,
    asset: str,
    market: str,
    timeframe: str,
) -> HistoricalCoverage:
    """Describe what the provider actually returned without fabricating coverage."""

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware")

    candles = sorted(fetch.candles, key=lambda candle: candle.timestamp)

    return HistoricalCoverage(
        requested_start=start.astimezone(timezone.utc),
        requested_end=end.astimezone(timezone.utc),
        actual_start=candles[0].timestamp if candles else None,
        actual_end=candles[-1].timestamp if candles else None,
        record_count=len(candles),
        provider=fetch.provenance.provider,
        asset=asset.upper(),
        market=market,
        timeframe=timeframe,
        limitations=fetch.limitations,
    )


def acquire_historical(
    provider: Any,
    asset: str,
    market: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> HistoricalAcquisition:
    """
    Acquire historical data through an existing MarketDataProvider.

    This function deliberately does not invent missing candles or alter
    provider-specific source data. The provider remains responsible for
    pagination and API-specific limits.

    Coinbase Exchange does not provide native 4H candles, so 4H is
    deterministically derived from 1H candles.
    """

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware")

    if start >= end:
        raise ValueError("start must be before end")

    if timeframe == "4H":
        source_timeframe = "1H"

        source_fetch = provider.fetch_candles(
            asset=asset,
            market=market,
            timeframe=source_timeframe,
            start=start,
            end=end,
        )

        aggregated = aggregate_candles(
            source_fetch.candles,
            source_timeframe=source_timeframe,
            target_timeframe=timeframe,
        )

        fetch = ProviderFetch(
            candles=aggregated,
            provenance=source_fetch.provenance,
            raw_pages=source_fetch.raw_pages,
            limitations=(
                f"{source_fetch.limitations} "
                "4H candles were deterministically aggregated from "
                "1H candles."
            ).strip(),
        )
    else:
        fetch = provider.fetch_candles(
            asset=asset,
            market=market,
            timeframe=timeframe,
            start=start,
            end=end,
        )

    coverage = build_historical_coverage(
        fetch,
        start,
        end,
        asset=asset,
        market=market,
        timeframe=timeframe,
    )

    warnings: list[str] = []

    if not fetch.candles:
        warnings.append(
            "Provider returned no candles for the requested historical window."
        )
    else:
        actual_start = coverage.actual_start
        actual_end = coverage.actual_end

        if actual_start is not None and actual_start > start:
            warnings.append(
                "Provider history begins after the requested start; "
                "earlier history was not fabricated."
            )

        if actual_end is not None and actual_end < end:
            warnings.append(
                "Provider history ends before the requested end; "
                "later history was not fabricated."
            )

    return HistoricalAcquisition(
        fetch=fetch,
        coverage=coverage,
        warnings=warnings,
    )
