from __future__ import annotations

import difflib
import re
from pathlib import Path


IGNORED_LINE_PATTERNS = [
    re.compile(r"^! Last configuration change at "),
    re.compile(r"^! NVRAM config last updated at "),
    re.compile(r"^ntp clock-period \d+"),
]


def normalize_config(config: str) -> list[str]:
    lines: list[str] = []
    for raw_line in config.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.rstrip()
        if any(pattern.search(line) for pattern in IGNORED_LINE_PATTERNS):
            continue
        lines.append(line)
    while lines and lines[-1] == "":
        lines.pop()
    return lines


def config_hash(config: str) -> str:
    from netconfigguard.hashing import sha256_text

    return sha256_text("\n".join(normalize_config(config)) + "\n")


def compare_configs(baseline: str | None, current: str) -> dict[str, object]:
    if baseline is None:
        return {"status": "missing_baseline", "diff": []}
    base_lines = normalize_config(baseline)
    current_lines = normalize_config(current)
    if base_lines == current_lines:
        return {"status": "clean", "diff": []}
    diff = list(
        difflib.unified_diff(
            base_lines,
            current_lines,
            fromfile="baseline",
            tofile="current",
            lineterm="",
        )
    )
    return {"status": "changed", "diff": diff}


def read_baseline_config(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")

