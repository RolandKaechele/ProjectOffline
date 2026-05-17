# -*- coding: utf-8 -*-
"""
Generate DOORS DSF requirement files for Project Offline.

DSF (DOORS Sync Format) is a tab-separated text format with sections
delimited by <SECTION>\r\n ... </SECTION>\r\n.
Files are UTF-8 encoded with CRLF line endings.

Output: documentation/requirements/dsf/
"""

import os
import time

CRLF = "\r\n"
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "documentation", "requirements", "dsf")

# Unix timestamp for creation date (May 4, 2026)
CREATION_DATE = str(int(time.mktime((2026, 5, 4, 12, 0, 0, 0, 0, 0))))

# ---------------------------------------------------------------------------
# DSF builder helpers
# ---------------------------------------------------------------------------

def _section(name, columns, rows):
    """Build one DSF section as a string with CRLF line endings."""
    lines = []
    lines.append("<{}>".format(name))
    lines.append("\t".join(columns))
    for row in rows:
        cells = []
        for col in columns:
            cells.append(str(row.get(col, "")))
        lines.append("\t".join(cells))
    lines.append("</{}>".format(name))
    return CRLF.join(lines) + CRLF


def _fileinfo(prefix, module, description, creator="Project Offline"):
    columns = [
        "Scriptversion", "Encoding", "Module", "Prefix", "Description",
        "Creation Date", "Creator", "Steps", "Internal links module",
        "Version number", "Export type", "Suffix", "Annotation"
    ]
    row = {
        "Scriptversion": "",
        "Encoding": "UTF-8",
        "Module": module,
        "Prefix": prefix,
        "Description": description,
        "Creation Date": CREATION_DATE,
        "Creator": creator,
        "Steps": "0",
        "Internal links module": "",
        "Version number": "1.0",
        "Export type": "6.1",
        "Suffix": "",
        "Annotation": "",
    }
    return _section("FILEINFO", columns, [row])


def _types():
    columns = ["Name", "Basetype", "minValue", "maxValue", "Strings", "Values", "Colors"]
    rows = [
        {"Name": "t_Status_Sup", "Basetype": "Enumeration", "minValue": "",
         "maxValue": "", "Strings": "open,clarify,approved,to be deleted",
         "Values": "", "Colors": ""},
        {"Name": "t_Status_ZF", "Basetype": "Enumeration", "minValue": "",
         "maxValue": "", "Strings": "new,modified,to be clarified,aligned,to be deleted",
         "Values": "", "Colors": ""},
    ]
    return _section("TYPES", columns, rows)


def _attributes():
    columns = ["Name", "Type", "Definitions", "Default"]
    rows = [
        {"Name": "a_EB_PO_Status", "Type": "t_Status_Sup", "Definitions": "", "Default": ""},
        {"Name": "a_ZF_PO_Status", "Type": "t_Status_ZF", "Definitions": "", "Default": ""},
    ]
    return _section("ATTRIBUTES", columns, rows)


def _empty_section(name, columns):
    return _section(name, columns, [])


def _objects(objects):
    columns = [
        "Object_Heading", "Object_Text", "aRequirementObjectType",
        "Section_number", "ID.Status", "aResponsibility",
        "a_EB_PO_Status", "a_ZF_PO_Status"
    ]
    return _section("OBJECTS", columns, objects)


def _heading(text, section, id_str):
    return {
        "Object_Heading": text,
        "Object_Text": "",
        "aRequirementObjectType": "",
        "Section_number": section,
        "ID.Status": "{}_Heading.0".format(id_str),
        "aResponsibility": "Not relevant",
        "a_EB_PO_Status": "",
        "a_ZF_PO_Status": "",
    }


def _info(text, section, req_id):
    return {
        "Object_Heading": "",
        "Object_Text": text,
        "aRequirementObjectType": "information",
        "Section_number": section,
        "ID.Status": "{}.0".format(req_id),
        "aResponsibility": "Not relevant",
        "a_EB_PO_Status": "",
        "a_ZF_PO_Status": "",
    }


def _func(text, section, req_id):
    return {
        "Object_Heading": "",
        "Object_Text": text,
        "aRequirementObjectType": "functional requirement",
        "Section_number": section,
        "ID.Status": "{}.0".format(req_id),
        "aResponsibility": "Not relevant",
        "a_EB_PO_Status": "approved",
        "a_ZF_PO_Status": "aligned",
    }


def _nfunc(text, section, req_id):
    return {
        "Object_Heading": "",
        "Object_Text": text,
        "aRequirementObjectType": "non functional requirement",
        "Section_number": section,
        "ID.Status": "{}.0".format(req_id),
        "aResponsibility": "Not relevant",
        "a_EB_PO_Status": "approved",
        "a_ZF_PO_Status": "aligned",
    }


def build_dsf(prefix, module, description, objects):
    parts = []
    parts.append(_fileinfo(prefix, module, description))
    parts.append(_types())
    parts.append(_attributes())
    parts.append(_empty_section("ATTRIBUTEVALUES", ["Attribute", "Value"]))
    parts.append(_empty_section("PICTURES", ["Object", "FileName"]))
    parts.append(_empty_section("PASSEDATTRIBUTES", ["Name"]))
    parts.append(_empty_section("LINKMODULES", ["Name"]))
    parts.append(_empty_section("FORMALMODULES", ["Name"]))
    parts.append(_empty_section("OBJECT_IDS", ["From", "To"]))
    parts.append(_objects(objects))
    return "".join(parts)


def write_dsf(filename, content):
    os.makedirs(OUT_DIR, exist_ok=True)
    filepath = os.path.join(OUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content.encode("utf-8"))
    print("Written: {}".format(filepath))


# ===========================================================================
# The DSF files in documentation/requirements/dsf/ are the single source of
# truth for requirement content.  Edit them directly with a text editor or
# DOORS tooling.  The builder helpers above (_section, _fileinfo, _types,
# _heading, _func, _nfunc, ...) remain available for scripted DSF creation
# if new packages need to be added programmatically.
#
# Downstream generation:
#   1. venv\Scripts\python.exe tools\generate_rxml_requirements.py
#      -> reads *.dsf -> writes documentation\requirements\requirement_collection.rxml
#         and requirement_additional_informations.ixml
#   2. venv\Scripts\python.exe tools\generate_dsi_elements.py
#      -> reads rxml -> appends DSI elements and populates ixml
# ===========================================================================

if __name__ == "__main__":
    import glob
    dsf_files = sorted(glob.glob(os.path.join(OUT_DIR, "*.dsf")))
    if dsf_files:
        print("DSF files already exist in {}".format(OUT_DIR))
        print("Edit them directly; then run generate_rxml_requirements.py to regenerate the rxml.")
        for f in dsf_files:
            print("  {}".format(os.path.basename(f)))
    else:
        print("No DSF files found in {}.".format(OUT_DIR))
        print("Use the builder helpers in this script to create them programmatically.")

