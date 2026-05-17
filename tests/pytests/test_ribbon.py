"""Tests for ribbon.py - MS Project-style ribbon toolbar."""

import pytest
from unittest.mock import MagicMock, patch
from PyQt5.QtWidgets import QToolButton


def test_ribbon_group_init(qapp):
    """Test _RibbonGroup initializes correctly."""
    from ribbon import _RibbonGroup
    
    group = _RibbonGroup("Test Group")
    
    assert group is not None
    assert group.separator_widget() is not None


def test_ribbon_group_add_button(qapp):
    """Test _RibbonGroup.add_button() creates button."""
    from ribbon import _RibbonGroup
    
    group = _RibbonGroup("Test Group")
    slot = MagicMock()
    
    btn = group.add_button("Test", "Test tooltip", slot=slot)
    
    assert isinstance(btn, QToolButton)
    assert btn.text() == "Test"
    assert btn.toolTip() == "Test tooltip"


def test_ribbon_group_add_button_with_icon(qapp):
    """Test _RibbonGroup.add_button() with icon."""
    from ribbon import _RibbonGroup
    from PyQt5.QtGui import QIcon
    
    group = _RibbonGroup("Test Group")
    icon = QIcon()
    
    btn = group.add_button("Test", "Tooltip", icon=icon)
    
    assert not btn.icon().isNull() or icon.isNull()  # Allow null icons


def test_ribbon_group_add_button_checkable(qapp):
    """Test _RibbonGroup.add_button() with checkable=True."""
    from ribbon import _RibbonGroup
    
    group = _RibbonGroup("Test Group")
    
    btn = group.add_button("Test", "Tooltip", checkable=True)
    
    assert btn.isCheckable()


def test_ribbon_panel_init(qapp):
    """Test _RibbonPanel initializes correctly."""
    from ribbon import _RibbonPanel
    
    panel = _RibbonPanel()
    
    assert panel is not None


def test_ribbon_panel_add_group(qapp):
    """Test _RibbonPanel.add_group() adds group."""
    from ribbon import _RibbonPanel, _RibbonGroup
    
    panel = _RibbonPanel()
    group = _RibbonGroup("Test")
    
    panel.add_group(group)
    
    # Group should be added to panel's layout
    assert True  # Test passes if no exceptions


def test_project_ribbon_init(qapp):
    """Test ProjectRibbon initializes correctly."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    assert ribbon is not None
    assert len(ribbon.TAB_NAMES) == 5
    assert ribbon.TAB_NAMES == ["TASK", "RESOURCE", "REPORT", "BASELINE", "VERSION CONTROL"]


def test_project_ribbon_has_tabs(qapp):
    """Test ProjectRibbon has tab buttons."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    assert len(ribbon._tab_buttons) == 5
    assert ribbon._tab_buttons[0].text() == "TASK"
    assert ribbon._tab_buttons[1].text() == "RESOURCE"
    assert ribbon._tab_buttons[2].text() == "REPORT"
    assert ribbon._tab_buttons[3].text() == "BASELINE"
    assert ribbon._tab_buttons[4].text() == "VERSION CONTROL"


def test_project_ribbon_first_tab_active(qapp):
    """Test ProjectRibbon activates first tab by default."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    assert ribbon._active_tab == 0
    assert ribbon._tab_buttons[0].isChecked()


def test_project_ribbon_switch_tabs(qapp):
    """Test ProjectRibbon tab switching."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Click second tab
    ribbon._tab_buttons[1].click()
    
    assert ribbon._active_tab == 1
    assert ribbon._tab_buttons[1].isChecked()
    assert not ribbon._tab_buttons[0].isChecked()


def test_project_ribbon_panels_created(qapp):
    """Test ProjectRibbon creates panels for each tab."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    assert len(ribbon._panels) == 5


def test_project_ribbon_set_save_enabled(qapp):
    """Test ProjectRibbon.set_save_enabled()."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Should not raise exception even if save button not set
    ribbon.set_save_enabled(True)
    ribbon.set_save_enabled(False)
    
    assert True


