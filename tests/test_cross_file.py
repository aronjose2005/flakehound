"""Regression test for Flakehound's headline capability: finding the root
cause of a flaky test when the non-determinism lives in the *application
code the test imports*, not in the test file itself.

`examples/test_flaky_appcode.py` asserts on `get_recommendation()`, whose
bug (a bare `random.choice`) lives in `examples/app_service.py`. A tool that
only blamed the assertion line would miss the real culprit; Flakehound should
surface the app-code line among its ranked candidates.
"""
import os
import sys
import importlib.util

from flakehound import runner, localizer, classifier

EXAMPLES = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples"))


def _load(filename, func_name):
    """Import an example test module and hand back its test callable + path.

    `examples/test_flaky_appcode.py` does `from app_service import ...` at
    import time, so the examples dir must be importable first.
    """
    if EXAMPLES not in sys.path:
        sys.path.insert(0, EXAMPLES)
    path = os.path.join(EXAMPLES, filename)
    spec = importlib.util.spec_from_file_location("_fh_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, func_name), path


def test_root_cause_found_in_imported_app_code():
    test_cb, test_path = _load("test_flaky_appcode.py", "test_no_blocked_recommendation")
    app_path = os.path.join(EXAMPLES, "app_service.py")
    files = [test_path, app_path]

    n = 60
    untraced = runner.run_untraced(test_cb, files, n=n)
    traced = runner.run_traced(test_cb, files, n=n)
    signals = localizer.localize(untraced, traced, files)
    verdict = classifier.classify(signals)

    # 1. We actually reproduced the flakiness (both outcomes observed).
    assert signals.passes > 0 and signals.fails > 0

    # 2. It is correctly classified as a randomness/non-determinism flake.
    assert "RANDOM" in verdict.category

    # 3. The marquee guarantee: a candidate points at the *app code*, not just
    #    the test's assertion — specifically the `random.choice` line.
    top = signals.candidates[:4]
    app_lines = [c.line for c in top if os.path.basename(c.file) == "app_service.py"]
    assert 8 in app_lines, (
        "expected the random.choice() line (app_service.py:8) among the top "
        f"candidates, got: {[(os.path.basename(c.file), c.line) for c in top]}"
    )
