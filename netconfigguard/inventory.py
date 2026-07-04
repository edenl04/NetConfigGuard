from __future__ import annotations

from pathlib import Path
from typing import Any

from netconfigguard.models import Device
from netconfigguard.yamlio import read_yaml


class InventoryError(ValueError):
    pass


def load_inventory(path: Path) -> list[Device]:
    data = read_yaml(path)
    if data is None:
        raise InventoryError(f"Inventory file not found: {path}")
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        raise InventoryError("Inventory must contain a top-level 'devices' list")

    devices: list[Device] = []
    names: set[str] = set()
    for index, raw in enumerate(data["devices"], start=1):
        if not isinstance(raw, dict):
            raise InventoryError(f"Device #{index} must be a mapping")
        device = _parse_device(raw, index)
        if device.name in names:
            raise InventoryError(f"Duplicate device name: {device.name}")
        names.add(device.name)
        if device.enabled:
            devices.append(device)
    return devices


def _parse_device(raw: dict[str, Any], index: int) -> Device:
    name = str(raw.get("name", "")).strip()
    host = str(raw.get("host", "")).strip()
    if not name:
        raise InventoryError(f"Device #{index} is missing name")
    if not host:
        raise InventoryError(f"Device {name} is missing host")
    try:
        port = int(raw.get("port", 22))
        timeout = int(raw.get("timeout", 30))
    except (TypeError, ValueError) as exc:
        raise InventoryError(f"Device {name} has invalid port or timeout") from exc
    tags_raw = raw.get("tags") or []
    if isinstance(tags_raw, str):
        tags = (tags_raw,)
    elif isinstance(tags_raw, list):
        tags = tuple(str(tag) for tag in tags_raw)
    else:
        raise InventoryError(f"Device {name} tags must be a string or list")
    return Device(
        name=name,
        host=host,
        device_type=str(raw.get("device_type", "cisco_ios")).strip() or "cisco_ios",
        role=str(raw.get("role", "") or ""),
        site=str(raw.get("site", "") or ""),
        port=port,
        enabled=bool(raw.get("enabled", True)),
        timeout=timeout,
        tags=tags,
    )

