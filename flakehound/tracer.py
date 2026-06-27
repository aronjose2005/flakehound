"""
Line-level execution tracer.

Uses sys.settrace to record, for every line executed in *user* code (we
deliberately skip the standard library and site-packages), the line number,
a snapshot of primitive local variables, and a high-resolution timestamp.

IMPORTANT — the observer effect:
    sys.settrace slows execution by ~50-100x. That means any *timing* the test
    measures internally is meaningless while tracing is on (a Heisenbug: the act
    of observing changes the result). Flakehound therefore separates concerns:
      * runner.run_untraced()  -> clean outcomes + real wall-clock durations
      * runner.run_traced()    -> execution paths + variable values
    The tracer below is only ever used by run_traced(). Timing-based reasoning
    comes from the untraced phase.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field

from . import scope

# Only these types are cheap and safe to snapshot every line.
_PRIMITIVES = (int, float, str, bool, bytes, type(None))

# Hard caps so a pathological test can't blow up memory.
_MAX_EVENTS = 200_000
_MAX_VARS_PER_LINE = 20
_MAX_REPR_LEN = 80


@dataclass
class LineEvent:
    file: str
    line: int
    t: float                       # seconds since trace start (unreliable! see note)
    locals: dict = field(default_factory=dict)


@dataclass
class Trace:
    events: list = field(default_factory=list)
    truncated: bool = False

    def last_locals_per_line(self) -> dict:
        """Map (file, line) -> the most recent locals snapshot at that line."""
        out = {}
        for ev in self.events:
            out[(ev.file, ev.line)] = ev.locals
        return out

    def executed_lines(self) -> set:
        return {(ev.file, ev.line) for ev in self.events}

    def successor_map(self) -> dict:
        """Map (file, line) -> set of the (file, line) that executed *next*.
        Lines with >1 distinct successor across a run are control-flow forks."""
        succ: dict = {}
        for a, b in zip(self.events, self.events[1:]):
            key = (a.file, a.line)
            succ.setdefault(key, set()).add((b.file, b.line))
        return succ


class Tracer:
    """Context manager that installs a line tracer scoped to user code.

    Traces explicit `target_files` plus any file under `roots` (the project
    source), while skipping stdlib / site-packages / venv / Flakehound itself.
    """

    def __init__(self, target_files, roots=None):
        self.target_files = {os.path.abspath(f) for f in target_files}
        self.roots = [os.path.abspath(r) for r in (roots or [])]
        self.excludes = scope.default_excludes()
        self._cache: dict = {}     # filename -> bool (is target)
        self.trace_obj = Trace()
        self._t0 = 0.0

    def _is_target(self, filename: str) -> bool:
        hit = self._cache.get(filename)
        if hit is None:
            hit = scope.is_user_file(
                filename, self.target_files, self.roots, self.excludes
            )
            self._cache[filename] = hit
        return hit

    @staticmethod
    def _snapshot(frame) -> dict:
        snap = {}
        for i, (k, v) in enumerate(frame.f_locals.items()):
            if i >= _MAX_VARS_PER_LINE:
                break
            if k.startswith("__"):
                continue
            if isinstance(v, _PRIMITIVES):
                try:
                    snap[k] = repr(v)[:_MAX_REPR_LEN]
                except Exception:
                    pass
        return snap

    def _dispatch(self, frame, event, arg):
        filename = frame.f_code.co_filename
        if event == "call":
            # Return a local tracer only for user frames; deeper user frames
            # still reach this global dispatcher via their own 'call' events.
            return self._dispatch if self._is_target(filename) else None
        if event == "line" and self._is_target(filename):
            if len(self.trace_obj.events) >= _MAX_EVENTS:
                self.trace_obj.truncated = True
                return None
            self.trace_obj.events.append(
                LineEvent(
                    file=filename,
                    line=frame.f_lineno,
                    t=time.perf_counter() - self._t0,
                    locals=self._snapshot(frame),
                )
            )
        return self._dispatch

    def __enter__(self) -> Tracer:
        self._t0 = time.perf_counter()
        sys.settrace(self._dispatch)
        return self

    def __exit__(self, *exc) -> bool:
        sys.settrace(None)
        return False
