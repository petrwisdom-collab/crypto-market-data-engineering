from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class Candle:
    """A source-specific, UTC-normalized OHLCV candle. Timestamp is candle open."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["timestamp"] = self.timestamp.astimezone(timezone.utc).isoformat()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Candle":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            open=float(data["open"]),
            high=float(data["high"]),
            low=float(data["low"]),
            close=float(data["close"]),
            volume=None if data["volume"] is None else float(data["volume"]),
        )


@dataclass(frozen=True)
class Provenance:
    provider: str
    endpoint: str
    retrieved_at: datetime
    asset: str
    market: str
    timeframe: str
    source_identifier: str
    request_parameters: dict[str, Any] = field(default_factory=dict)
    request_window: dict[str, str] = field(default_factory=dict)
    response_identifiers: list[str] = field(default_factory=list)
    timezone: str = "UTC"
    completeness_note: str = "Provider-returned data; no missing values are filled."

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["retrieved_at"] = self.retrieved_at.astimezone(timezone.utc).isoformat()
        return result

@dataclass(frozen=True)
class ProviderFetch:
    candles: list[Candle]
    provenance: Provenance
    raw_pages: list[Any]
    limitations: str

