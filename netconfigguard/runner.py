from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from netconfigguard.alerts import write_alerts
from netconfigguard.approvals import append_approval_audit, clear_pending_approval, pending_for_device, record_pending_approval
from netconfigguard.baseline import init_baseline, promote_backup_to_baseline, prune_baseline_history, write_successful_backup
from netconfigguard.collector import CollectorFn, collect_device, collect_devices
from netconfigguard.credentials import Credentials, load_credentials
from netconfigguard.drift import compare_configs, config_hash, read_baseline_config
from netconfigguard.git_ops import check_dirty_scope, commit_if_changed
from netconfigguard.hashing import sha256_data
from netconfigguard.inventory import load_inventory
from netconfigguard.lock import ProjectLock
from netconfigguard.maintenance import active_window_for, ended_window_for, load_maintenance_windows
from netconfigguard.models import Device, DeviceCollectionResult
from netconfigguard.paths import ProjectPaths
from netconfigguard.reports import finish_report, new_run_report, write_report
from netconfigguard.security import check_security, has_critical_security
from netconfigguard.state import last_successful_backup, record_collection_failure, record_collection_success
from netconfigguard.topology import compare_topology
from netconfigguard.yamlio import read_yaml


def run_backup(
    root: Path,
    inventory_path: Path,
    maintenance_path: Path,
    batch_size: int = 10,
    retries: int = 3,
    collector: CollectorFn = collect_device,
    credentials: Credentials | None = None,
    commit: bool = True,
) -> tuple[int, dict[str, Any]]:
    paths = ProjectPaths(root)
    paths.ensure_runtime_dirs()
    with ProjectLock(paths.lock_file):
        devices = load_inventory(inventory_path)
        creds = credentials or load_credentials()
        windows = load_maintenance_windows(maintenance_path, paths.manual_maintenance)
        results = asyncio.run(collect_devices(devices, creds, batch_size, retries, collector))
        report = _build_report(paths, results, windows, datetime.now(timezone.utc), write_backups=True)
        write_report(paths.reports, report)
        write_alerts(paths.latest_alerts, paths.alert_log, report)
        prune_baseline_history(paths)
        if commit:
            check_dirty_scope(paths.root)
            commit_if_changed(paths.root, f"Backup network configs {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        return _exit_code(report), report


def run_check(root: Path, inventory_path: Path, maintenance_path: Path) -> tuple[int, dict[str, Any]]:
    paths = ProjectPaths(root)
    paths.ensure_runtime_dirs()
    with ProjectLock(paths.lock_file):
        devices = load_inventory(inventory_path)
        windows = load_maintenance_windows(maintenance_path, paths.manual_maintenance)
        results: list[DeviceCollectionResult] = []
        for device in devices:
            backup_dir = paths.device_backup_dir(device.name)
            config_path = backup_dir / "running-config.txt"
            neighbors_path = backup_dir / "neighbors.yaml"
            if not config_path.exists():
                results.append(DeviceCollectionResult(device=device, success=False, error_type="missing_backup", error="No backup found"))
                continue
            neighbor_data = read_yaml(neighbors_path) or {"neighbors": []}
            results.append(
                DeviceCollectionResult(
                    device=device,
                    success=True,
                    running_config=config_path.read_text(encoding="utf-8"),
                    neighbors=[],
                    neighbor_status="ok",
                    neighbor_protocol="cached",
                    collected_at=datetime.now(timezone.utc),
                )
            )
            results[-1]._cached_neighbors = neighbor_data.get("neighbors", [])  # type: ignore[attr-defined]
        report = _build_report(paths, results, windows, datetime.now(timezone.utc), write_backups=False)
        write_report(paths.reports, report)
        write_alerts(paths.latest_alerts, paths.alert_log, report)
        return _exit_code(report), report


def run_init_baselines(root: Path, inventory_path: Path, commit: bool = True) -> tuple[int, list[str]]:
    paths = ProjectPaths(root)
    paths.ensure_runtime_dirs()
    initialized: list[str] = []
    with ProjectLock(paths.lock_file):
        for device in load_inventory(inventory_path):
            if init_baseline(paths, device.name):
                initialized.append(device.name)
        if commit:
            check_dirty_scope(paths.root)
            commit_if_changed(paths.root, f"Initialize baselines {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return (0 if initialized else 2), initialized


def approve_maintenance(root: Path, inventory_path: Path, commit: bool = True) -> tuple[int, list[str]]:
    paths = ProjectPaths(root)
    paths.ensure_runtime_dirs()
    approved: list[str] = []
    with ProjectLock(paths.lock_file):
        for device in load_inventory(inventory_path):
            if promote_backup_to_baseline(paths, device.name):
                append_approval_audit(
                    paths.approval_audit,
                    {
                        "mode": "manual",
                        "device": device.name,
                        "window_id": "",
                        "approved_config_hash": "",
                        "approved_topology_hash": "",
                    },
                )
                approved.append(device.name)
        if commit:
            check_dirty_scope(paths.root)
            commit_if_changed(paths.root, f"Approve maintenance {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return (0 if approved else 2), approved


def _build_report(
    paths: ProjectPaths,
    results: list[DeviceCollectionResult],
    windows,
    now: datetime,
    write_backups: bool,
) -> dict[str, Any]:
    report = new_run_report()
    for result in results:
        device = result.device
        if not result.success:
            failures = record_collection_failure(paths.failure_state, device.name)
            report["devices"].append(
                {
                    "device": device.name,
                    "site": device.site,
                    "collection_status": "unreachable",
                    "severity": "critical" if failures >= 3 else "high",
                    "reason": result.error_type,
                    "error": result.error,
                    "retries": result.retries,
                    "last_successful_backup": last_successful_backup(paths.failure_state, device.name),
                    "drift_status": "unknown",
                    "topology_status": "unknown",
                    "security_status": "unknown",
                }
            )
            continue

        record_collection_success(paths.failure_state, device.name)
        neighbors = _neighbors_as_dicts(result)
        if write_backups:
            write_successful_backup(paths, device.name, result.running_config, neighbors)

        baseline_dir = paths.device_baseline_dir(device.name)
        baseline_config = read_baseline_config(baseline_dir / "running-config.txt")
        drift = compare_configs(baseline_config, result.running_config)
        baseline_state = read_yaml(baseline_dir / "approved-state.yaml")
        baseline_neighbors = None
        if isinstance(baseline_state, dict):
            baseline_neighbors = baseline_state.get("neighbors")
        topology = compare_topology(baseline_neighbors, neighbors)
        findings = check_security(device.name, result.running_config)
        window = active_window_for(device, windows, now)
        drift_status = _drift_status(drift["status"], topology["status"], window is not None)
        device_report = {
            "device": device.name,
            "site": device.site,
            "collection_status": "ok",
            "collected_at": result.collected_at.isoformat() if result.collected_at else now.isoformat(),
            "maintenance_window_id": window.id if window else "",
            "drift_status": drift_status,
            "topology_status": result.neighbor_status if result.neighbor_status == "uncertain" else topology["status"],
            "security_status": "failed" if findings else "clean",
            "previous_config_hash": config_hash(baseline_config) if baseline_config else "",
            "current_config_hash": config_hash(result.running_config),
            "previous_topology_hash": sha256_data(baseline_neighbors or []),
            "current_topology_hash": sha256_data(neighbors),
            "diff": drift.get("diff", []),
            "topology_changes": topology.get("changes", []),
            "critical_security_blocks_approval": has_critical_security(findings),
            "auto_approval": "not_applicable",
        }
        _handle_maintenance_approval(paths, device, device_report, findings, windows, now)
        report["devices"].append(device_report)
        report["findings"].extend(finding.to_dict() for finding in findings)
    return finish_report(report)


def _neighbors_as_dicts(result: DeviceCollectionResult) -> list[dict[str, Any]]:
    cached = getattr(result, "_cached_neighbors", None)
    if cached is not None:
        return cached
    return [neighbor.to_dict() for neighbor in result.neighbors]


def _drift_status(config_status: object, topology_status: object, in_maintenance: bool) -> str:
    changed = config_status in {"changed", "missing_baseline"} or topology_status in {"changed", "missing_baseline"}
    if not changed:
        return "clean"
    return "planned_change_observed" if in_maintenance else "unauthorized_drift"


def _handle_maintenance_approval(paths: ProjectPaths, device: Device, device_report: dict[str, Any], findings, windows, now: datetime) -> None:
    window_id = device_report.get("maintenance_window_id")
    if window_id and device_report.get("drift_status") == "planned_change_observed":
        record_pending_approval(
            paths.pending_approvals,
            device.name,
            str(window_id),
            str(device_report.get("previous_config_hash", "")),
            str(device_report.get("current_config_hash", "")),
            str(device_report.get("previous_topology_hash", "")),
            str(device_report.get("current_topology_hash", "")),
        )
        device_report["auto_approval"] = "pending_until_window_end"
        return

    for pending in pending_for_device(paths.pending_approvals, device.name):
        ended = ended_window_for(device, windows, now, str(pending.get("window_id")))
        if not ended:
            continue
        if has_critical_security(findings):
            device_report["auto_approval"] = "blocked_critical_security"
            return
        if device_report.get("topology_status") == "uncertain":
            device_report["auto_approval"] = "blocked_uncertain_topology"
            return
        if device_report.get("collection_status") != "ok":
            device_report["auto_approval"] = "blocked_unreachable"
            return
        if device_report.get("drift_status") not in {"unauthorized_drift", "clean"}:
            device_report["auto_approval"] = "blocked_unexpected_status"
            return
        if promote_backup_to_baseline(paths, device.name):
            clear_pending_approval(paths.pending_approvals, device.name, ended.id)
            device_report["drift_status"] = "planned_change_auto_approved"
            device_report["auto_approval"] = "approved_after_window"
            device_report["approved_window_id"] = ended.id
            device_report["approved_previous_config_hash"] = pending.get("previous_config_hash", "")
            device_report["approved_new_config_hash"] = device_report.get("current_config_hash", "")
            device_report["approved_previous_topology_hash"] = pending.get("previous_topology_hash", "")
            device_report["approved_new_topology_hash"] = device_report.get("current_topology_hash", "")
            append_approval_audit(
                paths.approval_audit,
                {
                    "mode": "automatic",
                    "device": device.name,
                    "window_id": ended.id,
                    "previous_config_hash": pending.get("previous_config_hash", ""),
                    "approved_config_hash": device_report.get("current_config_hash", ""),
                    "previous_topology_hash": pending.get("previous_topology_hash", ""),
                    "approved_topology_hash": device_report.get("current_topology_hash", ""),
                },
            )
            return


def _exit_code(report: dict[str, Any]) -> int:
    if any(device.get("collection_status") == "unreachable" for device in report.get("devices", [])):
        return 2
    if report.get("overall_status") != "healthy":
        return 1
    return 0

