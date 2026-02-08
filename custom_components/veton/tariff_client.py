"""Day-ahead electricity tariff client.

Supports:
- EnergyZero public API (free, no auth, covers NL/BE)
- Home Assistant entity fallback (for Tibber, Nordpool, ENTSO-E integrations)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import aiohttp

_LOGGER = logging.getLogger(__name__)

ENERGYZERO_BASE = "https://public.api.energyzero.nl/public/v1/prices"
ENERGYZERO_TIMEOUT = 15


@dataclass
class HourPrice:
    """A single hour's electricity price."""

    start: datetime  # UTC
    end: datetime  # UTC
    price: float  # EUR/kWh (incl. BTW/VAT)

    @property
    def is_current(self) -> bool:
        now = datetime.now(timezone.utc)
        return self.start <= now < self.end


@dataclass
class TariffData:
    """Collection of hourly prices for today and optionally tomorrow."""

    prices: list[HourPrice]
    fetched_at: datetime
    source: str = "energyzero"

    @property
    def current_price(self) -> float | None:
        for p in self.prices:
            if p.is_current:
                return p.price
        return None

    @property
    def today_prices(self) -> list[HourPrice]:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        return [p for p in self.prices if today_start <= p.start < today_end]

    @property
    def tomorrow_prices(self) -> list[HourPrice]:
        now = datetime.now(timezone.utc)
        tomorrow_start = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        tomorrow_end = tomorrow_start + timedelta(days=1)
        return [p for p in self.prices if tomorrow_start <= p.start < tomorrow_end]

    @property
    def has_tomorrow(self) -> bool:
        return len(self.tomorrow_prices) > 0

    @property
    def today_min(self) -> float | None:
        prices = self.today_prices
        return min(p.price for p in prices) if prices else None

    @property
    def today_max(self) -> float | None:
        prices = self.today_prices
        return max(p.price for p in prices) if prices else None

    @property
    def today_avg(self) -> float | None:
        prices = self.today_prices
        if not prices:
            return None
        return sum(p.price for p in prices) / len(prices)

    def cheapest_hours(self, count: int, after: datetime | None = None) -> list[HourPrice]:
        """Return the N cheapest upcoming hours."""
        now = after or datetime.now(timezone.utc)
        upcoming = [p for p in self.prices if p.start >= now]
        upcoming.sort(key=lambda p: p.price)
        return upcoming[:count]

    def is_cheap_now(self, threshold: float | None = None) -> bool:
        """Check if the current price is below threshold or below average."""
        current = self.current_price
        if current is None:
            return False
        if threshold is not None:
            return current <= threshold
        avg = self.today_avg
        if avg is None:
            return False
        return current <= avg


class TariffClient:
    """Fetches day-ahead electricity prices from EnergyZero."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._cache: TariffData | None = None
        self._cache_date: date | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=ENERGYZERO_TIMEOUT)
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_prices(self, force: bool = False) -> TariffData:
        """Fetch today's (and tomorrow's if available) prices.

        Caches results and only re-fetches when:
        - The date has changed
        - We don't have tomorrow's prices yet and it's after 14:00 UTC
        - force=True
        """
        now = datetime.now(timezone.utc)
        today = now.date()

        # Check if cache is still valid
        if not force and self._cache and self._cache_date == today:
            # Re-fetch after 14:00 if we don't have tomorrow's prices yet
            if self._cache.has_tomorrow or now.hour < 14:
                return self._cache

        prices: list[HourPrice] = []

        # Fetch today
        today_prices = await self._fetch_day(today)
        prices.extend(today_prices)

        # Fetch tomorrow (available after ~14:00 UTC)
        if now.hour >= 13:
            tomorrow = today + timedelta(days=1)
            tomorrow_prices = await self._fetch_day(tomorrow)
            prices.extend(tomorrow_prices)

        data = TariffData(
            prices=prices,
            fetched_at=now,
            source="energyzero",
        )
        self._cache = data
        self._cache_date = today
        return data

    async def _fetch_day(self, day: date) -> list[HourPrice]:
        """Fetch hourly prices for a single day from EnergyZero."""
        session = await self._ensure_session()
        date_str = day.strftime("%d-%m-%Y")

        try:
            async with session.get(
                ENERGYZERO_BASE,
                params={
                    "energyType": "ENERGY_TYPE_ELECTRICITY",
                    "date": date_str,
                    "interval": "INTERVAL_HOUR",
                },
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning(
                        "EnergyZero returned %s for %s", resp.status, date_str
                    )
                    return []
                data = await resp.json()
        except Exception as err:
            _LOGGER.warning("Failed to fetch prices for %s: %s", date_str, err)
            return []

        prices: list[HourPrice] = []

        # EnergyZero v1 response: prices in "base" (excl. VAT) or
        # "all_in_with_vat" (incl. everything). Fall back through formats.
        raw_prices = (
            data.get("all_in_with_vat")
            or data.get("base_with_vat")
            or data.get("base")
            or data.get("prices")
            or data.get("data")
            or []
        )

        for entry in raw_prices:
            try:
                # Current format: {start, end, price: {value}}
                start_str = entry.get("start") or entry.get("readingDate") or entry.get("timestamp") or ""
                price_obj = entry.get("price", {})
                if isinstance(price_obj, dict):
                    price_val = float(price_obj.get("value", 0.0))
                else:
                    price_val = float(price_obj)

                if not start_str:
                    continue

                start_str = start_str.replace("Z", "+00:00")
                start = datetime.fromisoformat(start_str)
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)

                end_str = entry.get("end", "")
                if end_str:
                    end_str = end_str.replace("Z", "+00:00")
                    end = datetime.fromisoformat(end_str)
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=timezone.utc)
                else:
                    end = start + timedelta(hours=1)

                prices.append(HourPrice(
                    start=start,
                    end=end,
                    price=price_val,
                ))
            except (ValueError, TypeError, KeyError) as err:
                _LOGGER.debug("Skipping price entry: %s (%s)", entry, err)
                continue

        _LOGGER.debug("Fetched %d prices for %s", len(prices), date_str)
        return prices
