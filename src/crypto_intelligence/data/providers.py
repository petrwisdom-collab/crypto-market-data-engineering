from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
import json
import logging
import time
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from .models import Candle, ProviderFetch, Provenance
from .timeframes import TIMEFRAME_SECONDS, normalize_timeframe, timeframe_seconds

LOGGER = logging.getLogger(__name__)

class MarketDataProvider(ABC):
    """Provider boundary. Candles are never merged across providers/markets."""
    name: str

    @abstractmethod
    def fetch_candles(self, asset: str, market: str, timeframe: str, start: datetime, end: datetime) -> ProviderFetch:
        """Fetch source-native candles or raise ValueError when unavailable."""


class HttpProvider(MarketDataProvider):
    def __init__(self, base_url: str, timeout: float = 30, max_retries: int = 3, backoff: float = 2, pause: float = 1.0, opener: Callable[[str], Any] | None = None) -> None:
        self.base_url, self.timeout, self.max_retries, self.backoff, self.pause = base_url.rstrip("/"), timeout, max_retries, backoff, pause
        self.opener = opener or self._open

    def _open(self, url: str) -> Any:
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "crypto-market-intelligence/0.2"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get(self, url: str) -> Any:
        for attempt in range(self.max_retries + 1):
            try:
                return self.opener(url)
            except Exception as error:
                if attempt == self.max_retries:
                    raise RuntimeError(f"{self.name} request failed after {attempt + 1} attempts: {error}") from error
                delay = self.backoff * (2 ** attempt)
                LOGGER.warning("%s request failed (%s); retrying in %.1fs", self.name, error, delay)
                time.sleep(delay)
        raise AssertionError("unreachable")

    @staticmethod
    def _window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("start/end must be timezone-aware and start < end")
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


class CoinGeckoProvider(HttpProvider):
    name = "coingecko"
    asset_ids = {"BTC": "bitcoin", "ETH": "ethereum", "XRP": "ripple", "SOL": "solana", "BNB": "binancecoin", "ADA": "cardano", "DOGE": "dogecoin"}

    def fetch_candles(self, asset: str, market: str, timeframe: str, start: datetime, end: datetime) -> ProviderFetch:
        if asset.upper() not in self.asset_ids or timeframe not in TIMEFRAME_SECONDS:
            raise ValueError(f"CoinGecko cannot provide requested asset/timeframe: {asset}/{timeframe}")
        start, end = self._window(start, end)
        coin_id, endpoint, pages, rows, cursor = self.asset_ids[asset.upper()], f"/coins/{self.asset_ids[asset.upper()]}/market_chart/range", [], {}, start
        while cursor < end:
            page_end = min(cursor + timedelta(days=90), end)
            params = {"vs_currency": "usd", "from": int(cursor.timestamp()), "to": int(page_end.timestamp())}
            payload = self._get(f"{self.base_url}{endpoint}?{urlencode(params)}")
            pages.append(payload)
            volumes = {int(ts): value for ts, value in payload.get("total_volumes", [])}
            for ts_ms, price in payload.get("prices", []):
                stamp = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                rows[stamp] = Candle(stamp, float(price), float(price), float(price), float(price), float(volumes[ts_ms]) if ts_ms in volumes else None)
            cursor = page_end
            if cursor < end:
                time.sleep(self.pause)
        provenance = Provenance(self.name, endpoint, datetime.now(timezone.utc), asset.upper(), market, timeframe, coin_id, {"vs_currency": "usd"}, {"start": start.isoformat(), "end": end.isoformat()})
        return ProviderFetch(sorted(rows.values(), key=lambda item: item.timestamp), provenance, pages, "CoinGecko market_chart/range yields price observations and rolling volume, not exchange-native OHLCV. Its actual cadence is validated and it must not be merged with exchange candles.")


class CoinbaseProvider(HttpProvider):
    name = "coinbase"
    granularities = {"1M": 60, "5M": 300, "15M": 900, "1H": 3600, "4H": 14400, "1D": 86400}

    def fetch_candles(self, asset: str, market: str, timeframe: str, start: datetime, end: datetime) -> ProviderFetch:
        if timeframe not in self.granularities:
            raise ValueError(f"Coinbase does not expose requested timeframe {timeframe}")
        start, end = self._window(start, end)
        endpoint, pages, rows, cursor = f"/products/{market}/candles", [], {}, start
        max_window = timedelta(seconds=TIMEFRAME_SECONDS[timeframe] * 300)
        while cursor < end:
            page_end = min(cursor + max_window, end)
            params = {"start": cursor.isoformat(), "end": page_end.isoformat(), "granularity": self.granularities[timeframe]}
            payload = self._get(f"{self.base_url}{endpoint}?{urlencode(params)}")
            pages.append(payload)
            for item in payload:
                stamp = datetime.fromtimestamp(int(item[0]), tz=timezone.utc)
                rows[stamp] = Candle(stamp, float(item[3]), float(item[2]), float(item[1]), float(item[4]), float(item[5]))
            cursor = page_end
            if cursor < end:
                time.sleep(self.pause)
        provenance = Provenance(self.name, endpoint, datetime.now(timezone.utc), asset.upper(), market, timeframe, market, {"granularity_seconds": self.granularities[timeframe]}, {"start": start.isoformat(), "end": end.isoformat()})
        return ProviderFetch(sorted(rows.values(), key=lambda item: item.timestamp), provenance, pages, "Coinbase Exchange public candles are source-specific to the requested product. Requests are paginated at 300 candles; actual received coverage is reported per dataset.")

