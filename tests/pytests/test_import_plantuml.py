"""Tests for import_plantuml.py — PlantUML @startgantt parser.

All MPXJ / JPype / Java classes are mocked via sys.modules so no JVM is needed.
The tests verify the regex parsing logic, task / milestone / dependency handling,
and percentage-complete assignment.
"""

import sys
import os
import textwrap

import pytest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


# ---------------------------------------------------------------------------
# Java module mocking
# ---------------------------------------------------------------------------

def _java_mocks():
    """Build a minimal set of mocked Java modules for import_plantuml."""
    mock_task    = MagicMock()
    mock_project = MagicMock()
    mock_project.addTask.return_value = mock_task

    mock_project_file_cls = MagicMock(return_value=mock_project)

    mock_duration_cls  = MagicMock()
    mock_time_unit_cls = MagicMock()

    mock_org_mpxj = MagicMock()
    mock_org_mpxj.ProjectFile  = mock_project_file_cls
    mock_org_mpxj.Duration     = mock_duration_cls
    mock_org_mpxj.TimeUnit     = mock_time_unit_cls

    mock_ldt = MagicMock()
    mock_java_time = MagicMock()
    mock_java_time.LocalDateTime.of.return_value = mock_ldt

    mock_jpype = MagicMock()
    mock_jpype.JInt = int   # JInt(1) == 1

    return {
        'org':          MagicMock(),
        'org.mpxj':     mock_org_mpxj,
        'jpype':        mock_jpype,
        'java':         MagicMock(),
        'java.time':    mock_java_time,
    }, mock_project, mock_task


def _call_import(puml_text: str):
    """Write *puml_text* to a temp file and call import_plantuml()."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.puml',
                                    delete=False, encoding='utf-8') as f:
        f.write(puml_text)
        path = f.name

    mods, project, task = _java_mocks()
    with patch.dict(sys.modules, mods):
        from import_plantuml import import_plantuml
        result = import_plantuml(path)
    os.unlink(path)
    return result, project, task


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------

class TestBasicTaskParsing:
    def test_single_task_calls_addTask(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-06
            [Design] as [T1] starts 2025-01-06 and lasts 5 days
            @endgantt
        """)
        _, project, _ = _call_import(puml)
        project.addTask.assert_called()

    def test_multiple_tasks_adds_correct_count(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-06
            [Task A] as [A] starts 2025-01-06 and lasts 3 days
            [Task B] as [B] starts 2025-01-10 and lasts 2 days
            @endgantt
        """)
        _, project, _ = _call_import(puml)
        assert project.addTask.call_count == 2

    def test_task_name_is_set(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-02-01
            [My Task] as [MT] starts 2025-02-01 and lasts 1 days
            @endgantt
        """)
        _, project, task = _call_import(puml)
        task.setName.assert_called_with("My Task")

    def test_task_duration_is_set(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-02-01
            [Work] as [W] starts 2025-02-01 and lasts 7 days
            @endgantt
        """)
        _, project, task = _call_import(puml)
        task.setDuration.assert_called()

    def test_blank_lines_and_comments_are_ignored(self):
        puml = textwrap.dedent("""\
            @startgantt

            ' this is a comment
            Project starts 2025-01-01

            [A] as [A1] starts 2025-01-01 and lasts 1 days
            @endgantt
        """)
        _, project, _ = _call_import(puml)
        project.addTask.assert_called_once()


# ---------------------------------------------------------------------------
# Milestones
# ---------------------------------------------------------------------------

class TestMilestoneParsing:
    def test_milestone_calls_addTask(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-03-01
            [Kickoff] as [KO] happens at 2025-03-01
            @endgantt
        """)
        _, project, _ = _call_import(puml)
        project.addTask.assert_called()

    def test_milestone_sets_milestone_flag(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-03-01
            [Delivery] as [D] happens at 2025-03-15
            @endgantt
        """)
        _, project, task = _call_import(puml)
        task.setMilestone.assert_called_with(True)

    def test_milestone_and_task_both_parsed(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            [Task A] as [A] starts 2025-01-01 and lasts 5 days
            [Gate] as [G] happens at 2025-01-06
            @endgantt
        """)
        _, project, _ = _call_import(puml)
        assert project.addTask.call_count == 2


# ---------------------------------------------------------------------------
# Percentage complete
# ---------------------------------------------------------------------------

