from __future__ import annotations

import hashlib
from typing import Any

import yaml


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_data(data: Any) -> str:
    payload = yaml.safe_dump(data, sort_keys=True, default_flow_style=False)
    return sha256_text(payload)

