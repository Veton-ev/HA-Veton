"""Energy Management System for Veton EV Charger.

Controls charging current based on:
- Solar surplus (from P1 meter grid power)
- Capacity limitation (max site current per phase)
- Combination of both

Grid power sign convention (P1 meter):
  positive = importing from grid
  negative = exporting to grid (solar surplus)

Key formula for solar surplus:
  available_power = -grid_power + charger_power
  (We add charger_power back because it's already included in grid_power)
  target_current = available_power / (nominal_voltage * num_phases)

Key formula for capacity limitation:
  Per-phase: available_current = max_site_current - (grid_current - charger_current)
  Take the minimum across all phases to stay safe.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

_LOGGER = logging.getLogger(__name__)

# Minimum charge current per IEC 61851-1
MIN_CHARGE_CURRENT_A = 6
# Assumed nominal voltage for current<->power conversion
NOMINAL_VOLTAGE_V = 230
# Number of phases (assumed 3-phase unless we can detect otherwise)
NUM_PHASES = 3
# Hysteresis: seconds to wait before pausing/resuming to avoid flapping
PAUSE_DELAY_S = 60
RESUME_DELAY_S = 60
# Smoothing: exponential moving average factor (0-1, lower = smoother)
EMA_ALPHA = 0.3


class EmsMode(StrEnum):
    """EMS operating modes."""

    OFF = "off"
    FAST = "fast"
    SOLAR_ONLY = "solar_only"
    SOLAR_MIN = "solar_min"
    CAPACITY_ONLY = "capacity_only"
    CHEAP_TARIFF = "cheap_tariff"
    SOLAR_AND_CHEAP = "solar_and_cheap"


EMS_MODE_DESCRIPTIONS = {
    EmsMode.OFF: "EMS disabled — manual control only",
    EmsMode.FAST: "Charge at maximum allowed current",
    EmsMode.SOLAR_ONLY: "Charge only from solar surplus (pauses when insufficient)",
    EmsMode.SOLAR_MIN: "Prefer solar, but maintain minimum charge rate from grid",
    EmsMode.CAPACITY_ONLY: "Limit charger to protect mains fuse (no solar logic)",
    EmsMode.CHEAP_TARIFF: "Charge only during cheapest hours of the day",
    EmsMode.SOLAR_AND_CHEAP: "Use solar surplus, charge at full speed during cheap hours",
}


@dataclass
class EmsSettings:
    """User-configurable EMS parameters."""

    mode: EmsMode = EmsMode.OFF
    max_site_current_a: int = 25  # per-phase mains fuse rating
    min_solar_surplus_w: int = 1400  # ~6A × 230V = minimum for 1-phase charging
    solar_margin_w: int = 200  # extra buffer before starting solar charge
    max_charger_current_a: int = 16  # max current the user wants for the charger
    # Tariff settings
    cheap_hours_count: int = 6  # number of cheapest hours to charge in
    price_threshold: float | None = None  # EUR/kWh; None = use average


@dataclass
class EmsResult:
    """Output of an EMS control cycle."""

    target_current_a: int = 0
    should_charge: bool = False
    reason: str = ""
    solar_surplus_w: float = 0.0
    available_site_current_a: float = 0.0
    grid_power_w: float = 0.0
    tariff_cheap_now: bool = False


class EmsController:
    """Stateful EMS controller — call `compute()` every poll cycle."""

    def __init__(self, settings: EmsSettings | None = None) -> None:
        self.settings = settings or EmsSettings()
        self._smoothed_surplus_w: float | None = None
        self._pause_requested_at: float | None = None
        self._resume_requested_at: float | None = None
        self._is_paused = False
        self.last_result = EmsResult()
        self.tariff_data = None  # set externally by coordinator

    def compute(
        self,
        grid_power_w: float,
        grid_current_l1_a: float,
        grid_current_l2_a: float,
        grid_current_l3_a: float,
        charger_power_w: float,
        charger_current_a: float,
        vehicle_connected: bool,
        charger_max_configured_a: int,
    ) -> EmsResult:
        """Run one EMS control cycle.

        Returns an EmsResult with the target current and whether to charge.
        """
        mode = self.settings.mode
        now = time.monotonic()

        # Cap at the lower of user setting and hardware max
        hard_max = min(self.settings.max_charger_current_a, charger_max_configured_a)

        if mode == EmsMode.OFF:
            return self._result(
                target_current_a=0,
                should_charge=False,
                reason="EMS disabled",
                grid_power_w=grid_power_w,
            )

        if not vehicle_connected:
            self._reset_timers()
            return self._result(
                target_current_a=0,
                should_charge=False,
                reason="No vehicle connected",
                grid_power_w=grid_power_w,
            )

        if mode == EmsMode.FAST:
            return self._result(
                target_current_a=hard_max,
                should_charge=True,
                reason=f"Fast charge at {hard_max}A",
                grid_power_w=grid_power_w,
            )

        # ── Solar surplus calculation ────────────────────────────

        # Available power = what's being exported + what the charger is already using
        raw_surplus_w = -grid_power_w + charger_power_w

        # Smooth with EMA to avoid rapid oscillation
        if self._smoothed_surplus_w is None:
            self._smoothed_surplus_w = raw_surplus_w
        else:
            self._smoothed_surplus_w = (
                EMA_ALPHA * raw_surplus_w
                + (1 - EMA_ALPHA) * self._smoothed_surplus_w
            )

        surplus_w = self._smoothed_surplus_w

        # Target current from solar
        solar_target_a = int(surplus_w / (NOMINAL_VOLTAGE_V * NUM_PHASES))

        # ── Capacity limitation calculation ──────────────────────

        # Other consumption per phase = grid current - charger current
        # (charger_current_a is total; divide by phases for per-phase estimate)
        charger_per_phase_a = charger_current_a / NUM_PHASES
        other_l1 = grid_current_l1_a - charger_per_phase_a
        other_l2 = grid_current_l2_a - charger_per_phase_a
        other_l3 = grid_current_l3_a - charger_per_phase_a

        available_per_phase = [
            self.settings.max_site_current_a - other_l1,
            self.settings.max_site_current_a - other_l2,
            self.settings.max_site_current_a - other_l3,
        ]
        capacity_target_a = int(min(available_per_phase))

        # ── Mode-specific logic ──────────────────────────────────

        if mode == EmsMode.CAPACITY_ONLY:
            target = max(MIN_CHARGE_CURRENT_A, min(capacity_target_a, hard_max))
            should_charge = target >= MIN_CHARGE_CURRENT_A
            if not should_charge:
                target = 0
            return self._result(
                target_current_a=target,
                should_charge=should_charge,
                reason=f"Capacity limit: {target}A (site headroom: {min(available_per_phase):.0f}A)",
                grid_power_w=grid_power_w,
                available_site_current_a=min(available_per_phase),
                solar_surplus_w=surplus_w,
            )

        # Solar modes — also apply capacity limit as upper bound
        if mode in (EmsMode.SOLAR_ONLY, EmsMode.SOLAR_MIN):
            # Apply capacity ceiling
            target = min(solar_target_a, capacity_target_a, hard_max)

            if mode == EmsMode.SOLAR_MIN:
                # Guarantee minimum charge even without solar
                target = max(target, MIN_CHARGE_CURRENT_A)
                target = min(target, capacity_target_a, hard_max)
                should_charge = self._apply_hysteresis(
                    target >= MIN_CHARGE_CURRENT_A, now
                )
                return self._result(
                    target_current_a=max(MIN_CHARGE_CURRENT_A, target) if should_charge else 0,
                    should_charge=should_charge,
                    reason=f"Solar+min: {target}A (surplus: {surplus_w:.0f}W)",
                    grid_power_w=grid_power_w,
                    available_site_current_a=min(available_per_phase),
                    solar_surplus_w=surplus_w,
                )

            # SOLAR_ONLY
            enough_surplus = surplus_w >= (self.settings.min_solar_surplus_w + self.settings.solar_margin_w)
            if target < MIN_CHARGE_CURRENT_A:
                # Not enough solar for minimum current
                should_charge = False
            else:
                should_charge = enough_surplus

            should_charge = self._apply_hysteresis(should_charge, now)

            if should_charge:
                target = max(MIN_CHARGE_CURRENT_A, min(target, hard_max))
            else:
                target = 0

            return self._result(
                target_current_a=target,
                should_charge=should_charge,
                reason=f"Solar only: {target}A (surplus: {surplus_w:.0f}W)",
                grid_power_w=grid_power_w,
                available_site_current_a=min(available_per_phase),
                solar_surplus_w=surplus_w,
            )

        # ── Tariff-based modes ────────────────────────────────────

        cheap_now = self._is_cheap_hour()

        if mode == EmsMode.CHEAP_TARIFF:
            if cheap_now:
                target = min(capacity_target_a, hard_max)
                target = max(MIN_CHARGE_CURRENT_A, target)
                return self._result(
                    target_current_a=target,
                    should_charge=True,
                    reason=f"Cheap hour: {target}A",
                    grid_power_w=grid_power_w,
                    available_site_current_a=min(available_per_phase),
                    solar_surplus_w=surplus_w,
                    tariff_cheap_now=True,
                )
            else:
                return self._result(
                    target_current_a=0,
                    should_charge=False,
                    reason="Waiting for cheap hour",
                    grid_power_w=grid_power_w,
                    available_site_current_a=min(available_per_phase),
                    solar_surplus_w=surplus_w,
                    tariff_cheap_now=False,
                )

        if mode == EmsMode.SOLAR_AND_CHEAP:
            # Charge from solar surplus OR during cheap hours
            solar_ok = solar_target_a >= MIN_CHARGE_CURRENT_A

            if cheap_now:
                # Cheap hour: charge at max (respecting capacity)
                target = min(capacity_target_a, hard_max)
                target = max(MIN_CHARGE_CURRENT_A, target)
                return self._result(
                    target_current_a=target,
                    should_charge=True,
                    reason=f"Cheap hour + solar: {target}A",
                    grid_power_w=grid_power_w,
                    available_site_current_a=min(available_per_phase),
                    solar_surplus_w=surplus_w,
                    tariff_cheap_now=True,
                )
            elif solar_ok:
                # Not cheap but have solar — use surplus only
                target = min(solar_target_a, capacity_target_a, hard_max)
                target = max(MIN_CHARGE_CURRENT_A, target)
                should_charge = self._apply_hysteresis(True, now)
                return self._result(
                    target_current_a=target if should_charge else 0,
                    should_charge=should_charge,
                    reason=f"Solar surplus: {target}A (surplus: {surplus_w:.0f}W)",
                    grid_power_w=grid_power_w,
                    available_site_current_a=min(available_per_phase),
                    solar_surplus_w=surplus_w,
                    tariff_cheap_now=False,
                )
            else:
                should_charge = self._apply_hysteresis(False, now)
                return self._result(
                    target_current_a=0,
                    should_charge=should_charge,
                    reason="Waiting for solar or cheap hour",
                    grid_power_w=grid_power_w,
                    available_site_current_a=min(available_per_phase),
                    solar_surplus_w=surplus_w,
                    tariff_cheap_now=False,
                )

        return self._result(
            target_current_a=0,
            should_charge=False,
            reason=f"Unknown mode: {mode}",
            grid_power_w=grid_power_w,
        )

    def _apply_hysteresis(self, want_charge: bool, now: float) -> bool:
        """Apply time-based hysteresis to avoid rapid start/stop cycling."""
        if want_charge and self._is_paused:
            # Want to resume
            if self._resume_requested_at is None:
                self._resume_requested_at = now
            if now - self._resume_requested_at >= RESUME_DELAY_S:
                self._is_paused = False
                self._resume_requested_at = None
                self._pause_requested_at = None
                return True
            return False  # still waiting to resume

        if not want_charge and not self._is_paused:
            # Want to pause
            if self._pause_requested_at is None:
                self._pause_requested_at = now
            if now - self._pause_requested_at >= PAUSE_DELAY_S:
                self._is_paused = True
                self._pause_requested_at = None
                self._resume_requested_at = None
                return False
            return True  # still waiting to pause (keep charging)

        # Clear opposite timer
        if want_charge:
            self._pause_requested_at = None
        else:
            self._resume_requested_at = None

        return want_charge

    def _is_cheap_hour(self) -> bool:
        """Check if the current hour is among the cheapest."""
        if self.tariff_data is None:
            _LOGGER.debug("No tariff data available")
            return False

        # If user set a fixed price threshold, use that
        if self.settings.price_threshold is not None:
            return self.tariff_data.is_cheap_now(self.settings.price_threshold)

        # Otherwise: check if current hour is in the N cheapest upcoming hours
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        cheapest = self.tariff_data.cheapest_hours(
            self.settings.cheap_hours_count,
            after=now.replace(minute=0, second=0, microsecond=0),
        )
        current_price = self.tariff_data.current_price
        if current_price is None:
            return False

        # Current hour is cheap if its price is <= the most expensive of the N cheapest
        if not cheapest:
            return False
        threshold = max(h.price for h in cheapest)
        return current_price <= threshold

    def _reset_timers(self) -> None:
        self._pause_requested_at = None
        self._resume_requested_at = None
        self._is_paused = False
        self._smoothed_surplus_w = None

    def _result(self, **kwargs) -> EmsResult:
        self.last_result = EmsResult(**kwargs)
        return self.last_result
