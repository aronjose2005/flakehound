"""Tests for the terminal/JSON reporter and its colour handling."""
import json

from flakehound import reporter
from flakehound.localizer import Signals, Candidate
from flakehound.classifier import Verdict, RANDOM, _FIXES


def _signals(passes=6, fails=4):
    cand = Candidate(
        file="app.py", line=8, score=2.1,
        reasons=["non-deterministic source: random.choice() [random]"],
        source="return random.choice(options)",
    )
    return Signals(
        passes=passes, fails=fails, fail_anchor=("t.py", 7),
        exc_type="AssertionError", exc_msg="rec == 'blocked_item'",
        duration_pass_mean=0.0, duration_fail_mean=0.0, duration_effect=1.0,
        nondet_sources=[("app.py", 8, "random.choice()", "random")],
        discriminating_vars=[], candidates=[cand],
    )


def _verdict():
    return Verdict(RANDOM, "HIGH", ["a random source is on the path"], _FIXES[RANDOM])


def test_render_flaky_mentions_culprit():
    reporter.use_color(False)
    out = reporter.render("t::x", _signals(), _verdict())
    assert "FLAKY" in out
    assert "RANDOM" in out
    assert "app.py:8" in out


def test_render_all_pass():
    reporter.use_color(False)
    out = reporter.render("t::x", _signals(passes=10, fails=0), _verdict())
    assert "No flakiness" in out


def test_render_all_fail():
    reporter.use_color(False)
    out = reporter.render("t::x", _signals(passes=0, fails=10), _verdict())
    assert "failed every run" in out


def test_render_json_shape():
    data = json.loads(reporter.render_json("t::x", _signals(), _verdict()))
    assert data["flaky"] is True
    assert data["runs"]["total"] == 10
    assert data["candidates"][0]["line"] == 8


def test_color_toggle():
    reporter.use_color(True)
    assert "\033[" in reporter._c("x", "32")
    reporter.use_color(False)
    assert reporter._c("x", "32") == "x"
