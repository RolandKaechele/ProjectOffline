# -*- coding: utf-8 -*-
"""
Validate all DSF files in documentation/requirements/dsf/.

Checks performed
----------------
Per-file:
  [F01] File is valid UTF-8.
  [F02] All required sections are present.
  [F03] FILEINFO Module is non-empty and follows PO_NN_CamelCase.
  [F04] FILEINFO Module number matches the filename number.
  [F05] FILEINFO Prefix is non-empty and matches PO-XXX- pattern.

Per-object row:
  [R01] Object_Heading and Object_Text are not both non-empty.
  [R02] aRequirementObjectType is a recognised value (or empty for headings).
  [R03] Section_number matches \\d+(\\.\\d+)*.
  [R04] aResponsibility is 'Not relevant'.
  [R05] a_EB_PO_Status is a recognised value.
  [R06] a_ZF_PO_Status is a recognised value.
  [R07] Heading ID.Status matches <section_underscored>_Heading.0.
  [R08] Non-heading ID.Status matches the PO-...-NNN.0 pattern.
  [R09] Functional / non-functional requirement has non-empty Object_Text.
  [R10] No duplicate ID.Status within the file.

Cross-file:
  [X01] No duplicate requirement / info IDs across all files.

Usage:
  python tools/validate_dsf.py
  python tools/validate_dsf.py documentation/requirements/dsf/PO_15_jira_integration.dsf
"""

from __future__ import print_function
import glob
import os
import re
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
DSF_DIR = os.path.join(PROJECT_ROOT, "documentation", "requirements", "dsf")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REQUIRED_SECTIONS = [
    "FILEINFO", "TYPES", "ATTRIBUTES", "ATTRIBUTEVALUES",
    "PICTURES", "PASSEDATTRIBUTES", "LINKMODULES", "FORMALMODULES",
    "OBJECT_IDS", "OBJECTS",
]

VALID_REQ_TYPES = {
    "functional requirement",
    "non functional requirement",
    "information",
    "",          # headings have empty type
}

VALID_EB_STATUS = {"", "open", "clarify", "approved", "to be deleted"}
VALID_ZF_STATUS = {"", "new", "modified", "to be clarified", "aligned", "to be deleted"}

# PO_NN_CamelCase or PO_NN_Snake_Case (underscores allowed after the number)
RE_MODULE = re.compile(r'^PO_(\d+)_[A-Za-z][A-Za-z0-9_]*$')
# PO-SOMETHING-  (one or more dash-separated uppercase-letter groups)
RE_PREFIX = re.compile(r'^PO(-[A-Z][A-Z0-9]*)+- ?$')
# 1  /  1.2  /  3.4.5
RE_SECTION = re.compile(r'^\d+(\.\d+)*$')
# PO-CAT(-CAT)*-NNN[a].revision  e.g. PO-DBG-001.0  PO-J2P-035.0  PO-TASK-014a.0  PO-AD-007.1
RE_REQ_ID = re.compile(r'^PO(-[A-Z][A-Z0-9]*){1,4}-\d+[a-z]?\.\d+$')


# ---------------------------------------------------------------------------
# DSF parser  (same logic as generate_rxml_requirements.py)
# ---------------------------------------------------------------------------
def parse_dsf(filepath):
    """Return dict {section_name: {'headers': [...], 'rows': [...]}}."""
    sections = {}
    current = None
    headers = None
    rows = []
    with open(filepath, "r", encoding="utf-8-sig") as fh:
        for raw in fh:
            line = raw.rstrip("\r\n")
            if (line.startswith("<") and line.endswith(">")
                    and not line.startswith("</") and "\t" not in line):
                current = line[1:-1]
                headers = None
                rows = []
            elif line.startswith("</") and line.endswith(">"):
                if current is not None:
                    sections[current] = {"headers": headers or [], "rows": rows}
                current = None
                headers = None
                rows = []
            elif current is not None:
                cells = line.split("\t")
                if headers is None:
                    headers = cells
                else:
                    row = {headers[i]: (cells[i] if i < len(cells) else "")
                           for i in range(len(headers))}
                    rows.append(row)
    return sections


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _section_to_heading_id(section):
    """'2.1' -> '2_1_Heading.0'"""
    return "{}_Heading.0".format(section.replace(".", "_"))


