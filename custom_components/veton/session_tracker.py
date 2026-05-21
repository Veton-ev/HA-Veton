"""Charging session tracker with RFID logging and CSV export."""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .modbus_client import CharxConnectorData

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

SESSIONS_FILENAME = "veton_sessions_{entry_id}.json"
MAX_SESSIONS = 10000


@dataclass
class ChargingSession:
    """A single charging session record."""

    id: int = 0
    started: str = ""
    ended: str = ""
    rfid_uid: str = ""
    evcc_id: str = ""
    energy_wh: int = 0
    duration_s: int = 0
    max_power_w: int = 0
    connector: int = 1
    vehicle_status_start: str = ""


@dataclass
class SessionTrackerState:
    """Persistent state for the session tracker."""

    sessions: list[dict] = field(default_factory=list)
    next_id: int = 1


class SessionTracker:
    """Tracks charging sessions, detecting start/stop transitions.

    Disk I/O is always done on the executor so it never blocks the event loop.
    Call ``await load()`` once during setup, then ``await update(...)`` every
    poll cycle.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._hass = hass
        self._entry_id = entry_id
        self._storage_path = Path(hass.config.path(
            ".storage", SESSIONS_FILENAME.format(entry_id=entry_id)
        ))
        self._state = SessionTrackerState()
        self._current_session: ChargingSession | None = None
        self._was_charging = False
        self._peak_power_w = 0
        self._loaded = False

    @property
    def sessions(self) -> list[ChargingSession]:
        """Return all recorded sessions."""
        return [ChargingSession(**s) for s in self._state.sessions]

    @property
    def current_session(self) -> ChargingSession | None:
        """Return the active session, if any."""
        return self._current_session

    @property
    def session_count(self) -> int:
        return len(self._state.sessions)

    async def load(self) -> None:
        """Load persisted sessions from disk (once), on the executor."""
        if self._loaded:
            return
        self._loaded = True
        await self._hass.async_add_executor_job(self._read_from_disk)

    def _read_from_disk(self) -> None:
        """Blocking read of the sessions file — executor only."""
        if self._storage_path.exists():
            try:
                raw = json.loads(self._storage_path.read_text())
                self._state = SessionTrackerState(
                    sessions=raw.get("sessions", []),
                    next_id=raw.get("next_id", 1),
                )
            except (json.JSONDecodeError, KeyError, OSError):
                _LOGGER.warning("Could not load session history, starting fresh")

    def _write_to_disk(self) -> None:
        """Blocking write of the sessions file — executor only."""
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps({
            "sessions": self._state.sessions[-MAX_SESSIONS:],
            "next_id": self._state.next_id,
        }, indent=2))

    async def update(self, data: CharxConnectorData) -> None:
        """Called every poll cycle. Detects session start/end."""
        await self.load()

        is_charging = data.vehicle_status in ("C1", "C2")

        # Track peak power during the active session
        if is_charging and self._current_session:
            power_w = abs(data.active_power_mw) // 1000
            if power_w > self._peak_power_w:
                self._peak_power_w = power_w

        # Transition: not charging -> charging = new session
        if is_charging and not self._was_charging:
            self._current_session = ChargingSession(
                id=self._state.next_id,
                started=datetime.now(timezone.utc).isoformat(),
                rfid_uid=data.rfid_uid,
                evcc_id=data.evcc_id,
                vehicle_status_start=data.vehicle_status,
            )
            self._peak_power_w = abs(data.active_power_mw) // 1000
            self._state.next_id += 1
            _LOGGER.info(
                "Charging session #%d started (RFID: %s)",
                self._current_session.id,
                data.rfid_uid or "none",
            )

        # Transition: charging -> not charging = session ended
        if not is_charging and self._was_charging and self._current_session:
            self._current_session.ended = datetime.now(timezone.utc).isoformat()
            self._current_session.energy_wh = data.session_energy_wh
            self._current_session.duration_s = data.charging_time_s
            self._current_session.max_power_w = self._peak_power_w

            self._state.sessions.append(asdict(self._current_session))
            await self._hass.async_add_executor_job(self._write_to_disk)

            _LOGGER.info(
                "Charging session #%d ended: %d Wh in %d s",
                self._current_session.id,
                self._current_session.energy_wh,
                self._current_session.duration_s,
            )
            self._current_session = None
            self._peak_power_w = 0

        self._was_charging = is_charging

    def export_csv(self) -> str:
        """Export all recorded sessions as a CSV string (uses in-memory state)."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Session ID", "Started (UTC)", "Ended (UTC)", "RFID UID",
            "EVCC ID", "Energy (Wh)", "Energy (kWh)", "Duration (s)",
            "Duration (min)", "Max Power (W)", "Connector",
        ])
        for s in self._state.sessions:
            session = ChargingSession(**s)
            writer.writerow([
                session.id,
                session.started,
                session.ended,
                session.rfid_uid,
                session.evcc_id,
                session.energy_wh,
                round(session.energy_wh / 1000, 2),
                session.duration_s,
                round(session.duration_s / 60, 1),
                session.max_power_w,
                session.connector,
            ])
        return output.getvalue()
