"""
Repeated test execution.

A flaky test, by definition, takes different execution paths on pass vs fail
(otherwise the result would be deterministic). To find *why*, we run it many
times and gather two complementary datasets:

  Phase 1 - run_untraced(): the ground truth.
      Real outcomes (pass/fail), real wall-clock durations, and the exact line
      where each failure was raised. Unaffected by tracing overhead.

  Phase 2 - run_traced(): the microscope.
      Full line-by-line execution paths + primitive variable snapshots, so we
      can diff passing runs against failing runs. Absolute timings here are
      meaningless (see tracer.py), but paths and values are valid.
"""

from __future__ import annotations

import os
import time
import traceback
from dataclasses import dataclass

from .tracer import Tracer, Trace
from . import scope


@dataclass
class UntracedRun:
    passed: bool
    duration: float
    fail_file: str | None = None     # file:line where the failure surfaced
    fail_line: int | None = None
    exc_type: str | None = None
    exc_msg: str | None = None


@dataclass
class TracedRun:
    passed: bool
    trace: Trace


def _surface_location(exc: BaseException, target_files, roots):
    """Walk the traceback to the *last* frame inside user code — that's where
    the assertion/exception actually surfaced (the test OR the app code)."""
    targets = {os.path.abspath(f) for f in target_files}
    abs_roots = [os.path.abspath(r) for r in (roots or [])]
    excludes = scope.default_excludes()
    tb = exc.__traceback__
    last = (None, None)
    while tb is not None:
        fn = tb.tb_frame.f_code.co_filename
        if scope.is_user_file(fn, targets, abs_roots, excludes):
            last = (fn, tb.tb_lineno)
        tb = tb.tb_next
    return last


def run_untraced(test_callable, target_files, n: int = 30,
                 stop_when_balanced: int = 5, roots=None) -> list:
    """Run the test up to n times, no tracing. Early-exit once we have at least
    `stop_when_balanced` passes AND failures (enough signal to diff)."""
    runs: list = []
    passes = fails = 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            test_callable()
            dur = time.perf_counter() - t0
            runs.append(UntracedRun(passed=True, duration=dur))
            passes += 1
        except BaseException as exc:  # noqa: BLE001 - we want every failure mode
            dur = time.perf_counter() - t0
            f, ln = _surface_location(exc, target_files, roots)
            runs.append(UntracedRun(
                passed=False, duration=dur,
                fail_file=f, fail_line=ln,
                exc_type=type(exc).__name__,
                exc_msg=str(exc)[:200],
            ))
            fails += 1
        if passes >= stop_when_balanced and fails >= stop_when_balanced:
            break
    return runs


def run_traced(test_callable, target_files, n: int = 20,
               want_each: int = 4, roots=None) -> list:
    """Run with tracing until we have at least `want_each` passing and failing
    traces (or hit n). Returns TracedRun list."""
    runs: list = []
    passes = fails = 0
    for _ in range(n):
        tracer = Tracer(target_files, roots=roots)
        try:
            with tracer:
                test_callable()
            runs.append(TracedRun(passed=True, trace=tracer.trace_obj))
            passes += 1
        except BaseException:  # noqa: BLE001
            runs.append(TracedRun(passed=False, trace=tracer.trace_obj))
            fails += 1
        if passes >= want_each and fails >= want_each:
            break
    return runs
