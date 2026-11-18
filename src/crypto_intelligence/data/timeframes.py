from __future__ import annotations


TIMEFRAME_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1H": 3600,
    "2H": 7200,
    "4H": 14400,
    "6H": 21600,
    "12H": 43200,
    "1D": 86400,
    "1W": 604800,
}


SUPPORTED_TIMEFRAMES = tuple(TIMEFRAME_SECONDS)


def normalize_timeframe(timeframe: str) -> str:
    """Normalize a timeframe to the canonical internal representation."""

    if not isinstance(timeframe, str):
        raise TypeError("timeframe must be a string")

    value = timeframe.strip()

    aliases = {
        "1m": "1min",
        "5m": "5min",
        "5M": "5min",
        "15m": "15min",
        "15M": "15min",
        "30m": "30min",
        "30M": "30min",
        "1h": "1H",
        "2h": "2H",
        "4h": "4H",
        "6h": "6H",
        "12h": "12H",
        "1d": "1D",
        "1w": "1W",
    }

    value = aliases.get(value, value)

    if value not in TIMEFRAME_SECONDS:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    return value


def timeframe_seconds(timeframe: str) -> int:
    """Return the duration of a timeframe in seconds."""

    return TIMEFRAME_SECONDS[normalize_timeframe(timeframe)]


def timeframe_rank(timeframe: str) -> int:
    """Return the chronological rank of a timeframe."""

    return timeframe_seconds(timeframe)


def is_higher_timeframe(first: str, second: str) -> bool:
    """Return True when the first timeframe is larger than the second."""

    return timeframe_seconds(first) > timeframe_seconds(second)


def is_lower_timeframe(first: str, second: str) -> bool:
    """Return True when the first timeframe is smaller than the second."""

    return timeframe_seconds(first) < timeframe_seconds(second)