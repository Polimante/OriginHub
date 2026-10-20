"""Prints the CHANGELOG.md section of a version (used as the GitHub release notes).

    python tools/release_notes.py 0.2.0 > notes.md
Exits with an error if the version has no section, so a release cannot go out undocumented.
"""
import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(version: str, text: str) -> str:
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## \[|\Z)", text, re.M | re.S)
    if not m or not m.group(1).strip():
        raise SystemExit(f"CHANGELOG.md has no section for version {version}")
    return m.group(1).strip() + "\n"


if __name__ == "__main__":
    sys.stdout.write(section(sys.argv[1].lstrip("v"), CHANGELOG.read_text(encoding="utf-8")))
