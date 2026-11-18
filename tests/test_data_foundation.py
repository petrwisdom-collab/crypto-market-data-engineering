from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.crypto_intelligence.data.models import Candle, Provenance
from src.crypto_intelligence.data.providers import CoinbaseProvider, KrakenProvider, MarketDataProvider
from src.crypto_intelligence.data.reconciliation import ReconciliationThresholds, reconcile
from src.crypto_intelligence.data.storage import VersionedDatasetStore
from src.crypto_intelligence.data.validation import CandleValidator, aggregate_candles


def candle(hour: int, close: float = 100.0, volume: float = 1.0) -> Candle:
    stamp = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hour)
    return Candle(stamp, close - 1, close + 2, close - 2, close, volume)


class ProviderTests(unittest.TestCase):
    def test_providers_implement_interface_and_coinbase_paginates(self):
        calls = []
        def open_coinbase(url):
            calls.append(url)
            return [[1704067200, "99", "102", "100", "101", "10"]]
        provider = CoinbaseProvider("https://example.test", pause=0, opener=open_coinbase)
        self.assertIsInstance(provider, MarketDataProvider)
        result = provider.fetch_candles("BTC", "BTC-USD", "1H", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 30, tzinfo=timezone.utc))
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.candles[0].timestamp.tzinfo, timezone.utc)
        self.assertEqual(result.provenance.market, "BTC-USD")

    def test_kraken_parses_source_specific_ohlcv(self):
        def open_kraken(_):
            return {"error": [], "result": {"XXBTZUSD": [[1704067200, "100", "103", "99", "102", "101", "9", "4"]], "last": "1704070800"}}
        result = KrakenProvider("https://example.test", opener=open_kraken).fetch_candles("BTC", "XBTUSD", "1H", datetime(2024, 1, 1, tzinfo=timezone.utc), datetime(2024, 1, 2, tzinfo=timezone.utc))
        self.assertEqual(result.candles[0].high, 103.0)
        self.assertEqual(result.provenance.market, "XBTUSD")


