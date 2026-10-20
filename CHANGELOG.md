# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR (breaking changes) . MINOR (new features) . PATCH (fixes).

## [Unreleased]

## [0.3.1] - 2026-10-20

### Added
- The **PadraoLinha** graph template (the line-graph style used by OriginHub) is now included.
  If it is missing from Origin's User Files Folder, *Help → Setup check…* offers to install it
  (an existing template with that name is never replaced).

## [0.3.0] - 2026-10-20

### Added
- **Automatic updates**: OriginHub checks GitHub for a new version at start-up (in the
  background, silent when offline) and from *Help → Check for updates…*. It shows what changed
  and offers *Download and install*, *Skip this version* or *Later*. The installer's SHA-256 is
  verified before anything is installed; OriginHub restarts on the new version.
- **Setup check** (first start and *Help → Setup check…*): Origin version, work folder and graph
  template, with one-click fixes that run only when clicked and never overwrite existing files.
  Origin reports its User Files Folder on every export so the check knows where to look.
- Starting from source with missing Python packages asks whether to install them with pip.
- *Help* menu: user guide, check for updates, setup check, about (with version details for bug reports).
- Every pull request now builds the installer, installs it, and runs a real self-update from a
  local test release (download, checksum, silent reinstall, restart).

> Versions before 0.3.0 have no updater: install 0.3.0 once from the Releases page; later
> versions are offered inside the app.

## [0.2.0] - 2026-10-20

### Added
- Windows installer (`OriginHub-Setup-<version>.exe`): no Python needed, installs per user
  without administrator rights, Start menu shortcut, uninstaller. Built, installed and checked
  automatically by GitHub Actions for every release and published on the Releases page with its
  SHA-256 checksum.
- `OriginHub.exe --check` (self-test of the installed app) and `--version`; the version is shown
  in the window title.

### Changed
- Techniques are now independent plugins (`app/techniques/uvvis`, `app/techniques/xrd`), each with its
  own readers, tab, Origin script and tests. A technique that fails to load shows an error tab and
  the others keep working; each Origin export copies only its own technique's script.
- Python 3.11 or newer is required (it was 3.10).

### Added
- Material profiles (`app/materials/*.toml`: Generic, FAPbI3, MAPbI3, CsPbBr3) selectable in the
  window: baseline wavelength, transition, A max and absorption-edge search per material.
  Contributed profiles are validated by the tests.
- Guide for adding a material or a technique in CONTRIBUTING.md.
- Data validation: every reader's output is checked (finite, strictly ascending X; matching
  lengths; numeric Y) and files that fail are skipped with the reason.
- Automated tests on synthetic spectra with known band gap and Urbach energy, payload contract
  tests, static checks of the Origin-side script, and a GUI smoke test.
- Continuous integration on GitHub (lint + tests on Windows, Python 3.11 and 3.14).
- MIT license, contribution guide, code of conduct, issue/PR templates, citation file.

## [0.1.0] - 2026-10-19

First public version: UV-Vis (JASCO V-780, Agilent 8453/8454 .SD) and XRD (PowDLL) to Origin,
with baseline, transmittance, Tauc and Urbach analysis and Origin-native Linear Fits.
