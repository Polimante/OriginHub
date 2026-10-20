# OriginHub

A desktop app that turns raw **UV-Vis** and **XRD** instrument files into finished
**Origin** projects - worksheets, styled graphs, and Origin-native fits - with one click.
Built for perovskite thin-film and solar-cell research.

```
raw files ──► OriginHub (recognize · clean · preview · analyze) ──► Origin 2025 project (.opju)
```

## What it does

| | UV-Vis (absorbance) | XRD |
|---|---|---|
| **Input** | JASCO V-780 `.txt`; Agilent 8453/8454 ChemStation `.SD` (multi-spectrum binary) | PowDLL `.xls`/`.xlsx` |
| **Processing** | Material profiles set the defaults; baseline subtraction at a chosen wavelength, transmittance, Tauc band gap, Urbach energy | Min-max normalization |
| **Origin output** | `Raw`, `Baseline`, `Transmittance` sheets + one graph each; per-sample Tauc and Urbach graphs with Origin **Linear Fit** reports (auto-recalculating); results summary | `Raw` and `normalized` sheets, each plotted as *Stacked Lines by Y Offsets* |

Highlights

* **Content-based file recognition** - drop files or whole folders; the type comes
  from the file content, not the name.
* **Mixed wavelength grids** - spectra with a different range or step get their own
  X column (X1, X2, …) in the same worksheet.
* **Live preview** of every view (raw, baseline, %T, Tauc, Urbach) with the fit lines
  and the band gap / Urbach energy of each sample before exporting.
* **Fits done by Origin, not hidden in the app** - Tauc and Urbach use Origin's own
  *Linear Fit* operation, with the full report (parameters, X-intercept = Eg with
  error, R², ANOVA, residuals), the fit line on the graph, and **auto recalculation**:
  change the range via the green lock → *Change Parameters* and everything updates,
  including the Eg / E_U labels on the graphs.
* **Automatic, documented fit windows** - perovskite edge selection that ignores
  residual PbI₂ and saturated/deep-UV regions; Urbach fit on the steep edge
  shoulder; window-choice uncertainty for Eg.
* **Newest Origin is launched automatically** (scans `Program Files\OriginLab`).
* One Origin project per measurement type; built-in **Help** with methods and references.

## Requirements

* Windows with **Origin/OriginPro 2021 or newer** (developed and tested with
  OriginPro **2025b**) and a valid license.
* Python ≥ 3.11 with the packages in `requirements.txt`.
* Optional: an Origin graph template called **`PadraoLinha`** in Origin's *User Files
  Folder* - it defines the line-graph style. Without it Origin's default `line`
  template is used.

## Install

