"""
Root-cause localization.

Given the untraced runs (outcomes + durations + failure line) and the traced
runs (execution paths + variable snapshots), produce a ranked list of candidate
root-cause locations plus the signals that justify them.

Techniques combined:
  1. Failure anchor      - the line where the assertion/exception surfaced
                           (from the untraced phase traceback). Cheap, reliable.
  2. Spectrum (Ochiai)   - classic spectrum-based fault localization: a line that
                           runs in failing runs but not passing ones is suspicious.
                           Ochiai is a well-established SBFL formula.
  3. Control-flow forks  - lines after which execution goes *different* places in
                           passing vs failing runs. These are decision points
                           where the non-determinism expresses itself.
  4. Discriminating vars - variables whose captured values systematically differ
                           between passing and failing runs (statistical
                           debugging, à la Cooperative Bug Isolation).
  5. Nondeterminism scan - static AST scan of the involved files for known
                           sources of non-determinism (time, random, unordered
                           iteration, threads, env, network).
  6. Duration signal     - if failing runs are consistently slower, that points
                           at a timing/async root cause.
"""

from __future__ import annotations

import ast
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field


# (module_attr, call) pairs and bare names that introduce non-determinism.
_NONDET_CALLS = {
    "time": {"time", "monotonic", "perf_counter", "sleep"},
    "random": {"random", "randint", "choice", "choices", "uniform", "shuffle", "sample", "getrandbits"},
    "uuid": {"uuid1", "uuid4"},
    "secrets": {"token_hex", "token_bytes", "choice", "randbelow"},
    "os": {"urandom", "getpid"},
    "datetime": {"now", "utcnow", "today"},
}
_NONDET_HINTS_TIMING = {"sleep", "wait", "timeout", "perf_counter", "monotonic", "time"}
_NONDET_HINTS_THREAD = {"Thread", "Lock", "start", "join", "acquire", "release"}


@dataclass
class Candidate:
    file: str
    line: int
    score: float
    reasons: list = field(default_factory=list)
    source: str = ""


@dataclass
class Signals:
    passes: int
    fails: int
    fail_anchor: tuple | None          # (file, line) where failures surfaced
    exc_type: str | None
    exc_msg: str | None
    duration_pass_mean: float
    duration_fail_mean: float
    duration_effect: float             # fail_mean / pass_mean (>1 => slower fails)
    nondet_sources: list               # list of (file, line, label, kind)
    discriminating_vars: list          # list of (file, line, var, pass_vals, fail_vals)
    candidates: list                   # ranked Candidate list


def _read_source_lines(path: str) -> list:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read().splitlines()
    except Exception:
        return []


def _source_at(path: str, line: int) -> str:
    lines = _read_source_lines(path)
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return ""


def _scan_nondeterminism(files) -> list:
    """AST-scan each file for known non-determinism sources. Returns
    (file, line, label, kind) where kind in {timing, random, thread, env}."""
    found = []
    for path in files:
        src = "\n".join(_read_source_lines(path))
        if not src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            # module.attr(...) calls e.g. random.choice(...), time.sleep(...)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                mod = node.func.value.id if isinstance(node.func.value, ast.Name) else None
                label = f"{mod}.{attr}()" if mod else f".{attr}()"
                kind = None
                if mod in _NONDET_CALLS and attr in _NONDET_CALLS[mod]:
                    kind = "timing" if attr in _NONDET_HINTS_TIMING else (
                        "thread" if attr in _NONDET_HINTS_THREAD else "random")
                    if mod == "datetime":
                        kind = "timing"
                elif attr in _NONDET_HINTS_THREAD:
                    kind = "thread"
                if kind:
                    found.append((path, node.lineno, label, kind))
            # iterating an unordered collection without sorting: set(...) / dict.keys()
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "set":
                found.append((path, node.lineno, "set(...) iteration order", "random"))
    return found


def _ochiai(passed_with: int, failed_with: int, total_failed: int) -> float:
    denom = math.sqrt(total_failed * (passed_with + failed_with))
    return (failed_with / denom) if denom > 0 else 0.0


def _as_floats(values):
    out = []
    for v in values:
        s = v.strip("'\"")
        try:
            out.append(float(s))
        except (ValueError, AttributeError):
            return None
    return out


def _is_discriminating(pass_vals, fail_vals) -> bool:
    """A variable discriminates pass from fail if:
      - numeric: the two value ranges are cleanly separated by a threshold
        (so a per-run timestamp like `start`, whose ranges overlap, is rejected
        while `elapsed`, which is always <budget on pass and >budget on fail,
        is kept); or
      - categorical: the value-sets are disjoint AND at least one class repeats a
        value (so a unique-per-run id is rejected, but `winner`='alice' is kept).
    """
    if not pass_vals or not fail_vals:
        return False
    pf, ff = _as_floats(pass_vals), _as_floats(fail_vals)
    if pf is not None and ff is not None:
        return max(pf) < min(ff) or max(ff) < min(pf)
    ps, fs = set(pass_vals), set(fail_vals)
    if not ps.isdisjoint(fs):
        return False
    repeats = len(ps) < len(pass_vals) or len(fs) < len(fail_vals)
    return repeats


