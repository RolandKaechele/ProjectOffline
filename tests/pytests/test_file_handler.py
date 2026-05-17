"""Tests for file_handler.py — ProjectFileHandler open / save operations.

jpype.isJVMStarted and jpype.startJVM are patched so no real JVM is started.
MPXJ Reader / Writer are patched at the import level inside each method call.

jpype is pre-stubbed in sys.modules by conftest.py so file_handler can be
imported without a real JVM.  Individual tests use patch.object(jpype, ...)
to control JVM-startup behaviour.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from logic import ProjectLogic
import file_handler as fh_mod
import jpype  # resolved from sys.modules stub inserted by conftest.py


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _handler(jvm_running=True):
    """Return a ProjectFileHandler with JVM startup mocked."""
    logic = ProjectLogic()
    with patch.object(jpype, 'isJVMStarted', return_value=jvm_running), \
         patch.object(jpype, 'startJVM'):
        handler = fh_mod.ProjectFileHandler(logic)
    return handler, logic


# ---------------------------------------------------------------------------
# Constructor / JVM management
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_does_not_start_jvm_if_already_running(self):
        logic = ProjectLogic()
        with patch.object(jpype, 'isJVMStarted', return_value=True) as mock_running, \
             patch.object(jpype, 'startJVM') as mock_start:
            fh_mod.ProjectFileHandler(logic)
        mock_start.assert_not_called()

    def test_starts_jvm_if_not_running(self):
        logic = ProjectLogic()
        with patch.object(jpype, 'isJVMStarted', return_value=False), \
             patch.object(jpype, 'startJVM') as mock_start:
            fh_mod.ProjectFileHandler(logic)
        mock_start.assert_called_once()

    def test_jvm_started_with_log4j_arg(self):
        logic = ProjectLogic()
        with patch.object(jpype, 'isJVMStarted', return_value=False), \
             patch.object(jpype, 'startJVM') as mock_start:
            fh_mod.ProjectFileHandler(logic)
        args = mock_start.call_args[0]
        assert any("log4j" in str(a) for a in args)

    def test_logic_reference_stored(self):
        handler, logic = _handler()
        assert handler.logic is logic


# ---------------------------------------------------------------------------
# open_project()
# ---------------------------------------------------------------------------

class TestOpenProject:
    def test_open_project_success_stores_data_in_logic(self, tmp_path):
        handler, logic = _handler()
        mock_project = MagicMock()
        mock_reader  = MagicMock()
        mock_reader.read.return_value = mock_project

        xml_file = tmp_path / "test.xml"
        xml_file.write_text("<xml/>")

        with patch.dict(sys.modules, {
            'org': MagicMock(),
            'org.mpxj': MagicMock(),
            'org.mpxj.reader': MagicMock(),
        }):
            # Patch the UniversalProjectReader import inside the method
            with patch('file_handler.UniversalProjectReader', mock_reader, create=True):
                # UniversalProjectReader is imported inside the method;
                # patch the name in the module's namespace
                import importlib
                # Simpler: patch the whole inner import
                pass

        # Use a direct approach: inject into sys.modules before the method runs
        mock_upj_module = MagicMock()
        mock_upj_module.UniversalProjectReader.return_value = mock_reader
        with patch.dict(sys.modules, {
            'org': MagicMock(),
            'org.mpxj': MagicMock(),
            'org.mpxj.reader': mock_upj_module,
        }):
            result = handler.open_project(str(xml_file))

        assert result is True
        assert logic.get_data() is mock_project

    def test_open_project_returns_false_on_exception(self, tmp_path):
        handler, logic = _handler()

        with patch.dict(sys.modules, {
            'org': MagicMock(),
            'org.mpxj': MagicMock(),
            'org.mpxj.reader': MagicMock(),
        }):
            # reader raises on read()
            mock_upj_module = MagicMock()
            mock_upj_module.UniversalProjectReader.return_value.read.side_effect = \
                RuntimeError("bad file")
            with patch.dict(sys.modules, {'org.mpxj.reader': mock_upj_module}):
                result = handler.open_project("/nonexistent/file.xml", parent=None)

        assert result is False

    def test_open_project_returns_false_logic_unchanged_on_failure(self, tmp_path):
        handler, logic = _handler()
        logic.load_data("original")

        with patch.dict(sys.modules, {
            'org': MagicMock(),
            'org.mpxj': MagicMock(),
            'org.mpxj.reader': MagicMock(),
        }):
            mock_upj_module = MagicMock()
            mock_upj_module.UniversalProjectReader.return_value.read.side_effect = \
                RuntimeError("corrupt")
            with patch.dict(sys.modules, {'org.mpxj.reader': mock_upj_module}):
                handler.open_project("/bad/path.mpp", parent=None)

        # Logic should still hold whatever it had before — open_project only sets on success
        # (the failure path does not call logic.load_data, so data is unchanged)
        assert logic.get_data() == "original"


# ---------------------------------------------------------------------------
# save_project()
# ---------------------------------------------------------------------------

class TestSaveProject:
    def test_save_project_returns_false_when_no_project(self, tmp_path):
        handler, logic = _handler()
        # logic has no project (None)
        result = handler.save_project(str(tmp_path / "out.xml"))
        assert result is False

    def test_save_project_calls_writer(self, tmp_path):
        handler, logic = _handler()
        mock_project = MagicMock()
        logic.load_data(mock_project)

        mock_writer = MagicMock()
        mock_mspdi_module = MagicMock()
        mock_mspdi_module.MSPDIWriter.return_value = mock_writer

        out_path = str(tmp_path / "out.xml")
        # java.lang must be a real module entry so that
        # `from java.lang import Integer` inside _sanitize_calendar_uids works.
        mock_java_lang = MagicMock()
        with patch.dict(sys.modules, {
            'org': MagicMock(),
            'org.mpxj': MagicMock(),
            'org.mpxj.mspdi': mock_mspdi_module,
            'java': MagicMock(),
            'java.lang': mock_java_lang,
        }):
            result = handler.save_project(out_path)

        assert result is True
        mock_writer.write.assert_called_once_with(mock_project, out_path)

    def test_save_project_returns_false_on_exception(self, tmp_path):
        handler, logic = _handler()
        mock_project = MagicMock()
        logic.load_data(mock_project)

        mock_mspdi_module = MagicMock()
        mock_mspdi_module.MSPDIWriter.return_value.write.side_effect = RuntimeError("disk full")

        with patch.dict(sys.modules, {
            'org': MagicMock(),
            'org.mpxj': MagicMock(),
            'org.mpxj.mspdi': mock_mspdi_module,
        }):
            result = handler.save_project(str(tmp_path / "out.xml"))

        assert result is False


# ---------------------------------------------------------------------------
# _patch_enterprise_cf_values — resource name semicolon normalisation
# ---------------------------------------------------------------------------

_MSPDI_NS = 'http://schemas.microsoft.com/project'


def _minimal_xml(resource_names=None, task_uids=None):
    """Return a minimal MSPDI XML string with optional Resource Name and Task UID elements."""
    import xml.etree.ElementTree as ET
    ns = _MSPDI_NS
    ET.register_namespace('', ns)
    root = ET.Element(f'{{{ns}}}Project')
    if resource_names:
        resources_el = ET.SubElement(root, f'{{{ns}}}Resources')
        for i, name in enumerate(resource_names, start=1):
            res_el = ET.SubElement(resources_el, f'{{{ns}}}Resource')
            ET.SubElement(res_el, f'{{{ns}}}UID').text = str(i)
            ET.SubElement(res_el, f'{{{ns}}}Name').text = name
    if task_uids:
        tasks_el = ET.SubElement(root, f'{{{ns}}}Tasks')
        for uid in task_uids:
            task_el = ET.SubElement(tasks_el, f'{{{ns}}}Task')
            ET.SubElement(task_el, f'{{{ns}}}UID').text = str(uid)
    return ET.tostring(root, encoding='unicode', xml_declaration=False)


class TestXmlSemicolonNormalisation:
    """_patch_enterprise_cf_values must replace ';' with ',' in <Resource><Name> elements."""

    def _handler_with_xml(self, tmp_path, xml_content):
        """Write xml_content to a file, create a handler with _source_xml_path pointing at it."""
        handler, logic = _handler()
        src = tmp_path / "source.xml"
        src.write_text(xml_content, encoding='utf-8')
        handler._source_xml_path = str(src)
        return handler, logic

    def test_semicolon_in_resource_name_replaced_in_saved_xml(self, tmp_path):
        """After save, <Name>Smith; John</Name> becomes <Name>Smith, John</Name>."""
        xml_content = _minimal_xml(resource_names=["Smith; John", "Doe, Jane"])
        dest = tmp_path / "out.xml"
        dest.write_text(
            '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' + xml_content,
            encoding='utf-8',
        )
        handler, _ = self._handler_with_xml(tmp_path, xml_content)
        mock_project = MagicMock()
        mock_project.getCustomFields.return_value = []

        handler._patch_enterprise_cf_values(mock_project, str(dest))

        import xml.etree.ElementTree as ET
        tree = ET.parse(str(dest))
        names = [
            el.text
            for el in tree.getroot().findall(f'.//{{{_MSPDI_NS}}}Name')
        ]
        assert "Smith, John" in names
        assert "Smith; John" not in names

    def test_comma_resource_name_unchanged(self, tmp_path):
        """Resource names that already use ',' are left untouched."""
        xml_content = _minimal_xml(resource_names=["Doe, Jane"])
        dest = tmp_path / "out.xml"
        dest.write_text(
            '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' + xml_content,
            encoding='utf-8',
        )
        handler, _ = self._handler_with_xml(tmp_path, xml_content)
        mock_project = MagicMock()
        mock_project.getCustomFields.return_value = []

        handler._patch_enterprise_cf_values(mock_project, str(dest))

        import xml.etree.ElementTree as ET
        tree = ET.parse(str(dest))
        names = [el.text for el in tree.getroot().findall(f'.//{{{_MSPDI_NS}}}Name')]
        assert "Doe, Jane" in names

    def test_multiple_semicolons_all_replaced(self, tmp_path):
        """All ';' occurrences in a name are replaced with ','."""
        xml_content = _minimal_xml(resource_names=["A; B; C"])
        dest = tmp_path / "out.xml"
        dest.write_text(
            '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' + xml_content,
            encoding='utf-8',
        )
        handler, _ = self._handler_with_xml(tmp_path, xml_content)
        mock_project = MagicMock()
        mock_project.getCustomFields.return_value = []

        handler._patch_enterprise_cf_values(mock_project, str(dest))

        import xml.etree.ElementTree as ET
        tree = ET.parse(str(dest))
        names = [el.text for el in tree.getroot().findall(f'.//{{{_MSPDI_NS}}}Name')]
        assert "A, B, C" in names

    def test_no_resources_no_error(self, tmp_path):
        """XML with no Resource elements is handled gracefully."""
        xml_content = _minimal_xml(task_uids=[1])
        dest = tmp_path / "out.xml"
        dest.write_text(
            '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n' + xml_content,
            encoding='utf-8',
        )
        handler, _ = self._handler_with_xml(tmp_path, xml_content)
        mock_project = MagicMock()
        mock_project.getCustomFields.return_value = []

        # Must not raise
        handler._patch_enterprise_cf_values(mock_project, str(dest))


# ---------------------------------------------------------------------------
# _patch_save_custom_properties — sidecar JSON container expansion
# ---------------------------------------------------------------------------

def _make_mock_project_with_props(props_dict):
    """Return a mock project whose custom properties reflect *props_dict*."""
    mock_project = MagicMock()
    mock_cp = MagicMock()
    mock_cp.size.return_value = len(props_dict)
    mock_cp.keySet.return_value = list(props_dict.keys())
    mock_cp.get.side_effect = lambda k: props_dict.get(k)
    mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp
    return mock_project


class TestSaveCustomProperties:
    """_patch_save_custom_properties writes a JSON sidecar and expands JSON-string values."""

    def test_json_string_value_expanded_to_nested_dict_in_sidecar(self, tmp_path):
        """A valid JSON-object string is stored as a nested dict in the sidecar."""
        import json
        handler, _ = _handler()
        payload = {"filter": "project = TEST", "filter_type": "jql"}
        project = _make_mock_project_with_props({"jira2project": json.dumps(payload)})

        handler._patch_save_custom_properties(project, str(tmp_path / "proj.xml"))

        sidecar = tmp_path / "proj.xml.custom-props.json"
        data = json.loads(sidecar.read_text(encoding='utf-8'))
        assert isinstance(data["jira2project"], dict)
        assert data["jira2project"]["filter"] == "project = TEST"
        assert data["jira2project"]["filter_type"] == "jql"

    def test_plain_string_value_stored_as_string(self, tmp_path):
        """A plain string HashMap value is written to the sidecar as a string."""
        import json
        handler, _ = _handler()
        project = _make_mock_project_with_props({"My Key": "my value"})

        handler._patch_save_custom_properties(project, str(tmp_path / "proj.xml"))

        sidecar = tmp_path / "proj.xml.custom-props.json"
        data = json.loads(sidecar.read_text(encoding='utf-8'))
        assert data["My Key"] == "my value"

    def test_invalid_json_starting_with_brace_stored_as_string(self, tmp_path):
        """A value starting with '{' that is not valid JSON is stored as-is."""
        import json
        handler, _ = _handler()
        project = _make_mock_project_with_props({"bad": "{not json"})

        handler._patch_save_custom_properties(project, str(tmp_path / "proj.xml"))

        sidecar = tmp_path / "proj.xml.custom-props.json"
        data = json.loads(sidecar.read_text(encoding='utf-8'))
        assert data["bad"] == "{not json"

    def test_no_sidecar_created_when_custom_properties_empty(self, tmp_path):
        """No sidecar file is written when the project has no custom properties."""
        handler, _ = _handler()
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.size.return_value = 0
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        handler._patch_save_custom_properties(mock_project, str(tmp_path / "proj.xml"))

        assert not (tmp_path / "proj.xml.custom-props.json").exists()


# ---------------------------------------------------------------------------
# _patch_load_custom_properties — sidecar JSON container re-serialisation
# ---------------------------------------------------------------------------

class TestLoadCustomProperties:
    """_patch_load_custom_properties restores the HashMap from the sidecar."""

    def test_nested_dict_in_sidecar_loaded_as_json_string(self, tmp_path):
        """A dict value in the sidecar is re-serialised to a JSON string for the HashMap."""
        import json
        handler, _ = _handler()
        payload = {"filter": "project = X", "filter_type": "jql"}
        sidecar = tmp_path / "proj.xml.custom-props.json"
        sidecar.write_text(json.dumps({"jira2project": payload}), encoding='utf-8')

        mock_project = MagicMock()
        mock_java = MagicMock()
        captured = {}
        mock_java.util.HashMap.return_value.put.side_effect = lambda k, v: captured.update({k: v})

        with patch.dict(sys.modules, {'java': mock_java, 'java.util': mock_java.util}):
            handler._patch_load_custom_properties(mock_project, str(tmp_path / "proj.xml"))

        assert "jira2project" in captured
        loaded = json.loads(captured["jira2project"])
        assert loaded["filter"] == "project = X"
        assert loaded["filter_type"] == "jql"

    def test_plain_string_in_sidecar_passed_through(self, tmp_path):
        """A plain string value in the sidecar is stored in the HashMap as-is."""
        import json
        handler, _ = _handler()
        sidecar = tmp_path / "proj.xml.custom-props.json"
        sidecar.write_text(json.dumps({"My Key": "my value"}), encoding='utf-8')

        mock_project = MagicMock()
        mock_java = MagicMock()
        captured = {}
        mock_java.util.HashMap.return_value.put.side_effect = lambda k, v: captured.update({k: v})

        with patch.dict(sys.modules, {'java': mock_java, 'java.util': mock_java.util}):
            handler._patch_load_custom_properties(mock_project, str(tmp_path / "proj.xml"))

        assert captured.get("My Key") == "my value"

    def test_missing_sidecar_is_no_op(self, tmp_path):
        """No exception is raised and setCustomProperties is not called when sidecar absent."""
        handler, _ = _handler()
        mock_project = MagicMock()

        handler._patch_load_custom_properties(mock_project, str(tmp_path / "proj.xml"))

        mock_project.getProjectProperties.return_value.setCustomProperties.assert_not_called()


# ---------------------------------------------------------------------------
# TestPatchCalExcNames  (new: _patch_save_cal_exc_names / _patch_load_cal_exc_names)
# ---------------------------------------------------------------------------

class TestPatchCalExcNames:
    """_patch_save_cal_exc_names writes a .cal-exc-names.json sidecar; the
    companion _patch_load_cal_exc_names reads it back and calls setName() on
    matching calendar exceptions.

    \testinit
    Build a mock MPXJ project with calendars and calendar exceptions that have
    names.  Use a pytest tmp_path fixture for the on-disk sidecar file.

    \testrun
    Call _patch_save_cal_exc_names, inspect the resulting JSON, then call
    _patch_load_cal_exc_names on a project whose exceptions lack names and
    verify that setName() is invoked correctly.

    \testexpect
    Save: the sidecar file contains entries keyed by (cal, from, to).
    Load: setName() is called for each matching exception; exceptions that
          already have a name are skipped; missing sidecar is a no-op.

    \testcheck
    Assert sidecar file content and mock call counts.
    """

    def _make_exception(self, name="", from_date="2025-01-01", to_date="2025-01-01"):
        ex = MagicMock()
        ex.getName.return_value = name or None
        ex.getFromDate.return_value = from_date
        ex.getToDate.return_value = to_date
        return ex

    def _make_calendar(self, cal_name, exceptions):
        cal = MagicMock()
        cal.getName.return_value = cal_name
        cal.getCalendarExceptions.return_value = exceptions
        return cal

    def test_save_creates_sidecar_file(self, tmp_path):
        """_patch_save_cal_exc_names creates a .cal-exc-names.json sidecar."""
        handler, _ = _handler()
        ex = self._make_exception(name="Christmas", from_date="2025-12-25", to_date="2025-12-25")
        cal = self._make_calendar("Standard", [ex])
        mock_project = MagicMock()
        mock_project.getCalendars.return_value = [cal]

        xml_path = str(tmp_path / "proj.xml")
        handler._patch_save_cal_exc_names(mock_project, xml_path)

        sidecar = xml_path + ".cal-exc-names.json"
        assert os.path.exists(sidecar)

    def test_save_sidecar_contains_entry(self, tmp_path):
        """The sidecar JSON contains one entry for the named exception."""
        import json
        handler, _ = _handler()
        ex = self._make_exception(name="New Year", from_date="2025-01-01", to_date="2025-01-01")
        cal = self._make_calendar("Standard", [ex])
        mock_project = MagicMock()
        mock_project.getCalendars.return_value = [cal]

        xml_path = str(tmp_path / "proj.xml")
        handler._patch_save_cal_exc_names(mock_project, xml_path)

        with open(xml_path + ".cal-exc-names.json", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["cal"] == "Standard"
        assert data[0]["from"] == "2025-01-01"
        assert data[0]["name"] == "New Year"

    def test_save_skips_exceptions_without_names(self, tmp_path):
        """Exceptions with no name (None/empty) are omitted from the sidecar."""
        import json
        handler, _ = _handler()
        ex_no_name = self._make_exception(name="", from_date="2025-06-01", to_date="2025-06-01")
        ex_named   = self._make_exception(name="Holiday", from_date="2025-07-04", to_date="2025-07-04")
        cal = self._make_calendar("Standard", [ex_no_name, ex_named])
        mock_project = MagicMock()
        mock_project.getCalendars.return_value = [cal]

        xml_path = str(tmp_path / "proj.xml")
        handler._patch_save_cal_exc_names(mock_project, xml_path)

        with open(xml_path + ".cal-exc-names.json", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 1
        assert data[0]["name"] == "Holiday"

    def test_save_removes_stale_sidecar_when_no_entries(self, tmp_path):
        """If no named exceptions exist the sidecar file is removed if present."""
        handler, _ = _handler()
        ex = self._make_exception(name="", from_date="2025-01-01", to_date="2025-01-01")
        cal = self._make_calendar("Standard", [ex])
        mock_project = MagicMock()
        mock_project.getCalendars.return_value = [cal]

        xml_path = str(tmp_path / "proj.xml")
        sidecar = xml_path + ".cal-exc-names.json"
        # Create a stale sidecar
        with open(sidecar, "w") as f:
            f.write("[]")

        handler._patch_save_cal_exc_names(mock_project, xml_path)
        assert not os.path.exists(sidecar)

    def test_load_missing_sidecar_is_noop(self, tmp_path):
        """_patch_load_cal_exc_names does nothing when the sidecar is absent."""
        handler, _ = _handler()
        mock_project = MagicMock()
        mock_project.getCalendars.return_value = []

        # Should not raise even without sidecar
        handler._patch_load_cal_exc_names(mock_project, str(tmp_path / "proj.xml"))
        mock_project.getCalendars.assert_not_called()

    def test_load_calls_set_name_on_matching_exception(self, tmp_path):
        """_patch_load_cal_exc_names calls setName() for matching exceptions."""
        import json
        handler, _ = _handler()

        xml_path = str(tmp_path / "proj.xml")
        sidecar = xml_path + ".cal-exc-names.json"
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump([{"cal": "Standard", "from": "2025-12-25",
                        "to": "2025-12-25", "name": "Christmas"}], f)

        ex = self._make_exception(name="", from_date="2025-12-25", to_date="2025-12-25")
        cal = self._make_calendar("Standard", [ex])
        mock_project = MagicMock()
        mock_project.getCalendars.return_value = [cal]

        handler._patch_load_cal_exc_names(mock_project, xml_path)
        ex.setName.assert_called_once_with("Christmas")

    def test_load_skips_exceptions_that_already_have_name(self, tmp_path):
        """_patch_load_cal_exc_names does not overwrite existing names."""
        import json
        handler, _ = _handler()

        xml_path = str(tmp_path / "proj.xml")
        sidecar = xml_path + ".cal-exc-names.json"
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump([{"cal": "Standard", "from": "2025-12-25",
                        "to": "2025-12-25", "name": "Christmas"}], f)

        ex = self._make_exception(name="Existing Name", from_date="2025-12-25",
                                  to_date="2025-12-25")
        cal = self._make_calendar("Standard", [ex])
        mock_project = MagicMock()
        mock_project.getCalendars.return_value = [cal]

        handler._patch_load_cal_exc_names(mock_project, xml_path)
        ex.setName.assert_not_called()

    def test_load_ignores_unmatched_entries(self, tmp_path):
        """Sidecar entries that don't match any exception are silently ignored."""
        import json
        handler, _ = _handler()

        xml_path = str(tmp_path / "proj.xml")
        sidecar = xml_path + ".cal-exc-names.json"
        with open(sidecar, "w", encoding="utf-8") as f:
            json.dump([{"cal": "Standard", "from": "2025-01-01",
                        "to": "2025-01-01", "name": "Holiday"}], f)

        # Calendar has a different date — no match
        ex = self._make_exception(name="", from_date="2025-06-15", to_date="2025-06-15")
        cal = self._make_calendar("Standard", [ex])
        mock_project = MagicMock()
        mock_project.getCalendars.return_value = [cal]

        handler._patch_load_cal_exc_names(mock_project, xml_path)
        ex.setName.assert_not_called()
