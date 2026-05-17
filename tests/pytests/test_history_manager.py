"""Tests for history_manager.py — HistoryManager undo/redo engine.

Java / MPXJ calls (_serialize and _restore) are patched out so no JVM is needed.
The tests exercise the stack mechanics (push, undo, redo, can_undo, can_redo, depth)
by injecting raw byte snapshots directly into the stack structures.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from logic import ProjectLogic
from history_manager import HistoryManager

# Sentinel byte strings used as stand-in snapshots
_S0 = b'<xml>state-0</xml>'
_S1 = b'<xml>state-1</xml>'
_S2 = b'<xml>state-2</xml>'


def _hm_with_snaps(view, snaps, idx):
    """Build a HistoryManager whose *view* stack is pre-loaded with *snaps*."""
    logic = ProjectLogic()
    hm = HistoryManager(logic)
    hm._stacks[view]['snaps'] = list(snaps)
    hm._stacks[view]['idx']   = idx
    return hm


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

class TestInitialState:
    def test_all_stacks_start_empty(self):
        hm = HistoryManager(ProjectLogic())
        for view in HistoryManager.VIEWS:
            assert hm._stacks[view]['snaps'] == []
            assert hm._stacks[view]['idx'] == -1

    def test_can_undo_false_on_empty_stack(self):
        hm = HistoryManager(ProjectLogic())
        for view in HistoryManager.VIEWS:
            assert not hm.can_undo(view)

    def test_can_redo_false_on_empty_stack(self):
        hm = HistoryManager(ProjectLogic())
        for view in HistoryManager.VIEWS:
            assert not hm.can_redo(view)

    def test_views_constant_contains_all_five_views(self):
        assert set(HistoryManager.VIEWS) == {'tasks', 'resources', 'dependencies', 'baseline', 'team_planner'}


# ---------------------------------------------------------------------------
# push()
# ---------------------------------------------------------------------------

class TestPush:
    def test_push_adds_snapshot_to_empty_stack(self):
        logic = ProjectLogic()
        logic.load_data(MagicMock())
        hm = HistoryManager(logic)
        with patch.object(hm, '_serialize', return_value=_S0):
            hm.push('tasks')
        assert hm._stacks['tasks']['snaps'] == [_S0]
        assert hm._stacks['tasks']['idx'] == 0

    def test_push_increments_idx(self):
        logic = ProjectLogic()
        logic.load_data(MagicMock())
        hm = HistoryManager(logic)
        with patch.object(hm, '_serialize', side_effect=[_S0, _S1]):
            hm.push('tasks')
            hm.push('tasks')
        assert hm._stacks['tasks']['idx'] == 1

    def test_push_truncates_redo_branch(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1, _S2], idx=1)
        # Current position is 1; redo branch is [_S2] at idx=2
        logic = ProjectLogic()
        logic.load_data(MagicMock())
        hm._logic = logic
        new_snap = b'<xml>new</xml>'
        with patch.object(hm, '_serialize', return_value=new_snap):
            hm.push('tasks')
        # _S2 should be gone; new snapshot appended after _S1
        assert hm._stacks['tasks']['snaps'] == [_S0, _S1, new_snap]
        assert hm._stacks['tasks']['idx'] == 2

    def test_push_no_op_when_serialize_returns_none(self):
        hm = HistoryManager(ProjectLogic())
        with patch.object(hm, '_serialize', return_value=None):
            hm.push('tasks')
        assert hm._stacks['tasks']['snaps'] == []

    def test_push_no_op_while_restoring(self):
        logic = ProjectLogic()
        logic.load_data(MagicMock())
        hm = HistoryManager(logic)
        hm._restoring = True
        with patch.object(hm, '_serialize', return_value=_S0) as mock_ser:
            hm.push('tasks')
        mock_ser.assert_not_called()
        assert hm._stacks['tasks']['snaps'] == []

    def test_push_does_not_affect_other_views(self):
        logic = ProjectLogic()
        logic.load_data(MagicMock())
        hm = HistoryManager(logic)
        with patch.object(hm, '_serialize', return_value=_S0):
            hm.push('tasks')
        assert hm._stacks['resources']['snaps'] == []
        assert hm._stacks['dependencies']['snaps'] == []


# ---------------------------------------------------------------------------
# push_all()
# ---------------------------------------------------------------------------

class TestPushAll:
    def test_push_all_resets_all_stacks_to_single_entry(self):
        logic = ProjectLogic()
        logic.load_data(MagicMock())
        hm = HistoryManager(logic)
        with patch.object(hm, '_serialize', return_value=_S0):
            hm.push_all()
        for view in HistoryManager.VIEWS:
            assert hm._stacks[view]['snaps'] == [_S0]
            assert hm._stacks[view]['idx'] == 0

    def test_push_all_clears_previous_history(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)
        hm._stacks['resources']['snaps'] = [_S0]
        hm._stacks['resources']['idx'] = 0
        logic = ProjectLogic()
        logic.load_data(MagicMock())
        hm._logic = logic
        with patch.object(hm, '_serialize', return_value=_S2):
            hm.push_all()
        assert hm._stacks['tasks']['snaps'] == [_S2]
        assert hm._stacks['tasks']['idx'] == 0

    def test_push_all_clears_all_stacks_when_no_project(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)
        hm._logic = ProjectLogic()   # no project loaded
        with patch.object(hm, '_serialize', return_value=None):
            hm.push_all()
        for view in HistoryManager.VIEWS:
            assert hm._stacks[view]['snaps'] == []
            assert hm._stacks[view]['idx'] == -1


# ---------------------------------------------------------------------------
# undo()
# ---------------------------------------------------------------------------

class TestUndo:
    def test_undo_returns_true_and_steps_back(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)
        with patch.object(hm, '_restore') as mock_restore:
            result = hm.undo('tasks')
        assert result is True
        assert hm._stacks['tasks']['idx'] == 0
        mock_restore.assert_called_once_with(_S0)

    def test_undo_returns_false_at_initial_state(self):
        hm = _hm_with_snaps('tasks', [_S0], idx=0)
        with patch.object(hm, '_restore') as mock_restore:
            result = hm.undo('tasks')
        assert result is False
        mock_restore.assert_not_called()

    def test_undo_returns_false_on_empty_stack(self):
        hm = HistoryManager(ProjectLogic())
        assert hm.undo('tasks') is False

    def test_undo_sets_restoring_flag_during_restore(self):
        flags_seen = []
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)

        def fake_restore(data):
            flags_seen.append(hm._restoring)

        with patch.object(hm, '_restore', side_effect=fake_restore):
            hm.undo('tasks')
        assert flags_seen == [True]
        assert not hm._restoring

    def test_undo_clears_restoring_flag_even_on_error(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)
        with patch.object(hm, '_restore', side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError):
                hm.undo('tasks')
        assert not hm._restoring

    def test_multiple_undos(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1, _S2], idx=2)
        with patch.object(hm, '_restore'):
            hm.undo('tasks')
            hm.undo('tasks')
        assert hm._stacks['tasks']['idx'] == 0

    def test_undo_does_not_affect_other_views(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)
        hm._stacks['resources']['snaps'] = [_S0, _S1]
        hm._stacks['resources']['idx']   = 1
        with patch.object(hm, '_restore'):
            hm.undo('tasks')
        assert hm._stacks['resources']['idx'] == 1


# ---------------------------------------------------------------------------
# redo()
# ---------------------------------------------------------------------------

class TestRedo:
    def test_redo_returns_true_and_steps_forward(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=0)
        with patch.object(hm, '_restore') as mock_restore:
            result = hm.redo('tasks')
        assert result is True
        assert hm._stacks['tasks']['idx'] == 1
        mock_restore.assert_called_once_with(_S1)

    def test_redo_returns_false_at_latest_state(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)
        with patch.object(hm, '_restore') as mock_restore:
            result = hm.redo('tasks')
        assert result is False
        mock_restore.assert_not_called()

    def test_redo_returns_false_on_empty_stack(self):
        hm = HistoryManager(ProjectLogic())
        assert hm.redo('tasks') is False

    def test_undo_then_redo_returns_to_latest(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1, _S2], idx=2)
        with patch.object(hm, '_restore'):
            hm.undo('tasks')
            hm.undo('tasks')
            hm.redo('tasks')
            hm.redo('tasks')
        assert hm._stacks['tasks']['idx'] == 2


# ---------------------------------------------------------------------------
# can_undo / can_redo
# ---------------------------------------------------------------------------

class TestCanUndoRedo:
    def test_can_undo_false_at_idx_0(self):
        hm = _hm_with_snaps('tasks', [_S0], idx=0)
        assert not hm.can_undo('tasks')

    def test_can_undo_true_when_idx_gt_0(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)
        assert hm.can_undo('tasks')

    def test_can_redo_false_at_latest(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=1)
        assert not hm.can_redo('tasks')

    def test_can_redo_true_when_redo_branch_exists(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1], idx=0)
        assert hm.can_redo('tasks')


# ---------------------------------------------------------------------------
# depth()
# ---------------------------------------------------------------------------

class TestDepth:
    def test_depth_at_latest(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1, _S2], idx=2)
        assert hm.depth('tasks') == (2, 0)

    def test_depth_at_initial(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1, _S2], idx=0)
        assert hm.depth('tasks') == (0, 2)

    def test_depth_in_middle(self):
        hm = _hm_with_snaps('tasks', [_S0, _S1, _S2], idx=1)
        assert hm.depth('tasks') == (1, 1)

    def test_depth_empty_stack(self):
        hm = HistoryManager(ProjectLogic())
        assert hm.depth('tasks') == (-1, 0)
