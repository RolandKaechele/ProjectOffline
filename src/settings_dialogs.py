# settings_dialogs.py - Configuration dialogs for KeePass and Jira
#
# KeePassConfigDialog     – open an existing or create a new KeePass database
# KeePassNewEntryDialog   – add a new entry to the open KeePass database
# JiraServerEditDialog    – add / edit a single Jira server configuration
# JiraServersDialog       – manage the full list of Jira server configurations

from PyQt5.QtWidgets import (  # type: ignore
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QListWidget, QWidget, QFrame,
    QGroupBox, QFileDialog, QMessageBox,
    QAbstractItemView, QDialogButtonBox, QCheckBox,
    QRadioButton, QButtonGroup, QStackedWidget, QToolButton, QInputDialog,
    QScrollArea, QSizePolicy, QTabWidget, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import Qt  # type: ignore
from PyQt5.QtGui import QIntValidator  # type: ignore


# ------------------------------------------------------------------ #
# Shared styles (match dialogs.py colour palette)                      #
# ------------------------------------------------------------------ #

_DIALOG_STYLE = """
QDialog { background: white; font-family: "Segoe UI", Arial, sans-serif; }
QLineEdit, QComboBox {
    border: 1px solid #B8CBE4; padding: 3px 6px;
    font-size: 12px; border-radius: 2px;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #2B579A; }
QLineEdit[readOnly="true"] { background: #F5F5F5; color: #555; }
QLabel { font-size: 12px; color: #1F1F1F; }
QListWidget {
    border: 1px solid #B8CBE4; font-size: 12px;
    selection-background-color: #BDD7EE; selection-color: black;
    alternate-background-color: #F0F5FF;
}
QGroupBox {
    font-size: 12px; font-weight: bold; color: #2B579A;
    border: 1px solid #B8CBE4; border-radius: 3px;
    margin-top: 8px; padding-top: 6px;
}
QGroupBox::title { subcontrol-origin: margin; left: 8px; }
QRadioButton { font-size: 12px; }
QCheckBox    { font-size: 12px; }
"""

_BUTTON_STYLE = """
QPushButton {
    background: #2B579A; color: white; border: none;
    border-radius: 3px; padding: 5px 20px; font-size: 12px;
    min-width: 72px;
}
QPushButton:hover   { background: #3A6EBC; }
QPushButton:pressed { background: #1A4585; }
QPushButton[flat="true"] {
    background: #E4EDF8; color: #2B579A; border: 1px solid #BDD0E8;
}
QPushButton[flat="true"]:hover { background: #C5D8F0; }
QPushButton:disabled { background: #B0B8C8; color: #E0E0E0; }
"""

_TOGGLE_STYLE = (
    "QToolButton { border: 1px solid #B8CBE4; padding: 2px 6px; "
    "font-size: 11px; border-radius: 2px; background: #F5F5F5; }"
    "QToolButton:checked { background: #E4EDF8; }"
)


# ------------------------------------------------------------------ #
# Shared helpers                                                       #
# ------------------------------------------------------------------ #

def _make_header(title: str, subtitle: str = "") -> QFrame:
    """Blue MS-Project-style dialog header."""
    frame = QFrame()
    frame.setStyleSheet("background: #2B579A; border: none;")
    frame.setFixedHeight(52 if not subtitle else 68)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 8, 8, 8)
    layout.setSpacing(2)
    lbl = QLabel(title)
    lbl.setStyleSheet("color: white; font-size: 14px; font-weight: bold; background: transparent;")
    layout.addWidget(lbl)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setStyleSheet("color: #CCE0FF; font-size: 11px; background: transparent;")
        layout.addWidget(sub)
    return frame


def _btn(label: str, flat: bool = False) -> QPushButton:
    b = QPushButton(label)
    if flat:
        b.setProperty("flat", "true")
    b.setStyleSheet(_BUTTON_STYLE)
    return b


def _button_row(*buttons) -> QWidget:
    """Return a right-aligned row of buttons."""
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(12, 6, 12, 12)
    h.addStretch()
    for b in buttons:
        h.addWidget(b)
    return row


def _pwd_field_row(form_layout: QFormLayout, label: str, placeholder: str = "") -> QLineEdit:
    """Add a password row with Show/Hide toggle to a QFormLayout. Returns the QLineEdit."""
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.Password)
    edit.setPlaceholderText(placeholder)
    toggle = QToolButton()
    toggle.setText("Show")
    toggle.setCheckable(True)
    toggle.setStyleSheet(_TOGGLE_STYLE)
    toggle.toggled.connect(
        lambda checked: edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
    )
    toggle.toggled.connect(lambda checked: toggle.setText("Hide" if checked else "Show"))
    row_w = QWidget()
    row_h = QHBoxLayout(row_w)
    row_h.setContentsMargins(0, 0, 0, 0)
    row_h.addWidget(edit)
    row_h.addWidget(toggle)
    form_layout.addRow(label, row_w)
    return edit


def _browse_row(
    form_layout: QFormLayout,
    label: str,
    placeholder: str,
    existing: str,
    browse_slot,
) -> QLineEdit:
    """Add a (QLineEdit + Browse button) row to a QFormLayout. Returns the QLineEdit."""
    edit = QLineEdit(existing)
    edit.setPlaceholderText(placeholder)
    browse = _btn("Browse\u2026", flat=True)
    browse.setMinimumWidth(80)
    browse.clicked.connect(browse_slot)
    row_w = QWidget()
    row_h = QHBoxLayout(row_w)
    row_h.setContentsMargins(0, 0, 0, 0)
    row_h.addWidget(edit)
    row_h.addWidget(browse)
    form_layout.addRow(label, row_w)
    return edit


def _kf_row(
    form_layout: QFormLayout,
    label: str,
    existing: str,
    browse_slot,
    generate_slot,
) -> QLineEdit:
    """Key-file row: QLineEdit + Browse… + Generate… buttons."""
    edit = QLineEdit(existing)
    edit.setPlaceholderText("Optional \u2014 path to .keyx key file")
    browse = _btn("Browse\u2026", flat=True)
    browse.setMinimumWidth(80)
    browse.clicked.connect(browse_slot)
    generate = _btn("Generate\u2026", flat=True)
    generate.setMinimumWidth(90)
    generate.clicked.connect(generate_slot)
    row_w = QWidget()
    row_h = QHBoxLayout(row_w)
    row_h.setContentsMargins(0, 0, 0, 0)
    row_h.addWidget(edit)
    row_h.addWidget(browse)
    row_h.addWidget(generate)
    form_layout.addRow(label, row_w)
    return edit


_JIRA_SYNC_FIELD_SECTIONS = [
    (
        "Core Information",
        [
            ("jira_project_name", "Project Name", "Jira project name (descriptive alternative to project key)", "project"),
            ("jira_description", "Description", "Issue description text (wiki/markdown format)", "description"),
        ],
    ),
    (
        "Status and Resolution",
        [
            ("jira_status", "Status", "Current issue status (e.g., 'To Do', 'In Progress', 'Done')", "status"),
            ("jira_status_percent", "Status Progress %", "Percentage complete derived from status mapping (0-100)", "progress"),
            ("jira_resolution", "Resolution", "Issue resolution value (e.g., 'Fixed', 'Won\'t Fix', 'Duplicate')", "resolution"),
            ("jira_resolution_date", "Resolution Date", "Date/time when issue was resolved", "resolutiondate"),
            ("jira_security_level", "Security Level", "Security level name for restricted access issues", "security"),
        ],
    ),
    (
        "Assignment and Reporter",
        [
            ("jira_assignee", "Assignee", "Assigned user identifier (account ID, username, email, or full name)", "assignee"),
            ("jira_assignee_display_name", "Assignee Display Name", "Assignee's display name for visual reference", "assignee.displayName"),
            ("jira_reporter", "Reporter", "Reporter identifier (account ID, username, email, or full name)", "reporter"),
            ("jira_reporter_display_name", "Reporter Display Name", "Reporter's display name for visual reference", "reporter.displayName"),
        ],
    ),
    (
        "Priority and Dates",
        [
            ("jira_priority", "Priority", "Priority level name (e.g., 'High', 'Medium', 'Low')", "priority"),
            ("jira_due_date", "Due Date", "Issue due date (can map to task Finish field)", "duedate"),
            ("jira_created_date", "Created Date", "Date/time when issue was created", "created"),
            ("jira_updated_date", "Updated Date", "Date/time of last issue update", "updated"),
        ],
    ),
    (
        "Versions and Components",
        [
            ("jira_components", "Components", "Comma-separated list of component names", "components"),
            ("jira_fix_versions", "Fix Versions", "Comma-separated list of target release versions", "fixVersions"),
            ("jira_affects_versions", "Affects Versions", "Comma-separated list of versions where issue occurs", "versions"),
            ("jira_fix_version_description", "Fix Version Description", "Description of the fix version (single version only)", "fixVersions.description"),
            ("jira_fix_version_released", "Fix Version Released", "Whether fix version has been released (single version only)", "fixVersions.released"),
            ("jira_fix_version_start_date", "Fix Version Start Date", "Start date of fix version (single version only)", "fixVersions.startDate"),
            ("jira_fix_version_release_date", "Fix Version Release Date", "Release/due date of fix version (single version only)", "fixVersions.releaseDate"),
        ],
    ),
    (
        "Labels and Metadata",
        [
            ("jira_labels", "Labels", "Comma-separated list of issue labels (requires Jira 4.0+)", "labels"),
            ("jira_environment", "Environment", "Environment information (OS, browser, server config, etc.)", "environment"),
            ("jira_votes", "Votes", "Number of votes the issue has received", "votes"),
            ("jira_comments", "Comments", "Concatenated issue comments (usually appended to Notes field)", "comment"),
        ],
    ),
    (
        "Time Tracking",
        [
            ("jira_time_spent", "Time Spent", "Total time logged on issue (maps to Actual Work)", "timespent"),
            ("jira_remaining_estimate", "Remaining Estimate", "Remaining work estimate (can map to Work field)", "timeestimate"),
            ("jira_original_estimate", "Original Estimate", "Original time estimate before work began", "originalestimate"),
            ("jira_time_spent_seconds", "Time Spent (seconds)", "Time spent in seconds for precise tracking", "timespentSeconds"),
            ("jira_worklog_entries", "Worklog Entries", "Detailed work log entries with user, date, and duration", "worklog"),
        ],
    ),
    (
        "Hierarchy and Relationships",
        [
            ("jira_parent_key", "Parent Key", "Parent issue key for Jira Cloud hierarchy (replaces Epic Link)", "parent"),
            ("jira_epic_link", "Epic Link", "Epic issue key (Jira Server/DC only)", "epicLink"),
            ("jira_parent_link", "Parent Link", "Advanced Roadmaps parent key (Jira Server/DC only)", "parentLink"),
            ("jira_subtask_parent", "Sub-task Parent", "Sub-task parent issue key (Jira Server/DC only)", "subtask_parent"),
            ("jira_issue_links", "Issue Links", "Comma-separated list of linked issue keys for specific link types", "issuelinks"),
        ],
    ),
]

_P2J_JIRA_FIELD_SUGGESTIONS = [
    "summary", "description", "issuetype", "project", "status", "resolution",
    "resolutiondate", "assignee", "reporter", "priority", "duedate",
    "created", "updated", "components", "fixVersions", "versions",
    "labels", "environment", "comment", "timespent", "timeestimate",
    "originalestimate", "worklog", "parent", "epicLink", "issuelinks",
    "security", "votes", "progress", "customfield_10010", "customfield_10014",
]

# Dropdown options for Project -> Jira mapping tables
_P2J_TASK_TYPE_LEFT_OPTIONS = [
    "Task", "Milestone", "Summary", "Deliverable", "Phase",
    "Sub-task", "Work Package",
]
_P2J_TASK_TYPE_RIGHT_OPTIONS = [
    "Story", "Task", "Epic", "Bug", "Sub-task", "Feature",
    "Initiative", "Improvement", "New Feature",
]
_P2J_TRANSITION_LEFT_OPTIONS = [
    "Not Started", "In Progress", "Completed", "Cancelled", "Waiting", "On Hold",
]
_P2J_TRANSITION_RIGHT_OPTIONS = [
    "To Do", "In Progress", "Done", "Closed", "Resolved",
    "Won\u2019t Fix", "Cancelled", "Backlog", "Review",
]

_PROJECT2JIRA_DEFAULTS = {
    "export_scope": "changed_since_last_sync",
    "create_update_mode": "create_update",
    "conflict_policy": "manual_review",
    "dry_run": True,
    "unlinked_task_behavior": "skip",   # create | skip | prompt
    "fields": {
        "jira_project_name": {"enabled": True, "jira_field": "project"},
    },
    "issue_type_map": {
        "Task": "Task",
        "Sub-task": "Sub-task",
    },
    "transition_map": {},
    # Transition names are server-specific; leave empty so users configure
    # the actual transition id/name from their Jira project.
    "hierarchy_export": {
        "enabled": False,
        "epic_type": "Epic",
        "story_type": "Story",
        "subtask_type": "Sub-task",
        "dependency_link_type": "blocks",
    },
    "auditability": {
        "enabled": False,
    },
}

_JIRA2PROJECT_ADVANCED_DEFAULTS = {
    "relink": {"enabled": False, "behavior": "messagebox"},
    "incremental": {"enabled": False, "mode": "changed_since_last_sync"},
    "conflict": {
        "enabled": False,
        "policy": "messagebox",
        "field_policy": {
            "status": "messagebox",
            "dates": "messagebox",
            "assignee": "messagebox",
            "estimate": "messagebox",
            "labels": "messagebox",
        },
    },
    "orphan": {"enabled": False, "behavior": "messagebox"},
    "closed_state_completion": {"enabled": False},
    "normalize": {"enabled": False},
    "hierarchy": {"enabled": False},
    "dependencies": {"enabled": False},
    "reliability": {"enabled": False, "max_retries": 3, "backoff_seconds": 1.0},
    "preview": {"enabled": False, "include_keys": [], "exclude_keys": []},
}

_JIRA2PROJECT_FIELD_DEPENDENCIES = {
    "jira_status_percent": "jira_status",
    "jira_resolution_date": "jira_resolution",
    "jira_assignee_display_name": "jira_assignee",
    "jira_reporter_display_name": "jira_reporter",
    "jira_fix_version_description": "jira_fix_versions",
    "jira_fix_version_released": "jira_fix_versions",
    "jira_fix_version_start_date": "jira_fix_versions",
    "jira_fix_version_release_date": "jira_fix_versions",
    "jira_time_spent_seconds": "jira_time_spent",
    "jira_worklog_entries": "jira_time_spent",
}

_PROJECT2JIRA_REQUIRED_CREATE_FIELDS = {"project"}


# ------------------------------------------------------------------ #
# KeePass Configuration Dialog                                         #
# ------------------------------------------------------------------ #

