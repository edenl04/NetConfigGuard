from __future__ import annotations

import os

from netconfigguard.models import Credentials


class CredentialError(RuntimeError):
    pass


def load_credentials(env: dict[str, str] | None = None) -> Credentials:
    source = env if env is not None else os.environ
    username = source.get("NETOPS_USERNAME", "").strip()
    password = source.get("NETOPS_PASSWORD", "")
    secret = source.get("NETOPS_SECRET") or None
    if not username:
        raise CredentialError("Missing NETOPS_USERNAME")
    if not password:
        raise CredentialError("Missing NETOPS_PASSWORD")
    return Credentials(username=username, password=password, secret=secret)

