from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Device:
    name: str
    host: str
    device_type: str = "cisco_ios"
    role: str = ""
    site: str = ""
    port: int = 22
    enabled: bool = True
    timeout: int = 30
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str
    secret: str | None = None


@dataclass
class Neighbor:
    local_interface: str
    neighbor_id: str
    neighbor_interface: str = ""
    protocol: str = ""
    capabilities: str = ""
    platform: str = ""
    management_ip: str = ""
    endpoint_type: str = "unknown"

    def key(self) -> str:
        return self.local_interface.lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_interface": self.local_interface,
            "neighbor_id": self.neighbor_id,
            "neighbor_interface": self.neighbor_interface,
            "protocol": self.protocol,
            "capabilities": self.capabilities,
            "platform": self.platform,
            "management_ip": self.management_ip,
            "endpoint_type": self.endpoint_type,
        }


@dataclass
class DeviceCollectionResult:
    device: Device
    success: bool
    running_config: str = ""
    neighbors: list[Neighbor] = field(default_factory=list)
    neighbor_status: str = "unknown"
    neighbor_protocol: str = ""
    error_type: str = ""
    error: str = ""
    retries: int = 0
    collected_at: datetime | None = None


@dataclass
class Finding:
    device: str
    category: str
    severity: str
    rule_id: str
    message: str
    context: str = ""
    remediation: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "device": self.device,
            "category": self.category,
            "severity": self.severity,
            "rule_id": self.rule_id,
            "message": self.message,
            "context": self.context,
            "remediation": self.remediation,
        }

