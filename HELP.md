# OriginHub - Help

OriginHub reads raw files from UV-Vis and XRD instruments, shows a preview, and
builds a complete Origin project (worksheets, graphs and fits) with one click.

---

## 1. Quick start

1. **Load data** - drag files or folders onto the window, or use **Add files…** /
   **Add folder…**. Each file is recognized from its *content*, not its name, and
   goes to the matching tab (**UV-Vis (ABS)** or **XRD**).
2. **Check the table** - uncheck samples you do not want, double-click a name to
   rename it, and select rows + **Remove selected** to drop them.
3. **Choose the options** (UV-Vis tab, see section 3) and look at the **Preview**.
4. Pick the **Version** of Origin (the newest installation is selected by default)
   and, optionally, a **Save to** folder (default: the folder of the data).
5. Click **Export … to Origin**. Origin opens, builds everything and saves a
   `.opju` project named `ABS_<date>_<time>.opju` or `XRD_<date>_<time>.opju`.
   The status bar says **Done** when the project is ready.

Each measurement type is exported to its **own** Origin project.

---

## 2. Supported files

| Technique | Instrument / software | File | How it is read |
|---|---|---|---|
| UV-Vis | JASCO V-780 (Spectra Manager) | `.txt` | Only the `(wavelength, absorbance)` pairs below `XYDATA`; the header and the *Extended Information* block are discarded. The sample name is the **file name**. |
| UV-Vis | Agilent 8453 / 8454 (ChemStation UV-Vis) | `.SD` | Binary file with **several spectra**; each one becomes a sample, named after its *SampleName*. Date, time and instrument are kept. |
| XRD | PowDLL Converter | `.xls` / `.xlsx` | Column 1 = 2θ, other columns = intensity of each sample (header `name (Y)`). |

Spectra with a different wavelength range or step are detected automatically and
get their own X column in Origin (X1, X2, …), shown in the **X axis** column of
the table.

---

## 3. UV-Vis (ABS)

### Options

| Option | What it does |
|---|---|
| **Material** (top bar) | Loads the defaults of a material profile (baseline wavelength, transition, A max, where to look for the absorption edge and the width of the automatic Tauc range). Pick *Generic* for an unlisted material. You can still change every option by hand afterwards. Profiles are plain text files in `app/materials/`; new ones are welcome (see CONTRIBUTING.md). |
| **Baseline at** (nm) | Subtracts from each spectrum its absorbance at this wavelength (mean within ±2 nm). Use a region **below the band gap** where the film does not absorb. For FAPbI₃ (Eg ≈ 1.53 eV, ~810 nm) prefer ≥ 900–1000 nm when the instrument measures that far (Agilent 8454 goes to 1100 nm); 850 nm is still inside the Urbach tail. |
| **Tauc + Urbach** | Turns the band-gap and Urbach analysis on/off. |
| Transition type | Direct allowed (n = 1/2, default for lead-halide perovskites), direct forbidden (3/2), indirect allowed (2), indirect forbidden (3). |
| **A max** | Points whose *raw* absorbance is above this value are excluded from Tauc/Urbach (detector saturation; default 3). |
| **Thickness** + **Apply to all** | Film thickness in nm. Also editable per sample in the table. Optional: it only scales α, so **Eg and E_U do not depend on it**. If any sample has no thickness, α is reported in arbitrary units for all samples. |
| **Auto range** | Resets the Tauc range of every sample to the automatic suggestion (its width comes from the material profile). |
| **Tauc range** (table) | Wavelength window searched for the Tauc fit, e.g. `740-830`. Edit it per sample if the automatic choice is wrong. |

### Preview

The **Preview** menu shows Raw, Baseline, Transmittance, Tauc (each curve normalized,
with the fit line and Eg) and Urbach (ln α with the fit line and E_U). The table
shows the preview Eg and E_U of each sample.

### What is created in Origin

**Book "ABS"**

| Sheet | Content | Graph |
|---|---|---|
| `Raw` | Absorbance as measured | `ABS_raw` |
| `Baseline` | A − A(ref) for each spectrum; the subtracted values are listed in two extra columns at the end | `ABS_baseline` |
| `Transmittance` | %T = 100·10^(−A), from the **raw** absorbance | `ABS_T` |

**One book per sample, "Tauc data - [sample]"**

