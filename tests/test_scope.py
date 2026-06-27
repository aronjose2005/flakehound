"""Unit tests for scope.is_user_file — which files get traced."""
import os

from flakehound import scope


def test_explicit_target_is_in_scope(tmp_path):
    f = tmp_path / "t.py"
    f.write_text("x = 1\n")
    ex = scope.default_excludes()
    assert scope.is_user_file(str(f), {os.path.abspath(str(f))}, [], ex)


def test_file_under_root_is_in_scope(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    f = pkg / "m.py"
    f.write_text("x = 1\n")
    ex = scope.default_excludes()
    assert scope.is_user_file(str(f), set(), [str(tmp_path)], ex)


def test_stdlib_is_excluded():
    ex = scope.default_excludes()
    # os.py lives in the standard library, which default_excludes() covers
    assert not scope.is_user_file(os.__file__, set(), [os.getcwd()], ex)


def test_site_packages_is_excluded():
    ex = scope.default_excludes()
    fake = os.path.join(os.sep, "venv", "lib", "site-packages", "requests", "__init__.py")
    assert not scope.is_user_file(fake, set(), [os.path.join(os.sep, "venv")], ex)


def test_pycache_is_excluded():
    ex = scope.default_excludes()
    fake = os.path.join(os.sep, "proj", "__pycache__", "m.cpython-311.pyc")
    assert not scope.is_user_file(fake, set(), [os.path.join(os.sep, "proj")], ex)
