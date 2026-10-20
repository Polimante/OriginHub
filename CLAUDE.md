# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## OriginHub

Desktop app (PyQt6) that reads raw UV-Vis / XRD files, previews them and builds an
Origin project by launching Origin and running a Python script inside it. The user
(Lucas, UFABC) researches perovskite thin films / solar cells. **Talk to the user in
Portuguese; all code, comments, UI text and docs must be in English.**

## Commands
- Install: `pip install -r requirements.txt` (numpy, pandas, openpyxl, xlrd, PyQt6, pyqtgraph); Python >= 3.11 (tomllib)
- Run: `OriginHub.bat` or `python app/main.py [files or folders...]`
- Dev tools: `pip install -r requirements-dev.txt`; lint `ruff check .`; tests `pytest` (config in `pyproject.toml`,
  `testpaths = tests + app/techniques`). Single test:
  `pytest app/techniques/uvvis/tests/test_analysis.py::test_reference_spectrum_is_unchanged`
- Origin end-to-end (needs Origin): `python tools/e2e_test.py ABS <folder> --ref 1000 --thickness 400 --selftest`
  (or `XRD <folder>`; any technique key). Look at the PNGs in `--out`.
- Windows build: `packaging/build.ps1 [-NoInstaller] [-InstallTest]` (PyInstaller onedir via `packaging/OriginHub.spec`
  → `dist/OriginHub/`, then Inno Setup `packaging/OriginHub.iss` → `dist/OriginHub-Setup-<ver>.exe` + `.sha256`).
  The spec bundles non-imported files at the same relative paths (HELP.md, materials/*.toml, origin_side/origin_common.py,
  techniques/*/origin_build.py) and collects technique modules as hidden imports (pkgutil discovery). The frozen exe
  has no console: `OriginHub.exe --check <report.txt>` self-tests and sets the exit code. Version: `app/version.py`.
- Release: tag `vX.Y.Z` (must equal `app/version.py`, CHANGELOG needs a `## [X.Y.Z]` section, see
  `tools/release_notes.py`) → `.github/workflows/release.yml` builds, install-tests and publishes the GitHub Release.
  Installer is per-user (`{autopf}` = %LOCALAPPDATA%\Programs\OriginHub, no UAC); never change its AppId.
- Updates (`core/updater.py`): GitHub `releases/latest` → needs `OriginHub-Setup-<v>.exe` + `.sha256` assets from
  `https://github.com/Polimante/OriginHub/releases/download/`; SHA-256 verified; installer run with `/SILENT /RELAUNCH=1`
  (Inno `[Code] ShouldRelaunch` restarts the app). `ORIGINHUB_UPDATE_API` env var = test-only override (local fake
  release in `build.ps1 -UpdateTest`); `OriginHub.exe --self-update` = non-interactive update for that test. Only the
  frozen app self-updates. Lucas installed 0.2.0 *for all users* (Program Files, HKLM): updates there show a UAC prompt.
- `build.ps1 -InstallTest` refuses to run where OriginHub is registered (HKCU/HKLM) unless `$env:CI`: installing
  would hijack the real installation's uninstall entry. Install/update tests run only in GitHub Actions.
- Setup check (`core/environment.py`, `core/dialogs.py`): first run (`QSettings` `setup/done`) and Help menu; Origin
  >= 2021, work folder, templates from `app/resources/templates/*.otpu` copied (never overwritten) to the User Files
  Folder that `origin_common.save_origin_paths()` writes to `%LOCALAPPDATA%\OriginHub\origin_paths.json`
  (`op.path('u')`, verified). `app/bootstrap.py` (stdlib + Tk) asks before pip-installing missing packages (source only).
- Tests never touch the network or the real settings: pass `settings=QSettings(<tmp ini>)` to `MainWindow`; `startup()`
  (setup + update check) is called by `main()` only.
- CI (`.github/workflows/ci.yml`): ruff + pytest on windows-latest, Python 3.11 and 3.14; "Windows app build"
  (`build.ps1 -InstallTest -UpdateTest`); a job that fails if raw data / `.opju` files are tracked. `main` is
  protected: PR + these 4 checks green (enforced for admins too). Claude may merge PRs itself once CI is green.

## Architecture (plugins)
- `app/core/`: `dataset.py` (Dataset, `validate()`, `x_signature`), `registry.py` (Technique/Reader interface,
  `discover()` imports each `app/techniques/<pkg>` in try/except → `Registry.failures`; `identify()` picks the
  reader with the highest `detect()` score, a crashing detector counts as 0; `load()` sets `kind` and validates),
  `materials.py` (TOML profiles validated against each technique's `material_schema`), `tab.py` (TechniqueTab base:
  table/preview/export + hooks; BrokenTab), `origin_bridge.py` (common payload, run folder, launch).
- `app/techniques/<name>/`: `__init__.py` (`TECHNIQUE`), `readers.py`, `tab.py` (Qt imported lazily in `make_tab`),
  `origin_build.py` (defines `build(cfg)`, optional `selftest(cfg)`), `tests/` (`synthetic.py` writers,
  `fixtures.py` registered in root `conftest.py` via `pytest_plugins`). UV-Vis = key `ABS` (`analysis.py`,
  `payload.py`); XRD = key `XRD` (smallest, the template for new techniques). Techniques never import each other.
- `app/materials/*.toml`: Generic (first), FAPbI3 (baseline 1000 nm), MAPbI3, CsPbBr3. The main window's
  Material box calls `tab.apply_material(values)`; UV-Vis resets only automatic Tauc ranges (`tauc_range_auto`).
- `app/main.py` only hosts tabs, routes files, launches Origin; a technique that fails to import or to build its
  tab gets a "⚠" error tab and the others keep working.

## Tests (no Origin needed)
- Synthetic files with known Eg/E_U in the real formats (JASCO `.txt`, Agilent `.SD`, PowDLL `.xlsx`); never add
  real lab data to the repo.
- `test_reference_spectrum_is_unchanged` locks the fit-window output: update it only for a deliberate,
  explained scientific change. Each technique's payload test is the contract with its `origin_build.py`.
  `tests/test_origin_side.py` checks every Origin-side script: Python 3.11 syntax, stdlib + `originpro` +
  `origin_common` imports only, no relative imports, imported helper names exist in `origin_common.py`.
- GUI tests run offscreen (`QT_QPA_PLATFORM=offscreen`, set in root `conftest.py`).

## Layout
- `tools/e2e_test.py` real end-to-end test; `HELP.md` user guide + references; `README.md`; `CONTRIBUTING.md`
  (how to add a material / a technique)
- Parent folder `Scripts Origin/` (not in the repo) holds legacy LabTalk scripts (`*.ogs`, Portuguese)
  and the user's example data in `exemplos/` (never commit data).

## How Origin is driven (verified facts - do not re-derive)
- Origin 2025b: `C:\Program Files\OriginLab\Origin2025b\Origin64.exe`. COM (`Origin.Application`) points
  to the old Origin 2018 → **do not use COM**. Launch: `"Origin64.exe" -rs run -pyf "<script>"` as ONE
  command string (passing a list double-escapes the quotes).
- Each export writes a run folder `%LOCALAPPDATA%\OriginHub\run_<KEY>_<stamp>\` (ASCII path; Origin's command
  line breaks on accents) with `payload.json`, `origin_common.py`, the technique's script as `origin_build.py` and
  `launch.py` (`PAYLOAD = r"..."`, `sys.path.insert`, pops cached modules, `origin_common.run(PAYLOAD)`).
  Importing modules from that folder inside Origin works (verified e2e, Origin 2025b). Log: `payload.json.log`, ends with `OK`.
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
