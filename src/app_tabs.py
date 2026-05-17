# app_tabs.py — Named constants for QTabWidget (app) tab indices and
#               ribbon tab indices used throughout the application.
#
# HOW TO USE
# ----------
# Import the constants you need:
#
#   from app_tabs import TAB_GANTT, TAB_RESOURCES, RIBBON_TASK, RIBBON_RESOURCE
#
# HOW TO ADD A NEW VIEW
# ---------------------
# 1. Add a TAB_* constant here (next free integer).
# 2. Add the corresponding addTab() call in ui.py MainWindow.__init__.
# 3. Update the dictionaries in ui.py (_TAB_LABELS, _ZOOM_APP_TABS,
#    _APP_TO_RIBBON_TAB, _RIBBON_APP_TABS, _TAB_TO_HISTORY_VIEW,
#    _last_app_tab_for_ribbon).
# 4. Update _view_btns_by_app_tab and _hidden_groups_by_app_tab in
#    ribbon.py if the view needs a ribbon button or changes button
#    visibility.

# ---------------------------------------------------------------------------
# App tab indices  (order must match QTabWidget.addTab() calls in ui.py)
# ---------------------------------------------------------------------------
TAB_GANTT          = 0   # Gantt Chart  (TaskView + GanttView splitter)
TAB_RESOURCES      = 1   # Resource Sheet
TAB_DEPENDENCIES   = 2   # Dependencies
TAB_BASELINE       = 3   # Baseline Tracking
TAB_TEAM_PLANNER   = 4   # Team Planner
TAB_TASK_SHEET     = 5   # Task Sheet  ← default view on startup
TAB_RESOURCE_USAGE = 6   # Resource Usage Graph
TAB_TIMELINE       = -1  # Virtual identifier for the Timeline overlay strip.
                          # The timeline is NOT a tab in the QTabWidget; it is a
                          # pinned strip above the tab area.  -1 is used so that
                          # comparisons against self.tabs.currentIndex() (always
                          # >= 0) can never accidentally match.
TAB_CPM            = 7   # CPM Results panel (read-only critical-path analysis table)

# ---------------------------------------------------------------------------
# Ribbon tab indices  (order must match ProjectRibbon.TAB_NAMES)
# ---------------------------------------------------------------------------
RIBBON_TASK      = 0   # "TASK"     ribbon tab
RIBBON_RESOURCE  = 1   # "RESOURCE" ribbon tab
RIBBON_REPORT    = 2   # "REPORT"   ribbon tab
RIBBON_BASELINE  = 3   # "BASELINE" ribbon tab
RIBBON_VCS       = 4   # "VERSION CONTROL" ribbon tab  (shown only when repo detected)
