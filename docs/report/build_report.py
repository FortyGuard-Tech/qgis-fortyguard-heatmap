#!/usr/bin/env python3
"""Build docs/report/FortyGuard_Heatmap_QGIS_Project_Report.pdf from the captured screenshots."""
import os
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
                                KeepTogether)
from PIL import Image as PILImage

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "FortyGuard_Heatmap_QGIS_Project_Report.pdf")
W, H = A4
BLUE = colors.HexColor("#0a8fcc"); INK = colors.HexColor("#15232e"); MUTED = colors.HexColor("#5a6b78")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=18, textColor=BLUE, spaceBefore=6, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=INK, spaceBefore=10, spaceAfter=4)
P = ParagraphStyle("P", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=INK, alignment=TA_LEFT)
CAP = ParagraphStyle("CAP", parent=P, fontSize=8.5, leading=11, textColor=MUTED, spaceBefore=3, spaceAfter=10)
B = ParagraphStyle("B", parent=P, leftIndent=12, bulletIndent=2, spaceAfter=2)
TITLE = ParagraphStyle("TITLE", parent=H1, fontSize=26, leading=30, spaceAfter=4)
SUB = ParagraphStyle("SUB", parent=P, fontSize=12, leading=16, textColor=MUTED)

def img(name, max_w=W - 40 * mm, max_h=120 * mm):
    path = os.path.join(HERE, name)
    iw, ih = PILImage.open(path).size
    scale = min(max_w / iw, max_h / ih)
    return Image(path, iw * scale, ih * scale)

def bullets(items):
    return [Paragraph(t, B, bulletText="•") for t in items]

def table(rows, col_widths, header=True):
    data = [[Paragraph(c, P) for c in r] for r in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7e1ea")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5fb"))]
    t.setStyle(TableStyle(style))
    return t

def footer(canvas, doc):
    canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 12 * mm, "FortyGuard Heatmap for QGIS - Project Report - 16 October 2026")
    canvas.drawRightString(W - 20 * mm, 12 * mm, "Page %d" % doc.page); canvas.restoreState()

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                        title="FortyGuard Heatmap for QGIS - Project Report", author="FortyGuard")
s = []

# ---------------- Title page
s += [Spacer(1, 30 * mm), img("icon.png", 28 * mm, 28 * mm), Spacer(1, 8 * mm),
      Paragraph("FortyGuard Heatmap for QGIS", TITLE),
      Paragraph("Project report: a QGIS plugin that brings FortyGuard heat analysis to any map project", SUB),
      Spacer(1, 10 * mm),
      table([["Plugin version", "0.3.5 (0.3.3 is the version currently approved and public on plugins.qgis.org; 0.3.5 is uploaded and awaiting approval)"],
             ["Status", "Published in the official QGIS Plugin Repository (experimental), 15 October 2026"],
             ["Source code", "https://github.com/FortyGuard-Tech/qgis-fortyguard-heatmap (GPL-2.0-or-later)"],
             ["Listing", "https://plugins.qgis.org/plugins/fortyguard_heatmap/"],
             ["Tested on", "macOS 27 (Apple Silicon), QGIS 3.44.15 LTR"],
             ["Prepared by", "Mustafa Hamdy, Automation Engineer, FortyGuard - 16 October 2026"]],
            [40 * mm, W - 80 * mm], header=False),
      PageBreak()]

# ---------------- 1 Summary
s += [Paragraph("1. Summary", H1),
      Paragraph("FortyGuard Heatmap is a QGIS plugin that lets any QGIS user run FortyGuard heat analyses on a polygon in "
                "their own map project, using their own FortyGuard API key. The user selects an area, picks an analysis, a time "
                "window and a resolution, clicks Generate Heatmap, and receives a styled temperature layer in the same project. "
                "The plugin talks directly to the FortyGuard Temperature API (POST /v1/heatmap, GET /v1/status/{activity_id}); "
                "no intermediate backend is involved.", P), Spacer(1, 4),
      Paragraph("What was delivered:", P)]
s += bullets([
    "A complete, installable QGIS plugin with four analysis modes (Temperature/Snapshot, Exceedance, Persistence, Peak temperature time).",
    "131 automated tests plus automated checks inside the real QGIS application.",
    "Live verification against the FortyGuard API (development environment): five completed requests covering all four analyses.",
    "A public source repository with versioned releases, an installation guide, an API contract document and a test report.",
    "Submission to the official QGIS Plugin Repository: security scan passed, email confirmed, approved and publicly listed.",
])
s += [Spacer(1, 6), img("02_heatmap_over_streets.png", max_h=95 * mm),
      Paragraph("Figure 1. Real FortyGuard temperature heatmap (tcm, daily mean, 100 m tiles) over downtown Phoenix, Arizona, "
                "15 July 2024, rendered by the plugin on top of OpenStreetMap in QGIS.", CAP), PageBreak()]

# ---------------- 2 Install
s += [Paragraph("2. How users install the plugin", H1),
      Paragraph("The plugin is distributed through the official QGIS Plugin Repository, so installation is the standard QGIS flow:", P)]
