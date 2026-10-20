#!/usr/bin/env python3
"""Build docs/report/FortyGuard_QGIS_Plugin_Testing_Fix_Report.pdf: the internal-testing fix report (0.5.0 - 0.5.3)."""
import os
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from PIL import Image as PILImage

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "images")
OUT = os.path.join(HERE, "FortyGuard_QGIS_Plugin_Testing_Fix_Report.pdf")
W, H = A4
BLUE = colors.HexColor("#0a8fcc"); INK = colors.HexColor("#15232e"); MUTED = colors.HexColor("#5a6b78")
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=17, textColor=BLUE, spaceBefore=6, spaceAfter=8)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, textColor=INK, spaceBefore=10, spaceAfter=4)
P = ParagraphStyle("P", parent=ss["Normal"], fontName="Helvetica", fontSize=9.6, leading=13.4, textColor=INK, alignment=TA_LEFT)
S = ParagraphStyle("S", parent=P, fontSize=8.4, leading=11)
CAP = ParagraphStyle("CAP", parent=P, fontSize=8.5, leading=11, textColor=MUTED, spaceBefore=3, spaceAfter=10)
B = ParagraphStyle("B", parent=P, leftIndent=12, bulletIndent=2, spaceAfter=2)
TITLE = ParagraphStyle("TITLE", parent=H1, fontSize=24, leading=28, spaceAfter=4)
SUB = ParagraphStyle("SUB", parent=P, fontSize=12, leading=16, textColor=MUTED)


import tempfile
_TMP = tempfile.mkdtemp(prefix="fg_report_")


def img(name, max_w=W - 40 * mm, max_h=110 * mm):
    """Embed a screenshot downscaled to 1400 px (JPEG) so the PDF stays small enough to attach to a ticket."""
    path = os.path.join(IMG, name) if not os.path.isabs(name) else name
    im = PILImage.open(path).convert("RGB")
    if im.size[0] > 1400 and name.lower().endswith(".png") and "icon" not in name:
        ratio = 1400.0 / im.size[0]
        im = im.resize((1400, int(im.size[1] * ratio)), PILImage.LANCZOS)
        path = os.path.join(_TMP, os.path.splitext(os.path.basename(name))[0] + ".jpg")
        im.save(path, "JPEG", quality=82, optimize=True)
    iw, ih = im.size
    scale = min(max_w / iw, max_h / ih)
    return Image(path, iw * scale, ih * scale)


def fig(name, caption, max_h=110 * mm):
    return KeepTogether([img(name, max_h=max_h), Paragraph(caption, CAP)])


def bullets(items):
    return [Paragraph(t, B, bulletText="•") for t in items]


def table(rows, col_widths, header=True, style=S):
    data = [[Paragraph(c, style) for c in r] for r in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7e1ea")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef5fb"))]
    t.setStyle(TableStyle(st))
    return t


def footer(canvas, doc):
    canvas.saveState(); canvas.setFont("Helvetica", 8); canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 12 * mm, "FortyGuard Temperature Intelligence Layer for QGIS - Internal testing fix report - 20 October 2026")
    canvas.drawRightString(W - 20 * mm, 12 * mm, "Page %d" % doc.page); canvas.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                        title="FortyGuard QGIS plugin - internal testing fix report", author="FortyGuard")
s = []
FULL = W - 40 * mm

# ---------------- Title
s += [Spacer(1, 26 * mm), img(os.path.join(HERE, "icon.png"), 26 * mm, 26 * mm), Spacer(1, 8 * mm),
      Paragraph("FortyGuard Temperature Intelligence Layer for QGIS", TITLE),
      Paragraph("Internal testing fix report: every issue raised by the FortyGuard team, its root cause, the fix shipped, "
                "and how it was verified (plugin versions 0.5.0 to 0.5.3)", SUB),
      Spacer(1, 10 * mm),
      table([["Task", "Update the QGIS integration issues reported in the internal testing sheet (\"FortyGuard QGIS Plugin - Internal Testing\")"],
             ["Testing rounds", "19 October 2026 (9 testers, macOS / Windows / Ubuntu) and 20 October 2026 (3 testers, Windows), plus an independent code review on 20 October 2026"],
             ["Issues handled", "49 rows: 26 from round one, 11 from round two, 12 from the code review; all fixed, none deferred"],
             ["Versions shipped", "0.5.0, 0.5.1, 0.5.2, 0.5.3 (GitHub releases with installable ZIPs); 0.5.3 is the version to publish on plugins.qgis.org"],
             ["Verification", "96 pure-Python and 105 QGIS-runtime automated tests (0 failed); Bandit and plugins.qgis.org validator clean; three real production requests re-checked after the fixes"],
             ["Source", "https://github.com/FortyGuard-Tech/qgis-fortyguard-heatmap (GPL-2.0-or-later)"],
             ["Prepared by", "Mustafa Hamdy, Automation Engineer, FortyGuard - 20 October 2026"]],
            [38 * mm, FULL - 38 * mm], header=False, style=P),
      PageBreak()]

