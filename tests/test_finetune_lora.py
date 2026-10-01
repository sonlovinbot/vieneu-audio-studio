"""Runs finetune/tests in a separate interpreter.

Several test modules in this folder replace ``torch`` in ``sys.modules`` with stubs at
import time; the finetune data/label tests need the real package, so they get their own
process. Skipped when torch is not installed.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _has_real_torch() -> bool:
    # Checked in a child process: this process may hold a stubbed `torch`.
    return subprocess.run([sys.executable, "-c", "import torch.utils.data"], capture_output=True).returncode == 0


def test_finetune_lora_data_and_labels():
    if not _has_real_torch():
        pytest.skip("torch not installed")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(ROOT / "finetune" / "tests")],
        capture_output=True, text=True, cwd=str(ROOT), timeout=600,
    )
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-2000:]
