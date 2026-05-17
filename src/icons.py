# icons.py - Generates QIcon objects for the ribbon buttons.
#
# All icons are rendered at runtime by painting Unicode symbols or simple
# shapes onto a QPixmap — no external image files required.

from PyQt5.QtWidgets import QApplication, QStyle  # type: ignore
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QFont, QColor  # type: ignore
from PyQt5.QtCore import Qt, QRect, QSize  # type: ignore


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _icon_from_glyph(glyph: str, color: str = "#FFFFFF", size: int = 24) -> QIcon:
    """Paint a single Unicode glyph centred on a transparent pixmap."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    font = QFont("Segoe UI Symbol", int(size * 0.55))
    font.setWeight(QFont.Bold)
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(QRect(0, 0, size, size), Qt.AlignCenter, glyph)
    p.end()
    return QIcon(px)


def _std(sp) -> QIcon:
    """Return a Qt standard pixmap icon."""
    return QApplication.style().standardIcon(sp)


# ---------------------------------------------------------------------------
# Public icon accessors
# ---------------------------------------------------------------------------

def gantt_chart() -> QIcon:
    return _icon_from_glyph("📊")

def resource_sheet() -> QIcon:
    return _icon_from_glyph("👥")

def paste() -> QIcon:
    return _std(QStyle.SP_DialogSaveButton)

def cut() -> QIcon:
    return _icon_from_glyph("✂")

def copy() -> QIcon:
    return _icon_from_glyph("⎘")

def insert_task() -> QIcon:
    return _icon_from_glyph("➕")

def delete_task() -> QIcon:
    return _icon_from_glyph("✖")

def add_resource() -> QIcon:
    return _icon_from_glyph("➕")

def add_resource_from_ad() -> QIcon:
    return _icon_from_glyph("🔍")

def delete_resource() -> QIcon:
    return _icon_from_glyph("✖")

def export_svg() -> QIcon:
    return _icon_from_glyph("📤")

def export_plantuml() -> QIcon:
    return _icon_from_glyph("📄")

def dependencies() -> QIcon:
    return _icon_from_glyph("🔗")

def baseline() -> QIcon:
    return _icon_from_glyph("📏")

def team_planner() -> QIcon:
    return _icon_from_glyph("📅")

def sync_calendar() -> QIcon:
    return _icon_from_glyph("🔄")

def confluence_settings() -> QIcon:
    return _icon_from_glyph("⚙")

def task_sheet() -> QIcon:
    return _icon_from_glyph("📋")

def resource_usage_graph() -> QIcon:
    return _icon_from_glyph("📈")

def set_baseline_icon() -> QIcon:
    return _icon_from_glyph("📌")

def clear_baseline_icon() -> QIcon:
    return _icon_from_glyph("🗑")

def view_baseline_icon() -> QIcon:
    return _icon_from_glyph("📋")

def diff_bars_icon() -> QIcon:
    return _icon_from_glyph("⊟", "#4444CC")

def diff_delta_icon() -> QIcon:
    return _icon_from_glyph("Δ", "#2B579A")

def split_task_icon() -> QIcon:
    return _icon_from_glyph("⋯", "#2B579A")

def merge_task_icon() -> QIcon:
    return _icon_from_glyph("⊞", "#2B579A")

def vcs_config_icon() -> QIcon:
    return _icon_from_glyph("⚙", "#5D4037")

def vcs_commit_icon() -> QIcon:
    return _icon_from_glyph("✔", "#388E3C")

def vcs_log_icon() -> QIcon:
    return _icon_from_glyph("📜")

def vcs_branch_icon() -> QIcon:
    return _icon_from_glyph("⑂", "#1976D2")

def vcs_update_icon() -> QIcon:
    return _icon_from_glyph("⬇", "#1976D2")

def email_send_icon() -> QIcon:
    return _icon_from_glyph("✉")