s += bullets([
    "Open QGIS and choose <b>Plugins &gt; Manage and Install Plugins...</b>",
    "In <b>Settings</b>, tick <b>Show also experimental plugins</b> (required while the release is marked experimental).",
    "In the <b>All</b> tab, search for <b>FortyGuard</b>, select <b>FortyGuard Heatmap</b> and click <b>Install Plugin</b>.",
    "A FortyGuard button appears in the toolbar and under <b>Plugins &gt; FortyGuard Heatmap</b>.",
    "Offline alternative: <b>Install from ZIP</b> with the release file from GitHub (fortyguard_heatmap-&lt;version&gt;.zip).",
])
s += [Spacer(1, 4), img("04_plugin_manager.png", max_h=90 * mm),
      Paragraph("Figure 2. The QGIS Plugin Manager with FortyGuard Heatmap selected: description, tags, links, versions and the install button.", CAP),
      img("05_plugins_qgis_org_approved.png", max_h=70 * mm),
      Paragraph("Figure 3. The plugin page on plugins.qgis.org after approval: security scan passed, email confirmed, "
                "experimental version available.", CAP), PageBreak()]

# ---------------- 3 Use
s += [Paragraph("3. How a heatmap is generated", H1),
      Paragraph("Everything happens in one dialog. The settings scroll; the Generate button, status and log stay visible at the bottom.", P)]
s += bullets([
    "<b>API key</b>: the user pastes their own key (masked). <b>Check key and credits</b> shows the plan, key status, expiry and remaining credits before anything is spent. The key stays in memory; optionally it can be saved in the encrypted QGIS authentication database.",
    "<b>Area of interest</b>: any polygon layer in the project; exactly one selected feature. The plugin transforms it to EPSG:4326 (holes preserved) and shows the source CRS and area.",
    "<b>Analysis</b>: Temperature/Snapshot, Exceedance, Persistence or Peak temperature time, with a one-line explanation. A threshold (°C, default 35) appears only for Exceedance and Persistence.",
    "<b>Date and time</b>: single hour, range of hours, single day, range of days or calendar month, validated against the documented limits (2019-01-01 to now + 12 h, 23 h, 31 days). Times are the local time of the area.",
    "<b>Output</b>: 60 / 80 / 100 m resolution, measure for daily outputs (mean/min/max), output folder, maximum wait.",
    "<b>Generate Heatmap</b>: a confirmation shows the environment, area, request and credit cost. The job is polled in the background (QGIS stays responsive); Stop Waiting stops polling only, Check Again resumes the same activity.",
    "<b>Result</b>: GeoJSON saved (never overwritten) with a metadata sidecar, loaded as a separately styled layer, statistics shown in the dialog.",
])
s += [Spacer(1, 4), img("03_plugin_dialog_completed.png", max_h=118 * mm),
      Paragraph("Figure 4. The plugin dialog after a completed request for downtown Phoenix: 527 tiles, daily mean 35.63 to 36.37 °C, "
                "activity ID and saved file shown in the log.", CAP), PageBreak()]

# ---------------- 4 Results
s += [Paragraph("4. Result on the map", H1),
      Paragraph("The test area is a 5.16 km² (1.99 mi²) rectangle over downtown Phoenix, Arizona. Figure 5 shows the base map with "
                "the area outline; Figure 6 shows the heatmap the plugin produced for 15 July 2024 at 100 m resolution, with the "
                "selection layer hidden.", P), Spacer(1, 4),
      img("01_streets_map.png", max_h=92 * mm),
      Paragraph("Figure 5. OpenStreetMap base map of downtown Phoenix with the selected area outlined.", CAP),
      img("02_heatmap_over_streets.png", max_h=92 * mm),
      Paragraph("Figure 6. FortyGuard tcm heatmap (daily mean, °C) for the same area. Blue tiles are cooler, red tiles are hotter; "
                "seven graduated classes from 35.6 to 36.4 °C. Data returned by the FortyGuard API, activity b9ebf067.", CAP), PageBreak()]

# ---------------- 5 Analysis modes
s += [Paragraph("5. Analysis modes", H1),
      Paragraph("The four modes mirror the FortyGuard Autodesk Forma extension. Each mode is one API request; the API computes the result.", P), Spacer(1, 4),
      table([["Mode", "analytic_type", "Result per tile", "Legend"],
             ["Temperature / Snapshot", "tcm", "temperature in the period (°C); mean / min / max for daily windows", "°C"],
             ["Exceedance", "exceedance", "total hours above the threshold in the period", "hours"],
             ["Persistence", "persistence", "longest continuous run of hours above the threshold", "hours"],
             ["Peak temperature time", "time_of_measure", "hour of day (0-23) when the tile reaches its peak", "clock classes, UTC"]],
            [38 * mm, 30 * mm, 70 * mm, 32 * mm]), Spacer(1, 6)]
