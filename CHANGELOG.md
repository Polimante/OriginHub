# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR (breaking changes) . MINOR (new features) . PATCH (fixes).

## [Unreleased]

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
- Continuous integration on GitHub (lint + tests on Windows, Python 3.10 and 3.14).
- MIT license, contribution guide, code of conduct, issue/PR templates, citation file.

## [0.1.0] - 2026-10-19

First public version: UV-Vis (JASCO V-780, Agilent 8453/8454 .SD) and XRD (PowDLL) to Origin,
with baseline, transmittance, Tauc and Urbach analysis and Origin-native Linear Fits.
