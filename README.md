# Flakehound

**Find out _why_ a test is flaky — not just _that_ it is.**

Flaky tests (tests that pass and fail on the same code) are a systemic tax on
software teams — Google has reported that ~1 in 7 of their tests showed flakiness
at some point. A whole market exists to *detect* and *quarantine* them
(Trunk, BuildPulse, Datadog CI). **Almost nothing tells a developer the one thing
they actually need: the line of code causing the non-determinism, and why.**

Flakehound closes that gap for **Python**. Point it at a flaky test and it runs
the test many times, diffs the passing runs against the failing runs, and reports
the root cause — including when the bug lives in the *application code* your test
imports, not just the test file.

```
════════════════════════════════════════════════════════════════
  FLAKEHOUND  ·  test_no_blocked_recommendation
════════════════════════════════════════════════════════════════

  Ran 10×   5 passed   5 failed   (50% failure rate)  →  FLAKY

  VERDICT   RANDOMNESS / NON-DETERMINISM   (confidence: HIGH)
    • a randomness source (random/uuid/secrets/unordered set) is on the executed path
    • variable 'rec' takes disjoint values on pass vs fail

  FAILS AT   examples/test_flaky_appcode.py:7
       7 │ assert rec != "blocked_item"

  ROOT-CAUSE CANDIDATES  (ranked)
    1. examples/test_flaky_appcode.py:7   score 5.7
         assert rec != "blocked_item"
         ↳ failure surfaced here (AssertionError)
         ↳ variable 'rec' differs (pass=['video_a','video_b'] vs fail=['blocked_item'])
    2. examples/app_service.py:8   score 2.2          ← the real culprit, in app code
         return random.choice(options)
         ↳ non-deterministic source: random.choice() [random]

  SUGGESTED FIX
    Remove non-determinism from the assertion: seed the RNG, inject a
    fixed value, sort before comparing, or assert a property instead.
════════════════════════════════════════════════════════════════
```

## How it works (the 30-second version)

A flaky test takes **different execution paths on pass vs fail** — otherwise the
result would be deterministic. Flakehound runs the test many times and diffs the
passing runs against the failing runs to find *where* and *why* they diverge:

1. **Two-phase execution.** One phase runs the test untraced (clean outcomes +
   real wall-clock timing); another traces every line + variable. Tracing is
   ~50× slow, so timing reasoning never trusts traced runs — a flaky test is
   itself a Heisenbug, and Flakehound refuses to become one.
2. **Spectrum-based localization (Ochiai).** Lines that run in failing runs but
   not passing ones are ranked suspicious.
3. **Discriminating-variable analysis.** Variables whose values cleanly separate
   pass from fail (e.g. `winner` is always `alice` on pass).
4. **Non-determinism scan.** A static AST pass over the code that *actually ran*
   flags the usual culprits — `time.sleep`, `random.*`, unordered `set`
   iteration, threads, clocks — **across every file the test touches.**
5. **Classification + fix.** Maps the evidence to a category with a confidence
   and a concrete fix.

Zero runtime dependencies — the core is pure standard library.

## Install

```bash
git clone https://github.com/aronjose2005/flakehound.git
cd flakehound
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

### As a pytest plugin (recommended)

Point it at any test in your suite by node id:

```bash
pytest --flakehound "tests/test_payments.py::test_charge"
```

It handles fixtures, setup/teardown, and parametrized tests, and finds root
causes in the application code your test imports.

### As a CLI (for plain test functions)

```bash
flakehound path/to/file.py::test_function
```

### Try the bundled demos

```bash
flakehound examples/flaky_random.py::test_alice_wins
flakehound examples/flaky_timing.py::test_completes_quickly
pytest examples/test_flaky_appcode.py --flakehound "examples/test_flaky_appcode.py::test_no_blocked_recommendation"
```

## Status

**v0.1 — working.** What's done:

- ✅ CLI **and** pytest plugin
- ✅ Two-phase tracing engine (observer-effect aware)
- ✅ Spectrum (Ochiai) localization + discriminating-variable analysis
- ✅ Non-determinism scanning across project source (catches app-code bugs)
- ✅ Classifier with confidence + targeted fixes
- ✅ Solid support for **timing/async** and **randomness** flakes (order-dependency
  and concurrency are currently heuristic)

Roadmap (see [`BUILD_PLAN.md`](BUILD_PLAN.md)): dedicated **order-dependency**
detection (run-in-isolation vs suite-order), an optional **LLM explanation**
layer, a **GitHub Action**, and a measured **accuracy benchmark**.

## Accuracy

Flakehound's claims will be *measured*, not asserted. The methodology and labeled
benchmark live in [`BUILD_PLAN.md`](BUILD_PLAN.md) (§ Validation); the headline
accuracy number is filled in at milestone M5.

## License

MIT — see [`LICENSE`](LICENSE).