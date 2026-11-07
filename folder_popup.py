"""
FolderPopup - 폴더를 '삼성 폰 폴더'처럼 팝업으로 보여주는 Windows용 프로그램

사용법
  python folder_popup.py "C:\\경로\\게임"                 폴더 팝업 열기
  python folder_popup.py "C:\\경로\\게임" --at-cursor     마우스 위치에서 열기
  python folder_popup.py "C:\\경로\\게임" --install       바탕화면에 팝업용 바로가기 만들기

조작
  - 팝업 오른쪽 위 톱니바퀴(⚙): 이름 / 아이콘 크기 / 한 줄 개수 / 배경색 / 투명도 설정
  - 팝업 바깥을 '더블클릭'하면 닫힘 (한 번 클릭은 무시되어 다른 프로그램을 그대로 쓸 수 있음)
  - Esc: 닫기
설정은 %APPDATA%\\FolderPopup\\settings.json 에 폴더별로 저장됩니다.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve, QFileInfo, QPropertyAnimation, QSize, Qt, QTimer,
)
from PyQt6.QtGui import QColor, QCursor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QColorDialog, QDialog, QFileIconProvider, QFormLayout,
    QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

IS_WIN = sys.platform == "win32"
if IS_WIN:
    import ctypes
    user32 = ctypes.windll.user32
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ---------------------------------------------------------------- 기본값
MAX_VISIBLE_ROWS = 4           # 이 줄 수를 넘으면 스크롤
RESOLVE_SHORTCUT_ICON = True   # True: 바로가기(.lnk)의 화살표 없이 원본 프로그램 아이콘 사용
HIDDEN_NAMES = {"desktop.ini", "thumbs.db"}
HIDE_EXTENSIONS = {".lnk", ".url"}   # 이름 뒤 확장자 숨김
OUTSIDE_CLICK_TOLERANCE = 16   # 바깥 더블클릭으로 인정할 두 클릭 사이 최대 거리(px)

DEFAULTS = {
    "title": "",        # 비어 있으면 폴더 이름 사용
    "icon_size": 52,    # 아이콘 크기(px)
    "columns": 4,       # 한 줄 아이콘 수 (= 팝업 가로 크기)
    "bg": "#26262a",    # 배경색
    "opacity": 94,      # 배경 불투명도(%)
}

SETTINGS_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "FolderPopup"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

_provider = QFileIconProvider()


# ---------------------------------------------------------------- 설정 저장/불러오기
def _key(folder: Path) -> str:
    return str(folder).lower()


def _read_all() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_settings(folder: Path) -> dict:
    s = dict(DEFAULTS)
    saved = _read_all().get(_key(folder), {})
    for k in DEFAULTS:
        if k in saved:
            s[k] = saved[k]
    s["icon_size"] = max(32, min(96, int(s["icon_size"])))
    s["columns"] = max(1, min(10, int(s["columns"])))
    s["opacity"] = max(40, min(100, int(s["opacity"])))
    if not QColor(str(s["bg"])).isValid():
        s["bg"] = DEFAULTS["bg"]
    return s


def save_settings(folder: Path, s: dict) -> None:
    data = _read_all()
    data[_key(folder)] = {k: s[k] for k in DEFAULTS}
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


# ---------------------------------------------------------------- 테마(색/크기 계산)
class Theme:
    def __init__(self, s: dict):
        self.bg = QColor(s["bg"])
        lum = 0.299 * self.bg.red() + 0.587 * self.bg.green() + 0.114 * self.bg.blue()
        self.light = lum > 150
        self.bg.setAlpha(int(255 * s["opacity"] / 100))
        self.fg = "#1c1c1e" if self.light else "#f2f2f2"
        self.sub = "#55555a" if self.light else "#9a9aa2"
        self.hover = QColor(0, 0, 0, 34) if self.light else QColor(255, 255, 255, 34)
        self.border = QColor(0, 0, 0, 45) if self.light else QColor(255, 255, 255, 28)
        self.icon = s["icon_size"]
        self.cell = max(92, self.icon + 40)


# ---------------------------------------------------------------- 아이콘/이름
def display_name(path: Path) -> str:
    if path.suffix.lower() in HIDE_EXTENSIONS:
        return path.stem
    return path.name


def load_icon(path: Path):
    """파일/바로가기의 아이콘을 가져온다."""
    info = QFileInfo(str(path))
    if RESOLVE_SHORTCUT_ICON and path.suffix.lower() == ".lnk":
        target = info.symLinkTarget()
        if target and os.path.exists(target):
            icon = _provider.icon(QFileInfo(target))
            if not icon.isNull():
                return icon
    return _provider.icon(info)


# ---------------------------------------------------------------- 아이콘 칸
class Item(QWidget):
    def __init__(self, path: Path, on_open, theme: Theme):
        super().__init__()
        self.path = path
        self.on_open = on_open
        self.theme = theme
        self._hover = False
        self.setFixedWidth(theme.cell)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(str(path))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 8)
        lay.setSpacing(6)

        icon_label = QLabel()
        icon_label.setFixedHeight(theme.icon)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setPixmap(load_icon(path).pixmap(QSize(theme.icon, theme.icon)))
        lay.addWidget(icon_label)

        name = QLabel(display_name(path))
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        name.setFixedHeight(34)
        name.setStyleSheet(f"color:{theme.fg}; font-size:11px; background:transparent;")
        lay.addWidget(name)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.on_open(self.path)

    def paintEvent(self, e):
        if self._hover:
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(self.theme.hover)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect(), 12, 12)


# ---------------------------------------------------------------- 톱니바퀴 버튼
class GearButton(QLabel):
    def __init__(self, theme: Theme, on_click):
        super().__init__("\u2699")
        self.theme = theme
        self.on_click = on_click
        self.setFixedSize(30, 30)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("폴더 설정")
        self._style(False)

    def _style(self, hover: bool):
        color = self.theme.fg if hover else self.theme.sub
        bg = "rgba(128,128,128,70)" if hover else "transparent"
        self.setStyleSheet(
            f"color:{color}; font-size:19px; background:{bg}; border-radius:15px;"
        )

    def enterEvent(self, e):
        self._style(True)

    def leaveEvent(self, e):
        self._style(False)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.on_click()


# ---------------------------------------------------------------- 설정 창
DIALOG_QSS = """
QDialog { background:#2b2b30; }
QLabel { color:#ececf0; font-size:12px; }
QLineEdit, QSpinBox {
    background:#3a3a41; color:#f2f2f2; border:1px solid #55555e;
    border-radius:6px; padding:5px 8px; min-width:140px;
}
QSlider::groove:horizontal { height:4px; background:#55555e; border-radius:2px; }
QSlider::sub-page:horizontal { background:#8ab4ff; border-radius:2px; }
QSlider::handle:horizontal {
    background:#8ab4ff; width:14px; height:14px; margin:-5px 0; border-radius:7px;
}
QPushButton {
    background:#3f3f47; color:#f2f2f2; border:none; border-radius:6px; padding:7px 16px;
}
QPushButton:hover { background:#4d4d57; }
QPushButton#primary { background:#4c8dff; }
QPushButton#primary:hover { background:#6aa0ff; }
"""


class SettingsDialog(QDialog):
    PRESETS = ["#26262a", "#1d3557", "#3d2c5e", "#1e4d3b", "#5a2b2b", "#f2f2f2"]

    def __init__(self, parent, s: dict, default_title: str):
        super().__init__(parent)
        self.setWindowTitle("폴더 설정")
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setStyleSheet(DIALOG_QSS)
        self.default_title = default_title
        self.bg = s["bg"]

        self.name = QLineEdit(s["title"])
        self.name.setPlaceholderText(default_title)

        self.size, size_row = self._slider(32, 96, s["icon_size"], "px")

        self.cols = QSpinBox()
        self.cols.setRange(2, 8)
        self.cols.setValue(min(max(s["columns"], 2), 8))
        self.cols.setSuffix(" 개")

        self.opacity, opacity_row = self._slider(40, 100, s["opacity"], "%")

        # 색 선택 줄
        color_row = QWidget()
        cl = QHBoxLayout(color_row)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(6)
        for c in self.PRESETS:
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton{{background:{c}; border:2px solid #77777f; border-radius:13px; padding:0;}}"
                "QPushButton:hover{border:2px solid #ffffff;}"
            )
            b.clicked.connect(lambda _=False, col=c: self._set_bg(col))
            cl.addWidget(b)
        pick = QPushButton("직접 선택")
        pick.clicked.connect(self._pick_color)
        cl.addWidget(pick)
        self.preview = QLabel()
        self.preview.setFixedSize(40, 26)
        cl.addWidget(self.preview)
        cl.addStretch(1)
        self._set_bg(self.bg)

        form = QFormLayout()
        form.setSpacing(14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("폴더 이름", self.name)
        form.addRow("아이콘 크기", size_row)
        form.addRow("한 줄 아이콘 수", self.cols)
        form.addRow("배경색", color_row)
        form.addRow("투명도", opacity_row)

        reset = QPushButton("기본값")
        reset.clicked.connect(self._reset)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        save = QPushButton("저장")
        save.setObjectName("primary")
        save.setDefault(True)
        save.clicked.connect(self.accept)

        btns = QHBoxLayout()
        btns.addWidget(reset)
        btns.addStretch(1)
        btns.addWidget(cancel)
        btns.addWidget(save)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(18)
        root.addLayout(form)
        root.addLayout(btns)

    @staticmethod
    def _slider(lo, hi, val, suffix):
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(val)
        sl.setMinimumWidth(180)
        lab = QLabel(f"{val}{suffix}")
        lab.setFixedWidth(46)
        sl.valueChanged.connect(lambda v: lab.setText(f"{v}{suffix}"))
        lay.addWidget(sl, 1)
        lay.addWidget(lab)
        return sl, row

    def _set_bg(self, color: str):
        self.bg = color
        self.preview.setStyleSheet(
            f"background:{color}; border:2px solid #77777f; border-radius:6px;"
        )

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.bg), self, "배경색 선택")
        if c.isValid():
            self._set_bg(c.name())

    def _reset(self):
        self.name.setText("")
        self.size.setValue(DEFAULTS["icon_size"])
        self.cols.setValue(DEFAULTS["columns"])
        self.opacity.setValue(DEFAULTS["opacity"])
        self._set_bg(DEFAULTS["bg"])

    def values(self) -> dict:
        title = self.name.text().strip()
        if title == self.default_title:
            title = ""
        return {
            "title": title,
            "icon_size": self.size.value(),
            "columns": self.cols.value(),
            "bg": self.bg,
            "opacity": self.opacity.value(),
        }


# ---------------------------------------------------------------- 팝업 창
class FolderPopup(QWidget):
    def __init__(self, folder: Path, settings: dict, at_cursor: bool):
        super().__init__()
        self.folder = folder
        self.s = settings
        self.at_cursor = at_cursor
        self._dialog_open = False
        self._content = None
        self._was_down = False
        self._last_outside = None   # (시각, 위치)

        # Popup 플래그를 쓰면 바깥을 '한 번'만 눌러도 닫히므로,
        # 일반 창(Tool)으로 만들고 바깥 클릭은 직접 감지한다.
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(folder.name)

        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.build()
        self.adjustSize()

        self.timer = QTimer(self)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._poll)

    # -- 내용 만들기 (설정이 바뀌면 다시 호출)
    def build(self):
        s = self.s
        th = self.theme = Theme(s)
        columns = s["columns"]
        files = self._list_items()

        rows = max(1, -(-len(files) // columns))
        row_h = th.icon + 56 + 2
        visible_rows = min(rows, MAX_VISIBLE_ROWS)
        cols_used = min(max(len(files), 1), columns) if files else columns
        width = max(cols_used * (th.cell + 2), 220)
        scroll_w = width + (10 if rows > MAX_VISIBLE_ROWS else 0)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(18, 12, 18, 14)
        lay.setSpacing(8)

        # 맨 윗줄: [빈칸] 제목 [톱니바퀴]
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        spacer = QWidget()
        spacer.setFixedSize(30, 30)
        title_text = s["title"].strip() or self.folder.name
        title = QLabel()
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{th.fg}; font-size:16px; font-weight:600; background:transparent;"
        )
        title.setText(
            title.fontMetrics().elidedText(
                title_text, Qt.TextElideMode.ElideRight, max(scroll_w - 72, 80)
            )
        )
        title.setToolTip(title_text)
        top.addWidget(spacer)
        top.addWidget(title, 1)
        top.addWidget(GearButton(th, self.open_settings))
        lay.addLayout(top)

        grid_host = QWidget()
        grid_host.setStyleSheet("background:transparent;")
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        for i, f in enumerate(files):
            grid.addWidget(Item(f, self.open_item, th), i // columns, i % columns)
        if not files:
            empty = QLabel("비어 있는 폴더입니다")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color:{th.sub}; padding:30px; background:transparent;")
            grid.addWidget(empty, 0, 0, 1, columns)

        handle = "rgba(0,0,0,90)" if th.light else "rgba(255,255,255,70)"
        scroll = QScrollArea()
        scroll.setWidget(grid_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            f"QScrollBar::handle:vertical{{background:{handle};border-radius:3px;}}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        scroll.viewport().setStyleSheet("background:transparent;")
        scroll.setFixedSize(scroll_w, visible_rows * row_h if files else 90)
        lay.addWidget(scroll)

        link = QLabel("탐색기에서 열기")
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.setStyleSheet(f"color:{th.sub}; font-size:11px; background:transparent;")
        link.mouseReleaseEvent = lambda e: self.open_in_explorer()
        lay.addWidget(link)

        self.outer.addWidget(content)
        self._content = content

    def rebuild(self):
        center = self.frameGeometry().center()
        old = self._content
        if old is not None:
            self.outer.removeWidget(old)
            old.setParent(None)
            old.deleteLater()
        self.build()
        self.adjustSize()
        g = self.frameGeometry()
        g.moveCenter(center)
        self._move_clamped(g.x(), g.y())
        self.update()

    # -- 내용 읽기
    def _list_items(self):
        try:
            items = [
                p for p in self.folder.iterdir()
                if p.name.lower() not in HIDDEN_NAMES and not p.name.startswith(".")
            ]
        except OSError:
            return []
        items.sort(key=lambda p: (not p.is_dir(), display_name(p).lower()))
        return items

    # -- 동작
    def open_item(self, path: Path):
        try:
            os.startfile(str(path))
        except OSError as err:
            QMessageBox.warning(None, "열 수 없음", f"{path.name}\n\n{err}")
        self.close()

    def open_in_explorer(self):
        os.startfile(str(self.folder))
        self.close()

    def open_settings(self):
        self._dialog_open = True
        dlg = SettingsDialog(self, self.s, self.folder.name)
        accepted = dlg.exec()
        self._dialog_open = False
        self._last_outside = None
        self._was_down = self._pressed()
        if accepted:
            self.s = dlg.values()
            save_settings(self.folder, self.s)
            self.rebuild()
        self.activateWindow()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, e):
        self.timer.stop()
        super().closeEvent(e)

    # -- 바깥 더블클릭 감지
    def _pressed(self) -> bool:
        if not IS_WIN:
            return False
        vk = 0x02 if user32.GetSystemMetrics(23) else 0x01   # 마우스 버튼 좌우 바꿈 대응
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    def _poll(self):
        if self._dialog_open:
            return
        down = self._pressed()
        if down and not self._was_down:
            self._on_press(QCursor.pos())
        self._was_down = down

    def _on_press(self, pos):
        if self.frameGeometry().contains(pos):
            self._last_outside = None
            return
        now = time.monotonic()
        limit = user32.GetDoubleClickTime() / 1000.0 if IS_WIN else 0.5
        last = self._last_outside
        if (
            last
            and now - last[0] <= limit
            and abs(pos.x() - last[1].x()) <= OUTSIDE_CLICK_TOLERANCE
            and abs(pos.y() - last[1].y()) <= OUTSIDE_CLICK_TOLERANCE
        ):
            self.close()
        else:
            self._last_outside = (now, pos)

    # -- 모양
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1).toRectF(), 26, 26)
        p.fillPath(path, self.theme.bg)
        p.setPen(self.theme.border)
        p.drawPath(path)

    # -- 위치/표시
    def _move_clamped(self, x, y):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = max(area.left() + 8, min(x, area.right() - self.width() - 8))
        y = max(area.top() + 8, min(y, area.bottom() - self.height() - 8))
        self.move(x, y)

    def show_animated(self):
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        if self.at_cursor:
            pos = QCursor.pos()
            x = pos.x() - self.width() // 2
            y = pos.y() - self.height() - 12
            if y < area.top():
                y = pos.y() + 12
        else:
            x = area.center().x() - self.width() // 2
            y = area.center().y() - self.height() // 2
        self._move_clamped(x, y)

        self.setWindowOpacity(0.0)
        self.show()
        self.activateWindow()
        self.raise_()
        self._was_down = self._pressed()   # 팝업을 띄운 그 클릭은 세지 않는다
        self.timer.start()
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(140)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()


# ---------------------------------------------------------------- 같은 폴더 팝업 중복 실행 방지
_mutex_handle = None


def already_open(folder: Path) -> bool:
    global _mutex_handle
    if not IS_WIN:
        return False
    name = "Local\\FolderPopup_" + hashlib.md5(_key(folder).encode("utf-8")).hexdigest()
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    ctypes.set_last_error(0)
    _mutex_handle = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() == 183   # ERROR_ALREADY_EXISTS


# ---------------------------------------------------------------- 바탕화면 바로가기 만들기
def make_desktop_shortcut(folder: Path, at_cursor: bool) -> str:
    """바탕화면에 '폴더 이름.lnk' 를 만든다. 더블클릭하면 팝업이 뜬다."""
    extra = " --at-cursor" if at_cursor else ""
    if getattr(sys, "frozen", False):
        target = sys.executable
        args = f'"{folder}"{extra}'
    else:
        py = Path(sys.executable)
        pyw = py.with_name("pythonw.exe")
        target = str(pyw if pyw.exists() else py)
        args = f'"{Path(__file__).resolve()}" "{folder}"{extra}'

    ps = (
        "$d=[Environment]::GetFolderPath('Desktop');"
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut("
        "(Join-Path $d ($env:FP_NAME + '.lnk')));"
        "$s.TargetPath=$env:FP_TARGET;$s.Arguments=$env:FP_ARGS;"
        "$s.IconLocation='shell32.dll,4';$s.Save();"
        "Write-Output (Join-Path $d ($env:FP_NAME + '.lnk'))"
    )
    env = dict(os.environ, FP_NAME=folder.name, FP_TARGET=target, FP_ARGS=args)
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip() or "바로가기 생성 실패")
    return out.stdout.strip()


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="폴더를 팝업으로 열어주는 프로그램")
    ap.add_argument("folder", nargs="?", help="팝업으로 보여줄 폴더 경로")
    ap.add_argument("--at-cursor", action="store_true", help="마우스 위치 근처에서 열기")
    ap.add_argument("--columns", type=int, default=None, help="한 줄 아이콘 수(이번 실행에만 적용)")
    ap.add_argument("--install", action="store_true", help="바탕화면에 팝업용 바로가기 만들기")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    if not args.folder:
        QMessageBox.information(
            None, "FolderPopup",
            "폴더 경로를 지정해 주세요.\n\n예)  FolderPopup.exe \"D:\\Folders\\게임\"\n"
            "바탕화면 바로가기 만들기:  FolderPopup.exe \"D:\\Folders\\게임\" --install",
        )
        return 1

    folder = Path(args.folder).expanduser()
    if not folder.is_dir():
        QMessageBox.critical(None, "FolderPopup", f"폴더를 찾을 수 없습니다:\n{folder}")
        return 1
    folder = folder.resolve()

    if args.install:
        try:
            lnk = make_desktop_shortcut(folder, args.at_cursor)
        except Exception as err:
            QMessageBox.critical(None, "FolderPopup", str(err))
            return 1
        QMessageBox.information(
            None, "FolderPopup",
            f"바탕화면에 바로가기를 만들었습니다.\n{lnk}\n\n"
            "바탕화면에 같은 이름의 원본 폴더가 있다면 다른 곳으로 옮겨 두세요.",
        )
        return 0

    if already_open(folder):
        return 0

    settings = load_settings(folder)
    if args.columns:
        settings["columns"] = max(1, args.columns)

    popup = FolderPopup(folder, settings, args.at_cursor)
    popup.show_animated()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