def localize(untraced, traced, target_files) -> Signals:
    passes = sum(1 for r in untraced if r.passed)
    fails = sum(1 for r in untraced if not r.passed)

    # --- failure anchor + exception ---
    fail_runs = [r for r in untraced if not r.passed]
    fail_anchor = None
    exc_type = exc_msg = None
    if fail_runs:
        # most common surfacing line
        counts = defaultdict(int)
        for r in fail_runs:
            if r.fail_file and r.fail_line:
                counts[(r.fail_file, r.fail_line)] += 1
        if counts:
            fail_anchor = max(counts, key=counts.get)
        exc_type = fail_runs[0].exc_type
        exc_msg = fail_runs[0].exc_msg

    # --- duration signal (from untraced runs) ---
    p_durs = [r.duration for r in untraced if r.passed]
    f_durs = [r.duration for r in untraced if not r.passed]
    p_mean = statistics.mean(p_durs) if p_durs else 0.0
    f_mean = statistics.mean(f_durs) if f_durs else 0.0
    effect = (f_mean / p_mean) if p_mean > 0 else (float("inf") if f_mean > 0 else 1.0)

    # --- spectrum (Ochiai) over traced runs ---
    t_pass = [r.trace for r in traced if r.passed]
    t_fail = [r.trace for r in traced if not r.passed]
    passed_with = defaultdict(int)
    failed_with = defaultdict(int)
    for tr in t_pass:
        for key in tr.executed_lines():
            passed_with[key] += 1
    for tr in t_fail:
        for key in tr.executed_lines():
            failed_with[key] += 1
    spectrum = {}
    for key in set(passed_with) | set(failed_with):
        spectrum[key] = _ochiai(passed_with[key], failed_with[key], len(t_fail))

    # --- control-flow forks: lines whose successor differs pass vs fail ---
    def successors(traces):
        agg = defaultdict(set)
        for tr in traces:
            for k, succ in tr.successor_map().items():
                agg[k] |= succ
        return agg
    succ_pass = successors(t_pass)
    succ_fail = successors(t_fail)
    forks = set()
    for key in set(succ_pass) & set(succ_fail):
        if succ_pass[key] != succ_fail[key]:
            forks.add(key)

    # --- discriminating variables ---
    disc = []
    pass_locals = [tr.last_locals_per_line() for tr in t_pass]
    fail_locals = [tr.last_locals_per_line() for tr in t_fail]
    common_lines = set()
    for d in pass_locals + fail_locals:
        common_lines |= set(d.keys())
    for key in common_lines:
        var_pass = defaultdict(list)
        var_fail = defaultdict(list)
        for d in pass_locals:
            for var, val in d.get(key, {}).items():
                var_pass[var].append(val)
        for d in fail_locals:
            for var, val in d.get(key, {}).items():
                var_fail[var].append(val)
        for var in set(var_pass) & set(var_fail):
            if _is_discriminating(var_pass[var], var_fail[var]):
                disc.append((key[0], key[1], var,
                             sorted(set(var_pass[var]))[:4],
                             sorted(set(var_fail[var]))[:4]))

    # --- non-determinism scan (over ALL code that actually executed) ---
    executed_files = set(target_files)
    for tr in t_pass + t_fail:
        for ev in tr.events:
            executed_files.add(ev.file)
    nondet = _scan_nondeterminism(executed_files)

    # --- assemble & rank candidates ---
    cand: dict = {}

    def bump(file, line, pts, reason):
        c = cand.get((file, line))
        if c is None:
            c = Candidate(file=file, line=line, score=0.0,
                          source=_source_at(file, line))
            cand[(file, line)] = c
        c.score += pts
        c.reasons.append(reason)

    if fail_anchor:
        bump(*fail_anchor, 3.0, f"failure surfaced here ({exc_type})")
    for key, s in spectrum.items():
        if s > 0:
            bump(key[0], key[1], 2.0 * s, f"spectrum suspiciousness {s:.2f}")
    for key in forks:
        bump(key[0], key[1], 1.5, "execution diverges here (pass vs fail take different paths)")
    for f, ln, var, pv, fv in disc:
        bump(f, ln, 1.5, f"variable '{var}' differs (pass={pv} vs fail={fv})")
    for f, ln, label, kind in nondet:
        bump(f, ln, 1.0, f"non-deterministic source: {label} [{kind}]")

    ranked = sorted(cand.values(), key=lambda c: c.score, reverse=True)

    return Signals(
        passes=passes, fails=fails,
        fail_anchor=fail_anchor, exc_type=exc_type, exc_msg=exc_msg,
        duration_pass_mean=p_mean, duration_fail_mean=f_mean, duration_effect=effect,
        nondet_sources=nondet, discriminating_vars=disc,
        candidates=ranked,
    )
