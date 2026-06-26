# Contributing to Flakehound

Thanks for taking the time to help. Flakehound has one job — tell a developer
*why* a test is flaky and *where* the non-determinism lives — and the bar for
changes is that they make that answer more accurate, faster, or clearer.

## Dev setup

```bash
git clone https://github.com/aronjose2005/flakehound.git
cd flakehound
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

The core has **zero runtime dependencies** — it's pure standard library. Please
keep it that way; anything optional (e.g. the LLM explanation layer) belongs
behind an extra in `pyproject.toml`, never in the default install.

## The one rule that bites everyone: don't trust traced timing

A flaky test is a Heisenbug, and tracing every line is ~50× slower than running
untraced. So the engine deliberately separates the two:

- **Untraced runs** produce the real pass/fail outcomes *and* the only timing
  numbers you may reason about.
- **Traced runs** produce line/variable spectra, and nothing else.

If you find yourself reading a duration off a traced run, stop — that number is
contaminated by the tracer. This separation is the whole reason the tool can
diagnose timing flakes without becoming one.

## Architecture map

| Module | Responsibility |
| --- | --- |
| `runner.py` | Drives untraced/traced execution N times; collects outcomes. |
| `tracer.py` | Line- and variable-level tracing of a single run. |
| `scope.py` | Decides which files count as "project source" worth analysing. |
| `localizer.py` | Ochiai spectrum scoring + discriminating-variable analysis → ranked candidates. |
| `classifier.py` | Maps evidence to a category, confidence, and a concrete fix. |
| `reporter.py` | Renders the human-readable verdict block. |
| `cli.py` / `__main__.py` | `flakehound file.py::test` entry point. |
| `pytest_plugin.py` | The `--flakehound "node::id"` pytest integration. |

## Adding a flaky scenario

The fastest way to harden detection is a labeled example:

1. Add a minimal reproducer under `examples/` whose flakiness has a single,
   known root cause.
2. Add a test under `tests/` that runs it through
   `runner` → `localizer` → `classifier` and asserts the expected category and
   that the true culprit line is among the top candidates.
   See `tests/test_cross_file.py` for the pattern.

## Pull requests

- Keep `pytest -q` green; CI runs it on Python 3.9–3.13.
- One logical change per PR, with a clear message.
- If you change observable behaviour or output, add a `CHANGELOG.md` entry
  under `[Unreleased]`.
- Don't assert accuracy you haven't measured — claims about detection rates
  should come with a reproducible benchmark (see `BUILD_PLAN.md`).
