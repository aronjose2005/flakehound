# Flakehound — Build Plan & Technical Design

> **What this is:** the engineering design doc for Flakehound, a root-cause
> localization tool for flaky Python tests. It covers the system architecture,
> the exact tracing/diffing algorithms, a milestone roadmap with realistic
> timeboxes, and a validation methodology so the README can carry a *measured*
> accuracy number.

---

## 1. The wedge (why this is worth building)

The flaky-test market splits cleanly:

| Capability | Who does it | State |
|---|---|---|
| **Detect** which tests are flaky | Trunk, BuildPulse, Datadog CI, CircleCI, Mergify | Solved, commoditized |
| **Quarantine** flakes so they stop blocking merges | Trunk, BuildPulse | Solved |
| **Cluster** failures by category | TestDino, ContextQA (UI-focused) | Emerging, coarse |
| **Localize the root cause to a line + explain why** | Google's internal research (82% acc.) | **Proven, but no public/usable tool** |

Flakehound targets the empty box: **code-level "why + where," usable and open,
for regular developers.** It's de-risked (Google proved it's achievable) and
unoccupied (no public competitor does it). One-ecosystem focus — **Python /
pytest** — because Python's tracing hooks (`sys.settrace`, `sys.monitoring`)
make execution capture vastly easier than JVM bytecode instrumentation.

---

## 2. System architecture

### 2.1 Pipeline

```
   target test (file::function or pytest nodeid)
              │
              ▼
   ┌─────────────────────┐   Phase 1 (untraced): N runs
   │      RUNNER         │──▶ outcomes · wall-clock durations · failure line
   │  (two-phase exec)   │   Phase 2 (traced):   M runs
   └─────────────────────┘──▶ per-line paths · variable snapshots
              │
              ▼
   ┌─────────────────────┐   • spectrum (Ochiai) suspiciousness
   │     LOCALIZER       │   • control-flow fork detection
   │ (statistical core)  │   • discriminating-variable analysis
   └─────────────────────┘   • AST non-determinism scan + duration signal
              │  ranked candidates + signals
              ▼
   ┌─────────────────────┐   timing / randomness / order / concurrency
   │     CLASSIFIER      │──▶ category + confidence + targeted fix
   └─────────────────────┘
              │
              ▼
   ┌─────────────────────┐   terminal report  (v0.1)  ·  JSON  (v0.2)
   │  REPORTER / OUTPUT  │   PR comment / Action (v0.5) · LLM prose (v0.4)
   └─────────────────────┘
```

### 2.2 Components (as built in v0.1)

- **`tracer.py`** — `sys.settrace` line tracer, scoped to user files only
  (stdlib/site-packages skipped). Captures `(file, line, timestamp, primitive
  locals)` per line with hard memory caps.
- **`runner.py`** — runs the target repeatedly in two phases; early-exits once it
  has enough passing *and* failing samples to diff.
- **`localizer.py`** — the analytical core (see §3).
- **`classifier.py`** — rule-based category assignment over the localizer's
  signals, with confidence bands and category-specific fixes.
- **`reporter.py`** — human-readable terminal output.
- **`cli.py` / `__main__.py`** — entry point.

### 2.3 Design principle: respect the observer effect

`sys.settrace` slows execution ~50–100×, so any timing the test measures
internally is meaningless while tracing. A flaky test is *itself* a Heisenbug;
the tool must not become one. Hence the **two-phase split**: timing/outcome
truth comes from untraced runs; path/state detail comes from traced runs.
Reasoning that depends on wall-clock time never reads traced timings.

---

## 3. The tracing & diffing design (the technical heart)

### 3.1 What we capture

Per traced run we record an ordered list of `LineEvent(file, line, t, locals)`
for user code only. From that we derive: the **set** of executed lines, the
**successor map** (line → the lines that ran next), and **last-locals-per-line**
(primitive variable values).

### 3.2 Localization signals (combined, then ranked)

1. **Failure anchor** — walk the exception traceback to the *last* user-code
   frame. That's where the assertion surfaced. Cheap, reliable, always available.
   *(weight 3.0)*

