"""Shared pytest setup. Each technique provides its fixtures in techniques/<name>/tests/fixtures.py."""
import os

# GUI tests must not open a window (CI machines have no display)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest_plugins = [
    "techniques.uvvis.tests.fixtures",
    "techniques.xrd.tests.fixtures",
]
