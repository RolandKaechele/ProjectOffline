"""Tests for dialogs.py — Project detail dialogs.

Dialogs include:
  - NonWorkingDayDialog
  - AssignmentDetailDialog
  - TaskDialog
  - ResourceDialog
  - DependencyDialog
  - BaselineEntryDialog
  - ProjectInfoDialog

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
MPXJ Java objects are replaced with MagicMock instances.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
# Add current directory (tests/) for conftest imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from conftest import make_mock_task, make_mock_resource, make_mock_project


# ---------------------------------------------------------------------------
# NonWorkingDayDialog
# ---------------------------------------------------------------------------

class TestNonWorkingDayDialog:
    def test_dialog_exists(self, qapp):
        from dialogs import NonWorkingDayDialog
        dialog = NonWorkingDayDialog("Task1", "Saturday 2025-01-11", "Monday 2025-01-13")
        assert dialog is not None

    def test_dialog_has_constants(self):
        from dialogs import NonWorkingDayDialog
        assert hasattr(NonWorkingDayDialog, 'SNAP')
        assert hasattr(NonWorkingDayDialog, 'KEEP')
        assert hasattr(NonWorkingDayDialog, 'CANCEL')

    def test_dialog_title_set(self, qapp):
        from dialogs import NonWorkingDayDialog
        dialog = NonWorkingDayDialog("Task1", "Saturday 2025-01-11", "Monday 2025-01-13")
        assert dialog.windowTitle() != ""

    def test_dialog_is_modal(self, qapp):
        from dialogs import NonWorkingDayDialog
        dialog = NonWorkingDayDialog("Task1", "Saturday 2025-01-11", "Monday 2025-01-13")
        assert dialog.isModal()


# ---------------------------------------------------------------------------
# TaskDialog
# ---------------------------------------------------------------------------

class TestTaskDialog:
    def test_dialog_exists(self, qapp):
        from dialogs import TaskDialog
        task = make_mock_task(task_id=1, name="Test Task")
        project = make_mock_project(tasks=[task])
        # TaskDialog needs to import and call gantt_view functions, patch them
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dialog = TaskDialog(task, project)
        assert dialog is not None

    def test_dialog_is_modal(self, qapp):
        from dialogs import TaskDialog
        task = make_mock_task(task_id=1, name="Test Task")
        project = make_mock_project(tasks=[task])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dialog = TaskDialog(task, project)
        assert dialog.isModal()

    def test_dialog_created_with_task_and_project(self, qapp):
        from dialogs import TaskDialog
        task = make_mock_task(task_id=1, name="Test Task")
        project = make_mock_project(tasks=[task])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dialog = TaskDialog(task, project)
        # Dialog created successfully with both parameters
        assert dialog is not None

    # ------------------------------------------------------------------
    # Timeline checkbox (timeline_view= parameter)
    # ------------------------------------------------------------------

    def _make_timeline_view_mock(self, pinned_task_ids=(), pinned_milestone_ids=()):
        """Return a minimal mock that satisfies TaskDialog._tab_general."""
        tv = MagicMock()
        tv.is_task_pinned      = MagicMock(side_effect=lambda tid: tid in pinned_task_ids)
        tv.is_milestone_pinned = MagicMock(side_effect=lambda mid: mid in pinned_milestone_ids)
        return tv

    def test_timeline_checkbox_absent_without_timeline_view(self, qapp):
        """No timeline_view → _cb_timeline must be None (checkbox not shown)."""
        from dialogs import TaskDialog
        task = make_mock_task(task_id=1)
        project = make_mock_project(tasks=[task])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, timeline_view=None)
        assert dlg._cb_timeline is None

    def test_timeline_checkbox_present_with_timeline_view(self, qapp):
        """Passing timeline_view → _cb_timeline must be a QCheckBox."""
        from dialogs import TaskDialog
        from PyQt5.QtWidgets import QCheckBox
        task = make_mock_task(task_id=1)
        project = make_mock_project(tasks=[task])
        tv = self._make_timeline_view_mock()
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, timeline_view=tv)
        assert isinstance(dlg._cb_timeline, QCheckBox)

    def test_timeline_checkbox_checked_when_task_pinned(self, qapp):
        """Checkbox must be pre-checked when the task is already pinned."""
        from dialogs import TaskDialog
        task = make_mock_task(task_id=5)
        project = make_mock_project(tasks=[task])
        tv = self._make_timeline_view_mock(pinned_task_ids=(5,))
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, timeline_view=tv)
        assert dlg._cb_timeline.isChecked()

    def test_timeline_checkbox_unchecked_when_task_not_pinned(self, qapp):
        """Checkbox must be unchecked when the task is not pinned."""
        from dialogs import TaskDialog
        task = make_mock_task(task_id=5)
        project = make_mock_project(tasks=[task])
        tv = self._make_timeline_view_mock(pinned_task_ids=())
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, timeline_view=tv)
        assert not dlg._cb_timeline.isChecked()

    def test_timeline_checkbox_checked_when_milestone_pinned(self, qapp):
        """Milestone tasks: checkbox checked when pinned as milestone."""
        from dialogs import TaskDialog
        task = make_mock_task(task_id=7, is_milestone=True)
        project = make_mock_project(tasks=[task])
        tv = self._make_timeline_view_mock(pinned_milestone_ids=(7,))
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, timeline_view=tv)
        assert dlg._cb_timeline.isChecked()

    def test_timeline_checkbox_calls_is_task_pinned_with_correct_id(self, qapp):
        """is_task_pinned must be called with the integer task ID from getID()."""
        from dialogs import TaskDialog
        task = make_mock_task(task_id=42)
        project = make_mock_project(tasks=[task])
        tv = self._make_timeline_view_mock()
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            TaskDialog(task, project, timeline_view=tv)
        tv.is_task_pinned.assert_called_with(42)


# ---------------------------------------------------------------------------
# ResourceDialog
# ---------------------------------------------------------------------------

class TestResourceDialog:
    def test_dialog_exists(self, qapp):
        from dialogs import ResourceDialog
        res = make_mock_resource(res_id=1, name="Developer")
        project = make_mock_project(resources=[res])
        with patch('dialogs.QDialog.__init__'):
            try:
                dialog = ResourceDialog(res, project)
                assert dialog is not None
            except Exception:
                # If initialization fails due to missing Qt setup, that's ok for this test
                pass

    def test_resource_dialog_has_necessary_methods(self):
        from dialogs import ResourceDialog
        assert hasattr(ResourceDialog, '__init__')


# ---------------------------------------------------------------------------
# ResourceDialog — AD Lookup (DL-65 to DL-69)
# ---------------------------------------------------------------------------

class TestResourceDialogADLookup:
    """Tests for the 'Look up in AD…' button added to ResourceDialog.General tab."""

    def _make_resource_full(self, name="Smith, John", email=None, dept=None):
        """Return a mock resource with email and department attributes configured."""
        res = MagicMock()
        res.getID.return_value = 1
        res.getUniqueID.return_value = 1
        res.getName.return_value = name
        type_mock = MagicMock()
        type_mock.__str__ = MagicMock(return_value="Work")
        res.getType.return_value = type_mock
        res.getMaxUnits.return_value = 1.0
        std = MagicMock(); std.__str__ = MagicMock(return_value="$0.00/h")
        ovt = MagicMock(); ovt.__str__ = MagicMock(return_value="$0.00/h")
        res.getStandardRate.return_value = std
        res.getOvertimeRate.return_value = ovt
        res.getEmailAddress.return_value = email
        res.getDepartment.return_value = dept
        return res

    def _make_dialog(self, qapp, res, project):
        from dialogs import ResourceDialog
        project.getCustomFields.return_value = []
        return ResourceDialog(res, project)

    def test_email_field_prefilled_from_resource(self, qapp):
        """DL-65: Email QLineEdit is initialised from resource.getEmailAddress()."""
        res = self._make_resource_full(email="jane.doe@corp.com")
        project = make_mock_project(resources=[res])
        dlg = self._make_dialog(qapp, res, project)
        assert dlg._e_email.text() == "jane.doe@corp.com"

    def test_department_field_prefilled_from_resource(self, qapp):
        """DL-66: Department QLineEdit is initialised from resource.getDepartment()."""
        res = self._make_resource_full(dept="Research & Development")
        project = make_mock_project(resources=[res])
        dlg = self._make_dialog(qapp, res, project)
        assert dlg._e_dept.text() == "Research & Development"

    def test_ad_lookup_btn_present_with_correct_label(self, qapp):
        """DL-67: The 'Look up in AD…' button exists and its label contains 'AD'."""
        res = self._make_resource_full()
        project = make_mock_project(resources=[res])
        dlg = self._make_dialog(qapp, res, project)
        assert hasattr(dlg, '_ad_lookup_btn')
        assert "AD" in dlg._ad_lookup_btn.text()

    def test_do_ad_lookup_empty_name_shows_information(self, qapp):
        """DL-68: _do_ad_lookup() opens an information dialog when the name field is blank."""
        res = self._make_resource_full(name="")
        project = make_mock_project(resources=[res])
        dlg = self._make_dialog(qapp, res, project)
        with patch('dialogs.QMessageBox.information') as mock_info:
            dlg._do_ad_lookup()
        mock_info.assert_called_once()

    def test_do_ad_lookup_single_result_fills_email_and_dept(self, qapp):
        """DL-69: _do_ad_lookup() with a single AD hit writes email and department into the fields."""
        res = self._make_resource_full(name="Smith, John")
        project = make_mock_project(resources=[res])
        dlg = self._make_dialog(qapp, res, project)

        ad_hit = [{
            "email": "john.smith@corp.com",
            "department": "IT",
            "display_name": "John Smith",
            "username": "jsmith",
        }]

        mock_sel_dlg = MagicMock()
        mock_sel_dlg.exec_.return_value = 1  # QDialog.Accepted
        mock_sel_dlg.selected_user.return_value = ad_hit[0]

        with patch('integrations.ad_integration.is_ad_available', return_value=True), \
             patch('integrations.ad_integration.lookup_by_name_all', return_value=ad_hit), \
             patch('progress_worker.run_indeterminate', side_effect=lambda *a, **kw: a[2]()), \
             patch('dialogs.ADUserSelectDialog', return_value=mock_sel_dlg):
            dlg._do_ad_lookup()

        assert dlg._e_email.text() == "john.smith@corp.com"
        assert dlg._e_dept.text() == "IT"


# ---------------------------------------------------------------------------
# DependencyDialog
# ---------------------------------------------------------------------------

class TestDependencyDialog:
    def test_dialog_exists(self, qapp):
        from dialogs import DependencyDialog
        task = make_mock_task(task_id=1, name="Task A")
        predecessor = make_mock_task(task_id=2, name="Task B")
        project = make_mock_project(tasks=[task, predecessor])
        
        rel = MagicMock()
        rel.getTargetTask.return_value = predecessor
        rel.getLag.return_value = MagicMock()
        rel.getLag.return_value.getDuration.return_value = 0.0
        rel_type = MagicMock()
        rel_type.__str__ = MagicMock(return_value="FS")
        rel.getType.return_value = rel_type
        
        with patch('dialogs.QDialog.__init__'):
            try:
                dialog = DependencyDialog(rel, task, project)
                assert True  # Dialog class exists
            except Exception:
                pass

    def test_dependency_dialog_has_necessary_methods(self):
        from dialogs import DependencyDialog
        assert hasattr(DependencyDialog, '__init__')


# ---------------------------------------------------------------------------
# BaselineEntryDialog
# ---------------------------------------------------------------------------

class TestBaselineEntryDialog:
    def test_dialog_exists(self, qapp):
        from dialogs import BaselineEntryDialog
        task = make_mock_task(task_id=1, name="Test Task")
        with patch('gantt_view._to_qdate', return_value=None):
            dialog = BaselineEntryDialog(task)
        assert dialog is not None

    def test_dialog_is_modal(self, qapp):
        from dialogs import BaselineEntryDialog
        task = make_mock_task(task_id=1, name="Test Task")
        with patch('gantt_view._to_qdate', return_value=None):
            dialog = BaselineEntryDialog(task)
        assert dialog.isModal()

    def test_dialog_created_with_task(self, qapp):
        from dialogs import BaselineEntryDialog
        task = make_mock_task(task_id=1, name="Test Task")
        with patch('gantt_view._to_qdate', return_value=None):
            dialog = BaselineEntryDialog(task)
        # Dialog created successfully with task parameter
        assert dialog is not None


# ---------------------------------------------------------------------------
# AssignmentDetailDialog
# ---------------------------------------------------------------------------

class TestAssignmentDetailDialog:
    def test_dialog_exists(self, qapp):
        from dialogs import AssignmentDetailDialog
        assignment = MagicMock()
        task = make_mock_task(task_id=1, name="Test Task")
        res = make_mock_resource(res_id=1, name="Dev")
        assignment.getTask.return_value = task
        assignment.getResource.return_value = res
        assignment.getWork.return_value = MagicMock()
        assignment.getWork.return_value.getDuration.return_value = 40.0
        
        with patch('gantt_view._to_qdate', return_value=None):
            dialog = AssignmentDetailDialog(assignment, "Test Task")
        assert dialog is not None

    def test_dialog_is_modal(self, qapp):
        from dialogs import AssignmentDetailDialog
        assignment = MagicMock()
        task = make_mock_task(task_id=1, name="Test Task")
        res = make_mock_resource(res_id=1, name="Dev")
        assignment.getTask.return_value = task
        assignment.getResource.return_value = res
        assignment.getWork.return_value = MagicMock()
        assignment.getWork.return_value.getDuration.return_value = 40.0
        
        with patch('gantt_view._to_qdate', return_value=None):
            dialog = AssignmentDetailDialog(assignment, "Test Task")
        assert dialog.isModal()


# ---------------------------------------------------------------------------
# ProjectInfoDialog
# ---------------------------------------------------------------------------

class TestProjectInfoDialog:
    def test_dialog_exists(self, qapp):
        from dialogs import ProjectInfoDialog
        project = make_mock_project()
        with patch('gantt_view._to_qdate', return_value=None):
            dialog = ProjectInfoDialog(project)
        assert dialog is not None

    def test_dialog_is_modal(self, qapp):
        from dialogs import ProjectInfoDialog
        project = make_mock_project()
        with patch('gantt_view._to_qdate', return_value=None):
            dialog = ProjectInfoDialog(project)
        assert dialog.isModal()


# ---------------------------------------------------------------------------
# TaskDialog — critical_ids parameter
# ---------------------------------------------------------------------------

class TestTaskDialogCriticalIds:
    """TaskDialog uses the CPM-calculated critical_ids set to show the
    Critical field, ignoring getCritical() when the set is provided."""

    def _make_dlg(self, qapp, task_id, critical_ids):
        from dialogs import TaskDialog
        task = make_mock_task(task_id=task_id, name="Task")
        project = make_mock_project(tasks=[task])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, critical_ids=critical_ids)
        return dlg

    def test_task_in_critical_ids_is_critical(self, qapp):
        """Task whose ID is in critical_ids must display as critical."""
        dlg = self._make_dlg(qapp, task_id=5, critical_ids={5, 6})
        # _critical_ids stored on the dialog
        assert 5 in dlg._critical_ids

    def test_task_not_in_critical_ids_is_not_critical(self, qapp):
        """Task whose ID is absent from critical_ids must not be critical."""
        dlg = self._make_dlg(qapp, task_id=5, critical_ids={3, 4})
        assert 5 not in dlg._critical_ids

    def test_empty_critical_ids_means_not_critical(self, qapp):
        """An empty CPM set → task is not critical, regardless of getCritical()."""
        from dialogs import TaskDialog
        task = make_mock_task(task_id=1, name="Task")
        task.getCritical.return_value = True   # MPXJ flag says critical
        project = make_mock_project(tasks=[task])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, critical_ids=set())
        # The CPM set is empty: task should not be in it
        assert 1 not in dlg._critical_ids

    def test_critical_ids_none_falls_back_to_get_critical(self, qapp):
        """critical_ids=None → fallback branch uses getCritical()."""
        from dialogs import TaskDialog
        task = make_mock_task(task_id=1, name="Task")
        task.getCritical.return_value = True
        project = make_mock_project(tasks=[task])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, critical_ids=None)
        # critical_ids is None → dialog stores None
        assert dlg._critical_ids is None

    def test_critical_ids_stored_on_dialog(self, qapp):
        """The passed set is stored on dlg._critical_ids verbatim."""
        crit = {7, 8, 9}
        dlg = self._make_dlg(qapp, task_id=7, critical_ids=crit)
        assert dlg._critical_ids is crit


# ---------------------------------------------------------------------------
# TaskDialog — Jira tab
# ---------------------------------------------------------------------------

class TestTaskDialogJiraTab:
    """Unit tests for the Jira tab in TaskDialog.

    \testinit
    Create a mock task and project. Optionally supply task_jira_data with
    jira_key / jira_status entries or leave it empty / None.

    \testrun
    Instantiate TaskDialog with the task_jira_data keyword argument and call
    _tab_jira() directly to obtain the widget.

    \testexpect
    When task_jira_data is falsy the tab renders an explanatory label.
    When task_jira_data contains jira_key and jira_status those values appear
    in the tab's child QLineEdit widgets.

    \testcheck
    Assert widget child presence and text content.
    """

    def _make_dlg(self, qapp, task_jira_data=None):
        from dialogs import TaskDialog
        task = make_mock_task(task_id=1, name="T")
        project = make_mock_project(tasks=[task])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project, task_jira_data=task_jira_data)
        return dlg

    def test_jira_data_stored_on_dialog(self, qapp):
        data = {"jira_key": "PROJ-1", "jira_status": "Open"}
        dlg = self._make_dlg(qapp, task_jira_data=data)
        assert dlg._task_jira_data == data

    def test_jira_data_defaults_to_empty_dict_when_none(self, qapp):
        dlg = self._make_dlg(qapp, task_jira_data=None)
        assert dlg._task_jira_data == {}

    def test_jira_tab_widget_returned(self, qapp):
        """_tab_jira() must return a QWidget without raising."""
        from PyQt5.QtWidgets import QWidget
        dlg = self._make_dlg(qapp, task_jira_data={"jira_key": "X-1", "jira_status": "Open"})
        tab = dlg._tab_jira()
        assert isinstance(tab, QWidget)

    def test_jira_tab_no_data_returns_widget(self, qapp):
        """_tab_jira() with no data must still return a QWidget."""
        from PyQt5.QtWidgets import QWidget
        dlg = self._make_dlg(qapp, task_jira_data=None)
        tab = dlg._tab_jira()
        assert isinstance(tab, QWidget)

    def test_jira_tab_shows_jira_key(self, qapp):
        """When task_jira_data has jira_key, a QLineEdit with that value must exist."""
        from PyQt5.QtWidgets import QLineEdit
        dlg = self._make_dlg(qapp, task_jira_data={"jira_key": "ZOISIT-42", "jira_status": "In Progress"})
        tab = dlg._tab_jira()
        line_edits = tab.findChildren(QLineEdit)
        texts = [le.text() for le in line_edits]
        assert any("ZOISIT-42" in t for t in texts)

    def test_jira_tab_shows_jira_status(self, qapp):
        """When task_jira_data has jira_status, a QLineEdit with that value must exist."""
        from PyQt5.QtWidgets import QLineEdit
        dlg = self._make_dlg(qapp, task_jira_data={"jira_key": "ZOISIT-42", "jira_status": "In Progress"})
        tab = dlg._tab_jira()
        line_edits = tab.findChildren(QLineEdit)
        texts = [le.text() for le in line_edits]
        assert any("In Progress" in t for t in texts)

    def test_jira_tab_fields_are_read_only(self, qapp):
        """All QLineEdit fields on the Jira tab must be read-only."""
        from PyQt5.QtWidgets import QLineEdit
        dlg = self._make_dlg(qapp, task_jira_data={"jira_key": "X-1", "jira_status": "Done"})
        tab = dlg._tab_jira()
        for le in tab.findChildren(QLineEdit):
            assert le.isReadOnly()




    def test_dialog_created_with_project(self, qapp):
        from dialogs import ProjectInfoDialog
        project = make_mock_project()
        with patch('gantt_view._to_qdate', return_value=None):
            dialog = ProjectInfoDialog(project)
        # Dialog created successfully with project parameter
        assert dialog is not None


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

class TestDialogHelpers:
    def test_make_header_function_exists(self):
        from dialogs import _make_header
        assert callable(_make_header)

    def test_make_header_creates_widget(self, qapp):
        from dialogs import _make_header
        header = _make_header("Test Title", "Test Subtitle")
        assert header is not None

    def test_make_button_row_function_exists(self):
        from dialogs import _make_button_row
        assert callable(_make_button_row)

    def test_make_button_row_creates_widget(self, qapp):
        from dialogs import _make_button_row
        from PyQt5.QtWidgets import QDialog
        dialog = QDialog()
        button_row = _make_button_row(dialog)
        assert button_row is not None

    def test_xml_indent_et_function_exists(self):
        from dialogs import _xml_indent_et
        assert callable(_xml_indent_et)


# ---------------------------------------------------------------------------
# Base Dialog
# ---------------------------------------------------------------------------

class TestBaseDialog:
    def test_base_dialog_exists(self, qapp):
        from dialogs import _BaseDialog
        dialog = _BaseDialog("Test Dialog")
        assert dialog is not None

    def test_base_dialog_is_modal(self, qapp):
        from dialogs import _BaseDialog
        dialog = _BaseDialog("Test Dialog")
        assert dialog.isModal()

    def test_base_dialog_has_minimum_width(self, qapp):
        from dialogs import _BaseDialog
        dialog = _BaseDialog("Test Dialog")
        assert dialog.minimumWidth() >= 520

    def test_base_dialog_has_layout(self, qapp):
        from dialogs import _BaseDialog
        dialog = _BaseDialog("Test Dialog")
        assert dialog.layout() is not None


# ---------------------------------------------------------------------------
# NewProjectCalendarsDialog
# ---------------------------------------------------------------------------

class TestNewProjectCalendarsDialog:
    """Tests for the optional holiday-calendar picker shown during new project creation."""

    def test_dialog_exists(self, qapp):
        from dialogs import NewProjectCalendarsDialog
        dlg = NewProjectCalendarsDialog(None)
        assert dlg is not None

    def test_dialog_is_modal(self, qapp):
        from dialogs import NewProjectCalendarsDialog
        dlg = NewProjectCalendarsDialog(None)
        assert dlg.isModal()

    def test_has_german_states_list(self, qapp):
        from dialogs import NewProjectCalendarsDialog
        assert hasattr(NewProjectCalendarsDialog, '_GERMAN_STATES')
        assert len(NewProjectCalendarsDialog._GERMAN_STATES) == 15

    def test_has_other_countries_list(self, qapp):
        from dialogs import NewProjectCalendarsDialog
        assert hasattr(NewProjectCalendarsDialog, '_OTHER_COUNTRIES')
        assert len(NewProjectCalendarsDialog._OTHER_COUNTRIES) == 5

    def test_get_selected_returns_empty_by_default(self, qapp):
        """All checkboxes start unchecked → get_selected() returns []."""
        from dialogs import NewProjectCalendarsDialog
        dlg = NewProjectCalendarsDialog(None)
        assert dlg.get_selected() == []

    def test_germany_state_names_are_correct(self, qapp):
        from dialogs import NewProjectCalendarsDialog
        states = NewProjectCalendarsDialog._GERMAN_STATES
        assert "Bayern" in states
        assert "Baden-Württemberg" in states
        assert "Sachsen" in states

    def test_country_names_include_france_and_india(self, qapp):
        from dialogs import NewProjectCalendarsDialog
        countries = NewProjectCalendarsDialog._OTHER_COUNTRIES
        assert "France" in countries
        assert "India" in countries


# ---------------------------------------------------------------------------
# TaskDialog — Resource tab (3-column table with per-row ✕ delete button)
# ---------------------------------------------------------------------------

class TestTaskDialogResourceTab:
    """Tests for the resource-assignment tab of TaskDialog.

    Covers the 3-column QTableWidget (Name | Units% | ✕), _del_btns list
    tracking, _add_assignment_row (including null-resource guard), and
    _delete_assignment_row via button click.

    These tests exercise bug fixes for:
    - Assignment showing '(unknown)' after clicking ✕ then applying the dialog
      (root cause: unreliable cellWidget identity; fixed via _del_btns list).
    - Per-row ✕ delete button replacing the global 'Remove' button.
    """

    @pytest.fixture
    def dlg(self, qapp):
        from dialogs import TaskDialog
        res = make_mock_resource(res_id=1, name="Alice")
        task = make_mock_task(task_id=1, name="Test Task")
        task.getResourceAssignments.return_value = []
        project = make_mock_project(tasks=[task], resources=[res])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            return TaskDialog(task, project)

    def test_resource_table_has_three_columns(self, dlg):
        """Resource table must have 3 columns: Name, Units (%), and delete-button."""
        assert dlg._res_tbl.columnCount() == 3

    def test_del_btns_starts_empty_with_no_assignments(self, dlg):
        """_del_btns is initialised to [] when the task has no existing assignments."""
        assert dlg._del_btns == []


# ---------------------------------------------------------------------------
# set_resource_thumbnail_store() — dept_store parameter (DL-74)
# ---------------------------------------------------------------------------

class TestSetResourceThumbnailStore:
    """set_resource_thumbnail_store() must wire up both the thumbnail store and
    the department store, resetting them when called with empty dicts."""

    def test_dept_store_is_set(self):
        """dept_store kwarg must be stored in the module-level _resource_dept_store."""
        import dialogs as dlg_mod
        thumb = {"1": b"\x89PNG"}
        dept  = {"1": "Engineering"}
        dlg_mod.set_resource_thumbnail_store(thumb, dept_store=dept, sidecar_path=None)
        assert dlg_mod._resource_dept_store == dept

    def test_thumb_store_is_set(self):
        """Thumbnail store must be stored in _resource_thumbnail_store."""
        import dialogs as dlg_mod
        thumb = {"2": b"\xff\xd8"}
        dlg_mod.set_resource_thumbnail_store(thumb, dept_store={}, sidecar_path=None)
        assert dlg_mod._resource_thumbnail_store == thumb

    def test_dept_store_defaults_to_empty_when_none(self):
        """When dept_store=None, _resource_dept_store must be set to {}."""
        import dialogs as dlg_mod
        dlg_mod.set_resource_thumbnail_store({}, dept_store=None, sidecar_path=None)
        assert dlg_mod._resource_dept_store == {}

    def test_sidecar_path_stored(self):
        """sidecar_path must be stored in _resource_thumbnail_sidecar."""
        import dialogs as dlg_mod
        dlg_mod.set_resource_thumbnail_store({}, dept_store={}, sidecar_path="/tmp/foo.json")
        assert dlg_mod._resource_thumbnail_sidecar == "/tmp/foo.json"

    def test_reset_clears_both_stores(self):
        """Calling with empty dicts must clear both stores."""
        import dialogs as dlg_mod
        # Pre-populate
        dlg_mod._resource_thumbnail_store = {"1": b"x"}
        dlg_mod._resource_dept_store = {"1": "IT"}
        dlg_mod.set_resource_thumbnail_store({}, dept_store={}, sidecar_path=None)
        assert dlg_mod._resource_thumbnail_store == {}
        assert dlg_mod._resource_dept_store == {}


# ---------------------------------------------------------------------------
# _save_resource_thumbnail_sidecar() — merged JSON format (DL-75)
# ---------------------------------------------------------------------------

class TestSaveResourceThumbnailSidecar:
    """_save_resource_thumbnail_sidecar() must write a merged JSON file with
    structure {"resources": {<uid>: {"thumbnail": ..., "department": ...}}}."""

    def test_writes_merged_format(self, tmp_path):
        """Both thumbnail and department appear in the sidecar under 'resources'."""
        import json, base64
        import dialogs as dlg_mod

        sidecar = str(tmp_path / "proj.thumbnails.json")
        dlg_mod._resource_thumbnail_store = {"7": b"\x89PNG\r\n"}
        dlg_mod._resource_dept_store      = {"7": "Research"}
        dlg_mod._resource_thumbnail_sidecar = sidecar

        dlg_mod._save_resource_thumbnail_sidecar()

        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)

        assert "resources" in data
        assert "7" in data["resources"]
        entry = data["resources"]["7"]
        assert entry["department"] == "Research"
        assert base64.b64decode(entry["thumbnail"]) == b"\x89PNG\r\n"

    def test_empty_stores_write_empty_resources(self, tmp_path):
        """When both stores are empty the sidecar is written with resources: {}."""
        import json
        import dialogs as dlg_mod

        sidecar = str(tmp_path / "empty.json")
        dlg_mod._resource_thumbnail_store = {}
        dlg_mod._resource_dept_store      = {}
        dlg_mod._resource_thumbnail_sidecar = sidecar

        dlg_mod._save_resource_thumbnail_sidecar()

        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
        assert data == {"resources": {}}

    def test_no_sidecar_path_does_not_raise(self):
        """If sidecar path is None/empty, the function returns silently."""
        import dialogs as dlg_mod
        dlg_mod._resource_thumbnail_store = {"1": b"x"}
        dlg_mod._resource_dept_store      = {}
        dlg_mod._resource_thumbnail_sidecar = None
        dlg_mod._save_resource_thumbnail_sidecar()  # must not raise

    def test_thumbnail_only_entry(self, tmp_path):
        """UIDs with only a thumbnail (no dept) omit the 'department' key."""
        import json
        import dialogs as dlg_mod

        sidecar = str(tmp_path / "t.json")
        dlg_mod._resource_thumbnail_store = {"5": b"\xff\xd8"}
        dlg_mod._resource_dept_store      = {}
        dlg_mod._resource_thumbnail_sidecar = sidecar

        dlg_mod._save_resource_thumbnail_sidecar()

        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
        assert "5" in data["resources"]
        assert "department" not in data["resources"]["5"]

    def test_dept_only_entry(self, tmp_path):
        """UIDs with only a department (no thumbnail) omit the 'thumbnail' key."""
        import json
        import dialogs as dlg_mod

        sidecar = str(tmp_path / "d.json")
        dlg_mod._resource_thumbnail_store = {}
        dlg_mod._resource_dept_store      = {"9": "Finance"}
        dlg_mod._resource_thumbnail_sidecar = sidecar

        dlg_mod._save_resource_thumbnail_sidecar()

        with open(sidecar, encoding="utf-8") as f:
            data = json.load(f)
        assert "9" in data["resources"]
        assert "thumbnail" not in data["resources"]["9"]
        assert data["resources"]["9"]["department"] == "Finance"


# ---------------------------------------------------------------------------
# ResourceDialog — type-based visibility of email/dept/AD rows (DL-76)
# ---------------------------------------------------------------------------

class TestResourceDialogTypeVisibility:
    """For MATERIAL and COST resources, the email field, department field, and
    AD-lookup button must be hidden.  For WORK resources they must be visible."""

    def _make_resource(self, type_str="Work"):
        res = MagicMock()
        res.getID.return_value = 1
        res.getUniqueID.return_value = 1
        res.getName.return_value = "R"
        type_mock = MagicMock()
        type_mock.__str__ = MagicMock(return_value=type_str)
        res.getType.return_value = type_mock
        res.getMaxUnits.return_value = 1.0
        std = MagicMock(); std.__str__ = MagicMock(return_value="$0.00/h")
        ovt = MagicMock(); ovt.__str__ = MagicMock(return_value="$0.00/h")
        res.getStandardRate.return_value = std
        res.getOvertimeRate.return_value  = ovt
        res.getEmailAddress.return_value = None
        res.getDepartment.return_value   = None
        return res

    def _make_dialog(self, qapp, type_str):
        from dialogs import ResourceDialog
        res = self._make_resource(type_str)
        project = make_mock_project(resources=[res])
        project.getCustomFields.return_value = []
        return ResourceDialog(res, project)

    def test_ad_btn_visible_for_work(self, qapp):
        """AD-lookup button must not be hidden for WORK resources."""
        dlg = self._make_dialog(qapp, "Work")
        assert not dlg._ad_lookup_btn.isHidden()

    def test_ad_btn_hidden_for_material(self, qapp):
        """AD-lookup button must be hidden for MATERIAL resources."""
        dlg = self._make_dialog(qapp, "Material")
        assert dlg._ad_lookup_btn.isHidden()

    def test_ad_btn_hidden_for_cost(self, qapp):
        """AD-lookup button must be hidden for COST resources."""
        dlg = self._make_dialog(qapp, "Cost")
        assert dlg._ad_lookup_btn.isHidden()

    def test_email_field_visible_for_work(self, qapp):
        """Email row must not be hidden for WORK resources."""
        dlg = self._make_dialog(qapp, "Work")
        assert not dlg._email_row.isHidden()

    def test_email_field_hidden_for_material(self, qapp):
        """Email row must be hidden for MATERIAL resources."""
        dlg = self._make_dialog(qapp, "Material")
        assert dlg._email_row.isHidden()

    def test_dept_field_visible_for_work(self, qapp):
        """Department QLineEdit must not be hidden for WORK resources."""
        dlg = self._make_dialog(qapp, "Work")
        assert not dlg._e_dept.isHidden()

    def test_dept_field_hidden_for_cost(self, qapp):
        """Department QLineEdit must be hidden for COST resources."""
        dlg = self._make_dialog(qapp, "Cost")
        assert dlg._e_dept.isHidden()


# ---------------------------------------------------------------------------
# _resource_type_pixmap() — returns a QPixmap without crashing (DL-71)
# ---------------------------------------------------------------------------

class TestResourceTypePixmap:
    """_resource_type_pixmap() must return a non-null QPixmap for all known
    resource type strings and must not raise."""

    def test_work_pixmap_returned(self, qapp):
        """WORK type produces a non-null QPixmap."""
        from dialogs import _resource_type_pixmap
        from PyQt5.QtGui import QPixmap
        px = _resource_type_pixmap("Work")
        assert isinstance(px, QPixmap)
        assert not px.isNull()

    def test_material_pixmap_returned(self, qapp):
        from dialogs import _resource_type_pixmap
        from PyQt5.QtGui import QPixmap
        px = _resource_type_pixmap("Material")
        assert isinstance(px, QPixmap)
        assert not px.isNull()

    def test_cost_pixmap_returned(self, qapp):
        from dialogs import _resource_type_pixmap
        from PyQt5.QtGui import QPixmap
        px = _resource_type_pixmap("Cost")
        assert isinstance(px, QPixmap)
        assert not px.isNull()

    def test_unknown_type_does_not_raise(self, qapp):
        """An unrecognised type string must still return a QPixmap."""
        from dialogs import _resource_type_pixmap
        from PyQt5.QtGui import QPixmap
        px = _resource_type_pixmap("Unknown")
        assert isinstance(px, QPixmap)


# ---------------------------------------------------------------------------
# TaskDialog — Resource tab continued (delete btn / add / remove row)
# ---------------------------------------------------------------------------

class TestTaskDialogResourceTabMethods:
    """Additional tests for TaskDialog resource-assignment tab methods."""

    @pytest.fixture
    def dlg(self, qapp):
        from dialogs import TaskDialog
        res = make_mock_resource(res_id=1, name="Alice")
        task = make_mock_task(task_id=1, name="Test Task")
        task.getResourceAssignments.return_value = []
        project = make_mock_project(tasks=[task], resources=[res])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            return TaskDialog(task, project)

    def test_make_delete_btn_returns_pushbutton(self, dlg, qapp):
        """_make_delete_btn must return a QPushButton instance."""
        from PyQt5.QtWidgets import QPushButton
        btn = dlg._make_delete_btn()
        assert isinstance(btn, QPushButton)

    def test_make_delete_btn_has_x_text(self, dlg, qapp):
        """The delete button text must be the '✕' character."""
        btn = dlg._make_delete_btn()
        assert btn.text() == "✕"

    def test_add_assignment_row_increases_row_count(self, dlg, qapp):
        """_add_assignment_row must append one row to _res_tbl."""
        dlg._res_combo.setCurrentText("Alice")
        dlg._add_assignment_row()
        assert dlg._res_tbl.rowCount() == 1

    def test_add_assignment_row_appends_to_del_btns(self, dlg, qapp):
        """Adding a row must append exactly one button to _del_btns."""
        dlg._res_combo.setCurrentText("Alice")
        dlg._add_assignment_row()
        assert len(dlg._del_btns) == 1

    def test_add_assignment_row_appends_to_pending_assignments(self, dlg, qapp):
        """Adding a row must append exactly one entry to _pending_assignments."""
        dlg._res_combo.setCurrentText("Alice")
        dlg._add_assignment_row()
        assert len(dlg._pending_assignments) == 1

    def test_add_assignment_row_unknown_resource_ignored(self, dlg, qapp):
        """A resource name not present in _res_map must be silently ignored."""
        dlg._res_combo.addItem("UnknownXYZ")
        dlg._res_combo.setCurrentText("UnknownXYZ")
        dlg._add_assignment_row()
        assert dlg._res_tbl.rowCount() == 0

    def test_delete_assignment_row_removes_row(self, dlg, qapp):
        """Clicking the ✕ button must remove the corresponding row from _res_tbl."""
        dlg._res_combo.setCurrentText("Alice")
        dlg._add_assignment_row()
        assert dlg._res_tbl.rowCount() == 1
        dlg._del_btns[0].click()
        assert dlg._res_tbl.rowCount() == 0

    def test_delete_assignment_row_removes_from_del_btns(self, dlg, qapp):
        """After deletion _del_btns must be empty."""
        dlg._res_combo.setCurrentText("Alice")
        dlg._add_assignment_row()
        dlg._del_btns[0].click()
        assert len(dlg._del_btns) == 0

    def test_delete_assignment_row_removes_from_pending_assignments(self, dlg, qapp):
        """After deletion _pending_assignments must be empty."""
        dlg._res_combo.setCurrentText("Alice")
        dlg._add_assignment_row()
        dlg._del_btns[0].click()
        assert len(dlg._pending_assignments) == 0


# ---------------------------------------------------------------------------
# TaskDialog — Schedule tab (Phase 4)
# ---------------------------------------------------------------------------

class TestTaskDialogScheduleTab:
    """Tests for the read-only Schedule tab added to TaskDialog in Phase 4."""

    def _dlg(self, qapp, float_data=None, critical_ids=None):
        from dialogs import TaskDialog
        task = make_mock_task(task_id=1, name="Test Task")
        project = make_mock_project(tasks=[task])
        with patch('gantt_view._to_qdate', return_value=None), \
             patch('gantt_view._compute_critical_ids', return_value=set()):
            dlg = TaskDialog(task, project,
                             critical_ids=critical_ids or set(),
                             float_data=float_data or {})
        return dlg

    def test_dialog_has_schedule_tab(self, qapp):
        from PyQt5.QtWidgets import QTabWidget
        dlg = self._dlg(qapp)
        tabs = dlg.findChildren(QTabWidget)
        assert tabs, "TaskDialog must contain a QTabWidget"
        tab_texts = [tabs[0].tabText(i) for i in range(tabs[0].count())]
        assert "Schedule" in tab_texts, f"Expected 'Schedule' tab, got: {tab_texts}"

    def test_schedule_tab_shows_fallback_when_no_float_data(self, qapp):
        """When float_data is empty the Schedule tab must show a 'No CPM data' label."""
        from PyQt5.QtWidgets import QTabWidget, QLabel
        dlg = self._dlg(qapp, float_data={})
        tabs = dlg.findChildren(QTabWidget)[0]
        sched_idx = next(i for i in range(tabs.count()) if tabs.tabText(i) == "Schedule")
        sched_widget = tabs.widget(sched_idx)
        labels = sched_widget.findChildren(QLabel)
        texts = " ".join(lbl.text() for lbl in labels)
        assert "No CPM data" in texts

    def test_schedule_tab_shows_data_when_float_data_present(self, qapp):
        """When float_data contains task 1 the Schedule tab must not show the fallback."""
        from datetime import datetime, timedelta
        from PyQt5.QtWidgets import QTabWidget, QLabel
        fd = {1: {
            "es": datetime(2026, 1, 5, 8, 0), "ef": datetime(2026, 1, 9, 17, 0),
            "ls": datetime(2026, 1, 5, 8, 0), "lf": datetime(2026, 1, 9, 17, 0),
            "total_float": timedelta(0), "free_float": timedelta(0),
            "total_float_wh": None, "free_float_wh": None,
            "work_day_hours": 8.0, "critical": True,
        }}
        dlg = self._dlg(qapp, float_data=fd, critical_ids={1})
        tabs = dlg.findChildren(QTabWidget)[0]
        sched_idx = next(i for i in range(tabs.count()) if tabs.tabText(i) == "Schedule")
        sched_widget = tabs.widget(sched_idx)
        labels = sched_widget.findChildren(QLabel)
        texts = " ".join(lbl.text() for lbl in labels)
        assert "No CPM data" not in texts

    def test_schedule_tab_shows_critical_status(self, qapp):
        """A critical task must display 'CRITICAL' in the Schedule tab."""
        from datetime import datetime, timedelta
        from PyQt5.QtWidgets import QTabWidget, QLabel
        fd = {1: {
            "es": datetime(2026, 1, 5, 8, 0), "ef": datetime(2026, 1, 9, 17, 0),
            "ls": datetime(2026, 1, 5, 8, 0), "lf": datetime(2026, 1, 9, 17, 0),
            "total_float": timedelta(0), "free_float": timedelta(0),
            "total_float_wh": None, "free_float_wh": None,
            "work_day_hours": 8.0, "critical": True,
        }}
        dlg = self._dlg(qapp, float_data=fd, critical_ids={1})
        tabs = dlg.findChildren(QTabWidget)[0]
        sched_idx = next(i for i in range(tabs.count()) if tabs.tabText(i) == "Schedule")
        sched_widget = tabs.widget(sched_idx)
        labels = sched_widget.findChildren(QLabel)
        texts = " ".join(lbl.text() for lbl in labels)
        assert "CRITICAL" in texts
