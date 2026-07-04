from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from netconfigguard.hashing import sha256_data
from netconfigguard.paths import ProjectPaths
from netconfigguard.yamlio import read_yaml, write_yaml


def write_successful_backup(paths: ProjectPaths, device_name: str, running_config: str, neighbors: list[dict[str, Any]]) -> None:
    backup_dir = paths.device_backup_dir(device_name)
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "running-config.txt").write_text(running_config, encoding="utf-8", newline="\n")
    write_yaml(backup_dir / "neighbors.yaml", {"neighbors": neighbors})


def init_baseline(paths: ProjectPaths, device_name: str) -> bool:
    backup_dir = paths.device_backup_dir(device_name)
    config = backup_dir / "running-config.txt"
    neighbors = backup_dir / "neighbors.yaml"
    if not config.exists() or not neighbors.exists():
        return False
    baseline_dir = paths.device_baseline_dir(device_name)
    baseline_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config, baseline_dir / "running-config.txt")
    neighbor_data = read_yaml(neighbors) or {"neighbors": []}
    write_yaml(
        baseline_dir / "approved-state.yaml",
        {
            "device": device_name,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "config_file": "running-config.txt",
            "neighbors": neighbor_data.get("neighbors", []),
            "topology_hash": sha256_data(neighbor_data.get("neighbors", [])),
        },
    )
    return True


def backup_previous_baseline(paths: ProjectPaths, device_name: str) -> Path | None:
    baseline_dir = paths.device_baseline_dir(device_name)
    if not baseline_dir.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = paths.baseline_history / device_name / timestamp
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(baseline_dir, target)
    return target


def promote_backup_to_baseline(paths: ProjectPaths, device_name: str) -> bool:
    backup_previous_baseline(paths, device_name)
    return init_baseline(paths, device_name)


def prune_baseline_history(paths: ProjectPaths, retention_hours: int = 72) -> list[Path]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)
    removed: list[Path] = []
    if not paths.baseline_history.exists():
        return removed
    for leaf in paths.baseline_history.glob("*/*"):
        if not leaf.is_dir():
            continue
        mtime = datetime.fromtimestamp(leaf.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            shutil.rmtree(leaf)
            removed.append(leaf)
    return removed