# ---------------- 1 Summary
s += [Paragraph("1. Summary", H1),
      Paragraph("Nine colleagues tested plugin 0.4.2 from the official QGIS Plugin Repository against the production API on "
                "19 October 2026 and recorded 34 rows in the internal testing sheet; three more colleagues added 12 rows on "
                "20 October (Windows). The installation, Demo Mode, the direct comparison of all four analyses with the raw API "
                "(0 differences) and the Windows load/unload cycle passed. Every reported failure was traced to a root cause, "
                "fixed, covered by an automated test and released. An independent code review was then run on the whole "
                "plugin before the next round and found twelve further defects, which were fixed in 0.5.3.", P),
      Paragraph("One finding dominates: the plugin trusted the API documentation in places where the production API behaves "
                "differently. The documentation says data is available through 12 hours past the current time; in practice "
                "the most recent five to seven days are rejected. The documentation describes plan area caps; the API accepts "
                "any area, charges a flat 4,220 credits, and never finishes areas above a few hundred square miles. Completed "
                "jobs with zero tiles (areas outside the United States or smaller than one tile) are charged. The credits "
                "field the plugin displayed stays frozen after a billing cycle ends. The fixes therefore add client-side "
                "pre-checks, safer defaults and honest messages, and record these observations in the API contract document "
                "for the API team.", P),
      Paragraph("Highlights of what changed for users", H2)]
s += bullets([
    "Dates default to one week ago; a request for recent days is explained in plain words and marked as free of charge.",
    "Before any paid request the plugin checks coverage (United States), area size, recent dates, duplicates and unfinished "
    "earlier requests, and states the expected cost for the user's plan.",
    "\"Check key and credits\" shows the live balance; it moved by exactly 4,220 credits per request in verification.",
    "Legends are readable: labels get as many decimals as the data needs, uniform results show one class, tiles without a "
    "value no longer distort the classes, peak-time hours fall in the right class, and the smooth surface is named and bounded.",
    "Paid results are never lost: Stop during submission keeps the activity ID, cut-off answers are retried, results are "
    "saved before styling, and any earlier activity ID can be fetched again with Check Again.",
    "Dialog polish: readable steps, no orphan labels, remembered analysis settings, narrow-window wrapping, a demo-specific "
    "stop message, in-place status updates, a plain description, and the development environment hidden in the public build.",
    "The plugin is no longer marked experimental: it has now run on macOS, Windows 11 and Ubuntu."])

# ---------------- 2 Testing rounds
s += [Paragraph("2. Testing rounds and scope", H1),
      table([["Round", "Date", "Testers", "Platforms", "Rows", "Outcome"],
             ["1", "19 Oct 2026", "Fares, Rohit, Arpit, Inji, Sarang, Aashan, Akhilesh, Fawad (8) + Mustafa", "macOS 26/27 (QGIS 3.44.15), Windows 11 (3.44), Ubuntu 26 (3.40.15)", "34", "4 passed, 26 failures / observations, 1 blocked (static review) -> fixed in 0.5.0"],
             ["2", "20 Oct 2026", "Shreya, Mudethir, Snehil", "Windows 11 (QGIS 3.44.15 / 3.44)", "12", "1 passed, 10 failures / requests, 1 blocked (time-zone text to confirm) -> fixed in 0.5.2"],
             ["Review", "20 Oct 2026", "Independent code review (fresh-eyes pass, headless dialog driving)", "macOS (QGIS 3.44.15)", "12", "12 verified defects -> fixed in 0.5.3"]],
            [14 * mm, 20 * mm, 48 * mm, 44 * mm, 10 * mm, FULL - 136 * mm]),
      Spacer(1, 4 * mm),
      Paragraph("What passed without change: installation and reopening on all three platforms; Demo Mode on all analyses; "
                "the direct API comparison of Snapshot, Exceedance, Persistence and Peak temperature time (payloads, tile IDs, "
                "geometries, values, statistics and saved files identical, 0 differences); \"Generate\" correctly ignored while "
                "a job is running; load, unload and reopen on Windows; encrypted key storage.", P)]

