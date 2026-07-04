from __future__ import annotations

import netmiko

from netconfigguard.collector import collect_device
from netconfigguard.credentials import Credentials
from netconfigguard.models import Device, DeviceCollectionResult
from netconfigguard.runner import run_backup
from netconfigguard.yamlio import read_yaml


class FakeConnection:
    def __init__(self, enabled: bool, enable_raises: bool = False) -> None:
        self.enabled = enabled
        self.enable_raises = enable_raises
        self.enable_calls = 0
        self.commands: list[str] = []

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def check_enable_mode(self) -> bool:
        return self.enabled

    def enable(self) -> None:
        self.enable_calls += 1
        if self.enable_raises:
            raise ValueError("failed to enter enable mode")
        self.enabled = True

    def send_command(self, command: str, **kwargs):
        self.commands.append(command)
        if command == "show running-config":
            return "hostname sw1\n"
        return []


def test_collect_device_skips_enable_when_already_privileged(monkeypatch) -> None:
    fake = FakeConnection(enabled=True)
    monkeypatch.setattr(netmiko, "ConnectHandler", lambda **kwargs: fake)

    result = collect_device(Device(name="sw1", host="10.0.0.1"), Credentials("u", "p", "enable-secret"))

    assert result.success is True
    assert fake.enable_calls == 0
    assert "show running-config" in fake.commands


def test_collect_device_uses_secret_when_enable_is_needed(monkeypatch) -> None:
    fake = FakeConnection(enabled=False)
    captured_connection = {}

    def connect_handler(**kwargs):
        captured_connection.update(kwargs)
        return fake

    monkeypatch.setattr(netmiko, "ConnectHandler", connect_handler)

    result = collect_device(Device(name="sw1", host="10.0.0.1"), Credentials("u", "p", "enable-secret"))

    assert result.success is True
    assert captured_connection["secret"] == "enable-secret"
    assert fake.enable_calls == 1
    assert "show running-config" in fake.commands


def test_collect_device_reports_missing_enable_secret(monkeypatch) -> None:
    fake = FakeConnection(enabled=False)
    monkeypatch.setattr(netmiko, "ConnectHandler", lambda **kwargs: fake)

    result = collect_device(Device(name="sw1", host="10.0.0.1"), Credentials("u", "p"))

    assert result.success is False
    assert result.error_type == "enable_secret_required"
    assert "NETOPS_SECRET" in result.error
    assert fake.enable_calls == 0
    assert fake.commands == []


def test_collect_device_reports_bad_enable_secret(monkeypatch) -> None:
    fake = FakeConnection(enabled=False, enable_raises=True)
    monkeypatch.setattr(netmiko, "ConnectHandler", lambda **kwargs: fake)

    result = collect_device(Device(name="sw1", host="10.0.0.1"), Credentials("u", "p", "wrong-secret"))

    assert result.success is False
    assert result.error_type == "enable_authentication_failed"
    assert fake.enable_calls == 1
    assert fake.commands == []


def test_enable_secret_required_is_reported_in_alerts(tmp_path) -> None:
    inventory = tmp_path / "devices.yaml"
    maintenance = tmp_path / "maintenance.yaml"
    inventory.write_text("devices:\n  - name: sw1\n    host: 10.0.0.1\n", encoding="utf-8")
    maintenance.write_text("windows: []\n", encoding="utf-8")

    def collector(device, credentials, retries):
        return DeviceCollectionResult(
            device=device,
            success=False,
            error_type="enable_secret_required",
            error="Enable secret required: set NETOPS_SECRET or use a privilege 15 account.",
        )

    code, report = run_backup(
        tmp_path,
        inventory,
        maintenance,
        collector=collector,
        credentials=Credentials("u", "p"),
        commit=False,
    )

    latest_alerts = read_yaml(tmp_path / "reports" / "latest-alerts.yaml")
    assert code == 2
    assert report["devices"][0]["reason"] == "enable_secret_required"
    assert "Configure NETOPS_SECRET" in latest_alerts["alerts"][0]["message"]
