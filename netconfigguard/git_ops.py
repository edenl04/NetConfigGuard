from __future__ import annotations

import subprocess
from pathlib import Path


TOOL_MANAGED_PREFIXES = (
    "backups/",
    "baselines/",
    "baseline-history/",
    "reports/",
    ".netconfigguard-state/",
)


class GitError(RuntimeError):
    pass


def check_dirty_scope(root: Path) -> None:
    result = _git(root, "status", "--porcelain")
    unrelated = []
    for line in result.stdout.splitlines():
        path = line[3:].replace("\\", "/")
        if not path or path in {"README.md", "pyproject.toml", "main.py"} or path.startswith("netconfigguard/") or path.startswith("tests/"):
            continue
        if not path.startswith(TOOL_MANAGED_PREFIXES):
            unrelated.append(path)
    if unrelated:
        raise GitError(f"Unrelated working tree changes exist: {', '.join(unrelated)}")


def commit_if_changed(root: Path, message: str) -> bool:
    status = _git(root, "status", "--porcelain").stdout.strip()
    if not status:
        return False
    _git(root, "add", "backups", "baselines", "baseline-history", "reports", ".netconfigguard-state")
    staged = _git(root, "diff", "--cached", "--quiet", check=False)
    if staged.returncode == 0:
        return False
    _git(root, "commit", "-m", message)
    return True


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise GitError(result.stderr.strip() or result.stdout.strip())
    return result