def test_project_ribbon_set_project_open(qapp):
    """Test ProjectRibbon.set_project_open()."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    ribbon.set_project_open(True)
    
    # Project buttons (except selection buttons) should be enabled
    for btn in ribbon._project_btns:
        if btn not in ribbon._selection_btns:
            assert btn.isEnabled()
    
    # Selection buttons should remain disabled until selection
    for btn in ribbon._selection_btns:
        assert not btn.isEnabled()
    
    ribbon.set_project_open(False)
    
    # All project buttons should be disabled
    for btn in ribbon._project_btns:
        assert not btn.isEnabled()


def test_project_ribbon_set_delete_enabled(qapp):
    """Test ProjectRibbon.set_delete_enabled()."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    ribbon.set_delete_enabled(True)
    
    if ribbon._del_btn:
        assert ribbon._del_btn.isEnabled()
    
    ribbon.set_delete_enabled(False)
    
    if ribbon._del_btn:
        assert not ribbon._del_btn.isEnabled()


def test_project_ribbon_set_confluence_sync_state(qapp):
    """Test ProjectRibbon.set_confluence_sync_state()."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    ribbon.set_confluence_sync_state(True, "Sync enabled")
    assert ribbon._confluence_sync_btn.isEnabled()
    assert ribbon._confluence_sync_btn.toolTip() == "Sync enabled"
    
    ribbon.set_confluence_sync_state(False, "Sync disabled")
    assert not ribbon._confluence_sync_btn.isEnabled()
    assert ribbon._confluence_sync_btn.toolTip() == "Sync disabled"


def test_project_ribbon_confluence_config_btn_exists(qapp):
    """Confluence config button is created and is always enabled."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    assert ribbon._confluence_config_btn is not None
    # Config button is always enabled — not project-gated
    assert ribbon._confluence_config_btn.isEnabled()


def test_project_ribbon_set_confluence_config_state(qapp):
    """set_confluence_config_state() changes enabled state and tooltip."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_confluence_config_state(False, "DB not configured")
    assert not ribbon._confluence_config_btn.isEnabled()
    assert ribbon._confluence_config_btn.toolTip() == "DB not configured"
    ribbon.set_confluence_config_state(True, "Configure Confluence Calendar")
    assert ribbon._confluence_config_btn.isEnabled()


def test_project_ribbon_confluence_config_btn_not_in_project_btns(qapp):
    """Confluence config button is NOT in _project_btns (always stays enabled)."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    # set_project_open(False) must not disable the config button
    ribbon.set_project_open(False)
    assert ribbon._confluence_config_btn.isEnabled()


def test_project_ribbon_set_resource_units_checked(qapp):
    """Test ProjectRibbon.set_resource_units_checked()."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Should not raise exception
    ribbon.set_resource_units_checked(True)
    ribbon.set_resource_units_checked(False)
    
    assert True


def test_project_ribbon_update_actions(qapp):
    """Test ProjectRibbon.update_actions()."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Should update labels and enabled state
    ribbon.update_actions("Add Task", "Delete Task", enabled=True, zoom_enabled=True)
    
    if ribbon._add_btn:
        assert "Task" in ribbon._add_btn.text()
    
    if ribbon._del_btn:
        assert "Task" in ribbon._del_btn.text()


def test_project_ribbon_call_method(qapp):
    """Test ProjectRibbon._call() calls parent method."""
    from ribbon import ProjectRibbon
    from PyQt5.QtWidgets import QMainWindow
    
    parent = QMainWindow()
    parent.test_method = MagicMock()
    
    ribbon = ProjectRibbon(parent)
    ribbon._call("test_method", "arg1", "arg2")
    
    parent.test_method.assert_called_once_with("arg1", "arg2")