# ---------------- 3 Root causes
s += [Paragraph("3. Root causes observed on the production API", H1),
      Paragraph("These observations were made by the testers and confirmed by the fixes' own verification. They are not in "
                "the public documentation and are now recorded in docs/API_CONTRACT.md (section \"Observed behaviour\") for the API team.", P),
      table([["Topic", "Observed", "Plugin response"],
             ["Data latency", "On 19 October the days 15-18 October were rejected with HTTP 400 \"Temperature data is unavailable for one or more hours\"; 14 October completed. Rejections were free.", "Default date = today minus 7; warning for later windows; Calendar month clipped; plain-language message."],
             ["Range of days", "The end date is inclusive; 1 July to 1 August (32 days) was accepted, ran seven minutes and failed without a reason.", "Local rule: 31 days counting both dates; hint to use Calendar month."],
             ["Credits", "Every completed request cost exactly 4,220 credits on Premium and Hackathon keys, for any area or resolution.", "Observed cost shown for plans without a documented figure."],
             ["Empty results", "Paris, London, open ocean, a 64 m2 polygon and a 10 m polygon all completed with 0 tiles and were charged.", "Coverage outline check (block), tile-size warning, \"empty\" result kind that states the charge, local record file."],
             ["Area caps", "Not enforced: 400 mi2 completed (103,099 tiles); 1,300 and 11,472 mi2 were accepted, charged, and the status endpoint answered HTTP 504 forever.", "Warn above the plan allowance; block above 500 mi2; explain repeated 5xx."],
             ["Usage endpoint", "cycle_remaining_credits stayed frozen across nine billed requests on a key whose cycle had ended; total_remaining_credits moved by 4,220 each time.", "Read total_remaining_credits."],
             ["Idempotency", "An identical request re-run after completion created a new activity and was charged again.", "Request fingerprint stored in the sidecar; warning when it was already completed."],
             ["Gateway errors", "Occasional HTTP 504 on submission for small areas; the same request succeeded on the next try.", "Explained as server-side and uncertain, not as a key problem."]],
            [26 * mm, 80 * mm, FULL - 106 * mm])]