2. **Spectrum-based fault localization (Ochiai).** Classic SBFL: for each line,
   count how many failing vs passing runs executed it, then score

   ```
   suspiciousness(line) = failed_with(line) / sqrt( total_failed · (failed_with + passed_with) )
   ```

   A line in all failing runs and no passing runs scores ~1.0. Ochiai is chosen
   over Tarantula for its better empirical accuracy in the SBFL literature.
   *(weight 2.0 × score)*

3. **Control-flow fork detection.** Align the aggregated successor maps of
   passing vs failing runs. A line whose *successor set differs* between the two
   classes is a decision point where the non-determinism expresses itself.
   *(weight 1.5)*

4. **Discriminating-variable analysis** (statistical debugging, à la Cooperative
   Bug Isolation). For each variable captured at a line, decide whether its
   values separate pass from fail:
   - **numeric** → require *clean threshold separation* (`max(pass) < min(fail)`
     or vice-versa). This is what rejects a per-run timestamp like `start`
     (overlapping ranges) while keeping `elapsed` (always under budget on pass,
     over on fail). **This separability test is the key to low-noise output.**
   - **categorical** → require disjoint value-sets *and* repetition within a
     class (rejects unique-per-run ids; keeps `winner='alice'`).
   *(weight 1.5)*

5. **Non-determinism scan.** Static AST pass over the involved files flags known
   sources: `time.sleep/perf_counter`, `random.*`, `uuid`, `secrets`, `datetime.now`,
   `os.urandom`, unordered `set(...)` iteration, threading primitives. Each is
   tagged `timing | random | thread`. *(weight 1.0)*

6. **Duration signal.** From untraced runs: `effect = mean(fail_durations) /
   mean(pass_durations)`. Guarded by an absolute floor (3 ms) so scheduler jitter
   can't masquerade as a timing cause.

All candidates accumulate a weighted score and are returned ranked, each with
its human-readable reasons and source line.

### 3.3 Classification logic

| Category | Trigger |
|---|---|
| **Timing / async** | a *blocking* timing primitive (`sleep`/`wait`) on the path, **or** failures meaningfully slower (≥1.5× and ≥3 ms gap) |
| **Randomness** | a randomness source on the path; HIGH if a variable also discriminates |
| **Concurrency** (likely) | threading primitives on the path (LOW confidence in MVP) |
| **Order-dependency** (likely) | a variable discriminates with *no* in-test non-determinism source → state leaked from elsewhere (LOW; real proof needs §4 isolation runs) |
| **Undetermined** | no decisive signal — show ranked candidates, suggest more runs |

### 3.4 Known limitations (honest list — these are roadmap items, not bugs)

- **Order-dependency** is only *guessed* in v0.1. Proving it needs isolation vs.
  suite-order runs (planned v0.3).
- **Concurrency** flakes are detected weakly; deterministic interleaving control
  is V2.