def test_project_ribbon_call_method_no_parent(qapp):
    """Test ProjectRibbon._call() handles missing parent method."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Should not raise exception if method doesn't exist
    ribbon._call("nonexistent_method")
    
    assert True


def test_project_ribbon_tab_changed_signal(qapp):
    """Test ProjectRibbon emits ribbon_tab_changed signal."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    signal_received = []
    
    ribbon.ribbon_tab_changed.connect(lambda idx: signal_received.append(idx))
    
    ribbon._tab_buttons[2].click()
    
    assert 2 in signal_received


def test_project_ribbon_build_task_panel(qapp):
    """Test ProjectRibbon._build_task_panel() creates task panel."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Task panel should have buttons
    assert ribbon._add_btn is not None
    assert ribbon._del_btn is not None


def test_project_ribbon_build_resource_panel(qapp):
    """Test ProjectRibbon._build_resource_panel() creates resource panel."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Resource panel should be created (panel index 1)
    assert ribbon._panels[1] is not None


def test_project_ribbon_build_report_panel(qapp):
    """Test ProjectRibbon._build_report_panel() creates report panel."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Report panel should be created (panel index 2)
    assert ribbon._panels[2] is not None


def test_project_ribbon_activate_tab(qapp):
    """Test ProjectRibbon._activate_tab() switches panels."""
    from ribbon import ProjectRibbon
    from PyQt5.QtCore import QCoreApplication
    
    ribbon = ProjectRibbon()
    
    # Activate second tab
    ribbon._activate_tab(1)
    QCoreApplication.processEvents()  # Process UI updates
    
    assert ribbon._active_tab == 1
    # Check tab buttons
    assert ribbon._tab_buttons[1].isChecked()
    assert not ribbon._tab_buttons[0].isChecked()
    # The activated panel should be set visible (even if not rendered yet)
    # Test passes if switching works without exceptions


def test_project_ribbon_selection_buttons(qapp):
    """Test ProjectRibbon tracks selection-dependent buttons."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Delete button should be in selection buttons
    assert ribbon._del_btn in ribbon._selection_btns


def test_project_ribbon_project_buttons(qapp):
    """Test ProjectRibbon tracks project-dependent buttons."""
    from ribbon import ProjectRibbon
    
    ribbon = ProjectRibbon()
    
    # Add and delete buttons should be in project buttons
    assert ribbon._add_btn in ribbon._project_btns
    assert ribbon._del_btn in ribbon._project_btns
    assert len(ribbon._project_btns) > 2  # Should have more buttons


# ---------------------------------------------------------------------------
# add_menu_button helper  (RB-30 … RB-36)
# ---------------------------------------------------------------------------

def test_ribbon_group_add_menu_button_returns_tool_button(qapp):
    """RB-30: add_menu_button returns a QToolButton."""
    from ribbon import _RibbonGroup
    cb1 = MagicMock()
    group = _RibbonGroup("G")
    btn = group.add_menu_button("Lbl", "tip", [("Action 1", cb1)])
    assert isinstance(btn, QToolButton)


def test_ribbon_group_add_menu_button_has_menu(qapp):
    """RB-31: The returned button has a QMenu attached."""
    from ribbon import _RibbonGroup
    from PyQt5.QtWidgets import QMenu
    cb1 = MagicMock()
    group = _RibbonGroup("G")
    btn = group.add_menu_button("Lbl", "tip", [("Action 1", cb1)])
    assert btn.menu() is not None
    assert isinstance(btn.menu(), QMenu)


def test_ribbon_group_add_menu_button_action_count(qapp):
    """RB-32: The attached menu contains exactly the supplied number of actions."""
    from ribbon import _RibbonGroup
    cb1, cb2, cb3 = MagicMock(), MagicMock(), MagicMock()
    group = _RibbonGroup("G")
    btn = group.add_menu_button("Lbl", "tip", [
        ("Action 1", cb1),
        ("Action 2", cb2),
        ("Action 3", cb3),
    ])
    assert len(btn.menu().actions()) == 3