# ---------------- 4 Fixes
s += [PageBreak(), Paragraph("4. Issues, root causes and fixes", H1),
      Paragraph("4.1 Round one (fixed in 0.5.0, released 20 October 2026)", H2),
      table([["#", "Reported by", "Issue", "Root cause", "Fix"],
             ["1", "Fares, Arpit, Inji, Aashan", "Default date (yesterday) and recent dates fail with HTTP 400; message unexplained", "Plugin trusted the documented \"now + 12 h\" limit", "Default today - 7; latency warning; no_data kind with a plain explanation and \"nothing was charged\""],
             ["2", "Aashan", "Calendar month for the current month always fails", "Clipped to now + 12 h", "Clipped to the available days; explained"],
             ["3", "Fares", "Range of days defaults confusing", "start = end = yesterday", "Valid 7-day default window"],
             ["4", "Aashan", "32 inclusive days accepted; 7-minute server failure", "Day count ignored the inclusive end date", "Count both dates; hint to Calendar month"],
             ["5", "Aashan, Mudethir", "Credits shown never move", "Frozen cycle_remaining_credits read first", "Live total_remaining_credits; low-credit warning on the same figure"],
             ["6", "Aashan, Fawad, Rohit", "Paris / London / ocean / 64 m2 polygons: 0 tiles, charged, reported as \"malformed\"", "No coverage or size check; empty result treated as a parsing error", "Coverage outline (block / warn); tile-size warning; \"empty\" kind stating the charge; record file"],
             ["7", "Arpit, Fawad", "Huge polygons accepted, charged, HTTP 504 forever", "No area check; generic give-up message", "Block above 500 mi2; warn above the plan allowance; explained message"],
             ["8", "Aashan", "Identical request charged again", "Only \"Generate while active\" was guarded", "Fingerprint in the sidecar; warning in this session and from the output folder"],
             ["9", "Fawad", "Stop during submit may lose the paid job's ID", "The POST was aborted", "Answer awaited, ID recorded, then stop"],
             ["10", "Fawad", "New Generate after a timeout orphans the earlier job", "Silent disposal", "Unfinished activity pointed out in the confirmation"],
             ["11", "Fawad", "Status body cut off mid-transfer stops polling", "Fatal \"malformed\"; transport errors with a status were parsed", "Retryable; network-layer errors retried"],
             ["12", "Akhilesh", "Old activity 404 shown as \"just submitted\", 8 retries", "Same policy for submit and resume", "3 checks on resume, specific message"],
             ["13", "Aashan", "\"Message: Failed\" repeats the status", "Appended whenever present", "Only when informative"],
             ["14", "Fawad", "Transient HTTP 500 on submit; user not told it was free", "Generic message", "States no job was created and nothing was charged"],
             ["15", "Aashan, Fawad", "Legend labels collapse (\"21.9 - 21.9\"); uniform results show seven identical classes", "One-decimal labels; quantile on few distinct values", "Decimals follow the spread; zero-width classes dropped; one class for uniform results"],
             ["16", "Fawad", "Peak-time hours 4, 8, 12, 16, 20 in the previous class", "QGIS matches both class bounds inclusively", "Upper bound just below the next bound"],
             ["17", "Aashan", "Surface legend \"Band 1 (Gray)\"; 0.21 C stretched over the whole ramp", "No band description; min-max stretch", "Named band; minimum colour span 1 C / 1 h; spread shown"],
             ["18", "Fawad", "NaN written as literal NaN (invalid JSON)", "json.dump default", "Non-finite values become null"],
             ["19", "Fawad", "Long summary: OSError; sidecar overwritten", "Unbounded name; only .geojson checked", "Capped stem; all sibling files checked"],
             ["20", "Sarang", "Orphan \"Start date\" label in Calendar month mode", "Label never hidden", "Label toggled with the field"],
             ["21", "Sarang", "Demo stop mentions a server job and a disabled Check Again", "One handler for demo and live", "Demo-specific message"],
             ["22", "Sarang", "Getting-started steps run together", "No line breaks", "One step per line"],
             ["23", "Aashan", "Analysis settings not restored after restart", "Only presentation settings saved", "Analysis, time option, threshold, resolution, times remembered"],
             ["24", "Akhilesh", "Texts and buttons cropped at narrow widths", "Fixed-width rows", "Wrapping rows and labels; own row for the credits button"],
             ["25", "Akhilesh", "Hackathon plan: no cost in the confirmation", "Only documented plans quoted", "Cost for the checked plan, observed cost otherwise"],
             ["26", "Fares, Shreya", "Install needed \"Show also experimental plugins\"", "experimental = True", "experimental = False after Windows and Linux tests"]],
            [7 * mm, 22 * mm, 46 * mm, 40 * mm, FULL - 115 * mm]),
      Spacer(1, 3 * mm),
      Paragraph("0.5.1 added a \"Legend classes\" option (3 to 20, default 10) after the report review asked for more classes.", P),
      Paragraph("4.2 Round two (fixed in 0.5.2)", H2),
      table([["#", "Reported by", "Issue", "Root cause", "Fix"],
             ["27", "Mudethir", "Lowest legend class \"0.0 - 26.3 C\" when one tile has no value", "QGIS updateClasses() counts NULL as 0 (reproduced on macOS)", "Breaks computed from the numeric values only"],
             ["28", "Mudethir", "Default folder ignores OneDrive-redirected Documents", "Home folder + \"Documents\"", "Documents folder reported by the system"],
             ["29", "Shreya", "Cannot check a stopped request after sending another", "Only the last job could be polled", "Editable Activity ID field; Check Again on any pasted ID; IDs logged"],
             ["30", "Shreya", "HTTP 504 on submit; same request worked next time; \"reload the key?\"", "Message did not say it was server-side", "Gateway errors explained: server-side, not the key, outcome uncertain"],
             ["31", "Snehil", "\"Processing\" repeated every poll", "One line per check", "Status line updates in place; log only on change"],
             ["32", "Snehil", "Appearance option refers to \"the dashboard\"", "Wording", "\"Smooth surface (interpolated estimate) + exact tiles layer hidden\""],
             ["33", "Snehil", "Developer settings expose the development environment", "Selector always built", "Hidden unless FORTYGUARD_DEV_ENVIRONMENT=1; \"Advanced settings\""],
             ["34", "Snehil", "Plugin description cluttered", "Long paragraphs", "Short sections with bullets"],
             ["35", "Snehil", "Time-handling helper text to be confirmed", "-", "Unchanged: matches the API team's confirmation of 13 October; open for re-confirmation"],
             ["36", "self-review", "\"18.51 - 18.51 C\" labels with 10 classes on a 0.27 C spread", "Fixed decimals per spread", "Decimals increase until every label is distinct"]],
            [7 * mm, 22 * mm, 46 * mm, 40 * mm, FULL - 115 * mm]),
      Paragraph("4.3 Independent code review (fixed in 0.5.3)", H2),
      table([["#", "Severity", "Defect", "Fix"],
             ["38", "High", "Check Again on an earlier activity used the latest request's analysis type, threshold and area; a stopped Exceedance fetched after a Temperature run errored and the paid GeoJSON was not saved", "Per-activity request context; the API's stats_data.analytic_type is authoritative"],
             ["39", "High", "A cancelled confirmation or blocked pre-check overwrote the previous job's context", "Context applied only when the job starts"],
             ["40", "Medium", "Restyle after the layer was removed raised a Python error", "Layer resolved through the project; clean message"],
             ["41", "Medium", "Restyle changed the hidden tiles but not the visible surface", "Surface rebuilt for the new measure"],
             ["42", "Medium", "Schema check raised before saving; message claimed the file was saved", "Save first, then style; path in the message"],
             ["43", "Medium-low", "Zero-width first class forced four-decimal labels", "Zero-width classes merged into neighbours"],
             ["44", "Low-medium", "PolygonZ/M areas sent 3-D coordinates", "Z/M dropped"],
             ["45", "Low", "Check Again after a demo run replayed the fixture as if live", "Demo IDs refused"],
             ["46", "Low", "Same-job Check Again used the key from submission time", "Client rebuilt when the key differs"],
             ["47", "Low", "Date pickers allowed tomorrow; the payload rejected it before noon", "Maximum date = today"],
             ["48", "Low", "OSError while saving lost the paid result with a traceback", "Caught; message with the activity ID"],
             ["49", "Low", "Duplicate warning pointed at an empty-result record as a loadable file", "Separate wording"],
             ["-", "Hardening", "Enter could trigger Generate; a button re-enabled mid-run; unfinished activity cleared too eagerly; surface memory on large areas", "Non-default buttons; busy check; per-activity clearing; adaptive pixel grid"]],
            [8 * mm, 20 * mm, 88 * mm, FULL - 116 * mm])]

