from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from netconfigguard.models import Credentials, Device, DeviceCollectionResult, Neighbor
from netconfigguard.topology import normalize_neighbor


CollectorFn = Callable[[Device, Credentials, int], DeviceCollectionResult]


def collect_device(device: Device, credentials: Credentials, retries: int = 3) -> DeviceCollectionResult:
    last_error_type = ""
    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            return _collect_device_once(device, credentials, attempt - 1)
        except Exception as exc:  # Netmiko imports are optional until runtime.
            last_error_type = exc.__class__.__name__
            last_error = str(exc)
    return DeviceCollectionResult(
        device=device,
        success=False,
        error_type=_classify_error(last_error_type, last_error),
        error=last_error,
        retries=retries,
        collected_at=datetime.now(timezone.utc),
    )


async def collect_devices(
    devices: list[Device],
    credentials: Credentials,
    batch_size: int,
    retries: int = 3,
    collector: CollectorFn = collect_device,
) -> list[DeviceCollectionResult]:
    semaphore = asyncio.Semaphore(batch_size)

    async def run_one(device: Device) -> DeviceCollectionResult:
        async with semaphore:
            return await asyncio.to_thread(collector, device, credentials, retries)

    return await asyncio.gather(*(run_one(device) for device in devices))


def _collect_device_once(device: Device, credentials: Credentials, retry_count: int) -> DeviceCollectionResult:
    from netmiko import ConnectHandler
    from netmiko.exceptions import NetmikoAuthenticationException, NetmikoBaseException, NetmikoTimeoutException, ReadException, ReadTimeout

    connection = {
        "device_type": device.device_type,
        "host": device.host,
        "username": credentials.username,
        "password": credentials.password,
        "port": device.port,
        "conn_timeout": device.timeout,
        "auth_timeout": device.timeout,
        "banner_timeout": device.timeout,
        "read_timeout_override": max(device.timeout, 30),
        "fast_cli": True,
    }
    if credentials.secret:
        connection["secret"] = credentials.secret

    try:
        with ConnectHandler(**connection) as net_connect:
            if credentials.secret:
                net_connect.enable()
            running_config = net_connect.send_command("show running-config", read_timeout=max(device.timeout, 60))
            neighbors, status, protocol = _collect_neighbors(net_connect)
            return DeviceCollectionResult(
                device=device,
                success=True,
                running_config=running_config,
                neighbors=neighbors,
                neighbor_status=status,
                neighbor_protocol=protocol,
                retries=retry_count,
                collected_at=datetime.now(timezone.utc),
            )
    except (NetmikoTimeoutException, NetmikoAuthenticationException, ReadTimeout, ReadException, NetmikoBaseException):
        raise


def _collect_neighbors(net_connect: Any) -> tuple[list[Neighbor], str, str]:
    lldp_output = net_connect.send_command("show lldp neighbors detail", use_textfsm=True, read_timeout=30)
    lldp_neighbors = _parse_textfsm_neighbors(lldp_output, "lldp")
    if lldp_neighbors:
        return lldp_neighbors, "ok", "lldp"

    cdp_output = net_connect.send_command("show cdp neighbors detail", use_textfsm=True, read_timeout=30)
    cdp_neighbors = _parse_textfsm_neighbors(cdp_output, "cdp")
    if cdp_neighbors:
        return cdp_neighbors, "ok", "cdp"
    return [], "uncertain", ""


def _parse_textfsm_neighbors(output: Any, protocol: str) -> list[Neighbor]:
    if isinstance(output, list):
        neighbors = [normalize_neighbor(item, protocol) for item in output if isinstance(item, dict)]
        return [neighbor for neighbor in neighbors if neighbor.local_interface and neighbor.neighbor_id]
    return []


def _classify_error(error_type: str, error: str) -> str:
    text = f"{error_type} {error}".lower()
    if "auth" in text:
        return "ssh_authentication_failed"
    if "timeout" in text or "timed" in text:
        return "ssh_timeout"
    return "ssh_connection_failed"

