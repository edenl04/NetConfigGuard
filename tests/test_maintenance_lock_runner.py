import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from netconfigguard.credentials import Credentials
from netconfigguard.git_ops import GitError, check_dirty_scope
from netconfigguard.lock import LockError, ProjectLock
from netconfigguard.maintenance import MaintenanceError, active_window_for, load_maintenance_windows, start_manual_maintenance, stop_manual_maintenance
from netconfigguard.models import Device, DeviceCollectionResult, Neighbor
from netconfigguard.runner import run_backup, run_init_baselines
from netconfigguard.yamlio import read_yaml


def test_maintenance_rejects_timezone_less_window(tmp_path: Path) -> None:
    maintenance = tmp_path / "maintenance.yaml"
    manual = tmp_path / "manual.yaml"
    maintenance.write_text(
        """
windows:
  - id: bad
    start: "2026-07-04T22:00:00"
    end: "2026-07-05T01:00:00+03:00"
""",
        encoding="utf-8",
    )

    with pytest.raises(MaintenanceError, match="timezone"):
        load_maintenance_windows(maintenance, manual)


def test_manual_maintenance_start_stop(tmp_path: Path) -> None:
    state = tmp_path / "manual.yaml"
    start = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    window = start_manual_maintenance(
        state,
        devices=["core-sw01"],
        sites=[],
        reason="Troubleshooting",
        approver="Eden",
        now=start,
    )
    windows = load_maintenance_windows(tmp_path / "missing.yaml", state)

    assert active_window_for(Device(name="core-sw01", host="10.0.0.1"), windows, start).id == window.id

    stopped = stop_manual_maintenance(state, devices=["core-sw01"], sites=[], stop_all=False, now=start)

    assert stopped == [window.id]


def test_project_lock_blocks_second_writer(tmp_path: Path) -> None:
    lock_path = tmp_path / ".netconfigguard-state" / "netconfigguard.lock"
    with ProjectLock(lock_path):
        with pytest.raises(LockError):
            with ProjectLock(lock_path):
                pass


def test_unreachable_device_preserves_backup_and_blocks_baseline_update(tmp_path: Path) -> None:
    inventory = tmp_path / "devices.yaml"
    maintenance = tmp_path / "maintenance.yaml"
    inventory.write_text("devices:\n  - name: sw1\n    host: 10.0.0.1\n", encoding="utf-8")
    maintenance.write_text("windows: []\n", encoding="utf-8")
    backup_dir = tmp_path / "backups" / "sw1"
    backup_dir.mkdir(parents=True)
    old_backup = "hostname old\n"
    (backup_dir / "running-config.txt").write_text(old_backup, encoding="utf-8")

    def failing_collector(device, credentials, retries):
        return DeviceCollectionResult(device=device, success=False, error_type="ssh_timeout", error="timed out", retries=3)

    code, report = run_backup(
        tmp_path,
        inventory,
        maintenance,
        collector=failing_collector,
        credentials=Credentials("u", "p"),
        commit=False,
    )

    assert code == 2
    assert (backup_dir / "running-config.txt").read_text(encoding="utf-8") == old_backup
    assert not (tmp_path / "baselines" / "sw1").exists()
    assert report["devices"][0]["collection_status"] == "unreachable"

    latest_json = json.loads((tmp_path / "reports" / "latest.json").read_text(encoding="utf-8"))
    latest_alerts = read_yaml(tmp_path / "reports" / "latest-alerts.yaml")
    alerts_log = (tmp_path / "reports" / "alerts.log").read_text(encoding="utf-8")
    assert latest_json["run_id"] == report["run_id"]
    assert latest_alerts["alerts"][0]["category"] == "collection"
    assert "Device sw1 is unreachable" in alerts_log


def test_backup_then_init_baseline_with_mock_collector(tmp_path: Path) -> None:
    inventory = tmp_path / "devices.yaml"
    maintenance = tmp_path / "maintenance.yaml"
    inventory.write_text("devices:\n  - name: sw1\n    host: 10.0.0.1\n", encoding="utf-8")
    maintenance.write_text("windows: []\n", encoding="utf-8")

    def collector(device, credentials, retries):
        return DeviceCollectionResult(
            device=device,
            success=True,
            running_config="hostname sw1\nline vty 0 4\n transport input ssh\n",
            neighbors=[
                Neighbor(
                    local_interface="Gi1/0/1",
                    neighbor_id="dist-sw1",
                    neighbor_interface="Gi0/1",
                    endpoint_type="infrastructure",
                    protocol="lldp",
                )
            ],
        )

    code, report = run_backup(
        tmp_path,
        inventory,
        maintenance,
        collector=collector,
        credentials=Credentials("u", "p"),
        commit=False,
    )
    baseline_code, initialized = run_init_baselines(tmp_path, inventory, commit=False)

    assert code == 1
    assert report["devices"][0]["drift_status"] == "unauthorized_drift"
    assert baseline_code == 0
    assert initialized == ["sw1"]
    assert (tmp_path / "baselines" / "sw1" / "running-config.txt").exists()


