"""Runs tests/fused/serve_guards.py in a separate interpreter (same reason as
test_fused_frame: other modules here stub ``torch`` at import time). Skipped
without torch + transformers; otherwise every case must pass, none may skip."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _has_real_torch() -> bool:
    probe = "import torch.utils.data, transformers"
    return subprocess.run([sys.executable, "-c", probe], capture_output=True).returncode == 0


def test_serve_guards():
    if not _has_real_torch():
        pytest.skip("torch / transformers not installed")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider",
         str(ROOT / "tests" / "fused" / "serve_guards.py")],
        capture_output=True, text=True, cwd=str(ROOT), timeout=600,
    )
    out = proc.stdout[-4000:] + proc.stderr[-2000:]
    assert proc.returncode == 0, out
    assert "skipped" not in proc.stdout, out