class KeePassConfigDialog(QDialog):
    """Configure or create a KeePass database.

    Two modes (radio buttons):
    - Open existing: browse for .kdbx, optional key file, master password (saveable)
    - Create new:    new .kdbx path, optional key file + password (at least one required)
    """

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self.setWindowTitle("KeePass Configuration")
        self.setMinimumWidth(580)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        _hdr = _make_header(
            "KeePass Configuration",
            "Open an existing database or create a new one",
        )
        # Keep a reference to the subtitle label for dynamic updates
        self._header_subtitle: QLabel = _hdr.layout().itemAt(1).widget()
        root.addWidget(_hdr)

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 16, 16, 8)
        bv.setSpacing(10)

        # --- Mode selector ---
        mode_row = QHBoxLayout()
        self._rb_open   = QRadioButton("Open existing database")
        self._rb_create = QRadioButton("Create new database")
        bg = QButtonGroup(self)
        bg.addButton(self._rb_open,   0)
        bg.addButton(self._rb_create, 1)
        self._rb_open.setChecked(True)
        mode_row.addWidget(self._rb_open)
        mode_row.addSpacing(16)
        mode_row.addWidget(self._rb_create)
        mode_row.addStretch()
        bv.addLayout(mode_row)

        # --- Stacked pages ---
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_open_page())    # index 0
        self._stack.addWidget(self._build_create_page())  # index 1
        bv.addWidget(self._stack)

        self._rb_open.toggled.connect(self._on_mode_changed)
        self._rb_create.toggled.connect(self._on_mode_changed)

        # --- Status label (shared) ---
        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        bv.addWidget(self._status_lbl)

        # --- Confluence SSO section (visible only when DB is unlocked) ---
        self._confluence_group = QGroupBox("Confluence SSO Auto-fill")
        cf_form = QFormLayout(self._confluence_group)
        cf_form.setSpacing(8)
        cf_form.setLabelAlignment(Qt.AlignRight)
        self._confluence_entry_combo = QComboBox()
        self._confluence_entry_combo.setEditable(True)
        self._confluence_entry_combo.setPlaceholderText("Select or type entry title …")
        self._confluence_entry_combo.setToolTip(
            "KeePass entry whose username and password are auto-filled\n"
            "on the Microsoft SSO login page when syncing Confluence calendars.\n"
            "The TOTP / MFA step is always completed manually."
        )
        cf_form.addRow("KeePass Entry:", self._confluence_entry_combo)
        note = QLabel(
            "Username and password will be pre-filled automatically.\n"
            "The MFA / Authenticator step is always completed by you."
        )
        note.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        note.setWordWrap(True)
        cf_form.addRow("", note)
        self._confluence_group.setVisible(False)
        bv.addWidget(self._confluence_group)

        bv.addStretch()
        root.addWidget(body)

        ok = _btn("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

        # Populate the Confluence combo if the DB is already unlocked
        if self._sm.is_keepass_unlocked():
            self._populate_confluence_combo()

    # ---- Mode switch ----

    def _on_mode_changed(self):
        if self._rb_open.isChecked():
            self._stack.setCurrentIndex(0)
            self._header_subtitle.setText("Open an existing database")
        else:
            self._stack.setCurrentIndex(1)
            self._header_subtitle.setText("Create a new KeePass database")

    # ---- Page builders ----

    def _build_open_page(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 4, 0, 0)
        vbox.setSpacing(6)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._open_db_edit = _browse_row(
            form, "Database File:",
            "Path to .kdbx database file",
            self._sm.get_keepass_db_path(),
            self._browse_open_db,
        )
        self._open_kf_edit = _kf_row(
            form, "Key File:",
            self._sm.get_keepass_key_file(),
            self._browse_open_kf,
            self._generate_open_kf,
        )
        self._open_pwd_edit = _pwd_field_row(form, "Master Password:", "master password")
        self._open_pwd_edit.setText(self._sm.get_keepass_password())

        self._open_save_pwd = QCheckBox("Save password for automatic unlock")
        self._open_save_pwd.setChecked(bool(self._sm.get_keepass_password()))
        form.addRow("", self._open_save_pwd)

        vbox.addLayout(form)

        test_w = QWidget()
        test_h = QHBoxLayout(test_w)
        test_h.setContentsMargins(0, 0, 0, 0)
        test_h.addStretch()
        test_btn = _btn("Unlock", flat=True)
        test_btn.clicked.connect(self._test_connection)
        test_h.addWidget(test_btn)
        vbox.addWidget(test_w)
        return w

    def _build_create_page(self) -> QWidget:
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 4, 0, 0)
        vbox.setSpacing(6)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._new_db_edit = _browse_row(
            form, "New Database File:",
            "Path to the new .kdbx file",
            "",
            self._browse_new_db,
        )
        self._new_kf_edit = _kf_row(
            form, "Key File (optional):",
            "",
            self._browse_new_kf,
            self._generate_new_kf,
        )
        self._new_pwd_edit = _pwd_field_row(
            form, "Password (optional):",
            "Leave empty if using key file only",
        )
        self._new_pwd_confirm_edit = _pwd_field_row(
            form, "Confirm Password:", "repeat password"
        )

        self._new_save_pwd = QCheckBox("Save password for automatic unlock")
        self._new_save_pwd.setChecked(True)
        form.addRow("", self._new_save_pwd)

        note = QLabel(
            "At least one of \u201cPassword\u201d or \u201cKey File\u201d must be provided."
        )
        note.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        note.setWordWrap(True)

        vbox.addLayout(form)
        vbox.addWidget(note)
        return w

    # ---- Browse slots ----

    def _browse_open_db(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select KeePass Database", "",
            "KeePass Database (*.kdbx);;All Files (*)",
        )
        if path:
            self._open_db_edit.setText(path)

    def _browse_open_kf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Key File", "", "KeePass Key File (*.keyx);;All Files (*)"
        )
        if path:
            self._open_kf_edit.setText(path)

    def _generate_open_kf(self):
        self._generate_kf(self._open_kf_edit)

    def _browse_new_db(self):
        import os as _os
        start_dir = _os.path.join(_os.path.expanduser("~"), "Documents")
        if not _os.path.isdir(start_dir):
            start_dir = _os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, "Create KeePass Database", start_dir,
            "KeePass Database (*.kdbx);;All Files (*)",
        )
        if path:
            if not path.lower().endswith(".kdbx"):
                path += ".kdbx"
            self._new_db_edit.setText(path)

    def _browse_new_kf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Key File", "", "KeePass Key File (*.keyx);;All Files (*)"
        )
        if path:
            self._new_kf_edit.setText(path)

    def _generate_new_kf(self):
        self._generate_kf(self._new_kf_edit)

    def _generate_kf(self, target_edit: "QLineEdit"):
        """Prompt for a save path, generate a .keyx file, and fill *target_edit*."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Generate Key File", "",
            "KeePass Key File (*.keyx);;All Files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".keyx"):
            path += ".keyx"
        ok, err = self._sm.generate_key_file(path)
        if ok:
            target_edit.setText(path)
            self._set_status(f"Key file generated: {path}", error=False)
        else:
            self._set_status(f"Could not generate key file: {err}", error=True)

    # ---- Actions ----

    def _test_connection(self):
        db_path = self._open_db_edit.text().strip()
        if not db_path:
            self._set_status("Please enter a database file path.", error=True)
            return
        self._sm.set_keepass_db_path(db_path)
        self._sm.set_keepass_key_file(self._open_kf_edit.text().strip())
        ok, err = self._sm.unlock_keepass(self._open_pwd_edit.text())
        if ok:
            count = len(list(self._sm._keepass_db.entries))
            self._set_status(f"Connection successful \u2014 {count} entries found.", error=False)
            self._populate_confluence_combo()
        else:
            self._set_status(f"Connection failed: {err}", error=True)

    def _populate_confluence_combo(self):
        """Fill the Confluence entry combo with all KeePass entries and show the group."""
        if not self._sm.is_keepass_unlocked():
            self._confluence_group.setVisible(False)
            return
        current = self._sm.get_confluence_keepass_entry()
        if not isinstance(current, str):
            current = ""
        self._confluence_entry_combo.blockSignals(True)
        self._confluence_entry_combo.clear()
        self._confluence_entry_combo.addItem("")   # empty = disabled
        entries = self._sm.list_keepass_entries()
        self._confluence_entry_combo.addItems(entries)
        if current:
            idx = self._confluence_entry_combo.findText(current)
            if idx >= 0:
                self._confluence_entry_combo.setCurrentIndex(idx)
            else:
                self._confluence_entry_combo.setCurrentText(current)
        self._confluence_entry_combo.blockSignals(False)
        self._confluence_group.setVisible(True)

    def _set_status(self, msg: str, error: bool):
        color = "#C00000" if error else "#107C10"
        self._status_lbl.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._status_lbl.setText(msg)

    def _accept(self):
        if self._rb_open.isChecked():
            self._accept_open()
        else:
            self._accept_create()

    def _accept_open(self):
        db_path = self._open_db_edit.text().strip()
        if not db_path:
            self._set_status("Please enter a database file path.", error=True)
            return
        self._sm.set_keepass_db_path(db_path)
        self._sm.set_keepass_key_file(self._open_kf_edit.text().strip())
        if self._open_save_pwd.isChecked():
            self._sm.set_keepass_password(self._open_pwd_edit.text())
        else:
            self._sm.set_keepass_password("")
        if not self._sm.is_keepass_unlocked():
            ok, err = self._sm.unlock_keepass(self._open_pwd_edit.text())
            if not ok:
                self._set_status(f"Could not open database: {err}", error=True)
                return
        self._sm.set_confluence_keepass_entry(self._confluence_entry_combo.currentText().strip())
        self.accept()

    def _accept_create(self):
        import os as _os
        path = self._new_db_edit.text().strip()
        if not path:
            self._set_status("Please specify a path for the new database.", error=True)
            return
        if not path.lower().endswith(".kdbx"):
            path += ".kdbx"
        path = _os.path.abspath(path)
        self._new_db_edit.setText(path)  # show the resolved absolute path
        pwd = self._new_pwd_edit.text()
        kf  = self._new_kf_edit.text().strip()
        if not pwd and not kf:
            self._set_status(
                "Please provide a master password, a key file, or both.", error=True
            )
            return
        if pwd and pwd != self._new_pwd_confirm_edit.text():
            self._set_status("Passwords do not match.", error=True)
            return
        ok, err = self._sm.create_keepass_db(path, pwd or None, kf or None)
        if not ok:
            self._set_status(f"Could not create database: {err}", error=True)
            return
        if self._new_save_pwd.isChecked():
            self._sm.set_keepass_password(pwd)
        self._set_status(f"Database created: {path}", error=False)
        self.accept()


# ------------------------------------------------------------------ #
# KeePass New Entry Dialog                                             #
# ------------------------------------------------------------------ #

class KeePassNewEntryDialog(QDialog):
    """Add a new credential entry to the open KeePass database."""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._entry_path = ""
        self.setWindowTitle("New KeePass Entry")
        self.setMinimumWidth(440)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "New KeePass Entry",
            "Add a new credential entry to the database",
        ))

        body = QWidget()
        form = QFormLayout(body)
        form.setContentsMargins(16, 16, 16, 8)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("e.g. My Jira Account")
        form.addRow("Title:", self._title_edit)

        self._group_edit = QLineEdit()
        self._group_edit.setPlaceholderText("Optional \u2014 group / folder name")
        form.addRow("Group:", self._group_edit)

        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("username or email")
        form.addRow("Username:", self._user_edit)

        self._pwd_edit = _pwd_field_row(form, "Password:", "password or API token")

        root.addWidget(body)

        ok = _btn("Create Entry")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

    def _accept(self):
        title = self._title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "Validation", "Please enter an entry title.")
            return
        group = self._group_edit.text().strip()
        ok, err = self._sm.add_keepass_entry(
            title,
            self._user_edit.text().strip(),
            self._pwd_edit.text(),
            group,
        )
        if not ok:
            QMessageBox.critical(self, "Error", f"Could not create entry:\n{err}")
            return
        self._entry_path = f"{group}/{title}" if group else title
        self.accept()

    def get_entry_path(self) -> str:
        """Return the 'Group/Title' path of the newly created entry."""
        return self._entry_path


# ------------------------------------------------------------------ #
# Jira Server Edit Dialog                                              #
# ------------------------------------------------------------------ #

class JiraServerEditDialog(QDialog):
    """Add or edit a single Jira server configuration."""

    def __init__(self, settings_manager, server: dict | None = None, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._server = dict(server) if server else {
            "name": "", "url": "", "auth_mode": "manual",
            "username": "", "token": "", "credential_type": "token",
            "keepass_entry": "",
        }
        is_edit = server is not None
        self.setWindowTitle("Edit Jira Server" if is_edit else "Add Jira Server")
        self.setMinimumWidth(520)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Jira Server",
            "Edit server settings" if is_edit else "Add a new Jira server connection",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 16, 16, 8)
        bv.setSpacing(10)

        # ---- Basic fields ----
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._name_edit = QLineEdit(self._server.get("name", ""))
        self._name_edit.setPlaceholderText("e.g. My Company Jira")
        form.addRow("Name:", self._name_edit)

        self._url_edit = QLineEdit(self._server.get("url", ""))
        self._url_edit.setPlaceholderText("https://mycompany.atlassian.net")
        form.addRow("URL:", self._url_edit)

        self._auth_combo = QComboBox()
        self._auth_combo.addItem("Manual (username + credential)", "manual")
        self._auth_combo.addItem("From KeePass entry", "keepass")
        self._auth_combo.setCurrentIndex(
            1 if self._server.get("auth_mode") == "keepass" else 0
        )
        self._auth_combo.currentIndexChanged.connect(self._on_auth_mode_changed)
        form.addRow("Authentication:", self._auth_combo)

        bv.addLayout(form)

        # ---- Manual credentials group ----
        self._manual_group = QGroupBox("Credentials")
        self._mg_form = QFormLayout(self._manual_group)
        self._mg_form.setSpacing(8)
        self._mg_form.setLabelAlignment(Qt.AlignRight)

        self._cred_type_combo = QComboBox()
        self._cred_type_combo.addItem("API Token (Jira Cloud)", "token")
        self._cred_type_combo.addItem("Password",  "password")
        self._cred_type_combo.addItem("Personal Access Token (Server/Data Center)", "pat")
        current_type = self._server.get("credential_type", "token")
        if current_type == "pat":
            self._cred_type_combo.setCurrentIndex(2)
        elif current_type == "password":
            self._cred_type_combo.setCurrentIndex(1)
        else:
            self._cred_type_combo.setCurrentIndex(0)
        self._cred_type_combo.currentIndexChanged.connect(self._on_cred_type_changed)
        self._mg_form.addRow("Credential Type:", self._cred_type_combo)

        self._user_edit = QLineEdit(self._server.get("username", ""))
        self._user_edit.setPlaceholderText("username or email")
        self._mg_form.addRow("Username:", self._user_edit)

        # Password/token field — _pwd_field_row adds the row and returns the QLineEdit
        self._token_edit = _pwd_field_row(self._mg_form, "API Token:", "API token or password")
        self._token_edit.setText(self._server.get("token", ""))

        bv.addWidget(self._manual_group)

        # ---- KeePass credentials group ----
        self._kp_group = QGroupBox("KeePass Credentials")
        kp_vbox = QVBoxLayout(self._kp_group)
        kp_vbox.setSpacing(6)

        # Stacked widget: 0 = not configured, 1 = locked, 2 = unlocked
        self._kp_stack = QStackedWidget()

        # Page 0 – KeePass not configured
        p0 = QWidget()
        p0v = QVBoxLayout(p0)
        p0v.setContentsMargins(0, 4, 0, 4)
        p0v.setSpacing(8)
        p0_lbl = QLabel("KeePass is not configured.")
        p0_lbl.setStyleSheet("color: #888; font-size: 12px;")
        cfg_btn = _btn("Configure KeePass\u2026")
        cfg_btn.clicked.connect(self._configure_keepass)
        p0v.addWidget(p0_lbl)
        p0v.addWidget(cfg_btn)
        self._kp_stack.addWidget(p0)

        # Page 1 – configured but locked
        p1 = QWidget()
        p1v = QVBoxLayout(p1)
        p1v.setContentsMargins(0, 4, 0, 4)
        p1v.setSpacing(8)
        p1_lbl = QLabel("KeePass database is locked.")
        p1_lbl.setStyleSheet("color: #888; font-size: 12px;")
        unlock_btn = _btn("Unlock KeePass\u2026")
        unlock_btn.clicked.connect(self._unlock_keepass)
        p1v.addWidget(p1_lbl)
        p1v.addWidget(unlock_btn)
        self._kp_stack.addWidget(p1)

        # Page 2 – unlocked: entry selector + new entry button
        p2 = QWidget()
        p2f = QFormLayout(p2)
        p2f.setContentsMargins(0, 4, 0, 4)
        p2f.setSpacing(8)
        p2f.setLabelAlignment(Qt.AlignRight)

        entry_row_w = QWidget()
        entry_row_h = QHBoxLayout(entry_row_w)
        entry_row_h.setContentsMargins(0, 0, 0, 0)
        self._kp_entry_combo = QComboBox()
        self._kp_entry_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
        entry_row_h.addWidget(self._kp_entry_combo, stretch=1)
        new_entry_btn = _btn("New Entry\u2026", flat=True)
        new_entry_btn.setMinimumWidth(90)
        new_entry_btn.clicked.connect(self._new_kp_entry)
        entry_row_h.addWidget(new_entry_btn)
        p2f.addRow("Entry:", entry_row_w)

        self._kp_stack.addWidget(p2)
        kp_vbox.addWidget(self._kp_stack)
        
        # Credential type for KeePass mode (shared with manual mode logic)
        kp_cred_form = QFormLayout()
        kp_cred_form.setSpacing(8)
        kp_cred_form.setLabelAlignment(Qt.AlignRight)
        kp_cred_form.setContentsMargins(0, 8, 0, 0)
        
        self._kp_cred_type_combo = QComboBox()
        self._kp_cred_type_combo.addItem("API Token (Jira Cloud)", "token")
        self._kp_cred_type_combo.addItem("Password", "password")
        self._kp_cred_type_combo.addItem("Personal Access Token (Server/Data Center)", "pat")
        kp_current_type = self._server.get("credential_type", "token")
        if kp_current_type == "pat":
            self._kp_cred_type_combo.setCurrentIndex(2)
        elif kp_current_type == "password":
            self._kp_cred_type_combo.setCurrentIndex(1)
        else:
            self._kp_cred_type_combo.setCurrentIndex(0)
        kp_cred_form.addRow("Credential Type:", self._kp_cred_type_combo)
        
        kp_vbox.addLayout(kp_cred_form)
        bv.addWidget(self._kp_group)

        # ---- Test connection button ----
        test_w = QWidget()
        test_h = QHBoxLayout(test_w)
        test_h.setContentsMargins(0, 8, 0, 0)
        test_h.addStretch()
        test_btn = _btn("Test Connection", flat=True)
        test_btn.setMinimumWidth(120)
        test_btn.clicked.connect(self._test_connection)
        test_h.addWidget(test_btn)
        bv.addWidget(test_w)

        bv.addStretch()
        root.addWidget(body)

        ok = _btn("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

        # --- Initial state (no auto-open dialogs at init time) ---
        mode = self._auth_combo.currentData()
        self._manual_group.setVisible(mode == "manual")
        self._kp_group.setVisible(mode == "keepass")
        if mode == "keepass":
            self._refresh_kp_state()
        self._on_cred_type_changed(self._cred_type_combo.currentIndex())

    # ---- KeePass state management ----

    def _refresh_kp_state(self):
        """Update the stacked widget to reflect the current KeePass state."""
        if not self._sm.is_keepass_configured():
            self._kp_stack.setCurrentIndex(0)
        elif not self._sm.is_keepass_unlocked():
            self._kp_stack.setCurrentIndex(1)
        else:
            self._kp_stack.setCurrentIndex(2)
            self._repopulate_entry_combo()

    def _repopulate_entry_combo(self):
        current = self._server.get("keepass_entry", "")
        self._kp_entry_combo.blockSignals(True)
        self._kp_entry_combo.clear()
        entries = self._sm.list_keepass_entries()
        self._kp_entry_combo.addItems(entries)
        if current in entries:
            self._kp_entry_combo.setCurrentText(current)
        elif entries:
            self._kp_entry_combo.setCurrentIndex(0)
        self._kp_entry_combo.blockSignals(False)

    def _configure_keepass(self):
        dlg = KeePassConfigDialog(self._sm, self)
        dlg.exec_()
        self._refresh_kp_state()

    def _unlock_keepass(self):
        """Try auto-unlock; if it fails, prompt for the master password."""
        ok, _ = self._sm.auto_unlock_keepass()
        if not ok:
            pwd, entered = QInputDialog.getText(
                self, "KeePass Master Password",
                "Enter KeePass master password:",
                QLineEdit.Password,
            )
            if entered:
                ok, err = self._sm.unlock_keepass(pwd)
                if not ok:
                    QMessageBox.warning(
                        self, "Unlock Failed",
                        f"Could not open database:\n{err}",
                    )
        self._refresh_kp_state()

    def _new_kp_entry(self):
        dlg = KeePassNewEntryDialog(self._sm, self)
        if dlg.exec_() == QDialog.Accepted:
            self._repopulate_entry_combo()
            path = dlg.get_entry_path()
            if path:
                self._kp_entry_combo.setCurrentText(path)

    # ---- Auth / credential type switching ----

    def _on_auth_mode_changed(self, _idx: int):
        mode = self._auth_combo.currentData()
        self._manual_group.setVisible(mode == "manual")
        self._kp_group.setVisible(mode == "keepass")
        if mode == "keepass":
            # Auto-open KeePass config when user actively switches to keepass mode
            if not self._sm.is_keepass_configured():
                dlg = KeePassConfigDialog(self._sm, self)
                dlg.exec_()
            self._refresh_kp_state()

    def _on_cred_type_changed(self, _idx: int):
        ctype = self._cred_type_combo.currentData()
        # Update the label on the credential row (last row of _mg_form)
        row_count = self._mg_form.rowCount()
        if row_count > 0:
            item = self._mg_form.itemAt(row_count - 1, QFormLayout.LabelRole)
            if item and item.widget():
                if ctype == "password":
                    item.widget().setText("Password:")
                elif ctype == "pat":
                    item.widget().setText("Personal Access Token:")
                else:
                    item.widget().setText("API Token:")
        
        if ctype == "password":
            self._token_edit.setPlaceholderText("password")
        elif ctype == "pat":
            self._token_edit.setPlaceholderText("Personal Access Token (for Jira Server/Data Center)")
        else:
            self._token_edit.setPlaceholderText("API token (for Jira Cloud)")

    # ---- Test connection ----

    def _test_connection(self):
        """Test the connection to Jira server with current form values."""
        from app_debug import is_debug  # type: ignore
        
        # Validate basic fields
        name = self._name_edit.text().strip()
        url = self._url_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Test Connection", "Please enter a server name first.")
            return
        if not url:
            QMessageBox.warning(self, "Test Connection", "Please enter the server URL first.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        
        if is_debug():
            print(f"[DEBUG] Testing Jira connection: name={name}, url={url}")

        # Build temporary server dict from current form values
        mode = self._auth_combo.currentData()
        temp_server = {"name": name, "url": url, "auth_mode": mode}
        if mode == "manual":
            temp_server["username"] = self._user_edit.text().strip()
            temp_server["token"] = self._token_edit.text()
            temp_server["credential_type"] = self._cred_type_combo.currentData()
            
            # For PAT, username is not required; for token/password, both are required
            if temp_server["credential_type"] == "pat":
                if not temp_server["token"]:
                    QMessageBox.warning(
                        self, "Test Connection",
                        "Please enter a Personal Access Token before testing."
                    )
                    return
            else:
                if not temp_server["username"] or not temp_server["token"]:
                    QMessageBox.warning(
                        self, "Test Connection",
                        "Please enter both username and credential before testing."
                    )
                    return
            if is_debug():
                print(f"[DEBUG] Manual auth mode: username={temp_server['username']}, credential_type={temp_server['credential_type']}")
        else:
            temp_server["keepass_entry"] = self._kp_entry_combo.currentText()
            temp_server["credential_type"] = self._kp_cred_type_combo.currentData()
            if not temp_server["keepass_entry"]:
                QMessageBox.warning(
                    self, "Test Connection",
                    "Please select a KeePass entry before testing."
                )
                return
            if is_debug():
                print(f"[DEBUG] KeePass auth mode: entry={temp_server['keepass_entry']}, credential_type={temp_server['credential_type']}")

        # Test connection
        try:
            if is_debug():
                print(f"[DEBUG] Calling jira_integration.test_connection()...")
            from integrations.jira_integration import test_connection  # type: ignore
            success, error = test_connection(temp_server)
            if is_debug():
                print(f"[DEBUG] test_connection returned: success={success}, error={error}")
            if success:
                QMessageBox.information(
                    self, "Test Connection",
                    f"✓ Successfully connected to {name}!\n\n"
                    f"Server: {url}\n"
                    f"Authentication: {mode}"
                )
            else:
                if is_debug():
                    print(f"[DEBUG] Connection failed with error: {error}")
                QMessageBox.warning(
                    self, "Test Connection",
                    f"✗ Connection failed:\n\n{error}"
                )
        except Exception as exc:
            if is_debug():
                import traceback
                print(f"[DEBUG] Exception during test_connection:")
                print(traceback.format_exc())
            QMessageBox.critical(
                self, "Test Connection",
                f"✗ Error testing connection:\n\n{exc}"
            )

    # ---- Accept ----

    def _accept(self):
        name = self._name_edit.text().strip()
        url  = self._url_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Please enter a server name.")
            return
        if not url:
            QMessageBox.warning(self, "Validation", "Please enter the server URL.")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        mode = self._auth_combo.currentData()
        self._server.update({"name": name, "url": url, "auth_mode": mode})
        if mode == "manual":
            self._server["username"]        = self._user_edit.text().strip()
            self._server["token"]           = self._token_edit.text()
            self._server["credential_type"] = self._cred_type_combo.currentData()
        else:
            self._server["keepass_entry"]   = self._kp_entry_combo.currentText()
            self._server["credential_type"] = self._kp_cred_type_combo.currentData()
        self.accept()

    def get_server(self) -> dict:
        return self._server



# ------------------------------------------------------------------ #
# Jira Sync Configuration Dialog                                      #
# ------------------------------------------------------------------ #

class JiraSyncConfigDialog(QDialog):
    """Configure Jira sync settings (server selection and future sync options).

    This dialog allows selecting which Jira server to use for syncing and
    provides access to manage the list of configured Jira servers.
    """

    def __init__(self, settings_manager, project=None, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._project = project
        self._has_project = project is not None

        # availableGeometry() already excludes the taskbar; subtract a small buffer
        # for the window chrome (title bar + frame, typically ~40 px).
        screen = QApplication.desktop().availableGeometry()
        _CHROME_BUFFER = 40
        max_dialog_height = screen.height() - _CHROME_BUFFER
        max_scroll_height = max(120, (screen.height() - _CHROME_BUFFER) // 4)

        self.setWindowTitle("Jira Sync Configuration")
        self.setMinimumWidth(700)  # Increased to prevent tab names from being cut off
        self.setMaximumHeight(max_dialog_height)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        # Store for later use in scroll area
        self._max_scroll_height = max_scroll_height

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Jira Sync Configuration",
            "Configure Jira server connection and field synchronization",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 16, 16, 8)
        bv.setSpacing(12)

        # Server selection section (top of dialog, outside tabs)
        server_group = QGroupBox("Jira Server")
        server_form = QFormLayout(server_group)
        server_form.setSpacing(8)
        server_form.setLabelAlignment(Qt.AlignRight)

        # Server dropdown
        server_row_w = QWidget()
        server_row_h = QHBoxLayout(server_row_w)
        server_row_h.setContentsMargins(0, 0, 0, 0)
        server_row_h.setSpacing(8)

        self._server_combo = QComboBox()
        self._server_combo.setEditable(False)
        self._server_combo.setPlaceholderText("Select a Jira server...")
        server_row_h.addWidget(self._server_combo, stretch=1)

        add_btn = _btn("Add...", flat=True)
        add_btn.setMinimumWidth(80)
        add_btn.clicked.connect(self._open_server_config)
        server_row_h.addWidget(add_btn)

        test_btn = _btn("Test", flat=True)
        test_btn.setMinimumWidth(72)
        test_btn.clicked.connect(self._test_selected_server_connection)
        server_row_h.addWidget(test_btn)

        server_form.addRow("Server:", server_row_w)
        bv.addWidget(server_group)

        # Visual separator between server config and tabs
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setStyleSheet("QFrame { color: #B8CBE4; margin: 8px 0; }")
        bv.addWidget(separator)

        # Tab control for different sync configurations
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #ccc; }
            QTabBar::tab { 
                padding: 6px 20px; 
                min-width: 120px;
            }
        """)

        # TAB 1: Jira → Project (import/sync from Jira to tasks)
        tab1 = QWidget()
        tab1_layout = QVBoxLayout(tab1)
        tab1_layout.setContentsMargins(12, 12, 12, 12)
        tab1_layout.setSpacing(12)

        # Filter configuration
        filter_group = QGroupBox("Issue Filter")
        filter_form = QFormLayout(filter_group)
        filter_form.setSpacing(8)
        filter_form.setLabelAlignment(Qt.AlignRight)

        # Filter type selector
        type_row_w = QWidget()
        type_row_h = QHBoxLayout(type_row_w)
        type_row_h.setContentsMargins(0, 0, 0, 0)
        type_row_h.setSpacing(16)

        self._filter_type_group = QButtonGroup(self)
        self._radio_jql = QRadioButton("JQL")
        self._radio_filter_id = QRadioButton("Saved Filter (ID or URL)")
        self._filter_type_group.addButton(self._radio_jql, 0)
        self._filter_type_group.addButton(self._radio_filter_id, 1)
        self._radio_jql.setChecked(True)
        type_row_h.addWidget(self._radio_jql)
        type_row_h.addWidget(self._radio_filter_id)
        type_row_h.addStretch()

        filter_form.addRow("Filter Type:", type_row_w)

        # Filter value field
        filter_row_w = QWidget()
        filter_row_h = QHBoxLayout(filter_row_w)
        filter_row_h.setContentsMargins(0, 0, 0, 0)
        filter_row_h.setSpacing(8)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("e.g. project = MYPROJECT AND status = 'In Progress'")
        self._filter_edit.setToolTip(
            "JQL (Jira Query Language) filter to limit which issues are synchronized.\n"
            "Examples:\n"
            "• project = MYPROJECT\n"
            "• project = MYPROJECT AND status IN ('Open', 'In Progress')\n"
            "• assignee = currentUser() AND resolution = Unresolved\n\n"
            "Stored in custom property: JIRA Sync Filter"
        )
        filter_row_h.addWidget(self._filter_edit, stretch=1)

        self._test_filter_btn = _btn("Test Filter", flat=True)
        self._test_filter_btn.setMinimumWidth(100)
        self._test_filter_btn.clicked.connect(self._test_filter)
        filter_row_h.addWidget(self._test_filter_btn)

        filter_form.addRow("Filter:", filter_row_w)

        # Update placeholder/tooltip when filter type changes
        self._filter_type_group.buttonClicked.connect(self._on_filter_type_changed)

        tab1_layout.addWidget(filter_group)

        # Field selection checkboxes (individual fields)
        fields_group = QGroupBox("Fields to Import from Jira")
        fields_layout = QVBoxLayout(fields_group)
        fields_layout.setSpacing(8)

        hint_label = QLabel(
            "<i>Note: Essential fields (issue key, summary, project key, issue type) are always imported. "
            "Select additional fields to import:</i>"
        )
        hint_label.setStyleSheet("color: #888; font-size: 10px; padding-bottom: 4px;")
        hint_label.setWordWrap(True)
        fields_layout.addWidget(hint_label)

        # Create scrollable area for all checkboxes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setMaximumHeight(self._max_scroll_height)  # Dynamic based on screen size
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(8)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        # Dictionary to hold all field checkboxes {field_name: QCheckBox}
        self._field_checkboxes = {}
        self._project2jira_fields = {}
        self._project2jira_tables = {}
        self._project2jira_widgets = {}

        # Helper function to create checkbox
        def add_field_cb(field_name: str, display_text: str, tooltip: str, parent_layout):
            cb = QCheckBox(display_text)
            cb.setToolTip(tooltip)
            parent_layout.addWidget(cb)
            self._field_checkboxes[field_name] = cb

        # Core Information
        core_group = QGroupBox("Core Information")
        core_layout = QVBoxLayout(core_group)
        core_layout.setSpacing(4)
        add_field_cb("jira_project_name", "Project Name", "Jira project name (descriptive alternative to project key)", core_layout)
        add_field_cb("jira_description", "Description", "Issue description text (wiki/markdown format)", core_layout)
        scroll_layout.addWidget(core_group)

        # Status and Resolution
        status_group = QGroupBox("Status and Resolution")
        status_layout = QVBoxLayout(status_group)
        status_layout.setSpacing(4)
        add_field_cb("jira_status", "Status", "Current issue status (e.g., 'To Do', 'In Progress', 'Done')", status_layout)
        add_field_cb("jira_status_percent", "Status Progress %", "Percentage complete derived from status mapping (0-100)", status_layout)
        add_field_cb("jira_resolution", "Resolution", "Issue resolution value (e.g., 'Fixed', 'Won't Fix', 'Duplicate')", status_layout)
        add_field_cb("jira_resolution_date", "Resolution Date", "Date/time when issue was resolved", status_layout)
        add_field_cb("jira_security_level", "Security Level", "Security level name for restricted access issues", status_layout)
        scroll_layout.addWidget(status_group)

        # Assignment and Reporter
        people_group = QGroupBox("Assignment and Reporter")
        people_layout = QVBoxLayout(people_group)
        people_layout.setSpacing(4)
        add_field_cb("jira_assignee", "Assignee", "Assigned user identifier (account ID, username, email, or full name)", people_layout)
        add_field_cb("jira_assignee_display_name", "Assignee Display Name", "Assignee's display name for visual reference", people_layout)
        add_field_cb("jira_reporter", "Reporter", "Reporter identifier (account ID, username, email, or full name)", people_layout)
        add_field_cb("jira_reporter_display_name", "Reporter Display Name", "Reporter's display name for visual reference", people_layout)
        scroll_layout.addWidget(people_group)

        # Priority and Dates
        dates_group = QGroupBox("Priority and Dates")
        dates_layout = QVBoxLayout(dates_group)
        dates_layout.setSpacing(4)
        add_field_cb("jira_priority", "Priority", "Priority level name (e.g., 'High', 'Medium', 'Low')", dates_layout)
        add_field_cb("jira_due_date", "Due Date", "Issue due date (can map to task Finish field)", dates_layout)
        add_field_cb("jira_created_date", "Created Date", "Date/time when issue was created", dates_layout)
        add_field_cb("jira_updated_date", "Updated Date", "Date/time of last issue update", dates_layout)
        scroll_layout.addWidget(dates_group)

        # Versions and Components
        versions_group = QGroupBox("Versions and Components")
        versions_layout = QVBoxLayout(versions_group)
        versions_layout.setSpacing(4)
        add_field_cb("jira_components", "Components", "Comma-separated list of component names", versions_layout)
        add_field_cb("jira_fix_versions", "Fix Versions", "Comma-separated list of target release versions", versions_layout)
        add_field_cb("jira_affects_versions", "Affects Versions", "Comma-separated list of versions where issue occurs", versions_layout)
        add_field_cb("jira_fix_version_description", "Fix Version Description", "Description of the fix version (single version only)", versions_layout)
        add_field_cb("jira_fix_version_released", "Fix Version Released", "Whether fix version has been released (single version only)", versions_layout)
        add_field_cb("jira_fix_version_start_date", "Fix Version Start Date", "Start date of fix version (single version only)", versions_layout)
        add_field_cb("jira_fix_version_release_date", "Fix Version Release Date", "Release/due date of fix version (single version only)", versions_layout)
        scroll_layout.addWidget(versions_group)

        # Labels and Metadata
        metadata_group = QGroupBox("Labels and Metadata")
        metadata_layout = QVBoxLayout(metadata_group)
        metadata_layout.setSpacing(4)
        add_field_cb("jira_labels", "Labels", "Comma-separated list of issue labels (requires Jira 4.0+)", metadata_layout)
        add_field_cb("jira_environment", "Environment", "Environment information (OS, browser, server config, etc.)", metadata_layout)
        add_field_cb("jira_votes", "Votes", "Number of votes the issue has received", metadata_layout)
        add_field_cb("jira_comments", "Comments", "Concatenated issue comments (usually appended to Notes field)", metadata_layout)
        scroll_layout.addWidget(metadata_group)

        # Time Tracking
        time_group = QGroupBox("Time Tracking")
        time_layout = QVBoxLayout(time_group)
        time_layout.setSpacing(4)
        add_field_cb("jira_time_spent", "Time Spent", "Total time logged on issue (maps to Actual Work)", time_layout)
        add_field_cb("jira_remaining_estimate", "Remaining Estimate", "Remaining work estimate (can map to Work field)", time_layout)
        add_field_cb("jira_original_estimate", "Original Estimate", "Original time estimate before work began", time_layout)
        add_field_cb("jira_time_spent_seconds", "Time Spent (seconds)", "Time spent in seconds for precise tracking", time_layout)
        add_field_cb("jira_worklog_entries", "Worklog Entries", "Detailed work log entries with user, date, and duration", time_layout)
        scroll_layout.addWidget(time_group)

        # Hierarchy and Relationships
        hierarchy_group = QGroupBox("Hierarchy and Relationships")
        hierarchy_layout = QVBoxLayout(hierarchy_group)
        hierarchy_layout.setSpacing(4)
        add_field_cb("jira_parent_key", "Parent Key", "Parent issue key for Jira Cloud hierarchy (replaces Epic Link)", hierarchy_layout)
        add_field_cb("jira_epic_link", "Epic Link", "Epic issue key (Jira Server/DC only)", hierarchy_layout)
        add_field_cb("jira_parent_link", "Parent Link", "Advanced Roadmaps parent key (Jira Server/DC only)", hierarchy_layout)
        add_field_cb("jira_subtask_parent", "Sub-task Parent", "Sub-task parent issue key (Jira Server/DC only)", hierarchy_layout)
        add_field_cb("jira_issue_links", "Issue Links", "Comma-separated list of linked issue keys for specific link types", hierarchy_layout)
        scroll_layout.addWidget(hierarchy_group)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        fields_layout.addWidget(scroll_area)

        self._wire_jira2project_field_dependencies()

        tab1_layout.addWidget(fields_group)
        tab1_layout.addWidget(self._build_jira2project_advanced_group())
        tab1_layout.addStretch()

        # Add hint if no project is open
        if not self._has_project:
            hint = QLabel("Note: Settings are project-specific. Open a project to configure.")
            hint.setStyleSheet("color: #d9534f; font-size: 11px; font-weight: bold; padding: 8px; background: #f9f2f2; border: 1px solid #ebccd1; border-radius: 3px;")
            hint.setWordWrap(True)
            tab1_layout.insertWidget(0, hint)
            # Disable all controls that require a project
            self._radio_jql.setEnabled(False)
            self._radio_filter_id.setEnabled(False)
            self._filter_edit.setEnabled(False)
            self._filter_edit.setPlaceholderText("(open a project to edit)")
            self._test_filter_btn.setEnabled(False)
            # Disable all field checkboxes
            for cb in self._field_checkboxes.values():
                cb.setEnabled(False)
            for ctrl in getattr(self, "_j2p_advanced_controls", []):
                ctrl.setEnabled(False)

        tab1_scroll = QScrollArea()
        tab1_scroll.setWidgetResizable(True)
        tab1_scroll.setFrameShape(QFrame.NoFrame)
        tab1_scroll.setWidget(tab1)
        self._tabs.addTab(tab1_scroll, "Jira → Project")

        # TAB 2: Project -> Jira (export/sync from tasks to Jira)
        tab2 = self._build_project_to_jira_tab()
        tab2_scroll = QScrollArea()
        tab2_scroll.setWidgetResizable(True)
        tab2_scroll.setFrameShape(QFrame.NoFrame)
        tab2_scroll.setWidget(tab2)
        self._tabs.addTab(tab2_scroll, "Project → Jira")

        bv.addWidget(self._tabs)

        root.addWidget(body)

        # Dialog buttons
        ok = _btn("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

        # Populate the server dropdown and load settings from project
        self._refresh_servers()
        if self._has_project:
            filter_value, filter_type = self._get_filter_from_project()
            if filter_type == "filter":
                self._radio_filter_id.setChecked(True)
                self._on_filter_type_changed(self._radio_filter_id)
            self._filter_edit.setText(filter_value)
            
            # Load field selection checkboxes from project
            self._load_field_selections()
            self._load_project_to_jira_settings()
        else:
            self._set_project_to_jira_enabled(False)

        # Center the dialog on screen
        self._center_on_screen()

    def _center_on_screen(self):
        """Center the dialog on the available screen area."""
        self.adjustSize()  # Ensure dialog has final size before centering
        screen = QApplication.desktop().availableGeometry()
        # Use the constrained dimensions (respecting maximumHeight/Width) so the
        # dialog is never positioned partially off-screen before it is shown.
        w = min(self.sizeHint().width(), self.maximumWidth())
        h = min(self.sizeHint().height(), self.maximumHeight())
        x = screen.x() + (screen.width() - w) // 2
        y = screen.y() + (screen.height() - h) // 2
        self.move(x, y)

    def _refresh_servers(self):
        """Populate the server dropdown with configured Jira servers."""
        current_server = self._sm.get_jira_sync_server()
        self._server_combo.clear()
        
        servers = self._sm.get_jira_servers()
        if not servers:
            self._server_combo.addItem("(No servers configured)")
            self._server_combo.setEnabled(False)
            return
        
        self._server_combo.setEnabled(True)
        for server in servers:
            name = server.get("name", "(unnamed)")
            url = server.get("url", "")
            self._server_combo.addItem(f"{name} — {url}", userData=server)
        
        # Select the previously saved server
        if current_server:
            for i in range(self._server_combo.count()):
                server = self._server_combo.itemData(i)
                if server and server.get("name") == current_server:
                    self._server_combo.setCurrentIndex(i)
                    break

    def _open_server_config(self):
        """Open the Jira Servers dialog to manage server configurations."""
        dlg = JiraServersDialog(self._sm, self)
        if dlg.exec_() == QDialog.Accepted:
            # Refresh the dropdown after returning from server configuration
            self._refresh_servers()

    def _on_filter_type_changed(self, button):
        """Update the filter field placeholder and tooltip when the filter type changes."""
        if self._radio_jql.isChecked():
            self._filter_edit.setPlaceholderText("e.g. project = MYPROJECT AND status = 'In Progress'")
            self._filter_edit.setToolTip(
                "JQL (Jira Query Language) filter to limit which issues are synchronized.\n"
                "Examples:\n"
                "• project = MYPROJECT\n"
                "• project = MYPROJECT AND status IN ('Open', 'In Progress')\n"
                "• assignee = currentUser() AND resolution = Unresolved\n\n"
                "Stored in custom property: JIRA Sync Filter"
            )
        else:
            self._filter_edit.setPlaceholderText(
                "e.g. 66111  or  https://jira.example.com/issues/?filter=66111"
            )
            self._filter_edit.setToolTip(
                "Jira saved filter — enter either a numeric filter ID or the full filter URL.\n"
                "Examples:\n"
                "• 66111\n"
                "• https://jira.example.com/issues/?filter=66111\n\n"
                "The filter's JQL will be resolved at sync / test time.\n"
                "Stored in custom property: JIRA Sync Filter"
            )

    def _build_jira2project_advanced_group(self) -> QGroupBox:
        """Build advanced Jira -> Project import behavior controls."""
        grp = QGroupBox("Advanced Import Behavior")
        form = QFormLayout(grp)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._j2p_relink_enabled_cb = QCheckBox("Enable relink policy")
        self._j2p_relink_behavior_combo = QComboBox()
        self._j2p_relink_behavior_combo.addItem("Skip", "skip")
        self._j2p_relink_behavior_combo.addItem("Relink to new issue", "relink")
        self._j2p_relink_behavior_combo.addItem("Messagebox", "messagebox")
        relink_row = QWidget()
        relink_layout = QHBoxLayout(relink_row)
        relink_layout.setContentsMargins(0, 0, 0, 0)
        relink_layout.addWidget(self._j2p_relink_enabled_cb)
        relink_layout.addWidget(self._j2p_relink_behavior_combo)
        form.addRow("Relink Policy:", relink_row)

        self._j2p_incremental_enabled_cb = QCheckBox("Enable incremental import")
        self._j2p_incremental_mode_combo = QComboBox()
        self._j2p_incremental_mode_combo.addItem("Changed since last sync", "changed_since_last_sync")
        self._j2p_incremental_mode_combo.addItem("Full resync", "full_resync")
        incremental_row = QWidget()
        incremental_layout = QHBoxLayout(incremental_row)
        incremental_layout.setContentsMargins(0, 0, 0, 0)
        incremental_layout.addWidget(self._j2p_incremental_enabled_cb)
        incremental_layout.addWidget(self._j2p_incremental_mode_combo)
        form.addRow("Incremental:", incremental_row)

        self._j2p_conflict_enabled_cb = QCheckBox("Enable conflict handling")
        self._j2p_conflict_policy_combo = QComboBox()
        self._j2p_conflict_policy_combo.addItem("Prefer Jira", "prefer_jira")
        self._j2p_conflict_policy_combo.addItem("Prefer local", "prefer_local")
        self._j2p_conflict_policy_combo.addItem("Manual review", "manual_review")
        self._j2p_conflict_policy_combo.addItem("Messagebox", "messagebox")
        conflict_row = QWidget()
        conflict_layout = QHBoxLayout(conflict_row)
        conflict_layout.setContentsMargins(0, 0, 0, 0)
        conflict_layout.addWidget(self._j2p_conflict_enabled_cb)
        conflict_layout.addWidget(self._j2p_conflict_policy_combo)
        form.addRow("Conflict Policy:", conflict_row)

        self._j2p_field_policy = {}
        field_policy_defs = [
            ("status", "Status"),
            ("dates", "Dates"),
            ("assignee", "Assignee"),
            ("estimate", "Estimate"),
            ("labels", "Labels"),
        ]
        for key, label in field_policy_defs:
            combo = QComboBox()
            combo.addItem("Prefer Jira", "prefer_jira")
            combo.addItem("Prefer local", "prefer_local")
            combo.addItem("Manual review", "manual_review")
            combo.addItem("Messagebox", "messagebox")
            self._j2p_field_policy[key] = combo
            form.addRow(f"Field policy ({label}):", combo)

        self._j2p_orphan_enabled_cb = QCheckBox("Enable orphan handling")
        self._j2p_orphan_behavior_combo = QComboBox()
        self._j2p_orphan_behavior_combo.addItem("Keep link and task", "keep")
        self._j2p_orphan_behavior_combo.addItem("Unlink and keep task", "unlink")
        self._j2p_orphan_behavior_combo.addItem("Close task and unlink", "close")
        self._j2p_orphan_behavior_combo.addItem("Delete task", "delete")
        self._j2p_orphan_behavior_combo.addItem("Messagebox", "messagebox")
        orphan_row = QWidget()
        orphan_layout = QHBoxLayout(orphan_row)
        orphan_layout.setContentsMargins(0, 0, 0, 0)
        orphan_layout.addWidget(self._j2p_orphan_enabled_cb)
        orphan_layout.addWidget(self._j2p_orphan_behavior_combo)
        form.addRow("Out-of-scope issues:", orphan_row)

        self._j2p_closed_state_completion_cb = QCheckBox("Map Jira closed/resolved to 100% completion")
        self._j2p_normalize_enabled_cb = QCheckBox("Normalize timezone/date and sanitize rich text")
        self._j2p_hierarchy_enabled_cb = QCheckBox("Import hierarchy (Epic/parent/sub-task) into WBS")
        self._j2p_dependencies_enabled_cb = QCheckBox("Import Jira issue links as dependencies")
        form.addRow("Completion mapping:", self._j2p_closed_state_completion_cb)
        form.addRow("Normalization:", self._j2p_normalize_enabled_cb)
        form.addRow("Hierarchy:", self._j2p_hierarchy_enabled_cb)
        form.addRow("Dependencies:", self._j2p_dependencies_enabled_cb)

        self._j2p_reliability_enabled_cb = QCheckBox("Enable retry/backoff for transient API failures")
        self._j2p_retry_count_edit = QLineEdit("3")
        self._j2p_retry_count_edit.setValidator(QIntValidator(0, 10))
        self._j2p_backoff_edit = QLineEdit("1.0")
        reliability_row = QWidget()
        reliability_layout = QHBoxLayout(reliability_row)
        reliability_layout.setContentsMargins(0, 0, 0, 0)
        reliability_layout.addWidget(self._j2p_reliability_enabled_cb)
        reliability_layout.addWidget(QLabel("Retries:"))
        reliability_layout.addWidget(self._j2p_retry_count_edit)
        reliability_layout.addWidget(QLabel("Base backoff (s):"))
        reliability_layout.addWidget(self._j2p_backoff_edit)
        form.addRow("Reliability:", reliability_row)

        self._j2p_preview_enabled_cb = QCheckBox("Preview and selective apply")
        self._j2p_preview_include_edit = QLineEdit()
        self._j2p_preview_exclude_edit = QLineEdit()
        self._j2p_preview_include_edit.setPlaceholderText("Comma-separated issue keys to include (optional)")
        self._j2p_preview_exclude_edit.setPlaceholderText("Comma-separated issue keys to exclude (optional)")
        form.addRow("Preview:", self._j2p_preview_enabled_cb)
        form.addRow("Preview include:", self._j2p_preview_include_edit)
        form.addRow("Preview exclude:", self._j2p_preview_exclude_edit)

        self._j2p_advanced_controls = [
            self._j2p_relink_enabled_cb,
            self._j2p_relink_behavior_combo,
            self._j2p_incremental_enabled_cb,
            self._j2p_incremental_mode_combo,
            self._j2p_conflict_enabled_cb,
            self._j2p_conflict_policy_combo,
            self._j2p_orphan_enabled_cb,
            self._j2p_orphan_behavior_combo,
            self._j2p_closed_state_completion_cb,
            self._j2p_normalize_enabled_cb,
            self._j2p_hierarchy_enabled_cb,
            self._j2p_dependencies_enabled_cb,
            self._j2p_reliability_enabled_cb,
            self._j2p_retry_count_edit,
            self._j2p_backoff_edit,
            self._j2p_preview_enabled_cb,
            self._j2p_preview_include_edit,
            self._j2p_preview_exclude_edit,
        ] + list(self._j2p_field_policy.values())
        return grp

    def _get_selected_combo_data(self, combo: QComboBox, fallback: str) -> str:
        value = combo.currentData()
        return str(value) if value is not None else fallback

    def _parse_csv_keys(self, text: str) -> list[str]:
        keys = []
        for raw in (text or "").split(","):
            key = raw.strip()
            if key:
                keys.append(key)
        return keys

    def _wire_jira2project_field_dependencies(self):
        """Connect dependency rules for Jira -> Project field options."""
        for dependent_field, controller_field in _JIRA2PROJECT_FIELD_DEPENDENCIES.items():
            controller_cb = self._field_checkboxes.get(controller_field)
            if controller_cb is None:
                continue
            controller_cb.toggled.connect(self._apply_jira2project_field_dependencies)
        self._apply_jira2project_field_dependencies()

    def _apply_jira2project_field_dependencies(self):
        """Disable dependent checkboxes when the controlling checkbox is not active."""
        for dependent_field, controller_field in _JIRA2PROJECT_FIELD_DEPENDENCIES.items():
            dependent_cb = self._field_checkboxes.get(dependent_field)
            controller_cb = self._field_checkboxes.get(controller_field)
            if dependent_cb is None or controller_cb is None:
                continue

            active = controller_cb.isEnabled() and controller_cb.isChecked()
            if not active:
                dependent_cb.setChecked(False)
            dependent_cb.setEnabled(active)

    def _build_jira2project_advanced_payload(self) -> dict:
        field_policy = {
            key: self._get_selected_combo_data(combo, "messagebox")
            for key, combo in self._j2p_field_policy.items()
        }
        max_retries_text = self._j2p_retry_count_edit.text().strip()
        try:
            max_retries = int(max_retries_text) if max_retries_text else 3
        except Exception:
            max_retries = 3
        backoff_text = self._j2p_backoff_edit.text().strip()
        try:
            backoff_seconds = float(backoff_text) if backoff_text else 1.0
        except Exception:
            backoff_seconds = 1.0

        return {
            "relink": {
                "enabled": self._j2p_relink_enabled_cb.isChecked(),
                "behavior": self._get_selected_combo_data(self._j2p_relink_behavior_combo, "messagebox"),
            },
            "incremental": {
                "enabled": self._j2p_incremental_enabled_cb.isChecked(),
                "mode": self._get_selected_combo_data(self._j2p_incremental_mode_combo, "changed_since_last_sync"),
            },
            "conflict": {
                "enabled": self._j2p_conflict_enabled_cb.isChecked(),
                "policy": self._get_selected_combo_data(self._j2p_conflict_policy_combo, "messagebox"),
                "field_policy": field_policy,
            },
            "orphan": {
                "enabled": self._j2p_orphan_enabled_cb.isChecked(),
                "behavior": self._get_selected_combo_data(self._j2p_orphan_behavior_combo, "messagebox"),
            },
            "closed_state_completion": {
                "enabled": self._j2p_closed_state_completion_cb.isChecked(),
            },
            "normalize": {
                "enabled": self._j2p_normalize_enabled_cb.isChecked(),
            },
            "hierarchy": {
                "enabled": self._j2p_hierarchy_enabled_cb.isChecked(),
            },
            "dependencies": {
                "enabled": self._j2p_dependencies_enabled_cb.isChecked(),
            },
            "reliability": {
                "enabled": self._j2p_reliability_enabled_cb.isChecked(),
                "max_retries": max(0, min(10, max_retries)),
                "backoff_seconds": max(0.1, backoff_seconds),
            },
            "preview": {
                "enabled": self._j2p_preview_enabled_cb.isChecked(),
                "include_keys": self._parse_csv_keys(self._j2p_preview_include_edit.text()),
                "exclude_keys": self._parse_csv_keys(self._j2p_preview_exclude_edit.text()),
            },
        }

    def _load_jira2project_advanced_settings(self, j2p: dict):
        advanced = _JIRA2PROJECT_ADVANCED_DEFAULTS.copy()
        incoming = j2p.get("advanced") or {}
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(advanced.get(key), dict):
                merged = dict(advanced[key])
                merged.update(value)
                advanced[key] = merged
            else:
                advanced[key] = value

        relink = advanced.get("relink") or {}
        self._j2p_relink_enabled_cb.setChecked(bool(relink.get("enabled", False)))
        idx = self._j2p_relink_behavior_combo.findData(str(relink.get("behavior", "messagebox")))
        self._j2p_relink_behavior_combo.setCurrentIndex(idx if idx >= 0 else 2)

        incremental = advanced.get("incremental") or {}
        self._j2p_incremental_enabled_cb.setChecked(bool(incremental.get("enabled", False)))
        idx = self._j2p_incremental_mode_combo.findData(str(incremental.get("mode", "changed_since_last_sync")))
        self._j2p_incremental_mode_combo.setCurrentIndex(idx if idx >= 0 else 0)

        conflict = advanced.get("conflict") or {}
        self._j2p_conflict_enabled_cb.setChecked(bool(conflict.get("enabled", False)))
        idx = self._j2p_conflict_policy_combo.findData(str(conflict.get("policy", "messagebox")))
        self._j2p_conflict_policy_combo.setCurrentIndex(idx if idx >= 0 else 3)
        field_policy = conflict.get("field_policy") or {}
        for key, combo in self._j2p_field_policy.items():
            idx = combo.findData(str(field_policy.get(key, "messagebox")))
            combo.setCurrentIndex(idx if idx >= 0 else 3)

        orphan = advanced.get("orphan") or {}
        self._j2p_orphan_enabled_cb.setChecked(bool(orphan.get("enabled", False)))
        idx = self._j2p_orphan_behavior_combo.findData(str(orphan.get("behavior", "messagebox")))
        self._j2p_orphan_behavior_combo.setCurrentIndex(idx if idx >= 0 else 4)

        self._j2p_closed_state_completion_cb.setChecked(bool((advanced.get("closed_state_completion") or {}).get("enabled", False)))
        self._j2p_normalize_enabled_cb.setChecked(bool((advanced.get("normalize") or {}).get("enabled", False)))
        self._j2p_hierarchy_enabled_cb.setChecked(bool((advanced.get("hierarchy") or {}).get("enabled", False)))
        self._j2p_dependencies_enabled_cb.setChecked(bool((advanced.get("dependencies") or {}).get("enabled", False)))

        reliability = advanced.get("reliability") or {}
        self._j2p_reliability_enabled_cb.setChecked(bool(reliability.get("enabled", False)))
        self._j2p_retry_count_edit.setText(str(reliability.get("max_retries", 3)))
        self._j2p_backoff_edit.setText(str(reliability.get("backoff_seconds", 1.0)))

        preview = advanced.get("preview") or {}
        self._j2p_preview_enabled_cb.setChecked(bool(preview.get("enabled", False)))
        self._j2p_preview_include_edit.setText(", ".join(preview.get("include_keys") or []))
        self._j2p_preview_exclude_edit.setText(", ".join(preview.get("exclude_keys") or []))

    def _set_project_to_jira_enabled(self, enabled: bool):
        """Enable or disable all Project -> Jira controls together."""
        for widget_info in self._project2jira_fields.values():
            widget_info["checkbox"].setEnabled(enabled)
            widget_info["label"].setEnabled(enabled and widget_info["checkbox"].isChecked())
            widget_info["edit"].setEnabled(enabled and widget_info["checkbox"].isChecked())
        for table in self._project2jira_tables.values():
            table.setEnabled(enabled)
        for widget in self._project2jira_widgets.values():
            widget.setEnabled(enabled)
        for w in (self._p2j_hierarchy_enabled_cb, self._p2j_audit_enabled_cb,
                  self._export_scope_combo, self._create_update_combo,
                  self._conflict_combo, self._unlinked_combo):
            w.setEnabled(enabled)

    def _build_project_to_jira_field_row(self, field_name: str, display_text: str, tooltip: str, default_jira_field: str) -> QWidget:
        """Build one export mapping row with a controlling checkbox and Jira field edit."""
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        checkbox = QCheckBox()
        checkbox.setToolTip(f"Enable export of {display_text}.\n\n{tooltip}")

        label = QLabel(display_text)
        label.setMinimumWidth(180)
        label.setToolTip(tooltip)

        edit = QComboBox()
        edit.setEditable(True)
        _suggestions = ([default_jira_field] if default_jira_field else []) + [
            f for f in _P2J_JIRA_FIELD_SUGGESTIONS if f != default_jira_field
        ]
        edit.addItems(_suggestions)
        if default_jira_field:
            edit.setCurrentText(default_jira_field)
        edit.lineEdit().setPlaceholderText("e.g. summary, customfield_10010")
        edit.setToolTip(
            f"Target Jira field for {display_text}.\n"
            "Use a Jira system field name or a custom field name."
        )

        def _sync_row_state(checked: bool):
            label.setEnabled(checked)
            edit.setEnabled(checked)
            if checked:
                edit.setStyleSheet("")
            else:
                edit.setStyleSheet("color: #888;")

        checkbox.toggled.connect(_sync_row_state)
        _sync_row_state(False)

        row_layout.addWidget(checkbox)
        row_layout.addWidget(label, stretch=1)
        row_layout.addWidget(edit, stretch=1)

        self._project2jira_fields[field_name] = {
            "checkbox": checkbox,
            "label": label,
            "edit": edit,
            "default": default_jira_field,
        }
        return row

    def _build_project_to_jira_table(self, title: str, help_text: str, key: str, column_labels: tuple[str, str],
                                      left_options: list | None = None, right_options: list | None = None) -> QGroupBox:
        """Build a simple editable two-column mapping table.
        When *left_options* / *right_options* are provided the respective column
        uses an editable QComboBox instead of a plain text cell.
        """
        grp = QGroupBox(title)
        vbox = QVBoxLayout(grp)
        vbox.setSpacing(8)

        note = QLabel(help_text)
        note.setWordWrap(True)
        note.setStyleSheet("color: #666; font-size: 11px; font-style: italic;")
        vbox.addWidget(note)

        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(list(column_labels))
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        # Store options as dynamic properties so _dict_to_table can recreate combos
        if left_options is not None:
            table.setProperty("left_options", left_options)
        if right_options is not None:
            table.setProperty("right_options", right_options)
        vbox.addWidget(table)

        btn_row = QWidget()
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()
        add_btn = _btn("Add Row", flat=True)
        del_btn = _btn("Remove Row", flat=True)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        vbox.addWidget(btn_row)

        def _make_combo(options: list, value: str = "") -> QComboBox:
            cb = QComboBox()
            cb.setEditable(True)
            cb.addItems(options)
            if value in options:
                cb.setCurrentText(value)
            elif value:
                cb.setCurrentText(value)
            else:
                cb.setCurrentIndex(-1)
                cb.clearEditText()
            return cb

        def _add_row(left: str = "", right: str = ""):
            row = table.rowCount()
            table.insertRow(row)
            if left_options is not None:
                table.setCellWidget(row, 0, _make_combo(left_options, left))
            else:
                table.setItem(row, 0, QTableWidgetItem(left))
            if right_options is not None:
                table.setCellWidget(row, 1, _make_combo(right_options, right))
            else:
                table.setItem(row, 1, QTableWidgetItem(right))

        def _remove_selected_row():
            row = table.currentRow()
            if row >= 0:
                table.removeRow(row)

        add_btn.clicked.connect(_add_row)
        del_btn.clicked.connect(_remove_selected_row)

        self._project2jira_tables[key] = table
        self._project2jira_widgets[key] = grp
        return grp

    def _build_project_to_jira_tab(self) -> QWidget:
        """Build the Project -> Jira export configuration tab."""
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(12, 12, 12, 12)
        tab_layout.setSpacing(12)

        hint = QLabel(
            "Configure outbound Project -> Jira sync behavior, field mappings, and validation."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555; font-style: italic;")
        tab_layout.addWidget(hint)

        # Export scope and execution policy.
        policy_group = QGroupBox("Export Behavior")
        policy_layout = QFormLayout(policy_group)
        policy_layout.setSpacing(8)
        policy_layout.setLabelAlignment(Qt.AlignRight)

        self._export_scope_combo = QComboBox()
        self._export_scope_combo.addItems(["Selected tasks", "Changed since last sync", "Full project"])
        self._export_scope_combo.setCurrentIndex(1)  # Changed since last sync is default
        self._export_scope_combo.setToolTip("Which tasks to include in the export.")
        policy_layout.addRow("Export Scope:", self._export_scope_combo)

        self._create_update_combo = QComboBox()
        self._create_update_combo.addItems(["Create only", "Update only", "Create + update"])
        self._create_update_combo.setCurrentIndex(2)  # Create + update is default
        self._create_update_combo.setToolTip("Whether to create new Jira issues, update existing ones, or both.")
        policy_layout.addRow("Mode:", self._create_update_combo)

        self._conflict_combo = QComboBox()
        self._conflict_combo.addItems(["Prefer Jira", "Prefer Project", "Manual review"])
        self._conflict_combo.setCurrentIndex(2)  # Manual review is default
        self._conflict_combo.setToolTip("How to resolve conflicts when both project and Jira have been changed.")
        policy_layout.addRow("Conflict Policy:", self._conflict_combo)

        self._dry_run_check = QCheckBox("Dry-run / preview only")
        self._dry_run_check.setChecked(True)
        self._dry_run_check.setToolTip("Show planned create/update/transition actions before executing them.")
        policy_layout.addRow("Preview:", self._dry_run_check)

        self._unlinked_combo = QComboBox()
        self._unlinked_combo.addItems(["Create new issue", "Skip", "Prompt"])
        self._unlinked_combo.setCurrentIndex(1)  # Skip is default
        self._unlinked_combo.setToolTip(
            "What to do with project tasks that have no linked Jira issue.\n"
            "• Create new issue: create a new Jira issue for each unlinked task.\n"
            "• Skip: ignore unlinked tasks (default).\n"
            "• Prompt: ask what to do for each unlinked task."
        )
        policy_layout.addRow("Unlinked tasks:", self._unlinked_combo)

        tab_layout.addWidget(policy_group)

        # Export field mapping groups with 25% screen-height scroll area.
        fields_group = QGroupBox("Project field -> Jira field mapping")
        fields_group_layout = QVBoxLayout(fields_group)
        fields_group_layout.setSpacing(8)
        fields_group_layout.addWidget(QLabel("Enable only the fields you want to export and map each one to a Jira field."))

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setMaximumHeight(self._max_scroll_height)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(8)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        for section_title, items in _JIRA_SYNC_FIELD_SECTIONS:
            grp = QGroupBox(section_title)
            grp_layout = QVBoxLayout(grp)
            grp_layout.setSpacing(4)
            for field_name, display_text, tooltip, default_jira_field in items:
                grp_layout.addWidget(self._build_project_to_jira_field_row(field_name, display_text, tooltip, default_jira_field))
            scroll_layout.addWidget(grp)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        fields_group_layout.addWidget(scroll_area)
        tab_layout.addWidget(fields_group)

        self._task_type_map_group = self._build_project_to_jira_table(
            "Task type -> Jira issue type",
            "Map your project task types to Jira issue types. This mapping is validated against the selected Jira server when possible.",
            "issue_type_map",
            ("Project task type", "Jira issue type"),
            left_options=_P2J_TASK_TYPE_LEFT_OPTIONS,
            right_options=_P2J_TASK_TYPE_RIGHT_OPTIONS,
        )
        tab_layout.addWidget(self._task_type_map_group)

        # Warning label shown when mapped issue types are not available on the server.
        self._issue_type_warning_label = QLabel()
        self._issue_type_warning_label.setWordWrap(True)
        self._issue_type_warning_label.setStyleSheet(
            "color: #8a6d3b; background: #fcf8e3; border: 1px solid #faebcc; "
            "border-radius: 3px; padding: 6px; font-size: 11px;"
        )
        self._issue_type_warning_label.setVisible(False)
        tab_layout.addWidget(self._issue_type_warning_label)

        self._transition_map_group = self._build_project_to_jira_table(
            "Task status -> Jira transition",
            "Map project task statuses to Jira transition id or name. If a linked Jira issue is available, the dialog validates the transition choices against Jira.",
            "transition_map",
            ("Project task status", "Jira transition (id or name)"),
            left_options=_P2J_TRANSITION_LEFT_OPTIONS,
            right_options=_P2J_TRANSITION_RIGHT_OPTIONS,
        )
        tab_layout.addWidget(self._transition_map_group)

        # Hierarchy Export section
        hierarchy_grp = QGroupBox("Hierarchy & Dependency Export")
        hierarchy_form = QFormLayout(hierarchy_grp)
        hierarchy_form.setSpacing(8)
        hierarchy_form.setLabelAlignment(Qt.AlignRight)

        self._p2j_hierarchy_enabled_cb = QCheckBox("Export parent/child hierarchy and task dependencies")
        self._p2j_hierarchy_enabled_cb.setToolTip(
            "When enabled, parent tasks are created as the configured Epic type,\n"
            "child tasks as Story/Sub-task, and predecessor links are exported\n"
            "as Jira issue links of the configured type.\n"
            "Default: disabled."
        )
        hierarchy_form.addRow("Enable:", self._p2j_hierarchy_enabled_cb)

        p2j_hier_type_row = QWidget()
        p2j_hier_type_layout = QHBoxLayout(p2j_hier_type_row)
        p2j_hier_type_layout.setContentsMargins(0, 0, 0, 0)
        p2j_hier_type_layout.setSpacing(8)
        _hier_issue_types = ["Epic", "Story", "Task", "Bug", "Sub-task", "Feature", "Improvement", "New Feature", "Initiative"]
        self._p2j_epic_type_edit = QComboBox()
        self._p2j_epic_type_edit.setEditable(True)
        self._p2j_epic_type_edit.addItems(["Epic"] + [t for t in _hier_issue_types if t != "Epic"])
        self._p2j_story_type_edit = QComboBox()
        self._p2j_story_type_edit.setEditable(True)
        self._p2j_story_type_edit.addItems(["Story"] + [t for t in _hier_issue_types if t != "Story"])
        self._p2j_subtask_type_edit = QComboBox()
        self._p2j_subtask_type_edit.setEditable(True)
        self._p2j_subtask_type_edit.addItems(["Sub-task"] + [t for t in _hier_issue_types if t != "Sub-task"])
        for lbl, widget in [("Epic:", self._p2j_epic_type_edit),
                             ("Story:", self._p2j_story_type_edit),
                             ("Sub-task:", self._p2j_subtask_type_edit)]:
            p2j_hier_type_layout.addWidget(QLabel(lbl))
            p2j_hier_type_layout.addWidget(widget)
        p2j_hier_type_layout.addStretch()
        hierarchy_form.addRow("Issue types:", p2j_hier_type_row)

        self._p2j_dep_link_type_edit = QComboBox()
        self._p2j_dep_link_type_edit.setEditable(True)
        self._p2j_dep_link_type_edit.addItems([
            "blocks", "is blocked by", "relates to", "clones", "is cloned by",
            "duplicates", "is duplicated by",
        ])
        self._p2j_dep_link_type_edit.setCurrentText("blocks")
        self._p2j_dep_link_type_edit.setToolTip(
            "Jira issue link type used for predecessor dependencies (e.g. 'blocks', 'relates to')."
        )
        hierarchy_form.addRow("Dependency link type:", self._p2j_dep_link_type_edit)

        def _toggle_hier_controls(checked: bool):
            for w in (self._p2j_epic_type_edit, self._p2j_story_type_edit,
                      self._p2j_subtask_type_edit, self._p2j_dep_link_type_edit):
                w.setEnabled(checked)

        self._p2j_hierarchy_enabled_cb.toggled.connect(_toggle_hier_controls)
        _toggle_hier_controls(False)
        tab_layout.addWidget(hierarchy_grp)

        # Auditability section
        audit_grp = QGroupBox("Sync Auditability")
        audit_form = QFormLayout(audit_grp)
        audit_form.setSpacing(8)
        audit_form.setLabelAlignment(Qt.AlignRight)

        self._p2j_audit_enabled_cb = QCheckBox("Persist sync session summary and per-task push timestamps")
        self._p2j_audit_enabled_cb.setToolTip(
            "When enabled:\n"
            "• Saves a push session summary (created, updated, transitioned, skipped, errors)\n"
            "  to the sidecar JSON after each push.\n"
            "• Stores a per-task last-push timestamp and result status.\n"
            "Default: disabled."
        )
        audit_form.addRow("Enable:", self._p2j_audit_enabled_cb)
        tab_layout.addWidget(audit_grp)

        tab_layout.addStretch()
        return tab

    def _table_to_dict(self, table: QTableWidget) -> dict:
        """Convert a two-column mapping table to a dict."""
        result = {}
        for row in range(table.rowCount()):
            left_widget = table.cellWidget(row, 0)
            right_widget = table.cellWidget(row, 1)
            left_item = table.item(row, 0)
            right_item = table.item(row, 1)
            if left_widget is not None and hasattr(left_widget, "currentText"):
                left = left_widget.currentText().strip()
            else:
                left = left_item.text().strip() if left_item else ""
            if right_widget is not None and hasattr(right_widget, "currentText"):
                right = right_widget.currentText().strip()
            else:
                right = right_item.text().strip() if right_item else ""
            if left:
                result[left] = right
        return result

    def _dict_to_table(self, table: QTableWidget, data: dict):
        """Populate a two-column mapping table from a dict.
        If the table has QComboBox cell widgets (set by _build_project_to_jira_table),
        the first row's cell widget is used as a template to detect the options.
        """
        # Detect whether this table uses combo boxes by checking row 0 widgets
        # (we check after clearing, so we use the _add_row closure's behaviour)
        # Strategy: store left/right options on the table itself via dynamic property
        left_opts = table.property("left_options")
        right_opts = table.property("right_options")

        table.setRowCount(0)
        for key, value in data.items():
            row = table.rowCount()
            table.insertRow(row)
            if left_opts is not None:
                cb_l = QComboBox()
                cb_l.setEditable(True)
                cb_l.addItems(left_opts)
                cb_l.setCurrentText(str(key))
                table.setCellWidget(row, 0, cb_l)
            else:
                table.setItem(row, 0, QTableWidgetItem(str(key)))
            if right_opts is not None:
                cb_r = QComboBox()
                cb_r.setEditable(True)
                cb_r.addItems(right_opts)
                cb_r.setCurrentText(str(value))
                table.setCellWidget(row, 1, cb_r)
            else:
                table.setItem(row, 1, QTableWidgetItem(str(value)))

    def _load_project_to_jira_settings(self):
        """Load export settings from the project custom properties."""
        if not self._project:
            return
        try:
            import json as _json
            from integrations.jira_integration import PROJECT2JIRA_PROP  # type: ignore
            cp = self._project.getProjectProperties().getCustomProperties()
            raw = cp.get(PROJECT2JIRA_PROP) if cp is not None else None
            config = {}
            if raw:
                try:
                    config = _json.loads(str(raw))
                except Exception:
                    config = {}
            config = {**_PROJECT2JIRA_DEFAULTS, **config}
            # Deep-merge fields so default pre-enabled fields apply when not yet saved.
            # Maps (issue_type_map, transition_map) are NOT deep-merged: the shallow
            # merge above already applies defaults when no saved map exists, and
            # preserves the user's saved map (as a whole) when one does exist.
            merged_fields = {**(_PROJECT2JIRA_DEFAULTS.get("fields") or {}), **(config.get("fields") or {})}
            config["fields"] = merged_fields

            scope_map = {
                "selected_tasks": 0,
                "changed_since_last_sync": 1,
                "full_project": 2,
            }
            mode_map = {
                "create_only": 0,
                "update_only": 1,
                "create_update": 2,
            }
            conflict_map = {
                "prefer_jira": 0,
                "prefer_project": 1,
                "manual_review": 2,
            }
            unlinked_map = {
                "create": 0,
                "skip": 1,
                "prompt": 2,
            }
            self._export_scope_combo.setCurrentIndex(scope_map.get(str(config.get("export_scope")), 1))
            self._create_update_combo.setCurrentIndex(mode_map.get(str(config.get("create_update_mode")), 2))
            self._conflict_combo.setCurrentIndex(conflict_map.get(str(config.get("conflict_policy")), 2))
            self._unlinked_combo.setCurrentIndex(unlinked_map.get(str(config.get("unlinked_task_behavior")), 1))
            self._dry_run_check.setChecked(bool(config.get("dry_run", True)))

            field_cfg = config.get("fields") or {}
            for field_name, widget_info in self._project2jira_fields.items():
                entry = field_cfg.get(field_name) or {}
                enabled = bool(entry.get("enabled", False))
                jira_field = str(entry.get("jira_field") or widget_info["default"] or "")
                widget_info["checkbox"].setChecked(enabled)
                widget_info["edit"].setCurrentText(jira_field)

            self._dict_to_table(self._project2jira_tables["issue_type_map"], config.get("issue_type_map") or {})
            self._dict_to_table(self._project2jira_tables["transition_map"], config.get("transition_map") or {})

            # Hierarchy export
            hier = config.get("hierarchy_export") or {}
            self._p2j_hierarchy_enabled_cb.setChecked(bool(hier.get("enabled", False)))
            self._p2j_epic_type_edit.setCurrentText(str(hier.get("epic_type") or "Epic"))
            self._p2j_story_type_edit.setCurrentText(str(hier.get("story_type") or "Story"))
            self._p2j_subtask_type_edit.setCurrentText(str(hier.get("subtask_type") or "Sub-task"))
            self._p2j_dep_link_type_edit.setCurrentText(str(hier.get("dependency_link_type") or "blocks"))

            # Auditability
            audit = config.get("auditability") or {}
            self._p2j_audit_enabled_cb.setChecked(bool(audit.get("enabled", False)))
        except Exception:
            pass

    def _save_project_to_jira_settings(self):
        """Save export settings into the project custom properties container."""
        if not self._project:
            return
        import json as _json
        from integrations.jira_integration import JIRA2PROJECT_PROP, PROJECT2JIRA_PROP  # type: ignore
        try:
            import java.util  # type: ignore
            props = self._project.getProjectProperties()
            cp = props.getCustomProperties()
            new_cp = java.util.HashMap()

            if cp is not None:
                for key in cp.keySet():
                    key_str = str(key)
                    if key_str in (JIRA2PROJECT_PROP, PROJECT2JIRA_PROP):
                        continue
                    new_cp.put(key, cp.get(key))

            _scope_vals = ["selected_tasks", "changed_since_last_sync", "full_project"]
            scope = _scope_vals[min(self._export_scope_combo.currentIndex(), 2)]

            _mode_vals = ["create_only", "update_only", "create_update"]
            mode = _mode_vals[min(self._create_update_combo.currentIndex(), 2)]

            _conflict_vals = ["prefer_jira", "prefer_project", "manual_review"]
            conflict = _conflict_vals[min(self._conflict_combo.currentIndex(), 2)]

            _unlinked_vals = ["create", "skip", "prompt"]
            unlinked = _unlinked_vals[min(self._unlinked_combo.currentIndex(), 2)]

            payload = {
                "export_scope": scope,
                "create_update_mode": mode,
                "conflict_policy": conflict,
                "dry_run": self._dry_run_check.isChecked(),
                "unlinked_task_behavior": unlinked,
                "fields": {},
                "issue_type_map": self._table_to_dict(self._project2jira_tables["issue_type_map"]),
                "transition_map": self._table_to_dict(self._project2jira_tables["transition_map"]),
                "hierarchy_export": {
                    "enabled": self._p2j_hierarchy_enabled_cb.isChecked(),
                    "epic_type": self._p2j_epic_type_edit.currentText().strip() or "Epic",
                    "story_type": self._p2j_story_type_edit.currentText().strip() or "Story",
                    "subtask_type": self._p2j_subtask_type_edit.currentText().strip() or "Sub-task",
                    "dependency_link_type": self._p2j_dep_link_type_edit.currentText().strip() or "blocks",
                },
                "auditability": {
                    "enabled": self._p2j_audit_enabled_cb.isChecked(),
                },
            }
            for field_name, widget_info in self._project2jira_fields.items():
                payload["fields"][field_name] = {
                    "enabled": widget_info["checkbox"].isChecked(),
                    "jira_field": widget_info["edit"].currentText().strip(),
                }

            new_cp.put(PROJECT2JIRA_PROP, _json.dumps(payload, ensure_ascii=False))
            if new_cp.get(JIRA2PROJECT_PROP) is None:
                new_cp.put(JIRA2PROJECT_PROP, _json.dumps({}))
            props.setCustomProperties(new_cp)
        except Exception as exc:
            QMessageBox.warning(self, "Warning", f"Could not save Project -> Jira settings:\n{exc}")

    def _validate_project_to_jira_settings(self) -> tuple[bool, str]:
        """Validate export settings before saving."""
        if not self._project:
            return True, ""

        enabled_fields = []
        for field_name, widget_info in self._project2jira_fields.items():
            if widget_info["checkbox"].isChecked():
                enabled_fields.append((field_name, widget_info["edit"].currentText().strip()))

        if not enabled_fields:
            return False, "Select at least one Project -> Jira field to export."

        invalid = [field_name for field_name, jira_field in enabled_fields if not jira_field]
        if invalid:
            return False, "Every enabled export field needs a Jira field mapping."

        _mode_vals = ["create_only", "update_only", "create_update"]
        create_mode = _mode_vals[min(self._create_update_combo.currentIndex(), 2)]

        if create_mode in ("create_only", "create_update"):
            mapped_targets = {
                jira_field.strip().lower()
                for _, jira_field in enabled_fields
                if jira_field
            }
            missing_required = sorted(_PROJECT2JIRA_REQUIRED_CREATE_FIELDS - mapped_targets)
            if missing_required:
                return False, (
                    "Create-capable export modes require mappings for Jira field(s): "
                    + ", ".join(missing_required)
                    + "."
                )

        issue_type_map = self._table_to_dict(self._project2jira_tables["issue_type_map"])
        transition_map = self._table_to_dict(self._project2jira_tables["transition_map"])

        if not issue_type_map:
            return False, "Add at least one task type -> Jira issue type mapping."

        missing_transition_targets = [
            status for status, transition in transition_map.items()
            if not str(transition).strip()
        ]
        if missing_transition_targets:
            return False, "Every transition mapping needs a Jira transition id or name."

        include_keys = {k.upper() for k in self._parse_csv_keys(self._j2p_preview_include_edit.text())}
        exclude_keys = {k.upper() for k in self._parse_csv_keys(self._j2p_preview_exclude_edit.text())}
        overlap = sorted(include_keys & exclude_keys)
        if overlap:
            return False, "Preview include and exclude lists overlap: " + ", ".join(overlap)

        # Best-effort server capability validation for issue types.
        current_server = self._server_combo.currentData() if self._server_combo.isEnabled() else None
        if current_server:
            try:
                from integrations.jira_integration import get_jira_client  # type: ignore
                jira_client, err = get_jira_client(current_server)
                if jira_client is not None:
                    mapped_issue_types = {v for v in issue_type_map.values() if v}
                    available_issue_types = set()
                    try:
                        for issue_type in jira_client.issue_types():
                            available_issue_types.add(str(getattr(issue_type, "name", issue_type)))
                    except Exception:
                        available_issue_types = set()
                    missing_issue_types = sorted(mapped_issue_types - available_issue_types)
                    if missing_issue_types:
                        return False, (
                            "Unknown Jira issue type(s): " + ", ".join(missing_issue_types) +
                            ". Check the mapping against the selected Jira server."
                        )

                    if transition_map:
                        available_transition_ids = set()
                        available_transition_names = set()

                        for mapped_issue_type in sorted(mapped_issue_types):
                            safe_issue_type = str(mapped_issue_type).replace('"', '\\"')
                            sample_jql = f'issuetype = "{safe_issue_type}" ORDER BY updated DESC'
                            try:
                                issues = jira_client.search_issues(sample_jql, maxResults=1)
                            except Exception:
                                issues = []
                            if not issues:
                                continue

                            sample_issue = issues[0]
                            try:
                                transitions = jira_client.transitions(sample_issue) or []
                            except Exception:
                                transitions = []

                            for transition in transitions:
                                if isinstance(transition, dict):
                                    transition_id = str(transition.get("id", "")).strip()
                                    transition_name = str(transition.get("name", "")).strip()
                                else:
                                    transition_id = str(getattr(transition, "id", "")).strip()
                                    transition_name = str(getattr(transition, "name", "")).strip()

                                if transition_id:
                                    available_transition_ids.add(transition_id)
                                if transition_name:
                                    available_transition_names.add(transition_name.lower())

                        if not available_transition_ids and not available_transition_names:
                            return False, (
                                "Could not validate transition mappings against Jira server capabilities. "
                                "Ensure mapped issue types have at least one existing issue with accessible transitions."
                            )

                        invalid_transitions = []
                        for transition_value in {
                            str(v).strip()
                            for v in transition_map.values()
                            if str(v).strip()
                        }:
                            if transition_value in available_transition_ids:
                                continue
                            if transition_value.lower() in available_transition_names:
                                continue
                            invalid_transitions.append(transition_value)

                        if invalid_transitions:
                            return False, (
                                "Unknown Jira transition id/name: "
                                + ", ".join(sorted(invalid_transitions))
                                + ". Check transition mappings against allowed server transitions."
                            )
                elif err:
                    # Connection failures are reported in the sync flow; keep save-time validation local.
                    pass
            except Exception:
                pass

        return True, ""

    def _test_selected_server_connection(self):
        """Test the currently selected Jira server from the top-level combo."""
        if not self._server_combo.isEnabled():
            QMessageBox.warning(self, "No Server Configured", "Please configure at least one Jira server first.")
            return
        server = self._server_combo.currentData()
        if not server:
            QMessageBox.warning(self, "No Server Selected", "Please select a Jira server first.")
            return

        try:
            from integrations import jira_integration
            if server.get("auth_mode") == "keepass" and not self._sm.is_keepass_unlocked():
                answer = QMessageBox.question(
                    self,
                    "KeePass Locked",
                    "The KeePass database is locked.\n\nDo you want to unlock it now?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if answer != QMessageBox.Yes:
                    return
                ok, _ = self._sm.auto_unlock_keepass()
                if not ok:
                    pwd, entered = QInputDialog.getText(self, "KeePass Master Password", "Enter KeePass master password:", QLineEdit.Password)
                    if not entered:
                        return
                    ok, err = self._sm.unlock_keepass(pwd)
                    if not ok:
                        QMessageBox.warning(self, "Unlock Failed", f"Could not open KeePass database:\n{err}")
                        return

            ok, error = jira_integration.test_connection(server)
            if ok:
                QMessageBox.information(self, "Jira Connection", f"Connection test succeeded for '{server.get('name', '(unnamed)')}' .")
                self._refresh_issue_type_warning(server, jira_integration)
            else:
                QMessageBox.critical(self, "Jira Connection", f"Connection test failed:\n\n{error}")
        except Exception as exc:
            QMessageBox.critical(self, "Jira Connection", f"Connection test failed:\n\n{exc}")

    def _refresh_issue_type_warning(self, server: dict, jira_integration) -> None:
        """Fetch available issue types from the server and warn about invalid mappings.

        Called after a successful Test Connection.  Updates
        ``self._issue_type_warning_label`` in the Project -> Jira tab.
        Also restricts the issue-type combo dropdowns in the mapping table and
        hierarchy section to only offer types that actually exist on the server.
        """
        if not hasattr(self, "_issue_type_warning_label"):
            return

        # Discover which project(s) the configured filter targets by executing it
        # against the server and collecting the project keys from the results.
        project_key = ""
        filter_value = self._filter_edit.text().strip() if hasattr(self, "_filter_edit") else ""
        filter_type = (
            "filter"
            if hasattr(self, "_radio_filter_id") and self._radio_filter_id.isChecked()
            else "jql"
        )
        if filter_value:
            try:
                jira_client, _err = jira_integration.get_jira_client(server)
                if jira_client is not None:
                    # Resolve saved filter -> JQL first if needed
                    jql = filter_value
                    if filter_type == "filter":
                        jql, _ = jira_integration.resolve_filter_to_jql(
                            jira_client, filter_value, "filter"
                        )
                    if jql:
                        issues = list(jira_client.search_issues(
                            jql, maxResults=5, fields="project"
                        ))
                        found_keys = sorted({
                            str(getattr(getattr(i.fields, "project", None), "key", "") or "")
                            for i in issues
                        } - {""})
                        if found_keys:
                            project_key = found_keys[0]
            except Exception:
                pass

        caps = jira_integration.fetch_server_capabilities(server, project_key)
        available = set(caps.get("issue_types") or [])
        if caps.get("error") and not available:
            self._issue_type_warning_label.setVisible(False)
            return

        available_list = sorted(available)

        if available_list:
            # Restrict the right-column (Jira issue type) combos in the mapping
            # table to only show types that exist on the server.
            table = self._project2jira_tables.get("issue_type_map")
            if table is not None:
                table.setProperty("right_options", available_list)
                for row in range(table.rowCount()):
                    combo = table.cellWidget(row, 1)
                    if isinstance(combo, QComboBox):
                        current = combo.currentText()
                        combo.clear()
                        combo.addItems(available_list)
                        if current:
                            combo.setCurrentText(current)

            # Restrict hierarchy type combos the same way.
            for attr in ("_p2j_epic_type_edit", "_p2j_story_type_edit", "_p2j_subtask_type_edit"):
                combo = getattr(self, attr, None)
                if combo is not None:
                    current = combo.currentText()
                    combo.clear()
                    combo.addItems(available_list)
                    if current:
                        combo.setCurrentText(current)

        # Collect all Jira issue types configured in the mapping table
        issue_type_map = self._table_to_dict(self._project2jira_tables["issue_type_map"])
        mapped_types = {v.strip() for v in issue_type_map.values() if v.strip()}

        # Also include hierarchy types when hierarchy export is enabled
        hier_unsupported: list[str] = []
        if hasattr(self, "_p2j_hierarchy_enabled_cb") and self._p2j_hierarchy_enabled_cb.isChecked():
            for attr, label in [
                ("_p2j_epic_type_edit",    "Epic type"),
                ("_p2j_story_type_edit",   "Story type"),
                ("_p2j_subtask_type_edit", "Sub-task type"),
            ]:
                combo = getattr(self, attr, None)
                if combo is not None:
                    val = combo.currentText().strip()
                    if val:
                        mapped_types.add(val)
                        if available and val not in available:
                            hier_unsupported.append(f"{label} '{val}'")

        unsupported = sorted(mapped_types - available) if available else []
        if unsupported:
            types_str = ", ".join(f"'{t}'" for t in unsupported)
            available_str = ", ".join(sorted(available)) if available else "(none)"
            msg = (
                f"\u26a0\ufe0f  Issue type(s) not available on this server: {types_str}.\n"
                f"Available types: {available_str}.\n"
                "Update the task type mappings to use a supported type, "
                "or create mode will fail for those task types."
            )
            if hier_unsupported:
                msg += (
                    "\nHierarchy export uses unsupported types: "
                    + ", ".join(hier_unsupported)
                    + ". Disable hierarchy export or change to a supported type."
                )
            self._issue_type_warning_label.setText(msg)
            self._issue_type_warning_label.setVisible(True)
        else:
            self._issue_type_warning_label.setVisible(False)

    def _test_filter(self):
        """Test the JQL filter by fetching issues from the selected Jira server."""
        # Validate that a server is selected
        if not self._server_combo.isEnabled():
            QMessageBox.warning(
                self,
                "No Server Configured",
                "Please configure at least one Jira server before testing the filter.",
            )
            return
        
        current_server = self._server_combo.currentData()
        if not current_server:
            QMessageBox.warning(
                self,
                "No Server Selected",
                "Please select a Jira server before testing the filter.",
            )
            return
        
        # Validate that a filter is provided
        filter_text = self._filter_edit.text().strip()
        filter_type = "filter" if self._radio_filter_id.isChecked() else "jql"
        if not filter_text:
            QMessageBox.warning(
                self,
                "No Filter Specified",
                "Please enter a filter to test.",
            )
            return

        # Attempt to get a Jira client and search for issues
        try:
            from integrations import jira_integration

            # If the selected server uses KeePass and the database is locked,
            # offer to unlock before attempting the connection.
            if current_server.get("auth_mode") == "keepass" and not self._sm.is_keepass_unlocked():
                answer = QMessageBox.question(
                    self,
                    "KeePass Locked",
                    "\U0001f510  KeePass is required to connect to Jira\n\n"
                    "The configured Jira server uses KeePass for credential storage,\n"
                    "but KeePass is currently locked.\n\n"
                    "Would you like to unlock KeePass now to proceed with \u2018Test Filter\u2019?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if answer != QMessageBox.Yes:
                    return
                # Try auto-unlock first; fall back to password prompt
                ok, _ = self._sm.auto_unlock_keepass()
                if not ok:
                    pwd, entered = QInputDialog.getText(
                        self,
                        "KeePass Master Password",
                        "Enter KeePass master password:",
                        QLineEdit.Password,
                    )
                    if not entered:
                        return
                    ok, err = self._sm.unlock_keepass(pwd)
                    if not ok:
                        QMessageBox.warning(
                            self,
                            "Unlock Failed",
                            f"Could not open KeePass database:\n{err}",
                        )
                        return

            # Show a modal progress dialog while running the test
            from PyQt5.QtWidgets import QProgressDialog  # type: ignore
            progress = QProgressDialog(
                f"Testing filter against Jira server\u2026",
                None, 0, 0, self,
            )
            progress.setWindowTitle("Testing Filter")
            progress.setWindowModality(Qt.ApplicationModal)
            progress.setMinimumWidth(360)
            progress.setCancelButton(None)
            progress.show()
            from PyQt5.QtWidgets import QApplication  # type: ignore
            QApplication.processEvents()

            try:
                jira, error = jira_integration.get_jira_client(current_server)

                if jira is None:
                    progress.close()
                    # Record failed filter test
                    server_name = current_server.get("name", "(unnamed)")
                    jira_integration.record_filter_test(server_name, filter_text, 0, error)
                    QMessageBox.critical(
                        self,
                        "Connection Failed",
                        f"Failed to connect to Jira server:\n\n{error}",
                    )
                    return

                # Resolve saved filter to JQL if needed
                jql, resolve_error = jira_integration.resolve_filter_to_jql(
                    jira, filter_text, filter_type
                )
                if resolve_error:
                    progress.close()
                    server_name = current_server.get("name", "(unnamed)")
                    jira_integration.record_filter_test(server_name, filter_text, 0, resolve_error)
                    QMessageBox.critical(
                        self,
                        "Filter Resolution Failed",
                        f"Could not resolve the saved filter:\n\n{resolve_error}",
                    )
                    return

                # Search for issues with the resolved JQL (limit to 50 results for testing)
                issues = jira.search_issues(jql, maxResults=50)
                
                progress.close()
                
                # Record successful filter test
                server_name = current_server.get("name", "(unnamed)")
                jira_integration.record_filter_test(server_name, filter_text, len(issues))
                
                # Show results
                jql_hint = f"\nResolved JQL: {jql}" if filter_type == "filter" else ""
                if not issues:
                    QMessageBox.information(
                        self,
                        "Filter Test Successful",
                        f"The filter is valid but returned no issues.\n\n"
                        f"Filter: {filter_text}{jql_hint}",
                    )
                else:
                    # Build a summary of the results
                    issue_summary = "\n".join([
                        f"• {issue.key}: {issue.fields.summary}"
                        for issue in issues[:10]  # Show first 10
                    ])

                    more_text = ""
                    if len(issues) > 10:
                        more_text = f"\n\n... and {len(issues) - 10} more issue(s)"

                    QMessageBox.information(
                        self,
                        "Filter Test Successful",
                        f"Found {len(issues)} issue(s):{jql_hint}\n\n{issue_summary}{more_text}",
                    )
            
            finally:
                QApplication.restoreOverrideCursor()
        
        except ImportError as exc:
            # Record failed filter test due to import error
            server_name = current_server.get("name", "(unnamed)") if current_server else "unknown"
            jira_integration.record_filter_test(server_name, filter_text, 0, f"ImportError: {exc}")
            QMessageBox.critical(
                self,
                "Import Error",
                f"Failed to import Jira integration module:\n\n{exc}\n\n"
                f"Make sure the 'jira' package is installed.",
            )
        except Exception as exc:
            # Record failed filter test
            server_name = current_server.get("name", "(unnamed)") if current_server else "unknown"
            jira_integration.record_filter_test(server_name, filter_text, 0, str(exc))
            QMessageBox.critical(
                self,
                "Filter Test Failed",
                f"An error occurred while testing the filter:\n\n{exc}",
            )

    def _get_filter_from_project(self) -> tuple[str, str]:
        """Read the filter value and type from project custom properties.

        Returns:
            ``(filter_value, filter_type)`` where *filter_type* is ``"jql"``
            (default) or ``"filter"``.
        """
        if not self._project:
            return "", "jql"

        try:
            import json as _json
            from integrations.jira_integration import (
                JIRA2PROJECT_PROP,
                JIRA_SYNC_FILTER_PROP,
                JIRA_SYNC_FILTER_TYPE_PROP,
            )
            props = self._project.getProjectProperties()
            cp = props.getCustomProperties()
            if cp is not None:
                # New container format: "jira2project" = JSON string
                j2p_str = cp.get(JIRA2PROJECT_PROP)
                if j2p_str:
                    try:
                        j2p = _json.loads(str(j2p_str))
                        filter_value = str(j2p.get("filter") or "").strip()
                        filter_type = str(j2p.get("filter_type") or "jql").strip()
                        if filter_type not in ("jql", "filter"):
                            filter_type = "jql"
                        return filter_value, filter_type
                    except Exception:
                        pass
                # Backward compat: old flat keys
                val = cp.get(JIRA_SYNC_FILTER_PROP)
                filter_type = cp.get(JIRA_SYNC_FILTER_TYPE_PROP)
                filter_value = str(val).strip() if val else ""
                filter_type = str(filter_type).strip() if filter_type else "jql"
                if filter_type not in ("jql", "filter"):
                    filter_type = "jql"
                return filter_value, filter_type
        except Exception:
            pass

        return "", "jql"
    
    def _load_field_selections(self):
        """Load field selection checkbox states from project custom properties."""
        if not self._project:
            return

        try:
            import json as _json
            from integrations.jira_integration import JIRA2PROJECT_PROP
            props = self._project.getProjectProperties()
            cp = props.getCustomProperties()
            if cp is not None:
                # New container format: "jira2project" = JSON string
                j2p_str = cp.get(JIRA2PROJECT_PROP)
                if j2p_str:
                    try:
                        j2p = _json.loads(str(j2p_str))
                        fields = j2p.get("fields") or {}
                        for field_name, checkbox in self._field_checkboxes.items():
                            checkbox.setChecked(bool(fields.get(field_name, False)))
                        self._apply_jira2project_field_dependencies()
                        self._load_jira2project_advanced_settings(j2p)
                        return
                    except Exception:
                        pass
                # Backward compat: old flat keys ("JIRA Sync Field {field_name}")
                for field_name, checkbox in self._field_checkboxes.items():
                    prop_key = f"JIRA Sync Field {field_name}"
                    field_val = cp.get(prop_key)
                    checkbox.setChecked(self._to_bool(field_val))
                self._apply_jira2project_field_dependencies()
                self._load_jira2project_advanced_settings({})
        except Exception:
            # If loading fails, default to unchecked (False)
            self._apply_jira2project_field_dependencies()
            self._load_jira2project_advanced_settings({})

    @staticmethod
    def _to_bool(value) -> bool:
        """Convert various representations to boolean."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        try:
            # Handle Java Boolean
            return bool(value)
        except:
            return False
    
    def _save_filter_to_project(self):
        """Write the filter value, type, and field selections to project custom properties."""
        if not self._project:
            return

        import json as _json
        from integrations.jira_integration import (
            JIRA2PROJECT_PROP,
            PROJECT2JIRA_PROP,
            JIRA_SYNC_FILTER_PROP,
            JIRA_SYNC_FILTER_TYPE_PROP,
        )
        filter_text = self._filter_edit.text().strip()
        filter_type = "filter" if self._radio_filter_id.isChecked() else "jql"

        try:
            import java.util  # type: ignore
            props = self._project.getProjectProperties()
            cp = props.getCustomProperties()
            new_cp = java.util.HashMap()

            # Preserve existing custom properties, skipping old flat Jira keys
            if cp is not None:
                for key in cp.keySet():
                    key_str = str(key)
                    if key_str in (JIRA_SYNC_FILTER_PROP, JIRA_SYNC_FILTER_TYPE_PROP):
                        continue
                    if key_str.startswith("JIRA Sync Field "):
                        continue
                    new_cp.put(key, cp.get(key))

            # Build and store jira2project container
            j2p = {}
            if filter_text:
                j2p["filter"] = filter_text
                j2p["filter_type"] = filter_type
            j2p["fields"] = {
                field: checkbox.isChecked()
                for field, checkbox in self._field_checkboxes.items()
            }
            j2p["advanced"] = self._build_jira2project_advanced_payload()
            new_cp.put(JIRA2PROJECT_PROP, _json.dumps(j2p, ensure_ascii=False))

            # Ensure project2jira container exists (even if empty)
            if new_cp.get(PROJECT2JIRA_PROP) is None:
                new_cp.put(PROJECT2JIRA_PROP, _json.dumps({}))

            props.setCustomProperties(new_cp)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Warning",
                f"Could not save settings to project:\n{exc}"
            )
    
    def _accept(self):
        """Save the selected server and filter, then close."""
        if self._server_combo.isEnabled():
            current_server = self._server_combo.currentData()
            if current_server:
                server_name = current_server.get("name", "")
                self._sm.set_jira_sync_server(server_name)
        
        if self._has_project:
            ok, error = self._validate_project_to_jira_settings()
            if not ok:
                QMessageBox.warning(self, "Validation", error)
                return

            # Save both Jira tabs into the project custom properties
            self._save_filter_to_project()
            self._save_project_to_jira_settings()
        
        self.accept()


# ------------------------------------------------------------------ #
# Jira Push Preview Dialog                                             #
# ------------------------------------------------------------------ #

class JiraPushPreviewDialog(QDialog):
    """Dry-run preview of Project -> Jira push actions.

    Shows a table of planned creates / updates / transitions / skips.
    Each row has an Include checkbox so the user can exclude specific
    tasks before pressing "Execute".  Cancelled returns Rejected.
    """

    def __init__(self, preview_actions: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Jira Sync — Preview (Project → Jira)")
        self.setMinimumWidth(780)
        self.setMinimumHeight(520)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Project → Jira  Dry-run Preview",
            "Review the planned actions. Uncheck rows to skip individual tasks.",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 12, 16, 8)
        bv.setSpacing(8)

        summary = QLabel(
            f"<b>{len(preview_actions)}</b> action(s) planned. "
            "Uncheck rows to exclude them from the actual run."
        )
        summary.setWordWrap(True)
        bv.addWidget(summary)

        self._table = QTableWidget(len(preview_actions), 5)
        self._table.setHorizontalHeaderLabels(
            ["Include", "Issue Key", "Task Name", "Action", "Details"]
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

        _ACTION_COLORS = {
            "create": "#d4edda",
            "update": "#cce5ff",
            "transition": "#fff3cd",
            "skip":   "#f8d7da",
        }

        self._checkboxes: list[QCheckBox] = []
        for row, action in enumerate(preview_actions):
            cb = QCheckBox()
            cb.setChecked(action.get("action") != "skip")
            cb_widget = QWidget()
            cb_layout = QHBoxLayout(cb_widget)
            cb_layout.setContentsMargins(4, 0, 4, 0)
            cb_layout.addWidget(cb)
            cb_layout.setAlignment(cb, Qt.AlignCenter)
            self._table.setCellWidget(row, 0, cb_widget)
            self._checkboxes.append(cb)

            issue_key = str(action.get("jira_key") or action.get("issue_key") or "NEW")
            task_name = str(action.get("task_name") or action.get("summary") or "")
            act_str   = str(action.get("action") or "").capitalize()
            details   = str(action.get("details") or action.get("changed_fields") or "")

            for col, text in [(1, issue_key), (2, task_name), (3, act_str), (4, details)]:
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                bg_color = _ACTION_COLORS.get(str(action.get("action") or ""), "")
                if bg_color:
                    from PyQt5.QtGui import QColor  # type: ignore
                    item.setBackground(QColor(bg_color))
                self._table.setItem(row, col, item)

        bv.addWidget(self._table)

        # Select-all / deselect-all helpers
        btn_row = QWidget()
        btn_row_h = QHBoxLayout(btn_row)
        btn_row_h.setContentsMargins(0, 0, 0, 0)
        btn_row_h.setSpacing(8)
        select_all = _btn("Select All", flat=True)
        select_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self._checkboxes])
        deselect_all = _btn("Deselect All", flat=True)
        deselect_all.clicked.connect(lambda: [cb.setChecked(False) for cb in self._checkboxes])
        btn_row_h.addWidget(select_all)
        btn_row_h.addWidget(deselect_all)
        btn_row_h.addStretch()
        bv.addWidget(btn_row)

        root.addWidget(body)

        execute = _btn("Execute Selected")
        execute.setDefault(True)
        execute.clicked.connect(self.accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(execute, cancel))

        self._preview_actions = preview_actions

    def get_included_task_uids(self) -> set:
        """Return set of task UIDs whose Include checkbox is checked."""
        included = set()
        for row, (cb, action) in enumerate(zip(self._checkboxes, self._preview_actions)):
            if cb.isChecked():
                uid = action.get("task_uid")
                if uid is not None:
                    included.add(str(uid))
        return included


# ------------------------------------------------------------------ #
# Jira Servers Dialog                                                  #
# ------------------------------------------------------------------ #

class JiraServersDialog(QDialog):
    """Manage the full list of Jira server configurations."""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._servers: list[dict] = list(self._sm.get_jira_servers())

        self.setWindowTitle("Jira Server Configurations")
        self.setMinimumWidth(640)
        self.setMinimumHeight(420)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Jira Servers",
            "Manage multiple Jira server connections",
        ))

        body = QWidget()
        bv = QHBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 8)
        bv.setSpacing(12)

        # Left: server list
        left = QVBoxLayout()
        list_lbl = QLabel("Configured Servers:")
        list_lbl.setStyleSheet("font-weight: bold; color: #2B579A;")
        left.addWidget(list_lbl)
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self._edit_server)
        left.addWidget(self._list)

        # Right: action buttons
        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignTop)
        self._add_btn  = _btn("Add\u2026")
        self._edit_btn = _btn("Edit\u2026")
        self._del_btn  = _btn("Delete")
        self._up_btn   = _btn("\u25b2", flat=True)
        self._down_btn = _btn("\u25bc", flat=True)
        self._add_btn.clicked.connect(self._add_server)
        self._edit_btn.clicked.connect(self._edit_server)
        self._del_btn.clicked.connect(self._delete_server)
        self._up_btn.clicked.connect(self._move_up)
        self._down_btn.clicked.connect(self._move_down)
        for b in (self._add_btn, self._edit_btn, self._del_btn, self._up_btn, self._down_btn):
            right.addWidget(b)

        bv.addLayout(left, stretch=1)
        bv.addLayout(right)
        root.addWidget(body)

        ok = _btn("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

        self._refresh_list()
        self._on_selection_changed()

    # ---- List management ----

    def _refresh_list(self):
        current_row = self._list.currentRow()
        self._list.clear()
        for s in self._servers:
            mode = "KeePass" if s.get("auth_mode") == "keepass" else "Manual"
            self._list.addItem(
                f"{s.get('name', '(unnamed)')}  [{mode}]  \u2014  {s.get('url', '')}"
            )
        if 0 <= current_row < self._list.count():
            self._list.setCurrentRow(current_row)

    def _on_selection_changed(self):
        row = self._list.currentRow()
        has = row >= 0
        self._edit_btn.setEnabled(has)
        self._del_btn.setEnabled(has)
        self._up_btn.setEnabled(has and row > 0)
        self._down_btn.setEnabled(has and row < len(self._servers) - 1)

    def _add_server(self):
        dlg = JiraServerEditDialog(self._sm, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._servers.append(dlg.get_server())
            self._refresh_list()
            self._list.setCurrentRow(len(self._servers) - 1)
            self._on_selection_changed()

    def _edit_server(self):
        row = self._list.currentRow()
        if row < 0:
            return
        dlg = JiraServerEditDialog(self._sm, server=self._servers[row], parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._servers[row] = dlg.get_server()
            self._refresh_list()
            self._list.setCurrentRow(row)
            self._on_selection_changed()

    def _delete_server(self):
        row = self._list.currentRow()
        if row < 0:
            return
        name = self._servers[row].get("name", "?")
        reply = QMessageBox.question(
            self, "Delete Server",
            f"Delete server '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        del self._servers[row]
        self._refresh_list()
        self._on_selection_changed()

    def _move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        self._servers[row - 1], self._servers[row] = self._servers[row], self._servers[row - 1]
        self._refresh_list()
        self._list.setCurrentRow(row - 1)
        self._on_selection_changed()

    def _move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._servers) - 1:
            return
        self._servers[row], self._servers[row + 1] = self._servers[row + 1], self._servers[row]
        self._refresh_list()
        self._list.setCurrentRow(row + 1)
        self._on_selection_changed()

    def _accept(self):
        self._sm.set_jira_servers(self._servers)
        self.accept()


# ------------------------------------------------------------------ #
# Confluence Calendar Configuration Dialog                             #
# ------------------------------------------------------------------ #

class ConfluenceCalendarConfigDialog(QDialog):
    """Configure Confluence Calendar sync settings.

    Two sections:
    1. Authentication — choose between Manual (no SSO auto-fill) and
       From KeePass entry (auto-fills the Microsoft SSO page via Playwright).
    2. Calendar Props — edit the four per-project calendar properties stored in
       the project's enterprise custom fields (enabled only when a project is open).
    """

    def __init__(self, settings_manager, project=None, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._project = project  # may be None when no project is open

        self.setWindowTitle("Confluence Calendar Configuration")
        self.setMinimumWidth(540)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Confluence Calendar Configuration",
            "Authentication mode and per-project calendar properties",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 16, 16, 8)
        bv.setSpacing(12)

        # ---- Section 1: Authentication ----
        bv.addWidget(self._build_auth_section())

        # ---- Section 2: Calendar Props ----
        bv.addWidget(self._build_calendar_props_section())

        bv.addStretch()

        # Wrap in a scroll area so the dialog can shrink on small monitors
        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(scroll, stretch=1)

        ok = _btn("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

    # ---------------------------------------------------------------- #
    # Authentication section                                            #
    # ---------------------------------------------------------------- #

    def _build_auth_section(self) -> QGroupBox:
        grp = QGroupBox("Authentication")
        bv = QVBoxLayout(grp)
        bv.setSpacing(8)

        # ---- Mode selector (mirrors JiraServerEditDialog) ----
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._auth_combo = QComboBox()
        self._auth_combo.addItem("Manual (no SSO auto-fill)", "manual")
        self._auth_combo.addItem("From KeePass entry (auto-fill SSO)", "keepass")
        saved_mode = self._sm.get_confluence_auth_mode()
        self._auth_combo.setCurrentIndex(1 if saved_mode == "keepass" else 0)
        self._auth_combo.currentIndexChanged.connect(self._on_auth_mode_changed)
        form.addRow("Authentication:", self._auth_combo)
        bv.addLayout(form)

        # ---- Manual group ----
        self._manual_group = QGroupBox("Manual Sign-in")
        mg_vbox = QVBoxLayout(self._manual_group)
        mg_note = QLabel(
            "When syncing, a Chromium browser window will open and navigate to "
            "Confluence. You complete the entire sign-in (username, password, MFA) "
            "manually. The session is cached so subsequent syncs are headless."
        )
        mg_note.setWordWrap(True)
        mg_note.setStyleSheet("color: #555; font-size: 11px; font-style: italic;")
        mg_vbox.addWidget(mg_note)
        bv.addWidget(self._manual_group)

        # ---- KeePass group ----
        self._kp_group = QGroupBox("KeePass Credentials")
        kp_vbox = QVBoxLayout(self._kp_group)
        kp_vbox.setSpacing(6)

        kp_note = QLabel(
            "Username and password from the selected KeePass entry are pre-filled "
            "on the Microsoft SSO login page. "
            "The MFA / Authenticator step is always completed manually."
        )
        kp_note.setWordWrap(True)
        kp_note.setStyleSheet("color: #555; font-size: 11px; font-style: italic;")
        kp_vbox.addWidget(kp_note)

        # Stacked widget: 0 = not configured, 1 = locked, 2 = unlocked
        self._kp_stack = QStackedWidget()

        # Page 0 – KeePass not configured
        p0 = QWidget()
        p0v = QVBoxLayout(p0)
        p0v.setContentsMargins(0, 4, 0, 4)
        p0v.setSpacing(8)
        p0_lbl = QLabel("KeePass is not configured.")
        p0_lbl.setStyleSheet("color: #888; font-size: 12px;")
        cfg_btn = _btn("Configure KeePass\u2026")
        cfg_btn.clicked.connect(self._configure_keepass)
        p0v.addWidget(p0_lbl)
        p0v.addWidget(cfg_btn)
        self._kp_stack.addWidget(p0)

        # Page 1 – configured but locked
        p1 = QWidget()
        p1v = QVBoxLayout(p1)
        p1v.setContentsMargins(0, 4, 0, 4)
        p1v.setSpacing(8)
        p1_lbl = QLabel("KeePass database is locked.")
        p1_lbl.setStyleSheet("color: #888; font-size: 12px;")
        unlock_btn = _btn("Unlock KeePass\u2026")
        unlock_btn.clicked.connect(self._unlock_keepass)
        p1v.addWidget(p1_lbl)
        p1v.addWidget(unlock_btn)
        self._kp_stack.addWidget(p1)

        # Page 2 – unlocked: entry selector + new entry button
        p2 = QWidget()
        p2f = QFormLayout(p2)
        p2f.setContentsMargins(0, 4, 0, 4)
        p2f.setSpacing(8)
        p2f.setLabelAlignment(Qt.AlignRight)

        entry_row_w = QWidget()
        entry_row_h = QHBoxLayout(entry_row_w)
        entry_row_h.setContentsMargins(0, 0, 0, 0)
        self._kp_entry_combo = QComboBox()
        self._kp_entry_combo.setEditable(True)
        self._kp_entry_combo.setPlaceholderText("Select or type entry title \u2026")
        self._kp_entry_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
        entry_row_h.addWidget(self._kp_entry_combo, stretch=1)
        new_entry_btn = _btn("New Entry\u2026", flat=True)
        new_entry_btn.setMinimumWidth(90)
        new_entry_btn.clicked.connect(self._new_kp_entry)
        entry_row_h.addWidget(new_entry_btn)
        p2f.addRow("Entry:", entry_row_w)

        self._kp_stack.addWidget(p2)
        kp_vbox.addWidget(self._kp_stack)
        bv.addWidget(self._kp_group)

        # Set initial visibility and KeePass state
        self._on_auth_mode_changed(self._auth_combo.currentIndex())

        return grp

    def _on_auth_mode_changed(self, _idx: int):
        mode = self._auth_combo.currentData()
        self._manual_group.setVisible(mode == "manual")
        self._kp_group.setVisible(mode == "keepass")
        if mode == "keepass":
            self._refresh_kp_state()

    def _refresh_kp_state(self):
        if not self._sm.is_keepass_configured():
            self._kp_stack.setCurrentIndex(0)
        elif not self._sm.is_keepass_unlocked():
            self._kp_stack.setCurrentIndex(1)
        else:
            self._kp_stack.setCurrentIndex(2)
            self._repopulate_entry_combo()

    def _repopulate_entry_combo(self):
        current = self._sm.get_confluence_keepass_entry() or ""
        self._kp_entry_combo.blockSignals(True)
        self._kp_entry_combo.clear()
        self._kp_entry_combo.addItem("")  # empty = disabled
        entries = self._sm.list_keepass_entries()
        self._kp_entry_combo.addItems(entries)
        if current:
            idx = self._kp_entry_combo.findText(current)
            if idx >= 0:
                self._kp_entry_combo.setCurrentIndex(idx)
            else:
                self._kp_entry_combo.setCurrentText(current)
        self._kp_entry_combo.blockSignals(False)

    def _configure_keepass(self):
        dlg = KeePassConfigDialog(self._sm, self)
        dlg.exec_()
        self._refresh_kp_state()

    def _unlock_keepass(self):
        ok, _ = self._sm.auto_unlock_keepass()
        if not ok:
            pwd, entered = QInputDialog.getText(
                self, "KeePass Master Password",
                "Enter KeePass master password:",
                QLineEdit.Password,
            )
            if entered:
                ok, err = self._sm.unlock_keepass(pwd)
                if not ok:
                    QMessageBox.warning(self, "Unlock Failed",
                                        f"Could not open database:\n{err}")
        self._refresh_kp_state()

    def _new_kp_entry(self):
        dlg = KeePassNewEntryDialog(self._sm, self)
        if dlg.exec_() == QDialog.Accepted:
            self._repopulate_entry_combo()
            path = dlg.get_entry_path()
            if path:
                self._kp_entry_combo.setCurrentText(path)

    # ---------------------------------------------------------------- #
    # Calendar Props section                                            #
    # ---------------------------------------------------------------- #

    def _build_calendar_props_section(self) -> QGroupBox:
        from integrations.confluence_calendar_integration import (  # type: ignore
            CONFLUENCE_BASE_URL_PROP, CONFLUENCE_SPACE_KEY_PROP,
            CONFLUENCE_TIMEZONE_PROP, CONFLUENCE_DAYS_AHEAD_PROP,
            get_project_base_url, get_project_space_key,
            get_project_timezone, get_project_days_ahead,
        )
        self._cal_prop_keys = [
            CONFLUENCE_BASE_URL_PROP,
            CONFLUENCE_SPACE_KEY_PROP,
            CONFLUENCE_TIMEZONE_PROP,
            CONFLUENCE_DAYS_AHEAD_PROP,
        ]

        grp = QGroupBox("Calendar Properties (per-project)")
        form = QFormLayout(grp)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        has_project = self._project is not None

        self._cal_base_url_edit = QLineEdit()
        self._cal_base_url_edit.setPlaceholderText("https://confluence.example.com")
        self._cal_base_url_edit.setToolTip(f"Enterprise custom field: {CONFLUENCE_BASE_URL_PROP}")

        self._cal_space_key_edit = QLineEdit()
        self._cal_space_key_edit.setPlaceholderText("e.g. PROJ")
        self._cal_space_key_edit.setToolTip(f"Enterprise custom field: {CONFLUENCE_SPACE_KEY_PROP}")

        import zoneinfo
        from PyQt5.QtWidgets import QCompleter  # type: ignore
        _tz_names = sorted(zoneinfo.available_timezones())
        if not _tz_names:
            # zoneinfo.available_timezones() returns empty on Windows without the
            # tzdata package installed.  Try to load the zone list directly from
            # the tzdata package (listed in requirements.txt).
            try:
                import importlib.resources as _ir
                _tz_root = _ir.files("tzdata.zoneinfo")
                def _collect_zones(pkg, prefix=""):
                    _names = []
                    for _child in pkg.iterdir():
                        _n = _child.name
                        if _n in ("__init__.py", "__pycache__", "+VERSION"):
                            continue
                        _full = f"{prefix}/{_n}" if prefix else _n
                        try:
                            _names.extend(_collect_zones(_child, _full))
                        except Exception:
                            _names.append(_full)
                    return _names
                _tz_names = sorted(_collect_zones(_tz_root))
            except Exception:
                _tz_names = ["Africa/Abidjan", "America/New_York", "Europe/Berlin", "UTC"]
        self._cal_timezone_combo = QComboBox()
        self._cal_timezone_combo.setEditable(True)
        self._cal_timezone_combo.setInsertPolicy(QComboBox.NoInsert)
        self._cal_timezone_combo.addItem("")  # empty = unset
        self._cal_timezone_combo.addItems(_tz_names)
        _tz_completer = QCompleter(_tz_names, self._cal_timezone_combo)
        _tz_completer.setCompletionMode(QCompleter.PopupCompletion)
        _tz_completer.setFilterMode(Qt.MatchContains)
        _tz_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._cal_timezone_combo.setCompleter(_tz_completer)
        self._cal_timezone_combo.setToolTip(f"Enterprise custom field: {CONFLUENCE_TIMEZONE_PROP}")

        self._cal_days_ahead_edit = QLineEdit()
        self._cal_days_ahead_edit.setPlaceholderText("365")
        self._cal_days_ahead_edit.setToolTip(f"Enterprise custom field: {CONFLUENCE_DAYS_AHEAD_PROP}")

        if has_project:
            self._cal_base_url_edit.setText(get_project_base_url(self._project) or "")
            self._cal_space_key_edit.setText(get_project_space_key(self._project) or "")
            tz_val = get_project_timezone(self._project) or "Europe/Berlin"
            _tz_idx = self._cal_timezone_combo.findText(tz_val)
            if _tz_idx >= 0:
                self._cal_timezone_combo.setCurrentIndex(_tz_idx)
            else:
                self._cal_timezone_combo.setCurrentText(tz_val)
            days = get_project_days_ahead(self._project)
            self._cal_days_ahead_edit.setText(str(days) if days else "")
        else:
            # Pre-select Europe/Berlin even when disabled so the hint is visible
            _tz_idx = self._cal_timezone_combo.findText("Europe/Berlin")
            if _tz_idx >= 0:
                self._cal_timezone_combo.setCurrentIndex(_tz_idx)

        form.addRow("Base URL:", self._cal_base_url_edit)
        form.addRow("Space Key:", self._cal_space_key_edit)
        form.addRow("Timezone:", self._cal_timezone_combo)
        form.addRow("Days Ahead:", self._cal_days_ahead_edit)

        if not has_project:
            for edit in (self._cal_base_url_edit, self._cal_space_key_edit,
                         self._cal_days_ahead_edit):
                edit.setEnabled(False)
                edit.setPlaceholderText("(open a project to edit)")
            self._cal_timezone_combo.setEnabled(False)
            hint = QLabel("Open a project to edit calendar properties.")
            hint.setStyleSheet("color: #888; font-size: 11px; font-style: italic;")
            form.addRow("", hint)

        return grp

    # ---------------------------------------------------------------- #
    # Accept                                                            #
    # ---------------------------------------------------------------- #

    def _accept(self):
        # Save auth mode
        mode = self._auth_combo.currentData()
        self._sm.set_confluence_auth_mode(mode)

        # Save KeePass entry if keepass mode and unlocked
        if mode == "keepass" and self._kp_stack.currentIndex() == 2:
            entry = self._kp_entry_combo.currentText().strip()
            self._sm.set_confluence_keepass_entry(entry)

        # Save calendar properties back to the project custom fields
        if self._project is not None:
            self._save_calendar_props()

        self.accept()

    def _save_calendar_props(self):
        """Write the four CALENDAR properties into the project's custom properties."""
        from integrations.confluence_calendar_integration import (  # type: ignore
            CONFLUENCE_BASE_URL_PROP, CONFLUENCE_SPACE_KEY_PROP,
            CONFLUENCE_TIMEZONE_PROP, CONFLUENCE_DAYS_AHEAD_PROP,
        )
        values = {
            CONFLUENCE_BASE_URL_PROP:   self._cal_base_url_edit.text().strip(),
            CONFLUENCE_SPACE_KEY_PROP:  self._cal_space_key_edit.text().strip(),
            CONFLUENCE_TIMEZONE_PROP:   self._cal_timezone_combo.currentText().strip(),
            CONFLUENCE_DAYS_AHEAD_PROP: self._cal_days_ahead_edit.text().strip(),
        }
        try:
            import java.util  # type: ignore
            props = self._project.getProjectProperties()
            cp = props.getCustomProperties()
            new_cp = java.util.HashMap()
            # Preserve existing custom properties
            if cp is not None:
                for key in cp.keySet():
                    new_cp.put(key, cp.get(key))
            # Update / remove the CALENDAR keys
            for key, val in values.items():
                if val:
                    new_cp.put(key, val)
                else:
                    new_cp.remove(key)
            props.setCustomProperties(new_cp)
        except Exception as exc:
            QMessageBox.warning(self, "Warning",
                                f"Could not save calendar properties to project:\n{exc}")


# ------------------------------------------------------------------ #
# Email Server Edit Dialog                                             #
# ------------------------------------------------------------------ #

class EmailServerEditDialog(QDialog):
    """Add or edit a single Email (SMTP) server configuration."""

    def __init__(self, settings_manager, config: dict | None = None, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._config = dict(config) if config else {
            "name": "", "smtp_server": "", "smtp_port": 587,
            "smtp_use_tls": True,
        }
        is_edit = config is not None
        self.setWindowTitle("Edit Email Configuration" if is_edit else "Add Email Configuration")
        self.setMinimumWidth(520)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Email Configuration",
            "Edit SMTP settings" if is_edit else "Add a new email configuration",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 16, 16, 8)
        bv.setSpacing(10)

        # ---- Basic name field ----
        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._name_edit = QLineEdit(self._config.get("name", ""))
        self._name_edit.setPlaceholderText("e.g. Work SMTP")
        self._name_edit.setToolTip(
            "A short label to identify this configuration, e.g. \"Work SMTP\" or \"Office 365\"."
        )
        form.addRow("Name:", self._name_edit)
        bv.addLayout(form)

        # ---- SMTP Settings ----
        bv.addWidget(self._build_smtp_section())

        bv.addStretch()
        root.addWidget(body)

        ok = _btn("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

    # ---- SMTP section ----

    def _build_smtp_section(self) -> QGroupBox:
        grp = QGroupBox("SMTP Settings")
        form = QFormLayout(grp)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        self._smtp_server_edit = QLineEdit(self._config.get("smtp_server", ""))
        self._smtp_server_edit.setPlaceholderText("e.g. mail.example.com")
        self._smtp_server_edit.setToolTip(
            "Hostname or IP address of the outgoing mail (SMTP) server.\n"
            "Examples: smtp.gmail.com, smtp.office365.com, mail.example.com"
        )
        form.addRow("SMTP Server:", self._smtp_server_edit)

        self._smtp_port_edit = QLineEdit(str(self._config.get("smtp_port", 587)))
        self._smtp_port_edit.setValidator(QIntValidator(1, 65535))
        self._smtp_port_edit.setToolTip(
            "TCP port used to connect to the SMTP server.\n"
            "\u2022 587 \u2014 STARTTLS (recommended, most providers)\n"
            "\u2022 465 \u2014 SSL/TLS (implicit TLS)\n"
            "\u2022 25  \u2014 unencrypted relay (avoid in production)"
        )
        form.addRow("SMTP Port:", self._smtp_port_edit)

        self._smtp_use_tls_check = QCheckBox("Use STARTTLS (recommended for port 587)")
        self._smtp_use_tls_check.setChecked(bool(self._config.get("smtp_use_tls", True)))
        self._smtp_use_tls_check.setToolTip(
            "Upgrade the connection to TLS after the initial handshake (STARTTLS).\n"
            "Enable for port 587. Disable only when connecting via implicit SSL on port 465\n"
            "or on servers that do not support STARTTLS."
        )
        form.addRow("Encryption:", self._smtp_use_tls_check)

        return grp

    # ---- Accept ----

    def _build_config_dict(self) -> dict:
        port_text = self._smtp_port_edit.text().strip()
        port = int(port_text) if port_text.isdigit() else 587
        return {
            "name": self._name_edit.text().strip(),
            "smtp_server": self._smtp_server_edit.text().strip(),
            "smtp_port": port,
            "smtp_use_tls": self._smtp_use_tls_check.isChecked(),
        }

    def _accept(self):
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Please enter a configuration name.")
            return
        server = self._smtp_server_edit.text().strip()
        if not server:
            QMessageBox.warning(self, "Validation", "Please enter the SMTP server.")
            return
        self._config = self._build_config_dict()
        self.accept()

    def get_config(self) -> dict:
        """Return the completed configuration dict after the dialog was accepted."""
        return self._config


# ------------------------------------------------------------------ #
# Email Servers Dialog                                                  #
# ------------------------------------------------------------------ #

class EmailServersDialog(QDialog):
    """Manage the full list of Email (SMTP) configurations."""

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._configs: list[dict] = list(self._sm.get_email_configs())
        self._active_name = self._sm.get_active_email_config_name()

        self.setWindowTitle("Email Configurations")
        self.setMinimumWidth(660)
        self.setMinimumHeight(420)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Email Configurations",
            "Manage multiple SMTP configurations",
        ))

        body = QWidget()
        bv = QHBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 8)
        bv.setSpacing(12)

        # Left: config list
        left = QVBoxLayout()
        list_lbl = QLabel("Configured Accounts:")
        list_lbl.setStyleSheet("font-weight: bold; color: #2B579A;")
        left.addWidget(list_lbl)
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self._edit_config)
        left.addWidget(self._list)

        # Active config label
        self._active_lbl = QLabel("")
        self._active_lbl.setStyleSheet("color: #2B579A; font-size: 11px;")
        left.addWidget(self._active_lbl)

        # Right: action buttons
        right = QVBoxLayout()
        right.setSpacing(6)
        right.setAlignment(Qt.AlignTop)
        self._add_btn    = _btn("Add\u2026")
        self._edit_btn   = _btn("Edit\u2026")
        self._del_btn    = _btn("Delete")
        self._active_btn = _btn("Set Active")
        self._up_btn     = _btn("\u25b2", flat=True)
        self._down_btn   = _btn("\u25bc", flat=True)
        self._add_btn.setToolTip("Add a new SMTP configuration")
        self._edit_btn.setToolTip("Edit the selected SMTP configuration")
        self._del_btn.setToolTip("Delete the selected SMTP configuration")
        self._active_btn.setToolTip(
            "Mark the selected configuration as the default account for new projects.\n"
            "The active account is shown with a \u2605 star."
        )
        self._up_btn.setToolTip("Move selected configuration up")
        self._down_btn.setToolTip("Move selected configuration down")
        self._add_btn.clicked.connect(self._add_config)
        self._edit_btn.clicked.connect(self._edit_config)
        self._del_btn.clicked.connect(self._delete_config)
        self._active_btn.clicked.connect(self._set_active)
        self._up_btn.clicked.connect(self._move_up)
        self._down_btn.clicked.connect(self._move_down)
        for b in (self._add_btn, self._edit_btn, self._del_btn,
                  self._active_btn, self._up_btn, self._down_btn):
            right.addWidget(b)

        bv.addLayout(left, stretch=1)
        bv.addLayout(right)
        root.addWidget(body)

        ok = _btn("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

        self._refresh_list()
        self._on_selection_changed()

    # ---- List management ----

    def _refresh_list(self):
        current_row = self._list.currentRow()
        self._list.clear()
        for cfg in self._configs:
            name = cfg.get("name", "(unnamed)")
            server = cfg.get("smtp_server", "")
            marker = " \u2605" if name == self._active_name else ""
            self._list.addItem(f"{name}{marker}  \u2014  {server}")
        if 0 <= current_row < self._list.count():
            self._list.setCurrentRow(current_row)
        if self._active_name:
            self._active_lbl.setText(f"\u2605 Active: {self._active_name}")
        else:
            self._active_lbl.setText("No active configuration selected")

    def _on_selection_changed(self):
        row = self._list.currentRow()
        has = row >= 0
        self._edit_btn.setEnabled(has)
        self._del_btn.setEnabled(has)
        self._active_btn.setEnabled(has)
        self._up_btn.setEnabled(has and row > 0)
        self._down_btn.setEnabled(has and row < len(self._configs) - 1)

    def _add_config(self):
        dlg = EmailServerEditDialog(self._sm, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._configs.append(dlg.get_config())
            self._refresh_list()
            self._list.setCurrentRow(len(self._configs) - 1)
            self._on_selection_changed()

    def _edit_config(self):
        row = self._list.currentRow()
        if row < 0:
            return
        dlg = EmailServerEditDialog(self._sm, config=self._configs[row], parent=self)
        if dlg.exec_() == QDialog.Accepted:
            old_name = self._configs[row].get("name", "")
            self._configs[row] = dlg.get_config()
            new_name = self._configs[row].get("name", "")
            if self._active_name == old_name:
                self._active_name = new_name
            self._refresh_list()
            self._list.setCurrentRow(row)
            self._on_selection_changed()

    def _delete_config(self):
        row = self._list.currentRow()
        if row < 0:
            return
        name = self._configs[row].get("name", "?")
        reply = QMessageBox.question(
            self, "Delete Configuration",
            f"Delete email configuration '{name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self._active_name == name:
            self._active_name = ""
        del self._configs[row]
        self._refresh_list()
        self._on_selection_changed()

    def _set_active(self):
        row = self._list.currentRow()
        if row < 0:
            return
        self._active_name = self._configs[row].get("name", "")
        self._refresh_list()
        self._list.setCurrentRow(row)

    def _move_up(self):
        row = self._list.currentRow()
        if row <= 0:
            return
        self._configs[row - 1], self._configs[row] = self._configs[row], self._configs[row - 1]
        self._refresh_list()
        self._list.setCurrentRow(row - 1)
        self._on_selection_changed()

    def _move_down(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._configs) - 1:
            return
        self._configs[row], self._configs[row + 1] = self._configs[row + 1], self._configs[row]
        self._refresh_list()
        self._list.setCurrentRow(row + 1)
        self._on_selection_changed()

    def _accept(self):
        self._sm.set_email_configs(self._configs)
        self._sm.set_active_email_config_name(self._active_name)
        self.accept()


# ------------------------------------------------------------------ #
# Email Configuration Dialog                                           #
# ------------------------------------------------------------------ #

# Custom property keys for per-project email settings (stored in sidecar JSON)
EMAIL_ACTIVE_ACCOUNT_PROP   = "Email Active Account"
EMAIL_SENDER_NAME_PROP      = "Email Sender Name"
EMAIL_SENDER_ADDRESS_PROP   = "Email Sender Address"


class EmailConfigDialog(QDialog):
    """Configure Email settings for the current project.

    Three sections:
    1. KeePass Credentials — global KeePass entry for SMTP auth (machine-local, QSettings).
    2. Account Selection  — pick which configured SMTP account to use for this project.
    3. Sender Name        — display name in the From header (project-local, sidecar JSON).

    The selected account name and sender name are saved to the project sidecar JSON
    (``<file>.custom-props.json``).  The KeePass entry is saved to QSettings only.
    """

    def __init__(self, settings_manager, project=None, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._project = project

        self.setWindowTitle("Email Configuration")
        self.setMinimumWidth(540)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        # Load available SMTP accounts (used by account section)
        self._configs: list[dict] = list(self._sm.get_email_configs())

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Email Configuration",
            "Select an SMTP account and credentials for this project",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 16, 16, 8)
        bv.setSpacing(12)

        # ---- Section 1: KeePass Credentials ----
        bv.addWidget(self._build_keepass_section())

        # ---- Section 2: Account Selection ----
        bv.addWidget(self._build_account_section())

        # ---- Section 3: Sender Name (project-specific) ----
        bv.addWidget(self._build_sender_name_section())

        bv.addStretch()

        # Wrap in a scroll area
        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root.addWidget(scroll, stretch=1)

        # Bottom buttons: Test Connection, Send Test Email, OK, Cancel
        test_btn = _btn("Test Connection")
        test_btn.setToolTip(
            "Verify SMTP server connectivity and authenticate with the selected KeePass entry\n"
            "without sending an email."
        )
        test_btn.clicked.connect(self._test_connection)
        send_test_btn = _btn("Send Test Email\u2026")
        send_test_btn.setToolTip(
            "Send a test email to a chosen recipient to confirm the full send pipeline works."
        )
        send_test_btn.clicked.connect(self._send_test_email)
        ok = _btn("OK")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True)
        cancel.clicked.connect(self.reject)

        btn_row = QWidget()
        btn_h = QHBoxLayout(btn_row)
        btn_h.setContentsMargins(16, 8, 16, 12)
        btn_h.addWidget(test_btn)
        btn_h.addWidget(send_test_btn)
        btn_h.addStretch()
        btn_h.addWidget(ok)
        btn_h.addWidget(cancel)
        root.addWidget(btn_row)

        # Load project-specific settings (account selection + sender name)
        self._load_project_settings()

    # ---------------------------------------------------------------- #
    # KeePass Credentials section                                       #
    # ---------------------------------------------------------------- #

    def _build_keepass_section(self) -> QGroupBox:
        grp = QGroupBox("KeePass Credentials")
        bv = QVBoxLayout(grp)
        bv.setSpacing(8)

        note = QLabel(
            "Username and password for SMTP authentication are retrieved from the "
            "selected KeePass entry at send-time. No passwords are stored in settings."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555; font-size: 11px; font-style: italic;")
        bv.addWidget(note)

        # Stacked widget: 0 = not configured, 1 = locked, 2 = unlocked
        self._kp_stack = QStackedWidget()

        # Page 0 – KeePass not configured
        p0 = QWidget()
        p0v = QVBoxLayout(p0)
        p0v.setContentsMargins(0, 4, 0, 4)
        p0v.setSpacing(8)
        p0_lbl = QLabel("KeePass is not configured.")
        p0_lbl.setStyleSheet("color: #888; font-size: 12px;")
        cfg_btn = _btn("Configure KeePass\u2026")
        cfg_btn.setToolTip("Open the KeePass Configuration dialog to set the database path and unlock options.")
        cfg_btn.clicked.connect(self._configure_keepass)
        p0v.addWidget(p0_lbl)
        p0v.addWidget(cfg_btn)
        self._kp_stack.addWidget(p0)

        # Page 1 – configured but locked
        p1 = QWidget()
        p1v = QVBoxLayout(p1)
        p1v.setContentsMargins(0, 4, 0, 4)
        p1v.setSpacing(8)
        p1_lbl = QLabel("KeePass database is locked.")
        p1_lbl.setStyleSheet("color: #888; font-size: 12px;")
        unlock_btn = _btn("Unlock KeePass\u2026")
        unlock_btn.setToolTip("Unlock the KeePass database so entries can be read for SMTP authentication.")
        unlock_btn.clicked.connect(self._unlock_keepass)
        p1v.addWidget(p1_lbl)
        p1v.addWidget(unlock_btn)
        self._kp_stack.addWidget(p1)

        # Page 2 – unlocked: entry selector + new entry button
        p2 = QWidget()
        p2f = QFormLayout(p2)
        p2f.setContentsMargins(0, 4, 0, 4)
        p2f.setSpacing(8)
        p2f.setLabelAlignment(Qt.AlignRight)

        entry_row_w = QWidget()
        entry_row_h = QHBoxLayout(entry_row_w)
        entry_row_h.setContentsMargins(0, 0, 0, 0)
        self._kp_entry_combo = QComboBox()
        self._kp_entry_combo.setEditable(True)
        self._kp_entry_combo.setPlaceholderText("Select or type entry title \u2026")
        self._kp_entry_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
        self._kp_entry_combo.setToolTip(
            "KeePass entry whose Username and Password are used for SMTP authentication.\n"
            "The entry must exist in the configured KeePass database."
        )
        entry_row_h.addWidget(self._kp_entry_combo, stretch=1)
        new_entry_btn = _btn("New Entry\u2026", flat=True)
        new_entry_btn.setMinimumWidth(90)
        new_entry_btn.setToolTip("Create a new entry in the KeePass database for these SMTP credentials.")
        new_entry_btn.clicked.connect(self._new_kp_entry)
        entry_row_h.addWidget(new_entry_btn)
        p2f.addRow("Entry:", entry_row_w)

        self._kp_stack.addWidget(p2)
        bv.addWidget(self._kp_stack)

        # Set initial KeePass state
        self._refresh_kp_state()

        return grp

    def _refresh_kp_state(self):
        if not self._sm.is_keepass_configured():
            self._kp_stack.setCurrentIndex(0)
        elif not self._sm.is_keepass_unlocked():
            self._kp_stack.setCurrentIndex(1)
        else:
            self._kp_stack.setCurrentIndex(2)
            self._repopulate_entry_combo()

    def _repopulate_entry_combo(self):
        current = self._sm.get_email_keepass_entry() or ""
        self._kp_entry_combo.blockSignals(True)
        self._kp_entry_combo.clear()
        self._kp_entry_combo.addItem("")  # empty = disabled
        entries = self._sm.list_keepass_entries()
        self._kp_entry_combo.addItems(entries)
        if current:
            idx = self._kp_entry_combo.findText(current)
            if idx >= 0:
                self._kp_entry_combo.setCurrentIndex(idx)
            else:
                self._kp_entry_combo.setCurrentText(current)
        elif entries:
            # Auto-select first entry if no entry is saved yet
            self._kp_entry_combo.setCurrentIndex(1)  # Index 1 = first real entry (0 is empty)
        self._kp_entry_combo.blockSignals(False)

    def _configure_keepass(self):
        dlg = KeePassConfigDialog(self._sm, self)
        dlg.exec_()
        self._refresh_kp_state()

    def _unlock_keepass(self):
        ok, _ = self._sm.auto_unlock_keepass()
        if not ok:
            pwd, entered = QInputDialog.getText(
                self, "KeePass Master Password",
                "Enter KeePass master password:",
                QLineEdit.Password,
            )
            if entered:
                ok, err = self._sm.unlock_keepass(pwd)
                if not ok:
                    QMessageBox.warning(self, "Unlock Failed",
                                        f"Could not open database:\n{err}")
        self._refresh_kp_state()

    def _new_kp_entry(self):
        dlg = KeePassNewEntryDialog(self._sm, self)
        if dlg.exec_() == QDialog.Accepted:
            self._repopulate_entry_combo()
            path = dlg.get_entry_path()
            if path:
                self._kp_entry_combo.setCurrentText(path)

    # ---------------------------------------------------------------- #
    # SMTP Settings section                                             #
    # ---------------------------------------------------------------- #

    # ---------------------------------------------------------------- #
    # Account Selection section                                         #
    # ---------------------------------------------------------------- #

    def _build_account_section(self) -> QGroupBox:
        grp = QGroupBox("Email Account")
        bv = QVBoxLayout(grp)
        bv.setSpacing(8)

        note = QLabel(
            "Select which configured SMTP account to use for this project. "
            "Server, port, TLS, and sender address are managed in "
            "\u201cManage Accounts\u2026\u201d."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #555; font-size: 11px; font-style: italic;")
        bv.addWidget(note)

        row_w = QWidget()
        row_h = QHBoxLayout(row_w)
        row_h.setContentsMargins(0, 0, 0, 0)

        self._account_combo = QComboBox()
        self._account_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
        self._account_combo.setToolTip(
            "SMTP account to use when sending emails for this project.\n"
            "Accounts are shared across projects and managed via \u201cManage Accounts\u2026\u201d."
        )
        row_h.addWidget(self._account_combo, stretch=1)

        manage_btn = _btn("Manage Accounts\u2026", flat=True)
        manage_btn.setMinimumWidth(140)
        manage_btn.setToolTip("Add, edit, or delete SMTP account configurations")
        manage_btn.clicked.connect(self._manage_accounts)
        row_h.addWidget(manage_btn)
        bv.addWidget(row_w)

        self._no_accounts_lbl = QLabel(
            "\u26a0  No email accounts configured. Click \u201cManage Accounts\u2026\u201d to add one."
        )
        self._no_accounts_lbl.setWordWrap(True)
        self._no_accounts_lbl.setStyleSheet("color: #b85900; font-size: 11px;")
        bv.addWidget(self._no_accounts_lbl)

        self._refresh_account_combo()
        return grp

    def _refresh_account_combo(self, select_name: str | None = None):
        """Repopulate the account dropdown from self._configs."""
        self._account_combo.blockSignals(True)
        self._account_combo.clear()
        for cfg in self._configs:
            name   = cfg.get("name", "")
            server = cfg.get("smtp_server", "")
            self._account_combo.addItem(f"{name}  \u2014  {server}", userData=name)
        self._account_combo.blockSignals(False)

        has = bool(self._configs)
        self._account_combo.setVisible(has)
        self._no_accounts_lbl.setVisible(not has)

        if has and select_name:
            for i in range(self._account_combo.count()):
                if self._account_combo.itemData(i) == select_name:
                    self._account_combo.setCurrentIndex(i)
                    break

    def _manage_accounts(self):
        """Open EmailServersDialog; refresh combo when it closes."""
        dlg = EmailServersDialog(self._sm, parent=self)
        dlg.exec_()
        # Reload configs (the dialog may have saved changes)
        self._configs = list(self._sm.get_email_configs())
        current_name = self._account_combo.currentData() if self._account_combo.count() else None
        self._refresh_account_combo(select_name=current_name)

    # ---------------------------------------------------------------- #
    # Sender Name section (per-project)                                 #
    # ---------------------------------------------------------------- #

    def _build_sender_name_section(self) -> QGroupBox:
        grp = QGroupBox("Sender (Per-Project)")
        form = QFormLayout(grp)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignRight)

        # Sender Address row with From KeePass button
        self._sender_address_edit = QLineEdit()
        self._sender_address_edit.setPlaceholderText("user@example.com")
        self._sender_address_edit.setToolTip(
            "Email address that appears in the From field of outgoing emails.\n"
            "Must match the account authenticated via KeePass on most servers.\n"
            "Saved per project \u2014 different projects can send from different addresses."
        )
        addr_row_w = QWidget()
        addr_row_h = QHBoxLayout(addr_row_w)
        addr_row_h.setContentsMargins(0, 0, 0, 0)
        addr_row_h.addWidget(self._sender_address_edit, stretch=1)
        kp_lookup_btn = _btn("From KeePass\u2026", flat=True)
        kp_lookup_btn.setMinimumWidth(110)
        kp_lookup_btn.setToolTip(
            "Look up your email address from Active Directory\n"
            "using the username stored in the global KeePass entry"
        )
        kp_lookup_btn.clicked.connect(self._lookup_sender_from_keepass_ad)
        addr_row_h.addWidget(kp_lookup_btn)
        form.addRow("Sender Address:", addr_row_w)

        self._sender_name_edit = QLineEdit()
        self._sender_name_edit.setPlaceholderText("e.g. Alice Smith  (optional)")
        self._sender_name_edit.setToolTip(
            "Human-readable name shown alongside the sender address in email clients,\n"
            "e.g. \"Alice Smith <alice@example.com>\".  Leave blank to send address only."
        )
        form.addRow("Display Name:", self._sender_name_edit)

        hint_parts = [
            "Sender address and display name are used in the From header.  "
            "Saved per project in the project sidecar file."
        ]
        if self._project is None:
            hint_parts.append("  Open a project to persist these settings.")
        hint = QLabel("".join(hint_parts))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #555; font-size: 11px; font-style: italic;")
        form.addRow("", hint)
        return grp

    # ---------------------------------------------------------------- #
    # Sender address lookup (From KeePass…)                           #
    # ---------------------------------------------------------------- #

    def _lookup_sender_from_keepass_ad(self):
        """Fill Sender Address by looking up the KeePass user's email via LDAP/AD."""
        from app_debug import is_debug as _is_debug  # type: ignore

        # 1. Get the global KeePass entry name from the current dialog selection
        if self._kp_stack.currentIndex() == 2:
            entry_title = self._kp_entry_combo.currentText().strip()
        else:
            entry_title = self._sm.get_email_keepass_entry() if hasattr(self._sm, "get_email_keepass_entry") else ""

        if not entry_title:
            QMessageBox.warning(
                self, "No KeePass Entry Configured",
                "No KeePass entry is selected.\n\n"
                "Please select a KeePass entry in the KeePass Credentials section first.",
            )
            return

        # 2. Get the username from KeePass
        username = ""
        try:
            from integrations import keepass_integration  # type: ignore
            if not keepass_integration.is_unlocked():
                QMessageBox.warning(
                    self, "KeePass Locked",
                    "The KeePass database is locked.\n\n"
                    "Please unlock it in the KeePass Credentials section and try again.",
                )
                return
            username, _ = keepass_integration.get_credentials(entry_title)
        except Exception as exc:
            if _is_debug():
                print(f"[EmailConfigDialog] KeePass lookup error: {exc}")

        if not username:
            QMessageBox.warning(
                self, "Username Not Found",
                f"Could not retrieve a username from KeePass entry:\n{entry_title}\n\n"
                "Ensure the entry contains a valid Username field.",
            )
            return

        if _is_debug():
            print(f"[EmailConfigDialog] Looking up AD email for: {username}")

        # 3. Look up the email address in Active Directory via LDAP
        try:
            from integrations import ad_integration  # type: ignore
            if not ad_integration.is_ad_available():
                QMessageBox.warning(
                    self, "Active Directory Not Available",
                    "Active Directory lookup is not available.\n\n"
                    "Ensure you are on a domain-joined Windows machine with RSAT installed.",
                )
                return

            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                result = ad_integration.lookup_by_username(username)
            finally:
                QApplication.restoreOverrideCursor()

            if result and result.get("email"):
                email = result["email"]
                if _is_debug():
                    print(f"[EmailConfigDialog] Found AD email: {email}")
                self._sender_address_edit.setText(email)
                QMessageBox.information(
                    self, "Email Found",
                    f"Sender address set to:\n{email}\n\n"
                    f"From AD user: {result.get('display_name', username)}",
                )
            else:
                if _is_debug():
                    print(f"[EmailConfigDialog] No AD email found for: {username}")
                QMessageBox.warning(
                    self, "Email Not Found",
                    f"No email address found in Active Directory for:\n{username}\n\n"
                    "The account may not have an email address configured.",
                )
        except Exception as exc:
            if _is_debug():
                print(f"[EmailConfigDialog] AD lookup error: {exc}")
            QMessageBox.warning(
                self, "Lookup Failed",
                f"Failed to look up email address from Active Directory:\n\n{exc}",
            )

    # ---------------------------------------------------------------- #
    # Load / Save project-local settings                                #
    # ---------------------------------------------------------------- #

    def _load_project_settings(self):
        """Read selected account, sender address, and sender name from the project sidecar."""
        active_name = ""
        sender_address = ""
        sender_name = ""
        if self._project is not None:
            try:
                cp = self._project.getProjectProperties().getCustomProperties()
                if cp is not None:
                    v = cp.get(EMAIL_ACTIVE_ACCOUNT_PROP)
                    if v:
                        active_name = str(v)
                    v = cp.get(EMAIL_SENDER_ADDRESS_PROP)
                    if v:
                        sender_address = str(v)
                    v = cp.get(EMAIL_SENDER_NAME_PROP)
                    if v:
                        sender_name = str(v)
            except Exception:
                pass

        # Fall back to global active config when no project-local choice saved
        if not active_name:
            active_name = self._sm.get_active_email_config_name() or ""

        self._refresh_account_combo(select_name=active_name)
        self._sender_address_edit.setText(sender_address)
        self._sender_name_edit.setText(sender_name)

    def _save_settings(self):
        """Persist email settings: KeePass entry → QSettings; account/name → sidecar."""
        from app_debug import is_debug as _is_debug  # type: ignore

        # KeePass entry (global, machine-local QSettings)
        if self._kp_stack.currentIndex() == 2:
            entry = self._kp_entry_combo.currentText().strip()
            self._sm.set_email_keepass_entry(entry)
            if _is_debug():
                print(f"[EmailConfigDialog] Saved KeePass entry: '{entry}'")

        # Selected account name, sender address, and sender name → project sidecar JSON
        selected_name = ""
        if self._account_combo.isVisible() and self._account_combo.count() > 0:
            selected_name = self._account_combo.currentData() or ""
        sender_address = self._sender_address_edit.text().strip()
        sender_name = self._sender_name_edit.text().strip()

        if _is_debug():
            print(f"[EmailConfigDialog] _save_settings(): "
                  f"account='{selected_name}', sender_address='{sender_address}', "
                  f"sender_name='{sender_name}'")

        if self._project is not None:
            try:
                import java.util  # type: ignore
                props  = self._project.getProjectProperties()
                cp     = props.getCustomProperties()
                new_cp = java.util.HashMap()
                # Preserve all existing properties
                if cp is not None:
                    for key in cp.keySet():
                        new_cp.put(key, cp.get(key))
                # Update or remove email keys
                if selected_name:
                    new_cp.put(EMAIL_ACTIVE_ACCOUNT_PROP, selected_name)
                else:
                    new_cp.remove(EMAIL_ACTIVE_ACCOUNT_PROP)
                if sender_address:
                    new_cp.put(EMAIL_SENDER_ADDRESS_PROP, sender_address)
                else:
                    new_cp.remove(EMAIL_SENDER_ADDRESS_PROP)
                if sender_name:
                    new_cp.put(EMAIL_SENDER_NAME_PROP, sender_name)
                else:
                    new_cp.remove(EMAIL_SENDER_NAME_PROP)
                props.setCustomProperties(new_cp)
            except Exception as exc:
                if _is_debug():
                    print(f"[EmailConfigDialog] Could not save to project sidecar: {exc}")

    # ---------------------------------------------------------------- #
    # Build transient config dict for test / send                       #
    # ---------------------------------------------------------------- #

    def _get_current_config(self) -> dict | None:
        """Return a config dict for the currently-selected account.

        Injects ``sender_name`` from the Sender Name field when set.
        Returns None when no accounts are configured.
        """
        if not self._configs or self._account_combo.isHidden() \
                or self._account_combo.count() == 0:
            return None
        selected_name = self._account_combo.currentData()
        cfg = next(
            (c for c in self._configs if c.get("name") == selected_name),
            self._configs[0],
        )
        result = dict(cfg)
        sender_address = self._sender_address_edit.text().strip()
        if sender_address:
            result["sender_address"] = sender_address
        sender_name = self._sender_name_edit.text().strip()
        if sender_name:
            result["sender_name"] = sender_name
        return result

    # ---------------------------------------------------------------- #
    # Test Connection                                                   #
    # ---------------------------------------------------------------- #

    def _test_connection(self):
        """Test SMTP connection and authentication without sending an email."""
        from integrations import email_integration  # type: ignore
        from app_debug import is_debug as _is_debug  # type: ignore

        config = self._get_current_config()

        if _is_debug():
            print("[EmailConfigDialog] Test Connection clicked")
            print(f"  config: {config}")
            print(f"  KeePass stack index: {self._kp_stack.currentIndex()}")

        missing = []
        if config is None:
            missing.append("Email Account (no accounts configured \u2014 add one first)")
        if self._kp_stack.currentIndex() != 2:
            missing.append("KeePass (not unlocked)")
        elif not self._kp_entry_combo.currentText().strip():
            missing.append("KeePass Entry (not selected)")

        if missing:
            QMessageBox.warning(
                self, "Configuration Incomplete",
                "The following are required:\n\n" +
                "\n".join(f"\u2022 {m}" for m in missing) +
                "\n\nPlease complete all required fields before testing."
            )
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            success, error = email_integration.test_connection(config=config)
            if _is_debug():
                print(f"[EmailConfigDialog] test_connection() -> success={success}, error='{error}'")
        finally:
            QApplication.restoreOverrideCursor()

        if success:
            QMessageBox.information(
                self, "Connection Successful",
                "SMTP connection and authentication succeeded.\n\n"
                "The email integration is configured correctly."
            )
        else:
            QMessageBox.warning(
                self, "Connection Failed",
                f"SMTP connection test failed:\n\n{error}\n\n"
                "Please verify your settings and ensure the SMTP server is reachable."
            )

    # ---------------------------------------------------------------- #
    # Send Test Email                                                   #
    # ---------------------------------------------------------------- #

    def _send_test_email(self):
        """Send a test email to a recipient address."""
        from integrations import email_integration  # type: ignore
        from app_debug import is_debug as _is_debug  # type: ignore

        config = self._get_current_config()

        if _is_debug():
            print("[EmailConfigDialog] Send Test Email clicked")
            print(f"  config: {config}")

        missing = []
        if config is None:
            missing.append("Email Account (no accounts configured \u2014 add one first)")
        if self._kp_stack.currentIndex() != 2:
            missing.append("KeePass (not unlocked)")
        elif not self._kp_entry_combo.currentText().strip():
            missing.append("KeePass Entry (not selected)")

        if missing:
            QMessageBox.warning(
                self, "Configuration Incomplete",
                "The following are required:\n\n" +
                "\n".join(f"\u2022 {m}" for m in missing) +
                "\n\nPlease complete all required fields before sending."
            )
            return

        # Prompt for recipient
        dlg = QDialog(self)
        dlg.setWindowTitle("Send Test Email")
        dlg.setModal(True)
        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(16, 16, 16, 16)
        dlg_layout.setSpacing(12)
        dlg_layout.addWidget(QLabel("Enter recipient email address:"))

        recipient_row = QWidget()
        recipient_row_h = QHBoxLayout(recipient_row)
        recipient_row_h.setContentsMargins(0, 0, 0, 0)

        recipient_edit = QLineEdit()
        recipient_edit.setPlaceholderText("user@example.com")
        recipient_edit.setMinimumWidth(350)
        recipient_row_h.addWidget(recipient_edit, stretch=1)

        use_my_email_btn = _btn("Use My Email", flat=True)
        use_my_email_btn.setMinimumWidth(110)
        use_my_email_btn.setToolTip("Look up your email address from Active Directory")

        def _fill_my_email():
            import os
            try:
                uname = os.getlogin()
            except Exception:
                uname = os.environ.get("USERNAME", "")
            if not uname:
                QMessageBox.warning(dlg, "Username Not Found",
                                    "Could not determine your Windows username.")
                return
            if _is_debug():
                print(f"[EmailConfigDialog] Looking up AD email for current user: {uname}")
            try:
                from integrations import ad_integration  # type: ignore
                if not ad_integration.is_ad_available():
                    QMessageBox.warning(
                        dlg, "Active Directory Not Available",
                        "Active Directory lookup is not available.\n\n"
                        "Ensure you are on a domain-joined machine with RSAT installed."
                    )
                    return
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    result = ad_integration.lookup_by_username(uname)
                finally:
                    QApplication.restoreOverrideCursor()
                if result and result.get("email"):
                    recipient_edit.setText(result["email"])
                    if _is_debug():
                        print(f"[EmailConfigDialog] Found AD email: {result['email']}")
                else:
                    if _is_debug():
                        print(f"[EmailConfigDialog] No AD email found for: {uname}")
                    QMessageBox.warning(dlg, "Email Not Found",
                                        f"No email found in Active Directory for:\n{uname}")
            except Exception as exc:
                if _is_debug():
                    print(f"[EmailConfigDialog] AD lookup error: {exc}")
                QMessageBox.warning(dlg, "Lookup Failed",
                                    f"Failed to look up email address:\n\n{exc}")

        use_my_email_btn.clicked.connect(_fill_my_email)
        recipient_row_h.addWidget(use_my_email_btn)
        dlg_layout.addWidget(recipient_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        dlg_layout.addWidget(btn_box)

        if dlg.exec_() != QDialog.Accepted:
            return

        recipient = recipient_edit.text().strip()
        if not recipient:
            return

        if _is_debug():
            print(f"[EmailConfigDialog] Sending test email to: {recipient}")

        sender_addr = config.get("sender_address", "") if config else ""
        server_addr = config.get("smtp_server", "") if config else ""
        subject = "Email Configuration Test"
        body = (
            "This is a test email from Project Offline Email Integration.\n\n"
            f"SMTP Server: {server_addr}\n"
            f"Sender Address: {sender_addr}\n\n"
            "If you received this email, your email configuration is working correctly."
        )

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            success, error = email_integration.send_email(
                to=recipient, subject=subject, body=body, config=config
            )
            if _is_debug():
                print(f"[EmailConfigDialog] send_email() -> success={success}, error='{error}'")
        finally:
            QApplication.restoreOverrideCursor()

        if success:
            QMessageBox.information(
                self, "Email Sent",
                f"Test email sent successfully to:\n{recipient}\n\n"
                "Please check the recipient's inbox to verify delivery."
            )
        else:
            QMessageBox.warning(
                self, "Send Failed",
                f"Failed to send test email:\n\n{error}\n\n"
                "Please verify your settings and ensure the SMTP server allows relay."
            )

    # ---------------------------------------------------------------- #
    # Accept                                                            #
    # ---------------------------------------------------------------- #

    def _accept(self):
        self._save_settings()
        self.accept()


# ==========================================================================
# VCS Configuration Dialogs
# ==========================================================================

class VcsConfigDialog(QDialog):
    """Version Control Integration configuration dialog.

    Allows the user to:
      - Select a KeePass entry for VCS credentials (Git / SVN).
      - Configure auto-commit settings (enabled, message template, scope).
      - Optionally override paths to git.exe / svn.exe.

    The dialog is always accessible from the VERSION CONTROL ribbon tab.
    """

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self.setWindowTitle("Version Control Configuration")
        self.setMinimumWidth(520)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Version Control",
            "Configure Git / SVN credentials and auto-commit settings",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 16, 16, 8)
        bv.setSpacing(10)

        # ---- KeePass credentials group ----
        kp_grp = QGroupBox("Credentials (KeePass)")
        kp_vbox = QVBoxLayout(kp_grp)
        kp_vbox.setSpacing(6)

        self._kp_stack = QStackedWidget()

        # Page 0 – KeePass not configured
        p0 = QWidget(); p0v = QVBoxLayout(p0); p0v.setContentsMargins(0, 4, 0, 4)
        p0_lbl = QLabel("KeePass is not configured.")
        p0_lbl.setStyleSheet("color: #888; font-size: 12px;")
        cfg_btn = _btn("Configure KeePass\u2026")
        cfg_btn.clicked.connect(self._configure_keepass)
        p0v.addWidget(p0_lbl); p0v.addWidget(cfg_btn)
        self._kp_stack.addWidget(p0)

        # Page 1 – configured but locked
        p1 = QWidget(); p1v = QVBoxLayout(p1); p1v.setContentsMargins(0, 4, 0, 4)
        p1_lbl = QLabel("KeePass database is locked.")
        p1_lbl.setStyleSheet("color: #888; font-size: 12px;")
        unlock_btn = _btn("Unlock KeePass\u2026")
        unlock_btn.clicked.connect(self._unlock_keepass)
        p1v.addWidget(p1_lbl); p1v.addWidget(unlock_btn)
        self._kp_stack.addWidget(p1)

        # Page 2 – unlocked: entry selector
        p2 = QWidget(); p2f = QFormLayout(p2); p2f.setContentsMargins(0, 4, 0, 4)
        p2f.setSpacing(8); p2f.setLabelAlignment(Qt.AlignRight)
        entry_row_w = QWidget(); entry_row_h = QHBoxLayout(entry_row_w)
        entry_row_h.setContentsMargins(0, 0, 0, 0)
        self._kp_entry_combo = QComboBox()
        self._kp_entry_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)
        entry_row_h.addWidget(self._kp_entry_combo, stretch=1)
        new_entry_btn = _btn("New Entry\u2026", flat=True)
        new_entry_btn.setMinimumWidth(90)
        new_entry_btn.clicked.connect(self._new_kp_entry)
        entry_row_h.addWidget(new_entry_btn)
        p2f.addRow("KeePass Entry:", entry_row_w)
        self._kp_stack.addWidget(p2)

        kp_vbox.addWidget(self._kp_stack)
        kp_vbox.addWidget(QLabel(
            "Used for both Git (GIT_ASKPASS) and SVN (--username / --password).",
        ))
        bv.addWidget(kp_grp)

        # ---- Auto-commit settings ----
        ac_grp = QGroupBox("Auto-commit on Save")
        ac_form = QFormLayout(ac_grp)
        ac_form.setSpacing(8); ac_form.setLabelAlignment(Qt.AlignRight)

        self._auto_commit_chk = QCheckBox("Enable auto-commit after each save")
        self._auto_commit_chk.setChecked(self._sm.get_vcs_auto_commit_enabled())
        self._auto_commit_chk.toggled.connect(self._on_auto_commit_toggled)
        ac_form.addRow("", self._auto_commit_chk)

        self._template_edit = QLineEdit(self._sm.get_vcs_auto_commit_template())
        self._template_edit.setPlaceholderText(
            "Auto-commit: {project_name} saved at {timestamp}"
        )
        self._template_edit.setToolTip(
            "Placeholders: {project_name}, {timestamp}\n"
            "Example: Auto-commit: {project_name} saved at {timestamp}"
        )
        ac_form.addRow("Message Template:", self._template_edit)

        self._scope_combo = QComboBox()
        self._scope_combo.addItem("Project file only", "project")
        self._scope_combo.addItem("All tracked changes", "all")
        current_scope = self._sm.get_vcs_auto_commit_scope()
        self._scope_combo.setCurrentIndex(
            1 if current_scope == "all" else 0
        )
        ac_form.addRow("Commit Scope:", self._scope_combo)
        bv.addWidget(ac_grp)

        # ---- Executable paths (optional) ----
        paths_grp = QGroupBox("Executable Paths (optional — leave blank to auto-detect)")
        paths_form = QFormLayout(paths_grp)
        paths_form.setSpacing(8); paths_form.setLabelAlignment(Qt.AlignRight)

        self._git_path_edit = QLineEdit(self._sm.get_vcs_git_path())
        self._git_path_edit.setPlaceholderText("auto-detect from tools/git/")
        git_browse_btn = _btn("Browse\u2026", flat=True)
        git_browse_btn.clicked.connect(self._browse_git)
        git_row = QWidget(); git_row_h = QHBoxLayout(git_row)
        git_row_h.setContentsMargins(0, 0, 0, 0)
        git_row_h.addWidget(self._git_path_edit, stretch=1)
        git_row_h.addWidget(git_browse_btn)
        paths_form.addRow("git.exe:", git_row)

        self._svn_path_edit = QLineEdit(self._sm.get_vcs_svn_path())
        self._svn_path_edit.setPlaceholderText("auto-detect from tools/svn/")
        svn_browse_btn = _btn("Browse\u2026", flat=True)
        svn_browse_btn.clicked.connect(self._browse_svn)
        svn_row = QWidget(); svn_row_h = QHBoxLayout(svn_row)
        svn_row_h.setContentsMargins(0, 0, 0, 0)
        svn_row_h.addWidget(self._svn_path_edit, stretch=1)
        svn_row_h.addWidget(svn_browse_btn)
        paths_form.addRow("svn.exe:", svn_row)
        bv.addWidget(paths_grp)

        bv.addStretch()
        root.addWidget(body)

        ok = _btn("OK"); ok.setDefault(True); ok.clicked.connect(self._accept)
        cancel = _btn("Cancel", flat=True); cancel.clicked.connect(self.reject)
        root.addWidget(_button_row(ok, cancel))

        # Initial state
        self._on_auto_commit_toggled(self._auto_commit_chk.isChecked())
        self._refresh_kp_state()

    # ---- KeePass state ----

    def _refresh_kp_state(self):
        if not self._sm.is_keepass_configured():
            self._kp_stack.setCurrentIndex(0)
        elif not self._sm.is_keepass_unlocked():
            self._kp_stack.setCurrentIndex(1)
        else:
            self._kp_stack.setCurrentIndex(2)
            self._repopulate_entry_combo()

    def _repopulate_entry_combo(self):
        current = self._sm.get_vcs_keepass_entry()
        self._kp_entry_combo.blockSignals(True)
        self._kp_entry_combo.clear()
        entries = self._sm.list_keepass_entries()
        self._kp_entry_combo.addItems(entries)
        if current in entries:
            self._kp_entry_combo.setCurrentText(current)
        elif entries:
            self._kp_entry_combo.setCurrentIndex(0)
        self._kp_entry_combo.blockSignals(False)

    def _configure_keepass(self):
        dlg = KeePassConfigDialog(self._sm, self)
        dlg.exec_()
        self._refresh_kp_state()

    def _unlock_keepass(self):
        ok, _ = self._sm.auto_unlock_keepass()
        if not ok:
            pwd, entered = QInputDialog.getText(
                self, "KeePass Master Password",
                "Enter KeePass master password:", QLineEdit.Password,
            )
            if entered:
                ok, err = self._sm.unlock_keepass(pwd)
                if not ok:
                    QMessageBox.warning(self, "Unlock Failed",
                                        f"Could not open database:\n{err}")
        self._refresh_kp_state()

    def _new_kp_entry(self):
        dlg = KeePassNewEntryDialog(self._sm, self)
        if dlg.exec_() == QDialog.Accepted:
            self._repopulate_entry_combo()
            path = dlg.get_entry_path()
            if path:
                self._kp_entry_combo.setCurrentText(path)

    # ---- Browse ----

    def _browse_git(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select git.exe", "", "Executables (*.exe);;All Files (*)"
        )
        if path:
            self._git_path_edit.setText(path)

    def _browse_svn(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select svn.exe", "", "Executables (*.exe);;All Files (*)"
        )
        if path:
            self._svn_path_edit.setText(path)

    # ---- Auto-commit toggling ----

    def _on_auto_commit_toggled(self, checked: bool):
        self._template_edit.setEnabled(checked)
        self._scope_combo.setEnabled(checked)

    # ---- Accept ----

    def _accept(self):
        # Save KeePass entry
        if self._kp_stack.currentIndex() == 2:
            self._sm.set_vcs_keepass_entry(self._kp_entry_combo.currentText())

        # Save auto-commit settings
        self._sm.set_vcs_auto_commit_enabled(self._auto_commit_chk.isChecked())
        self._sm.set_vcs_auto_commit_template(self._template_edit.text().strip())
        self._sm.set_vcs_auto_commit_scope(self._scope_combo.currentData())

        # Save executable paths
        self._sm.set_vcs_git_path(self._git_path_edit.text().strip())
        self._sm.set_vcs_svn_path(self._svn_path_edit.text().strip())

        self.accept()


class VcsLogDialog(QDialog):
    """Show the commit history for the current repository."""

    def __init__(self, log_entries: list[dict], vcs_type: str = "git",
                 repo_root: str = "", parent=None):
        super().__init__(parent)
        self._entries = log_entries
        self._vcs_type = vcs_type
        self._repo_root = repo_root
        self.setWindowTitle("Version Control Log")
        self.setMinimumSize(700, 480)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Version Control Log",
            f"{'Git' if vcs_type == 'git' else 'SVN'} commit history for: {repo_root or '(unknown)'}",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 8)
        bv.setSpacing(8)

        # Log list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        for entry in log_entries:
            short = entry.get("short", "")
            date = entry.get("date", "")[:10]
            author = entry.get("author", "")
            subject = entry.get("subject", "")
            self._list.addItem(f"{short}  {date}  {author}  —  {subject}")
        bv.addWidget(self._list)

        # Diff area
        diff_grp = QGroupBox("Diff (selected revision vs. working copy)")
        diff_vbox = QVBoxLayout(diff_grp)
        from PyQt5.QtWidgets import QTextEdit  # type: ignore
        self._diff_text = QTextEdit()
        self._diff_text.setReadOnly(True)
        self._diff_text.setFont(_monospace_font())
        self._diff_text.setMinimumHeight(150)
        diff_vbox.addWidget(self._diff_text)
        bv.addWidget(diff_grp)

        self._list.currentRowChanged.connect(self._on_row_changed)
        bv.addStretch()
        root.addWidget(body)

        # Buttons
        restore_btn = _btn("Restore This Revision\u2026")
        restore_btn.clicked.connect(self._restore)
        close_btn = _btn("Close", flat=True)
        close_btn.clicked.connect(self.accept)
        row_w = _button_row(restore_btn, close_btn)
        root.addWidget(row_w)

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._entries):
            entry = self._entries[row]
            rev = entry.get("hash", entry.get("short", ""))
            from integrations import version_control_integration as vcs  # type: ignore
            ok, diff = vcs.diff_revision(rev)
            self._diff_text.setPlainText(diff if ok else "(No diff available)")

    def _restore(self):
        row = self._list.currentRow()
        if row < 0 or row >= len(self._entries):
            QMessageBox.information(self, "Restore", "Please select a revision first.")
            return
        entry = self._entries[row]
        rev = entry.get("hash", entry.get("short", ""))
        subject = entry.get("subject", rev)[:60]
        reply = QMessageBox.question(
            self, "Restore Revision",
            f"Restore to revision:\n{rev} — {subject}\n\n"
            "A safety snapshot of the current file will be created first.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        from integrations import version_control_integration as vcs  # type: ignore
        ok, msg = vcs.restore_revision(rev, file_only=True)
        if ok:
            QMessageBox.information(self, "Restore", f"Restored to {rev}.\n\n{msg}")
            self.accept()
        else:
            QMessageBox.critical(self, "Restore Failed", msg)


def _monospace_font():
    from PyQt5.QtGui import QFont  # type: ignore
    f = QFont("Consolas", 9)
    f.setFixedPitch(True)
    return f


class VcsBranchDialog(QDialog):
    """Git branch management: list, create, and switch branches."""

    def __init__(self, current_branch: str, parent=None):
        super().__init__(parent)
        self._current_branch = current_branch
        self.setWindowTitle("Branch Management")
        self.setMinimumSize(480, 360)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header("Branch Management",
                                    f"Current branch: {current_branch or '(detached HEAD)'}"))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 8)
        bv.setSpacing(8)

        self._branch_list = QListWidget()
        self._branch_list.setAlternatingRowColors(True)
        bv.addWidget(self._branch_list)
        self._refresh_branches()

        # New branch row
        new_row = QWidget()
        new_row_h = QHBoxLayout(new_row)
        new_row_h.setContentsMargins(0, 0, 0, 0)
        self._new_branch_edit = QLineEdit()
        self._new_branch_edit.setPlaceholderText("new-branch-name")
        new_row_h.addWidget(self._new_branch_edit, stretch=1)
        create_btn = _btn("Create", flat=True)
        create_btn.clicked.connect(self._create_branch)
        new_row_h.addWidget(create_btn)
        bv.addWidget(new_row)

        bv.addStretch()
        root.addWidget(body)

        switch_btn = _btn("Switch to Selected")
        switch_btn.clicked.connect(self._switch_branch)
        close_btn = _btn("Close", flat=True)
        close_btn.clicked.connect(self.accept)
        root.addWidget(_button_row(switch_btn, close_btn))

    def _refresh_branches(self):
        from integrations import version_control_integration as vcs  # type: ignore
        ok, branches = vcs.branch_list()
        self._branch_list.clear()
        if ok:
            for b in branches:
                self._branch_list.addItem(b)
        # Pre-select current branch
        for i in range(self._branch_list.count()):
            if self._branch_list.item(i).text() == self._current_branch:
                self._branch_list.setCurrentRow(i)
                break

    def _create_branch(self):
        name = self._new_branch_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Create Branch", "Please enter a branch name.")
            return
        from integrations import version_control_integration as vcs  # type: ignore
        ok, msg = vcs.branch_create(name)
        if ok:
            self._new_branch_edit.clear()
            self._refresh_branches()
        else:
            QMessageBox.critical(self, "Create Branch Failed", msg)

    def _switch_branch(self):
        item = self._branch_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Switch Branch", "Please select a branch.")
            return
        name = item.text()
        if name == self._current_branch:
            QMessageBox.information(self, "Switch Branch",
                                    f"Already on branch '{name}'.")
            return
        from integrations import version_control_integration as vcs  # type: ignore
        ok, msg = vcs.branch_switch(name)
        if ok:
            self._current_branch = name
            QMessageBox.information(self, "Branch Switched",
                                    f"Switched to branch '{name}'.")
            self.accept()
        else:
            QMessageBox.critical(self, "Switch Failed", msg)


