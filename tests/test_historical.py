from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from src.crypto_intelligence.data.historical import (
    acquire_historical,
    build_historical_coverage,
)
from src.crypto_intelligence.data.models import Candle, ProviderFetch, Provenance


class FakeProvider:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles

    def fetch_candles(
        self,
        asset: str,
        market: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> ProviderFetch:
        provenance = Provenance(
            provider="fake",
            endpoint="/historical",
            retrieved_at=datetime.now(timezone.utc),
            asset=asset,
            market=market,
            timeframe=timeframe,
            source_identifier=market,
        )
        return ProviderFetch(
            candles=self.candles,
            provenance=provenance,
            raw_pages=[{"fake": True}],
            limitations="Fake provider for testing.",
        )


def candle(hour: int) -> Candle:
    timestamp = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hour)
    return Candle(
        timestamp,
        99.0,
        102.0,
        98.0,
        101.0,
        10.0,
    )


class HistoricalTests(unittest.TestCase):
    def test_coverage_reports_actual_provider_window(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 4, tzinfo=timezone.utc)

        fetch = FakeProvider([candle(1), candle(2)]).fetch_candles(
            "BTC",
            "BTC-USD",
            "1H",
            start,
            end,
        )

        coverage = build_historical_coverage(
            fetch,
            start,
            end,
            asset="BTC",
            market="BTC-USD",
            timeframe="1H",
        )

        self.assertEqual(coverage.actual_start, candle(1).timestamp)
        self.assertEqual(coverage.actual_end, candle(2).timestamp)
        self.assertEqual(coverage.record_count, 2)

    def test_acquisition_warns_when_provider_starts_late(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 4, tzinfo=timezone.utc)

        result = acquire_historical(
            FakeProvider([candle(1), candle(2)]),
            "BTC",
            "BTC-USD",
            "1H",
            start,
            end,
        )

        self.assertEqual(len(result.candles), 2)
        self.assertTrue(
            any("begins after the requested start" in warning for warning in result.warnings)
        )

    def test_acquisition_warns_when_provider_ends_early(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 4, tzinfo=timezone.utc)

        result = acquire_historical(
            FakeProvider([candle(1), candle(2)]),
            "BTC",
            "BTC-USD",
            "1H",
            start,
            end,
        )

        self.assertTrue(
            any("ends before the requested end" in warning for warning in result.warnings)
        )


if __name__ == "__main__":
    unittest.main()