def test_automatic_approval_after_maintenance_window(tmp_path: Path) -> None:
    inventory = tmp_path / "devices.yaml"
    maintenance = tmp_path / "maintenance.yaml"
    inventory.write_text("devices:\n  - name: sw1\n    host: 10.0.0.1\n", encoding="utf-8")
    now = datetime.now(timezone.utc)
    maintenance.write_text(
        f"""
windows:
  - id: maint-1
    start: "{(now - timedelta(minutes=10)).isoformat()}"
    end: "{(now + timedelta(minutes=10)).isoformat()}"
    devices:
      - sw1
""",
        encoding="utf-8",
    )

    baseline_dir = tmp_path / "baselines" / "sw1"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "running-config.txt").write_text("hostname old\n", encoding="utf-8")
    (baseline_dir / "approved-state.yaml").write_text("device: sw1\nneighbors: []\n", encoding="utf-8")

    def collector(device, credentials, retries):
        return DeviceCollectionResult(device=device, success=True, running_config="hostname new\n", neighbors=[])

    first_code, first_report = run_backup(
        tmp_path,
        inventory,
        maintenance,
        collector=collector,
        credentials=Credentials("u", "p"),
        commit=False,
    )
    assert first_code == 1
    assert first_report["devices"][0]["auto_approval"] == "pending_until_window_end"

    maintenance.write_text(
        f"""
windows:
  - id: maint-1
    start: "{(now - timedelta(minutes=20)).isoformat()}"
    end: "{(now - timedelta(minutes=1)).isoformat()}"
    devices:
      - sw1
""",
        encoding="utf-8",
    )

    second_code, second_report = run_backup(
        tmp_path,
        inventory,
        maintenance,
        collector=collector,
        credentials=Credentials("u", "p"),
        commit=False,
    )

    assert second_code == 0
    assert second_report["devices"][0]["auto_approval"] == "approved_after_window"
    assert (baseline_dir / "running-config.txt").read_text(encoding="utf-8") == "hostname new\n"
    assert list((tmp_path / "baseline-history" / "sw1").glob("*"))
    audit = read_yaml(tmp_path / ".netconfigguard-state" / "approval-audit.yaml")
    assert audit["approvals"][0]["mode"] == "automatic"
    assert audit["approvals"][0]["device"] == "sw1"


def test_automatic_approval_blocks_uncertain_topology(tmp_path: Path) -> None:
    inventory = tmp_path / "devices.yaml"
    maintenance = tmp_path / "maintenance.yaml"
    inventory.write_text("devices:\n  - name: sw1\n    host: 10.0.0.1\n", encoding="utf-8")
    now = datetime.now(timezone.utc)
    maintenance.write_text(
        f"""
windows:
  - id: maint-1
    start: "{(now - timedelta(minutes=10)).isoformat()}"
    end: "{(now + timedelta(minutes=10)).isoformat()}"
    devices:
      - sw1
""",
        encoding="utf-8",
    )

    baseline_dir = tmp_path / "baselines" / "sw1"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "running-config.txt").write_text("hostname old\n", encoding="utf-8")
    (baseline_dir / "approved-state.yaml").write_text("device: sw1\nneighbors: []\n", encoding="utf-8")

    def in_window_collector(device, credentials, retries):
        return DeviceCollectionResult(device=device, success=True, running_config="hostname new\n", neighbors=[])

    run_backup(
        tmp_path,
        inventory,
        maintenance,
        collector=in_window_collector,
        credentials=Credentials("u", "p"),
        commit=False,
    )

    maintenance.write_text(
        f"""
windows:
  - id: maint-1
    start: "{(now - timedelta(minutes=20)).isoformat()}"
    end: "{(now - timedelta(minutes=1)).isoformat()}"
    devices:
      - sw1
""",
        encoding="utf-8",
    )

    def uncertain_collector(device, credentials, retries):
        return DeviceCollectionResult(
            device=device,
            success=True,
            running_config="hostname new\n",
            neighbors=[],
            neighbor_status="uncertain",
        )

    code, report = run_backup(
        tmp_path,
        inventory,
        maintenance,
        collector=uncertain_collector,
        credentials=Credentials("u", "p"),
        commit=False,
    )

    assert code == 1
    assert report["devices"][0]["auto_approval"] == "blocked_uncertain_topology"
    assert (baseline_dir / "running-config.txt").read_text(encoding="utf-8") == "hostname old\n"
    latest_alerts = read_yaml(tmp_path / "reports" / "latest-alerts.yaml")
    assert any(alert["category"] == "approval" for alert in latest_alerts["alerts"])


def test_dirty_git_scope_rejects_unrelated_changes(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "operator-notes.txt").write_text("manual change\n", encoding="utf-8")

    with pytest.raises(GitError, match="operator-notes"):
        check_dirty_scope(tmp_path)


def test_dirty_git_scope_allows_tool_managed_changes(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    report_dir = tmp_path / "reports"
    report_dir.mkdir()
    (report_dir / "latest.yaml").write_text("overall_status: healthy\n", encoding="utf-8")

    check_dirty_scope(tmp_path)

