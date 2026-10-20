## What does this change?

<!-- One or two sentences. Link the issue if there is one: "Closes #12". -->

## Type

- [ ] Bug fix
- [ ] New instrument format / reader
- [ ] New material defaults
- [ ] New analysis or technique
- [ ] Documentation / other

## Checklist

- [ ] `ruff check .` and `pytest` pass locally
- [ ] Tests added or updated for the change (synthetic files only, no lab data)
- [ ] If a scientific result changes: explained below, with a reference, and the locked values in
      `tests/test_analysis.py` updated
- [ ] If `app/origin_side/` changed: tested in Origin with `tools/e2e_test.py` (say which version)
- [ ] Entry added under *Unreleased* in `CHANGELOG.md`

## Scientific justification / how it was tested

<!-- Method, references, Origin version, screenshots of the generated graphs if relevant. -->
