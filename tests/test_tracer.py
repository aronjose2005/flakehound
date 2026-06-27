"""Unit test for the line/locals tracer."""
import importlib.util

from flakehound import tracer


def _load(path):
    spec = importlib.util.spec_from_file_location("_traced_mod", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_records_executed_lines_and_primitive_locals(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text("def run():\n    a = 1\n    b = a + 1\n    return b\n")
    mod = _load(f)

    t = tracer.Tracer([str(f)], roots=[str(tmp_path)])
    with t:
        mod.run()

    lines = {ln for _file, ln in t.trace_obj.executed_lines()}
    assert {2, 3, 4} <= lines  # the assignment + return lines all ran

    snapshots = t.trace_obj.last_locals_per_line()
    # a primitive local was captured as its repr somewhere along the trace
    assert any("a" in vars_at for vars_at in snapshots.values())