# ---------------- 5 Verification
s += [PageBreak(), Paragraph("5. Verification", H1),
      Paragraph("5.1 Automated", H2),
      table([["Check", "Result"],
             ["scripts/run_tests.sh (0.5.3)", "96 pure-Python tests and 105 QGIS-runtime tests, 0 failed (1 keychain test skipped headless). New suites: tests/test_preflight.py and DialogLiveFlowTests, which drives the real dialog against a scripted local HTTP server that plays the FortyGuard API (Stop during submit, cut-off bodies, 404 on resume, Check Again across requests, cancelled confirmations, restyle after layer removal)."],
             ["Security scan", "Bandit clean (the same scan plugins.qgis.org runs); scripts/package.sh refuses to build otherwise."],
             ["Repository validator", "scripts/validate_package.py: PASS for fortyguard_heatmap-0.5.3.zip (metadata, URLs, structure)."],
             ["Dialog at narrow widths", "Rendered offscreen at 560 px and 680 px: all rows wrap, nothing cropped."]],
            [42 * mm, FULL - 42 * mm], style=P),
      Paragraph("5.2 On the production API (20 October 2026, Hackathon key shared with the team)", H2),
      table([["Check", "Result"],
             ["Request for yesterday (free)", "HTTP 400 classified as no_data: \"no temperature data yet ... choose dates ending on or before 2026-10-13 ... Nothing was charged\"."],
             ["1 July to 1 August", "Blocked locally before submission with the day count and the Calendar month hint."],
             ["Full dialog run with the default date (today - 7), twice", "Both completed (activities b291e768, c2a98efa): 150 tiles, layers added, files saved without the key, project reopened. The confirmation showed the plan-specific cost and \"inside documented coverage\"."],
             ["Credits display", "8,538,680 before the second run, 8,534,460 after: exactly 4,220, while the frozen cycle figure stayed at 9,341,680 (the value the testers saw)."],
             ["San Jose, 4 km square, 60 m, 15-21 July 2024", "Completed: 4,290 tiles; used for the review screenshots (section 6)."],
             ["Cost of the verification", "3 completed requests x 4,220 = 12,660 credits."]],
            [42 * mm, FULL - 42 * mm], style=P),
      Spacer(1, 4 * mm),
      fig("12_dialog_after_production_run.png", "Figure 1. The plugin dialog after a completed production request with the default date (QGIS 3.44.15, macOS): "
          "live credits, coverage status in the selected-feature line, activity ID, statistics with the data spread.", max_h=120 * mm)]