- **Accuracy is not 100%.** Target is *useful* (≈Google's 82% ballpark), with
  evidence the developer can verify — not an oracle.
- `sys.settrace` overhead is fine for one test but too slow for whole suites;
  v0.6 moves to `sys.monitoring` (PEP 669, Python 3.12+) for speed.

---

## 4. Milestone roadmap (realistic, part-time timeboxes)

> Assumes ~10–15 focused hrs/week alongside other commitments. Each milestone is
> independently demo-able and commit-able.

| Milestone | Scope | Timebox |
|---|---|---|
| **M0 — Core PoC** ✅ *(done)* | Tracer + two-phase runner + Ochiai localizer + discriminating-var analysis + classifier + reporter. Works on timing & randomness flakes; correct "no flakiness" path; own test suite green. | shipped |
| **M1 — Productionize the core** | pytest **plugin** (`pytest --flakehound <nodeid>`): handle fixtures, setup/teardown, parametrization, real test signatures. Robust user-file scoping. JSON output. Packaging, `--help`, error handling, CI for the repo itself. | 1–2 wks |
| **M2 — Strengthen localization** | Multi-occurrence line handling, branch-level (not just line-level) spectrum, data-flow link from failing assertion back to the non-det source, confidence calibration. | 1–2 wks |
| **M3 — Order-dependency** | Run-in-isolation vs run-in-suite-order detection; culprit-predecessor bisection (iDFlakies-style) to name the *polluting* test. This is a headline feature — order-dependency is one of the most common and most painful flake classes. | 1–2 wks |
| **M4 — LLM explanation layer** | Optional: feed the *structured evidence* (ranked lines, category, diffs) to an LLM to produce a plain-English "why" + a concrete diff-style fix. Grounded on evidence only (no blind guessing). This is the AI/ML showcase. | 1 wk |
| **M5 — CI integration + launch** | GitHub Action that ingests reruns from CI and posts a root-cause **PR comment**; demo GIF; build the validation benchmark (§5) and put the real accuracy number in the README; write the launch post (Show HN / r/Python / dev.to). | 2 wks |
| **V2 (post-launch)** | `sys.monitoring` fast tracer; real concurrency support (interleaving exploration); deterministic replay for hard cases; auto-fix PRs; second language (JVM via JaCoCo + bytecode); hosted dashboard. | ongoing |

**To a launchable, measured, genuinely impressive tool: ~8–10 weeks part-time.**

---

## 5. Validation methodology (so the README number is real)

The credibility of this project rests on a measured claim, mirroring how Google
reported 82%. Protocol:

### 5.1 Build a labeled benchmark

Two sources, kept separate:

- **Synthetic set (control).** Hand-written flaky tests with *known* category and
  *known* root-cause line (the `examples/` are the seed). Lets you measure on
  ground truth you fully trust. Target: ~30 tests across all categories.
- **Real-world set (the credible one).** Mine public Python repos for *merged PRs
  that fixed a flaky test* — search commit/PR text for `flaky`, `flake`,
  `intermittent`, `nondeterministic`, `race`. The fixing diff reveals (a) the
  root-cause location and (b) the category. Reproduce the *pre-fix* test, run
  Flakehound on it, compare. Target: 40–60 tests from popular projects.

For each benchmark entry store: repo/commit, the test, ground-truth category,
ground-truth root-cause line(s).

### 5.2 Metrics

- **Category accuracy** — `% of tests where Flakehound's category == ground truth`.
- **Localization @k** — `% where a ground-truth root-cause line is within the
  top-k ranked candidates` (report top-1 and top-5).
- **Reproduction rate** — `% of known-flaky tests where Flakehound actually
  reproduced the flake within N runs` (an honest denominator; you can't localize
  what you can't reproduce).

### 5.3 Discipline

- **Hold-out.** Tune heuristics/weights only on the synthetic + a *dev split* of
  the real set; report final numbers on an untouched *test split*. No fitting on
  the eval set.
- **Per-category breakdown.** Report accuracy per flake class — timing will score
  higher than concurrency, and saying so is more credible than one blended number.
- **Honest caveats in the README.** State N, the reproduction rate, and that
  results are on this benchmark, not a universal guarantee.

### 5.4 The headline sentence (template)

> *"On a benchmark of **N** real-world Python flaky tests, Flakehound reproduced
> the flake in **R%** of cases, identified the correct root-cause category in
> **X%**, and localized the root cause within the top-5 lines in **Y%**."*

That single, defensible sentence is what turns a side project into a portfolio
centerpiece — and the same number anchors the launch post and the résumé bullet.

---

## 6. Why this lands for a portfolio

- **Real whitespace, not a clone** — does what no public tool does.
- **Deep engineering** — runtime tracing, statistical fault localization, AST
  analysis, an awareness of the observer effect baked into the architecture.
- **Demo-able in 60 seconds** — "watch it pinpoint why this test is flaky."
- **Measured** — a real accuracy number, validated against real-world bugs.
- **On-thesis for AI/ML + DevOps roles** — testing/CI tooling with a statistical
  (and optionally LLM) core.
