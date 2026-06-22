"""A test that is flaky because of TIMING (a random delay sometimes blows the budget)."""
import time
import random


def do_work():
    time.sleep(random.uniform(0.0, 0.05))   # variable work duration
    return "done"


def test_completes_quickly():
    start = time.perf_counter()
    result = do_work()
    elapsed = time.perf_counter() - start
    assert result == "done"
    assert elapsed < 0.025   # flaky: fails when the random delay exceeds the budget
