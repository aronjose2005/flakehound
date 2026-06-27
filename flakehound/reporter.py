"""Human-readable terminal report."""

from __future__ import annotations

import json
import os
import sys


# Colour is auto-detected: off when piped/redirected or when NO_COLOR is set
# (https://no-color.org), on for an interactive terminal. use_color() forces it.
_USE_COLOR = None  # None => auto-detect; otherwise a forced bool


def use_color(value) -> None:
    """Force ANSI colour on/off. Pass None to restore auto-detection."""
    global _USE_COLOR
    _USE_COLOR = value


def _color_enabled() -> bool:
    if _USE_COLOR is not None:
        return bool(_USE_COLOR)
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _rel(path: str | None) -> str:
    if not path:
        return "?"
    try:
        return os.path.relpath(path)
    except Exception:
        return path


# minimal ANSI without a dependency; suppressed when colour is disabled
def _c(text, code):
    if not _color_enabled():
        return str(text)
    return f"\033[{code}m{text}\033[0m"


def render(target: str, signals, verdict) -> str:
    out = []
    bar = "═" * 64
    out.append(_c(bar, "90"))
    out.append(_c(f"  FLAKEHOUND  ·  {target}", "1;36"))
    out.append(_c(bar, "90"))

    total = signals.passes + signals.fails
    if signals.fails == 0:
        out.append(_c("\n  ✓ No flakiness reproduced", "1;32"))
        out.append(f"    Ran {signals.passes} times, all passed. "
                   "Increase -n if you expect rare flakes.")
        return "\n".join(out)
    if signals.passes == 0:
        out.append(_c("\n  ✗ Test failed every run", "1;31"))
        out.append("    This looks like a genuine, consistent failure — not a flake.")
        out.append(f"    {signals.exc_type}: {signals.exc_msg}")
        return "\n".join(out)

    rate = 100.0 * signals.fails / total
    out.append(f"\n  Ran {total}×   "
               + _c(f"{signals.passes} passed", "32") + "   "
               + _c(f"{signals.fails} failed", "31")
               + f"   ({rate:.0f}% failure rate)  →  " + _c("FLAKY", "1;33"))

    out.append("\n  " + _c("VERDICT", "1") + f"   {_c(verdict.category, '1;35')}"
               f"   (confidence: {verdict.confidence})")
    for r in verdict.rationale:
        out.append(f"    • {r}")

    if signals.fail_anchor:
        f, ln = signals.fail_anchor
        out.append("\n  " + _c("FAILS AT", "1")
                   + f"   {_rel(f)}:{ln}")
        src = signals.candidates and next(
            (c.source for c in signals.candidates
             if (c.file, c.line) == signals.fail_anchor), "")
        if src:
            out.append(f"    {ln:>4} │ {src}")

    out.append("\n  " + _c("ROOT-CAUSE CANDIDATES", "1") + "  (ranked)")
    for i, c in enumerate(signals.candidates[:5], 1):
        out.append(f"    {i}. {_rel(c.file)}:{c.line}   "
                   + _c(f"score {c.score:.1f}", "90"))
        if c.source:
            out.append(f"         {c.source}")
        for reason in c.reasons[:3]:
            out.append(f"         ↳ {reason}")

    out.append("\n  " + _c("SUGGESTED FIX", "1;32"))
    for line in _wrap(verdict.fix, 58):
        out.append(f"    {line}")
    out.append(_c("\n" + bar, "90"))
    return "\n".join(out)


def _wrap(text: str, width: int) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines
