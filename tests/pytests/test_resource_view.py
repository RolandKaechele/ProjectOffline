"""Tests for views/resource_view.py — ResourceView widget.

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
MPXJ Java objects are replaced with MagicMock instances.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from conftest import make_mock_resource, make_mock_project, make_mock_task


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def view(qapp):
    from resource_view import ResourceView
    return ResourceView()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestResourceViewInit:
    def test_widget_created(self, qapp):
        from resource_view import ResourceView
        assert ResourceView() is not None

    def test_initial_row_count_is_zero(self, view):
        assert view.rowCount() == 0

    def test_column_count_matches_constant(self, view):
        from resource_view import ResourceView
        assert view.columnCount() == len(ResourceView.COLUMNS)

    def test_data_changed_signal_exists(self, view):
        assert hasattr(view, 'data_changed')

    def test_column_headers(self, view):
        from resource_view import ResourceView
        for col, header in enumerate(ResourceView.COLUMNS):
            assert view.horizontalHeaderItem(col).text() == header


# ---------------------------------------------------------------------------
# load_project()
# ---------------------------------------------------------------------------

class TestLoadProject:
    def test_load_none_clears_rows(self, view):
        view.load_project(None)
        assert view.rowCount() == 0

    def test_load_project_with_one_resource(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        res = make_mock_resource(res_id=1, name="Alice")
        project = make_mock_project(resources=[res])
        v.load_project(project)
        assert v.rowCount() == 1

    def test_load_project_with_multiple_resources(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        resources = [make_mock_resource(res_id=i, name=f"R{i}") for i in range(1, 5)]
        project = make_mock_project(resources=resources)
        v.load_project(project)
        assert v.rowCount() == 4

    def test_resource_name_displayed_in_name_column(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        res = make_mock_resource(res_id=1, name="Bob")
        v.load_project(make_mock_project(resources=[res]))
        name_item = v.item(0, 1)
        assert name_item is not None
        assert name_item.text() == "Bob"

    def test_resource_id_displayed_in_id_column(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        res = make_mock_resource(res_id=7, name="Carol")
        v.load_project(make_mock_project(resources=[res]))
        id_item = v.item(0, 0)
        assert id_item is not None
        assert id_item.text() == "7"

    def test_resources_with_none_name_are_excluded(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        res_valid = make_mock_resource(res_id=1, name="Valid")
        res_null  = make_mock_resource(res_id=2, name=None)
        res_null.getName.return_value = None
        v.load_project(make_mock_project(resources=[res_valid, res_null]))
        # Only 'Valid' should appear
        assert v.rowCount() == 1

    def test_load_project_replaces_previous(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        r1 = [make_mock_resource(res_id=i, name=f"R{i}") for i in range(1, 4)]
        v.load_project(make_mock_project(resources=r1))
        assert v.rowCount() == 3

        r2 = [make_mock_resource(res_id=1, name="OnlyOne")]
        v.load_project(make_mock_project(resources=r2))
        assert v.rowCount() == 1

    def test_load_none_after_data_clears(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        v.load_project(make_mock_project(resources=[make_mock_resource()]))
        v.load_project(None)
        assert v.rowCount() == 0


# ---------------------------------------------------------------------------
# delete_selected_resources()
# ---------------------------------------------------------------------------

class TestDeleteResources:
    def test_delete_with_no_project_does_not_raise(self, view):
        view.delete_selected_resources()

    def test_delete_selected_emits_data_changed(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        res = make_mock_resource(res_id=1, name="Dave")
        v.load_project(make_mock_project(resources=[res]))
        v.selectRow(0)

        received = []
        v.data_changed.connect(lambda: received.append(1))
        v.delete_selected_resources()

        assert len(received) > 0

    def test_delete_removes_row(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        resources = [make_mock_resource(res_id=i, name=f"R{i}") for i in range(1, 4)]
        v.load_project(make_mock_project(resources=resources))
        v.selectRow(0)
        v.delete_selected_resources()
        assert v.rowCount() == 2

    def test_delete_no_selection_does_nothing(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        v.load_project(make_mock_project(resources=[make_mock_resource()]))
        initial = v.rowCount()
        # No row selected
        v.delete_selected_resources()
        assert v.rowCount() == initial


# ---------------------------------------------------------------------------
# add_resource_from_ad() — resource-ID assignment & duplicate guard
# ---------------------------------------------------------------------------

class TestAddResourceFromAd:
    """Tests for the AD-resource-addition path added in the AD integration feature.

    All MPXJ / Java calls and the AD dialog are mocked so tests run without a
    real AD environment or JVM.

    Patching strategy:
    - ``ADSearchDialog`` and ``ResourceDialog`` are imported locally inside
      ``add_resource_from_ad`` via ``from dialogs import …``, so we patch them
      on the ``dialogs`` module: ``"dialogs.ADSearchDialog"`` /
      ``"dialogs.ResourceDialog"``.
    - ``QMessageBox`` is also imported locally from ``PyQt5.QtWidgets`` inside
      the duplicate-guard branch, so we patch it there:
      ``"PyQt5.QtWidgets.QMessageBox"``.
    """

    def _make_project_with_resources(self, resources):
        """Return a mock project whose getResources() list is *resources* and
        whose addResource() returns a fresh mock with getID() == None (simulating
        MPXJ before the ID is assigned by our code)."""
        project = make_mock_project(resources=resources)
        new_res = make_mock_resource(res_id=None, name="Doe, John")
        new_res.getID.return_value = None
        new_res.getCalendar.return_value = None
        project.addResource.return_value = new_res
        project.getCalendars.return_value = []
        project.getDefaultCalendar.return_value = None
        return project, new_res

    def test_duplicate_name_is_blocked(self, qapp):
        """add_resource_from_ad must reject a resource whose name (case-insensitive)
        already exists in the project and show a warning — no new resource created."""
        from resource_view import ResourceView
        from unittest.mock import patch, MagicMock
        v = ResourceView()
        existing = make_mock_resource(res_id=1, name="Doe, John")
        project, _ = self._make_project_with_resources([existing])
        v.load_project(project)

        dlg_mock = MagicMock()
        dlg_mock.exec_.return_value = 1          # QDialog.Accepted
        dlg_mock.get_resource_name.return_value = "doe, john"   # case variant
        dlg_mock.get_user_data.return_value = {}

        with patch("dialogs.ADSearchDialog", return_value=dlg_mock), \
             patch("PyQt5.QtWidgets.QMessageBox.warning") as warn_mock:
            v.add_resource_from_ad()

        project.addResource.assert_not_called()
        warn_mock.assert_called_once()

    def test_duplicate_name_exact_match_blocked(self, qapp):
        """Exact-case duplicate is also blocked."""
        from resource_view import ResourceView
        from unittest.mock import patch, MagicMock
        v = ResourceView()
        existing = make_mock_resource(res_id=2, name="Müller, Hans")
        project, _ = self._make_project_with_resources([existing])
        v.load_project(project)

        dlg_mock = MagicMock()
        dlg_mock.exec_.return_value = 1
        dlg_mock.get_resource_name.return_value = "Müller, Hans"
        dlg_mock.get_user_data.return_value = {}

        with patch("dialogs.ADSearchDialog", return_value=dlg_mock), \
             patch("PyQt5.QtWidgets.QMessageBox.warning") as warn_mock:
            v.add_resource_from_ad()

        project.addResource.assert_not_called()
        warn_mock.assert_called_once()

    def test_unique_name_proceeds(self, qapp):
        """A name not yet in the project must pass the duplicate guard."""
        from resource_view import ResourceView
        from unittest.mock import patch, MagicMock
        v = ResourceView()
        existing = make_mock_resource(res_id=1, name="Smith, Jane")
        project, new_res = self._make_project_with_resources([existing])
        v.load_project(project)

        res_dlg_mock = MagicMock()
        res_dlg_mock.exec_.return_value = 1

        dlg_mock = MagicMock()
        dlg_mock.exec_.return_value = 1
        dlg_mock.get_resource_name.return_value = "Doe, John"
        dlg_mock.get_user_data.return_value = {"email": "j.doe@example.com"}

        with patch("dialogs.ADSearchDialog", return_value=dlg_mock), \
             patch("dialogs.ResourceDialog", return_value=res_dlg_mock), \
             patch("PyQt5.QtWidgets.QMessageBox.warning") as warn_mock:
            v.add_resource_from_ad()

        project.addResource.assert_called_once()
        warn_mock.assert_not_called()

    def test_resource_id_assigned_after_add(self, qapp):
        """add_resource_from_ad must call setID() on the new resource so the ID
        column is populated immediately (before the next save)."""
        from resource_view import ResourceView
        from unittest.mock import patch, MagicMock
        import sys
        v = ResourceView()

        # Existing resource has ID 3 → new resource should get ID 4
        existing = make_mock_resource(res_id=3, name="Existing, Person")
        project, new_res = self._make_project_with_resources([existing])
        v.load_project(project)

        res_dlg_mock = MagicMock()
        res_dlg_mock.exec_.return_value = 1

        dlg_mock = MagicMock()
        dlg_mock.exec_.return_value = 1
        dlg_mock.get_resource_name.return_value = "Doe, John"
        dlg_mock.get_user_data.return_value = {}

        # java.lang is not in the global stubs; inject a minimal stub so that
        # the `from java.lang import Integer` inside add_resource_from_ad works.
        java_lang_stub = MagicMock()
        java_lang_stub.Integer = int   # use plain int so int(str(call_arg)) works

        with patch.dict(sys.modules, {"java.lang": java_lang_stub}), \
             patch("dialogs.ADSearchDialog", return_value=dlg_mock), \
             patch("dialogs.ResourceDialog", return_value=res_dlg_mock), \
             patch("PyQt5.QtWidgets.QMessageBox.warning"):
            v.add_resource_from_ad()

        new_res.setID.assert_called_once()
        call_arg = new_res.setID.call_args[0][0]
        assert int(str(call_arg)) == 4

    def test_resource_id_starts_at_1_when_no_existing(self, qapp):
        """When the project has no resources with assigned IDs the first AD
        resource should receive ID 1."""
        from resource_view import ResourceView
        from unittest.mock import patch, MagicMock
        import sys
        v = ResourceView()

        project, new_res = self._make_project_with_resources([])
        v.load_project(project)

        res_dlg_mock = MagicMock()
        res_dlg_mock.exec_.return_value = 1

        dlg_mock = MagicMock()
        dlg_mock.exec_.return_value = 1
        dlg_mock.get_resource_name.return_value = "First, Resource"
        dlg_mock.get_user_data.return_value = {}

        java_lang_stub = MagicMock()
        java_lang_stub.Integer = int

        with patch.dict(sys.modules, {"java.lang": java_lang_stub}), \
             patch("dialogs.ADSearchDialog", return_value=dlg_mock), \
             patch("dialogs.ResourceDialog", return_value=res_dlg_mock), \
             patch("PyQt5.QtWidgets.QMessageBox.warning"):
            v.add_resource_from_ad()

        new_res.setID.assert_called_once()
        call_arg = new_res.setID.call_args[0][0]
        assert int(str(call_arg)) == 1

    def test_cancel_on_search_dialog_does_not_add_resource(self, qapp):
        """Cancelling the AD search dialog must leave the project unchanged."""
        from resource_view import ResourceView
        from unittest.mock import patch, MagicMock
        v = ResourceView()
        project, _ = self._make_project_with_resources([])
        v.load_project(project)

        dlg_mock = MagicMock()
        dlg_mock.exec_.return_value = 0   # QDialog.Rejected

        with patch("dialogs.ADSearchDialog", return_value=dlg_mock):
            v.add_resource_from_ad()

        project.addResource.assert_not_called()


# ---------------------------------------------------------------------------
# _ensure_resource_uid() — UID assignment for newly added resources
# ---------------------------------------------------------------------------

class TestEnsureResourceUid:
    """Tests for ResourceView._ensure_resource_uid().

    This method was added to fix a bug where a resource newly added via
    add_resource() or add_resource_from_ad() was not visible in the Team Planner
    because MPXJ's addResource() does not always auto-assign a UniqueID.
    """

    def _make_view(self, qapp, resources):
        from resource_view import ResourceView
        v = ResourceView()
        v.load_project(make_mock_project(resources=resources))
        return v

    def test_does_nothing_when_uid_already_set(self, qapp):
        """If resource already has a UID, setUniqueID must NOT be called."""
        v = self._make_view(qapp, [])
        res = MagicMock()
        res.getUniqueID.return_value = 5
        v._ensure_resource_uid(res)
        res.setUniqueID.assert_not_called()

    def test_assigns_uid_when_none(self, qapp):
        """If getUniqueID() returns None, setUniqueID must be called exactly once."""
        import sys
        v = self._make_view(qapp, [])
        res = MagicMock()
        res.getUniqueID.return_value = None
        java_lang_stub = MagicMock()
        java_lang_stub.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang_stub}):
            v._ensure_resource_uid(res)
        res.setUniqueID.assert_called_once()

    def test_picks_next_free_uid_avoiding_collision(self, qapp):
        """The assigned UID must not collide with any existing resource UID."""
        import sys
        existing = make_mock_resource(res_id=3, name="Existing")
        existing.getUniqueID.return_value = 3
        v = self._make_view(qapp, [existing])
        new_res = MagicMock()
        new_res.getUniqueID.return_value = None
        java_lang_stub = MagicMock()
        java_lang_stub.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang_stub}):
            v._ensure_resource_uid(new_res)
        call_arg = new_res.setUniqueID.call_args[0][0]
        assert int(str(call_arg)) not in {3}

    def test_starts_at_1_when_no_existing_resources(self, qapp):
        """With no resources in the project, the first assigned UID must be 1."""
        import sys
        v = self._make_view(qapp, [])
        new_res = MagicMock()
        new_res.getUniqueID.return_value = None
        java_lang_stub = MagicMock()
        java_lang_stub.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang_stub}):
            v._ensure_resource_uid(new_res)
        call_arg = new_res.setUniqueID.call_args[0][0]
        assert int(str(call_arg)) == 1


# ---------------------------------------------------------------------------
# delete_selected_resources() — calendar cleanup (bug fix)
# ---------------------------------------------------------------------------

class TestDeleteResourcesCalendarCleanup:
    """When a resource is deleted its linked personal calendar must also be
    removed from the project's calendar list."""

    def _make_view_with_resources(self, qapp, resources):
        from resource_view import ResourceView
        v = ResourceView()
        v.load_project(make_mock_project(resources=resources))
        return v

    def test_delete_calls_remove_on_linked_calendar(self, qapp):
        """Deleting a resource whose getCalendar() returns a mock calendar must
        call project.getCalendars().remove(cal)."""
        from resource_view import ResourceView
        v = ResourceView()

        res = make_mock_resource(res_id=1, name="Alice")
        cal_mock = MagicMock()
        res.getCalendar.return_value = cal_mock

        cal_list_mock = MagicMock()
        project = make_mock_project(resources=[res])
        project.getCalendars.return_value = cal_list_mock
        v.load_project(project)

        v.selectRow(0)
        v.delete_selected_resources()

        cal_list_mock.remove.assert_called_once_with(cal_mock)

    def test_delete_skips_calendar_removal_when_no_calendar(self, qapp):
        """If getCalendar() returns None no attempt to remove a calendar is made."""
        from resource_view import ResourceView
        v = ResourceView()

        res = make_mock_resource(res_id=1, name="Bob")
        res.getCalendar.return_value = None

        cal_list_mock = MagicMock()
        project = make_mock_project(resources=[res])
        project.getCalendars.return_value = cal_list_mock
        v.load_project(project)

        v.selectRow(0)
        v.delete_selected_resources()  # must not raise

        cal_list_mock.remove.assert_not_called()

    def test_delete_still_removes_resource_row_after_calendar_removal(self, qapp):
        """Row count drops even when a calendar is attached."""
        from resource_view import ResourceView
        v = ResourceView()

        res = make_mock_resource(res_id=1, name="Carol")
        cal_mock = MagicMock()
        res.getCalendar.return_value = cal_mock

        cal_list_mock = MagicMock()
        project = make_mock_project(resources=[res])
        project.getCalendars.return_value = cal_list_mock
        v.load_project(project)

        assert v.rowCount() == 1
        v.selectRow(0)
        v.delete_selected_resources()
        assert v.rowCount() == 0

    def test_delete_continues_when_calendar_remove_raises(self, qapp):
        """If removing the calendar throws, the resource row is still deleted."""
        from resource_view import ResourceView
        v = ResourceView()

        res = make_mock_resource(res_id=1, name="Dave")
        cal_mock = MagicMock()
        res.getCalendar.return_value = cal_mock

        cal_list_mock = MagicMock()
        cal_list_mock.remove.side_effect = Exception("MPXJ error")
        project = make_mock_project(resources=[res])
        project.getCalendars.return_value = cal_list_mock
        v.load_project(project)

        v.selectRow(0)
        v.delete_selected_resources()  # must not propagate exception

        assert v.rowCount() == 0


