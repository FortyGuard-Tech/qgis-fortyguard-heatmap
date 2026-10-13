# Submitting FortyGuard Heatmap to the official QGIS Plugin Repository

Goal: users open **Plugins ▸ Manage and Install Plugins…**, search "FortyGuard",
select **FortyGuard Heatmap**, click **Install**, then enter their own API key.

Three different states, in order. None of them has happened yet.

| State | Meaning | Who/what moves it forward |
|---|---|---|
| **Submitted** | The ZIP was uploaded to plugins.qgis.org. It is invisible to users. | A person with an OSGeo ID uploads (web form or XML-RPC). |
| **Approved** | The automatic security scan passed and a volunteer reviewer approved the version. | plugins.qgis.org staff/volunteers; minutes to days, weekdays. |
| **Publicly available** | The version appears in the repository feed and therefore in the QGIS Plugin Manager. | Automatic after approval. Experimental versions are shown only to users who enable *Show also experimental plugins*. |

## 1. Status of the requirements (checked 2026-10-13 against the live validator source)

| Requirement | Status |
|---|---|
| Public code repository, not a ZIP | **Done:** https://github.com/FortyGuard-Tech/qgis-fortyguard-heatmap |
| `tracker` URL reachable | **Done:** https://github.com/FortyGuard-Tech/qgis-fortyguard-heatmap/issues |
| `homepage` describes the plugin | **Done:** repository README |
| Required metadata (name, description, version, qgisMinimumVersion, author, email, about, tracker, repository) | **Done** (`author=FortyGuard`, `email=support@fortyguard.com`) |
| One top-level folder, PEP 8 name, `__init__.py`, `metadata.txt`, `LICENSE`, README, icon present, no `.pyc`/`__pycache__`/`__MACOSX`/`.git`, ≤ 25 MB | **Done**, verified locally with `scripts/validate_package.py` (a copy of the server rules) |
| Licence compatible with GPL v2+ | **Done:** GPL-2.0-or-later |
| No binaries, uses `QgsNetworkAccessManager` | Done |
| Plugin name not already taken | **Checked:** `fortyguard_heatmap` is not in the repository (404) and no plugin matches "fortyguard" |
| Works on Windows, Linux, macOS | **Only macOS tested.** Reviewers may random-test on other platforms. The release is flagged `experimental=True` for this reason. |
| Uploader account | **Missing: an OSGeo ID.** |

## 2. What is still needed from FortyGuard

1. **An OSGeo ID.** Register at https://id.osgeo.org (free). Use the e-mail that
   should receive the upload and approval notifications (support@fortyguard.com
   is a reasonable choice, so the account belongs to the company and not to one
   person). Keep the password in a password manager; if you want me to upload,
   store it locally as described in §4 and never paste it in chat.
2. **A decision on the experimental flag** (see §5).

## 3. Upload via the web form (recommended for the first version)

1. Log in at https://plugins.qgis.org/accounts/login/ with the OSGeo ID.
2. Open https://plugins.qgis.org/plugins/add/ ("Upload a plugin").
3. Choose `dist/fortyguard_heatmap-0.2.0.zip` (rebuild with `scripts/package.sh`
   and re-check with `python3 scripts/validate_package.py dist/fortyguard_heatmap-0.2.0.zip`
   first).
4. Leave "Publish immediately after security scan passes" unticked (it only
   works for trusted accounts anyway). Submit.
5. You receive a confirmation e-mail, then a second e-mail with the security
   scan result. If the scan blocks the version, fix the finding, bump the
   version number, rebuild and upload again.
6. Wait for manual approval. The plugin page will be
   https://plugins.qgis.org/plugins/fortyguard_heatmap/ once it exists.
7. After approval, verify in QGIS: Plugins ▸ Manage and Install Plugins ▸
   Settings ▸ *Show also experimental plugins* ▸ All ▸ search "FortyGuard".

بالمصري: اعمل حساب OSGeo ID من id.osgeo.org، بعدين ادخل على plugins.qgis.org
وارفع ملف الـ ZIP من صفحة Upload a plugin. هيجيلك إيميلين: تأكيد الرفع ونتيجة
الفحص الأمني. بعد كده هتستنى الموافقة اليدوية. البلجن مش هيظهر في QGIS غير
بعد الموافقة.

## 4. Upload via XML-RPC (automated, after the OSGeo ID exists)

```bash
umask 077; mkdir -p ~/.config/fortyguard
printf 'OSGEO_USERNAME\nOSGEO_PASSWORD\n' > ~/.config/fortyguard/osgeo_credentials
python3 scripts/upload_to_qgis_repo.py dist/fortyguard_heatmap-0.2.0.zip
```
The script calls `plugin.upload` on https://plugins.qgis.org/plugins/RPC2/
(endpoint verified reachable) and never prints the password. Per-plugin API
tokens (plugins.qgis.org ▸ plugin ▸ Tokens) can be created only after the
plugin exists, so they are an option for later versions, not the first one.

## 5. Experimental flag and discoverability

`experimental=True` is honest (macOS-only testing) but hides the plugin from
the default Plugin Manager view: users must tick *Show also experimental
plugins* in the Plugin Manager settings before "FortyGuard" appears in search.
To reach the goal "search and install" without that step, 0.2.x should be
re-tested on Windows and Linux (install the ZIP, run `scripts/run_tests.sh`
and the in-app demo check) and the next version uploaded with
`experimental=False`. Each new upload needs a new version number and a
changelog entry (both already in `metadata.txt`).

## 6. After it is listed

- Update the download page (`docs/download-page/index.html`) with the listing
  URL and the Plugin Manager instructions.
- Later versions: bump `version=`, add a `changelog=` entry, `scripts/package.sh`,
  validate, upload. Reviewers re-check links and may re-test for crashes.