class _Results:
    def __init__(self, filename):
        self.filename = filename
        self.errors = []
        self.warnings = []

    def error(self, code, msg):
        self.errors.append("[{}] {}".format(code, msg))

    def warn(self, code, msg):
        self.warnings.append("[{}] {}".format(code, msg))

    def ok(self):
        return not self.errors


# ---------------------------------------------------------------------------
# Single-file validation
# ---------------------------------------------------------------------------
def validate_file(filepath):
    """Validate one DSF file.  Returns a _Results object."""
    filename = os.path.basename(filepath)
    res = _Results(filename)

    # [F01] UTF-8 readability
    try:
        raw_bytes = open(filepath, "rb").read()
        raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        res.error("F01", "File is not valid UTF-8: {}".format(exc))
        return res  # can't continue

    sections = parse_dsf(filepath)

    # [F02] Required sections
    for sec in REQUIRED_SECTIONS:
        if sec not in sections:
            res.error("F02", "Missing required section <{}>".format(sec))

    # [F03] Module format
    fi_rows = sections.get("FILEINFO", {}).get("rows", [])
    fi = fi_rows[0] if fi_rows else {}
    module = fi.get("Module", "").strip()
    if not module:
        res.error("F03", "FILEINFO Module is empty")
    else:
        m = RE_MODULE.match(module)
        if not m:
            res.error("F03", "FILEINFO Module '{}' does not match PO_NN_CamelCase".format(module))
        else:
            # [F04] Module number vs filename number
            module_num = m.group(1)
            # Filename: PO_02_app_debug.dsf -> leading number group
            fn_match = re.match(r'^PO_(\d+)_', filename, re.IGNORECASE)
            if fn_match:
                fn_num = fn_match.group(1)
                # Normalise: '02' vs '2' -> compare as int
                if int(module_num) != int(fn_num):
                    res.error("F04",
                              "FILEINFO Module number ({}) does not match filename number ({})".format(
                                  module_num, fn_num))
            else:
                res.warn("F04", "Filename '{}' does not follow PO_NN_ convention".format(filename))

    # [F05] Prefix format
    prefix = fi.get("Prefix", "").strip()
    if not prefix:
        res.error("F05", "FILEINFO Prefix is empty")
    elif not RE_PREFIX.match(prefix):
        res.error("F05", "FILEINFO Prefix '{}' does not match PO-XXX- pattern".format(prefix))

    # --- OBJECTS rows ---
    obj_rows = sections.get("OBJECTS", {}).get("rows", [])
    seen_ids = {}   # id -> row_number (1-based within OBJECTS)

    for row_idx, row in enumerate(obj_rows, start=1):
        heading  = row.get("Object_Heading", "").strip()
        text     = row.get("Object_Text", "").strip()
        req_type = row.get("aRequirementObjectType", "").strip()
        section  = row.get("Section_number", "").strip()
        id_status= row.get("ID.Status", "").strip()
        resp     = row.get("aResponsibility", "").strip()
        eb_stat  = row.get("a_EB_PO_Status", "").strip()
        zf_stat  = row.get("a_ZF_PO_Status", "").strip()

        # Skip entirely blank trailer rows
        if not heading and not text and not section and not id_status:
            continue

        is_heading = bool(heading)
        label = "row {} (ID={})".format(row_idx, id_status or "<empty>")

        # [R01] Heading and Text both non-empty
        if heading and text:
            res.error("R01", "{}: Object_Heading and Object_Text are both non-empty".format(label))

        # [R02] aRequirementObjectType
        if req_type not in VALID_REQ_TYPES:
            res.error("R02", "{}: aRequirementObjectType '{}' is not recognised".format(label, req_type))
        if is_heading and req_type:
            res.warn("R02", "{}: heading row has non-empty aRequirementObjectType '{}'".format(label, req_type))
        if not is_heading and not req_type:
            res.error("R02", "{}: non-heading row has empty aRequirementObjectType".format(label))

        # [R03] Section_number
        if not section:
            res.error("R03", "{}: Section_number is empty".format(label))
        elif not RE_SECTION.match(section):
            res.error("R03", "{}: Section_number '{}' is not a valid dot-separated number".format(label, section))

        # [R04] aResponsibility
        if resp != "Not relevant":
            res.error("R04", "{}: aResponsibility is '{}' (expected 'Not relevant')".format(label, resp))

        # [R05] a_EB_PO_Status
        if eb_stat not in VALID_EB_STATUS:
            res.error("R05", "{}: a_EB_PO_Status '{}' is not recognised".format(label, eb_stat))

        # [R06] a_ZF_PO_Status
        if zf_stat not in VALID_ZF_STATUS:
            res.error("R06", "{}: a_ZF_PO_Status '{}' is not recognised".format(label, zf_stat))

        # [R07] Heading ID format
        if is_heading and section:
            expected_id = _section_to_heading_id(section)
            if id_status != expected_id:
                res.error("R07", "{}: heading ID.Status '{}' should be '{}'".format(
                    label, id_status, expected_id))

        # [R08] Non-heading ID format
        if not is_heading:
            if not id_status:
                res.error("R08", "{}: non-heading row has empty ID.Status".format(label))
            elif not RE_REQ_ID.match(id_status):
                res.error("R08", "{}: ID.Status '{}' does not match PO-CAT-NNN.0 pattern".format(
                    label, id_status))
            elif not id_status.endswith(".0"):
                res.warn("R08", "{}: ID.Status '{}' has a non-zero revision suffix (expected .0)".format(
                    label, id_status))

        # [R09] Functional / NFR must have text
        if req_type in ("functional requirement", "non functional requirement") and not text:
            res.error("R09", "{}: {} row has empty Object_Text".format(label, req_type))

        # [R10] Duplicate IDs within file
        if id_status:
            if id_status in seen_ids:
                res.error("R10", "Duplicate ID.Status '{}' (rows {} and {})".format(
                    id_status, seen_ids[id_status], row_idx))
            else:
                seen_ids[id_status] = row_idx

    return res


