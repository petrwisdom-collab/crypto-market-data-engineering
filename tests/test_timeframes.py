import unittest

from src.crypto_intelligence.data.timeframes import (
    SUPPORTED_TIMEFRAMES,
    TIMEFRAME_SECONDS,
    is_higher_timeframe,
    is_lower_timeframe,
    normalize_timeframe,
    timeframe_rank,
    timeframe_seconds,
)


class TestTimeframes(unittest.TestCase):

    def test_supported_timeframes(self):
        self.assertEqual(
            SUPPORTED_TIMEFRAMES,
            (
                "1min",
                "5min",
                "15min",
                "30min",
                "1H",
                "2H",
                "4H",
                "6H",
                "12H",
                "1D",
                "1W",
            ),
        )

    def test_timeframe_seconds(self):
        self.assertEqual(timeframe_seconds("1min"), 60)
        self.assertEqual(timeframe_seconds("5min"), 300)
        self.assertEqual(timeframe_seconds("1H"), 3600)
        self.assertEqual(timeframe_seconds("4H"), 14400)
        self.assertEqual(timeframe_seconds("1D"), 86400)

    def test_alias_normalization(self):
        self.assertEqual(normalize_timeframe("1m"), "1min")
        self.assertEqual(normalize_timeframe("5m"), "5min")
        self.assertEqual(normalize_timeframe("15m"), "15min")
        self.assertEqual(normalize_timeframe("30m"), "30min")
        self.assertEqual(normalize_timeframe("1h"), "1H")
        self.assertEqual(normalize_timeframe("4h"), "4H")
        self.assertEqual(normalize_timeframe("1d"), "1D")

    def test_timeframe_order(self):
        self.assertLess(timeframe_rank("1min"), timeframe_rank("5min"))
        self.assertLess(timeframe_rank("15min"), timeframe_rank("1H"))
        self.assertLess(timeframe_rank("1H"), timeframe_rank("4H"))
        self.assertLess(timeframe_rank("4H"), timeframe_rank("1D"))
        self.assertLess(timeframe_rank("1D"), timeframe_rank("1W"))

    def test_higher_and_lower(self):
        self.assertTrue(is_higher_timeframe("4H", "1H"))
        self.assertTrue(is_lower_timeframe("5min", "1H"))

        self.assertFalse(is_higher_timeframe("1H", "4H"))
        self.assertFalse(is_lower_timeframe("4H", "1H"))

    def test_invalid_timeframe(self):
        with self.assertRaises(ValueError):
            normalize_timeframe("10min")

        with self.assertRaises(ValueError):
            normalize_timeframe("1Month")

    def test_invalid_type(self):
        with self.assertRaises(TypeError):
            normalize_timeframe(60)


if __name__ == "__main__":
    unittest.main()