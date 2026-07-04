from __future__ import annotations

from pathlib import Path


class ProjectPaths:
    def __init__(self, root: Path | str = ".") -> None:
        self.root = Path(root).resolve()
        self.backups = self.root / "backups"
        self.baselines = self.root / "baselines"
        self.baseline_history = self.root / "baseline-history"
        self.reports = self.root / "reports"
        self.state = self.root / ".netconfigguard-state"
        self.lock_file = self.state / "netconfigguard.lock"
        self.failure_state = self.state / "failures.yaml"
        self.manual_maintenance = self.state / "manual-maintenance.yaml"
        self.pending_approvals = self.state / "pending-approvals.yaml"
        self.approval_audit = self.state / "approval-audit.yaml"
        self.alert_log = self.reports / "alerts.log"
        self.latest_alerts = self.reports / "latest-alerts.yaml"

    def ensure_runtime_dirs(self) -> None:
        for path in (self.backups, self.baselines, self.reports, self.state):
            path.mkdir(parents=True, exist_ok=True)

    def device_backup_dir(self, device_name: str) -> Path:
        return self.backups / safe_name(device_name)

    def device_baseline_dir(self, device_name: str) -> Path:
        return self.baselines / safe_name(device_name)


def safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_", ".") else "_" for char in value)

