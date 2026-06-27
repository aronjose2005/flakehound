"""Unit tests for the subtle localizer heuristics."""
from flakehound import localizer


def test_numeric_cleanly_separated_is_discriminating():
    # pass values all below fail values -> a real threshold separates them
    assert localizer._is_discriminating(["0.1", "0.2"], ["0.9", "1.0"])


def test_numeric_overlapping_is_not_discriminating():
    # ranges overlap (like a per-run timestamp) -> not a signal
    assert not localizer._is_discriminating(["0.1", "0.9"], ["0.2", "1.0"])


def test_categorical_disjoint_and_repeated_is_discriminating():
    # 'winner' is always alice on pass, bob on fail
    assert localizer._is_discriminating(["alice", "alice"], ["bob", "bob"])


def test_unique_per_run_ids_are_not_discriminating():
    # disjoint but every value unique (like a uuid) -> rejected
    assert not localizer._is_discriminating(["id1", "id2"], ["id3", "id4"])


def test_empty_side_is_not_discriminating():
    assert not localizer._is_discriminating([], ["x"])


def test_ochiai_ranks_failure_only_lines_highest():
    only_in_fail = localizer._ochiai(passed_with=0, failed_with=5, total_failed=5)
    mostly_in_pass = localizer._ochiai(passed_with=5, failed_with=1, total_failed=5)
    assert only_in_fail > mostly_in_pass
    assert localizer._ochiai(0, 0, 0) == 0.0
