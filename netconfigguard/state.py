from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from netconfigguard.yamlio import read_yaml, write_yaml


def record_collection_success(path: Path, device_name: str) -> None:
    data = read_yaml(path) or {"devices": {}}
    entry = data.setdefault("devices", {}).setdefault(device_name, {})
    entry["consecutive_failures"] = 0
    entry["last_successful_backup"] = datetime.now(timezone.utc).isoformat()
    write_yaml(path, data)


def record_collection_failure(path: Path, device_name: str) -> int:
    data = read_yaml(path) or {"devices": {}}
    entry = data.setdefault("devices", {}).setdefault(device_name, {})
    failures = int(entry.get("consecutive_failures", 0)) + 1
    entry["consecutive_failures"] = failures
    entry["last_failure"] = datetime.now(timezone.utc).isoformat()
    write_yaml(path, data)
    return failures


def last_successful_backup(path: Path, device_name: str) -> str:
    data = read_yaml(path) or {"devices": {}}
    return str(data.get("devices", {}).get(device_name, {}).get("last_successful_backup", "") or "")

