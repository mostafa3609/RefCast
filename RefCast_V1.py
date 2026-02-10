import sys
import os
import time
import re
import base64
import subprocess
import glob
import shutil
from PySide2 import QtWidgets, QtCore, QtGui
import pymxs

rt = pymxs.runtime

# ==========================================
# ===== MAXSCRIPT FUNCTION INJECTION =======
# ==========================================
rt.execute("""
fn UPDATE_VISIBILITY_FN obj val = (
    if isValidNode obj do (
        if obj.visibility == undefined then (
            obj.visibility = Bezier_Float()
        )
        else (
            if (getPropertyController obj #visibility) == undefined do (
                obj.visibility = Bezier_Float()
            )
        )
        obj.visibility.controller.value = val
    )
)
""")
# ==========================================

# === PLUGIN INFO ===
PLUGIN_NAME = "RefCast"
PLUGIN_VERSION = "1.0"
PLUGIN_FULL = f"{PLUGIN_NAME} V{PLUGIN_VERSION}"
LAYER_NAME = "REFERENCES"

# === SUPPORT ===
SUPPORT_URL = "https://www.paypal.com/paypalme/jokerproduction"
SUPPORT_IMG_BASE64 = """iVBORw0KGgoAAAANSUhEUgAAAGAAAAAwCAYAAADuFn/PAAAAAXNSR0IArs4c6QAAAp1JREFUeF7t
m0FuwzAMBJX/fzq9NEUCA1viUrTkXhNZXM4OKTn59fX9/ev5t8kTfD0B2ITvAE8ANoN/Kj4V
YJN/NwUeAJv8NwUeAB8AwO9r+Bb0u8k9zzylAnwqgF/i8QCYDwJ5HOABsAeAvgj/aQVgvwjn
FQAsge8J6FVT/ASw6wLkPeAB4MuvexzgAeB7AvYYgNb2dx7/FkB9DPAB4O8e/ACw6QJk8vkW
5AOwKwJk+fMeoKb/zwD2F3V9vXwZ/NcVYNcLMK8CAT0rAN8KoD4F/UkF2HUN8skXYF8E8EPQ
A2CPB6j1k+8BqoBdAHgb6scA9V4weQ3gFQBOQXQK4n6CegDY4wHqc5CnIFoB8CmIUhD9CPBL
UN5KZhdBeg8QXwi5AuAKgGsAXAN4GioB8FWYe8C2hwCxB+w+BnsFAD2EEYDvCfjsAPRGPE9B
pAI8W4DzDhB/D/AAsPMi7OkB8o3ohzC5DfVzgAfArghwH0N9TwBPA9T3gQdA/U7oNRg9BtgD
4KcAt/WdH4T4MxifguwpCO8BNn0dIPcADwD7MlReA3gRpt8FxXuA+k6YKwD7fYC+BvBViO4B
5FXIFYBdBGkFsI8B+DTEn4KoD+HeAnwPUJ8D7InYFQB7DLAH/Pl+AHUb5EeAvJfcqwA+BdFj
gH0VID8H4G+C4kM4fQrySxD5JchPQeQ94HkPsO8J+FMQPQbII0DfA8wrQP8YYE8E9SaIvgfg
CtC/C4o3IjwNtQfAe4D+MUDdA+Q1oL8IqvcBnobyGsBPQXQK2vVF+F9Pwa4I6k2QPQXxKYh+
GdorAK8A/YMYvQbw0xB/CrKnYR4BdkXYFWFXBP1uiD0A/z1A/z2A/TJM/j2AXRHsdyG8Evwf
ELWowTafeb4AAAAASUVORK5CYII="""


def get_max_main_window():
    try:
        from qtmax import GetQMaxMainWindow
        return GetQMaxMainWindow()
    except ImportError:
        pass
    for widget in QtWidgets.QApplication.topLevelWidgets():
        if "QMainWindow" in str(type(widget)) and "3ds Max" in widget.windowTitle():
            return widget
    return None


def get_or_create_layer(name):
    layer = rt.LayerManager.getLayerFromName(name)
    if layer is None:
        layer = rt.LayerManager.newLayerFromName(name)
    return layer


# ==========================================
# ===== FFMPEG VIDEO CONVERSION SYSTEM =====
# ==========================================

def find_ffmpeg():
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        os.path.expanduser(r"~\ffmpeg\bin\ffmpeg.exe"),
        os.path.expanduser(r"~\Desktop\ffmpeg\bin\ffmpeg.exe"),
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    winget_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Packages")
    if os.path.isdir(winget_dir):
        for root, dirs, files in os.walk(winget_dir):
            if "ffmpeg.exe" in files:
                return os.path.join(root, "ffmpeg.exe")
    return None


def convert_video_to_sequence(ffmpeg_path, video_path):
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    temp_root = rt.GetDir(rt.name("temp"))
    seq_dir = os.path.join(temp_root, f"refcast_{base_name}_{int(time.time())}").replace("\\", "/")
    os.makedirs(seq_dir, exist_ok=True)
    frame_pattern = os.path.join(seq_dir, f"{base_name}_%05d.png").replace("\\", "/")

    cmd = [ffmpeg_path, "-i", video_path, "-vf", "format=rgba", "-y", frame_pattern]
    try:
        cflags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, creationflags=cflags)
    except subprocess.TimeoutExpired:
        return None, f"FFmpeg timed out converting '{os.path.basename(video_path)}'"
    except Exception as e:
        return None, f"FFmpeg error: {str(e)}"

    frames = sorted(glob.glob(os.path.join(seq_dir, f"{base_name}_*.png")))
    if not frames:
        stderr_short = result.stderr[-300:] if result.stderr else "Unknown error"
        return None, f"FFmpeg produced no frames for '{os.path.basename(video_path)}'.\n{stderr_short}"

    ifl_path = os.path.join(seq_dir, f"{base_name}.ifl").replace("\\", "/")
    with open(ifl_path, 'w') as f:
        for frame in frames:
            f.write(frame.replace("\\", "/") + "\n")
    return ifl_path, None


