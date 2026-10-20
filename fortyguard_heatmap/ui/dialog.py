# -*- coding: utf-8 -*-
"""FortyGuard Temperature Intelligence Layer dialog (built in code; no generated ui_*.py files).

The dialog owns no network logic. It collects input, calls the core modules,
drives a HeatmapJob and reflects its signals. Everything runs on the main thread.
The API key lives in the password field only, unless the user explicitly saves it
to the QGIS authentication store.
"""
import contextlib
import datetime as _dt
import os

from qgis.PyQt.QtCore import QDate, QTime, Qt
from qgis.PyQt.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QTimeEdit, QVBoxLayout, QWidget,
)
from qgis.PyQt.QtGui import QStandardItemModel
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsMapLayerProxyModel,
    QgsMessageLog, QgsProject, QgsSettings, QgsVectorLayer, Qgis,
)
from qgis.gui import QgsCollapsibleGroupBox, QgsFileWidget, QgsMapLayerComboBox

from ..core import contract, credentials, demo, geometry, output, payload, preflight, responses, styling, surface
from ..core.api_client import HeatmapApiClient
from ..core.demo import DemoApiClient
from ..core.job import HeatmapJob
from ..core.payload import ValidationError
from ..core.responses import ApiError

LOG_TAG = "FortyGuard Temperature Intelligence Layer"
SETTING_MEASURE = "fortyguard_heatmap/preferred_measure"
SETTING_DEADLINE = "fortyguard_heatmap/deadline_minutes"
SETTING_APPEARANCE = "fortyguard_heatmap/appearance"
# Analysis settings restored on the next start (dates are deliberately not saved: they are relative to today).
SETTING_ANALYSIS = "fortyguard_heatmap/analysis_type"
SETTING_FILTER = "fortyguard_heatmap/filter_type"
SETTING_THRESHOLD = "fortyguard_heatmap/threshold_c"
SETTING_GRANULARITY = "fortyguard_heatmap/granularity_m"
SETTING_START_TIME = "fortyguard_heatmap/start_time"
SETTING_END_TIME = "fortyguard_heatmap/end_time"
SETTING_CLASSES = "fortyguard_heatmap/legend_classes"
DEFAULT_CLASSES = 10          # legend classes for the tiles layer (3-20); more classes show finer differences
MIN_CLASSES, MAX_CLASSES = 3, 20
APPEARANCE_TILES = "tiles"
APPEARANCE_SMOOTH = "smooth"
FILTER_MONTH = "month"  # UI-only choice; submitted as filter_type 4 with the month's first/last dates

MEASURE_CHOICES = (
    (contract.FIELD_AVERAGE, "Mean (average_temperature)"),
    (contract.FIELD_MIN, "Minimum (min_temperature)"),
    (contract.FIELD_MAX, "Maximum (max_temperature)"),
)

GETTING_STARTED = (
    "<b>Getting started</b><br>"
    "1. Paste your own FortyGuard API key below (available at "
    "<a href='" + contract.URL_API_PLANS + "'>fortyguard.com/api-pricing</a>).<br>"
    "2. Click <i>Check key and credits</i>.<br>"
    "3. Pick exactly one polygon on the map (United States coverage).<br>"
    "4. Choose the analysis, date/time and resolution, then <i>Generate Heatmap</i>.<br>"
    "Each completed request consumes credits of your plan. Data for the most recent days (about the last %d) "
    "is usually not available yet.<br>"
    "Docs: <a href='" + contract.URL_DOCS + "'>API introduction</a> · "
    "<a href='" + contract.URL_DOCS_HEATMAP + "'>Create Heatmap</a> · "
    "<a href='" + contract.URL_DOCS_AUTH + "'>Authentication</a> · "
    "<a href='" + contract.URL_DOCS_LIMITS + "'>Limits</a> · "
    "<a href='" + contract.URL_DOCS_CREDITS + "'>Credits usage</a> · "
    "<a href='" + contract.URL_CONTACT + "'>Contact FortyGuard</a>"
) % contract.DATA_LATENCY_DAYS


def saved_output_dir():
    """Saved output folder if it still exists, otherwise the user-friendly default."""
    value = QgsSettings().value(output.OUTPUT_DIR_SETTING, "")
    if isinstance(value, str) and value and os.path.isdir(value):
        return value
    return output.default_output_dir()


def default_dates(today=None):
    """(start, end) QDate defaults: the latest day that normally has data, and a 7-day range before it."""
    today = today or QDate.currentDate()
    end = today.addDays(-contract.DATA_LATENCY_DAYS)
    return end.addDays(-6), end


def _form(parent):
    """QFormLayout that wraps long rows instead of clipping them at narrow widths."""
    f = QFormLayout(parent)
    f.setRowWrapPolicy(QFormLayout.WrapLongRows)
    f.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
    return f


def _wrapping_label(text=""):
    """Label that takes the available width and wraps instead of forcing the dialog wider."""
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    label.setMinimumWidth(1)
    return label


def _shrinkable(combo, chars=18):
    """Let a combo box shrink below the width of its longest item (the popup still shows full text)."""
    combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(chars)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    return combo


class HeatmapDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or (iface.mainWindow() if iface else None))
        self.iface = iface
        self.setWindowTitle("FortyGuard Temperature Intelligence Layer")
        self.setMinimumSize(520, 480)
        self.resize(680, 720)  # fits a 13-inch laptop screen; the settings part scrolls
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint)

        self.job = None
        self.client = None
        self.usage_client = None
        self.last_usage = None
        self.last_layer = None
        self.last_map_data = None
        self.last_stats = None
        self.last_request_summary = ""
        self.last_demo = False
        self.last_activity_id = ""
        self.last_analytic_type = contract.ANALYTIC_TYPE_TCM
        self.last_threshold = None
        self.last_aoi_polygon = None
        self.last_surface_layer = None
        self.last_fingerprint = None
        self._completed_requests = {}      # fingerprint -> (activity_id, path, when) for this session
        self._unfinished_activity = None    # activity id whose outcome is unknown (stopped / timed out)
        self._session_activities = []       # (activity_id, request summary) of every submission this session
        self._foreign_activity = False      # Check Again on an ID not submitted in this session
        self._last_status_key = None
        self._status_repeats = 0
        self._connected_layer = None

        self._build_ui()
        self._wire()
        self._restore_settings()
        self._on_analysis_changed()
        self._on_filter_changed()
        self._on_demo_toggled(self.demo_check.isChecked())
        self._refresh_selection_info()
        self._set_busy(False)

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        # All settings live in a scrollable area; the request buttons and status stay pinned below.
        content = QWidget()
        root = QVBoxLayout(content)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # content fits the width; long rows wrap
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        intro = QLabel(GETTING_STARTED)
        intro.setWordWrap(True)
        intro.setOpenExternalLinks(True)
        intro.setTextInteractionFlags(Qt.TextBrowserInteraction)
        intro.setStyleSheet("background: #eef5fb; color: #15232e; border: 1px solid #c9dcec; border-radius: 4px; "
                            "padding: 6px;")  # explicit text colour so it stays readable in dark themes
        root.addWidget(intro)

        # --- API key
        conn = QGroupBox("Your FortyGuard API key")
        f = _form(conn)
        key_row = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("Paste your API key (kept in memory only)")
        self.key_edit.setMinimumWidth(120)
        self.show_key_check = QCheckBox("Show")
        key_row.addWidget(self.key_edit, 1)
        key_row.addWidget(self.show_key_check)
        f.addRow("API key", key_row)
        check_row = QHBoxLayout()
        self.check_key_btn = QPushButton("Check key and credits")
        check_row.addWidget(self.check_key_btn)
        check_row.addStretch(1)
        f.addRow("", check_row)
        self.usage_label = _wrapping_label("Not checked yet.")
        f.addRow("Plan / credits", self.usage_label)

        store_row = QHBoxLayout()
        self.load_key_btn = QPushButton("Load key")
        self.load_key_btn.setToolTip("Restore the key saved in the encrypted QGIS authentication store.")
        self.save_key_btn = QPushButton("Save key (encrypted)")
        self.save_key_btn.setToolTip("Store the key in the encrypted QGIS authentication store (master password).")
        self.forget_key_btn = QPushButton("Forget key")
        self.forget_key_btn.setToolTip("Remove the saved key from the QGIS authentication store.")
        for b in (self.load_key_btn, self.save_key_btn, self.forget_key_btn):
            store_row.addWidget(b)
        store_row.addStretch(1)
        f.addRow("QGIS auth store", store_row)
        store_hint = QLabel("Saving uses the encrypted QGIS Authentication database (master password). "
                            "Nothing else stores the key.")
        store_hint.setWordWrap(True)
        store_hint.setStyleSheet("color: #555; font-size: 11px;")
        f.addRow("", store_hint)

        self.demo_check = QCheckBox("Demo Mode (offline SYNTHETIC data, no API call)")
        self.demo_check.setToolTip("Optional. Replays bundled synthetic data so you can try the plugin without a key.")
        self.demo_check.setStyleSheet("font-weight: bold;")
        f.addRow("", self.demo_check)
        root.addWidget(conn)

        # --- Area
        area = QGroupBox("Area of interest")
        f = _form(area)
        self.layer_combo = _shrinkable(QgsMapLayerComboBox())
        self.layer_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.layer_combo.setAllowEmptyLayer(True)
        f.addRow("Polygon layer", self.layer_combo)
        self.selection_label = _wrapping_label("-")
        f.addRow("Selected feature", self.selection_label)
        self.demo_aoi_btn = QPushButton("Add demo AOI layer (synthetic test area, USA)")
        self.demo_aoi_btn.setToolTip("Adds a small synthetic polygon in EPSG:3857 over lower Manhattan and selects it.")
        f.addRow("", self.demo_aoi_btn)
        root.addWidget(area)

        # --- Analysis
        ana = QGroupBox("Analysis")
        f = _form(ana)
        self.analysis_combo = _shrinkable(QComboBox())
        for at in contract.ANALYTIC_TYPES:
            self.analysis_combo.addItem(contract.ANALYSIS_LABELS[at], at)
        f.addRow("Analysis type", self.analysis_combo)
        self.analysis_help = QLabel("")
        self.analysis_help.setWordWrap(True)
        self.analysis_help.setStyleSheet("color: #555;")
        f.addRow("", self.analysis_help)
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(contract.THRESHOLD_MIN_C, contract.THRESHOLD_MAX_C)
        self.threshold_spin.setDecimals(1)
        self.threshold_spin.setSingleStep(0.5)
        self.threshold_spin.setSuffix(" °C")
        self.threshold_spin.setValue(contract.DEFAULT_THRESHOLD_C)
        self.threshold_label = QLabel("Threshold (°C)")
        f.addRow(self.threshold_label, self.threshold_spin)
        self.threshold_help = QLabel(
            "Exceedance = total hours above the threshold in the period (hours may be spread out). "
            "Persistence = the longest unbroken run of hours above it. Both are sent with direction 'above'.")
        self.threshold_help.setWordWrap(True)
        self.threshold_help.setStyleSheet("color: #555; font-size: 11px;")
        f.addRow("", self.threshold_help)
        root.addWidget(ana)

        # --- Date/time
        when = QGroupBox("Date and time")
        f = _form(when)
        self.filter_combo = _shrinkable(QComboBox())
        for ft in (contract.FILTER_SINGLE_HOUR, contract.FILTER_RANGE_OF_HOURS,
                   contract.FILTER_SINGLE_DAY, contract.FILTER_RANGE_OF_DAYS):
            self.filter_combo.addItem(contract.FILTER_TYPE_LABELS[ft], ft)
        self.filter_combo.addItem("Calendar month (whole month, submitted as a range of days)", FILTER_MONTH)
        self.filter_combo.setCurrentIndex(2)  # single day: the schema verified live
        f.addRow("Filter type", self.filter_combo)

        min_date = QDate.fromString(contract.MIN_DATE_ISO, "yyyy-MM-dd")
        max_date = QDate.currentDate().addDays(1)   # documented limit (now + 12 h); the API is the authority
        default_start, default_end = default_dates()

        self.month_edit = QDateEdit()
        self.month_edit.setCalendarPopup(True)
        self.month_edit.setDisplayFormat("MMMM yyyy")
        self.month_edit.setMinimumDate(min_date)
        self.month_edit.setMaximumDate(max_date)
        self.month_edit.setDate(QDate(default_end.year(), default_end.month(), 1).addMonths(-1))
        self.month_label = QLabel("Month")
        f.addRow(self.month_label, self.month_edit)

        self.start_date = QDateEdit()
        self.start_date.setCalendarPopup(True)
        self.start_date.setDisplayFormat("yyyy-MM-dd")
        self.start_date.setMinimumDate(min_date)
        self.start_date.setMaximumDate(max_date)
        self.start_date.setDate(default_end)
        self.start_date_label = QLabel("Start date")
        f.addRow(self.start_date_label, self.start_date)

        self.start_time = QTimeEdit()
        self.start_time.setDisplayFormat("HH:mm")
        self.start_time.setTime(QTime(14, 0))
        self.start_time_label = QLabel("Start time")
        f.addRow(self.start_time_label, self.start_time)

        self.end_time = QTimeEdit()
        self.end_time.setDisplayFormat("HH:mm")
        self.end_time.setTime(QTime(17, 0))
        self.end_time_label = QLabel("End time")
        f.addRow(self.end_time_label, self.end_time)

        self.end_date = QDateEdit()
        self.end_date.setCalendarPopup(True)
        self.end_date.setDisplayFormat("yyyy-MM-dd")
        self.end_date.setMinimumDate(min_date)
        self.end_date.setMaximumDate(max_date)
        self.end_date.setDate(default_end)
        self.end_date_label = QLabel("End date")
        f.addRow(self.end_date_label, self.end_date)

        tz = QLabel("Start/end times are the local time of the selected area (confirmed by FortyGuard). "
                    "Peak temperature time results are reported in UTC. Dates default to %d days ago: FortyGuard data "
                    "for the most recent days is usually not available yet (the API then answers 'Temperature data is "
                    "unavailable', free of charge)." % contract.DATA_LATENCY_DAYS)
        tz.setWordWrap(True)
        tz.setStyleSheet("color: #555; font-size: 11px;")
        f.addRow("", tz)
        root.addWidget(when)

        # --- Output options
        opts = QGroupBox("Output")
        f = _form(opts)
        self.granularity_combo = _shrinkable(QComboBox(), 8)
        for g in contract.GRANULARITY_OPTIONS:
            self.granularity_combo.addItem("%d m" % g, g)
        self.granularity_combo.setCurrentIndex(self.granularity_combo.findData(contract.DEFAULT_GRANULARITY))
        f.addRow("Resolution", self.granularity_combo)

        self.measure_combo = _shrinkable(QComboBox())
        for field, label in MEASURE_CHOICES:
            self.measure_combo.addItem(label, field)
        saved = QgsSettings().value(SETTING_MEASURE, contract.FIELD_AVERAGE)
        idx = self.measure_combo.findData(saved)
        self.measure_combo.setCurrentIndex(idx if idx >= 0 else 0)
        measure_row = QHBoxLayout()
        measure_row.addWidget(self.measure_combo, 1)
        self.restyle_btn = QPushButton("Restyle last layer")
        measure_row.addWidget(self.restyle_btn)
        f.addRow("Measure (daily outputs)", measure_row)

        self.appearance_combo = _shrinkable(QComboBox())
        self.appearance_combo.addItem("Smooth surface (interpolated estimate) + exact tiles layer hidden", APPEARANCE_SMOOTH)
        self.appearance_combo.addItem("Tiles only (exact API values per tile)", APPEARANCE_TILES)
        saved_app = QgsSettings().value(SETTING_APPEARANCE, APPEARANCE_SMOOTH)
        self.appearance_combo.setCurrentIndex(max(0, self.appearance_combo.findData(saved_app)))
        self.appearance_combo.setToolTip("Smooth surface paints the same API tiles onto a fine pixel grid, blurs them and "
                                         "clips to your area. Values between tile centres are estimates; the tiles layer keeps "
                                         "the exact numbers. Not available for Peak temperature time (hours are cyclic).")
        f.addRow("Appearance", self.appearance_combo)

        self.classes_spin = QSpinBox()
        self.classes_spin.setRange(MIN_CLASSES, MAX_CLASSES)
        self.classes_spin.setValue(DEFAULT_CLASSES)
        self.classes_spin.setToolTip("Number of colour classes for the tiles layer (quantile classes for temperature, "
                                     "equal intervals for hours). More classes show finer differences; identical "
                                     "classes are merged automatically. Peak temperature time always uses six clock classes.")
        f.addRow("Legend classes", self.classes_spin)

        out_row = QHBoxLayout()
        self.output_dir = QgsFileWidget()
        self.output_dir.setStorageMode(QgsFileWidget.GetDirectory)
        self.output_dir.setFilePath(saved_output_dir())
        self.output_default_btn = QPushButton("Default")
        self.output_default_btn.setToolTip("Reset to " + output.default_output_dir())
        out_row.addWidget(self.output_dir, 1)
        out_row.addWidget(self.output_default_btn)
        f.addRow("Output folder", out_row)

        self.deadline_spin = QSpinBox()
        self.deadline_spin.setRange(1, 120)
        self.deadline_spin.setSuffix(" min")
        self.deadline_spin.setValue(int(QgsSettings().value(SETTING_DEADLINE, contract.POLL_DEFAULT_DEADLINE_S // 60)))
        f.addRow("Max wait", self.deadline_spin)
        root.addWidget(opts)

        # --- Advanced settings (collapsed; not persisted)
        self.dev_group = QgsCollapsibleGroupBox("Advanced settings (leave collapsed for normal use)")
        self.dev_group.setCollapsed(True)
        f = _form(self.dev_group)
        self.skip_checks_check = QCheckBox("Skip the coverage, area and duplicate pre-checks")
        self.skip_checks_check.setToolTip("The pre-checks exist because the API charges for empty and never-finishing "
                                          "jobs. Only skip them if you know the request is valid.")
        f.addRow("", self.skip_checks_check)
        # The API environment selector is for FortyGuard developers only. The public build talks to
        # api.fortyguard.com; the selector appears only when FORTYGUARD_DEV_ENVIRONMENT=1 is set.
        self.base_url_combo = _shrinkable(QComboBox())
        for label, url in contract.BASE_URL_CHOICES:
            self.base_url_combo.addItem(label, url)
        self.base_url_combo.setCurrentIndex(0)  # always production
        self.base_url_combo.setToolTip("FortyGuard developers only. Keys are environment-specific: switching clears "
                                       "the key field; the choice is not remembered between sessions.")
        self.base_url_label = QLabel("API environment")
        f.addRow(self.base_url_label, self.base_url_combo)
        self.developer_mode = os.environ.get("FORTYGUARD_DEV_ENVIRONMENT", "") == "1"
        self.base_url_combo.setVisible(self.developer_mode)
        self.base_url_label.setVisible(self.developer_mode)
        root.addWidget(self.dev_group)

        root.addStretch(1)

        # --- Actions / status (pinned below the scroll area, always visible)
        act = QGroupBox("Request")
        v = QVBoxLayout(act)
        btns = QHBoxLayout()
        self.generate_btn = QPushButton("Generate Heatmap")
        self.generate_btn.setDefault(True)
        self.stop_btn = QPushButton("Stop Waiting")
        self.stop_btn.setToolTip("Stops polling locally only. The FortyGuard job keeps running on the server.")
        self.resume_btn = QPushButton("Check Again")
        self.resume_btn.setToolTip("Poll the activity ID shown below again, without a new submission. You can also "
                                   "paste the ID of an earlier request (see the log) to fetch its result.")
        btns.addWidget(self.generate_btn, 1)
        btns.addWidget(self.stop_btn)
        btns.addWidget(self.resume_btn)
        v.addLayout(btns)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(8)
        v.addWidget(self.progress)

        grid = QFormLayout()
        grid.setRowWrapPolicy(QFormLayout.WrapLongRows)
        grid.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.status_label = _wrapping_label("Idle")
        self.status_label.setStyleSheet("font-weight: bold;")
        grid.addRow("Status", self.status_label)
        self.activity_label = QLineEdit()
        self.activity_label.setPlaceholderText("(none yet - paste an earlier activity ID here and click Check Again)")
        self.activity_label.setToolTip("Filled in after each submission. Editable: paste the ID of an earlier request "
                                       "from the log to fetch its result without paying again.")
        grid.addRow("Activity ID", self.activity_label)
        self.stats_label = _wrapping_label("-")
        grid.addRow("Area statistics", self.stats_label)
        v.addLayout(grid)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(60)
        self.log.setMaximumHeight(110)
        self.log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        v.addWidget(self.log)
        outer.addWidget(act, 0)

        notice = QLabel(
            "Using this plugin requires a FortyGuard API key with an appropriate plan. A completed request consumes "
            "credits (documented: 3,500 per request on API Basic/Startup, 4,220 on API Premium; rejected and failed "
            "tasks are free, but a completed job with 0 tiles is charged). Documented coverage: United States only. "
            "Area caps: 10 mi² (Basic/Startup) or 50 mi² (Premium). tcm values are in °C. Support: %s"
            % contract.SUPPORT_EMAIL)
        notice.setWordWrap(True)
        notice.setStyleSheet("color: #555; font-size: 11px;")
        outer.addWidget(notice, 0)

    def _wire(self):
        self.show_key_check.toggled.connect(
            lambda on: self.key_edit.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        self.check_key_btn.clicked.connect(self._check_usage)
        self.load_key_btn.clicked.connect(self._load_key)
        self.save_key_btn.clicked.connect(self._save_key)
        self.forget_key_btn.clicked.connect(self._forget_key)
        self.demo_check.toggled.connect(self._on_demo_toggled)
        self.activity_label.textChanged.connect(lambda _t: self._set_busy(bool(self.job and self.job.is_active)))
        self.layer_combo.layerChanged.connect(self._on_layer_changed)
        self.demo_aoi_btn.clicked.connect(self._add_demo_aoi_layer)
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.analysis_combo.currentIndexChanged.connect(self._on_analysis_changed)
        self.generate_btn.clicked.connect(self._on_generate)
        self.stop_btn.clicked.connect(self._on_stop)
        self.resume_btn.clicked.connect(self._on_resume)
        self.restyle_btn.clicked.connect(self._on_restyle)
        self.output_default_btn.clicked.connect(lambda: self.output_dir.setFilePath(output.default_output_dir()))
        self.measure_combo.currentIndexChanged.connect(
            lambda _i: QgsSettings().setValue(SETTING_MEASURE, self.measure_combo.currentData()))
        self.deadline_spin.valueChanged.connect(lambda v: QgsSettings().setValue(SETTING_DEADLINE, v))
        self.appearance_combo.currentIndexChanged.connect(
            lambda _i: QgsSettings().setValue(SETTING_APPEARANCE, self.appearance_combo.currentData()))
        self.output_dir.fileChanged.connect(lambda p: QgsSettings().setValue(output.OUTPUT_DIR_SETTING, p))
        self.base_url_combo.currentIndexChanged.connect(self._on_environment_changed)
        # analysis settings remembered for the next session
        self.analysis_combo.currentIndexChanged.connect(
            lambda _i: QgsSettings().setValue(SETTING_ANALYSIS, self.analysis_combo.currentData()))
        self.filter_combo.currentIndexChanged.connect(
            lambda _i: QgsSettings().setValue(SETTING_FILTER, str(self.filter_combo.currentData())))
        self.threshold_spin.valueChanged.connect(lambda v: QgsSettings().setValue(SETTING_THRESHOLD, v))
        self.granularity_combo.currentIndexChanged.connect(
            lambda _i: QgsSettings().setValue(SETTING_GRANULARITY, self.granularity_combo.currentData()))
        self.classes_spin.valueChanged.connect(lambda v: QgsSettings().setValue(SETTING_CLASSES, v))
        self.start_time.timeChanged.connect(lambda t: QgsSettings().setValue(SETTING_START_TIME, t.toString("HH:mm")))
        self.end_time.timeChanged.connect(lambda t: QgsSettings().setValue(SETTING_END_TIME, t.toString("HH:mm")))
        self._on_layer_changed(self.layer_combo.currentLayer())

    def _restore_settings(self):
        """Restore the analysis settings of the previous session (dates stay relative to today)."""
        s = QgsSettings()
        at = s.value(SETTING_ANALYSIS, "")
        if self.analysis_combo.findData(at) >= 0:
            self.analysis_combo.setCurrentIndex(self.analysis_combo.findData(at))
        ft = s.value(SETTING_FILTER, "")
        for i in range(self.filter_combo.count()):
            if str(self.filter_combo.itemData(i)) == str(ft):
                self.filter_combo.setCurrentIndex(i)
                break
        with contextlib.suppress(TypeError, ValueError):
            thr = float(s.value(SETTING_THRESHOLD, contract.DEFAULT_THRESHOLD_C))
            if contract.THRESHOLD_MIN_C <= thr <= contract.THRESHOLD_MAX_C:
                self.threshold_spin.setValue(thr)
        with contextlib.suppress(TypeError, ValueError):
            g = int(s.value(SETTING_GRANULARITY, contract.DEFAULT_GRANULARITY))
            if self.granularity_combo.findData(g) >= 0:
                self.granularity_combo.setCurrentIndex(self.granularity_combo.findData(g))
        with contextlib.suppress(TypeError, ValueError):
            n = int(s.value(SETTING_CLASSES, DEFAULT_CLASSES))
            if MIN_CLASSES <= n <= MAX_CLASSES:
                self.classes_spin.setValue(n)
        for key, widget in ((SETTING_START_TIME, self.start_time), (SETTING_END_TIME, self.end_time)):
            t = QTime.fromString(str(s.value(key, "")), "HH:mm")
            if t.isValid():
                widget.setTime(t)

    # ----------------------------------------------------------- helpers

    @property
    def base_url(self):
        return self.base_url_combo.currentData()

    def log_line(self, text, level=Qgis.Info):
        stamp = _dt.datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText("[%s] %s" % (stamp, text))
        QgsMessageLog.logMessage(text, LOG_TAG, level)

    def _set_busy(self, busy):
        self.progress.setVisible(busy)
        self.generate_btn.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        can_resume = (not busy) and not self.demo_check.isChecked() and (
            bool(self.job and self.job.can_resume) or bool(self.activity_label.text().strip()))
        self.resume_btn.setEnabled(can_resume)
        for w in (self.key_edit, self.demo_check, self.layer_combo, self.filter_combo, self.start_date,
                  self.start_time, self.end_time, self.end_date, self.granularity_combo, self.output_dir,
                  self.output_default_btn, self.deadline_spin, self.load_key_btn, self.save_key_btn,
                  self.forget_key_btn, self.demo_aoi_btn, self.base_url_combo, self.check_key_btn,
                  self.analysis_combo, self.threshold_spin, self.month_edit, self.appearance_combo,
                  self.skip_checks_check, self.classes_spin):
            w.setEnabled(not busy)
        if not busy:
            self._on_demo_toggled(self.demo_check.isChecked())
        self.restyle_btn.setEnabled((not busy) and self.last_layer is not None)

    def _on_demo_toggled(self, on):
        self.key_edit.setEnabled(not on)
        self.check_key_btn.setEnabled(not on)
        for b in (self.load_key_btn, self.save_key_btn, self.forget_key_btn):
            b.setEnabled(not on and credentials.auth_available())
        self.generate_btn.setText("Generate DEMO Heatmap (synthetic)" if on else "Generate Heatmap")
        busy = bool(self.job and self.job.is_active)
        self.resume_btn.setEnabled((not busy) and (not on) and (
            bool(self.job and self.job.can_resume) or bool(self.activity_label.text().strip())))
        self.setWindowTitle("FortyGuard Temperature Intelligence Layer - DEMO MODE" if on else "FortyGuard Temperature Intelligence Layer")

    def _on_environment_changed(self, _index):
        # Never reuse a key across environments.
        if self.key_edit.text():
            self.key_edit.clear()
            self.log_line("API environment changed to %s; the key field was cleared (keys are environment-specific)."
                          % self.base_url, Qgis.Warning)
        else:
            self.log_line("API environment: %s" % self.base_url)
        self.usage_label.setText("Not checked yet.")
        self.last_usage = None

    @property
    def analytic_type(self):
        return self.analysis_combo.currentData()

    def _set_filter_item_enabled(self, filter_type, enabled):
        model = self.filter_combo.model()
        if isinstance(model, QStandardItemModel):
            item = model.item(self.filter_combo.findData(filter_type))
            if item is not None:
                item.setEnabled(enabled)

    def _on_analysis_changed(self, *_args):
        at = self.analytic_type
        self.analysis_help.setText(contract.ANALYSIS_EXPLANATIONS[at])
        needs_threshold = at in contract.THRESHOLD_TYPES
        self.threshold_spin.setVisible(needs_threshold)
        self.threshold_label.setVisible(needs_threshold)
        self.threshold_help.setVisible(needs_threshold)
        is_tcm = at == contract.ANALYTIC_TYPE_TCM
        self.measure_combo.setEnabled(is_tcm)
        # Single hour is only meaningful for the temperature snapshot (as in the Forma extension).
        self._set_filter_item_enabled(contract.FILTER_SINGLE_HOUR, is_tcm)
        if not is_tcm and self.filter_combo.currentData() == contract.FILTER_SINGLE_HOUR:
            self.filter_combo.setCurrentIndex(self.filter_combo.findData(contract.FILTER_SINGLE_DAY))
            msg = ("%s needs a time window, so the filter type was changed from 'Single hour' to 'Single day'."
                   % contract.ANALYSIS_LABELS[at])
            self.log_line(msg, Qgis.Warning)
            self.status_label.setText(msg)

    def _on_filter_changed(self):
        ft = self.filter_combo.currentData()
        show_start_time = ft in (contract.FILTER_SINGLE_HOUR, contract.FILTER_RANGE_OF_HOURS)
        show_end_time = ft == contract.FILTER_RANGE_OF_HOURS
        show_end_date = ft == contract.FILTER_RANGE_OF_DAYS
        show_month = ft == FILTER_MONTH
        self.start_time.setVisible(show_start_time); self.start_time_label.setVisible(show_start_time)
        self.end_time.setVisible(show_end_time); self.end_time_label.setVisible(show_end_time)
        self.end_date.setVisible(show_end_date); self.end_date_label.setVisible(show_end_date)
        self.month_edit.setVisible(show_month); self.month_label.setVisible(show_month)
        self.start_date.setVisible(not show_month); self.start_date_label.setVisible(not show_month)
        if show_end_date and self.end_date.date() <= self.start_date.date():
            # a sensible default window (7 days) instead of an invalid start = end pair
            self.start_date.setDate(self.end_date.date().addDays(-6))
        aggregate = ft in (contract.FILTER_SINGLE_DAY, contract.FILTER_RANGE_OF_DAYS, FILTER_MONTH)
        self.measure_combo.setToolTip("Used when the result contains average/min/max fields (daily outputs)."
                                      if aggregate else "Hourly outputs carry a single 'temperature' field; "
                                                        "this choice applies only to daily outputs.")

    def _on_layer_changed(self, layer):
        if self._connected_layer is not None:
            with contextlib.suppress(Exception):
                self._connected_layer.selectionChanged.disconnect(self._refresh_selection_info)
        self._connected_layer = layer
        if layer is not None:
            layer.selectionChanged.connect(self._refresh_selection_info)
        self._refresh_selection_info()

    def _refresh_selection_info(self, *_args):
        layer = self.layer_combo.currentLayer()
        if layer is None:
            self.selection_label.setText("Choose a polygon layer, then select exactly one feature on the map.")
            return
        try:
            info = geometry.prepare_aoi(layer)
        except ValidationError as exc:
            self.selection_label.setText("<span style='color:#a33'>%s</span>" % exc)
            return
        status, regions = preflight.coverage_status(info.geometry_geojson)
        if status == preflight.COVERAGE_INSIDE:
            cov = "inside documented coverage (%s)" % regions[0]
        elif status == preflight.COVERAGE_PARTIAL:
            cov = "<span style='color:#a33'>partly outside documented coverage (United States)</span>"
        else:
            cov = "<span style='color:#a33'>outside documented coverage (United States): the API would return 0 tiles and charge</span>"
        self.selection_label.setText(
            "Feature %s of '%s' | source CRS %s | ~%.2f km² (%.2f mi²) | sent as EPSG:4326 Polygon | %s"
            % (info.feature_id, info.layer_name, info.source_crs_authid, info.area_sq_km, info.area_sq_mi, cov))

    # ------------------------------------------------------- credentials

    def _current_key(self):
        return self.key_edit.text().strip()

    def _load_key(self):
        key = credentials.load_key()
        if key:
            self.key_edit.setText(key)
            self.log_line("Loaded the API key from the QGIS authentication store (%s)." % credentials.mask(key))
        else:
            self.log_line("No saved key found (or the master password was not provided).", Qgis.Warning)

    def _save_key(self):
        key = self._current_key()
        if not key:
            QMessageBox.information(self, "Save key", "Enter an API key first.")
            return
        if credentials.store_key(key):
            self.log_line("API key saved in the encrypted QGIS authentication store.")
        else:
            self.log_line("Could not save the key (authentication manager unavailable or master password cancelled).",
                          Qgis.Warning)

    def _forget_key(self):
        if credentials.forget_key():
            self.log_line("Saved API key removed from the QGIS authentication store.")
        else:
            self.log_line("Could not remove the saved key.", Qgis.Warning)

    def _check_usage(self):
        key = self._current_key()
        if not key:
            self._show_error("Enter your FortyGuard API key first.")
            return
        self.check_key_btn.setEnabled(False)
        self.usage_label.setText("Checking...")
        self.usage_client = HeatmapApiClient(key, base_url=self.base_url, parent=self)
        self.log_line("Checking key and credits on %s (key %s)..." % (self.base_url, credentials.mask(key)))

        def _cb(info, error):
            self.check_key_btn.setEnabled(not self.demo_check.isChecked())
            if error is not None:
                self.last_usage = None
                self.usage_label.setText("<span style='color:#a33'>%s</span>" % error.user_message())
                self.log_line("Key/credits check failed [%s]: %s" % (error.kind, error.user_message()), Qgis.Warning)
                return
            self.last_usage = info
            text = info.summary()
            if info.remaining_credits is not None and info.remaining_credits < contract.CREDITS_PER_REQUEST_OBSERVED:
                text += " - WARNING: fewer credits than one heatmap request may need."
            self.usage_label.setText(text)
            self.log_line("Key OK. " + text)

        self.usage_client.fetch_usage(_cb)

    # --------------------------------------------------------------- demo

    def _add_demo_aoi_layer(self):
        feat_gj = demo.load_demo_aoi()
        geom = QgsGeometry.fromWkt(geometry._polygon_wkt(feat_gj["geometry"]))
        xform = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:4326"),
                                       QgsCoordinateReferenceSystem("EPSG:3857"), QgsProject.instance())
        geom.transform(xform)
        layer = QgsVectorLayer("Polygon?crs=EPSG:3857&field=name:string(80)&field=demo:boolean",
                               "Demo AOI (synthetic test area)", "memory")
        f = QgsFeature(layer.fields())
        f.setAttributes([feat_gj["properties"].get("name", "Demo AOI"), True])
        f.setGeometry(geom)
        layer.dataProvider().addFeatures([f])
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        layer.selectAll()
        self.layer_combo.setLayer(layer)
        if self.iface:
            self.iface.mapCanvas().setExtent(self.iface.mapCanvas().mapSettings().layerExtentToOutputExtent(layer, layer.extent()))
            self.iface.mapCanvas().refresh()
        self.log_line("Added the synthetic demo AOI layer (EPSG:3857) and selected its feature.")

    # -------------------------------------------------------------- run

    def _collect_inputs(self):
        """Validate UI input and return (payload, aoi_info, notes). Raises ValidationError."""
        layer = self.layer_combo.currentLayer()
        aoi = geometry.prepare_aoi(layer)
        ft = self.filter_combo.currentData()
        start_date = self.start_date.date().toString("yyyy-MM-dd")
        end_date = self.end_date.date().toString("yyyy-MM-dd")
        notes = []
        if ft == FILTER_MONTH:
            y, m = self.month_edit.date().year(), self.month_edit.date().month()
            start_date, end_date = payload.month_range(y, m)
            if payload.month_was_clipped(y, m, start_date, end_date):
                notes.append("%s is not complete yet: the request covers %s to %s (data for more recent days is not "
                             "available yet)." % (self.month_edit.date().toString("MMMM yyyy"), start_date, end_date))
            ft = contract.FILTER_RANGE_OF_DAYS
        at = self.analytic_type
        body = payload.build_payload(
            aoi.geometry_geojson, ft, start_date,
            self.granularity_combo.currentData(),
            start_time=self.start_time.time().toString("HH:mm"),
            end_time=self.end_time.time().toString("HH:mm"),
            end_date=end_date,
            analytic_type=at,
            threshold=self.threshold_spin.value() if at in contract.THRESHOLD_TYPES else None,
            direction=contract.DIRECTION_ABOVE if at in contract.THRESHOLD_TYPES else None,
        )
        output.ensure_dir(self.output_dir.filePath())
        return body, aoi, notes

    def _preflight(self, body, aoi):
        """Client-side checks before a paid request. Returns (block_reason or None, [warnings])."""
        warnings = []
        if self.skip_checks_check.isChecked():
            return None, ["Pre-checks skipped (Developer settings)."]
        status, regions = preflight.coverage_status(aoi.geometry_geojson)
        if status == preflight.COVERAGE_OUTSIDE:
            return ("The area lies outside the documented FortyGuard coverage (United States). In testing such requests "
                    "completed with 0 tiles and were still charged. Choose an area in the United States (or tick "
                    "'Skip the pre-checks' in Developer settings if coverage has been extended)."), warnings
        if status == preflight.COVERAGE_PARTIAL:
            warnings.append("Part of the area lies outside the documented coverage (United States; it touches %s). "
                            "Tiles outside the coverage will be missing but the request is charged in full."
                            % ", ".join(regions))
        area = preflight.area_assessment(aoi.area_sq_km, body["granularity"],
                                         plan_type=self.last_usage.plan_type if self.last_usage else None)
        if area["block"]:
            return area["block"], warnings
        warnings.extend(area["warnings"])
        dt = body["date_time"]
        recent = payload.recent_data_warning(dt["start_date"], dt.get("end_date"))
        if recent:
            warnings.append(recent)
        previous = self._previous_identical(body)
        if previous:
            warnings.append(previous)
        return None, warnings

    def _previous_identical(self, body):
        """Text describing an identical completed request from this session or the output folder, or None."""
        fp = preflight.request_fingerprint(body, self.base_url)
        hit = self._completed_requests.get(fp)
        if hit:
            activity_id, path, when = hit
            return ("An identical request was already completed in this session (%s, activity %s, saved as %s). "
                    "Submitting it again is charged again and returns the same tiles."
                    % (when.strftime("%H:%M"), activity_id, os.path.basename(path or "-")))
        meta = output.find_previous_result(self.output_dir.filePath(), fp)
        if meta:
            return ("An identical request was already completed on %s (activity %s, file %s in the output folder). "
                    "Submitting it again is charged again and returns the same tiles. You can load that file instead."
                    % (meta.get("saved_at", "?"), meta.get("activity_id", "?"), os.path.basename(meta["path"])))
        return None

    def _on_generate(self):
        if self.job is not None and self.job.is_active:
            return
        demo_mode = self.demo_check.isChecked()
        try:
            body, aoi, notes = self._collect_inputs()
        except (ValidationError, ApiError) as exc:
            self._show_error(str(exc))
            return
        for note in notes:
            self.log_line(note, Qgis.Warning)

        self.last_request_summary = payload.describe_request(body)
        self.last_aoi_polygon = aoi.geometry_geojson
        self.last_analytic_type = body["analytic_type"]
        self.last_threshold = body.get("threshold")
        self.last_demo = demo_mode
        self.last_fingerprint = preflight.request_fingerprint(body, self.base_url)
        analysis_label = "%s (%s)" % (contract.ANALYSIS_LABELS[self.last_analytic_type],
                                      output.unit_label(self.last_analytic_type))

        if demo_mode:
            fixture = demo.fixture_for_request(body["analytic_type"], body["date_time"]["filter_type"])
            self.client = DemoApiClient(fixture, parent=self)
            self.log_line("DEMO MODE: %s - replaying synthetic fixture '%s'. No request is sent to FortyGuard."
                          % (analysis_label, fixture))
        else:
            key = self._current_key()
            if not key:
                self._show_error("Enter your FortyGuard API key (or enable Demo Mode for an offline test).")
                return
            block, warnings = self._preflight(body, aoi)
            if block:
                self._show_error(block)
                return
            if self._unfinished_activity and not self.skip_checks_check.isChecked():
                warnings.append("The previous request (activity %s) was stopped or timed out before its result was "
                                "seen; it may have completed and been charged. Use 'Check Again' to fetch it before "
                                "paying for a new one." % self._unfinished_activity)
            base_url = self.base_url
            cost = preflight.expected_cost_text(self.last_usage.plan_type if self.last_usage else None,
                                                self.last_usage.remaining_credits if self.last_usage else None)
            msg = ("Submit a live FortyGuard request?\n\n"
                   "Environment: %s\n"
                   "Analysis: %s\n"
                   "Area: feature %s of '%s' (~%.2f km² / %.2f mi²)\n"
                   "Request: %s (filter type %d)\n\n%s\n"
                   % (base_url, analysis_label, aoi.feature_id, aoi.layer_name, aoi.area_sq_km, aoi.area_sq_mi,
                      self.last_request_summary, body["date_time"]["filter_type"], cost))
            if notes:
                msg += "\n" + "\n".join(notes) + "\n"
            if warnings:
                msg += "\nWARNINGS:\n" + "\n".join("- " + w for w in warnings) + "\n"
                for w in warnings:
                    self.log_line("Pre-check warning: %s" % w, Qgis.Warning)
            msg += "\nContinue?"
            if self._confirm("Confirm live request", msg) is not True:
                self.log_line("Request cancelled by the user before submission (nothing sent).")
                return
            self.client = HeatmapApiClient(key, base_url=base_url, parent=self)
            self.log_line("Submitting live %s request to %s: %s (area ~%.2f km², source CRS %s, key %s)."
                          % (analysis_label, base_url, self.last_request_summary, aoi.area_sq_km,
                             aoi.source_crs_authid, credentials.mask(key)))

        self.last_map_data = None
        self.last_stats = None
        self.stats_label.setText("-")
        self.activity_label.setText("")
        self._start_job(body)

    def _confirm(self, title, text):
        return QMessageBox.question(self, title, text, QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def _new_job(self):
        self._dispose_job()
        self.job = HeatmapJob(self.client, deadline_s=self.deadline_spin.value() * 60, parent=self)
        self.job.submitted.connect(self._on_submitted)
        self.job.status_changed.connect(self._on_status)
        self.job.progress.connect(lambda m: self.status_label.setText(m))
        self.job.completed.connect(self._on_completed)
        self.job.failed.connect(self._on_failed)
        self.job.stopped.connect(self._on_stopped)
        self._last_status_key = None
        self._status_repeats = 0
        return self.job

    def _start_job(self, body):
        self._new_job()
        self._set_busy(True)
        self.status_label.setText("Submitting...")
        self.job.submit(body)

    def _dispose_job(self):
        if self.job is not None:
            with contextlib.suppress(Exception):
                self.job.abandon()
            self.job.deleteLater()
            self.job = None

    def _on_submitted(self, activity_id):
        self.last_activity_id = activity_id
        self.activity_label.setText(activity_id)
        if self.last_demo:
            self.log_line("Submitted (demo). activity_id = %s" % activity_id)
            return
        self._session_activities.append((activity_id, self.last_request_summary))
        self.log_line("Submitted. activity_id = %s (%s). Keep this ID: paste it into the Activity ID field and click "
                      "Check Again to fetch the result later." % (activity_id, self.last_request_summary))

    def _on_status(self, status, detail):
        key = (status, detail)
        elapsed = int(self.job.policy.elapsed_s) if self.job else 0
        if key == self._last_status_key:
            # same state as the previous check: update the status line in place, do not repeat the log line
            self._status_repeats += 1
            self.status_label.setText("%s - %s (check %d, %d s elapsed)" % (status, detail, self._status_repeats + 1, elapsed))
            return
        self._last_status_key = key
        self._status_repeats = 0
        self.status_label.setText("%s - %s" % (status, detail))
        self.log_line("Status: %s (%s)" % (status, detail))

    def _on_stop(self):
        if self.job is not None:
            if self.job._awaiting_submit and not self.last_demo:
                self.log_line("Stop requested while the request is being submitted; waiting for the activity ID so a "
                              "possibly paid job is not lost.", Qgis.Warning)
            self.job.stop()

    def _on_stopped(self, activity_id):
        self._set_busy(False)
        if self.last_demo:
            self.status_label.setText("Demo stopped")
            self.log_line("Demo replay stopped. No request was sent to FortyGuard and nothing was charged; "
                          "click Generate again to replay the synthetic data.")
            return
        if activity_id:
            self._unfinished_activity = activity_id
            self.status_label.setText("Stopped waiting (server job not cancelled)")
            self.log_line("Stopped waiting locally. The FortyGuard job %s may still complete on the server and be "
                          "charged. To fetch it later, paste this ID into the Activity ID field and click 'Check Again' "
                          "(no new charge), even after other requests." % activity_id, Qgis.Warning)
        else:
            self.status_label.setText("Stopped before submission")
            self.log_line("Stopped before any job was created; nothing was sent or charged.")

    def _on_resume(self):
        """Check Again: poll the job's activity, or any activity ID pasted into the field."""
        if self.job is not None and self.job.is_active:
            return
        typed = self.activity_label.text().strip()
        if self.demo_check.isChecked():
            self._show_error("Check Again polls the FortyGuard API; untick Demo Mode first.")
            return
        key = self._current_key()
        if not key:
            self._show_error("Enter your FortyGuard API key to check an activity.")
            return
        same_job = self.job is not None and self.job.can_resume and typed in ("", self.job.activity_id or "")
        if same_job and self.client is not None and getattr(self.client, "has_api_key", lambda: False)():
            self._foreign_activity = False
            self._set_busy(True)
            self.job.resume()
            return
        if not typed:
            self._show_error("Paste an activity ID into the Activity ID field first.")
            return
        # another (earlier) activity: build a fresh job on the current key and poll that ID
        known = dict(self._session_activities).get(typed)
        self.client = HeatmapApiClient(key, base_url=self.base_url, parent=self)
        self._foreign_activity = known is None
        self.last_demo = False
        self.last_request_summary = known or ("activity %s" % typed[:8])
        self.last_fingerprint = None
        self.last_aoi_polygon = None if known is None else self.last_aoi_polygon
        self.last_map_data = None
        self.last_stats = None
        self.stats_label.setText("-")
        self._new_job()
        self._set_busy(True)
        self.log_line("Checking activity %s on %s (no new submission, nothing charged)." % (typed, self.base_url))
        self.job.resume(typed)

    def _on_failed(self, message, kind):
        self._set_busy(False)
        self.status_label.setText("Failed (%s)" % kind)
        self.log_line("ERROR [%s]: %s" % (kind, message), Qgis.Critical)
        activity_id = self.job.activity_id if self.job else ""
        if kind == "auth":
            message += " Tip: use 'Check key and credits' to verify the key for the selected environment."
        if kind == "empty" and activity_id and not self.last_demo:
            self._completed_requests[self.last_fingerprint] = (activity_id, None, _dt.datetime.now())
            self._unfinished_activity = None
            with contextlib.suppress(ApiError, OSError):
                path = output.save_empty_record(self.output_dir.filePath(), self.job.last_stats, self.last_request_summary,
                                                activity_id, self.last_analytic_type, fingerprint=self.last_fingerprint,
                                                environment=self.base_url)
                self.log_line("A record of this charged activity was saved as %s" % path)
        elif kind in ("timeout", "server", "network", "rate_limited", "unknown") and activity_id and not self.last_demo:
            self._unfinished_activity = activity_id   # outcome unknown: the job may complete and be charged
        elif kind in ("no_data", "invalid_input", "failed") and not self.last_demo:
            self._unfinished_activity = None          # the API rejected or failed it: nothing to fetch later
        if self.iface:
            self.iface.messageBar().pushMessage("FortyGuard Temperature Intelligence Layer", message, level=Qgis.Critical, duration=15)

    def _on_completed(self, map_data, stats_data):
        self.last_map_data = map_data
        self.last_stats = stats_data
        if self._foreign_activity:
            # The request that created this activity is unknown: read the analysis type from the result itself.
            api_at = responses.analysis_stats(stats_data).get("analytic_type")
            if api_at in contract.ANALYTIC_TYPES:
                self.last_analytic_type = api_at
            elif responses.result_schema(map_data) == "value":
                self.last_analytic_type = contract.ANALYTIC_TYPE_EXCEEDANCE
                self.log_line("The result carries 'value' tiles but stats_data names no analysis type; styled as hours.",
                              Qgis.Warning)
            else:
                self.last_analytic_type = contract.ANALYTIC_TYPE_TCM
            self.last_threshold = None
        at = self.last_analytic_type
        unit_kind = contract.UNIT_KIND.get(at, "celsius")
        activity_id = self.job.activity_id if self.job else ""
        if not self.last_demo:
            self._unfinished_activity = None
        try:
            schema = responses.result_schema(map_data)
            if at == contract.ANALYTIC_TYPE_TCM:
                measures = responses.available_measures(map_data)
                if not measures:
                    raise ApiError("The temperature result has no numeric temperature field (%s). Nothing was styled."
                                   % ", ".join(contract.MEASURE_PRIORITY), kind="malformed")
                measure = self._choose_measure(measures)
            else:
                if schema != "value":
                    raise ApiError("The %s result does not use the expected 'value' field (detected schema: %s). "
                                   "Nothing was styled; the raw GeoJSON was still saved."
                                   % (contract.ANALYSIS_LABELS[at], schema or "no numeric field"), kind="malformed")
                measure = contract.FIELD_VALUE
                api_stats = responses.analysis_stats(stats_data)
                if api_stats.get("units") and api_stats["units"].lower() != "hour":
                    self.log_line("stats_data.units is '%s' (expected 'hour'); legend labels assume hours."
                                  % api_stats["units"], Qgis.Warning)
                if api_stats.get("analytic_type") and api_stats["analytic_type"] != at:
                    self.log_line("stats_data.analytic_type is '%s' but '%s' was requested."
                                  % (api_stats["analytic_type"], at), Qgis.Warning)
            gpath, mpath = output.save_result(self.output_dir.filePath(), map_data, stats_data,
                                              self.last_request_summary, activity_id, demo=self.last_demo,
                                              analytic_type=at, fingerprint=self.last_fingerprint,
                                              environment=None if self.last_demo else self.base_url)
            self.log_line("Saved result to %s" % gpath)
            if not self.last_demo and self.last_fingerprint:
                self._completed_requests[self.last_fingerprint] = (activity_id, gpath, _dt.datetime.now())
            name = output.layer_name(measure, self.last_request_summary, demo=self.last_demo, analytic_type=at)
            layer = output.load_layer(gpath, name, measure, self.last_request_summary, activity_id,
                                      demo=self.last_demo, analytic_type=at, threshold=self.last_threshold)
            n = styling.apply_analysis_style(layer, measure, unit_kind, classes=self.classes_spin.value())
            self.last_layer = layer
            summary = responses.numeric_summary(map_data, measure)
            self.log_line("Added layer '%s' (%d tiles, %d classes on '%s' in %s; %d tiles without a value)."
                          % (name, layer.featureCount(), n, measure, output.unit_label(at), summary["missing"]))
            self._add_smooth_surface(map_data, measure, unit_kind, gpath, name, layer, activity_id, at)
            self._show_stats(stats_data, measure, summary)
            self.status_label.setText("Completed - layer added" + (" (DEMO, synthetic)" if self.last_demo else ""))
            if self.iface:
                zoom_layer = self.last_surface_layer or layer
                self.iface.mapCanvas().setExtent(self.iface.mapCanvas().mapSettings().layerExtentToOutputExtent(zoom_layer, zoom_layer.extent()))
                self.iface.mapCanvas().refresh()
                self.iface.messageBar().pushMessage(
                    "FortyGuard Temperature Intelligence Layer",
                    ("DEMO layer added (synthetic data, not a FortyGuard analysis)." if self.last_demo
                     else "Heatmap layer added: %s" % name), level=Qgis.Success, duration=8)
        except ApiError as exc:
            self._show_error(str(exc))
        finally:
            self._set_busy(False)

    def _add_smooth_surface(self, map_data, measure, unit_kind, gpath, base_name, tiles_layer, activity_id, at):
        """Optional presentation layer: interpolated raster from the same tiles."""
        self.last_surface_layer = None
        if self.appearance_combo.currentData() != APPEARANCE_SMOOTH:
            return
        if not surface.supports_surface(at):
            self.log_line("Smooth surface skipped for %s: hour-of-day values are cyclic and cannot be averaged. "
                          "Showing tiles." % contract.ANALYSIS_LABELS[at], Qgis.Warning)
            return
        try:
            array, gt, st = surface.build_surface(map_data, measure, aoi_polygon=self.last_aoi_polygon)
            tif = surface.write_geotiff(surface.surface_path_for(gpath), array, gt,
                                        description=surface.band_description(at, measure))
            sname = output.surface_layer_name(base_name)
            rl = output.load_surface_layer(tif, sname, measure, self.last_request_summary, activity_id, demo=self.last_demo,
                                           analytic_type=at, threshold=self.last_threshold)
            styling.apply_surface_style(rl, unit_kind, st["min"], st["max"])
            lo, hi, widened = styling.surface_colour_span(unit_kind, st["min"], st["max"])
            # surface on top, tiles kept but hidden (exact values stay one click away)
            root = QgsProject.instance().layerTreeRoot()
            node = root.findLayer(tiles_layer.id())
            if node is not None:
                node.setItemVisibilityChecked(False)
            self.last_surface_layer = rl
            unit = output.unit_label(at)
            self.log_line("Added smooth surface '%s' (%d x %d pixels, %d valid; range %.2f to %.2f %s, spread %.2f). The tiles "
                          "layer was added hidden; presentation only, values between tile centres are estimates."
                          % (sname, st["cols"], st["rows"], st["valid_pixels"], st["min"], st["max"], unit, st["max"] - st["min"]))
            if widened:
                self.log_line("The colour scale spans %.2f to %.2f %s (a minimum of %g %s) so that the small spread of "
                              "%.2f %s is not shown as a strong hot/cold contrast."
                              % (lo, hi, unit, styling.MIN_SURFACE_SPAN.get(unit_kind, 0), unit, st["max"] - st["min"], unit))
        except (ApiError, Exception) as exc:  # a surface failure must never lose the tiles result
            self.log_line("Smooth surface could not be created (%s). The tiles layer is shown instead." % exc, Qgis.Warning)
            node = QgsProject.instance().layerTreeRoot().findLayer(tiles_layer.id())
            if node is not None:
                node.setItemVisibilityChecked(True)

    def _choose_measure(self, measures):
        if contract.FIELD_TEMPERATURE in measures:
            return contract.FIELD_TEMPERATURE
        preferred = self.measure_combo.currentData()
        if preferred in measures:
            return preferred
        self.log_line("Preferred measure '%s' is not in the result; using '%s'." % (preferred, measures[0]), Qgis.Warning)
        return measures[0]

    def _on_restyle(self):
        if self.last_layer is None or self.last_map_data is None:
            return
        if self.last_analytic_type != contract.ANALYTIC_TYPE_TCM:
            self.log_line("Restyle with another measure applies to temperature layers only.", Qgis.Warning)
            return
        try:
            if self.last_layer.id() not in QgsProject.instance().mapLayers():
                raise ApiError("The last layer is no longer in the project.", kind="malformed")
            measures = responses.available_measures(self.last_map_data)
            measure = self._choose_measure(measures)
            n = styling.apply_temperature_style(self.last_layer, measure, classes=self.classes_spin.value())
            self.last_layer.setName(output.layer_name(measure, self.last_request_summary, demo=self.last_demo))
            self.last_layer.setCustomProperty(output.PROP_MEASURE, measure)
            self._show_stats(self.last_stats, measure, responses.numeric_summary(self.last_map_data, measure))
            self.log_line("Restyled layer on '%s' (%d classes)." % (measure, n))
        except ApiError as exc:
            self._show_error(str(exc))

    def _show_stats(self, stats_data, measure, summary):
        parts = []
        at = self.last_analytic_type
        kind = contract.UNIT_KIND.get(at, "celsius")
        md = self.last_map_data or {"features": []}
        if kind == "celsius":
            ts = responses.temperature_stats(stats_data)
            if ts:
                parts.append("API stats_data (%s): min %.2f, max %.2f, mean %.2f%s" % (
                    contract.TCM_UNIT, ts.get("minimum", float("nan")), ts.get("maximum", float("nan")),
                    ts.get("mean", float("nan")),
                    (", sd %.2f" % ts["standard_deviation"]) if "standard_deviation" in ts else ""))
            if summary["count"]:
                parts.append("Measure '%s': %d valid tiles, range %.2f to %.2f %s (spread %.2f, mean %.2f); %d missing" % (
                    measure, summary["count"], summary["min"], summary["max"], contract.TCM_UNIT,
                    summary["max"] - summary["min"], summary["mean"], summary["missing"]))
                if summary["max"] == summary["min"]:
                    parts.append("All tiles share the same value; the legend shows a single class.")
        elif kind == "hours":
            d = responses.duration_summary(md, measure)
            api = responses.analysis_stats(stats_data)
            label = "above %g °C" % self.last_threshold if self.last_threshold is not None else "above threshold"
            if d["count"]:
                parts.append("%s: %d valid tiles; %.1f%% of valid tiles (%d) have more than 0 h %s; "
                             "maximum %.1f h%s; %d missing"
                             % (contract.ANALYSIS_LABELS[at], d["count"], d["positive_pct_of_valid_tiles"], d["positive"],
                                label, d["max"], " (longest continuous run)" if at == contract.ANALYTIC_TYPE_PERSISTENCE else "",
                                d["missing"]))
                if d["max"] == d["min"]:
                    parts.append("All tiles share the same value (%.1f h); the legend shows a single class." % d["max"])
            if api:
                parts.append("API stats_data: %s" % ", ".join(
                    "%s %s" % (k, ("%.2f" % v) if isinstance(v, float) else v)
                    for k, v in api.items() if k in ("n_cells", "min", "max", "mean", "units")))
        elif kind == "hour_of_day":
            pk = responses.peak_time_summary(md, measure)
            if pk["mode_hour"] is not None:
                parts.append("Peak temperature time: most common peak hour %s (%d of %d valid tiles, %.1f%%); "
                             "%d missing%s"
                             % (responses.format_hour_of_day(pk["mode_hour"]), pk["mode_count"], pk["count"],
                                100.0 * pk["mode_count"] / pk["count"], pk["missing"],
                                ("; %d out-of-range values" % pk["invalid"]) if pk["invalid"] else ""))
                parts.append("Peak hours are in %s (confirmed by FortyGuard); they are not converted to the area's local time."
                             % contract.PEAK_TIME_TZ)
            else:
                parts.append("Peak temperature time: no valid hour values.")
        if self.last_demo:
            parts.append("SYNTHETIC DEMO DATA - not a FortyGuard analysis.")
        self.stats_label.setText("\n".join(parts) if parts else "No statistics available.")

    def _show_error(self, text):
        self.log_line("ERROR: %s" % text, Qgis.Warning)
        QMessageBox.warning(self, "FortyGuard Temperature Intelligence Layer", text)

    # ------------------------------------------------------------ cleanup

    def shutdown(self):
        """Stop timers/replies and detach signals. Called by the plugin on unload."""
        self._dispose_job()
        for attr in ("client", "usage_client"):
            c = getattr(self, attr)
            if c is not None:
                with contextlib.suppress(Exception):
                    c.abort_all()
                setattr(self, attr, None)
        if self._connected_layer is not None:
            with contextlib.suppress(Exception):
                self._connected_layer.selectionChanged.disconnect(self._refresh_selection_info)
            self._connected_layer = None
        self.key_edit.clear()

    def closeEvent(self, event):
        # Closing the window hides it; an active job keeps running so the result can still be added.
        event.accept()
