"""A test that is flaky because of RANDOMNESS (passes ~1/3 of the time)."""
import random


def pick_winner(players):
    return random.choice(players)


def test_alice_wins():
    players = ["alice", "bob", "carol"]
    winner = pick_winner(players)
    assert winner == "alice"   # flaky: only true ~33% of runs
