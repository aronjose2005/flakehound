"""
Flakehound CLI.

Usage:
    flakehound path/to/test_file.py::test_function [-n RUNS]

Targets a plain callable in a file. For pytest-collected tests (fixtures,
parametrize, classes), use the pytest plugin instead:

    pytest --flakehound "tests/test_api.py::test_login"
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys

from . import runner, localizer, classifier, reporter, __version__


def _load_callable(target: str):
    if "::" not in target:
        sys.exit("error: target must be 'file.py::function_name'")
    path, func = target.split("::", 1)
    path = os.path.abspath(path)
    if not os.path.exists(path):
        sys.exit(f"error: no such file: {path}")
    spec = importlib.util.spec_from_file_location("_fh_target", path)
    mod = importlib.util.module_from_spec(spec)
    # let the target import its own siblings
    sys.path.insert(0, os.path.dirname(path))
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    if not hasattr(mod, func):
        sys.exit(f"error: {path} has no attribute '{func}'")
    fn = getattr(mod, func)
    if not callable(fn):
        sys.exit(f"error: '{func}' is not callable")
    return fn, path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="flakehound",
        description="Find out WHY a test is flaky — not just that it is.",
    )
    p.add_argument("target", help="file.py::test_function")
    p.add_argument("-n", "--runs", type=int, default=30,
                   help="max untraced runs (default 30)")
    p.add_argument("--also", nargs="*", default=[],
                   help="extra source files to trace (the code under test)")
    p.add_argument("--json", action="store_true",
                   help="emit machine-readable JSON instead of the terminal report")
    p.add_argument("--no-color", action="store_true",
                   help="disable ANSI colour (also honoured via the NO_COLOR env var)")
    p.add_argument("--top", type=int, default=5, metavar="N",
                   help="how many ranked candidates to show (default 5)")
    p.add_argument("--exit-zero", action="store_true",
                   help="always exit 0; by default a reproduced flake exits 1 (for CI gating)")
    p.add_argument("--version", action="version", version=f"flakehound {__version__}")
    args = p.parse_args(argv)

    if args.no_color:
        reporter.use_color(False)

    fn, path = _load_callable(args.target)
    target_files = [path] + [os.path.abspath(f) for f in args.also]
    roots = [os.getcwd()]   # trace the user's project source, not just the test file

    untraced = runner.run_untraced(fn, target_files, n=args.runs, roots=roots)
    traced = runner.run_traced(fn, target_files, n=max(20, args.runs), roots=roots)
    signals = localizer.localize(untraced, traced, target_files)
    verdict = classifier.classify(signals)

    if args.json:
        print(reporter.render_json(args.target, signals, verdict))
    else:
        print(reporter.render(args.target, signals, verdict, top=args.top))

    # A reproduced flake (both outcomes seen) exits non-zero so CI can gate on it.
    flaky = signals.passes > 0 and signals.fails > 0
    if flaky and not args.exit_zero:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
