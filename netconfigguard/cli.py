from __future__ import annotations

import argparse
import time
from pathlib import Path

from netconfigguard.maintenance import start_manual_maintenance, stop_manual_maintenance
from netconfigguard.paths import ProjectPaths
from netconfigguard.runner import approve_maintenance, run_backup, run_check, run_init_baselines


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="netconfigguard", description="Cisco config backup and drift detection")
    parser.add_argument("--root", type=Path, default=Path("."), help="Project root directory")
    parser.add_argument("--inventory", type=Path, default=Path("devices.yaml"), help="YAML device inventory")
    parser.add_argument("--maintenance-file", type=Path, default=Path("maintenance.yaml"), help="Scheduled maintenance YAML")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Run one collection/check cycle")
    backup.add_argument("--batch-size", type=int, default=10)
    backup.add_argument("--retries", type=int, default=3)
    backup.add_argument("--no-commit", action="store_true")

    monitor = subparsers.add_parser("monitor", help="Run continuously")
    monitor.add_argument("--batch-size", type=int, default=10)
    monitor.add_argument("--retries", type=int, default=3)
    monitor.add_argument("--interval-minutes", type=int, default=120)
    monitor.add_argument("--once", action="store_true", help="Run one monitor cycle, useful for tests")

    subparsers.add_parser("check", help="Validate existing backups without connecting")

    init_baselines = subparsers.add_parser("init-baselines", help="Create baselines from current backups")
    init_baselines.add_argument("--no-commit", action="store_true")

    approve = subparsers.add_parser("approve-maintenance", help="Promote current backups to baselines")
    approve.add_argument("--no-commit", action="store_true")

    maintenance = subparsers.add_parser("maintenance", help="Manual maintenance controls")
    maintenance_sub = maintenance.add_subparsers(dest="maintenance_command", required=True)
    start = maintenance_sub.add_parser("start", help="Enter manual maintenance")
    start.add_argument("--device", action="append", default=[])
    start.add_argument("--site", action="append", default=[])
    start.add_argument("--duration-minutes", type=int)
    start.add_argument("--reason", required=True)
    start.add_argument("--approver", default="")
    start.add_argument("--ticket", default="")
    stop = maintenance_sub.add_parser("stop", help="Exit manual maintenance")
    stop.add_argument("--device", action="append", default=[])
    stop.add_argument("--site", action="append", default=[])
    stop.add_argument("--all", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()
    inventory = _resolve(root, args.inventory)
    maintenance_file = _resolve(root, args.maintenance_file)

    if args.command == "backup":
        code, report = run_backup(root, inventory, maintenance_file, args.batch_size, args.retries, commit=not args.no_commit)
        _print_summary(report)
        return code
    if args.command == "monitor":
        while True:
            code, report = run_backup(root, inventory, maintenance_file, args.batch_size, args.retries)
            _print_summary(report)
            if args.once:
                return code
            time.sleep(args.interval_minutes * 60)
    if args.command == "check":
        code, report = run_check(root, inventory, maintenance_file)
        _print_summary(report)
        return code
    if args.command == "init-baselines":
        code, devices = run_init_baselines(root, inventory, commit=not args.no_commit)
        print(f"Initialized baselines for: {', '.join(devices) if devices else 'none'}")
        return code
    if args.command == "approve-maintenance":
        code, devices = approve_maintenance(root, inventory, commit=not args.no_commit)
        print(f"Approved baselines for: {', '.join(devices) if devices else 'none'}")
        return code
    if args.command == "maintenance":
        paths = ProjectPaths(root)
        if args.maintenance_command == "start":
            window = start_manual_maintenance(
                paths.manual_maintenance,
                devices=args.device,
                sites=args.site,
                duration_minutes=args.duration_minutes,
                reason=args.reason,
                approver=args.approver,
                ticket=args.ticket,
            )
            print(f"Started manual maintenance {window.id}")
            return 0
        if args.maintenance_command == "stop":
            stopped = stop_manual_maintenance(paths.manual_maintenance, args.device, args.site, args.all)
            print(f"Stopped manual maintenance: {', '.join(stopped) if stopped else 'none'}")
            return 0
    parser.error("unknown command")
    return 2


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _print_summary(report) -> None:
    print(f"Run {report['run_id']} status: {report['overall_status']}")
    for device in report.get("devices", []):
        print(
            f"- {device['device']}: collection={device['collection_status']} "
            f"drift={device.get('drift_status')} security={device.get('security_status')} "
            f"topology={device.get('topology_status')}"
        )

