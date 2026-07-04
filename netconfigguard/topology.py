from __future__ import annotations

import re
from typing import Any

from netconfigguard.models import Neighbor


PHONE_HINTS = ("phone", "ip phone", "cisco ip phone", "sep", "cp-", "ucphone")
INFRA_CAPABILITY_HINTS = ("router", "switch", "bridge", "wlan", "firewall")


def normalize_neighbor(raw: dict[str, Any], protocol: str) -> Neighbor:
    local_interface = _first(raw, "local_interface", "local_port", "local_port_id", "local_intf", "interface")
    neighbor_id = _first(raw, "neighbor", "neighbor_id", "device_id", "chassis_id", "system_name")
    neighbor_interface = _first(raw, "neighbor_interface", "neighbor_port_id", "port_id", "remote_port")
    capabilities = _first(raw, "capabilities", "capability")
    platform = _first(raw, "platform", "system_description")
    management_ip = _first(raw, "management_ip", "mgmt_address", "ip_address", "entry_address")
    endpoint_type = classify_endpoint(neighbor_id, capabilities, platform)
    return Neighbor(
        local_interface=local_interface,
        neighbor_id=neighbor_id,
        neighbor_interface=neighbor_interface,
        protocol=protocol,
        capabilities=capabilities,
        platform=platform,
        management_ip=management_ip,
        endpoint_type=endpoint_type,
    )


def classify_endpoint(neighbor_id: str, capabilities: str = "", platform: str = "") -> str:
    text = f"{neighbor_id} {capabilities} {platform}".lower()
    if any(hint in text for hint in PHONE_HINTS):
        return "phone"
    if any(hint in text for hint in INFRA_CAPABILITY_HINTS):
        return "infrastructure"
    if re.search(r"\b(r|s|b)\b", capabilities.lower()):
        return "infrastructure"
    return "unknown"


def compare_topology(baseline: list[dict[str, Any]] | None, current: list[dict[str, Any]]) -> dict[str, Any]:
    if baseline is None:
        return {"status": "missing_baseline", "changes": []}
    baseline_by_port = {str(item.get("local_interface", "")).lower(): item for item in baseline}
    current_by_port = {str(item.get("local_interface", "")).lower(): item for item in current}
    changes: list[dict[str, Any]] = []

    for port, expected in baseline_by_port.items():
        actual = current_by_port.get(port)
        expected_type = str(expected.get("endpoint_type", "unknown"))
        if actual is None:
            changes.append(
                {
                    "type": "phone_missing_info" if expected_type == "phone" else "neighbor_missing",
                    "severity": "info" if expected_type == "phone" else "high",
                    "local_interface": expected.get("local_interface", port),
                    "expected": expected,
                    "actual": None,
                }
            )
            continue
        if _neighbor_identity(expected) != _neighbor_identity(actual):
            actual_type = str(actual.get("endpoint_type", "unknown"))
            severity = "high"
            change_type = "neighbor_changed"
            if expected_type == "phone" and actual_type == "phone":
                severity = "info"
                change_type = "phone_changed_info"
            changes.append(
                {
                    "type": change_type,
                    "severity": severity,
                    "local_interface": expected.get("local_interface", port),
                    "expected": expected,
                    "actual": actual,
                }
            )

    for port, actual in current_by_port.items():
        if port not in baseline_by_port:
            changes.append(
                {
                    "type": "unexpected_neighbor",
                    "severity": "medium",
                    "local_interface": actual.get("local_interface", port),
                    "expected": None,
                    "actual": actual,
                }
            )

    drift_changes = [change for change in changes if change["severity"] != "info"]
    return {"status": "changed" if drift_changes else "clean", "changes": changes}


def _first(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _neighbor_identity(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("neighbor_id", "")).lower(),
        str(item.get("neighbor_interface", "")).lower(),
        str(item.get("endpoint_type", "")).lower(),
    )

