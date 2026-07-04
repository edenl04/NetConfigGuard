from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from netconfigguard.yamlio import write_yaml


def build_alerts(report: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for device in report.get("devices", []):
        if device.get("collection_status") == "unreachable":
            reason = str(device.get("reason", ""))
            alerts.append(
                {
                    "severity": device.get("severity", "high"),
                    "category": "collection",
                    "device": device.get("device", ""),
                    "message": _collection_message(str(device.get("device", "")), reason),
                    "reason": reason,
                    "run_id": report.get("run_id", ""),
                }
            )
        if device.get("drift_status") == "unauthorized_drift":
            alerts.append(
                {
                    "severity": "high",
                    "category": "drift",
                    "device": device.get("device", ""),
                    "message": f"Unauthorized drift detected on {device.get('device', '')}",
                    "run_id": report.get("run_id", ""),
                }
            )
        if device.get("topology_status") == "uncertain":
            alerts.append(
                {
                    "severity": "medium",
                    "category": "topology",
                    "device": device.get("device", ""),
                    "message": f"Topology status is uncertain for {device.get('device', '')}",
                    "run_id": report.get("run_id", ""),
                }
            )
        if str(device.get("auto_approval", "")).startswith("blocked"):
            alerts.append(
                {
                    "severity": "high",
                    "category": "approval",
                    "device": device.get("device", ""),
                    "message": f"Automatic approval blocked for {device.get('device', '')}: {device.get('auto_approval')}",
                    "run_id": report.get("run_id", ""),
                }
            )

    for finding in report.get("findings", []):
        alerts.append(
            {
                "severity": finding.get("severity", "medium"),
                "category": "security",
                "device": finding.get("device", ""),
                "message": finding.get("message", ""),
                "rule_id": finding.get("rule_id", ""),
                "run_id": report.get("run_id", ""),
            }
        )
    return alerts


def _collection_message(device_name: str, reason: str) -> str:
    if reason == "enable_secret_required":
        return f"Device {device_name} requires privileged EXEC mode. Configure NETOPS_SECRET or use a privilege 15 account."
    if reason == "enable_authentication_failed":
        return f"Device {device_name} rejected NETOPS_SECRET while entering privileged EXEC mode."
    return f"Device {device_name} is unreachable"


def write_alerts(latest_path: Path, log_path: Path, report: dict[str, Any]) -> list[dict[str, Any]]:
    alerts = build_alerts(report)
    payload = {
        "run_id": report.get("run_id", ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "alerts": alerts,
    }
    write_yaml(latest_path, payload)
    if alerts:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            for alert in alerts:
                handle.write(
                    f"{payload['generated_at']} severity={alert['severity']} "
                    f"category={alert['category']} device={alert['device']} message={alert['message']}\n"
                )
    return alerts