class ValidationTests(unittest.TestCase):
    def test_hourly_data_claiming_daily_fails_regression(self):
        result = CandleValidator().validate([candle(0), candle(1)], "1D", now=datetime(2024, 1, 3, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any(item["code"] == "wrong_cadence" for item in result["findings"]))

    def test_aggregation_creates_true_daily_ohlcv_and_drops_incomplete_days(self):
        source = [candle(hour, close=100 + hour, volume=hour + 1) for hour in range(25)]
        daily = aggregate_candles(source, "1H", "1D")
        self.assertEqual(len(daily), 1)
        self.assertEqual(daily[0].open, 99)
        self.assertEqual(daily[0].high, 125)
        self.assertEqual(daily[0].low, 98)
        self.assertEqual(daily[0].close, 123)
        self.assertEqual(daily[0].volume, sum(range(1, 25)))
        self.assertEqual(CandleValidator().validate(daily, "1D", now=datetime(2024, 1, 3, tzinfo=timezone.utc))["status"], "PASS")

    def test_invalid_ohlcv_duplicate_and_gap_fail(self):
        invalid_ohlc = Candle(candle(0).timestamp, 10, 9, 11, 10, 1)
        invalid_volume = Candle(candle(2).timestamp, 10, 12, 9, 11, -1)
        result = CandleValidator().validate([candle(0), candle(0), invalid_ohlc, invalid_volume, candle(5)], "1H", now=datetime(2024, 1, 2, tzinfo=timezone.utc))
        self.assertEqual(result["status"], "FAIL")
        codes = {item["code"] for item in result["findings"]}
        self.assertTrue({"duplicate_timestamp", "invalid_ohlc", "invalid_volume", "severe_gap"} <= codes)


class ReconciliationAndStorageTests(unittest.TestCase):
    def test_reconciliation_flags_significant_difference_without_merging(self):
        outcome = reconcile(
            [candle(0, 100), candle(1, 100)],
            [candle(0, 103), candle(1, 103)],
            ReconciliationThresholds(minor_bps=25, significant_bps=100),
        )
        self.assertEqual(outcome["classification"], "SIGNIFICANT_DISCREPANCY")
        self.assertEqual(outcome["overlap_count"], 2)

    def test_validated_storage_does_not_leave_csv_when_manifest_write_fails(self):
        provenance = Provenance(
            'coinbase',
            '/candles',
            datetime.now(timezone.utc),
            'BTC',
            'BTC-USD',
            '1H',
            'BTC-USD',
        )

        with tempfile.TemporaryDirectory() as root:
            store = VersionedDatasetStore(Path(root))

            with patch(
                'src.crypto_intelligence.data.storage.json.dump',
                side_effect=RuntimeError('manifest write failed'),
            ):
                with self.assertRaises(RuntimeError):
                    store.save_validated(
                        [candle(0)],
                        provenance,
                        'parent-version',
                        'validated_provider_candles',
                    )

            files = list(Path(root).rglob('*'))
            leftover_files = [path for path in files if path.is_file()]
            self.assertEqual(leftover_files, [])

    def test_versioned_raw_and_validated_storage_preserve_provenance(self):
        provenance = Provenance(
            "coinbase",
            "/candles",
            datetime.now(timezone.utc),
            "BTC",
            "BTC-USD",
            "1H",
            "BTC-USD",
        )
        with tempfile.TemporaryDirectory() as root:
            store = VersionedDatasetStore(Path(root))
            raw_version, raw_csv, raw_manifest = store.save_raw(
                [candle(0)],
                provenance,
                [{"candles": []}],
            )
            validated_version, validated_csv, validated_manifest = store.save_validated(
                [candle(0)],
                provenance,
                raw_version,
                "test",
            )
            self.assertNotEqual(raw_version, validated_version)
            self.assertTrue(
                raw_csv.exists()
                and raw_manifest.exists()
                and validated_csv.exists()
                and validated_manifest.exists()
            )
            storage_root = Path(root).resolve()
            for output_path in (raw_csv, raw_manifest, validated_csv, validated_manifest):
                self.assertTrue(output_path.resolve().is_relative_to(storage_root))
            raw_metadata = json.loads(raw_manifest.read_text(encoding="utf-8"))
            validated_metadata = json.loads(validated_manifest.read_text(encoding="utf-8"))
            self.assertEqual(raw_metadata["stored_csv_sha256"], hashlib.sha256(raw_csv.read_bytes()).hexdigest())
            self.assertEqual(validated_metadata["stored_csv_sha256"], hashlib.sha256(validated_csv.read_bytes()).hexdigest())

    def test_storage_does_not_leave_csv_when_manifest_write_fails(self):
        provenance = Provenance(
            "coinbase",
            "/candles",
            datetime.now(timezone.utc),
            "BTC",
            "BTC-USD",
            "1H",
            "BTC-USD",
        )

        with tempfile.TemporaryDirectory() as root:
            store = VersionedDatasetStore(Path(root))

            with patch(
                "src.crypto_intelligence.data.storage.json.dump",
                side_effect=RuntimeError("manifest write failed"),
            ):
                with self.assertRaises(RuntimeError):
                    store.save_raw(
                        [candle(0)],
                        provenance,
                        [{"candles": []}],
                    )

            files = list(Path(root).rglob("*"))
            final_csv_files = [
                path for path in files
                if path.is_file() and path.suffix == ".csv"
            ]

            self.assertEqual(final_csv_files, [])

    def test_storage_accepts_supported_market_names_and_rejects_unsafe_components(self):
        valid_components = (
            ("coingecko", "BTC", "1h"),
            ("coinbase", "BTC-USD", "1h"),
            ("binance_spot", "BTCUSDT", "4h"),
        )
        for provider, market, timeframe in valid_components:
            with self.subTest(provider=provider, market=market, timeframe=timeframe), tempfile.TemporaryDirectory() as root:
                provenance = Provenance(
                    provider, "/candles", datetime.now(timezone.utc), "BTC", market, timeframe, market
                )
                _, csv_path, _ = VersionedDatasetStore(Path(root)).save_raw(
                    [candle(0)], provenance, []
                )
                self.assertEqual(csv_path.parent.name, timeframe)
                self.assertTrue(csv_path.resolve().is_relative_to(Path(root).resolve()))

        unsafe_values = (
            "../outside",
            "..\\outside",
            "/absolute",
            "C:\\outside",
            "C:relative",
            "\\\\server\\share",
            "\\outside",
            "BTC/USD",
            "BTC\\USD",
        )
        for field in ("provider", "market", "timeframe"):
            for value in unsafe_values:
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as root:
                    fields = {
                        "provider": "coinbase",
                        "market": "BTC-USD",
                        "timeframe": "1h",
                    }
                    fields[field] = value
                    provenance = Provenance(
                        fields["provider"], "/candles", datetime.now(timezone.utc), "BTC",
                        fields["market"], fields["timeframe"], "source",
                    )
                    with self.assertRaises(ValueError):
                        VersionedDatasetStore(Path(root)).save_raw([candle(0)], provenance, [])
