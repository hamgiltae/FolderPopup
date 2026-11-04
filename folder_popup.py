"""
FolderPopup - 폴더를 '삼성 폰 폴더'처럼 팝업으로 보여주는 Windows용 프로그램

사용법
  python folder_popup.py "C:\\경로\\게임"                 폴더 팝업 열기
  python folder_popup.py "C:\\경로\\게임" --at-cursor     마우스 위치에서 열기
  python folder_popup.py "C:\\경로\\게임" --install       바탕화면에 팝업용 바로가기 만들기
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import (
    QEasingCurve, QFileInfo, QPropertyAnimation, QSize, Qt,
)
from PyQt6.QtGui import QColor, QCursor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QFileIconProvider, QFrame, QGridLayout, QLabel,
    QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

# ---------------------------------------------------------------- 설정값
COLUMNS = 4              # 한 줄에 보여줄 아이콘 수
ICON_SIZE = 52           # 아이콘 크기(px)
CELL_WIDTH = 92          # 아이콘 한 칸 너비
MAX_VISIBLE_ROWS = 4     # 이 줄 수를 넘으면 스크롤
RESOLVE_SHORTCUT_ICON = True   # True: 바로가기(.lnk)의 화살표 없이 원본 프로그램 아이콘 사용
HIDDEN_NAMES = {"desktop.ini", "thumbs.db"}
HIDE_EXTENSIONS = {".lnk", ".url"}   # 이름 뒤 확장자 숨김

BG = QColor(38, 38, 42, 240)
HOVER = QColor(255, 255, 255, 30)
TEXT = "#f2f2f2"
SUBTEXT = "#9a9aa2"

_provider = QFileIconProvider()


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
    def __init__(self, path: Path, on_open):
        super().__init__()
        self.path = path
        self.on_open = on_open
        self._hover = False
        self.setFixedWidth(CELL_WIDTH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(str(path))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 8, 4, 8)
        lay.setSpacing(6)

        icon_label = QLabel()
        icon_label.setFixedHeight(ICON_SIZE)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setPixmap(load_icon(path).pixmap(QSize(ICON_SIZE, ICON_SIZE)))
        lay.addWidget(icon_label)

        name = QLabel(display_name(path))
        name.setWordWrap(True)
        name.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        name.setFixedHeight(34)
        name.setStyleSheet(f"color:{TEXT}; font-size:11px; background:transparent;")
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
            p.setBrush(HOVER)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect(), 12, 12)


# ---------------------------------------------------------------- 팝업 창
class FolderPopup(QWidget):
    def __init__(self, folder: Path, at_cursor: bool, columns: int):
        super().__init__()
        self.folder = folder
        self.at_cursor = at_cursor
        self.columns = columns

        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(folder.name)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 14)
        outer.setSpacing(10)

        title = QLabel(folder.name)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"color:{TEXT}; font-size:16px; font-weight:600; background:transparent;"
        )
        outer.addWidget(title)

        files = self._list_items()

        grid_host = QWidget()
        grid_host.setStyleSheet("background:transparent;")
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(2)
        for i, f in enumerate(files):
            grid.addWidget(Item(f, self.open_item), i // columns, i % columns)

        if not files:
            empty = QLabel("비어 있는 폴더입니다")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color:{SUBTEXT}; padding:30px; background:transparent;")
            grid.addWidget(empty, 0, 0, 1, columns)

        rows = max(1, -(-len(files) // columns))
        row_h = ICON_SIZE + 34 + 6 + 16 + 2
        visible_rows = min(rows, MAX_VISIBLE_ROWS)
        cols_used = min(max(len(files), 1), columns) if files else columns
        width = cols_used * (CELL_WIDTH + 2)

        scroll = QScrollArea()
        scroll.setWidget(grid_host)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;}"
            "QScrollBar:vertical{width:6px;background:transparent;}"
            "QScrollBar::handle:vertical{background:rgba(255,255,255,70);border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        scroll.viewport().setStyleSheet("background:transparent;")
        scroll.setFixedSize(max(width, 220) + (10 if rows > MAX_VISIBLE_ROWS else 0),
                            visible_rows * row_h if files else 90)
        outer.addWidget(scroll)

        link = QLabel("탐색기에서 열기")
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.setStyleSheet(f"color:{SUBTEXT}; font-size:11px; background:transparent;")
        link.mouseReleaseEvent = lambda e: self.open_in_explorer()
        outer.addWidget(link)

        self.adjustSize()

    # -- 내용 읽기
    def _list_items(self):
        try:
            items = [
                p for p in self.folder.iterdir()
                if p.name.lower() not in HIDDEN_NAMES and not p.name.startswith(".")
            ]
        except OSError:
            return []
        # 폴더 먼저, 그다음 이름순
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

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()

    # -- 모양
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(1, 1, -1, -1).toRectF(), 26, 26)
        p.fillPath(path, BG)
        p.setPen(QColor(255, 255, 255, 25))
        p.drawPath(path)

    def show_animated(self):
        screen = (QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen())
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
        x = max(area.left() + 8, min(x, area.right() - self.width() - 8))
        y = max(area.top() + 8, min(y, area.bottom() - self.height() - 8))
        self.move(x, y)

        self.setWindowOpacity(0.0)
        self.show()
        self.activateWindow()
        self.raise_()
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(140)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()


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
    ap.add_argument("--columns", type=int, default=COLUMNS, help="한 줄 아이콘 수")
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

    popup = FolderPopup(folder, args.at_cursor, max(1, args.columns))
    popup.show_animated()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