# ---------------- 6 Screenshots
s += [PageBreak(), Paragraph("6. Review screenshots requested after the first report", H1),
      Paragraph("The report review asked for a better heatmap: more granular, smooth, more classes, a larger area and time frame, "
                "in San Jose. The request below was made through the plugin's own code against the production API: downtown San "
                "Jose, a 4 km by 4 km square aligned to the UTM grid (16 km2, about 6.2 mi2), 60 m resolution, 15 to 21 July 2024 "
                "(a seven-day window), 4,290 tiles.", P),
      fig("09_tiles_12_classes_san_jose.png", "Figure 2. Mean temperature of the week, exact API tiles with 12 legend classes over OpenStreetMap, inside the QGIS window.", max_h=84 * mm),
      fig("10_smooth_surface_san_jose_max.png", "Figure 3. Maximum temperature of the week as the smooth surface (interpolated estimate; the tiles layer is kept underneath). "
          "The legend heading names the quantity and unit.", max_h=84 * mm)]

# ---------------- 7 Releases and next steps
s += [PageBreak(), Paragraph("7. Releases, evidence and next steps", H1),
      table([["Version", "Date", "Content", "Link"],
             ["0.5.0", "20 Oct 2026", "Round-one fixes (26 issues); no longer experimental", "github.com/FortyGuard-Tech/qgis-fortyguard-heatmap/releases/tag/v0.5.0"],
             ["0.5.1", "20 Oct 2026", "Legend classes option (report review)", ".../releases/tag/v0.5.1"],
             ["0.5.2", "20 Oct 2026", "Round-two fixes (Windows)", ".../releases/tag/v0.5.2"],
             ["0.5.3", "20 Oct 2026", "Independent code review fixes; version to publish", ".../releases/tag/v0.5.3"]],
            [16 * mm, 22 * mm, 60 * mm, FULL - 98 * mm]),
      Spacer(1, 4 * mm),
      Paragraph("Evidence in the repository", H2)]
s += bullets([
    "docs/TEST_REPORT.md, sections 0 to 0d: issue / root cause / fix / test tables for every row, and the production verification log.",
    "docs/API_CONTRACT.md, \"Observed behaviour\": the API facts behind the fixes, for the API team.",
    "CHANGELOG.md: per-version notes. tests/: 201 automated tests. dist/live_dialog_report.json: the step-by-step record of the production dialog run.",
    "docs/report/images/: the review screenshots (Phoenix and San Jose, 12 classes, smooth surface, zoom, full-contrast comparison)."])
s += [Paragraph("Next steps", H2)]
s += bullets([
    "Publish 0.5.3 on plugins.qgis.org (Add version) and ask the team to re-test on the published build.",
    "Fawad to re-confirm the time-zone helper text (inputs are the area's local time; peak hours are UTC).",
    "API team: confirm which usage field is authoritative for the balance, and whether the 7-day data latency and the flat 4,220-credit charge for empty results are intended.",
    "QGIS 4 (Qt 6) remains untested."])

doc.build(s, onFirstPage=footer, onLaterPages=footer)
print("built", OUT)
