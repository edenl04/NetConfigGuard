from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from netconfigguard.models import Device
from netconfigguard.yamlio import read_yaml, write_yaml


class MaintenanceError(ValueError):
    pass


@dataclass(frozen=True)
class MaintenanceWindow:
    id: str
    start: datetime
    end: datetime | None
    devices: tuple[str, ...] = ()
    sites: tuple[str, ...] = ()
    reason: str = ""
    approver: str = ""
    ticket: str = ""
    manual: bool = False

    def is_active(self, now: datetime) -> bool:
        return self.start <= now and (self.end is None or now <= self.end)

    def is_ended(self, now: datetime) -> bool:
        return self.end is not None and now > self.end

    def matches(self, device: Device) -> bool:
        return not self.devices and not self.sites or device.name in self.devices or bool(device.site and device.site in self.sites)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "devices": list(self.devices),
            "sites": list(self.sites),
            "reason": self.reason,
            "approver": self.approver,
            "ticket": self.ticket,
            "manual": self.manual,
        }


def load_maintenance_windows(scheduled_path: Path, manual_path: Path) -> list[MaintenanceWindow]:
    windows: list[MaintenanceWindow] = []
    windows.extend(_load_windows_from_file(scheduled_path, manual=False))
    windows.extend(_load_windows_from_file(manual_path, manual=True))
    return windows


def active_window_for(device: Device, windows: list[MaintenanceWindow], now: datetime) -> MaintenanceWindow | None:
    for window in windows:
        if window.is_active(now) and window.matches(device):
            return window
    return None


def ended_window_for(device: Device, windows: list[MaintenanceWindow], now: datetime, window_id: str | None = None) -> MaintenanceWindow | None:
    for window in windows:
        if window_id and window.id != window_id:
            continue
        if window.is_ended(now) and window.matches(device):
            return window
    return None


def start_manual_maintenance(
    path: Path,
    devices: list[str],
    sites: list[str],
    reason: str,
    approver: str = "",
    ticket: str = "",
    duration_minutes: int | None = None,
    now: datetime | None = None,
) -> MaintenanceWindow:
    start = now or datetime.now(timezone.utc)
    end = start + timedelta(minutes=duration_minutes) if duration_minutes else None
    if not devices and not sites:
        raise MaintenanceError("Manual maintenance requires at least one device or site")
    window = MaintenanceWindow(
        id=f"manual-{uuid4().hex[:12]}",
        start=start,
        end=end,
        devices=tuple(devices),
        sites=tuple(sites),
        reason=reason,
        approver=approver,
        ticket=ticket,
        manual=True,
    )
    data = read_yaml(path) or {"windows": []}
    data.setdefault("windows", []).append(window.to_dict())
    write_yaml(path, data)
    return window


def stop_manual_maintenance(path: Path, devices: list[str], sites: list[str], stop_all: bool, now: datetime | None = None) -> list[str]:
    data = read_yaml(path) or {"windows": []}
    stopped: list[str] = []
    stop_time = now or datetime.now(timezone.utc)
    updated = []
    for raw in data.get("windows", []):
        window = _parse_window(raw, manual=True)
        should_stop = stop_all or bool(set(devices) & set(window.devices)) or bool(set(sites) & set(window.sites))
        if should_stop and (window.end is None or window.end > stop_time):
            raw = dict(raw)
            raw["end"] = stop_time.isoformat()
            stopped.append(window.id)
        updated.append(raw)
    write_yaml(path, {"windows": updated})
    return stopped


def _load_windows_from_file(path: Path, manual: bool) -> list[MaintenanceWindow]:
    data = read_yaml(path)
    if data is None:
        return []
    if not isinstance(data, dict) or not isinstance(data.get("windows", []), list):
        raise MaintenanceError(f"Invalid maintenance file: {path}")
    return [_parse_window(raw, manual=manual) for raw in data.get("windows", [])]


def _parse_window(raw: dict[str, Any], manual: bool) -> MaintenanceWindow:
    try:
        start = _parse_datetime(raw["start"])
        end = _parse_datetime(raw["end"]) if raw.get("end") else None
    except KeyError as exc:
        raise MaintenanceError("Maintenance window is missing start") from exc
    return MaintenanceWindow(
        id=str(raw.get("id") or f"window-{uuid4().hex[:8]}"),
        start=start,
        end=end,
        devices=tuple(str(item) for item in raw.get("devices", []) or []),
        sites=tuple(str(item) for item in raw.get("sites", []) or []),
        reason=str(raw.get("reason", "") or ""),
        approver=str(raw.get("approver", "") or ""),
        ticket=str(raw.get("ticket", "") or ""),
        manual=bool(raw.get("manual", manual)),
    )


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MaintenanceError("Maintenance timestamps must include a timezone offset")
    return parsed

