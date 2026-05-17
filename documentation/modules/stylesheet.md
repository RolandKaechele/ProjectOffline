# stylesheet.py

Defines `MS_PROJECT_STYLE`, the global QSS string that is applied to
`MainWindow` via `self.setStyleSheet(MS_PROJECT_STYLE)`.  It gives the
application an MS Project-style visual theme using the `#2B579A` blue palette.

## `MS_PROJECT_STYLE`

A single module-level string constant.  It covers the following Qt widget
classes:

| Widget | Key visual rules |
| - | - |
| `QMainWindow` | White background, Segoe UI font |
| `QMenuBar` | `#2B579A` blue background, white text; hover `#3A6EBC`, pressed `#1A4585` |
| `QMenu` | White background, 12 px font, `#D0E4F7` selection highlight |
| `QToolBar` | Vertical linear gradient `#3C71C0 → #2B579A`; white semi-transparent button hover/press states |
| `QTabWidget` / `QTabBar` | Light blue inactive tabs, white selected tab with a 2-px blue top border |
| `QTableWidget` | `#D0DDF0` grid lines, `#BDD7EE` selection, `#F0F5FF` alternating rows |
| `QHeaderView::section` | Vertical gradient `#ECF3FB → #D8E8F5`, 2-px blue bottom border |
| `QSplitter::handle` | `#B8CBE4` (4 px horizontal, 4 px vertical) |
| `QScrollBar` | Thin (12 px) flat scrollbars with `#B0C0D8` handles; hover turns `#2B579A` |
| `QStatusBar` | `#2B579A` blue, white 11 px text |
| `QToolTip` | White background, `#2B579A` border, 11 px font |
