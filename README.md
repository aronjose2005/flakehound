# 🐺 Flakehound

**Find out _why_ a test is flaky — not just _that_ it is.**

Flaky tests (tests that pass and fail on the same code) are a systemic tax on
software teams — Google has reported that ~1 in 7 of their tests showed flakiness
at some point. A whole market exists to *detect* and *quarantine* them
(Trunk, BuildPulse, Datadog CI). **Almost nothing tells a developer the one thing
they actually need: the line of code causing the non-determinism, and why.**

That gap is real and proven-tractable: Google's internal research located
flaky-test root causes at the code level with 82% accuracy — but it was never
shipped as a tool anyone can use. Flakehound is an open, developer-facing tool
that does exactly this for **Python**.

```
════════════════════════════════════════════════════════════════
  FLAKEHOUND  ·  test_completes_quickly
════════════════════════════════════════════════════════════════

  Ran 12×   7 passed   5 failed   (42% failure rate)  →  FLAKY

  VERDICT   TIMING / ASYNC   (confidence: HIGH)
    • a blocking timing primitive (sleep/wait) is on the executed path
    • failing runs are 3.7x slower on average (39ms vs 11ms)

  FAILS AT   examples/flaky_timing.py:16
      16 │ assert elapsed < 0.025

  ROOT-CAUSE CANDIDATES  (ranked)
    1. flaky_timing.py:16   score 5.6
         assert elapsed < 0.025
         ↳ failure surfaced here (AssertionError)
         ↳ variable 'elapsed' differs (pass<0.0036  vs  fail>0.0259)
    2. flaky_timing.py:7    score 3.1
         time.sleep(random.uniform(0.0, 0.05))
         ↳ non-deterministic source: time.sleep() [timing]

  SUGGESTED FIX
    Replace fixed sleeps/timeouts with active polling or an explicit
    wait for the condition. Never assert work finished within a budget.
════════════════════════════════════════════════════════════════
```

## How it works (the 30-second version)

A flaky test takes **different execution paths on pass vs fail** — otherwise the
result would be deterministic. Flakehound runs the test many times and diffs the
passing runs against the failing runs to find *where* and *why* they diverge:

1. **Two-phase execution.** One phase runs the test untraced (clean outcomes +
   real wall-clock timing); another traces every line + variable. (Tracing is
   ~50× slow, so timing-based reasoning never trusts traced runs — a flaky test
   is itself a Heisenbug, and we refuse to become one.)
2. **Spectrum-based localization (Ochiai).** Lines that run in failing runs but
   not passing ones get ranked suspicious.
3. **Discriminating-variable analysis.** Variables whose values cleanly separate
   pass from fail (e.g. `elapsed` always under budget on pass, over on fail).
4. **Non-determinism scan.** A static AST pass flags the usual culprits —
   `time.sleep`, `random.*`, unordered `set` iteration, threads, clocks.
5. **Classification + fix.** Maps the evidence to a category (timing / randomness
   / order-dependency / concurrency) with a confidence and a concrete fix.

Zero runtime dependencies — the core is pure standard library.

## Install

```bash
pip install -e .          # from this repo
```

## Usage

```bash
flakehound path/to/test_file.py::test_function [-n RUNS]
```

Try the bundled examples:

```bash
flakehound examples/flaky_random.py::test_alice_wins
flakehound examples/flaky_timing.py::test_completes_quickly
flakehound examples/stable_pass.py::test_add        # → "No flakiness reproduced"
```

> **Status: v0.1 (alpha).** The core localization engine is working today on plain
> test callables. The pytest plugin, order-dependency detection, the optional
> LLM explanation layer, and the CI/GitHub Action are on the roadmap — see
> [`BUILD_PLAN.md`](BUILD_PLAN.md).

## Accuracy

Flakehound's claims are measured, not asserted. The methodology and the labeled
benchmark live in [`BUILD_PLAN.md`](BUILD_PLAN.md) (§ Validation). The headline
README number — *"correct category X% / root cause in top-5 Y% on N real-world
Python flaky tests"* — is filled in once the benchmark is run at milestone M5.

## License

MIT.
