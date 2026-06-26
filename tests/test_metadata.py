"""Cheap guards that keep package metadata honest.

These catch the classic release-day mistakes: bumping the version in one
place but not the other, or renaming a classifier category that the README
and output format depend on. Written without `tomllib` so it runs on every
supported interpreter (3.9+), where `tomllib` may be unavailable.
"""
import os
import re

import flakehound
from flakehound import classifier

PYPROJECT = os.path.join(os.path.dirname(__file__), "..", "pyproject.toml")


def _declared_version():
    with open(PYPROJECT, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
            if m:
                return m.group(1)
    raise AssertionError("no version found in pyproject.toml")


def test_version_matches_pyproject():
    assert flakehound.__version__ == _declared_version()


def test_classifier_categories_are_stable():
    # The output format and README contract depend on these existing.
    for name in ("TIMING", "RANDOM", "ORDER", "CONCURRENCY", "UNKNOWN"):
        value = getattr(classifier, name)
        assert isinstance(value, str) and value
