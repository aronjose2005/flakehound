"""End-to-end tests for the CLI entry point (flakehound.cli.main)."""
import json

import pytest

from flakehound import cli

RANDOM_DEMO = "examples/flaky_random.py::test_alice_wins"
STABLE_DEMO = "examples/stable_pass.py::test_add"


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "flakehound" in capsys.readouterr().out


def test_reports_flaky_and_exits_nonzero(capsys):
    rc = cli.main([RANDOM_DEMO, "-n", "40", "--no-color"])
    out = capsys.readouterr().out
    assert "FLAKY" in out
    assert "RANDOM" in out
    # a reproduced flake gates CI: non-zero exit
    assert rc == 1


def test_exit_zero_overrides(capsys):
    rc = cli.main([RANDOM_DEMO, "-n", "40", "--no-color", "--exit-zero"])
    capsys.readouterr()
    assert rc == 0


def test_json_output_is_valid(capsys):
    rc = cli.main([RANDOM_DEMO, "-n", "40", "--json", "--exit-zero"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["flaky"] is True
    assert "RANDOM" in data["verdict"]["category"]


def test_stable_test_exits_zero(capsys):
    rc = cli.main([STABLE_DEMO, "-n", "8", "--no-color"])
    out = capsys.readouterr().out
    assert "No flakiness" in out
    assert rc == 0
