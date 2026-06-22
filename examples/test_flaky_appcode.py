"""The flaky behaviour lives in app_service.py, NOT in this test file."""
from app_service import get_recommendation


def test_no_blocked_recommendation():
    rec = get_recommendation("u1")
    assert rec != "blocked_item"   # flaky ~1/3 — root cause is in app_service.py