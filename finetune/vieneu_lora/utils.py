"""Small helpers shared by the finetune scripts."""
from __future__ import annotations

import os
from pathlib import Path


def safe_path(p: str | os.PathLike, base: str | os.PathLike | None = None) -> Path:
    """Resolve ``p`` (relative to ``base``, default: the working directory) and refuse
    anything that escapes ``base``. The scripts run all their reads/writes through this,
    so a stray CLI argument can only touch files under the folder you launched them from."""
    root = os.path.realpath(str(base) if base else os.getcwd())
    full = os.path.realpath(os.path.join(root, os.path.normpath(str(p))))
    if os.path.commonpath([root, full]) != root:
        raise ValueError(f"Path {p!r} is outside the working directory {root!r}")
    return Path(full)