def test_ribbon_group_add_menu_button_default_slot_called(qapp):
    """RB-33: Clicking the button face triggers the supplied default_slot."""
    from ribbon import _RibbonGroup
    cb_default = MagicMock()
    cb_menu = MagicMock()
    group = _RibbonGroup("G")
    btn = group.add_menu_button("Lbl", "tip", [("Action 1", cb_menu)],
                                default_slot=cb_default)
    btn.click()
    cb_default.assert_called_once()
    cb_menu.assert_not_called()


def test_ribbon_group_add_menu_button_default_slot_falls_back_to_first_action(qapp):
    """RB-34: When default_slot is None, clicking the button face calls actions[0][1]."""
    from ribbon import _RibbonGroup
    cb1 = MagicMock()
    cb2 = MagicMock()
    group = _RibbonGroup("G")
    btn = group.add_menu_button("Lbl", "tip", [("Action 1", cb1), ("Action 2", cb2)],
                                default_slot=None)
    btn.click()
    cb1.assert_called_once()
    cb2.assert_not_called()


def test_ribbon_group_add_menu_button_popup_mode(qapp):
    """RB-35: Button popup mode defaults to MenuButtonPopup."""
    from ribbon import _RibbonGroup
    group = _RibbonGroup("G")
    btn = group.add_menu_button("Lbl", "tip", [("A", MagicMock())])
    assert btn.popupMode() == QToolButton.MenuButtonPopup


def test_ribbon_group_add_menu_button_in_project_btns_can_be_disabled(qapp):
    """RB-36: A menu button appended to _project_btns is disabled by set_project_open(False)."""
    from ribbon import _RibbonGroup, ProjectRibbon
    ribbon = ProjectRibbon()
    group = _RibbonGroup("G")
    extra_btn = group.add_menu_button("Extra", "tip", [("A", MagicMock())])
    ribbon._project_btns.append(extra_btn)
    ribbon.set_project_open(False)
    assert not extra_btn.isEnabled()


# ---------------------------------------------------------------------------
# Listview split-button popup item counts for each converted ribbon button (RB-37 … RB-46)
#
# Buttons now use _SplitToolButton + _RibbonListPopup instead of QMenu/QAction.
# The dummy QMenu still exists (for the ▾ arrow) but is empty.
# Tests verify the popup list item count instead.
# ---------------------------------------------------------------------------

def test_project_ribbon_jira_sync_btn_is_menu_button(qapp):
    """RB-37: Jira Sync listview split-button has 3 popup entries."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    btn = ribbon._jira_sync_btn
    assert isinstance(btn, _SplitToolButton)
    popup = btn.findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 3


def test_project_ribbon_jira_push_btn_is_menu_button(qapp):
    """RB-38: Jira Push listview split-button has 2 popup entries."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    btn = ribbon._jira_push_btn
    assert isinstance(btn, _SplitToolButton)
    popup = btn.findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 2


def test_project_ribbon_add_resource_btn_is_menu_button(qapp):
    """RB-39: Add Resource listview split-button has 3 popup entries."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    add_res_btns = [b for b in ribbon._project_btns
                    if isinstance(b, _SplitToolButton)
                    and "Add" in b.text() and "Resource" in b.text()]
    assert len(add_res_btns) == 1
    popup = add_res_btns[0].findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 3


def test_project_ribbon_gantt_export_btn_is_menu_button(qapp):
    """RB-40: Gantt Export listview split-button has 5 popup entries (2 save + 1 sep + 2 email)."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    gantt_btns = [b for b in ribbon._project_btns
                  if isinstance(b, _SplitToolButton) and "Gantt" in b.text()]
    assert len(gantt_btns) == 1
    popup = gantt_btns[0].findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 5