s += bullets([
    "Threshold and direction (\"above\") are sent only for Exceedance and Persistence.",
    "Single hour is disabled for the three analyses; the dialog switches to Single day and says so.",
    "Calendar month submits the month's first and last day as a range of days (leap years handled, current month clipped).",
    "Zero hours and 00:00 are valid results, not missing data. Percentages in the summary are shares of valid tiles, not of area.",
    "Each result is its own layer, named with the analysis, dates, resolution and threshold.",
])
s += [Spacer(1, 4), img("06_exceedance_live_result.png", max_h=80 * mm),
      Paragraph("Figure 7. Live Exceedance result (hours above 35 °C, 15-21 July 2024, lower Manhattan test area) rendered with the "
                "plugin's hours legend. Returned by the FortyGuard API, activity d0439dfd.", CAP), PageBreak()]

# ---------------- 6 Technical
s += [Paragraph("6. Technical design", H1)]
s += bullets([
    "Pure QGIS/Python plugin, no external dependencies; network calls use QgsNetworkAccessManager (asynchronous, cache disabled for API calls, redirects not followed).",
    "Modules: contract (verified API constants), payload (request building and validation), responses (envelope and schema parsing), polling (bounded deadline, backoff, retry limits), geometry (selection and CRS transformation), api_client, job (submit once, poll with timers), output (save and load), styling (graduated renderers), credentials, demo.",
    "The API key is sent only as the documented api-key header to the chosen FortyGuard host and never written to logs, layers, project files or result files. Production is the default; the development environment sits in a separate Developer settings section and switching clears the key.",
    "A submission is never repeated automatically; the activity ID is kept so an interrupted job can be checked again.",
    "Result schemas are validated per response (temperature fields for the snapshot, the value field for analyses) instead of being assumed.",
    "Demo Mode replays clearly labelled synthetic fixtures through the same code path for offline testing.",
])
s += [Paragraph("7. Validation", H1)]
s += [table([["Check", "Result"],
             ["Automated tests (pure Python + QGIS runtime)", "131 tests, 130 passed, 1 opt-in skipped"],
             ["Automated checks inside QGIS 3.44.15", "Install/load, Demo Mode, styling, project save/reopen, unload, Plugin Manager install: passed"],
             ["Live API, development environment", "tcm single day and single hour; exceedance, persistence and time_of_measure (range of days): all completed; schemas and units verified"],
             ["Real request through the dialog", "Completed (tcm, lower Manhattan); later Phoenix runs by the user"],
             ["plugins.qgis.org security scan", "Passed (Bandit and secret detection clean)"],
             ["Not yet tested", "Windows, Linux, QGIS 4 (Qt 6), production environment (development key only)"]],
            [60 * mm, W - 100 * mm])]
s += [Paragraph("8. Publication timeline", H1),
      table([["Date", "Milestone"],
             ["12 Oct 2026", "API documentation verified; prototype with live request path and Demo Mode"],
             ["13 Oct 2026", "First live requests (dev); release candidate 0.2.0; public GitHub repository created; analysis modes 0.3.0; time zones confirmed by the API team (0.3.1)"],
             ["14 Oct 2026", "OSGeo account; 0.3.2 uploaded and blocked by the security scan; 0.3.3 uploaded and passed; plugin email confirmed"],
             ["15 Oct 2026", "0.3.3 approved and publicly listed; Plugin Manager install verified; 0.3.4/0.3.5 (laptop-screen layout, dark-theme text) released on GitHub and uploaded"]],
            [30 * mm, W - 70 * mm]), PageBreak()]

# ---------------- 9 Findings / next
s += [Paragraph("9. API findings reported to the FortyGuard team", H1)]
s += bullets([
    "An hourly tcm request returned average/min/max fields (identical values) instead of the documented temperature field.",
    "Exceedance and persistence values are fractional hours.",
    "Error messages are under details.message, not the top-level message field.",
    "The usage endpoint returns HTTP 500 on production for a development key.",
    "Confirmed by the team: start/end times are the local time of the area; peak-time hours are UTC. The public docs do not yet state the input time zone.",
])
s += [Paragraph("10. Open items and next steps", H1)]
s += bullets([
    "Approval of 0.3.5 on plugins.qgis.org (uploaded, scan passed, awaiting review). Users on 0.3.3 will see an Upgrade button.",
    "Windows and Linux test runs, then a release without the experimental flag so the plugin appears in the default Plugin Manager search.",
    "One end-to-end request on the production API with a production key.",
    "Optional: 'below' threshold direction, local-time display of peak hours, other FortyGuard products (satellite, street view, heat intelligence).",
])
s += [Paragraph("11. Links", H1)]
s += bullets([
    "Plugin page: https://plugins.qgis.org/plugins/fortyguard_heatmap/",
    "Source and releases: https://github.com/FortyGuard-Tech/qgis-fortyguard-heatmap",
    "FortyGuard API documentation: https://docs-api.fortyguard.com/docs/introduction",
    "API plans: https://www.fortyguard.com/api-pricing - Support: support@fortyguard.com",
])
doc.build(s, onFirstPage=footer, onLaterPages=footer)
print("wrote", OUT)
