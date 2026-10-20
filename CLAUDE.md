# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## OriginHub

Desktop app (PyQt6) that reads raw UV-Vis / XRD files, previews them and builds an
Origin project by launching Origin and running a Python script inside it. The user
(Lucas, UFABC) researches perovskite thin films / solar cells. **Talk to the user in
Portuguese; all code, comments, UI text and docs must be in English.**

## Commands
- Install: `pip install -r requirements.txt` (numpy, pandas, openpyxl, xlrd, PyQt6, pyqtgraph)
- Run: `OriginHub.bat` or `python app/main.py [files or folders...]`
- Syntax check (especially `app/origin_side/build.py` before it runs in Origin): `python -m py_compile <file>`
- Dev tools: `pip install -r requirements-dev.txt`; lint `ruff check .`; tests `pytest`
  (single test: `pytest tests/test_analysis.py::test_reference_spectrum_is_unchanged`). Config in `pyproject.toml`.
- CI (`.github/workflows/ci.yml`): ruff + pytest on windows-latest, Python 3.10 and 3.14, plus a job that fails
  if raw data / `.opju` files are tracked. `main` is meant to be changed only through reviewed PRs.

## Tests (no Origin needed)
- `tests/synthetic.py` generates spectra with known Eg/E_U and writes them as JASCO `.txt`, Agilent `.SD`
  and PowDLL `.xlsx`; never add real lab data to the repo.
- `test_reference_spectrum_is_unchanged` locks the fit-window output: update it only for a deliberate,
  explained scientific change. `test_origin_bridge.py` is the payload contract with `build.py` - add any new
  key `build.py` reads. `test_origin_side.py` enforces stdlib + `originpro` imports and Python 3.11 syntax.
- `parsers.load()` runs `parsers.validate()` on every Dataset (finite strictly ascending x, matching lengths);
  the GUI lists failing files as "Skipped" with the reason.

## Layout
- `app/main.py` GUI (tabs per technique, editable table, pyqtgraph preview, Help dialog → `HELP.md`)
- `app/parsers.py` `detect()` by content + readers: JASCO V-780 `.txt`, Agilent 8453/8454 `.SD`
  (reverse-engineered binary, several spectra per file), PowDLL `.xls` (XRD)
- `app/analysis.py` baseline, %T, α, Tauc/Urbach columns, **fit-window selection** (preview fits use numpy)
- `app/origin_bridge.py` finds newest Origin, groups samples by X grid, writes JSON payload, launches Origin
- `app/origin_side/build.py` runs **inside Origin** (embedded Python 3.11, **no numpy** - stdlib + `originpro` only)
- `tools/e2e_test.py` real end-to-end test; `HELP.md` user guide + references; `README.md`
- Parent folder `Scripts Origin/` (not in the repo) holds legacy LabTalk scripts (`*.ogs`, Portuguese)
  and the user's example data in `exemplos/` (never commit data).

## How Origin is driven (verified facts - do not re-derive)
- Origin 2025b: `C:\Program Files\OriginLab\Origin2025b\Origin64.exe`. COM (`Origin.Application`) points
  to the old Origin 2018 → **do not use COM**. Launch: `"Origin64.exe" -rs run -pyf "<script>"` as ONE
  command string (passing a list double-escapes the quotes).
- Payload + script copy go to `%LOCALAPPDATA%\OriginHub\` (ASCII path; Origin's command line breaks on accents).
  The script copy starts with `PAYLOAD = r"..."`; `build.py` logs to `<payload>.log` and ends with `OK`.
- XRD stacked graph: `plotxy iy:=[Book]Sheet!(1,2:end) plot:=200 ogl:=[<new template:=OffsetStackY>]`
  (brackets = new page; without them plots land in the previous graph).
- Native Linear Fit (what the user wants): `xop execute:=init classname:=FitLinear iotrgui:=tree`, set
  `GUI.AutoUpdate=1`, `GUI.Quantities.XIntercept=1` (Eg + error computed by Origin),
  `GUI.Graph1.XDataType.Range=1` (line spans the axis; Range=2 custom min/max is LOST on recalculation),
  input `[Book]Sheet!col[r1:r2]`, then `@NLFS=0; xop execute:=report`. `__REPORT$`/`__FITCURVE$` give
  the sheets. `Output.Report.SheetName` is ignored → rename the sheets afterwards (renaming is safe).
  Read results with `getresults tr:=t iw:=[Book]Sheet!` + `originpro.utils.lt_tree_to_dict`.
- Live labels: `gl.add_label(text)` + `label.set_int("link", 1)` with `$(ReportCell("Book","Sheet","Parameters","XIntercept","Value"),.4)`
  works and updates on recalculation. `label -s` + text via LabTalk does NOT.
- Worksheet cells linked to reports (`=ReportCell(...)` → `cell://...`) show the link text, not the value,
  when set by script → "Tauc Results" sheet is static (initial fit). Unsolved.
- `fitlr iy:=[Book]Sheet!(x,y)[r1:r2]` (results in `fitlr.a/b/aerr/berr/r`) is used only for quick values.
- Template `PadraoLinha` (user's style) lives in Origin's User Files Folder; `new_graph` falls back to `line`.

## Testing workflow
- `python tools/e2e_test.py ABS <folder> --ref 1000 --thickness 400 --selftest` (or `XRD <folder>`), then look
  at the exported PNGs. Example data: `../exemplos/abs` (JASCO), `../exemplos/abs/agilent` (.SD), `../exemplos/xrd`.
- GUI smoke test without a window: `QT_QPA_PLATFORM=offscreen` and `widget.grab().save(...)` (text renders as boxes).
- The user may have Origin open: **only kill the PID you started**, never "all Origin64 started recently".
- Write probe scripts with the file tool and `python -m py_compile` them before running in Origin
  (a syntax error pops up a dialog on the user's screen). Avoid `python -c` from PowerShell with quotes/accents.

## Scientific decisions (agreed with the user)
- Baseline: subtract A at λ_ref (±2 nm mean), default 850 nm; Agilent goes to 1100 nm → 1000 nm is better
  for FAPbI₃ (850 nm is inside its Urbach tail). %T from RAW absorbance.
- Tauc: default direct allowed (n = 1/2); α = 2.303A/d, thickness optional (Eg independent); exclude raw A > 3;
  auto range = ±45 nm around the longest-λ edge above 300 nm (skips residual PbI₂ and glass/deep-UV noise);
  window grows from max −dA/dλ while R² ≥ 0.99; Eg window uncertainty = half spread for ±25 % window changes.
- Urbach: fit on the steep edge shoulder (user corrected an earlier version that fitted the slow sub-gap rise):
  max d(lnα)/dE in [Eg−0.15, Eg+0.03] eV, extend while slope ≥ 70 % of max, corrected A ≥ 0.05; E_U > 100 meV
  flagged unreliable. UV-Vis E_U depends on baseline λ (~±5 meV) - compare samples with the same baseline.
- Graph style: Paul Tol "muted" palette; data lines 2 pt; XRD frame 3 pt all sides, ticks only on 2θ,
  intensity axis title only; XRD axis "Diffraction Angle (2θ)"; one Origin project per technique.

## Roadmap / open items
- J-V module (legacy `../jv.ogs` + `../LEIAME.md` describe the desired outputs: champion J-V, per-group J-V, boxplots).
- XRD: phase markers (PbI₂ 12.7°, α-FAPbI₃ ~13.9°, δ-FAPbI₃ ~11.8°, substrate), PbI₂/perovskite ratio, Scherrer.
- Live "Tauc Results" summary.