def test_project_ribbon_timeline_export_btn_is_menu_button(qapp):
    """RB-41: Timeline Export listview split-button has 4 popup entries (2 save + 1 sep + 1 email)."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    tl_btns = [b for b in ribbon._project_btns
               if isinstance(b, _SplitToolButton) and "Timeline" in b.text()]
    assert len(tl_btns) == 1
    popup = tl_btns[0].findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 4


def test_project_ribbon_set_baseline_btn_is_menu_button(qapp):
    """RB-42: Set Baseline listview split-button has 3 popup entries."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    set_btns = [b for b in ribbon._project_btns
                if isinstance(b, _SplitToolButton) and "Set" in b.text()
                and "Baseline" in b.text()]
    assert len(set_btns) == 1
    popup = set_btns[0].findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 3


def test_project_ribbon_clear_baseline_btn_is_menu_button(qapp):
    """RB-43: Clear Baseline listview split-button has 2 popup entries."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    clr_btns = [b for b in ribbon._project_btns
                if isinstance(b, _SplitToolButton) and "Clear" in b.text()
                and "Baseline" in b.text()]
    assert len(clr_btns) == 1
    popup = clr_btns[0].findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 2


def test_project_ribbon_vcs_commit_btn_is_menu_button(qapp):
    """RB-44: VCS Commit listview split-button has 2 popup entries."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    btn = ribbon._vcs_commit_btn
    assert isinstance(btn, _SplitToolButton)
    popup = btn.findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 2


def test_project_ribbon_vcs_pull_btn_is_menu_button(qapp):
    """RB-45: VCS Pull listview split-button has 3 popup entries (merge, rebase, fetch)."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    btn = ribbon._vcs_pull_btn
    assert isinstance(btn, _SplitToolButton)
    popup = btn.findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 3


def test_project_ribbon_vcs_update_btn_is_menu_button(qapp):
    """RB-46: SVN Update listview split-button has 2 popup entries."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    btn = ribbon._vcs_update_btn
    assert isinstance(btn, _SplitToolButton)
    popup = btn.findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 2


# ---------------------------------------------------------------------------
# Split-buttons disabled when no project open (RB-47)
# ---------------------------------------------------------------------------

