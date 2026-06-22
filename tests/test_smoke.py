"""Flakehound's own tests. A flaky-test tool with flaky tests would be ironic."""
import os
from flakehound import runner, localizer, classifier

EX = os.path.join(os.path.dirname(__file__), "..", "examples")


def _load(file, fn):
    import importlib.util
    path = os.path.abspath(os.path.join(EX, file))
    spec = importlib.util.spec_from_file_location("_t", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, fn), path


def _analyze(file, fn, n=40):
    cb, path = _load(file, fn)
    files = [path]
    u = runner.run_untraced(cb, files, n=n)
    t = runner.run_traced(cb, files, n=n)
    s = localizer.localize(u, t, files)
    return s, classifier.classify(s)


def test_detects_randomness():
    s, v = _analyze("flaky_random.py", "test_alice_wins")
    assert s.passes > 0 and s.fails > 0           # reproduced flakiness
    assert "RANDOM" in v.category                  # correct category
    # root cause (random.choice line 6) is in the top candidates
    assert any(c.line == 6 for c in s.candidates[:4])


def test_detects_timing():
    s, v = _analyze("flaky_timing.py", "test_completes_quickly")
    assert s.passes > 0 and s.fails > 0
    assert "TIMING" in v.category
    assert any(c.line == 7 for c in s.candidates[:4])  # the sleep line


def test_stable_is_not_flaky():
    s, v = _analyze("stable_pass.py", "test_add")
    assert s.fails == 0