**Windows installer (recommended, no Python needed):** download
`OriginHub-Setup-<version>.exe` from the
[latest release](https://github.com/Polimante/OriginHub/releases/latest) and run it. It installs
for your user only (no administrator rights) and adds OriginHub to the Start menu.

> Windows may show *"Windows protected your PC"* because the installer is not code-signed
> yet. Click **More info → Run anyway**. You can check that the file is genuine by comparing
> its SHA-256 (PowerShell: `Get-FileHash OriginHub-Setup-<version>.exe`) with the `.sha256`
> file published next to it.

**From source (developers):**

```bat
git clone https://github.com/Polimante/OriginHub.git
cd OriginHub
pip install -r requirements.txt
OriginHub.bat
```

(or `python app/main.py [files or folders…]`)

Usage in four steps: **load files → check the table and options → look at the
preview → Export to Origin**. The full guide is in [`HELP.md`](HELP.md) and inside
the app (**Help** button).

## How it works

```
app/
├── main.py                 window: hosts the technique tabs, material selector, export
├── core/                   technique-independent parts
│   ├── dataset.py          Dataset + validate() (the contract every reader must meet)
│   ├── registry.py         Technique/Reader interface, plugin discovery and isolation
│   ├── materials.py        material profiles (app/materials/*.toml)
│   ├── tab.py              base tab: sample table, preview plot, export button
│   └── origin_bridge.py    finds Origin, common payload, run folder, launches Origin
├── origin_side/
│   └── origin_common.py    runs INSIDE Origin: shared helpers + run() entry point
├── techniques/             one independent plugin per technique
│   ├── uvvis/              readers, analysis, payload, tab, origin_build.py, tests/
│   └── xrd/                the smallest plugin: start here for a new technique
└── materials/              generic.toml, fapbi3.toml, mapbi3.toml, cspbbr3.toml
tests/                      tests of the core (each technique has its own tests/)
tools/
└── e2e_test.py             end-to-end test against a real Origin installation
HELP.md                     user guide + references (shown by the Help button)
```

1. Each file is offered to every technique's readers; the one that recognizes the
   content with the highest confidence reads it, and the result is validated.
2. On export, the technique processes the data in regular Python (numpy/pandas) and
   adds its keys to a JSON payload. The app writes a run folder in
   `%LOCALAPPDATA%\OriginHub\` (an ASCII-only path - Origin's command line does not
   like accented paths) with the payload, `origin_common.py`, **only this technique's**
   `origin_build.py`, and a small `launch.py`.
3. It starts the newest Origin with `Origin64.exe -rs run -pyf <run folder>\launch.py`.
   No COM registration is needed, so it works even when COM still points to an
   older Origin.
4. The scripts run in Origin's embedded Python (3.11, **no numpy**), using only the
   standard library and `originpro`/LabTalk. They write `payload.json.log`; the app
   watches it and reports *Done* or the error.

A technique that fails to load (a bug, a missing dependency) shows an error tab;
the other techniques keep working.

### Agilent `.SD` format

ChemStation UV-Vis `.SD` files are MFC-serialized binaries with no public
specification. The reader was reverse-engineered: each spectrum starts at a
`CHPUVObject` record; metadata are UTF-16 key/value pairs (`SampleName`,
`TimeOfDay`, `Date`, `InstrId`); the `Absorbance (AU)` block holds `uint32 n`, one
flag byte and `n` float64 values; the `Wavelength (nm)` block stores start and step
(e.g. 190 nm, 1 nm → 190-1100 nm).

## Scientific methods (summary)

* **Baseline:** A − A(λ_ref), mean within ±2 nm of λ_ref (default 850 nm; use a
  sub-gap wavelength, ideally ≥ 900-1000 nm for FAPbI₃).
* **Transmittance:** %T = 100·10^(−A) from the raw absorbance.
* **Tauc:** α = 2.303·A/d, E = 1239.84/λ, (αhν)^(1/n) vs E (n = 1/2 direct allowed by
  default). The fit window starts at the edge center (max −dA/dλ) inside the Tauc
  range and grows while R² ≥ 0.99; points with raw A > A_max (default 3) are excluded.
  Eg = X-intercept (Origin). The *window uncertainty* is half the spread of Eg when the
  window is shifted/shortened by 25 %. Thickness is optional (it does not change Eg).
* **Urbach:** E_U = 1 / slope of ln α vs E on the steep edge shoulder: start at the
  maximum of d(ln α)/dE within [Eg − 0.15, Eg + 0.03] eV and extend while the local
  slope is ≥ 70 % of the maximum (corrected A ≥ 0.05). E_U > 100 meV is flagged
  unreliable.
* **XRD normalization:** (I − I_min)/(I_max − I_min).

Caveats: transmission-based E_U depends on the baseline wavelength and is usually
higher than PDS/FTPS values; compare samples processed the same way. See
[`HELP.md`](HELP.md) for details and the full reference list (Tauc 1966; Urbach 1953;
De Wolf *et al.* 2014; Ledinský *et al.* 2019; Makuła *et al.* 2018; Zanatta 2019; …).

## Testing

Automated tests need no Origin and run on every pull request (GitHub Actions):

```bat
pip install -r requirements-dev.txt
ruff check .
pytest
```

They use synthetic files in the real instrument formats, with a known band gap and Urbach
energy ([`tests/synthetic.py`](tests/synthetic.py)); no lab data is stored in the repository.

`tools/e2e_test.py` builds a real Origin project from a folder of data files,
exports all graphs as PNG and closes only the Origin instance it opened:

```bat
python tools/e2e_test.py ABS path\to\uvvis_folder --ref 1000 --thickness 400 --selftest
python tools/e2e_test.py XRD path\to\xrd_folder
```

`--selftest` modifies the Tauc data after building and checks that Origin's Linear
Fit recalculates (Eg before/after in the log).

## Contributing

Contributions are welcome: bug reports, instrument formats, material defaults, new techniques.
See [`CONTRIBUTING.md`](CONTRIBUTING.md). Every pull request must pass the automated checks
and a review before it is merged.

## Known limitations / roadmap

* The **Tauc Results** summary keeps the *initial* fit values; after changing a range
  in Origin, read the live values in the `TaucFit`/`UrbachFit` reports or the graph
  labels (linking worksheet cells to report cells could not be done by script).
* XRD samples must share the same 2θ grid to be exported together.
* Planned: J-V (solar-cell) module; XRD phase markers (PbI₂, α/δ-FAPbI₃, substrate),
  PbI₂/perovskite peak ratio, Scherrer crystallite size.

## Author, license and citation

Lucas Polimante - Universidade Federal do ABC (UFABC).
Developed with the help of Claude (Anthropic).

Released under the [MIT License](LICENSE). If OriginHub helps your research, please cite it
(see [`CITATION.cff`](CITATION.cff), or *Cite this repository* on the GitHub page).
