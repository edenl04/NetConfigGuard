from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from netconfigguard.yamlio import read_yaml, write_yaml


def record_pending_approval(
    path: Path,
    device_name: str,
    window_id: str,
    previous_config_hash: str,
    current_config_hash: str,
    previous_topology_hash: str,
    current_topology_hash: str,
) -> None:
    if not previous_config_hash:
        return
    data = read_yaml(path) or {"pending": {}}
    key = _key(device_name, window_id)
    data.setdefault("pending", {}).setdefault(
        key,
        {
            "device": device_name,
            "window_id": window_id,
            "first_seen_at": datetime.now(timezone.utc).isoformat(),
            "previous_config_hash": previous_config_hash,
            "first_seen_config_hash": current_config_hash,
            "previous_topology_hash": previous_topology_hash,
            "first_seen_topology_hash": current_topology_hash,
        },
    )
    write_yaml(path, data)


def pending_for_device(path: Path, device_name: str) -> list[dict[str, Any]]:
    data = read_yaml(path) or {"pending": {}}
    return [item for item in data.get("pending", {}).values() if item.get("device") == device_name]


def clear_pending_approval(path: Path, device_name: str, window_id: str) -> None:
    data = read_yaml(path) or {"pending": {}}
    data.get("pending", {}).pop(_key(device_name, window_id), None)
    write_yaml(path, data)


def append_approval_audit(path: Path, entry: dict[str, Any]) -> None:
    data = read_yaml(path) or {"approvals": []}
    audit_entry = {
        "approved_at": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    data.setdefault("approvals", []).append(audit_entry)
    write_yaml(path, data)


def _key(device_name: str, window_id: str) -> str:
    return f"{device_name}::{window_id}"

