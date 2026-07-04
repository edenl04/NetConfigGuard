# NetConfigGuard

A Cisco network configuration backup and drift-detection utility powered by Python, Netmiko, YAML inventories, and Git. The tool connects to managed switches and routers, collects running configurations, checks LLDP/CDP neighbors, detects unauthorized changes against approved baselines, reports security weaknesses, and commits backups and reports locally.

## Overview

This project is a NetConfigGuard monitoring backend for Cisco network devices. It is designed for managed L2/L3 switches and routers that share the same operational credentials. The tool can run as a one-shot backup command or as a 24/7 monitor that checks the environment every 2 hours by default.

Technically, Netmiko handles SSH connections to Cisco devices, YAML files define inventory and maintenance windows, and Git stores the backup history. The workflow collects running configs and topology data, compares them against approved baselines, classifies planned and unauthorized drift, flags security risks, writes YAML/JSON reports, and keeps rollback copies of old baselines.

## Capabilities

### Device Backup

- Loads managed devices from a YAML inventory.
- Connects to enabled devices over SSH with Netmiko.
- Uses shared credentials from environment variables.
- Pulls `show running-config` from each reachable device.
- Stores current configs under `backups/<device-name>/running-config.txt`.
- Preserves the last known good backup when a device is unreachable.

### Drift Detection

- Compares collected running configs against approved baselines.
- Stores approved configs under `baselines/<device-name>/running-config.txt`.
- Ignores only narrow allowlisted volatile lines such as Cisco config timestamps.
- Reports unauthorized drift outside maintenance windows.
- Reports planned drift during active maintenance windows.
- Records previous and current config hashes in reports.

### Topology Validation

- Checks physical/logical neighbors for every reachable device.
- Tries LLDP first.
- Falls back to CDP when LLDP is disabled, unsupported, empty, or unparseable.
- Stores normalized neighbor state under `backups/<device-name>/neighbors.yaml`.
- Compares neighbor state against the approved topology baseline.
- Treats missing expected IP phones as informational.
- Flags infrastructure neighbor changes, missing uplinks, unexpected devices, and non-phone devices replacing expected phones.

### Security Checks

- Scans running configs for risky Cisco configuration patterns.
- Flags Telnet on VTY lines.
- Flags `enable password` instead of `enable secret`.
- Flags plaintext password forms.
- Flags weak/default SNMP communities such as `public` and `private`.
- Flags `ip http server`.
- Flags missing SSH version 2 hardening where SSH is configured.
- Flags broad VTY access without access-class restrictions.
- Redacts sensitive values from report context.

### 24/7 Monitoring

- Runs continuously with `python -m netconfigguard monitor`.
- Checks every 2 hours by default.
- Supports configurable intervals.
- Uses a lock file to prevent overlapping backup, monitor, and approval writes.
- Writes machine-readable reports and alert summaries.
- Continues checking other devices when one device fails.

### Maintenance Mode

- Supports scheduled maintenance windows through `maintenance.yaml`.
- Supports manual maintenance mode for urgent troubleshooting.
- Marks drift during maintenance as `planned_change_observed`.
- Automatically approves eligible planned changes after maintenance ends.
- Blocks automatic approval when a device is unreachable, topology is uncertain, or critical security findings exist.
- Saves old baselines in `baseline-history/` for at least 72 hours as rollback copies.

## Network Collection

Network collection is handled through `netconfigguard/collector.py`. The collector is designed to gather operational state only and does not make configuration changes.

### Collected Commands

- `show running-config`
- `show lldp neighbors detail`
- `show cdp neighbors detail`

### Collection Safety Model

The tool intentionally avoids configuration commands and write actions. It does not enter configuration mode, save device configs, reload devices, change interfaces, modify VLANs, alter routing, or update credentials on network equipment.

If SSH fails, the device state is treated as unknown:

- The previous backup is preserved.
- The baseline is not updated.
- Maintenance auto-approval is blocked for that device.
- Drift, topology, and security checks are skipped for that device.
- Reports include the error reason, retry count, and last successful backup time when known.
- Repeated failures escalate severity after three failed cycles.

## Architecture Flow

1. `netconfigguard.cli` parses the command and options.
2. `netconfigguard.inventory` loads enabled devices from the YAML inventory.
3. `netconfigguard.credentials` loads shared credentials from environment variables.
4. `netconfigguard.lock` prevents overlapping write operations.
5. `netconfigguard.collector` connects with Netmiko and collects config plus LLDP/CDP neighbor data.
6. `netconfigguard.drift`, `netconfigguard.security`, and `netconfigguard.topology` evaluate the collected state.
7. `netconfigguard.maintenance` classifies active or completed maintenance windows.
8. `netconfigguard.approvals` tracks pending and completed baseline approvals.
9. `netconfigguard.baseline` writes backups, approved baselines, and rollback history.
10. `netconfigguard.reports` and `netconfigguard.alerts` write YAML/JSON reports and alert logs.
11. `netconfigguard.git_ops` stages and commits tool-managed backup/report/baseline changes.

## Project Layout

