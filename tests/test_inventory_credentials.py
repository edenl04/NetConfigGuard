from pathlib import Path

import pytest

from netconfigguard.credentials import CredentialError, load_credentials
from netconfigguard.inventory import InventoryError, load_inventory


def test_load_inventory_filters_disabled_devices(tmp_path: Path) -> None:
    inventory = tmp_path / "devices.yaml"
    inventory.write_text(
        """
devices:
  - name: core-sw01
    host: 10.0.0.1
    site: hq
    enabled: true
  - name: old-sw
    host: 10.0.0.2
    enabled: false
""",
        encoding="utf-8",
    )

    devices = load_inventory(inventory)

    assert [device.name for device in devices] == ["core-sw01"]
    assert devices[0].device_type == "cisco_ios"
    assert devices[0].port == 22


def test_load_inventory_rejects_duplicate_names(tmp_path: Path) -> None:
    inventory = tmp_path / "devices.yaml"
    inventory.write_text(
        """
devices:
  - name: sw1
    host: 10.0.0.1
  - name: sw1
    host: 10.0.0.2
""",
        encoding="utf-8",
    )

    with pytest.raises(InventoryError, match="Duplicate"):
        load_inventory(inventory)


def test_load_credentials_from_env_mapping() -> None:
    credentials = load_credentials(
        {
            "NETOPS_USERNAME": "admin",
            "NETOPS_PASSWORD": "secret-password",
            "NETOPS_SECRET": "enable-secret",
        }
    )

    assert credentials.username == "admin"
    assert credentials.password == "secret-password"
    assert credentials.secret == "enable-secret"


def test_load_credentials_requires_password() -> None:
    with pytest.raises(CredentialError, match="NETOPS_PASSWORD"):
        load_credentials({"NETOPS_USERNAME": "admin"})

