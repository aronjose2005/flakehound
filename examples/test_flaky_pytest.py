"""A REAL pytest test (with a fixture) that is flaky due to randomness."""
import random
import pytest


@pytest.fixture
def players():
    return ["alice", "bob", "carol"]


def pick_winner(options):
    return random.choice(options)


def test_winner(players):           # <- takes a fixture, like real tests do
    winner = pick_winner(players)
    assert winner == "alice"        # flaky: true only ~1/3 of the time