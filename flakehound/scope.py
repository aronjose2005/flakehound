"""
Deciding which files count as 'user code' worth tracing.

We trace the user's project source (so we catch root causes in application code,
not just the test file) while skipping the standard library, site-packages, the
virtualenv, and Flakehound's own code.
"""

from __future__ import annotations

import os
import sys
import sysconfig


def _abs(p: str) -> str:
    return os.path.abspath(p)


def _under(path: str, base: str) -> bool:
    """True if `path` is `base` or sits inside it (no false prefix matches)."""
    return path == base or path.startswith(base + os.sep)


def default_excludes() -> set:
    """Directories we never trace into."""
    ex = {sys.prefix, sys.base_prefix, os.path.dirname(_abs(__file__))}
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        try:
            p = sysconfig.get_path(key)
            if p:
                ex.add(p)
        except Exception:
            pass
    return {_abs(p) for p in ex if p}


def is_user_file(filename: str, target_files: set, roots: list, excludes: set) -> bool:
    """A file is in scope if it's an explicit target OR lives under a watched
    project root — and is not under any excluded dir / package cache."""
    try:
        ap = _abs(filename)
    except Exception:
        return False
    if "site-packages" in ap or "dist-packages" in ap or "__pycache__" in ap:
        return False
    for ex in excludes:
        if _under(ap, ex):
            return False
    if ap in target_files:
        return True
    for r in roots:
        if _under(ap, r):
            return True
    return False