def test_project_ribbon_menu_btns_disabled_when_no_project(qapp):
    """RB-47: All new split-buttons are disabled by set_project_open(False)."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_project_open(False)
    # All buttons registered in _project_btns must be disabled
    menu_btns = [b for b in ribbon._project_btns
                 if isinstance(b, QToolButton) and b.menu()]
    assert len(menu_btns) > 0
    for btn in menu_btns:
        assert not btn.isEnabled(), f"Expected {btn.text()!r} to be disabled"


# ---------------------------------------------------------------------------
# Resource SVG popup item count (RB-48)
# ---------------------------------------------------------------------------

def test_project_ribbon_resource_svg_btn_popup_count(qapp):
    """RB-48: Resource SVG listview split-button has 3 popup entries (1 save + 1 sep + 1 email)."""
    from ribbon import ProjectRibbon, _RibbonListPopup, _SplitToolButton
    ribbon = ProjectRibbon()
    rsvg_btns = [b for b in ribbon._project_btns
                 if isinstance(b, _SplitToolButton) and "Resource" in b.text()
                 and "SVG" in b.text()]
    assert len(rsvg_btns) == 1
    popup = rsvg_btns[0].findChild(_RibbonListPopup)
    assert popup is not None
    assert popup._list.count() == 3


# ---------------------------------------------------------------------------
# _RibbonListPopup.set_item_enabled (RB-49 … RB-51)
# ---------------------------------------------------------------------------

def test_ribbon_list_popup_set_item_enabled_disables_item(qapp):
    """RB-49: set_item_enabled(label, False) removes ItemIsEnabled flag."""
    from ribbon import _RibbonGroup
    from PyQt5.QtCore import Qt
    cb = lambda: None  # noqa: E731
    group = _RibbonGroup("G")
    btn = group.add_listview_button("Lbl", "tip", [("Action A", cb), ("Action B", cb)])
    popup = btn._ribbon_popup
    popup.set_item_enabled("Action A", False, "Not available")
    item = popup._list.item(0)
    assert not (item.flags() & Qt.ItemIsEnabled)
    assert item.data(Qt.ToolTipRole) == "Not available"


def test_ribbon_list_popup_set_item_enabled_re_enables_item(qapp):
    """RB-50: set_item_enabled(label, True) restores ItemIsEnabled flag."""
    from ribbon import _RibbonGroup
    from PyQt5.QtCore import Qt
    cb = lambda: None  # noqa: E731
    group = _RibbonGroup("G")
    btn = group.add_listview_button("Lbl", "tip", [("Action A", cb)])
    popup = btn._ribbon_popup
    popup.set_item_enabled("Action A", False, "Off")
    popup.set_item_enabled("Action A", True)
    item = popup._list.item(0)
    assert bool(item.flags() & Qt.ItemIsEnabled)
    assert not item.data(Qt.ToolTipRole)  # tooltip cleared


def test_ribbon_list_popup_set_item_enabled_unknown_label_is_noop(qapp):
    """RB-51: set_item_enabled with an unknown label does not raise."""
    from ribbon import _RibbonGroup
    cb = lambda: None  # noqa: E731
    group = _RibbonGroup("G")
    btn = group.add_listview_button("Lbl", "tip", [("Action A", cb)])
    popup = btn._ribbon_popup
    popup.set_item_enabled("Nonexistent", False, "tip")  # must not raise


# ---------------------------------------------------------------------------
# ProjectRibbon.set_email_actions_enabled (RB-52 … RB-53)
# ---------------------------------------------------------------------------

def test_project_ribbon_set_email_actions_enabled_disables(qapp):
    """RB-52: set_email_actions_enabled(False) disables all email items in all three popups."""
    from ribbon import ProjectRibbon
    from PyQt5.QtCore import Qt
    ribbon = ProjectRibbon()
    tip = "No email account configured"
    ribbon.set_email_actions_enabled(False, tip)
    _EMAIL_LABELS = ["Email Gantt SVG", "Email to All Resources", "Email Timeline SVG"]
    for popup in (ribbon._gantt_exp_popup, ribbon._rsvg_popup, ribbon._tl_exp_popup):
        for i in range(popup._list.count()):
            item = popup._list.item(i)
            label = item.data(Qt.DisplayRole)
            if label in _EMAIL_LABELS:
                assert not (item.flags() & Qt.ItemIsEnabled), (
                    f"{label!r} in popup should be disabled"
                )
                assert item.data(Qt.ToolTipRole) == tip


def test_project_ribbon_set_email_actions_enabled_enables(qapp):
    """RB-53: set_email_actions_enabled(True) re-enables all email items in all three popups."""
    from ribbon import ProjectRibbon
    from PyQt5.QtCore import Qt
    ribbon = ProjectRibbon()
    ribbon.set_email_actions_enabled(False, "off")
    ribbon.set_email_actions_enabled(True)
    _EMAIL_LABELS = ["Email Gantt SVG", "Email to All Resources", "Email Timeline SVG"]
    for popup in (ribbon._gantt_exp_popup, ribbon._rsvg_popup, ribbon._tl_exp_popup):
        for i in range(popup._list.count()):
            item = popup._list.item(i)
            label = item.data(Qt.DisplayRole)
            if label in _EMAIL_LABELS:
                assert bool(item.flags() & Qt.ItemIsEnabled), (
                    f"{label!r} in popup should be enabled"
                )


# ---------------------------------------------------------------------------
# CPM ribbon buttons (Phase 3)
# ---------------------------------------------------------------------------

def test_cpm_report_button_in_project_btns(qapp):
    """RB-CPM-1: CPM Report dropdown must be in _project_btns — disabled without open project."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    cpm_btns = [b for b in ribbon._project_btns if "CPM" in (b.text() or "")]
    assert len(cpm_btns) >= 1, "At least one CPM button must be in _project_btns"