- `main.py`: compatibility entrypoint that runs the CLI.
- `netconfigguard/cli.py`: command-line interface and command routing.
- `netconfigguard/collector.py`: Netmiko collection, LLDP-first topology discovery, and CDP fallback.
- `netconfigguard/inventory.py`: YAML inventory loading and validation.
- `netconfigguard/credentials.py`: environment-based credential loading.
- `netconfigguard/drift.py`: running-config normalization, hashing, and baseline comparison.
- `netconfigguard/security.py`: built-in Cisco security checks.
- `netconfigguard/topology.py`: neighbor normalization, endpoint classification, and topology drift detection.
- `netconfigguard/maintenance.py`: scheduled and manual maintenance-window handling.
- `netconfigguard/approvals.py`: pending maintenance approval and approval audit tracking.
- `netconfigguard/baseline.py`: backup writing, baseline initialization, baseline promotion, and rollback retention.
- `netconfigguard/reports.py`: YAML and JSON report generation.
- `netconfigguard/alerts.py`: alert summary and alert log generation.
- `netconfigguard/git_ops.py`: Git dirty-state protection and local commit helper.
- `netconfigguard/lock.py`: lock-file protection for write operations.
- `devices.example.yaml`: sample device inventory.
- `maintenance.example.yaml`: sample scheduled maintenance file.
- `tests/`: pytest coverage for inventory, credentials, drift, security, topology, maintenance, locking, reports, alerts, and approval behavior.

## Configuration

Create a device inventory file named `devices.yaml`.

```yaml
devices:
  - name: core-sw01
    host: 10.0.0.10
    device_type: cisco_ios
    role: core_switch
    site: hq
    port: 22
    enabled: true
    tags:
      - core
      - l3
```

Create a scheduled maintenance file named `maintenance.yaml` when planned changes are needed.

```yaml
windows:
  - id: core-upgrade-001
    start: "2026-07-04T22:00:00+03:00"
    end: "2026-07-05T01:00:00+03:00"
    devices:
      - core-sw01
      - core-sw02
    sites: []
    reason: "Core switch upgrade and VLAN cleanup"
    approver: "Eden"
    ticket: "CHG-1042"
```

Maintenance timestamps must include a timezone offset.

## Environment Variables

Set these variables locally and do not commit real secrets.

### Network Device Login

- `NETOPS_USERNAME`: SSH username for managed devices.
- `NETOPS_PASSWORD`: SSH password for managed devices.
- `NETOPS_SECRET`: optional Cisco enable secret.

Example:

```powershell
$env:NETOPS_USERNAME='admin'
$env:NETOPS_PASSWORD='your-password'
$env:NETOPS_SECRET='your-enable-secret'
```

## Installation

This project uses `uv`.

```powershell
uv sync --dev
```

You can also use the installed console command through `uv run`.

```powershell
uv run netconfigguard --help
```

The older `gitops` command is kept as a compatibility alias.

## Run

Run one backup and validation cycle:

```powershell
uv run netconfigguard backup --inventory devices.yaml --maintenance-file maintenance.yaml
```

Run continuously:

```powershell
uv run netconfigguard monitor --inventory devices.yaml --maintenance-file maintenance.yaml --interval-minutes 120
```

Validate existing backups without connecting to devices:

```powershell
uv run netconfigguard check --inventory devices.yaml --maintenance-file maintenance.yaml
```

Create initial baselines from successful backups:

```powershell
uv run netconfigguard init-baselines --inventory devices.yaml
```

Start manual maintenance mode:

```powershell
uv run netconfigguard maintenance start --device core-sw01 --reason "Troubleshooting uplink issue" --approver Eden --ticket INC-2044
```

Stop manual maintenance mode:

```powershell
uv run netconfigguard maintenance stop --device core-sw01
```

## Reports

Each run writes reports under `reports/`.

- `reports/latest.yaml`: latest machine-readable YAML report.
- `reports/latest.json`: latest machine-readable JSON report.
- `reports/<run-id>.yaml`: archived YAML report.
- `reports/<run-id>.json`: archived JSON report.
- `reports/latest-alerts.yaml`: latest alert summary.
- `reports/alerts.log`: append-only alert log.

Runtime state is stored under `.netconfigguard-state/`.

- `.netconfigguard-state/failures.yaml`: consecutive SSH failure tracking.
- `.netconfigguard-state/manual-maintenance.yaml`: active manual maintenance windows.
- `.netconfigguard-state/pending-approvals.yaml`: planned changes waiting for post-window approval.
- `.netconfigguard-state/approval-audit.yaml`: automatic and manual approval audit records.
- `.netconfigguard-state/netconfigguard.lock`: active write-operation lock file.

## Test

Run the test suite:

```powershell
uv run pytest
```

The tests validate inventory parsing, credential loading, config normalization, security rules, topology drift, IP phone behavior, maintenance windows, manual maintenance mode, unreachable-device handling, report and alert generation, dirty Git protection, and automatic approval guardrails without connecting to real network devices.

Current verified result:

```text
19 passed
```

## Important Note

Running configurations can contain sensitive values such as SNMP communities, local user hashes, keys, and pre-shared keys. Treat this repository as sensitive infrastructure data. Reports redact secret context, but full backups are stored as operational evidence and should be protected with the same care as production network configuration.

