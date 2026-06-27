"""Shared test fixtures."""
import pytest

from flakehound import reporter


@pytest.fixture(autouse=True)
def _reset_reporter_color():
    """Reporter colour is module-level global state; reset it after every test
    so a test that forces colour on/off can't leak into the next one."""
    yield
    reporter.use_color(None)