# ==========================================
# ===== SMART VIEW DETECTION =====
# ==========================================
def detect_view_from_name(filename):
    """
    Advanced view detection from filename.
    Supports full names, abbreviations, prefixes, suffixes,
    multi-language hints, and common 3D naming conventions.
    """
    name = os.path.splitext(os.path.basename(filename))[0].lower()
    tokens = re.split(r'[\s_\-\.]+', name)

    # Priority ordered: each entry = (view, exact_tokens, substring_patterns)
    rules = [
        ("Front",
         {"front", "fv", "fnt", "frnt", "f_view", "frontview", "anterior", "fwd", "forward", "facade", "face"},
         {"_front", "front_", "-front", "front-", ".front", "_fv", "fv_", "_fnt"}),
        ("Back",
         {"back", "bv", "bck", "bk", "rear", "b_view", "backview", "posterior", "behind", "dorsal"},
         {"_back", "back_", "-back", "back-", ".back", "_bv", "bv_", "_bck", "_rear"}),
        ("Left",
         {"left", "lv", "lft", "lt", "l_view", "leftview", "lside", "l_side", "gauche", "izquierda"},
         {"_left", "left_", "-left", "left-", ".left", "_lv", "lv_", "_lft"}),
        ("Right",
         {"right", "rv", "rgt", "rt", "r_view", "rightview", "rside", "r_side", "droite", "derecha"},
         {"_right", "right_", "-right", "right-", ".right", "_rv", "rv_", "_rgt"}),
        ("Top",
         {"top", "tv", "tp", "t_view", "topview", "above", "up", "overhead", "ceil", "upper", "plan"},
         {"_top", "top_", "-top", "top-", ".top", "_tv", "tv_"}),
        ("Bottom",
         {"bottom", "bov", "bot", "btm", "bt", "b_view", "bottomview", "below",
          "down", "under", "ventral", "floor", "base", "sole", "lower"},
         {"_bottom", "bottom_", "-bottom", "bottom-", ".bottom", "_bot", "bot_", "_btm", "btm_"}),
    ]

    # Pass 1: Exact token match (highest confidence)
    for view, token_set, _ in rules:
        for t in tokens:
            if t in token_set:
                return view

    # Pass 2: Substring match
    for view, _, substr_set in rules:
        for pat in substr_set:
            if pat in name:
                return view

    # Pass 3: Loose contains (unambiguous long keywords only)
    loose = [
        ("Front", ["front", "anterior", "forward", "facade"]),
        ("Back",  ["back", "rear", "posterior", "behind"]),
        ("Left",  ["left"]),
        ("Right", ["right"]),
        ("Top",   ["top", "above", "overhead"]),
        ("Bottom",["bottom", "below", "under"]),
    ]
    for view, keywords in loose:
        for kw in keywords:
            if kw in name:
                return view

    return None


# ===== STYLE CONSTANTS =====
STYLE_DARK_BG = "#1a1a1a"
STYLE_PANEL_BG = "#222"
STYLE_WIDGET_BG = "#333"
STYLE_BORDER = "#444"
STYLE_ACCENT = "#00aaff"
STYLE_TEXT = "#eee"
STYLE_MUTED = "#888"

GROUPBOX_STYLE = f"""
    QGroupBox {{
        border: 1px solid {STYLE_BORDER};
        margin-top: 14px;
        padding-top: 18px;
        font-weight: bold;
        color: {STYLE_TEXT};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
        color: {STYLE_ACCENT};
    }}
"""

BUTTON_STYLE = f"""
    QPushButton {{
        background-color: #505050; color: white;
        border-radius: 4px; padding: 8px;
        font-weight: bold; border: 1px solid #666;
    }}
    QPushButton:hover {{ background-color: #606060; border-color: {STYLE_ACCENT}; }}
    QPushButton:pressed {{ background-color: #333; }}
"""

# ===== SUPPORTED FORMATS =====
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tga', '.bmp', '.tif', '.tiff', '.exr', '.hdr', '.gif']
VIDEO_EXTENSIONS = ['.avi', '.mov', '.mp4', '.wmv', '.mpg', '.mpeg', '.mkv', '.webm', '.flv', '.m4v']
SEQUENCE_EXTENSIONS = ['.ifl']
ALL_MEDIA_EXTENSIONS = IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + SEQUENCE_EXTENSIONS


# =============================================================================
#  DRAG DROP WIDGET
# =============================================================================
class DragDropWidget(QtWidgets.QLabel):
    files_dropped = QtCore.Signal(list)

    def __init__(self):
        super().__init__()
        self.setText("Drop Images, Videos or Folders Here\n\nاسحب الصور أو الفيديوهات أو المجلدات هنا")
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet(f"""
            QLabel {{
                border: 2px dashed #555;
                border-radius: 10px;
                font-size: 14px;
                color: #aaa;
                background-color: #2a2a2a;
            }}
            QLabel:hover {{
                border-color: {STYLE_ACCENT};
                color: {STYLE_ACCENT};
                background-color: #333;
            }}
        """)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        final_files = []
        for f in files:
            if os.path.isdir(f):
                for root, dirs, filenames in os.walk(f):
                    for fn in filenames:
                        if os.path.splitext(fn)[1].lower() in ALL_MEDIA_EXTENSIONS:
                            final_files.append(os.path.join(root, fn).replace("\\", "/"))
            elif os.path.splitext(f)[1].lower() in ALL_MEDIA_EXTENSIONS:
                final_files.append(f.replace("\\", "/"))
        if final_files:
            self.files_dropped.emit(final_files)


