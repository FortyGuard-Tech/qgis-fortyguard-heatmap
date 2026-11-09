#!/usr/bin/env python3
"""Print how often the FortyGuard QGIS plugin has been downloaded.

    python3 scripts/plugin_stats.py            # per-release download counts + total, plus 14-day repository traffic
    python3 scripts/plugin_stats.py --json     # same as JSON (for dashboards or a scheduled job)

Where the numbers come from: every install from the QGIS Plugin Manager, from the install page on GitHub Pages and
from the documentation downloads the ZIP attached to the GitHub release (scripts/build_plugin_repo.py points
<download_url> there), and GitHub counts each download of a release asset. The count is downloads, not people:
an update from 0.5.4 to 0.5.5 adds one download to each version. QGIS does not download anything when it only
checks the repository for updates, so those checks are not counted.

Needs the GitHub CLI (gh) signed in to an account with access to the repository; the traffic numbers need push
access. Nothing is stored and no key is involved.
"""
import argparse
import json
import subprocess
import sys

REPO = "FortyGuard-Tech/qgis-fortyguard-heatmap"


def gh_json(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode != 0:
        return None
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args()

    releases = gh_json(f"repos/{REPO}/releases?per_page=100")
    if releases is None:
        sys.exit("Could not read the releases. Is `gh auth status` OK and does the account see the repository?")
    rows = []
    for rel in releases:
        for asset in rel.get("assets", []):
            if asset["name"].endswith(".zip"):
                rows.append({"version": rel["tag_name"], "published": rel["published_at"][:10],
                             "asset": asset["name"], "downloads": asset["download_count"]})
    total = sum(r["downloads"] for r in rows)
    clones = gh_json(f"repos/{REPO}/traffic/clones") or {}
    views = gh_json(f"repos/{REPO}/traffic/views") or {}
    traffic = {"views_14d": views.get("count"), "unique_visitors_14d": views.get("uniques"),
               "clones_14d": clones.get("count"), "unique_cloners_14d": clones.get("uniques")}

    if args.json:
        print(json.dumps({"repository": REPO, "total_downloads": total, "releases": rows, "traffic": traffic}, indent=2))
        return
    print(f"{REPO}\n")
    print(f"{'version':10s} {'published':12s} {'downloads':>9s}")
    for r in rows:
        print(f"{r['version']:10s} {r['published']:12s} {r['downloads']:>9d}")
    print(f"{'total':10s} {'':12s} {total:>9d}\n")
    if views:
        print(f"Repository page, last 14 days: {views['count']} views by {views['uniques']} visitors; "
              f"{clones.get('count', 0)} clones by {clones.get('uniques', 0)} people.")


if __name__ == "__main__":
    main()
