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
   - `pytest`: readers, data validation, scientific results on synthetic spectra, the
     app → Origin payload contract, static checks of the Origin-side script, a GUI smoke test;
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

Run a single file or test with `pytest tests/test_analysis.py` or
`pytest tests/test_analysis.py::test_reference_spectrum_is_unchanged`.

## Rules that keep the project safe

- **Language**: code, comments, UI text and docs are in English.
- **No lab data in the repository.** Tests generate synthetic files in the real instrument
  formats ([tests/synthetic.py](tests/synthetic.py)). A new reader comes with a generator for its
  format and tests for it.
- **Every reader returns data that passes `parsers.validate()`**: finite, strictly ascending X;
  Y with the same length; no infinite values.
- **Scientific changes are explicit.** `tests/test_analysis.py::test_reference_spectrum_is_unchanged`
  locks the output for a reference spectrum. If your change moves it, explain why in the PR
  (with a reference when possible) and update the numbers in the same PR.
- **Code in `app/origin_side/` runs inside Origin's embedded Python 3.11**: standard library and
  `originpro` only (no numpy/pandas). A test enforces this.
- **The payload is a contract.** If you add a key that `build.py` reads, add it to
  `tests/test_origin_bridge.py`.
- Keep pull requests small and focused on one thing; add an entry under *Unreleased* in
  [CHANGELOG.md](CHANGELOG.md).

## Code of conduct

This project follows the [Code of Conduct](CODE_OF_CONDUCT.md). By participating you agree to it.
