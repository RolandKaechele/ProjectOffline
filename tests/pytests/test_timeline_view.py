"""Tests for views/timeline_view.py — TimelineView widget.

Covers:
  - _set_collapsed(): height constraints and visibility toggled atomically
  - is_task_pinned() / is_milestone_pinned() query helpers
  - add_task() / remove_task() / add_milestone() / remove_milestone() mutations
  - pinned_task_ids() / pinned_milestone_ids() accessors
  - register() wires data_changed and remove_from_canvas_requested signals
  - Initial state: widget starts collapsed (max/min height == 0, invisible)

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PyQt5.QtCore import QDate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_view(qapp):
    """Return a fresh TimelineView (patched to avoid gantt_view constants import issues)."""
    from timeline_view import TimelineView
    return TimelineView()


def _make_task_mock(task_id=1, name="Task A",
                    start="2025-01-06", finish="2025-01-10",
                    is_milestone=False):
    """Return a minimal MPXJ task mock consumable by TimelineView.add_task()."""
    t = MagicMock()
    t.getID.return_value = task_id
    t.getName.return_value = name
    t.getMilestone.return_value = is_milestone

    def _ldt(iso):
        m = MagicMock()
        m.__str__ = MagicMock(return_value=iso)
        return m

    t.getStart.return_value  = _ldt(start)
    t.getFinish.return_value = _ldt(finish)
    return t


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def view(qapp):
    return _make_view(qapp)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestTimelineViewInit:
    def test_widget_created(self, qapp):
        from timeline_view import TimelineView
        assert TimelineView() is not None

    def test_starts_collapsed(self, view):
        """Widget must start collapsed so it takes no layout space by default."""
        assert view.maximumHeight() == 0
        assert view.minimumHeight() == 0

    def test_starts_invisible(self, view):
        assert not view.isVisible()

    def test_fixed_h_attribute_set(self, view):
        from timeline_view import FIXED_HEIGHT
        assert view._fixed_h == FIXED_HEIGHT

    def test_no_tasks_initially(self, view):
        assert view._timeline_tasks == []

    def test_no_milestones_initially(self, view):
        assert view._timeline_milestones == []


# ---------------------------------------------------------------------------
# _set_collapsed
# ---------------------------------------------------------------------------

class TestSetCollapsed:
    def test_expand_sets_correct_heights(self, view):
        from timeline_view import FIXED_HEIGHT
        view._set_collapsed(False)
        assert view.minimumHeight() == FIXED_HEIGHT
        assert view.maximumHeight() == FIXED_HEIGHT

    def test_expand_makes_visible(self, view):
        view._set_collapsed(False)
        assert view.isVisible()

    def test_collapse_sets_zero_heights(self, view):
        view._set_collapsed(False)   # expand first
        view._set_collapsed(True)
        assert view.minimumHeight() == 0
        assert view.maximumHeight() == 0

    def test_collapse_makes_invisible(self, view):
        view._set_collapsed(False)
        view._set_collapsed(True)
        assert not view.isVisible()

    def test_roundtrip_expand_collapse_expand(self, view):
        from timeline_view import FIXED_HEIGHT
        view._set_collapsed(False)
        view._set_collapsed(True)
        view._set_collapsed(False)
        assert view.minimumHeight() == FIXED_HEIGHT
        assert view.isVisible()

    def test_collapse_already_collapsed_is_safe(self, view):
        """Calling _set_collapsed(True) on an already-collapsed widget must not raise."""
        view._set_collapsed(True)   # already collapsed at start
        assert view.maximumHeight() == 0

    def test_expand_already_expanded_is_safe(self, view):
        from timeline_view import FIXED_HEIGHT
        view._set_collapsed(False)
        view._set_collapsed(False)  # second call
        assert view.minimumHeight() == FIXED_HEIGHT


# ---------------------------------------------------------------------------
# add_task / remove_task / is_task_pinned / pinned_task_ids
# ---------------------------------------------------------------------------

class TestTaskPinning:
    def test_add_task_pins_it(self, view):
        t = _make_task_mock(task_id=1)
        view.add_task(t)
        assert view.is_task_pinned(1)

    def test_add_task_not_pinned_before_add(self, view):
        assert not view.is_task_pinned(99)

    def test_add_duplicate_task_does_not_duplicate(self, view):
        t = _make_task_mock(task_id=2)
        view.add_task(t)
        view.add_task(t)   # second call must be a no-op
        assert len(view._timeline_tasks) == 1

    def test_remove_task_unpins_it(self, view):
        t = _make_task_mock(task_id=3)
        view.add_task(t)
        view.remove_task(3)
        assert not view.is_task_pinned(3)

    def test_remove_nonexistent_task_is_safe(self, view):
        view.remove_task(999)   # must not raise

    def test_pinned_task_ids_lists_all(self, view):
        for i in [1, 2, 3]:
            view.add_task(_make_task_mock(task_id=i, name=f"T{i}"))
        assert sorted(view.pinned_task_ids()) == [1, 2, 3]

    def test_pinned_task_ids_empty_initially(self, view):
        assert view.pinned_task_ids() == []

    def test_add_task_emits_data_changed(self, view):
        received = []
        view.data_changed.connect(lambda: received.append(True))
        view.add_task(_make_task_mock(task_id=10))
        assert received

    def test_remove_task_emits_data_changed(self, view):
        view.add_task(_make_task_mock(task_id=11))
        received = []
        view.data_changed.connect(lambda: received.append(True))
        view.remove_task(11)
        assert received


# ---------------------------------------------------------------------------
# add_milestone / remove_milestone / is_milestone_pinned / pinned_milestone_ids
# ---------------------------------------------------------------------------

class TestMilestonePinning:
    def test_add_milestone_pins_it(self, view):
        t = _make_task_mock(task_id=5, name="MS", is_milestone=True,
                            start="2025-03-01", finish="2025-03-01")
        view.add_milestone(t)
        assert view.is_milestone_pinned(5)

    def test_not_pinned_before_add(self, view):
        assert not view.is_milestone_pinned(99)

    def test_add_duplicate_milestone_is_noop(self, view):
        t = _make_task_mock(task_id=6, is_milestone=True,
                            start="2025-03-01", finish="2025-03-01")
        view.add_milestone(t)
        view.add_milestone(t)
        assert len(view._timeline_milestones) == 1

    def test_remove_milestone_unpins_it(self, view):
        t = _make_task_mock(task_id=7, is_milestone=True,
                            start="2025-03-01", finish="2025-03-01")
        view.add_milestone(t)
        view.remove_milestone(7)
        assert not view.is_milestone_pinned(7)

    def test_remove_nonexistent_milestone_is_safe(self, view):
        view.remove_milestone(999)

    def test_pinned_milestone_ids_empty_initially(self, view):
        assert view.pinned_milestone_ids() == []


# ---------------------------------------------------------------------------
# register()
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_connects_data_changed(self, view):
        mw = MagicMock()
        mw._on_timeline_data_changed = MagicMock()
        mw._on_timeline_remove_from_canvas = MagicMock()
        view.register(mw)
        # Emit the signal and verify the slot was called
        view.data_changed.emit()
        mw._on_timeline_data_changed.assert_called_once()

    def test_register_connects_remove_signal(self, view):
        mw = MagicMock()
        mw._on_timeline_data_changed = MagicMock()
        mw._on_timeline_remove_from_canvas = MagicMock()
        view.register(mw)
        view.remove_from_canvas_requested.emit(42, False)
        mw._on_timeline_remove_from_canvas.assert_called_once_with(42, False)

    def test_register_stores_main_window_ref(self, view):
        mw = MagicMock()
        mw._on_timeline_data_changed = MagicMock()
        mw._on_timeline_remove_from_canvas = MagicMock()
        view.register(mw)
        assert view._main_window is mw
