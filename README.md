# NetConfigGuard

NetConfigGuard is a Python/Netmiko utility for backing up Cisco running configurations to Git, detecting unauthorized config and topology drift, and flagging common security risks.

It is built for managed Cisco switches and routers that use shared operational credentials. The tool can run once on demand or continuously as a lightweight monitor.

Running configs can contain sensitive data. Use this only in a protected repository.

## What It Does

- Connects to Cisco devices over SSH with Netmiko.
- Pulls and stores `show running-config`.
- Commits backups, reports, baselines, and approval history to Git.
- Compares current configs against approved baselines.
- Checks LLDP first, then CDP, to detect neighbor/topology changes.
- Treats disconnected expected IP phones as informational.
- Flags risky config such as Telnet access, weak SNMP communities, plaintext passwords, insecure HTTP, and missing SSH hardening.
- Supports planned and manual maintenance windows.
- Automatically approves eligible planned changes after a successful post-maintenance check.
- Blocks approval when a device is unreachable, topology is uncertain, or critical security findings exist.

## How It Works

NetConfigGuard keeps three main states:

```text
backups/          latest collected device state
baselines/        approved config and topology standard
baseline-history/ previous approved baselines kept for rollback
```

During each run, the tool collects the latest device state, compares it to the approved baseline, writes reports, and commits changes locally. It does not push to GitHub by default.

If a device cannot be reached, NetConfigGuard preserves the last good backup and marks the device as unreachable. It does not overwrite backups or update baselines for unreachable devices.

## Setup

Install dependencies:

```powershell
uv sync --dev
```

Create `devices.yaml`:

```yaml
devices:
  - name: core-sw01
    host: 10.0.0.10
    device_type: cisco_ios
    site: hq
    port: 22
    enabled: true
```

Set device credentials:

PowerShell:

```powershell
$env:NETOPS_USERNAME='admin'
$env:NETOPS_PASSWORD='your-password'
$env:NETOPS_SECRET='your-enable-secret'
```

`NETOPS_SECRET` is optional and is used for Cisco enable mode.

NetConfigGuard auto-detects whether enable mode is needed. If the SSH user lands directly in privileged EXEC mode (`#`), `NETOPS_SECRET` is not used. If the user lands in user EXEC mode (`>`) and the device requires `enable`, NetConfigGuard uses `NETOPS_SECRET`. If it is missing or wrong, the device is reported with a clear enable-secret error in reports and alerts.

## Usage

Run one backup/check cycle:

```powershell
uv run netconfigguard backup --inventory devices.yaml
```

Create initial approved baselines from successful backups:

```powershell
uv run netconfigguard init-baselines --inventory devices.yaml
```

Typical first run:

```text
1. Run backup.
2. Review the collected config and reports.
3. Run init-baselines to approve the current state.
4. Use backup or monitor for ongoing drift detection.
```

Run continuously every 2 hours:

```powershell
uv run netconfigguard monitor --inventory devices.yaml --interval-minutes 120
```

Check existing backups against baselines without connecting to devices:

```powershell
uv run netconfigguard check --inventory devices.yaml
```

## Maintenance

Use maintenance windows when planned troubleshooting or approved changes are expected.

Example `maintenance.yaml`:

```yaml
windows:
  - id: core-upgrade-001
    start: "2026-07-04T22:00:00+03:00"
    end: "2026-07-05T01:00:00+03:00"
    devices:
      - core-sw01
    reason: "Core switch upgrade"
    approver: "Eden"
    ticket: "CHG-1042"
```

Run with scheduled maintenance:

```powershell
uv run netconfigguard backup --inventory devices.yaml --maintenance-file maintenance.yaml
```

Start manual maintenance:

```powershell
uv run netconfigguard maintenance start --device core-sw01 --reason "Troubleshooting uplink issue" --approver Eden --ticket INC-2044
```

Stop manual maintenance:

```powershell
uv run netconfigguard maintenance stop --device core-sw01
```

During maintenance, drift is reported as planned. After maintenance ends, eligible changes can become the new approved baseline, while the previous baseline is saved for rollback.

Automatic approval requires a reachable device, a successful post-maintenance collection, no critical security findings, and usable topology data.

## Reports

Reports are written under `reports/`:

```text
reports/latest.yaml
reports/latest.json
reports/latest-alerts.yaml
reports/alerts.log
```

Start with `reports/latest-alerts.yaml` when checking current problems.

Runtime state is stored under `.netconfigguard-state/`.

## Important Note

Running configs can contain sensitive data such as SNMP communities, user hashes, keys, and pre-shared secrets. Treat this repository as sensitive infrastructure data.
