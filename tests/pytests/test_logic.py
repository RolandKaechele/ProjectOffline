"""Tests for logic.py — ProjectLogic in-memory data store."""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from logic import ProjectLogic


class TestProjectLogic:
    def test_initial_state_is_none(self):
        logic = ProjectLogic()
        assert logic.get_data() is None

    def test_load_data_stores_value(self):
        logic = ProjectLogic()
        sentinel = object()
        logic.load_data(sentinel)
        assert logic.get_data() is sentinel

    def test_load_data_none_clears_previous(self):
        logic = ProjectLogic()
        logic.load_data("something")
        logic.load_data(None)
        assert logic.get_data() is None

    def test_load_data_overwrites_previous(self):
        logic = ProjectLogic()
        logic.load_data("first")
        logic.load_data("second")
        assert logic.get_data() == "second"

    def test_get_data_does_not_mutate(self):
        logic = ProjectLogic()
        logic.load_data(42)
        _ = logic.get_data()
        assert logic.get_data() == 42

    def test_project_data_attribute_accessible(self):
        logic = ProjectLogic()
        assert hasattr(logic, 'project_data')
        assert logic.project_data is None