class VcsConflictDialog(QDialog):
    """Show conflicting files after a pull/update and offer resolution actions."""

    def __init__(self, conflicts: list[str], output: str = "", parent=None):
        super().__init__(parent)
        self._conflicts = conflicts
        self.setWindowTitle("Version Control Conflicts")
        self.setMinimumSize(560, 400)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Conflicts Detected",
            "The following files have conflicts that need to be resolved.",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 8)
        bv.setSpacing(8)

        if conflicts:
            conflict_list = QListWidget()
            conflict_list.setSelectionMode(QAbstractItemView.MultiSelection)
            for path in conflicts:
                conflict_list.addItem(path)
            conflict_list.selectAll()
            self._conflict_list = conflict_list
            bv.addWidget(QLabel(f"{len(conflicts)} conflicting file(s):"))
            bv.addWidget(conflict_list)

            revert_btn = _btn("Revert Selected Files\u2026")
            revert_btn.clicked.connect(self._revert_selected)
            bv.addWidget(revert_btn)
        else:
            self._conflict_list = None
            bv.addWidget(QLabel("No conflicts found."))

        if output:
            out_grp = QGroupBox("Command Output")
            out_vbox = QVBoxLayout(out_grp)
            from PyQt5.QtWidgets import QTextEdit  # type: ignore
            out_text = QTextEdit()
            out_text.setReadOnly(True)
            out_text.setFont(_monospace_font())
            out_text.setMaximumHeight(120)
            out_text.setPlainText(output[:4000])
            out_vbox.addWidget(out_text)
            bv.addWidget(out_grp)

        bv.addStretch()
        root.addWidget(body)

        close_btn = _btn("Close")
        close_btn.clicked.connect(self.accept)
        root.addWidget(_button_row(close_btn))

    def _revert_selected(self):
        if self._conflict_list is None:
            return
        paths = [item.text() for item in self._conflict_list.selectedItems()]
        if not paths:
            QMessageBox.information(self, "Revert", "No files selected.")
            return
        reply = QMessageBox.question(
            self, "Revert Files",
            f"Revert {len(paths)} file(s) to the last committed state?\n"
            "All local changes in those files will be lost.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        from integrations import version_control_integration as vcs  # type: ignore
        ok, msg = vcs.svn_revert(paths) if vcs.get_vcs_type() == "svn" else (False, "Git revert not supported here.")
        if vcs.get_vcs_type() == "git":
            # For git, use checkout to discard local changes
            from integrations.version_control_integration import _run_git, get_repo_root  # type: ignore
            root = get_repo_root()
            rc, out, err = _run_git(["checkout", "--", "--"] + paths, cwd=root, timeout=15)
            ok = rc == 0
            msg = (out + err).strip()
        if ok:
            QMessageBox.information(self, "Revert Done", "Files reverted successfully.")
            self.accept()
        else:
            QMessageBox.critical(self, "Revert Failed", msg)


# ==========================================================================
# CPM Settings Dialog
# ==========================================================================

class CPMSettingsDialog(QDialog):
    """Configure Critical Path Method engine settings.

    calc settings  → saved to per-project sidecar JSON via MainWindow
    display prefs  → saved to QSettings via SettingsManager
    """

    def __init__(self, cpm_cfg: dict, settings_manager, parent=None):
        super().__init__(parent)
        self._sm = settings_manager
        self._cpm_cfg = dict(cpm_cfg)
        self.setWindowTitle("Critical Path Settings")
        self.setMinimumWidth(400)
        self.setStyleSheet(_DIALOG_STYLE + _BUTTON_STYLE)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # --- Calculation settings (per-project) ----------------------------
        calc_grp = QGroupBox("Calculation Settings (saved per project)")
        form = QFormLayout(calc_grp)
        form.setSpacing(8)

        # Critical slack threshold
        from PyQt5.QtWidgets import QSpinBox  # type: ignore
        self._slack_spin = QSpinBox()
        self._slack_spin.setRange(0, 30)
        self._slack_spin.setSuffix(" day(s)")
        self._slack_spin.setToolTip(
            "Tasks with Total Float ≤ this value are highlighted as critical.\n"
            "MS Project default is 0."
        )
        self._slack_spin.setValue(int(self._cpm_cfg.get("critical_slack_days", 0)))
        form.addRow("Critical slack threshold:", self._slack_spin)

        # Dependency types
        self._dep_all   = QRadioButton("All dependency types (FS, SS, FF, SF)")
        self._dep_fs    = QRadioButton("Finish-to-Start only (FS)")
        self._dep_group = QButtonGroup(self)
        self._dep_group.addButton(self._dep_all, 0)
        self._dep_group.addButton(self._dep_fs,  1)
        dep_mode = self._cpm_cfg.get("dep_types", "all")
        if dep_mode == "fs_only":
            self._dep_fs.setChecked(True)
        else:
            self._dep_all.setChecked(True)
        dep_box = QVBoxLayout()
        dep_box.addWidget(self._dep_all)
        dep_box.addWidget(self._dep_fs)
        dep_widget = QWidget()
        dep_widget.setLayout(dep_box)
        form.addRow("Dependency types:", dep_widget)

        root.addWidget(calc_grp)

        # --- Display preferences (global, via QSettings) -------------------
        disp_grp = QGroupBox("Display Preferences (global)")
        disp_form = QFormLayout(disp_grp)
        disp_form.setSpacing(8)

        self._chk_float_bar = QCheckBox("Show total-float overlay bar on Gantt")
        self._chk_float_bar.setChecked(self._sm.get_show_float_bar())
        disp_form.addRow(self._chk_float_bar)

        self._chk_ff_col = QCheckBox("Show Free Float column in Task Sheet")
        self._chk_ff_col.setChecked(self._sm.get_show_free_float_column())
        disp_form.addRow(self._chk_ff_col)

        self._chk_results = QCheckBox("Show CPM Results panel")
        self._chk_results.setChecked(self._sm.get_show_cpm_results_panel())
        disp_form.addRow(self._chk_results)

        root.addWidget(disp_grp)

        # --- Restore defaults -----------------------------------------------
        restore_btn = _btn("Restore MS Project Defaults")
        restore_btn.clicked.connect(self._restore_defaults)
        root.addWidget(restore_btn, alignment=Qt.AlignLeft)

        # --- Button row ----------------------------------------------------
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_ok)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    def _restore_defaults(self):
        self._slack_spin.setValue(0)
        self._dep_all.setChecked(True)
        self._chk_float_bar.setChecked(False)
        self._chk_ff_col.setChecked(False)
        self._chk_results.setChecked(False)

    def _on_ok(self):
        self._cpm_cfg["critical_slack_days"] = self._slack_spin.value()
        self._cpm_cfg["dep_types"] = "fs_only" if self._dep_fs.isChecked() else "all"
        # Save display prefs immediately to QSettings
        self._sm.set_show_float_bar(self._chk_float_bar.isChecked())
        self._sm.set_show_free_float_column(self._chk_ff_col.isChecked())
        self._sm.set_show_cpm_results_panel(self._chk_results.isChecked())
        self.accept()

    def get_cpm_cfg(self) -> dict:
        """Return the (possibly updated) CPM config dict."""
        return dict(self._cpm_cfg)