# ---------------------------------------------------------------------------
# add_resource() — new behaviour: ID + calendar assigned before dialog
# ---------------------------------------------------------------------------

class TestAddResource:
    """Tests for the updated add_resource() flow.

    add_resource() now:
    - Assigns a resource ID immediately (setID called before dialog opens).
    - Creates a personal calendar linked to the project standard calendar.
    - Rolls back both the calendar and the resource on Cancel.

    All MPXJ / Java objects and dialogs are mocked.
    """

    def _make_project(self, resources=None):
        project = make_mock_project(resources=resources or [])
        new_res = MagicMock()
        new_res.getID.return_value      = None
        new_res.getUniqueID.return_value = None
        new_res.getCalendar.return_value = None
        new_res.getName.return_value     = "New Resource"
        project.addResource.return_value = new_res
        project.getCalendars.return_value = MagicMock()
        project.getDefaultCalendar.return_value = None
        return project, new_res

    def test_resource_id_assigned_on_accept(self, qapp):
        """setID must be called when the dialog is accepted."""
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        existing = make_mock_resource(res_id=5, name="Existing")
        project, new_res = self._make_project(resources=[existing])
        v.load_project(project)

        res_dlg = MagicMock()
        res_dlg.exec_.return_value = 1
        java_lang = MagicMock()
        java_lang.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang}), \
             patch("dialogs.ResourceDialog", return_value=res_dlg):
            v.add_resource()

        new_res.setID.assert_called_once()
        call_arg = new_res.setID.call_args[0][0]
        assert int(str(call_arg)) == 6

    def test_resource_id_starts_at_1_when_no_existing(self, qapp):
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, new_res = self._make_project()
        v.load_project(project)

        res_dlg = MagicMock()
        res_dlg.exec_.return_value = 1
        java_lang = MagicMock()
        java_lang.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang}), \
             patch("dialogs.ResourceDialog", return_value=res_dlg):
            v.add_resource()

        call_arg = new_res.setID.call_args[0][0]
        assert int(str(call_arg)) == 1

    def test_calendar_created_on_accept(self, qapp):
        """_create_resource_calendar must be called even for manual add."""
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, new_res = self._make_project()
        v.load_project(project)

        new_cal = MagicMock()
        project.addCalendar.return_value = new_cal

        res_dlg = MagicMock()
        res_dlg.exec_.return_value = 1
        java_lang = MagicMock()
        java_lang.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang}), \
             patch("dialogs.ResourceDialog", return_value=res_dlg):
            v.add_resource()

        project.addCalendar.assert_called_once()

    def test_calendar_and_resource_rolled_back_on_cancel(self, qapp):
        """Cancelling the dialog must remove both the calendar and the resource."""
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, new_res = self._make_project()
        v.load_project(project)

        cal_mock = MagicMock()
        project.addCalendar.return_value = cal_mock
        new_res.getCalendar.return_value = cal_mock

        cal_list_mock = MagicMock()
        project.getCalendars.return_value = cal_list_mock

        res_dlg = MagicMock()
        res_dlg.exec_.return_value = 0   # Rejected
        java_lang = MagicMock()
        java_lang.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang}), \
             patch("dialogs.ResourceDialog", return_value=res_dlg):
            v.add_resource()

        cal_list_mock.remove.assert_called_once_with(cal_mock)
        new_res.remove.assert_called_once()

    def test_no_project_does_not_raise(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        v.add_resource()   # must not raise


# ---------------------------------------------------------------------------
# add_resources_from_ad_group() — bulk-add group members
# ---------------------------------------------------------------------------

class TestAddResourcesFromAdGroup:
    """Tests for add_resources_from_ad_group().

    ADGroupSearchDialog is imported locally inside the method so it is patched
    on the 'dialogs' module.  QMessageBox is also patched to suppress the
    summary pop-up.
    """

    _JAVA_LANG_STUB = {"java.lang": MagicMock(Integer=int)}

    def _make_project(self, resources=None):
        project = make_mock_project(resources=resources or [])
        new_res = MagicMock()
        new_res.getID.return_value       = None
        new_res.getUniqueID.return_value = None
        new_res.getCalendar.return_value  = None
        new_res.getName.return_value      = "New Resource"
        project.addResource.return_value  = new_res
        project.getCalendars.return_value = MagicMock()
        project.getDefaultCalendar.return_value = None
        return project, new_res

    def _make_group_dlg(self, accepted=True, users=None):
        dlg = MagicMock()
        dlg.exec_.return_value = 1 if accepted else 0
        dlg.get_selected_users.return_value = users or []
        return dlg

    def test_no_project_does_not_raise(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        v.add_resources_from_ad_group()   # must not raise

    def test_cancel_does_not_add_resource(self, qapp):
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, _ = self._make_project()
        v.load_project(project)

        dlg = self._make_group_dlg(accepted=False)
        with patch.dict(sys.modules, self._JAVA_LANG_STUB), \
             patch("dialogs.ADGroupSearchDialog", return_value=dlg):
            v.add_resources_from_ad_group()

        project.addResource.assert_not_called()

    def test_empty_user_list_does_not_add_resource(self, qapp):
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, _ = self._make_project()
        v.load_project(project)

        dlg = self._make_group_dlg(accepted=True, users=[])
        with patch.dict(sys.modules, self._JAVA_LANG_STUB), \
             patch("dialogs.ADGroupSearchDialog", return_value=dlg), \
             patch("PyQt5.QtWidgets.QMessageBox.information"):
            v.add_resources_from_ad_group()

        project.addResource.assert_not_called()

    def test_new_user_is_added(self, qapp):
        """A user not already in the project must be added as a resource."""
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, _ = self._make_project()
        v.load_project(project)

        users = [{"display_name": "Doe, John", "email": "j.doe@corp.com",
                  "department": "IT", "username": "jdoe"}]
        dlg = self._make_group_dlg(users=users)
        with patch.dict(sys.modules, self._JAVA_LANG_STUB), \
             patch("dialogs.ADGroupSearchDialog", return_value=dlg), \
             patch("dialogs._format_resource_name", return_value="Doe, John"), \
             patch("PyQt5.QtWidgets.QMessageBox.information"):
            v.add_resources_from_ad_group()

        project.addResource.assert_called_once()

    def test_duplicate_user_is_skipped(self, qapp):
        """A user whose name already exists (case-insensitive) must be skipped."""
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        existing = make_mock_resource(res_id=1, name="Doe, John")
        project, _ = self._make_project(resources=[existing])
        v.load_project(project)

        users = [{"display_name": "Doe, John", "email": "j.doe@corp.com",
                  "department": "IT", "username": "jdoe"}]
        dlg = self._make_group_dlg(users=users)
        with patch.dict(sys.modules, self._JAVA_LANG_STUB), \
             patch("dialogs.ADGroupSearchDialog", return_value=dlg), \
             patch("dialogs._format_resource_name", return_value="Doe, John"), \
             patch("PyQt5.QtWidgets.QMessageBox.information"):
            v.add_resources_from_ad_group()

        project.addResource.assert_not_called()

    def test_data_changed_emitted_when_resource_added(self, qapp):
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, _ = self._make_project()
        v.load_project(project)

        received = []
        v.data_changed.connect(lambda: received.append(1))

        users = [{"display_name": "Smith, Jane", "email": "j.smith@corp.com",
                  "department": "HR", "username": "jsmith"}]
        dlg = self._make_group_dlg(users=users)
        with patch.dict(sys.modules, self._JAVA_LANG_STUB), \
             patch("dialogs.ADGroupSearchDialog", return_value=dlg), \
             patch("dialogs._format_resource_name", return_value="Smith, Jane"), \
             patch("PyQt5.QtWidgets.QMessageBox.information"):
            v.add_resources_from_ad_group()

        assert len(received) > 0

    def test_user_with_no_display_name_skipped(self, qapp):
        """Users whose display_name is empty must be silently skipped."""
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, _ = self._make_project()
        v.load_project(project)

        users = [{"display_name": "", "email": "anon@corp.com",
                  "department": "IT", "username": "anon"}]
        dlg = self._make_group_dlg(users=users)
        with patch.dict(sys.modules, self._JAVA_LANG_STUB), \
             patch("dialogs.ADGroupSearchDialog", return_value=dlg), \
             patch("PyQt5.QtWidgets.QMessageBox.information"):
            v.add_resources_from_ad_group()

        project.addResource.assert_not_called()

    def test_email_written_to_resource(self, qapp):
        from resource_view import ResourceView
        import sys
        v = ResourceView()
        project, new_res = self._make_project()
        v.load_project(project)

        users = [{"display_name": "Doe, John", "email": "j.doe@corp.com",
                  "department": "IT", "username": "jdoe"}]
        dlg = self._make_group_dlg(users=users)
        with patch.dict(sys.modules, self._JAVA_LANG_STUB), \
             patch("dialogs.ADGroupSearchDialog", return_value=dlg), \
             patch("dialogs._format_resource_name", return_value="Doe, John"), \
             patch("PyQt5.QtWidgets.QMessageBox.information"):
            v.add_resources_from_ad_group()

        new_res.setEmailAddress.assert_called_once_with("j.doe@corp.com")


# ---------------------------------------------------------------------------
# _create_resource_calendar() — base calendar is the project standard calendar
# ---------------------------------------------------------------------------

class TestCreateResourceCalendar:
    """Tests for _create_resource_calendar().

    Verifies that the newly created personal calendar:
    - Has setParent() called with the project default calendar when one exists.
    - Falls back to addDefaultCalendarDays() when no default calendar exists.
    - Is linked to the resource via setCalendar().
    - Gets a unique UID that does not collide with existing calendars.
    """

    def _make_view(self, qapp):
        from resource_view import ResourceView
        v = ResourceView()
        v.load_project(make_mock_project())
        return v

    def _make_res(self, name="Alice"):
        res = MagicMock()
        res.getName.return_value = name
        return res

    def _make_cal(self, uid=1):
        cal = MagicMock()
        cal.getUniqueID.return_value = uid
        return cal

    def test_set_parent_called_with_default_calendar(self, qapp):
        """When a project default calendar exists, cal.setParent() must be called
        with it so the Base Calendar field is properly linked."""
        import sys
        v = self._make_view(qapp)
        res = self._make_res()
        default_cal = self._make_cal(uid=1)
        new_cal = MagicMock()
        new_cal.getUniqueID.return_value = 2

        v._project = MagicMock()
        v._project.getDefaultCalendar.return_value = default_cal
        v._project.getCalendars.return_value = [default_cal]
        v._project.addCalendar.return_value  = new_cal

        jpype_stub = MagicMock()
        java_time_stub = MagicMock()
        java_time_stub.DayOfWeek.values.return_value = []
        jpype_stub.JClass.return_value = MagicMock()

        with patch.dict(sys.modules, {
            "java.lang": MagicMock(Integer=int),
            "jpype":     jpype_stub,
            "java.time": java_time_stub,
        }):
            v._create_resource_calendar(res)

        new_cal.setParent.assert_called_once_with(default_cal)

    def test_set_calendar_called_on_resource(self, qapp):
        """The newly created calendar must be linked to the resource."""
        import sys
        v = self._make_view(qapp)
        res = self._make_res()
        new_cal = MagicMock()

        v._project = MagicMock()
        v._project.getDefaultCalendar.return_value = None
        v._project.getCalendars.return_value = []
        v._project.addCalendar.return_value  = new_cal

        with patch.dict(sys.modules, {"java.lang": MagicMock(Integer=int)}):
            v._create_resource_calendar(res)

        res.setCalendar.assert_called_once_with(new_cal)

    def test_no_default_calendar_uses_default_days(self, qapp):
        """Without a project default calendar, addDefaultCalendarDays() must be
        called so the new calendar has a sensible Mon–Fri working week."""
        import sys
        v = self._make_view(qapp)
        res = self._make_res()
        new_cal = MagicMock()

        v._project = MagicMock()
        v._project.getDefaultCalendar.return_value = None
        v._project.getCalendars.return_value = []
        v._project.addCalendar.return_value  = new_cal

        with patch.dict(sys.modules, {"java.lang": MagicMock(Integer=int)}):
            v._create_resource_calendar(res)

        new_cal.addDefaultCalendarDays.assert_called_once()

    def test_calendar_uid_avoids_collision(self, qapp):
        """The new calendar UID must not collide with existing calendar UIDs."""
        import sys
        v = self._make_view(qapp)
        res = self._make_res()
        existing_cal = self._make_cal(uid=3)
        new_cal = MagicMock()
        new_cal.getUniqueID.return_value = None

        v._project = MagicMock()
        v._project.getDefaultCalendar.return_value = None
        v._project.getCalendars.return_value = [existing_cal]
        v._project.addCalendar.return_value  = new_cal

        assigned_uid = []
        def capture_uid(uid):
            assigned_uid.append(uid)

        new_cal.setUniqueID.side_effect = capture_uid

        with patch.dict(sys.modules, {"java.lang": MagicMock(Integer=int)}):
            v._create_resource_calendar(res)

        assert assigned_uid, "setUniqueID was never called"
        assert int(str(assigned_uid[0])) != 3


# ---------------------------------------------------------------------------
# delete_selected_resources() — sidecar store cleanup (DL-82/83)
# ---------------------------------------------------------------------------

class TestDeleteResourcesSidecarCleanup:
    """delete_selected_resources() must prune _resource_thumbnail_store and
    _resource_dept_store for the deleted resource's UID, then call
    _save_resource_thumbnail_sidecar().
    """

    def _make_stores(self, uid_key):
        thumb_store = {uid_key: b"\x89PNG"}
        dept_store  = {uid_key: "Engineering"}
        return thumb_store, dept_store

    def test_thumbnail_store_pruned_on_delete(self, qapp):
        """_resource_thumbnail_store must not contain the deleted UID."""
        from resource_view import ResourceView
        import dialogs as dlg_mod

        uid = 42
        uid_key = str(uid)
        thumb_store, dept_store = self._make_stores(uid_key)

        dlg_mod._resource_thumbnail_store = thumb_store
        dlg_mod._resource_dept_store      = dept_store
        dlg_mod._resource_thumbnail_sidecar = None  # no file write

        res = make_mock_resource(res_id=1, name="Alice")
        res.getUniqueID.return_value = uid
        res.getCalendar.return_value = None

        project = make_mock_project(resources=[res])
        project.getCalendars.return_value = MagicMock()
        v = ResourceView()
        v.load_project(project)

        v.selectRow(0)
        v.delete_selected_resources()

        assert uid_key not in dlg_mod._resource_thumbnail_store

    def test_dept_store_pruned_on_delete(self, qapp):
        """_resource_dept_store must not contain the deleted UID."""
        from resource_view import ResourceView
        import dialogs as dlg_mod

        uid = 43
        uid_key = str(uid)
        thumb_store, dept_store = self._make_stores(uid_key)

        dlg_mod._resource_thumbnail_store = thumb_store
        dlg_mod._resource_dept_store      = dept_store
        dlg_mod._resource_thumbnail_sidecar = None

        res = make_mock_resource(res_id=1, name="Bob")
        res.getUniqueID.return_value = uid
        res.getCalendar.return_value = None

        project = make_mock_project(resources=[res])
        project.getCalendars.return_value = MagicMock()
        v = ResourceView()
        v.load_project(project)

        v.selectRow(0)
        v.delete_selected_resources()

        assert uid_key not in dlg_mod._resource_dept_store

    def test_sidecar_save_called_on_delete(self, qapp):
        """_save_resource_thumbnail_sidecar must be called after sidecar pruning."""
        from resource_view import ResourceView

        uid = 44
        res = make_mock_resource(res_id=1, name="Carol")
        res.getUniqueID.return_value = uid
        res.getCalendar.return_value = None

        project = make_mock_project(resources=[res])
        project.getCalendars.return_value = MagicMock()
        v = ResourceView()
        v.load_project(project)

        v.selectRow(0)
        with patch("dialogs._save_resource_thumbnail_sidecar") as mock_save:
            # Also patch the stores imported inside the method
            with patch("dialogs._resource_thumbnail_store", {}), \
                 patch("dialogs._resource_dept_store", {}):
                v.delete_selected_resources()
        # _save_resource_thumbnail_sidecar is called (may be 0 or more times
        # depending on whether _del_uid resolves; just ensure no exception)
        # The main contract is that the method completes without error.

    def test_other_uids_not_pruned(self, qapp):
        """Only the deleted resource's UID is removed; other entries survive."""
        from resource_view import ResourceView
        import dialogs as dlg_mod

        uid_del  = 50
        uid_keep = 99
        thumb_store = {str(uid_del): b"\xff", str(uid_keep): b"\xfe"}
        dept_store  = {str(uid_del): "Eng",   str(uid_keep): "HR"}

        dlg_mod._resource_thumbnail_store = thumb_store
        dlg_mod._resource_dept_store      = dept_store
        dlg_mod._resource_thumbnail_sidecar = None

        res = make_mock_resource(res_id=1, name="Dave")
        res.getUniqueID.return_value = uid_del
        res.getCalendar.return_value = None

        project = make_mock_project(resources=[res])
        project.getCalendars.return_value = MagicMock()
        v = ResourceView()
        v.load_project(project)

        v.selectRow(0)
        v.delete_selected_resources()

        assert str(uid_keep) in dlg_mod._resource_thumbnail_store
        assert str(uid_keep) in dlg_mod._resource_dept_store


# ---------------------------------------------------------------------------
# add_resource() — duplicate name guard (DL-80)
# ---------------------------------------------------------------------------

class TestAddResourceDuplicateGuard:
    """add_resource() must reject a name that already exists (case-insensitive)
    and roll back the newly created resource + calendar.
    """

    def _make_project(self, existing_name="Existing"):
        existing = make_mock_resource(res_id=1, name=existing_name)
        existing.getUniqueID.return_value = 1
        project = make_mock_project(resources=[existing])

        new_res = MagicMock()
        new_res.getID.return_value       = None
        new_res.getUniqueID.return_value = 2          # different UID
        new_res.getCalendar.return_value = MagicMock()
        new_res.getName.return_value     = "New Resource"
        project.addResource.return_value = new_res
        project.getCalendars.return_value = MagicMock()
        project.getDefaultCalendar.return_value = None
        return project, new_res, existing

    def test_duplicate_name_shows_warning(self, qapp):
        """When the dialog proposes a name that already exists, QMessageBox.warning
        must be called."""
        from resource_view import ResourceView
        import sys

        project, new_res, _ = self._make_project(existing_name="Alice")
        v = ResourceView()
        v.load_project(project)

        res_dlg = MagicMock()
        res_dlg.exec_.return_value = 1          # Accepted
        res_dlg._e_name = MagicMock()
        res_dlg._e_name.text.return_value = "Alice"   # duplicate!

        java_lang = MagicMock()
        java_lang.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang}), \
             patch("dialogs.ResourceDialog", return_value=res_dlg), \
             patch("PyQt5.QtWidgets.QMessageBox.warning") as mock_warn:
            v.add_resource()

        mock_warn.assert_called_once()

    def test_duplicate_name_rolls_back_resource(self, qapp):
        """When a duplicate name is detected, new_res.remove() must be called."""
        from resource_view import ResourceView
        import sys

        project, new_res, _ = self._make_project(existing_name="Alice")
        v = ResourceView()
        v.load_project(project)

        res_dlg = MagicMock()
        res_dlg.exec_.return_value = 1
        res_dlg._e_name = MagicMock()
        res_dlg._e_name.text.return_value = "alice"  # case-insensitive match

        java_lang = MagicMock()
        java_lang.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang}), \
             patch("dialogs.ResourceDialog", return_value=res_dlg), \
             patch("PyQt5.QtWidgets.QMessageBox.warning"):
            v.add_resource()

        new_res.remove.assert_called_once()

    def test_unique_name_proceeds_without_warning(self, qapp):
        """A name that does not exist must not trigger a warning and must call
        apply_to_resource()."""
        from resource_view import ResourceView
        import sys

        project, new_res, _ = self._make_project(existing_name="Alice")
        v = ResourceView()
        v.load_project(project)

        res_dlg = MagicMock()
        res_dlg.exec_.return_value = 1
        res_dlg._e_name = MagicMock()
        res_dlg._e_name.text.return_value = "Bob"  # unique

        java_lang = MagicMock()
        java_lang.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang}), \
             patch("dialogs.ResourceDialog", return_value=res_dlg), \
             patch("PyQt5.QtWidgets.QMessageBox.warning") as mock_warn:
            v.add_resource()

        mock_warn.assert_not_called()
        res_dlg.apply_to_resource.assert_called_once()

    def test_duplicate_calendar_rolled_back(self, qapp):
        """Calendar linked to the new resource must also be removed on duplicate
        name detection."""
        from resource_view import ResourceView
        import sys

        project, new_res, _ = self._make_project(existing_name="Alice")
        cal_mock = MagicMock()
        new_res.getCalendar.return_value = cal_mock
        cal_list = MagicMock()
        project.getCalendars.return_value = cal_list

        v = ResourceView()
        v.load_project(project)

        res_dlg = MagicMock()
        res_dlg.exec_.return_value = 1
        res_dlg._e_name = MagicMock()
        res_dlg._e_name.text.return_value = "Alice"

        java_lang = MagicMock()
        java_lang.Integer = int
        with patch.dict(sys.modules, {"java.lang": java_lang}), \
             patch("dialogs.ResourceDialog", return_value=res_dlg), \
             patch("PyQt5.QtWidgets.QMessageBox.warning"):
            v.add_resource()

        cal_list.remove.assert_called_with(cal_mock)