class KrakenProvider(HttpProvider):
    name = "kraken"
    intervals = {"1M": 1, "5M": 5, "15M": 15, "1H": 60, "4H": 240, "1D": 1440, "1W": 10080}

    def fetch_candles(self, asset: str, market: str, timeframe: str, start: datetime, end: datetime) -> ProviderFetch:
        if timeframe not in self.intervals:
            raise ValueError(f"Kraken does not expose requested timeframe {timeframe}")
        start, end = self._window(start, end)
        endpoint, params = "/0/public/OHLC", {"pair": market, "interval": self.intervals[timeframe], "since": int(start.timestamp())}
        payload = self._get(f"{self.base_url}{endpoint}?{urlencode(params)}")
        if payload.get("error"):
            raise RuntimeError(f"Kraken API error: {payload['error']}")
        result = payload.get("result", {})
        series_key = next((key for key in result if key != "last"), None)
        if series_key is None:
            raise RuntimeError("Kraken response did not include an OHLC series")
        candles = [Candle(datetime.fromtimestamp(int(item[0]), tz=timezone.utc), float(item[1]), float(item[2]), float(item[3]), float(item[4]), float(item[6])) for item in result[series_key] if start <= datetime.fromtimestamp(int(item[0]), tz=timezone.utc) < end]
        provenance = Provenance(self.name, endpoint, datetime.now(timezone.utc), asset.upper(), market, timeframe, series_key, params, {"start": start.isoformat(), "end": end.isoformat()}, [str(result.get("last", ""))])
        return ProviderFetch(sorted(candles, key=lambda item: item.timestamp), provenance, [payload], "Kraken OHLC returns a provider-limited recent window (typically up to 720 entries); the final candle may be in progress and is flagged by validation.")


class BinanceSpotProvider(HttpProvider):
    """Binance Spot klines with UTC candle-open timestamps and bounded pagination."""

    name = "binance_spot"
    interval_codes = {"1H": "1h"}
    page_limit = 1000

    def fetch_candles(self, asset: str, market: str, timeframe: str, start: datetime, end: datetime) -> ProviderFetch:
        if asset.upper() != "BTC" or market.upper() != "BTCUSDT":
            raise ValueError("Binance Spot provider is scoped to BTC/BTCUSDT; preserve the BTC/USDT market identity.")
        if timeframe not in self.interval_codes:
            raise ValueError("Binance Spot acquisition currently supports only 1H klines.")
        start, end = self._window(start, end)
        interval_ms = TIMEFRAME_SECONDS[timeframe] * 1000
        start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
        if start_ms % interval_ms or end_ms % interval_ms:
            raise ValueError("Binance Spot 1H request boundaries must align to UTC hour opens.")

        endpoint, pages, candles = "/api/v3/klines", [], []
        retrieved_at = datetime.now(timezone.utc)
        closed_through = min(end, retrieved_at)
        cursor = start_ms
        last_open_ms = None
        expected_slots = (end_ms - start_ms) // interval_ms
        max_pages = max(1, (expected_slots + self.page_limit - 1) // self.page_limit)
        page_count = 0
        while cursor < end_ms:
            if page_count >= max_pages:
                raise RuntimeError("Binance Spot pagination exceeded the maximum pages implied by the requested window.")
            params = {"symbol": market.upper(), "interval": self.interval_codes[timeframe], "startTime": cursor, "endTime": end_ms - 1, "limit": self.page_limit}
            payload = self._get(f"{self.base_url}{endpoint}?{urlencode(params)}")
            page_count += 1
            if not isinstance(payload, list):
                raise RuntimeError("Binance Spot klines response must be a list.")
            pages.append(payload)
            if not payload:
                break
            for item in payload:
                if not isinstance(item, (list, tuple)) or len(item) < 6:
                    raise RuntimeError("Binance Spot returned a malformed kline row.")
                try:
                    opened_ms = int(item[0])
                except (TypeError, ValueError) as error:
                    raise RuntimeError("Binance Spot returned a malformed kline timestamp.") from error
                if opened_ms % interval_ms:
                    raise RuntimeError("Binance Spot returned a kline timestamp not aligned to a UTC hour.")
                if opened_ms < cursor:
                    raise RuntimeError("Binance Spot returned an overlapping page before the active cursor.")
                if last_open_ms is not None and opened_ms <= last_open_ms:
                    raise RuntimeError("Binance Spot returned duplicate or out-of-order klines across pages.")
                last_open_ms = opened_ms
                if start_ms <= opened_ms < end_ms and datetime.fromtimestamp((opened_ms + interval_ms) / 1000, tz=timezone.utc) <= closed_through:
                    stamp = datetime.fromtimestamp(opened_ms / 1000, tz=timezone.utc)
                    candles.append(Candle(stamp, float(item[1]), float(item[2]), float(item[3]), float(item[4]), float(item[5])))
            next_cursor = int(payload[-1][0]) + interval_ms
            if next_cursor <= cursor:
                raise RuntimeError("Binance Spot pagination did not advance.")
            cursor = next_cursor
            if len(payload) < self.page_limit:
                break
            if cursor < end_ms:
                time.sleep(self.pause)

        provenance = Provenance(
            self.name, endpoint, retrieved_at, "BTC", "BTCUSDT", "1H", "BTCUSDT",
            {"symbol": "BTCUSDT", "interval": "1h", "limit": self.page_limit, "timestamp_semantics": "UTC candle open", "volume_units": "base asset (BTC) volume"},
            {"start": start.isoformat(), "end": end.isoformat()},
        )
        return ProviderFetch(candles, provenance, pages, "Binance Spot BTCUSDT 1H klines; end is exclusive, incomplete boundary candles are excluded, and gaps are preserved.")
