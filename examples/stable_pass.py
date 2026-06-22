"""A deterministic test — Flakehound should report NO flakiness."""


def add(a, b):
    return a + b


def test_add():
    assert add(2, 2) == 4
