
# stylesheet.py - Project Offline QSS stylesheet

MS_PROJECT_STYLE = """
QMainWindow {
    background: #FFFFFF;
    font-family: "Segoe UI", Arial, sans-serif;
}

QMenuBar {
    background: #2B579A;
    color: white;
    font-size: 13px;
    padding: 2px 0;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 12px;
    color: white;
}
QMenuBar::item:selected { background: #3A6EBC; }
QMenuBar::item:pressed  { background: #1A4585; }

QMenu {
    background: white;
    border: 1px solid #AAAAAA;
    padding: 2px 0;
    font-size: 12px;
}
QMenu::item { padding: 6px 30px 6px 20px; color: #1F1F1F; }
QMenu::item:selected { background: #D0E4F7; color: black; }
QMenu::separator { height: 1px; background: #E0E0E0; margin: 3px 8px; }

QToolBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3C71C0, stop:1 #2B579A);
    border: none;
    padding: 4px 6px;
    spacing: 2px;
}
QToolBar::separator {
    background: rgba(255,255,255,0.35);
    width: 1px;
    margin: 3px 4px;
}
QToolBar QToolButton {
    color: white;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 4px 10px;
    font-size: 12px;
    font-weight: bold;
    min-width: 32px;
}
QToolBar QToolButton:hover {
    background: rgba(255,255,255,0.18);
    border: 1px solid rgba(255,255,255,0.5);
}
QToolBar QToolButton:pressed { background: rgba(0,0,0,0.15); }

QTabWidget::pane {
    border: none;
    border-top: 2px solid #2B579A;
    background: white;
}
QTabBar::tab {
    background: #E4EDF8;
    color: #2B579A;
    border: 1px solid #BDD0E8;
    border-bottom: none;
    padding: 6px 16px;
    font-size: 12px;
    font-weight: bold;
    min-width: 80px;
    margin-right: 1px;
}
QTabBar::tab:selected {
    background: white;
    color: #1A3F7A;
    border-top: 2px solid #2B579A;
}
QTabBar::tab:hover:!selected { background: #C5D8F0; }

QTableWidget {
    gridline-color: #D0DDF0;
    background: white;
    alternate-background-color: #F0F5FF;
    selection-background-color: #BDD7EE;
    selection-color: black;
    font-size: 12px;
    border: none;
    outline: none;
}
QTableWidget::item { padding: 3px 6px; border: none; }
QTableWidget::item:selected { background: #BDD7EE; color: black; }

QHeaderView::section {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #ECF3FB, stop:1 #D8E8F5);
    border: none;
    border-right: 1px solid #B0C8E0;
    border-bottom: 2px solid #2B579A;
    padding: 4px 8px;
    font-size: 12px;
    font-weight: bold;
    color: #1A3F7A;
}

QSplitter::handle:horizontal { background: #B8CBE4; width: 4px; }
QSplitter::handle:vertical   { background: #B8CBE4; height: 4px; }

QScrollBar:vertical {
    background: #F0F0F0; width: 12px; border: none;
}
QScrollBar::handle:vertical {
    background: #B0C0D8; border-radius: 6px; min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #2B579A; }
QScrollBar:horizontal {
    background: #F0F0F0; height: 12px; border: none;
}
QScrollBar::handle:horizontal {
    background: #B0C0D8; border-radius: 6px; min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #2B579A; }
QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; }

QStatusBar {
    background: #2B579A;
    color: white;
    font-size: 11px;
    padding: 2px 8px;
}
QStatusBar::item { border: none; }
QStatusBar QLabel { color: white; font-size: 11px; padding: 0 6px; }

QToolTip {
    background: white;
    border: 1px solid #2B579A;
    color: #1F1F1F;
    padding: 4px 6px;
    font-size: 11px;
}

/* --- Ribbon tab buttons --- */
QPushButton#RibbonTab {
    background: #1C3761;
    color: rgba(255, 255, 255, 0.80);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-bottom: 2px solid #3C71C0;
    padding: 5px 16px;
    font-size: 12px;
    font-weight: bold;
    min-width: 60px;
}
QPushButton#RibbonTab:hover:!checked {
    background: #234585;
    color: white;
}
QPushButton#RibbonTab:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                stop:0 #3C71C0, stop:1 #2B579A);
    color: white;
    border: 1px solid rgba(255, 255, 255, 0.20);
    border-bottom: none;
}

/* Thin separator line between tab row and ribbon panel */
#RibbonPanelContainer {
    border-top: 1px solid rgba(255, 255, 255, 0.20);
}

/* Active-view ribbon button highlight */
QToolBar QToolButton:checked {
    background: rgba(120, 190, 255, 0.28);
    border: 1px solid rgba(120, 190, 255, 0.65);
    border-radius: 3px;
}
QToolBar QToolButton:checked:hover {
    background: rgba(120, 190, 255, 0.45);
    border: 1px solid rgba(120, 190, 255, 0.85);
    border-radius: 3px;
}
"""