class TestPercentageParsing:
    def test_pct_complete_is_set(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            [Work] as [W] starts 2025-01-01 and lasts 10 days
            [W] is 40% completed
            @endgantt
        """)
        _, project, task = _call_import(puml)
        # Source: if pct > 0: task.setPercentageComplete(Double.valueOf(float(pct)))
        task.setPercentageComplete.assert_called_once()

    def test_zero_pct_complete_skips_call(self):
        """Source only calls setPercentageComplete when pct > 0.
        A 0% line should NOT trigger the call.
        """
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            [Task] as [T] starts 2025-01-01 and lasts 3 days
            [T] is 0% completed
            @endgantt
        """)
        _, project, task = _call_import(puml)
        task.setPercentageComplete.assert_not_called()


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

class TestDependencyParsing:
    def test_dependency_adds_predecessor(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            [A] as [A1] starts 2025-01-01 and lasts 3 days
            [B] as [B1] starts 2025-01-04 and lasts 2 days
            [B1] starts after [A1]'s end
            @endgantt
        """)
        _, project, task = _call_import(puml)
        # addPredecessor or similar should have been called on the successor task
        task.addPredecessor.assert_called()

    def test_colored_lines_are_ignored(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            [Task] as [T] starts 2025-01-01 and lasts 1 days
            [T] is colored in LightBlue/Red
            @endgantt
        """)
        _, project, _ = _call_import(puml)
        project.addTask.assert_called_once()


# ---------------------------------------------------------------------------
# Project start
# ---------------------------------------------------------------------------

class TestProjectStart:
    def test_no_project_start_line_still_parses(self):
        puml = textwrap.dedent("""\
            @startgantt
            [Task] as [T] starts 2025-01-01 and lasts 1 days
            @endgantt
        """)
        _, project, _ = _call_import(puml)
        project.addTask.assert_called()

    def test_project_start_sets_project_start_date(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-06-01
            [T] as [T1] starts 2025-06-01 and lasts 1 days
            @endgantt
        """)
        _, project, _ = _call_import(puml)
        # ProjectFile.getProjectProperties().setStartDate() should be called
        props = project.getProjectProperties()
        props.setStartDate.assert_called()

    def test_returns_project_file_object(self):
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            [T] as [T1] starts 2025-01-01 and lasts 1 days
            @endgantt
        """)
        result, project, _ = _call_import(puml)
        assert result is project


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_no_tasks_raises_value_error(self):
        """Test that ValueError is raised when no tasks are found."""
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            ' Only comments, no tasks
            @endgantt
        """)
        mods, _, _ = _java_mocks()
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.puml',
                                        delete=False, encoding='utf-8') as f:
            f.write(puml)
            path = f.name
        
        with patch.dict(sys.modules, mods):
            from import_plantuml import import_plantuml
            with pytest.raises(ValueError, match="No tasks found"):
                import_plantuml(path)
        os.unlink(path)
    
    def test_dependency_with_invalid_alias_continues(self):
        """Test that dependencies with invalid aliases are skipped."""
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            [A] as [A1] starts 2025-01-01 and lasts 3 days
            [B] as [B1] starts 2025-01-04 and lasts 2 days
            [B1] starts after [INVALID]'s end
            @endgantt
        """)
        # Should not raise an exception, should just skip the invalid dependency
        result, project, _ = _call_import(puml)
        assert result is not None
    
    def test_dependency_exception_is_caught(self):
        """Test that exceptions during dependency addition are caught and warned."""
        puml = textwrap.dedent("""\
            @startgantt
            Project starts 2025-01-01
            [A] as [A1] starts 2025-01-01 and lasts 3 days
            [B] as [B1] starts 2025-01-04 and lasts 2 days
            [B1] starts after [A1]'s end
            @endgantt
        """)
        
        mods, project, task = _java_mocks()
        # Make addPredecessor raise an exception
        task.addPredecessor.side_effect = Exception("Test exception")
        
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.puml',
                                        delete=False, encoding='utf-8') as f:
            f.write(puml)
            path = f.name
        
        with patch.dict(sys.modules, mods):
            from import_plantuml import import_plantuml
            # Should not raise, should catch and print warning
            with patch('builtins.print') as mock_print:
                result = import_plantuml(path)
                # Verify warning was printed
                assert any('[WARN]' in str(call) for call in mock_print.call_args_list)
        os.unlink(path)
