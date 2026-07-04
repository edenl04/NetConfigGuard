from netconfigguard.drift import compare_configs, normalize_config
from netconfigguard.security import check_security
from netconfigguard.topology import compare_topology, normalize_neighbor


def test_normalize_config_ignores_only_allowlisted_volatile_lines() -> None:
    config = """!
! Last configuration change at 10:00:00 UTC Sat Jul 4 2026
hostname core-sw01
ntp clock-period 123456
ip route 0.0.0.0 0.0.0.0 10.0.0.1
"""

    assert normalize_config(config) == ["!", "hostname core-sw01", "ip route 0.0.0.0 0.0.0.0 10.0.0.1"]


def test_compare_configs_detects_meaningful_drift() -> None:
    baseline = "hostname core-sw01\nline vty 0 4\n transport input ssh\n"
    current = "hostname core-sw01\nline vty 0 4\n transport input telnet ssh\n"

    result = compare_configs(baseline, current)

    assert result["status"] == "changed"
    assert any("telnet" in line for line in result["diff"])


def test_security_checks_redact_secret_context() -> None:
    findings = check_security(
        "sw1",
        """
enable password 0 badsecret
snmp-server community public RO
line vty 0 4
 password 0 linepass
 transport input telnet ssh
""",
    )

    rule_ids = {finding.rule_id for finding in findings}
    assert "SEC_VTY_TELNET" in rule_ids
    assert "SEC_ENABLE_PASSWORD" in rule_ids
    assert "SEC_WEAK_SNMP_COMMUNITY" in rule_ids
    assert all("badsecret" not in finding.context for finding in findings)
    assert all("linepass" not in finding.context for finding in findings)


def test_topology_missing_phone_is_info_only() -> None:
    baseline = [
        {
            "local_interface": "Gi1/0/10",
            "neighbor_id": "SEP001122334455",
            "neighbor_interface": "Port 1",
            "endpoint_type": "phone",
        }
    ]

    result = compare_topology(baseline, [])

    assert result["status"] == "clean"
    assert result["changes"][0]["type"] == "phone_missing_info"


def test_topology_infrastructure_neighbor_change_is_drift() -> None:
    baseline = [
        {
            "local_interface": "Gi1/0/1",
            "neighbor_id": "dist-sw01",
            "neighbor_interface": "Gi0/1",
            "endpoint_type": "infrastructure",
        }
    ]
    current = [
        {
            "local_interface": "Gi1/0/1",
            "neighbor_id": "unknown-switch",
            "neighbor_interface": "Gi0/24",
            "endpoint_type": "infrastructure",
        }
    ]

    result = compare_topology(baseline, current)

    assert result["status"] == "changed"
    assert result["changes"][0]["severity"] == "high"


def test_normalize_neighbor_classifies_phone() -> None:
    neighbor = normalize_neighbor(
        {
            "local_interface": "Gi1/0/5",
            "neighbor": "SEP001122334455",
            "platform": "Cisco IP Phone 8841",
        },
        "cdp",
    )

    assert neighbor.endpoint_type == "phone"