| Sheet | Content |
|---|---|
| `Data` | λ, E = 1239.84/λ, baseline-corrected A, α, (αhν)^(1/n) (scaled by 10^p for readable axes), ln α |
| `TaucFit` | Origin **Linear Fit** report of the Tauc fit: parameters, **X-Intercept = Eg with its error**, R², adjusted R², ANOVA, residual plots |
| `UrbachFit` | Same, for ln α vs E |
| `…Curve` | Fitted curves |

Graphs **Tauc - [sample]** and **Urbach - [sample]** show the data, the fit line
(black dashed), Origin's fit results table and a label with Eg or E_U.

**Book "Tauc Results"** - one row per sample with the values of the **initial**
fit (Eg, fit error, window uncertainty, R², E_U, …).

### Changing a fit range in Origin

The fits are Origin's own **Linear Fit** operations with **auto recalculation**.
To change a range: click the **green lock** on the graph or on the report →
**Change Parameters…** → edit *Input Data* (you can select the range on the graph).
The report, the fit line, the results table on the graph and the Eg/E_U labels
update automatically.

> The "Tauc Results" sheet is **not** updated by such changes (it keeps the
> initial values). The live values are in each `TaucFit`/`UrbachFit` report and in
> the graph labels.

### How the analysis works

**Tauc (optical band gap).**
α = 2.303·A/d, E = hc/λ, and (αhν)^(1/n) is plotted against E. A straight line is
fitted to the linear part of the absorption edge and extrapolated to the energy
axis: Eg = −intercept/slope (Origin's *X-Intercept*).

* The search window is the **Tauc range**. By default it is ±45 nm around the
  absorption edge with the **longest wavelength** above 300 nm, so in films with
  residual PbI₂ (edge ≈ 500 nm) the perovskite edge (≈ 780–800 nm) is used.
  Below 300 nm glass/ITO absorbs and the signal is noisy.
* Inside the window the fit starts at the edge center (maximum of −dA/dλ) and
  grows while R² ≥ 0.99. Saturated points (A > A max) are excluded.
* **Uncertainty.** The statistical error of the fit is usually < 1 meV and does
  not represent the real uncertainty, which comes from the choice of the window.
  OriginHub refits with the window shifted and shortened by 25 % and reports half
  the spread as *Eg window uncertainty* (typically a few meV).

**Urbach energy (band-tail disorder).**
Below the gap the absorption follows α ∝ exp(E/E_U). E_U is the inverse slope of
ln α vs E **at the absorption edge**: the steep, linear "shoulder" right before
the gap, not the slow rise further below (scattering, defects) nor the plateau
above the gap.

* Search region: Eg − 0.15 eV to Eg + 0.03 eV, using only points with corrected
  A ≥ 0.05.
* The fit starts at the point of maximum d(ln α)/dE and grows while the local
  slope stays ≥ 70 % of that maximum.
* E_U > 100 meV is flagged as **unreliable** (not an exponential tail; e.g. PbI₂
  films, which show broad sub-gap scattering).

**Limitations to keep in mind**

* E_U from transmission UV-Vis is **sensitive to the baseline wavelength** (± a few
  meV) and tends to be **higher** than values from photothermal deflection (PDS) or
  Fourier-transform photocurrent spectroscopy (FTPS), because scattering and
  reflection affect the region near the gap. Compare samples processed with the
  **same** baseline; treat absolute values with care.
* Typical values: ~15 meV for MAPbI₃ measured by PDS/FTPS; 20–40 meV is common
  for perovskite films measured by UV-Vis transmission.
* Tauc analysis of halide perovskites ignores excitonic effects; report the
  method together with Eg.

---

## 4. XRD

**Book "XRD"**

| Sheet | Content | Graph |
|---|---|---|
| `Raw` | X = *Diffraction Angle* (2θ), one Y column (intensity) per sample | `XRD_raw` |
| `normalized` | Each pattern normalized as (I − I_min)/(I_max − I_min) | `XRD_norm` |

Both graphs are **Stacked Lines by Y Offsets** (Origin template `OffsetStackY`):
all samples in one frame, offset vertically. Frame: 3 pt on all four sides, data
lines 2 pt, ticks only on the 2θ axis, the intensity axis shows only its title.

The preview can show raw or normalized data, stacked or overlaid.

---

## 5. Requirements and troubleshooting

* **Origin 2021 or newer** (tested with OriginPro 2025b) with an active license.
  OriginHub looks for installations in `Program Files\OriginLab\` and selects the
  newest one.
* Graph style comes from the user template **PadraoLinha** (saved in Origin's
  *User Files Folder*). If it does not exist, Origin's default `line` template is used.
* If Origin shows an error, the full message is written to a `.log` file in
  `%LOCALAPPDATA%\OriginHub\` and shown by OriginHub.
* Files that are not recognized are skipped; hover over the status bar to see which.

### Setup check (Help → Setup check…)

Shown automatically the first time OriginHub starts. It lists what OriginHub needs outside
itself and its status: **Origin** (2021 or newer; it cannot be installed by OriginHub because
it needs a license), the **work folder** in `%LOCALAPPDATA%\OriginHub`, and the **graph
template** in Origin's User Files Folder. When something can be fixed automatically (for
example, copying a bundled template that is missing) a button appears next to it. **Nothing
is changed unless you click it**, and existing templates are never overwritten. Origin's User
Files Folder is learned from Origin itself on the first export; open Origin once if it is
reported as not found.

When OriginHub runs from source (not installed) and Python packages are missing, it asks
whether to install them with `pip` before starting; it does nothing if you answer no.

### Updates (Help → Check for updates…)

OriginHub checks GitHub for a new version when it starts (in the background; it stays quiet
when offline or up to date). Turn this off with the check box in the update or setup window.
When a new version exists you see what changed and can choose **Download and install**,
**Skip this version** or **Later**. The installer is downloaded from the project's GitHub
Releases page, its SHA-256 checksum is verified (a damaged or altered file is deleted and
nothing is installed), it installs over the current version and OriginHub restarts. If
OriginHub was installed *for all users* (in `Program Files`), Windows asks for permission
during the update. Only published versions are offered, never work in progress.

---

## 6. References

**Band gap (Tauc)**

1. J. Tauc, R. Grigorovici, A. Vancu. *Optical properties and electronic structure
   of amorphous germanium.* Phys. Status Solidi B **15**, 627–637 (1966).
   https://doi.org/10.1002/pssb.19660150224
2. P. Makuła, M. Pacia, W. Macyk. *How to correctly determine the band gap energy
   of modified semiconductor photocatalysts based on UV–Vis spectra.* J. Phys. Chem.
   Lett. **9**, 6814–6817 (2018). https://doi.org/10.1021/acs.jpclett.8b02892
3. A. R. Zanatta. *Revisiting the optical bandgap of semiconductors and the proposal
   of a unified methodology to its determination.* Sci. Rep. **9**, 11225 (2019).
   https://doi.org/10.1038/s41598-019-47670-y

**Urbach energy**

4. F. Urbach. *The long-wavelength edge of photographic sensitivity and of the
   electronic absorption of solids.* Phys. Rev. **92**, 1324 (1953).
   https://doi.org/10.1103/PhysRev.92.1324
5. S. De Wolf, J. Holovsky, S.-J. Moon, P. Löper, B. Niesen, M. Ledinsky, F.-J. Haug,
   J.-H. Yum, C. Ballif. *Organometallic halide perovskites: sharp optical absorption
   edge and its relation to photovoltaic performance.* J. Phys. Chem. Lett. **5**,
   1035–1039 (2014). https://doi.org/10.1021/jz500279b
6. M. Ledinský, T. Schönfeldová, J. Holovský, E. Aydin, Z. Hájková, L. Landová,
   N. Neyková, A. Fejfar, S. De Wolf. *Temperature dependence of the Urbach energy in
   lead iodide perovskites.* J. Phys. Chem. Lett. **10**, 1368–1373 (2019).
   https://doi.org/10.1021/acs.jpclett.9b00138
7. Shatsala et al. *Quantifying optical disorder in CsFaPb(Br,I)₃ perovskites via
   Urbach energy analysis using OPAL2 Fresnel-based simulations.* Adv. Phys. Res.
   (2026). https://doi.org/10.1002/apxr.202500187 - on the effect of reflection and
   scattering on UV-Vis-derived Urbach energies.

**Other**

8. P. Tol. *Colour schemes.* SRON Technical Note SRON/EPS/TN/09-002 (2021) - the
   colour-blind-safe "muted" palette used in all graphs. https://personal.sron.nl/~pault/
9. OriginLab. *Linear Fit* and *LabTalk / originpro* documentation.
   https://www.originlab.com/doc
