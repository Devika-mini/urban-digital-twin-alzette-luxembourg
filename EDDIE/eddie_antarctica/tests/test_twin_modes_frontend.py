"""Run the dependency-free JavaScript checks of the mode selection and the Casual mode with Node."""
from pathlib import Path
import shutil
import subprocess

import pytest

TERRIAJS = Path(__file__).resolve().parents[1] / "terriajs"


def test_mode_selection_and_shared_state() -> None:
    """Casual by default, last choice remembered, Casual buttons act on the In-depth state."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed; run terriajs/tests/mode_checks.js in the terria_map container instead.")
    result = subprocess.run(
        [node, str(TERRIAJS / "tests" / "mode_checks.js"), str(TERRIAJS)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "mode checks passed" in result.stdout, result.stdout + result.stderr
