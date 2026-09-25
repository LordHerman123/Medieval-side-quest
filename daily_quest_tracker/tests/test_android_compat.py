"""Guards that keep the project packageable with Buildozer / python-for-android.

These don't build an APK; they catch the usual ways a Kivy app stops packaging:
an unpackaged file type, a desktop-only dependency, a missing recipe, or code
that depends on the current working directory.
"""

import ast
import configparser
import os
import sys

import pytest

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(PACKAGE_DIR)
SPEC_FILE = os.path.join(REPO_DIR, "buildozer.spec")

# Third-party modules we allow in app code. Kivy ships as a p4a recipe; certifi is optional.
ALLOWED_THIRD_PARTY = {"kivy", "certifi"}
LOCAL_PACKAGES = {"core", "database", "services", "ui", "main"}


def spec() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(SPEC_FILE)
    return parser


def app_files():
    for root, dirs, files in os.walk(PACKAGE_DIR):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__", ".pytest_cache")]
        for name in files:
            yield os.path.join(root, name)


def imported_modules(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.module.split(".")[0]


def test_spec_points_at_the_app():
    app = spec()["app"]
    source_dir = os.path.join(REPO_DIR, app["source.dir"])
    assert os.path.samefile(source_dir, PACKAGE_DIR)
    assert os.path.exists(os.path.join(source_dir, "main.py"))


def test_every_app_file_type_is_packaged():
    included = {e.strip() for e in spec()["app"]["source.include_exts"].split(",")}
    ignored = {"pyc", "db"}
    for path in app_files():
        ext = os.path.splitext(path)[1].lstrip(".").lower()
        if ext and ext not in ignored:
            assert ext in included, f"{os.path.relpath(path, REPO_DIR)} would be left out of the APK"


def test_spec_has_required_recipes_and_assets():
    app = spec()["app"]
    requirements = {r.strip().split("==")[0] for r in app["requirements"].split(",")}
    assert {"python3", "kivy", "sqlite3", "openssl"} <= requirements
    assert "INTERNET" in app["android.permissions"]
    for key in ("icon.filename", "presplash.filename"):
        path = app[key].replace("%(source.dir)s", os.path.join(REPO_DIR, app["source.dir"]))
        assert os.path.exists(path), key


@pytest.mark.skipif(not hasattr(sys, "stdlib_module_names"), reason="needs Python 3.10+")
def test_only_android_friendly_dependencies():
    for path in app_files():
        if not path.endswith(".py"):
            continue
        for module in imported_modules(path):
            if module in sys.stdlib_module_names or module in LOCAL_PACKAGES or module == "__future__":
                continue
            assert module in ALLOWED_THIRD_PARTY, f"{os.path.relpath(path, REPO_DIR)} imports {module!r}"


def test_core_logic_has_no_kivy_dependency():
    for folder in ("core", "database", "services"):
        for name in os.listdir(os.path.join(PACKAGE_DIR, folder)):
            if name.endswith(".py"):
                path = os.path.join(PACKAGE_DIR, folder, name)
                assert "kivy" not in set(imported_modules(path)), path


def test_data_loads_regardless_of_working_directory(tmp_path, monkeypatch):
    from core.progression import Progression
    from core.quest_engine import QuestLibrary

    monkeypatch.chdir(tmp_path)
    assert len(QuestLibrary.load()) >= 800
    assert Progression.load().items


def test_bundled_data_stays_small():
    total = sum(os.path.getsize(p) for p in app_files() if p.endswith((".json", ".png", ".ttf")))
    assert total < 5 * 1024 * 1024
