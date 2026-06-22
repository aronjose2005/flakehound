"""
Flake categorisation.

Maps the Signals produced by the localizer onto one of the well-known flaky-test
categories, with a confidence band and a concrete, category-specific fix
suggestion. The categories follow the taxonomy reported across the flaky-test
literature (timing/async, test-order dependency, randomness, concurrency, ...).

Order-dependency note: robustly proving order dependency requires running the
test in isolation vs. in suite order (planned for v0.3). The MVP flags *likely*
order dependency from shared/global state signals and is honest about the
confidence.
"""

from __future__ import annotations

from dataclasses import dataclass


TIMING = "TIMING / ASYNC"
RANDOM = "RANDOMNESS / NON-DETERMINISM"
ORDER = "TEST-ORDER DEPENDENCY (likely)"
CONCURRENCY = "CONCURRENCY (likely)"
UNKNOWN = "UNDETERMINED"

_FIXES = {
    TIMING: (
        "Replace fixed sleeps/timeouts with active polling or an explicit wait "
        "for the condition (e.g. poll until ready, or use your framework's "
        "`wait_for`). Never assert that work finished within a hard-coded budget."
    ),
    RANDOM: (
        "Remove non-determinism from the assertion: seed the RNG for the test, "
        "inject a fixed value, sort before comparing unordered collections, or "
        "assert a property (e.g. membership) instead of an exact value."
    ),
    ORDER: (
        "Make the test self-contained: create and tear down its own state, avoid "
        "reading shared/global/module state set by other tests, and reset fixtures "
        "between tests so execution order can't change the outcome."
    ),
    CONCURRENCY: (
        "Synchronise access to shared state (locks/queues), or make the unit under "
        "test deterministic for the test by removing the inter-thread race. Don't "
        "rely on a particular thread interleaving."
    ),
    UNKNOWN: (
        "Inspect the ranked candidates below and the divergence point. Re-run with "
        "more iterations (-n) to strengthen the signal."
    ),
}


@dataclass
class Verdict:
    category: str
    confidence: str          # HIGH / MEDIUM / LOW
    rationale: list
    fix: str


# Wall-clock differences below this are noise (scheduler jitter, GC), not timing.
_MIN_MEANINGFUL_GAP_S = 0.003   # 3 ms


def classify(signals) -> Verdict:
    rationale = []
    kinds = {k for *_rest, k in signals.nondet_sources}

    timing_source = any(k == "timing" for *_r, k in signals.nondet_sources)
    random_source = any(k == "random" for *_r, k in signals.nondet_sources)
    thread_source = any(k == "thread" for *_r, k in signals.nondet_sources)
    # A *blocking* timing primitive (sleep/wait) is far stronger evidence than a
    # mere clock read (perf_counter is usually just measurement, not the cause).
    blocking_timing = any(
        ("sleep" in label or "wait" in label)
        for _f, _ln, label, k in signals.nondet_sources if k == "timing"
    )

    gap = signals.duration_fail_mean - signals.duration_pass_mean
    slower_fails = (
        (signals.duration_effect != float("inf")
         and signals.duration_effect >= 1.5 and gap >= _MIN_MEANINGFUL_GAP_S)
        or (signals.duration_effect == float("inf")
            and signals.duration_fail_mean >= _MIN_MEANINGFUL_GAP_S)
    )

    # 1) Timing/async: a blocking timing primitive is present, OR failures are
    #    *meaningfully* slower (millisecond-scale, not jitter).
    if blocking_timing or slower_fails:
        if blocking_timing:
            rationale.append("a blocking timing primitive (sleep/wait) is on the executed path")
        if slower_fails and signals.duration_pass_mean > 0:
            rationale.append(
                f"failing runs are {signals.duration_effect:.1f}x slower on average "
                f"({signals.duration_fail_mean*1000:.0f}ms vs "
                f"{signals.duration_pass_mean*1000:.0f}ms)"
            )
        conf = "HIGH" if (blocking_timing and slower_fails) else "MEDIUM"
        return Verdict(TIMING, conf, rationale, _FIXES[TIMING])

    # 2) Randomness: a random source executed and a value discriminates pass/fail.
    if random_source:
        rationale.append("a randomness source (random/uuid/secrets/unordered set) is on the executed path")
        if signals.discriminating_vars:
            v = signals.discriminating_vars[0]
            rationale.append(f"variable '{v[2]}' takes disjoint values on pass vs fail")
            return Verdict(RANDOM, "HIGH", rationale, _FIXES[RANDOM])
        return Verdict(RANDOM, "MEDIUM", rationale, _FIXES[RANDOM])

    # 3) Concurrency.
    if thread_source:
        rationale.append("threading primitives are on the executed path; outcome likely depends on interleaving")
        return Verdict(CONCURRENCY, "LOW", rationale, _FIXES[CONCURRENCY])

    # 4) Order dependency (weak MVP signal): a discriminating variable with no
    #    in-test randomness/timing source suggests state leaked in from elsewhere.
    if signals.discriminating_vars and not kinds:
        v = signals.discriminating_vars[0]
        rationale.append(
            f"variable '{v[2]}' differs across runs with no in-test non-determinism "
            "source — value likely leaks in from another test's state"
        )
        return Verdict(ORDER, "LOW", rationale, _FIXES[ORDER])

    rationale.append("no decisive signal; see ranked candidates")
    return Verdict(UNKNOWN, "LOW", rationale, _FIXES[UNKNOWN])
