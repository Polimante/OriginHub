# Contributing to OriginHub

Thanks for helping! OriginHub is used to analyze real research data, so the rule is simple:
**a change must never silently alter a scientific result or break an existing technique.**
Every contribution goes through automated checks and a review before it is merged.

## Ways to contribute

- **Report a bug** or a file that is not recognized: open an issue with the *Bug report* form.
  If you can share an example file, say so in the issue, but do not attach unpublished data
  you are not allowed to share.
- **Propose a material, technique or instrument format**: use the matching issue form, ideally
  with a literature reference for the method.
- **Send code**: fork the repository, create a branch, and open a pull request (PR).

## How a pull request is accepted

1. **Automated checks (CI)** run on every PR, on Windows with the oldest and newest supported
   Python. All must pass:
   - `ruff` (lint): undefined names, unused imports, likely bugs;
   - `pytest`: the core (plugin isolation, data validation, material profiles, Origin run
     folder, static checks of the Origin-side scripts, GUI smoke test) and every technique's
     own tests (readers, scientific results on synthetic data, payload contract);
   - no measurement data or Origin projects in the repository.
2. **Review** by a code owner (see [.github/CODEOWNERS](.github/CODEOWNERS)). Nobody pushes
   directly to `main`, maintainers included.
3. **Origin end-to-end test** before each release, on a machine with Origin (CI has no Origin
   license): `python tools/e2e_test.py ABS <folder> --ref 1000 --selftest` and
   `python tools/e2e_test.py XRD <folder>`.

## Development setup

```bat
git clone https://github.com/<your-user>/OriginHub.git
cd OriginHub
pip install -r requirements.txt -r requirements-dev.txt
python app/main.py
```

Before opening the PR, run what CI runs:

```bat
ruff check .
pytest
```

Run a single file or test with `pytest app/techniques/uvvis/tests/test_analysis.py` or
`pytest app/techniques/uvvis/tests/test_analysis.py::test_reference_spectrum_is_unchanged`.

## Adding a material

No programming needed. Copy `app/materials/generic.toml` to a new file, change the
name, description and values, and add references (DOI links) for the choices. Keys you
leave out use the technique defaults. Run `pytest tests/test_materials.py`: it rejects
unknown keys, wrong types and out-of-range values, so typos cannot reach users.

## Adding a technique

Each technique is an independent plugin in `app/techniques/<name>/`. The app discovers
it automatically; if it fails to load, it shows an error tab and the rest of the app keeps
working. Start by copying `app/techniques/xrd/` (the smallest one). A plugin has:

| File | Role |
|---|---|
| `__init__.py` | `TECHNIQUE = MyTechnique()`, a `core.registry.Technique` subclass: `key` (e.g. `"PL"`), `title`, `readers`, `origin_script`, `make_tab()`, `build_payload()` and, optionally, `material_section`/`material_schema`/`material_defaults` |
| `readers.py` | one `detect(path) -> 0..1` (from the file **content**) and one `read(path) -> list[Dataset]` per instrument format |
| `tab.py` | a `core.tab.TechniqueTab` subclass: options, extra columns, preview plot |
| `origin_build.py` | runs **inside Origin**: defines `build(cfg)`; may import helpers from `origin_common`; standard library + `originpro` only |
| `tests/` | `synthetic.py` (writes files in the instrument format), `fixtures.py` (register it in the root `conftest.py`), and tests |

The core tests check every plugin automatically (interface, Origin-side imports, run
folder). Test the Origin part with `python tools/e2e_test.py <KEY> <data folder>` and
attach a screenshot of the graphs to the PR. Add the folder to `.github/CODEOWNERS` with
its maintainer.

## Rules that keep the project safe

- **Language**: code, comments, UI text and docs are in English.
- **Techniques stay independent.** A technique never imports another technique; shared code
  goes to `app/core/` (or `app/origin_side/origin_common.py` for Origin-side helpers), and
  changes there must keep every technique's tests passing.
- **No lab data in the repository.** Tests generate synthetic files in the real instrument
  formats (`app/techniques/*/tests/synthetic.py`). A new reader comes with a generator for its
  format and tests for it.
- **Every reader returns data that passes `parsers.validate()`**: finite, strictly ascending X;
  Y with the same length; no infinite values.
- **Scientific changes are explicit.** `app/techniques/uvvis/tests/test_analysis.py::test_reference_spectrum_is_unchanged`
  locks the output for a reference spectrum. If your change moves it, explain why in the PR
  (with a reference when possible) and update the numbers in the same PR.
- **Code that runs inside Origin** (`app/origin_side/`, `app/techniques/*/origin_build.py`) uses
  Origin's embedded Python 3.11: standard library and `originpro` only (no numpy/pandas).
  A test enforces this.
- **The payload is a contract.** If you add a key that a technique's `origin_build.py` reads,
  add it to that technique's payload test (e.g. `app/techniques/uvvis/tests/test_payload.py`).
- Keep pull requests small and focused on one thing; add an entry under *Unreleased* in
  [CHANGELOG.md](CHANGELOG.md).

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to it.
