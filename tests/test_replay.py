from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from crypto_intelligence.data.models import Candle
from crypto_intelligence.replay.engine import HistoricalReplay


class TestHistoricalReplay(unittest.TestCase):
    def setUp(self):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.candles = [
            Candle(
                start + timedelta(hours=i),
                100 + i,
                101 + i,
                99 + i,
                100 + i,
                10.0,
            )
            for i in range(3)
        ]

    def test_chronological_replay(self):
        replay = HistoricalReplay(self.candles)
        states = list(replay.run())

        self.assertEqual(len(states), 3)
        self.assertEqual([state.index for state in states], [0, 1, 2])
        self.assertEqual(
            [state.timestamp for state in states],
            [candle.timestamp for candle in self.candles],
        )

    def test_replay_state_represents_closed_current_candle(self):
        replay = HistoricalReplay(self.candles)

        state = replay.step()

        self.assertIsNotNone(state)
        self.assertEqual(state.candle.timestamp, state.timestamp)
        self.assertEqual(state.history[-1], state.candle)
        self.assertEqual(len(state.history), state.index + 1)

    def test_no_future_candles_exposed(self):
        replay = HistoricalReplay(self.candles)

        first = replay.step()
        self.assertEqual(len(first.history), 1)
        self.assertEqual(first.history[-1].timestamp, self.candles[0].timestamp)

        second = replay.step()
        self.assertEqual(len(second.history), 2)
        self.assertEqual(second.history[-1].timestamp, self.candles[1].timestamp)

    def test_empty_input_rejected(self):
        with self.assertRaises(ValueError):
            HistoricalReplay([])

    def test_duplicate_timestamps_rejected(self):
        with self.assertRaises(ValueError):
            HistoricalReplay([self.candles[0], self.candles[0]])

    def test_completion_behavior(self):
        replay = HistoricalReplay(self.candles[:2])

        self.assertIsNotNone(replay.step())
        self.assertIsNotNone(replay.step())
        self.assertTrue(replay.finished)
        self.assertIsNone(replay.step())

    def test_reset_behavior(self):
        replay = HistoricalReplay(self.candles)

        replay.step()
        replay.step()
        replay.reset()

        self.assertEqual(replay.current_index, -1)
        self.assertFalse(replay.finished)

        state = replay.step()
        self.assertEqual(state.index, 0)

    def test_synthetic_serialized_candle_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture_path = Path(directory) / "candles.json"
            fixture_path.write_text(
                json.dumps({"candles": [candle.to_dict() for candle in self.candles]}),
                encoding="utf-8",
            )

            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
            candles = [Candle.from_dict(item) for item in payload["candles"]]
            replay = HistoricalReplay(candles)
            states = list(replay.run())

            self.assertEqual(len(states), len(candles))
            self.assertTrue(replay.finished)
            for index, state in enumerate(states):
                self.assertEqual(state.index, index)
                self.assertEqual(state.timestamp, candles[index].timestamp)
                self.assertEqual(state.candle, candles[index])
                self.assertEqual(state.history, tuple(candles[: index + 1]))

if __name__ == "__main__":
    unittest.main()

