from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..data.models import Candle


@dataclass(frozen=True)
class ReplayState:
    """The information visible to the research system at one replay step."""

    index: int
    timestamp: datetime
    candle: Candle
    history: tuple[Candle, ...]


class HistoricalReplay:
    """Chronologically replay validated historical candles without future leakage."""

    def __init__(self, candles: list[Candle]) -> None:
        ordered = sorted(candles, key=lambda candle: candle.timestamp)

        if not ordered:
            raise ValueError("Replay requires at least one candle")

        timestamps = [candle.timestamp for candle in ordered]
        if len(timestamps) != len(set(timestamps)):
            raise ValueError("Replay candles must have unique timestamps")

        self._candles = tuple(ordered)
        self._index = -1

    @property
    def total_steps(self) -> int:
        return len(self._candles)

    @property
    def current_index(self) -> int:
        return self._index

    @property
    def finished(self) -> bool:
        return self._index >= len(self._candles) - 1

    def reset(self) -> None:
        self._index = -1

    def step(self) -> ReplayState | None:
        """Advance exactly one candle and expose only information available then."""
        if self.finished:
            return None

        self._index += 1
        candle = self._candles[self._index]

        return ReplayState(
            index=self._index,
            timestamp=candle.timestamp,
            candle=candle,
            history=self._candles[: self._index + 1],
        )

    def run(self):
        """Yield replay states in strict chronological order."""
        self.reset()

        while True:
            state = self.step()
            if state is None:
                break
            yield state
