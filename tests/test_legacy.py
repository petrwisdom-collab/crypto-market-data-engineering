from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from src.crypto_intelligence.data.legacy import audit_legacy_price_csv


class LegacyAuditTests(unittest.TestCase):
    def test_hourly_legacy_prices_claimed_as_daily_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            source, report = Path(directory) / "legacy.csv", Path(directory) / "audit.json"
            source.write_text("timestamp,price_usd,volume_usd\n2024-01-01T00:00:00+00:00,100,1\n2024-01-01T01:00:00+00:00,101,1\n", encoding="utf-8")
            result = audit_legacy_price_csv(source, "1D", report)
            self.assertEqual(result["validation_status"], "FAIL")
            self.assertTrue(report.exists())