# ---------------------------------------------------------------------------
# Cross-file duplicate check
# ---------------------------------------------------------------------------
def check_cross_file_duplicates(all_results_with_ids):
    """
    all_results_with_ids: list of (filename, {id: row_num}) dicts.
    Returns list of error strings.
    """
    global_ids = {}  # id -> filename
    errors = []
    for filename, seen_ids in all_results_with_ids:
        for id_status in seen_ids:
            # Skip heading IDs — those are expected to repeat across files
            if id_status.endswith("_Heading.0"):
                continue
            if id_status in global_ids:
                errors.append(
                    "[X01] Duplicate ID '{}' in '{}' and '{}'".format(
                        id_status, global_ids[id_status], filename))
            else:
                global_ids[id_status] = filename
    return errors


# ---------------------------------------------------------------------------
# Collect IDs from parsed rows (for cross-file check)
# ---------------------------------------------------------------------------
def _collect_ids(filepath):
    sections = parse_dsf(filepath)
    obj_rows = sections.get("OBJECTS", {}).get("rows", [])
    seen = {}
    for row_idx, row in enumerate(obj_rows, start=1):
        id_status = row.get("ID.Status", "").strip()
        if id_status and id_status not in seen:
            seen[id_status] = row_idx
    return seen


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(args):
    if args:
        # Validate specified files
        paths = []
        for a in args:
            if os.path.isfile(a):
                paths.append(a)
            else:
                expanded = glob.glob(a)
                if expanded:
                    paths.extend(sorted(expanded))
                else:
                    print("WARNING: not found: {}".format(a))
        if not paths:
            print("No files to validate.")
            return 1
        cross_check = len(paths) > 1
    else:
        paths = sorted(glob.glob(os.path.join(DSF_DIR, "*.dsf")))
        if not paths:
            print("No *.dsf files found in {}".format(DSF_DIR))
            return 1
        cross_check = True

    total_errors = 0
    total_warnings = 0
    all_ids = []  # for cross-file check

    for filepath in paths:
        res = validate_file(filepath)
        if cross_check:
            all_ids.append((res.filename, _collect_ids(filepath)))

        header = "{}  {}".format(
            "OK " if res.ok() else "ERR",
            res.filename,
        )
        if res.errors or res.warnings:
            print(header)
            for e in res.errors:
                print("  ERROR  {}".format(e))
            for w in res.warnings:
                print("  WARN   {}".format(w))
        else:
            print(header)

        total_errors += len(res.errors)
        total_warnings += len(res.warnings)

    # Cross-file duplicate check
    if cross_check:
        cross_errors = check_cross_file_duplicates(all_ids)
        for e in cross_errors:
            print("  ERROR  {}".format(e))
        total_errors += len(cross_errors)

    print("")
    print("Files checked : {}".format(len(paths)))
    print("Errors        : {}".format(total_errors))
    print("Warnings      : {}".format(total_warnings))

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