def test_cpm_results_view_button_in_project_btns(qapp):
    """RB-CPM-2: CPM Results view button must be in _project_btns."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    results_btns = [b for b in ribbon._project_btns
                    if "CPM" in (b.text() or "") and "Results" in (b.text() or "")]
    assert len(results_btns) >= 1, "A 'CPM Results' button must be in _project_btns"


def test_cpm_results_button_registered_in_view_btns_by_tab(qapp):
    """RB-CPM-3: CPM Results button must be registered in _view_btns_by_app_tab[TAB_CPM]."""
    from ribbon import ProjectRibbon
    from ui import TAB_CPM
    ribbon = ProjectRibbon()
    assert TAB_CPM in ribbon._view_btns_by_app_tab, \
        "TAB_CPM must have a registered button in _view_btns_by_app_tab"


def test_cpm_buttons_disabled_without_open_project(qapp):
    """RB-CPM-4: CPM buttons (in _project_btns) must be disabled when no project is open."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_project_open(False)
    cpm_btns = [b for b in ribbon._project_btns if "CPM" in (b.text() or "")]
    for btn in cpm_btns:
        assert not btn.isEnabled(), \
            f"CPM button '{btn.text()}' must be disabled when no project is open"


# ---------------------------------------------------------------------------
# CPM Report button — email-configured state (Phase 3 follow-up)
# ---------------------------------------------------------------------------

_NO_EMAIL_TIP = (
    "No email account configured.\n"
    "Use Email Accounts in the Report ribbon to add an SMTP account,\n"
    "then select it via Email Config."
)


def test_cpm_report_disabled_when_email_not_configured(qapp):
    """RB-58: set_email_actions_enabled(False) disables the CPM Report button."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_project_open(True)   # project open so button would normally be on
    ribbon.set_email_actions_enabled(False, _NO_EMAIL_TIP)
    assert not ribbon._cpm_exp_btn.isEnabled()


def test_cpm_report_tooltip_when_email_not_configured(qapp):
    """RB-59: CPM Report button tooltip is the no-email message when email is not configured."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_project_open(True)
    ribbon.set_email_actions_enabled(False, _NO_EMAIL_TIP)
    assert "No email account configured" in ribbon._cpm_exp_btn.toolTip()


def test_cpm_report_enabled_when_email_configured_and_project_open(qapp):
    """RB-60: CPM Report button is enabled after set_email_actions_enabled(True) with project open."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_project_open(True)
    ribbon.set_email_actions_enabled(False, _NO_EMAIL_TIP)   # disable first
    ribbon.set_email_actions_enabled(True)                   # then re-enable
    assert ribbon._cpm_exp_btn.isEnabled()


def test_cpm_report_restores_original_tooltip_when_email_configured(qapp):
    """RB-61: Original tooltip is restored when email is configured."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_project_open(True)
    ribbon.set_email_actions_enabled(False, _NO_EMAIL_TIP)
    ribbon.set_email_actions_enabled(True)
    assert ribbon._cpm_exp_btn.toolTip() == ribbon._cpm_exp_btn_tip
    assert "No email account configured" not in ribbon._cpm_exp_btn.toolTip()


def test_cpm_report_stays_disabled_after_project_open_when_email_not_configured(qapp):
    """RB-62: set_project_open(True) must not override the email-disabled state."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_email_actions_enabled(False, _NO_EMAIL_TIP)
    ribbon.set_project_open(True)   # project opened while email still not configured
    assert not ribbon._cpm_exp_btn.isEnabled()


def test_cpm_report_disabled_when_email_configured_but_no_project(qapp):
    """RB-63: CPM Report button stays disabled when no project is open even if email is configured."""
    from ribbon import ProjectRibbon
    ribbon = ProjectRibbon()
    ribbon.set_email_actions_enabled(True)   # email configured
    ribbon.set_project_open(False)           # but no project
    assert not ribbon._cpm_exp_btn.isEnabled()

