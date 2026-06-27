"""
Flakehound pytest plugin.

    pytest --flakehound "tests/test_api.py::test_login"

Finds the target test, lets pytest set up its fixtures normally, then runs the
test body many times and prints a root-cause report from Flakehound's engine.
"""

import pytest


def pytest_addoption(parser):
    group = parser.getgroup("flakehound", "Flakehound — flaky-test root-cause analysis")
    group.addoption("--flakehound", action="store", default=None, metavar="NODEID",
                    help="Analyse the given test node id for flakiness.")
    group.addoption("--flakehound-runs", action="store", type=int, default=30, metavar="N",
                    help="How many times to run the target test (default: 30).")
    group.addoption("--flakehound-json", action="store_true", default=False,
                    help="Emit the Flakehound report as JSON instead of the terminal view.")


def _matches(item, target):
    return item.nodeid == target or item.nodeid.endswith(target)


def pytest_collection_modifyitems(config, items):
    """Keep only the targeted test; deselect everything else."""
    target = config.getoption("flakehound")
    if not target:
        return
    selected = [it for it in items if _matches(it, target)]
    if not selected:
        raise pytest.UsageError(f"--flakehound: no test matching '{target}'")
    deselected = [it for it in items if it not in selected]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected


@pytest.hookimpl(tryfirst=True)
def pytest_pyfunc_call(pyfuncitem):
    """pytest calls this to execute the test body — fixtures are already resolved.
    For our target we take over and run Flakehound instead of the single call."""
    target = pyfuncitem.config.getoption("flakehound")
    if not target or not _matches(pyfuncitem, target):
        return None        # let pytest run the test normally
    _analyze(pyfuncitem)
    return True            # we executed the call; pytest won't run it again


def _analyze(item):
    from . import runner, localizer, classifier, reporter

    runs = item.config.getoption("flakehound_runs")
    target_files = [str(getattr(item, "path", item.fspath))]
    # Trace the whole project (pytest's rootdir), so root causes in application
    # code the test imports are caught too — not just bugs in the test file.
    rootpath = getattr(item.config, "rootpath", None) or item.config.rootdir
    roots = [str(rootpath)]

    # Fixtures are already set up by pytest -> item.funcargs is populated.
    argnames = item._fixtureinfo.argnames

    def call():
        item.obj(**{name: item.funcargs[name] for name in argnames})

    untraced = runner.run_untraced(call, target_files, n=runs, roots=roots)
    traced = runner.run_traced(call, target_files, n=max(20, runs), roots=roots)
    signals = localizer.localize(untraced, traced, target_files)
    verdict = classifier.classify(signals)
    if item.config.getoption("flakehound_json"):
        report = reporter.render_json(item.nodeid, signals, verdict)
    else:
        report = reporter.render(item.nodeid, signals, verdict)

    # pytest captures stdout by default — suspend capture so the report prints.
    capman = item.config.pluginmanager.getplugin("capturemanager")
    if capman:
        with capman.global_and_fixture_disabled():
            print(report)
    else:
        print(report)
