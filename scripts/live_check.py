#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless LIVE check of one real FortyGuard heatmap request using the plugin's own code path.

This script spends credits when the job completes. It refuses to run unless you
pass --confirm and it never prints the API key.

Credential source (first found wins):
  1. environment variable FORTYGUARD_API_KEY
  2. file ~/.config/fortyguard/api_key  (create with: umask 077; mkdir -p ~/.config/fortyguard;
     printf '%s' 'YOUR_KEY' > ~/.config/fortyguard/api_key)

Run with the QGIS-bundled Python so qgis.core is importable:
  /Applications/QGIS.app/Contents/MacOS/python scripts/live_check.py \
      --aoi fortyguard_heatmap/fixtures/demo_aoi.geojson --date 2024-07-15 --filter 3 \
      --granularity 100 --out "$HOME/Documents/FortyGuard Heatmaps" --confirm

Outputs: the saved GeoJSON + .meta.json, a summary JSON next to them, and a
schema report on stdout (field names, numeric ranges, stats keys) for docs/API_CONTRACT.md.
"""
import argparse
import json
import os
import stat
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def read_key():
    key = os.environ.get("FORTYGUARD_API_KEY", "").strip()
    if key:
        return key, "environment variable FORTYGUARD_API_KEY"
    path = os.path.expanduser("~/.config/fortyguard/api_key")
    if os.path.isfile(path):
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & 0o077:
            print("!! %s is readable by other users (mode %o). Run: chmod 600 %s" % (path, mode, path))
            sys.exit(2)
        with open(path, "r", encoding="utf-8") as fh:
            key = fh.read().strip()
        if key:
            return key, path
    return "", ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aoi", required=True, help="GeoJSON file with one Polygon Feature/geometry (EPSG:4326)")
    ap.add_argument("--date", required=True, help="start_date YYYY-MM-DD")
    ap.add_argument("--filter", type=int, default=3, help="filter_type 1-4 (default 3 = single day)")
    ap.add_argument("--start-time", default=None, help="HH:MM for filter 1/2")
    ap.add_argument("--end-time", default=None, help="HH:MM for filter 2")
    ap.add_argument("--end-date", default=None, help="YYYY-MM-DD for filter 4")
    ap.add_argument("--granularity", type=int, default=100)
    ap.add_argument("--analytic", default="tcm", choices=["tcm", "exceedance", "persistence", "time_of_measure"])
    ap.add_argument("--threshold", type=float, default=None, help="°C, required for exceedance/persistence")
    ap.add_argument("--out", default=os.path.expanduser("~/Documents/FortyGuard Heatmaps"))
    ap.add_argument("--max-wait-min", type=int, default=20)
    ap.add_argument("--base-url", default=None, help="override API base URL (e.g. dev environment)")
    ap.add_argument("--activity-id", default=None, help="skip submission and poll this existing activity instead")
    ap.add_argument("--confirm", action="store_true", help="required: acknowledges that a completed request costs credits")
    args = ap.parse_args()

    if not args.confirm:
        print("Refusing to run without --confirm (a completed request consumes credits).")
        sys.exit(2)

    key, source = read_key()
    if not key:
        print("No API key found. Set FORTYGUARD_API_KEY or create ~/.config/fortyguard/api_key (chmod 600).")
        sys.exit(2)
    print("API key loaded from %s (%d characters; value not shown)." % (source, len(key)))

    from tests import qgis_env  # sets PROJ/GDAL paths and starts a headless QgsApplication
    qgis_env.start()
    from qgis.PyQt.QtCore import QEventLoop, QTimer
    from fortyguard_heatmap.core import contract, output, payload, responses
    from fortyguard_heatmap.core.api_client import HeatmapApiClient
    from fortyguard_heatmap.core.job import HeatmapJob

    with open(args.aoi, "r", encoding="utf-8") as fh:
        gj = json.load(fh)
    if gj.get("type") == "FeatureCollection":
        gj = gj["features"][0]
    geom = gj["geometry"] if gj.get("type") == "Feature" else gj
    body = payload.build_payload(geom, args.filter, args.date, args.granularity,
                                 start_time=args.start_time, end_time=args.end_time, end_date=args.end_date,
                                 analytic_type=args.analytic, threshold=args.threshold,
                                 direction="above" if args.threshold is not None else None)
    summary = payload.describe_request(body)
    print("Request:", json.dumps({k: v for k, v in body.items() if k != "polygon_aoi"}))
    print("AOI ring points:", len(body["polygon_aoi"]["features"][0]["geometry"]["coordinates"][0]))

    client = HeatmapApiClient(key, base_url=args.base_url or contract.DEFAULT_BASE_URL)
    job = HeatmapJob(client, deadline_s=args.max_wait_min * 60)
    state = {"done": False, "ok": False, "map": None, "stats": None, "error": None}
    job.submitted.connect(lambda a: print("submitted -> activity_id", a))
    job.status_changed.connect(lambda s, d: print("status:", s, "|", d))
    job.progress.connect(lambda m: print("  ", m))
    job.completed.connect(lambda m, s: state.update(done=True, ok=True, map=m, stats=s))
    job.failed.connect(lambda m, k: (print("FAILED [%s]: %s" % (k, m)), state.update(done=True, error=(k, m))))

    if args.activity_id:
        job.resume(args.activity_id)
    else:
        job.submit(body)

    loop = QEventLoop()
    while not state["done"]:
        loop.processEvents(QEventLoop.AllEvents, 100)
        QTimer.singleShot(100, lambda: None)

    report = {"activity_id": job.activity_id, "request": {k: v for k, v in body.items() if k != "polygon_aoi"},
              "ok": state["ok"], "error": state["error"]}
    if state["ok"]:
        md, st = state["map"], state["stats"]
        feats = md["features"]
        keys = sorted({k for f in feats for k in (f.get("properties") or {}).keys()})
        gtypes = sorted({(f.get("geometry") or {}).get("type") for f in feats})
        measures = responses.available_measures(md)
        schema = responses.result_schema(md)
        report.update({
            "n_features": len(feats), "geometry_types": gtypes, "property_keys": keys, "schema": schema,
            "available_measures": measures,
            "ranges": {m: responses.numeric_summary(md, m) for m in (measures or ([contract.FIELD_VALUE] if schema == "value" else []))},
            "stats_data_keys": sorted(st.keys()) if isinstance(st, dict) else None,
            "temperature_stats": responses.temperature_stats(st),
            "analysis_stats": responses.analysis_stats(st),
            "duration_summary": responses.duration_summary(md) if args.analytic in ("exceedance", "persistence") else None,
            "peak_time_summary": {k: v for k, v in responses.peak_time_summary(md).items() if k != "histogram"} if args.analytic == "time_of_measure" else None,
            "first_feature_properties": feats[0].get("properties"),
        })
        gpath, mpath = output.save_result(args.out, md, st, summary, job.activity_id, demo=False, analytic_type=args.analytic)
        report["saved_geojson"] = gpath
        report["saved_meta"] = mpath
        with open(os.path.splitext(gpath)[0] + ".live_check.json", "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    print(json.dumps(report, indent=2, default=str))
    sys.exit(0 if state["ok"] else 1)


if __name__ == "__main__":
    main()