# =============================================================================
#  FOOTER WIDGET (reusable)
# =============================================================================
def create_footer(parent=None):
    footer = QtWidgets.QWidget(parent)
    footer.setStyleSheet(f"background-color: {STYLE_DARK_BG};")
    lay = QtWidgets.QVBoxLayout(footer)
    lay.setContentsMargins(8, 6, 8, 8)
    lay.setSpacing(6)

    lbl = QtWidgets.QLabel(f"SCRIPTED BY : MOSTAFA_AHMED360  |  {PLUGIN_FULL}  |  2026 ©")
    lbl.setAlignment(QtCore.Qt.AlignCenter)
    lbl.setStyleSheet("color: #555; font-size: 10px;")
    lay.addWidget(lbl)

    btn = QtWidgets.QPushButton()
    btn.setToolTip("Support the developer — Thank you!")
    btn.setCursor(QtCore.Qt.PointingHandCursor)
    btn.setFixedHeight(56)
    btn.setMinimumWidth(220)

    try:
        img_data = base64.b64decode(SUPPORT_IMG_BASE64.strip())
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(img_data)
        if not pixmap.isNull():
            btn.setIcon(QtGui.QIcon(pixmap))
            btn.setIconSize(QtCore.QSize(200, 48))
        else:
            btn.setText("☕  Support Me")
    except Exception:
        btn.setText("☕  Support Me")

    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: #252525;
            border: 1px solid #444;
            border-radius: 8px;
            padding: 6px 24px;
            color: #ffcc00;
            font-weight: bold;
            font-size: 15px;
        }}
        QPushButton:hover {{
            background-color: #3a3a3a;
            border-color: #ffcc00;
        }}
    """)
    btn.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(SUPPORT_URL)))

    h_lay = QtWidgets.QHBoxLayout()
    h_lay.setAlignment(QtCore.Qt.AlignCenter)
    h_lay.addWidget(btn)
    lay.addLayout(h_lay)

    return footer


# =============================================================================
#  MAIN WIDGET
# =============================================================================
class ReferenceManager(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # =====================================================================
        # FIXED HEADER — Title + Viewport Switcher
        # =====================================================================
        header = QtWidgets.QWidget()
        header.setStyleSheet(f"background-color: {STYLE_DARK_BG};")
        header_lay = QtWidgets.QVBoxLayout(header)
        header_lay.setContentsMargins(6, 6, 6, 4)
        header_lay.setSpacing(4)

        lbl_title = QtWidgets.QLabel(PLUGIN_FULL)
        lbl_title.setAlignment(QtCore.Qt.AlignCenter)
        lbl_title.setStyleSheet(f"font-weight: bold; font-size: 15px; color: {STYLE_ACCENT};")
        header_lay.addWidget(lbl_title)

        # Viewport switcher
        switch_frame = QtWidgets.QFrame()
        switch_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #111;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 2px;
            }}
        """)
        sw_lay = QtWidgets.QHBoxLayout(switch_frame)
        sw_lay.setSpacing(2)
        sw_lay.setContentsMargins(4, 3, 4, 3)

        views_config = [
            ("F", "Front"), ("BA", "Back"), ("L", "Left"),
            ("R", "Right"), ("T", "Top"), ("BO", "Bottom"), ("P", "Persp")
        ]
        for label, cmd_name in views_config:
            btn = QtWidgets.QPushButton(label)
            btn.setFixedWidth(35)
            btn.setFixedHeight(25)
            btn.setToolTip(f"Switch to {cmd_name} View" + (" (Home)" if cmd_name == "Persp" else ""))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #2a2a2a; color: #ccc;
                    border: 1px solid #3a3a3a; border-radius: 3px;
                    font-weight: bold; font-size: 11px;
                }}
                QPushButton:hover {{
                    background-color: {STYLE_ACCENT}; color: black;
                    border-color: {STYLE_ACCENT};
                }}
            """)
            btn.clicked.connect(lambda checked=False, c=cmd_name: self.switch_viewport(c))
            sw_lay.addWidget(btn)
        header_lay.addWidget(switch_frame)
        root.addWidget(header)

        # =====================================================================
        # PAGE NAVIGATION BAR
        # =====================================================================
        nav_bar = QtWidgets.QWidget()
        nav_bar.setStyleSheet(f"background-color: {STYLE_DARK_BG}; border-top: 1px solid #333;")
        nav_lay = QtWidgets.QHBoxLayout(nav_bar)
        nav_lay.setContentsMargins(6, 4, 6, 4)
        nav_lay.setSpacing(6)

        NAV_BTN_STYLE = f"""
            QPushButton {{
                background-color: #2a2a2a; color: #bbb;
                border: 1px solid #444; border-radius: 4px;
                font-weight: bold; font-size: 11px; padding: 0 14px;
            }}
            QPushButton:hover {{
                background-color: {STYLE_ACCENT}; color: black; border-color: {STYLE_ACCENT};
            }}
            QPushButton:checked {{
                background-color: {STYLE_ACCENT}; color: black; border-color: {STYLE_ACCENT};
            }}
        """

        self.btn_page_import = QtWidgets.QPushButton("📥  Import")
        self.btn_page_import.setCheckable(True)
        self.btn_page_import.setChecked(True)
        self.btn_page_import.setFixedHeight(28)
        self.btn_page_import.setStyleSheet(NAV_BTN_STYLE)

        self.btn_page_settings = QtWidgets.QPushButton("⚙  Settings")
        self.btn_page_settings.setCheckable(True)
        self.btn_page_settings.setFixedHeight(28)
        self.btn_page_settings.setStyleSheet(NAV_BTN_STYLE)

        nav_lay.addWidget(self.btn_page_import, 1)
        nav_lay.addWidget(self.btn_page_settings, 1)
        root.addWidget(nav_bar)

        # =====================================================================
        # STACKED PAGES
        # =====================================================================
        self.stack = QtWidgets.QStackedWidget()
        self.stack.setStyleSheet(f"background-color: {STYLE_PANEL_BG};")

        self.stack.addWidget(self._build_import_page())   # index 0
        self.stack.addWidget(self._build_settings_page())  # index 1
        self.stack.setCurrentIndex(0)
        root.addWidget(self.stack, 1)

        # =====================================================================
        # FIXED FOOTER
        # =====================================================================
        root.addWidget(create_footer(self))

        # =====================================================================
        # SIGNALS
        # =====================================================================
        self.btn_page_import.clicked.connect(lambda: self._go_page(0))
        self.btn_page_settings.clicked.connect(lambda: self._go_page(1))
        self.update_ui_state()

    # =================================================================
    # PAGE BUILDERS
    # =================================================================
    def _build_import_page(self):
        page = QtWidgets.QWidget()
        page.setStyleSheet(f"background-color: {STYLE_PANEL_BG}; color: {STYLE_TEXT};")
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        # Browse + Clipboard row
        btn_row = QtWidgets.QHBoxLayout()
        self.btn_browse = QtWidgets.QPushButton("📁  Browse Files")
        self.btn_browse.clicked.connect(self.browse_files)
        self.btn_browse.setStyleSheet(BUTTON_STYLE)
        self.btn_browse.setFixedHeight(40)

        self.btn_clipboard = QtWidgets.QPushButton("📋  Paste Clipboard")
        self.btn_clipboard.clicked.connect(self.paste_from_clipboard)
        self.btn_clipboard.setFixedHeight(40)
        self.btn_clipboard.setStyleSheet(f"""
            QPushButton {{
                background-color: #005570; color: white;
                border-radius: 4px; padding: 8px;
                border: 1px solid #007799; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: #007799; border-color: {STYLE_ACCENT}; }}
        """)
        btn_row.addWidget(self.btn_browse)
        btn_row.addWidget(self.btn_clipboard)
        lay.addLayout(btn_row)

        # Drop Zone — LARGE, expands
        self.drop_zone = DragDropWidget()
        self.drop_zone.files_dropped.connect(self.process_files)
        self.drop_zone.setMinimumHeight(220)
        self.drop_zone.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        lay.addWidget(self.drop_zone, 1)

        # Select All References
        self.btn_select_all = QtWidgets.QPushButton("⬚  Select All Reference Planes")
        self.btn_select_all.setToolTip(f"Select all objects in the '{LAYER_NAME}' layer")
        self.btn_select_all.clicked.connect(self.select_all_references)
        self.btn_select_all.setFixedHeight(36)
        self.btn_select_all.setStyleSheet(f"""
            QPushButton {{
                background-color: #333; color: #bbb;
                border-radius: 4px; padding: 8px;
                font-weight: bold; font-size: 12px;
                border: 1px solid #555;
            }}
            QPushButton:hover {{
                background-color: #444; border-color: {STYLE_ACCENT}; color: white;
            }}
        """)
        lay.addWidget(self.btn_select_all)

        return page

    def _build_settings_page(self):
        page = QtWidgets.QWidget()
        page.setStyleSheet(f"background-color: {STYLE_PANEL_BG}; color: {STYLE_TEXT};")

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: {STYLE_PANEL_BG}; }}")

        container = QtWidgets.QWidget()
        container.setStyleSheet(f"background-color: {STYLE_PANEL_BG}; color: {STYLE_TEXT};")
        layout = QtWidgets.QVBoxLayout(container)
        layout.setSpacing(4)

        # 1. MODE
        group_mode = QtWidgets.QGroupBox("1. Setup Mode")
        group_mode.setStyleSheet(GROUPBOX_STYLE)
        mode_layout = QtWidgets.QVBoxLayout()
        self.COMBO_MODE = QtWidgets.QComboBox()
        self.COMBO_MODE.addItems(["Manual View (Standard)", "Box Mode (6 Sides Cube)", "Smart Detect (By Name)"])
        self.COMBO_MODE.currentIndexChanged.connect(self.update_ui_state)
        self.COMBO_MODE.setStyleSheet(f"padding: 5px; background-color: {STYLE_WIDGET_BG};")
        mode_layout.addWidget(self.COMBO_MODE)
        self.lbl_info = QtWidgets.QLabel("")
        self.lbl_info.setStyleSheet(f"color: {STYLE_MUTED}; font-size: 11px;")
        mode_layout.addWidget(self.lbl_info)
        group_mode.setLayout(mode_layout)
        layout.addWidget(group_mode)

        # 2. VIEWPORT ORIENTATION
        self.group_align = QtWidgets.QGroupBox("2. Target View Orientation")
        self.group_align.setStyleSheet(GROUPBOX_STYLE)
        align_layout = QtWidgets.QVBoxLayout()
        self.COMBO_VIEW = QtWidgets.QComboBox()
        self.COMBO_VIEW.addItems(["Front", "Back", "Left", "Right", "Top", "Bottom"])
        self.COMBO_VIEW.setStyleSheet(f"padding: 5px; background-color: {STYLE_WIDGET_BG};")
        align_layout.addWidget(self.COMBO_VIEW)
        self.group_align.setLayout(align_layout)
        layout.addWidget(self.group_align)

        # 3. GEOMETRY & OFFSET
        group_trans = QtWidgets.QGroupBox("3. Geometry & Offset")
        group_trans.setStyleSheet(GROUPBOX_STYLE)
        trans_layout = QtWidgets.QVBoxLayout()

        row_scale = QtWidgets.QHBoxLayout()
        row_scale.addWidget(QtWidgets.QLabel("Scale:"))
        self.SPIN_SCALE = QtWidgets.QDoubleSpinBox()
        self.SPIN_SCALE.setRange(0.01, 1000.0)
        self.SPIN_SCALE.setValue(1.0)
        self.SPIN_SCALE.setStyleSheet(f"background-color: {STYLE_WIDGET_BG}; padding: 3px;")
        row_scale.addWidget(self.SPIN_SCALE)
        trans_layout.addLayout(row_scale)

        row_offset = QtWidgets.QHBoxLayout()
        row_offset.addWidget(QtWidgets.QLabel("Offset:"))
        self.SPIN_OFFSET = QtWidgets.QDoubleSpinBox()
        self.SPIN_OFFSET.setRange(0.0, 100000.0)
        self.SPIN_OFFSET.setValue(50.0)
        self.SPIN_OFFSET.setStyleSheet(f"background-color: {STYLE_WIDGET_BG}; padding: 3px;")

        self.btn_auto_offset = QtWidgets.QPushButton("AUTO")
        self.btn_auto_offset.setCheckable(True)
        self.btn_auto_offset.setFixedWidth(80)
        self.btn_auto_offset.setToolTip("Auto-calculate offset based on Image Dimensions")
        self.btn_auto_offset.clicked.connect(self.toggle_auto_offset)
        self.btn_auto_offset.setStyleSheet(f"""
            QPushButton {{
                background-color: #505050; color: white;
                border-radius: 4px; padding: 4px;
                font-weight: bold; border: 1px solid #666;
            }}
            QPushButton:checked {{ background-color: {STYLE_ACCENT}; color: black; border: 1px solid #fff; }}
            QPushButton:hover {{ background-color: #606060; border-color: {STYLE_ACCENT}; }}
        """)
        row_offset.addWidget(self.SPIN_OFFSET)
        row_offset.addWidget(self.btn_auto_offset)
        trans_layout.addLayout(row_offset)

        row_pivot = QtWidgets.QHBoxLayout()
        row_pivot.addWidget(QtWidgets.QLabel("Pivot:"))
        self.COMBO_PIVOT = QtWidgets.QComboBox()
        self.COMBO_PIVOT.addItems(["Center", "Bottom Center", "Top Center", "Left Edge", "Right Edge"])
        self.COMBO_PIVOT.setCurrentIndex(1)
        self.COMBO_PIVOT.setStyleSheet(f"background-color: {STYLE_WIDGET_BG}; padding: 3px;")
        row_pivot.addWidget(self.COMBO_PIVOT)
        trans_layout.addLayout(row_pivot)
        group_trans.setLayout(trans_layout)
        layout.addWidget(group_trans)

        # 4. PROPERTIES (REAL-TIME)
        group_props = QtWidgets.QGroupBox("4. Properties (Real-Time)")
        group_props.setStyleSheet(f"""
            QGroupBox {{
                border: 1px solid #5a5a6a;
                margin-top: 14px;
                padding-top: 22px;
                font-weight: bold;
                color: {STYLE_TEXT};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #8ab4f8;
            }}
        """)
        props_layout = QtWidgets.QVBoxLayout()
        props_layout.setContentsMargins(8, 8, 8, 8)

        props_layout.addWidget(QtWidgets.QLabel("Opacity / Visibility:"))
        self.SLIDER_OPACITY = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.SLIDER_OPACITY.setRange(0, 100)
        self.SLIDER_OPACITY.setValue(100)
        self.SLIDER_OPACITY.setTracking(True)
        self.SLIDER_OPACITY.valueChanged.connect(self.update_live_properties)
        props_layout.addWidget(self.SLIDER_OPACITY)

        grid = QtWidgets.QGridLayout()
        self.CHK_FREEZE = QtWidgets.QCheckBox("Freeze")
        self.CHK_CULL = QtWidgets.QCheckBox("Backface Cull")
        self.CHK_RENDERABLE = QtWidgets.QCheckBox("Renderable")
        self.CHK_CAST_SHADOWS = QtWidgets.QCheckBox("Cast Shadows")
        self.CHK_RCV_SHADOWS = QtWidgets.QCheckBox("Rec. Shadows")
        self.CHK_SHOW_GRAY = QtWidgets.QCheckBox("Frozen Gray")

        for chk in [self.CHK_FREEZE, self.CHK_CULL, self.CHK_RENDERABLE,
                     self.CHK_CAST_SHADOWS, self.CHK_RCV_SHADOWS, self.CHK_SHOW_GRAY]:
            chk.toggled.connect(self.update_live_properties)

        self.CHK_CULL.setChecked(True)
        self.CHK_RENDERABLE.setChecked(True)

        grid.addWidget(self.CHK_FREEZE, 0, 0)
        grid.addWidget(self.CHK_CULL, 0, 1)
        grid.addWidget(self.CHK_RENDERABLE, 1, 0)
        grid.addWidget(self.CHK_SHOW_GRAY, 1, 1)
        grid.addWidget(self.CHK_CAST_SHADOWS, 2, 0)
        grid.addWidget(self.CHK_RCV_SHADOWS, 2, 1)
        props_layout.addLayout(grid)
        group_props.setLayout(props_layout)
        layout.addWidget(group_props)

        # 5. MATERIAL
        group_mat = QtWidgets.QGroupBox("5. Material")
        group_mat.setStyleSheet(GROUPBOX_STYLE)
        mat_layout = QtWidgets.QVBoxLayout()
        self.COMBO_MAT = QtWidgets.QComboBox()
        self.COMBO_MAT.addItems(["Physical", "Standard", "VRay", "Corona", "Arnold", "Redshift"])
        self.COMBO_MAT.setStyleSheet(f"padding: 5px; background-color: {STYLE_WIDGET_BG};")
        mat_layout.addWidget(self.COMBO_MAT)
        self.CHK_ALPHA = QtWidgets.QCheckBox("Use Alpha Channel")
        self.CHK_ALPHA.setChecked(True)
        mat_layout.addWidget(self.CHK_ALPHA)
        group_mat.setLayout(mat_layout)
        layout.addWidget(group_mat)

        # Select All References (also on settings page)
        self.btn_select_all_s = QtWidgets.QPushButton("⬚  Select All Reference Planes")
        self.btn_select_all_s.setToolTip(f"Select all objects in the '{LAYER_NAME}' layer")
        self.btn_select_all_s.clicked.connect(self.select_all_references)
        self.btn_select_all_s.setFixedHeight(36)
        self.btn_select_all_s.setStyleSheet(f"""
            QPushButton {{
                background-color: #333; color: #bbb;
                border-radius: 4px; padding: 8px;
                font-weight: bold; font-size: 12px;
                border: 1px solid #555;
                margin-top: 6px;
            }}
            QPushButton:hover {{
                background-color: #444; border-color: {STYLE_ACCENT}; color: white;
            }}
        """)
        layout.addWidget(self.btn_select_all_s)

        layout.addStretch()
        scroll.setWidget(container)

        page_lay = QtWidgets.QVBoxLayout(page)
        page_lay.setContentsMargins(0, 0, 0, 0)
        page_lay.addWidget(scroll)
        return page

    # =================================================================
    # NAVIGATION
    # =================================================================
    def _go_page(self, idx):
        self.stack.setCurrentIndex(idx)
        self.btn_page_import.setChecked(idx == 0)
        self.btn_page_settings.setChecked(idx == 1)

    # =================================================================
    # UI STATE
    # =================================================================
    def update_ui_state(self):
        mode = self.COMBO_MODE.currentText()
        if "Manual" in mode:
            self.group_align.setVisible(True)
            self.lbl_info.setText("Standard Mode: Applies selected View to all images.")
            self.COMBO_PIVOT.setEnabled(True)
        elif "Box" in mode:
            self.group_align.setVisible(False)
            self.lbl_info.setText("Box Mode: Creates 6 planes (Cube). Offset adjusted by W/H.")
            self.COMBO_PIVOT.setEnabled(True)
        elif "Smart" in mode:
            self.group_align.setVisible(False)
            self.lbl_info.setText("Auto-Detect: Reads filename keywords for view assignment.")
            self.COMBO_PIVOT.setEnabled(True)

    def toggle_auto_offset(self):
        self.SPIN_OFFSET.setEnabled(not self.btn_auto_offset.isChecked())

    # =================================================================
    # SELECT ALL REFERENCES
    # =================================================================
    def select_all_references(self):
        layer = rt.LayerManager.getLayerFromName(LAYER_NAME)
        if layer is None:
            QtWidgets.QMessageBox.information(self, PLUGIN_NAME,
                f"No '{LAYER_NAME}' layer found.\nImport some references first.")
            return

        count = rt.execute(f"""
        (
            local theLayer = LayerManager.getLayerFromName "{LAYER_NAME}"
            local result = 0
            if theLayer != undefined do (
                local layerNodes = #()
                theLayer.nodes &layerNodes
                if layerNodes.count > 0 do (
                    select layerNodes
                    result = layerNodes.count
                )
            )
            result
        )
        """)
        rt.redrawViews()

        if count and count > 0:
            QtWidgets.QMessageBox.information(self, PLUGIN_NAME,
                f"Selected {count} reference plane(s).")
        else:
            QtWidgets.QMessageBox.information(self, PLUGIN_NAME,
                f"Layer '{LAYER_NAME}' exists but has no objects.")

    # =================================================================
    # VIEWPORT
    # =================================================================
    def switch_viewport(self, view_name):
        try:
            if view_name == "Persp":
                # Go to Perspective HOME — standard 3/4 isometric view
                rt.execute("""
                (
                    viewport.setType #view_persp_user
                    viewport.setTM (matrix3 [0.707107,0.353553,-0.612372] [-0.707107,0.353553,-0.612372] [0,0.866025,0.5] [0,0,0])
                    max zoomext sel all
                )
                """)
            else:
                cmds = {
                    "Front": "max vpt front", "Back": "max vpt back",
                    "Left": "max vpt left", "Right": "max vpt right",
                    "Top": "max vpt top", "Bottom": "max vpt bottom"
                }
                rt.execute(cmds.get(view_name, ""))
        except Exception:
            pass

    # =================================================================
    # LIVE PROPERTIES
    # =================================================================
    def update_live_properties(self):
        sel = rt.selection
        if not sel or len(sel) == 0:
            return

        opacity_val = self.SLIDER_OPACITY.value() / 100.0
        freeze = self.CHK_FREEZE.isChecked()
        cull = self.CHK_CULL.isChecked()
        renderable = self.CHK_RENDERABLE.isChecked()
        cast = self.CHK_CAST_SHADOWS.isChecked()
        rcv = self.CHK_RCV_SHADOWS.isChecked()
        gray = self.CHK_SHOW_GRAY.isChecked()

        with pymxs.undo(False):
            for obj in sel:
                try:
                    rt.UPDATE_VISIBILITY_FN(obj, opacity_val)
                    obj.showFrozenInGray = gray
                    if freeze:
                        if not obj.isFrozen: rt.freeze(obj)
                    else:
                        if obj.isFrozen: rt.unfreeze(obj)
                    obj.backFaceCull = cull
                    obj.renderable = renderable
                    obj.castShadows = cast
                    obj.receiveShadows = rcv
                except Exception:
                    pass
        rt.redrawViews()

    # =================================================================
    # PIVOT HELPER
    # =================================================================
    def _get_pivot_world_offset(self, view_name, pivot_loc, final_w, final_h):
        if pivot_loc == "Center":
            return (0.0, 0.0, 0.0)

        w2 = final_w / 2.0
        h2 = final_h / 2.0
        dx = dy = dz = 0.0

        if view_name in ("Front", "Back"):
            if "Bottom" in pivot_loc: dz = -h2
            elif "Top" in pivot_loc: dz = h2
            if "Left" in pivot_loc: dx = -w2
            elif "Right" in pivot_loc: dx = w2
        elif view_name == "Left":
            if "Bottom" in pivot_loc: dz = -h2
            elif "Top" in pivot_loc: dz = h2
            if "Left" in pivot_loc: dy = w2
            elif "Right" in pivot_loc: dy = -w2
        elif view_name == "Right":
            if "Bottom" in pivot_loc: dz = -h2
            elif "Top" in pivot_loc: dz = h2
            if "Left" in pivot_loc: dy = -w2
            elif "Right" in pivot_loc: dy = w2
        elif view_name == "Top":
            if "Bottom" in pivot_loc: dy = -h2
            elif "Top" in pivot_loc: dy = h2
            if "Left" in pivot_loc: dx = -w2
            elif "Right" in pivot_loc: dx = w2
        elif view_name == "Bottom":
            if "Bottom" in pivot_loc: dy = h2
            elif "Top" in pivot_loc: dy = -h2
            if "Left" in pivot_loc: dx = -w2
            elif "Right" in pivot_loc: dx = w2

        return (dx, dy, dz)

    # =================================================================
    # CREATE PLANE
    # =================================================================
    def create_plane_obj(self, tex, view_name, scale_val, offset_val, pivot_loc, mat, props, is_box_mode=False):
        img_w = tex.bitmap.width
        img_h = tex.bitmap.height
        final_w = img_w * scale_val
        final_h = img_h * scale_val

        plane = rt.Plane(width=final_w, length=final_h, widthsegs=1, lengthsegs=1)
        plane.name = "Ref_" + view_name + "_" + os.path.basename(tex.filename)
        plane.material = mat

        rt.showTextureMap(mat, tex, True)
        rt.addModifier(plane, rt.Uvwmap(maptype=4))

        rot_x = rot_y = rot_z = 0
        if view_name == "Front": rot_x = 90
        elif view_name == "Back": rot_x = 90; rot_z = 180
        elif view_name == "Left": rot_x = 90; rot_z = -90
        elif view_name == "Right": rot_x = 90; rot_z = 90
        elif view_name == "Top": rot_x = 0
        elif view_name == "Bottom": rot_x = 180

        rt.rotate(plane, rt.EulerAngles(rot_x, rot_y, rot_z))

        px = py = pz = 0.0
        if view_name == "Front": py = offset_val
        elif view_name == "Back": py = -offset_val
        elif view_name == "Left": px = offset_val
        elif view_name == "Right": px = -offset_val
        elif view_name == "Top": pz = -offset_val
        elif view_name == "Bottom": pz = offset_val

        plane.pos = rt.Point3(px, py, pz)

        pdx, pdy, pdz = self._get_pivot_world_offset(view_name, pivot_loc, final_w, final_h)
        plane.pivot = rt.Point3(px + pdx, py + pdy, pz + pdz)

        plane.renderable = props['renderable']
        plane.castShadows = props['cast']
        plane.receiveShadows = props['rcv']
        plane.backFaceCull = props['cull']

        rt.UPDATE_VISIBILITY_FN(plane, props['opacity'])

        if props['freeze']:
            plane.showFrozenInGray = props['gray']
            rt.freeze(plane)

        return plane

    # =================================================================
    # MATERIAL
    # =================================================================
    def get_material_instance(self, mat_type, name, tex_map, use_alpha):
        mat = None
        if "Physical" in mat_type:
            mat = rt.PhysicalMaterial(name=name)
            mat.base_color_map = tex_map
            mat.roughness = 1.0
            if use_alpha: mat.cutout_map = tex_map
        elif "Standard" in mat_type:
            mat = rt.StandardMaterial(name=name)
            mat.diffuseMap = tex_map
            if use_alpha: mat.opacityMap = tex_map
        elif "VRay" in mat_type:
            try:
                mat = rt.VRayMtl(name=name); mat.texmap_diffuse = tex_map
                if use_alpha: mat.texmap_opacity = tex_map
            except Exception:
                return self.get_material_instance("Standard", name, tex_map, use_alpha)
        elif "Corona" in mat_type:
            try:
                mat = rt.CoronaPhysicalMtl(name=name); mat.baseTexmap = tex_map
                if use_alpha: mat.opacityTexmap = tex_map
            except Exception:
                return self.get_material_instance("Standard", name, tex_map, use_alpha)
        elif "Arnold" in mat_type:
            try:
                mat = rt.ai_standard_surface(name=name); mat.base_color_shader = tex_map
                if use_alpha: mat.opacity_shader = tex_map
            except Exception:
                return self.get_material_instance("Standard", name, tex_map, use_alpha)
        elif "Redshift" in mat_type:
            try:
                mat = rt.Redshift_Material(name=name); mat.diffuse_color_map = tex_map
                if use_alpha: mat.opacity_color_map = tex_map
            except Exception:
                return self.get_material_instance("Standard", name, tex_map, use_alpha)
        else:
            mat = rt.StandardMaterial(name=name, diffuseMap=tex_map)
        return mat

    # =================================================================
    # LOAD TEXTURE
    # =================================================================
    def load_texture_map(self, fpath, use_alpha):
        ext = os.path.splitext(fpath)[1].lower()
        load_path = fpath

        if ext in VIDEO_EXTENSIONS:
            ffmpeg = find_ffmpeg()
            if ffmpeg is None:
                return None, (
                    f"Cannot load video '{os.path.basename(fpath)}'.\n"
                    f"FFmpeg is required for video support.\n\n"
                    f"Install FFmpeg:\n"
                    f"  winget install ffmpeg\n"
                    f"  or download from https://ffmpeg.org/download.html\n"
                    f"  and add to system PATH"
                )
            ifl_path, err = convert_video_to_sequence(ffmpeg, fpath)
            if ifl_path is None:
                return None, err
            load_path = ifl_path

        try:
            tex = rt.BitmapTexture(fileName=load_path)
            bmp = tex.bitmap
            if bmp is None:
                return None, f"Max could not read: {os.path.basename(fpath)}"
            _ = bmp.width
            _ = bmp.height
        except Exception as e:
            return None, f"Cannot load '{os.path.basename(fpath)}': {str(e)}"

        if use_alpha:
            tex.alphaSource = 2
            tex.monoOutput = 1

        loaded_ext = os.path.splitext(load_path)[1].lower()
        if loaded_ext in SEQUENCE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
            try:
                tex.startTime = 0
                tex.playBackRate = 1.0
                tex.endCondition = 1
            except Exception:
                pass

        return tex, None

    # =================================================================
    # BROWSE / CLIPBOARD
    # =================================================================
    def browse_files(self):
        img_filter = " ".join([f"*{e}" for e in IMAGE_EXTENSIONS])
        vid_filter = " ".join([f"*{e}" for e in VIDEO_EXTENSIONS])
        seq_filter = " ".join([f"*{e}" for e in SEQUENCE_EXTENSIONS])
        all_filter = " ".join([f"*{e}" for e in ALL_MEDIA_EXTENSIONS])
        filters = (
            f"All Supported ({all_filter});;"
            f"Images ({img_filter});;"
            f"Videos ({vid_filter});;"
            f"Sequences ({seq_filter});;"
            f"All Files (*.*)"
        )
        files, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Select Media Files", "", filters)
        if files:
            self.process_files(files)

    def paste_from_clipboard(self):
        cb = QtGui.QGuiApplication.clipboard()
        if cb.mimeData().hasImage():
            temp_dir = rt.GetDir(rt.name("temp"))
            fname = "clipboard_ref_{}.png".format(str(int(time.time())))
            full_path = os.path.join(temp_dir, fname).replace("\\", "/")
            if cb.image().save(full_path, "PNG"):
                self.process_files([full_path])
        else:
            QtWidgets.QMessageBox.warning(self, "Info", "Clipboard is empty or has no image!")

    # =================================================================
    # PROCESS FILES
    # =================================================================
    def process_files(self, file_paths):
        mode = self.COMBO_MODE.currentText()
        scale_val = self.SPIN_SCALE.value()
        pivot_loc = self.COMBO_PIVOT.currentText()
        mat_type = self.COMBO_MAT.currentText()
        use_alpha = self.CHK_ALPHA.isChecked()
        is_auto_offset = self.btn_auto_offset.isChecked()

        props = {
            'freeze': self.CHK_FREEZE.isChecked(),
            'cull': self.CHK_CULL.isChecked(),
            'renderable': self.CHK_RENDERABLE.isChecked(),
            'cast': self.CHK_CAST_SHADOWS.isChecked(),
            'rcv': self.CHK_RCV_SHADOWS.isChecked(),
            'gray': self.CHK_SHOW_GRAY.isChecked(),
            'opacity': self.SLIDER_OPACITY.value() / 100.0
        }

        created_objs = []
        failed_files = []

        with pymxs.undo(True, "RefCast Import"):
            loaded_data = []
            max_width = 0.0
            max_height = 0.0

            for fpath in file_paths:
                tex, err = self.load_texture_map(fpath, use_alpha)
                if tex is None:
                    failed_files.append(err or os.path.basename(fpath))
                    continue
                current_w = tex.bitmap.width * scale_val
                current_h = tex.bitmap.height * scale_val
                if current_w > max_width: max_width = current_w
                if current_h > max_height: max_height = current_h
                loaded_data.append((tex, fpath))

            if is_auto_offset:
                offset_val_w = max_width / 2.0
                offset_val_h = max_height / 2.0
                self.SPIN_OFFSET.setValue(offset_val_w)
            else:
                offset_val_w = self.SPIN_OFFSET.value()
                offset_val_h = self.SPIN_OFFSET.value()

            if "Manual" in mode:
                view_name = self.COMBO_VIEW.currentText()
                for tex, fpath in loaded_data:
                    mat_name = "Ref_" + os.path.basename(fpath)
                    mat = self.get_material_instance(mat_type, mat_name, tex, use_alpha)
                    if not mat: mat = rt.StandardMaterial(name=mat_name, diffuseMap=tex)
                    obj = self.create_plane_obj(tex, view_name, scale_val, offset_val_w, pivot_loc, mat, props, False)
                    created_objs.append(obj)

            elif "Box" in mode:
                all_views = ["Front", "Back", "Left", "Right", "Top", "Bottom"]
                for tex, fpath in loaded_data:
                    base_mat_name = "Ref_Box_" + os.path.basename(fpath)
                    mat = self.get_material_instance(mat_type, base_mat_name, tex, use_alpha)
                    if not mat: mat = rt.StandardMaterial(name=base_mat_name, diffuseMap=tex)
                    for v in all_views:
                        use_offset = offset_val_h if (v in ["Top", "Bottom"]) else offset_val_w
                        obj = self.create_plane_obj(tex, v, scale_val, use_offset, pivot_loc, mat, props, True)
                        created_objs.append(obj)

            elif "Smart" in mode:
                for tex, fpath in loaded_data:
                    detected = detect_view_from_name(fpath)
                    if detected:
                        mat_name = "Ref_" + os.path.basename(fpath)
                        mat = self.get_material_instance(mat_type, mat_name, tex, use_alpha)
                        if not mat: mat = rt.StandardMaterial(name=mat_name, diffuseMap=tex)
                        obj = self.create_plane_obj(tex, detected, scale_val, offset_val_w, pivot_loc, mat, props, False)
                        created_objs.append(obj)

            if created_objs:
                ref_layer = get_or_create_layer(LAYER_NAME)
                for obj in created_objs:
                    ref_layer.addNode(obj)
                rt.select(created_objs)
                rt.redrawViews()

        if failed_files:
            msg = "The following files could not be loaded:\n\n"
            msg += "\n".join(f"• {f}" for f in failed_files)
            QtWidgets.QMessageBox.warning(self, f"{PLUGIN_NAME} — Import Warning", msg)


# =============================================================================
# RUN
# =============================================================================
def run():
    max_win = get_max_main_window()
    dock_id = f"{PLUGIN_NAME}Dock_V1"

    if max_win:
        for dock in max_win.findChildren(QtWidgets.QDockWidget):
            if dock.objectName() == dock_id:
                max_win.removeDockWidget(dock)
                dock.close()
                dock.deleteLater()

    widget = ReferenceManager()
    dock_widget = QtWidgets.QDockWidget(PLUGIN_FULL, max_win)
    dock_widget.setObjectName(dock_id)
    dock_widget.setAllowedAreas(QtCore.Qt.AllDockWidgetAreas)
    dock_widget.setWidget(widget)

    if max_win:
        max_win.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock_widget)
        dock_widget.setFloating(True)
        dock_widget.resize(310, 520)
        dock_widget.show()
    else:
        widget.resize(310, 520)
        widget.show()

run()
