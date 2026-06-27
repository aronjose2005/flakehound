"""Integration test for the pytest plugin via a real subprocess `pytest` run.

Exercises the full --flakehound path: collection narrowing, taking over the
test call, and printing the root-cause report — including a culprit that lives
in imported application code.
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NODE = "examples/test_flaky_appcode.py::test_no_blocked_recommendation"


def test_flakehound_plugin_reports_root_cause():
    result = subprocess.run(
        [sys.executable, "-m", "pytest",
         "examples/test_flaky_appcode.py",
         "--flakehound", NODE,
         "-s", "-q", "-p", "no:cacheprovider"],
        cwd=REPO, capture_output=True, text=True, timeout=180,
    )
    combined = result.stdout + result.stderr
    assert "FLAKEHOUND" in combined
    assert "FLAKY" in combined
    # the real culprit is in the imported app code, not the test file
    assert "app_service" in combined
