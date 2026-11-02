#!/usr/bin/env python3
"""Build the FortyGuard QGIS plugin repository (the files QGIS reads when the
repository URL is added under Plugins > Manage and Install Plugins > Settings).

    python3 scripts/build_plugin_repo.py --out <folder> [--base-url URL] [--zip dist/fortyguard_heatmap-<ver>.zip]

The output folder is what gets published (GitHub Pages branch "gh-pages"):

    plugins.xml                     the index QGIS fetches (one entry: the current version)
    fortyguard_heatmap.<ver>.zip    the plugin package; the dot before the version is REQUIRED,
                                    QGIS derives the plugin id from the part before the first dot
    icon.png                        plugin icon shown in the Plugin Manager
    index.html                      install instructions for people who open the URL in a browser
    .nojekyll                       keeps GitHub Pages from processing the folder

Everything is derived from fortyguard_heatmap/metadata.txt; nothing is typed twice.
"""
import argparse
import configparser
import datetime as dt
import html
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_ID = "fortyguard_heatmap"
DEFAULT_BASE_URL = "https://fortyguard-tech.github.io/qgis-fortyguard-heatmap/"


def read_metadata():
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(ROOT / PLUGIN_ID / "metadata.txt", encoding="utf-8")
    return cp["general"]


def plugins_xml(g, base_url, zip_name, today):
    e = html.escape
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<plugins>
  <pyqgis_plugin name="{e(g['name'])}" version="{g['version']}" plugin_id="{PLUGIN_ID}">
    <description>{e(g['description'])}</description>
    <about>{e(g['about'].strip())}</about>
    <version>{g['version']}</version>
    <qgis_minimum_version>{g['qgisMinimumVersion']}</qgis_minimum_version>
    <qgis_maximum_version>{g.get('qgisMaximumVersion', '3.99')}</qgis_maximum_version>
    <homepage>{e(g['homepage'])}</homepage>
    <file_name>{zip_name}</file_name>
    <icon>{base_url}icon.png</icon>
    <author_name>{e(g['author'])}</author_name>
    <download_url>{base_url}{zip_name}</download_url>
    <uploaded_by>{e(g['author'])}</uploaded_by>
    <create_date>{today}</create_date>
    <update_date>{today}</update_date>
    <experimental>{str(g.get('experimental', 'False')).strip().lower() == 'true' and 'True' or 'False'}</experimental>
    <deprecated>False</deprecated>
    <tracker>{e(g['tracker'])}</tracker>
    <repository>{e(g['repository'])}</repository>
    <tags>{e(g.get('tags', ''))}</tags>
    <downloads>0</downloads>
    <average_vote>0</average_vote>
    <rating_votes>0</rating_votes>
  </pyqgis_plugin>
</plugins>
"""


def index_html(g, base_url, zip_name, today):
    e = html.escape
    repo_url = f"{base_url}plugins.xml"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FortyGuard QGIS plugin repository</title>
<style>
  :root {{ --fg:#16202c; --muted:#66717f; --blue:#2f6fdb; --bg:#ffffff; --box:#f3f6fa; --line:#d9dfe7; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --fg:#e8edf3; --muted:#9aa5b3; --bg:#101722; --box:#17202d; --line:#2a3542; }} }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; }}
  main {{ max-width:720px; margin:0 auto; padding:40px 16px 64px; }}
  h1 {{ font-size:28px; line-height:1.2; margin:16px 0 8px; }}
  h2 {{ font-size:20px; margin:32px 0 8px; }}
  p {{ margin:8px 0; }}
  .muted {{ color:var(--muted); }}
  code, pre {{ font:14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }}
  pre {{ background:var(--box); border:1px solid var(--line); border-radius:6px; padding:12px 14px; overflow:auto; }}
  ol li {{ margin:6px 0; }}
  a {{ color:var(--blue); }}
  .btn {{ display:inline-block; background:var(--blue); color:#fff; text-decoration:none; padding:10px 18px; border-radius:4px; font-weight:700; margin-top:8px; }}
  img.icon {{ width:64px; height:64px; display:block; }}
</style>
</head>
<body>
<main>
  <img class="icon" src="icon.png" alt="">
  <h1>{e(g['name'])}</h1>
  <p class="muted">Version {g['version']} &middot; QGIS {g['qgisMinimumVersion']} or newer &middot; updated {today}</p>
  <p>{e(g['description'])}</p>

  <h2>Install from inside QGIS (recommended)</h2>
  <ol>
    <li>Open QGIS, then <strong>Plugins &rsaquo; Manage and Install Plugins&hellip;</strong></li>
    <li>Click <strong>Settings</strong> in the left column.</li>
    <li>Under <strong>Plugin Repositories</strong> click <strong>Add&hellip;</strong></li>
    <li>Name: <code>FortyGuard</code> &mdash; URL: copy the address below, then click <strong>OK</strong>.</li>
    <li>Go back to <strong>All</strong>, search for <em>FortyGuard</em> and click <strong>Install Plugin</strong>.</li>
  </ol>
  <pre>{repo_url}</pre>
  <p class="muted">QGIS checks this repository for updates like any other, so new versions appear in the Plugin Manager automatically.</p>

  <h2>Or install the ZIP</h2>
  <p>Download the package and use <strong>Plugins &rsaquo; Manage and Install Plugins&hellip; &rsaquo; Install from ZIP</strong>.</p>
  <a class="btn" href="{zip_name}">Download {zip_name}</a>

  <h2>Links</h2>
  <p><a href="{e(g['homepage'])}">Documentation and source code</a> &middot; <a href="{e(g['tracker'])}">Report an issue</a> &middot; <a href="https://www.fortyguard.com/api-pricing">Get an API key</a></p>
</main>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="output folder (created; existing index files are overwritten)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL, help="public URL the folder will be served from (with trailing slash)")
    ap.add_argument("--zip", help="plugin ZIP built by scripts/package.sh (default: dist/fortyguard_heatmap-<version>.zip)")
    args = ap.parse_args()

    g = read_metadata()
    version = g["version"].strip()
    base_url = args.base_url if args.base_url.endswith("/") else args.base_url + "/"
    src_zip = pathlib.Path(args.zip) if args.zip else ROOT / "dist" / f"{PLUGIN_ID}-{version}.zip"
    if not src_zip.exists():
        sys.exit(f"ZIP not found: {src_zip} (run scripts/package.sh first)")
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    zip_name = f"{PLUGIN_ID}.{version}.zip"
    today = dt.date.today().isoformat()
    shutil.copyfile(src_zip, out / zip_name)
    shutil.copyfile(ROOT / PLUGIN_ID / "resources" / "icon.png", out / "icon.png")
    (out / "plugins.xml").write_text(plugins_xml(g, base_url, zip_name, today), encoding="utf-8")
    (out / "index.html").write_text(index_html(g, base_url, zip_name, today), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"Repository built in {out}")
    print(f"  index:    {base_url}plugins.xml")
    print(f"  package:  {base_url}{zip_name}")


if __name__ == "__main__":
    main()
