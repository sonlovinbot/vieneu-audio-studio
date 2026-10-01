"""Runs tests/fused/cases.py in a separate interpreter (same reason as test_finetune_lora:
other modules here stub ``torch`` at import time). Skipped without torch."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _has_real_torch() -> bool:
    return subprocess.run([sys.executable, "-c", "import torch.utils.data"], capture_output=True).returncode == 0


def test_fused_frame_cases():
    if not _has_real_torch():
        pytest.skip("torch not installed")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(ROOT / "tests" / "fused" / "cases.py")],
        capture_output=True, text=True, cwd=str(ROOT), timeout=900,
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
