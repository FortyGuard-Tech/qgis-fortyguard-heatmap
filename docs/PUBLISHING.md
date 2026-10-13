# Publishing FortyGuard Heatmap to the official QGIS Plugin Repository

Requirements below were read on 2026-10-13 from
https://plugins.qgis.org/docs/publish and https://plugins.qgis.org/docs/approval.
Nothing has been uploaded yet; the plugin is **not** listed anywhere.

## 1. What the repository requires

| Requirement (plugins.qgis.org) | Status in this project |
|---|---|
| One top-level folder in the ZIP, named like the plugin id, no `__MACOSX`, `.git`, `__pycache__`, generated `ui_*.py`/`resources_rc.py`, no binaries, ≤ 25 MB | Done: `scripts/package.sh` → `dist/fortyguard_heatmap-0.2.0.zip` (one folder `fortyguard_heatmap`, ~110 KB) |
| `metadata.txt` with name, qgisMinimumVersion, description, about, version, author, email, repository (+ tracker, homepage, changelog, tags, icon, experimental) | **Done** (`author=FortyGuard`, `email=support@fortyguard.com`) |
| `homepage` must describe the plugin (README or repo README accepted); `tracker` must be the repository issue tracker; `repository` must be a public, non-ZIP source repo | **Done:** https://github.com/FortyGuard-Tech/qgis-fortyguard-heatmap (public, issues enabled, README as homepage). Both URLs verified reachable. |
| License compatible with GPL v2 or later; `LICENSE` file in the plugin; README included | Done: GPL-2.0-or-later, `fortyguard_heatmap/LICENSE`, root `README.md` (copy into the plugin folder if the repo README is not used as homepage) |
| Short English description, English code comments, PEP8-ish code | Done |
| Use `QgsNetworkAccessManager`, not `requests`/`urllib` | Done |
| Works on Windows, Linux and macOS (reviewers random-test for crashes) | **Only macOS tested.** Release stays `experimental=True` until Windows/Linux runs are done. |
| New version number + changelog for every update | Done (0.2.0, `changelog=` in metadata and `CHANGELOG.md`) |
| Upload → automatic security scan (secrets, suspicious files, code quality) → e-mail with results → manual approval by volunteers (minutes to days, weekdays) | Not started. The package contains no secrets (`scripts/package.sh` refuses key-like strings). |
| Uploader needs a plugins.qgis.org account (OSGeo ID) | **Missing – FortyGuard has no OSGeo ID yet.** See `docs/SUBMISSION.md`. |

## 2. Upload steps

1. Repository, metadata and ZIP are ready (see `docs/SUBMISSION.md` for the
   step-by-step upload guide and the three states: submitted → approved → available).
2. Re-check before every upload: `scripts/run_tests.sh`, `scripts/package.sh`,
   `python3 scripts/validate_package.py dist/fortyguard_heatmap-<version>.zip`.
3. Not applicable (done).
4. Log in at https://plugins.qgis.org/accounts/login/ (OSGeo ID) → *Upload a plugin* → choose the ZIP.
5. Wait for the two e-mails (upload confirmation, security scan). Fix and re-upload
   with a new version number if the scan blocks the version.
6. Wait for manual approval. Only after approval does the plugin appear in
   QGIS → Plugins → *All* (experimental plugins are visible only when the user
   enables "Show also experimental plugins").
7. Announce the listing URL (`https://plugins.qgis.org/plugins/fortyguard_heatmap/`)
   on the download page once it is really live.

## 3. Still missing (do not invent)

- plugins.qgis.org (OSGeo ID) account to upload with – register at https://id.osgeo.org.
- Official vector logo (the current icon is the 256 px mark from fortyguard.com).
- Windows/Linux test runs before dropping the experimental flag.

## 4. Interim distribution without the repository

Users can already install the ZIP via *Plugins → Manage and Install Plugins →
Install from ZIP*. See `docs/download-page/` for the download-page content.
