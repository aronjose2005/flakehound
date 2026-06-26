# Changelog

All notable changes to Flakehound are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Continuous integration via GitHub Actions, running the test suite on
  Python 3.9 through 3.13.
- Regression test for the headline capability — locating the root cause of a
  flaky test when the non-determinism lives in *imported application code*
  rather than the test file.
- Metadata guard tests that keep `__version__` in sync with `pyproject.toml`
  and pin the classifier category names the output format depends on.
- `CONTRIBUTING.md` with dev setup, the architecture map, and the
  observer-effect rule every contributor needs to know.
- A structured bug-report issue template tailored to flaky-test reports.

### Fixed
- Corrected the GitHub project URLs in package metadata (they pointed at a
  non-existent `aronjose/` namespace instead of `aronjose2005/`).

## [0.1.0] - 2026-06-22

### Added
- Two-phase execution engine: untraced runs for clean outcomes and honest
  wall-clock timing, traced runs for line/variable spectra — so a flaky-test
  tool never becomes a Heisenbug itself.
- Spectrum-based (Ochiai) fault localization plus discriminating-variable
  analysis to rank suspicious lines.
- Static non-determinism scan across every source file the test touches,
  catching `time.sleep`, `random.*`, unordered `set` iteration, threads, and
  clock reads — including in application code the test imports.
- Classifier mapping evidence to a category (timing/async, randomness,
  order-dependency, concurrency) with a confidence band and a concrete fix.
- Both a CLI (`flakehound file.py::test`) and a pytest plugin
  (`pytest --flakehound "node::id"`).
- Bundled, deliberately-flaky demo files under `examples/`.

[Unreleased]: https://github.com/aronjose2005/flakehound/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aronjose2005/flakehound/releases/tag/v0.1.0
