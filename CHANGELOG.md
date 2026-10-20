# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/):
MAJOR (breaking changes) . MINOR (new features) . PATCH (fixes).

## [Unreleased]

### Added
- Data validation: every reader's output is checked (finite, strictly ascending X; matching
  lengths; numeric Y) and files that fail are skipped with the reason.
- Automated tests on synthetic spectra with known band gap and Urbach energy, payload contract
  tests, static checks of the Origin-side script, and a GUI smoke test.
- Continuous integration on GitHub (lint + tests on Windows, Python 3.10 and 3.14).
- MIT license, contribution guide, code of conduct, issue/PR templates, citation file.

## [0.1.0] - 2026-10-19

First public version: UV-Vis (JASCO V-780, Agilent 8453/8454 .SD) and XRD (PowDLL) to Origin,
with baseline, transmittance, Tauc and Urbach analysis and Origin-native Linear Fits.
