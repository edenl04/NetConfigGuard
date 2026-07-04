from __future__ import annotations

import re

from netconfigguard.models import Finding
from netconfigguard.redact import redact_config


def check_security(device_name: str, config: str) -> list[Finding]:
    findings: list[Finding] = []
    redacted = redact_config(config)
    lines = redacted.splitlines()

    if re.search(r"(?im)^\s*transport input(?:\s+\S+)*\s+telnet(?:\s|$)", config):
        findings.append(
            Finding(
                device=device_name,
                category="security",
                severity="critical",
                rule_id="SEC_VTY_TELNET",
                message="Telnet is allowed on VTY lines.",
                context=_matching_lines(lines, r"^\s*transport input.*telnet"),
                remediation="Use SSH only on VTY lines, for example 'transport input ssh'.",
            )
        )

    if re.search(r"(?im)^\s*enable password\b", config):
        findings.append(
            Finding(
                device=device_name,
                category="security",
                severity="high",
                rule_id="SEC_ENABLE_PASSWORD",
                message="enable password is configured instead of enable secret.",
                context=_matching_lines(lines, r"^\s*enable password\b"),
                remediation="Replace enable password with enable secret.",
            )
        )

    if re.search(r"(?im)^\s*password\s+0\s+\S+", config):
        findings.append(
            Finding(
                device=device_name,
                category="security",
                severity="high",
                rule_id="SEC_PLAINTEXT_PASSWORD",
                message="Plaintext password form is present.",
                context=_matching_lines(lines, r"^\s*password\s+0\s+"),
                remediation="Use secret/hash based authentication and remove plaintext passwords.",
            )
        )

    if re.search(r"(?im)^\s*snmp-server community\s+(public|private)(?:\s|$)", config):
        findings.append(
            Finding(
                device=device_name,
                category="security",
                severity="high",
                rule_id="SEC_WEAK_SNMP_COMMUNITY",
                message="Default SNMP community is configured.",
                context=_matching_lines(lines, r"^\s*snmp-server community\s+"),
                remediation="Remove default communities and use SNMPv3 where possible.",
            )
        )

    if re.search(r"(?im)^\s*ip http server\s*$", config):
        findings.append(
            Finding(
                device=device_name,
                category="security",
                severity="medium",
                rule_id="SEC_HTTP_SERVER",
                message="Insecure HTTP server is enabled.",
                context=_matching_lines(lines, r"^\s*ip http server\s*$"),
                remediation="Disable HTTP with 'no ip http server' or use hardened HTTPS only.",
            )
        )

    if re.search(r"(?im)^\s*line vty\b", config) and not re.search(r"(?im)^\s*access-class\s+\S+\s+in\b", config):
        findings.append(
            Finding(
                device=device_name,
                category="security",
                severity="medium",
                rule_id="SEC_VTY_NO_ACCESS_CLASS",
                message="VTY lines do not appear to restrict source access with access-class.",
                context=_matching_lines(lines, r"^\s*line vty\b"),
                remediation="Apply an access-class to VTY lines to restrict management sources.",
            )
        )

    if re.search(r"(?im)^\s*ip ssh\b", config) and not re.search(r"(?im)^\s*ip ssh version 2\s*$", config):
        findings.append(
            Finding(
                device=device_name,
                category="security",
                severity="medium",
                rule_id="SEC_SSH_VERSION",
                message="SSH is configured but SSH version 2 is not explicitly enforced.",
                context=_matching_lines(lines, r"^\s*ip ssh\b"),
                remediation="Configure 'ip ssh version 2'.",
            )
        )

    return findings


def has_critical_security(findings: list[Finding]) -> bool:
    return any(finding.severity == "critical" for finding in findings)


def _matching_lines(lines: list[str], pattern: str) -> str:
    regex = re.compile(pattern, re.IGNORECASE)
    matches = [line for line in lines if regex.search(line)]
    return "\n".join(matches[:5])

