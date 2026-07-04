from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from netconfigguard.yamlio import write_yaml


def new_run_report() -> dict[str, Any]:
    return {
        "run_id": uuid4().hex,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "ended_at": None,
        "overall_status": "healthy",
        "devices": [],
        "findings": [],
    }


def finish_report(report: dict[str, Any]) -> dict[str, Any]:
    report["ended_at"] = datetime.now(timezone.utc).isoformat()
    device_statuses = [device.get("collection_status") for device in report.get("devices", [])]
    has_drift = any(device.get("drift_status") in {"unauthorized_drift", "planned_change_observed"} for device in report.get("devices", []))
    has_security = bool(report.get("findings"))
    if "unreachable" in device_statuses:
        report["overall_status"] = "degraded"
    elif has_drift or has_security:
        report["overall_status"] = "degraded"
    else:
        report["overall_status"] = "healthy"
    return report


def write_report(report_dir: Path, report: dict[str, Any]) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    latest_yaml = report_dir / "latest.yaml"
    latest_json = report_dir / "latest.json"
    archive_yaml = report_dir / f"{report['run_id']}.yaml"
    archive_json = report_dir / f"{report['run_id']}.json"
    write_yaml(archive_yaml, report)
    write_yaml(latest_yaml, report)
    _write_json(archive_json, report)
    _write_json(latest_json, report)
    return latest_yaml


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, sort_keys=False)
        handle.write("\n")

