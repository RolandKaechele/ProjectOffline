# -*- coding: utf-8 -*-
r"""
Generate DOORS rxml requirement files for Project Offline.

These rxml files are loadable by:
  d:\Projekte\ZFF\tools\requirementProcessTool_2.1.0\EAAReqGui\mainGui.py

Usage:
  python tools\generate_rxml_requirements.py
  -> generates documentation\requirements\requirement_collection.rxml
                               requirement_additional_informations.ixml
                               requirements\rtf\   (empty folder)

How the loader works:
  mainGui.py -> DsfRepresentation(filepath)
             -> xpath(".//GROUP_OBJECTS/..") finds each package element
             -> element path minus /root/ -> package name list
             -> each OBJECTS child attr becomes a RequirementObject

rxml OBJECTS attributes used by the tool:
  ID.Status          primary key e.g. "1.0"; getReqId() => "{prefix}{n:03d}"
  Section_number     "1", "1.1", "2.1", "2.1.1"  -> drives tree hierarchy
  Object_Heading     non-empty => heading node in tree (type must be empty)
  Object_Text        requirement text (plain or RTF)
  aRequirementObjectType  "functional requirement" | "non functional requirement"
                          | "information" | ""
  a_EB_PO_Status     "approved" | "open" | "" etc.
  a_ZF_PO_Status     "aligned" | "new" | "" etc.
  a_RequestedInCR_PO CR reference string
  a_EB4ZF_PO_Comment comment from EB to ZF
  a_ZF4EB_PO_Comment comment from ZF to EB
  RequirementParent  DSI parent req ID (empty for us)
"""

from __future__ import print_function
import glob
import os
import re
import sys
import time

try:
    from lxml import etree as ET # type: ignore
    LXML = True
except ImportError:
    import xml.etree.ElementTree as ET
    LXML = False

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
OUT_DIR = os.path.join(PROJECT_ROOT, "documentation", "requirements")
RXML_PATH = os.path.join(OUT_DIR, "requirement_collection.rxml")   # manifest
IXML_PATH = os.path.join(OUT_DIR, "requirement_additional_informations.ixml")
PKG_DIR   = os.path.join(OUT_DIR, "packageRxml")                    # per-package files
RTF_DIR   = os.path.join(OUT_DIR, "requirements", "rtf")

CREATION_DATE = str(int(time.mktime((2026, 5, 4, 12, 0, 0, 0, 0, 0))))

# ---------------------------------------------------------------------------
# DSF source files — auto-discovered from DSF_DIR at runtime
# The DSF files in documentation/requirements/dsf/ are the single source of
# truth for requirement content.  Edit them there; run this script to
# regenerate requirement_collection.rxml.
#
# xml_name  is derived from the Module FILEINFO field by stripping the
#            leading 'PO_NN_' prefix and converting CamelCase to Under_Score.
# rxml_prefix is read directly from the Prefix FILEINFO field in each DSF file
#            (e.g. 'PO-CPM-' stored in the Prefix column).
# ---------------------------------------------------------------------------

DSF_DIR = os.path.join(OUT_DIR, "dsf")


def _derive_xml_name(module):
    """Convert a DSF Module field to an xml element name.

    'PO_07_AdvancedFeatures' -> 'Advanced_Features'
    """
    name = re.sub(r'^PO_\d+_', '', module)
    name = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name)
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    return name


# ---------------------------------------------------------------------------
# DSF parser
# ---------------------------------------------------------------------------

def parse_dsf(filepath):
    """
    Parse a DSF file and return a dict mapping section name to a dict with
    keys 'headers' (list of column names) and 'rows' (list of row-dicts).

    DSF section format::

        <SECTIONNAME>
        col1\tcol2\tcol3
        val1\tval2\tval3
        </SECTIONNAME>
    """
    sections = {}
    current = None
    headers = None
    rows = []
    with open(filepath, 'r', encoding='utf-8-sig') as fh:
        for raw in fh:
            line = raw.rstrip('\r\n')
            # Section open tag: <NAME> (no tabs, not a closing tag)
            if (line.startswith('<') and line.endswith('>')
                    and not line.startswith('</') and '\t' not in line):
                current = line[1:-1]
                headers = None
                rows = []
            # Section close tag
            elif line.startswith('</') and line.endswith('>'):
                if current:
                    sections[current] = {'headers': headers or [], 'rows': rows}
                current = None
                headers = None
                rows = []
            elif current is not None:
                cells = line.split('\t')
                if headers is None:
                    headers = cells
                else:
                    row = {headers[i]: (cells[i] if i < len(cells) else '')
                           for i in range(len(headers))}
                    rows.append(row)
    return sections


def load_dsf_packages():
    """
    Auto-discover all *.dsf files in DSF_DIR (sorted by filename) and load them.
    Returns a list of package dicts with keys:
        xml_name, prefix, module, description, reqs
    where reqs is a list of (section, heading, text, req_type, eb_status, zf_status, id_status).
    """
    dsf_paths = sorted(glob.glob(os.path.join(DSF_DIR, '*.dsf')))
    if not dsf_paths:
        print('WARNING: No *.dsf files found in {}'.format(DSF_DIR))
    packages = []
    for path in dsf_paths:
        dsf_file = os.path.basename(path)
        secs = parse_dsf(path)

        fi_rows = secs.get('FILEINFO', {}).get('rows', [])
        fi = fi_rows[0] if fi_rows else {}
        module = fi.get('Module', '').strip()
        description = fi.get('Description', '').strip()

        xml_name = _derive_xml_name(module) if module else dsf_file.replace('.dsf', '')

        rxml_prefix = fi.get('Prefix', '').strip()
        if not rxml_prefix:
            print('WARNING: Empty Prefix in {} — skipping'.format(dsf_file))
            continue

        obj_rows = secs.get('OBJECTS', {}).get('rows', [])
        reqs = []
        for row in obj_rows:
            section   = row.get('Section_number', '').strip()
            heading   = row.get('Object_Heading', '').strip()
            text      = row.get('Object_Text', '').strip()
            req_type  = row.get('aRequirementObjectType', '').strip()
            eb_status = row.get('a_EB_PO_Status', '').strip()
            zf_status = row.get('a_ZF_PO_Status', '').strip()
            id_status = row.get('ID.Status', '').strip()
            if not section and not heading and not text:
                continue  # skip blank trailer lines
            reqs.append((section, heading, text, req_type, eb_status, zf_status, id_status))

        packages.append({
            'xml_name':    xml_name,
            'prefix':      rxml_prefix,
            'module':      module,
            'description': description,
            'reqs':        reqs,
        })
        print('  Loaded {} -> {} ({}) ({} objects)'.format(
            dsf_file, xml_name, rxml_prefix, len(reqs)))
    return packages


# ---------------------------------------------------------------------------
# XML building helpers
# ---------------------------------------------------------------------------

def _sub(parent, tag, attrib=None):
    e = ET.SubElement(parent, tag)
    if attrib:
        for k, v in attrib.items():
            e.set(k, v)
    return e


def _build_group_types(parent):
    g = _sub(parent, "GROUP_TYPES")
    for t in [
        ("teRequirementObjectType", "Enumeration",
         "functional requirement,non functional requirement,information"),
        ("t_Status_Sup", "Enumeration",
         "open,clarify,approved,to be deleted"),
        ("t_Status_ZF", "Enumeration",
         "new,modified,to be clarified,aligned,to be deleted"),
        ("teVariant", "Enumeration", ""),
    ]:
        _sub(g, "TYPES", {
            "Name": t[0], "Basetype": t[1], "minValue": "", "maxValue": "",
            "Strings": t[2], "Values": "", "Colors": "",
        })


def _build_group_attributes(parent):
    g = _sub(parent, "GROUP_ATTRIBUTES")
    attrs = [
        ("aRequirementObjectType", "teRequirementObjectType", ""),
        ("Object_Text",            "Text",                    "System Attribute"),
        ("Object_Heading",         "String",                  "System Attribute"),
        ("a_EB_Variant",           "teVariant",               ""),
        ("a_EB_PO_Status",         "t_Status_Sup",            ""),
        ("a_ZF_PO_Status",         "t_Status_ZF",             ""),
        ("a_RequestedInCR_PO",     "Text",                    ""),
        ("a_EB4ZF_PO_Comment",     "Text",                    ""),
        ("a_ZF4EB_PO_Comment",     "Text",                    ""),
    ]
    for name, typ, desc in attrs:
        _sub(g, "ATTRIBUTES", {
            "Default": "", "Definitions": "270",
            "Description": desc, "Name": name, "Type": typ,
        })


def _build_group_fileinfo(parent, prefix, module, description):
    g = _sub(parent, "GROUP_FILEINFO")
    _sub(g, "FILEINFO", {
        "Annotation":              "-",
        "Creation_Date":           CREATION_DATE,
        "Creator":                 "Project Offline",
        "Description":             description,
        "Encoding":                "65001",
        "Export_type":             "6.1",
        "Internal_links_module":   "",
        "Module":                  module,
        "Prefix":                  prefix,
        "Scriptversion":           "1.0",
        "Steps":                   "0",
        "Suffix":                  "-",
        "Version_number":          "1.0",
    })


def _build_group_objects(parent, reqs_data):
    g = _sub(parent, "GROUP_OBJECTS")
    req_counter = 1   # counts requirement rows only (not headings)
    for (section, heading, text, req_type, eb_status, zf_status, dsf_id_status) in reqs_data:
        if heading:
            # Heading rows: keep the DSF heading ID (e.g. '1_Heading.0', '1_1_Heading.0').
            # The tool parses these via regex '^(\d+)_(.*)' and renders them as tree nodes.
            id_status = dsf_id_status if dsf_id_status else "{}_Heading.0".format(req_counter)
        else:
            # Requirement rows: use a sequential numeric ID so requirementProcessTool's
            # getReqId() computes "{prefix}{n:03d}" (e.g. "PO-NFR-001") correctly.
            # Alphanumeric IDs would cause getReqId() to double-prefix them and break
            # DSI parent-child linking (searchParentRequirement never finds the parent).
            id_status = "{}.0".format(req_counter)
            req_counter += 1
        _sub(g, "OBJECTS", {
            "ID.Status":              id_status,
            "Object_Heading":         heading,
            "Object_Text":            text,
            "Section_number":         section,
            "aRequirementObjectType": req_type,
            "a_EB_Variant":           "",
            "a_EB_PO_Status":         eb_status,
            "a_ZF_PO_Status":         zf_status,
            "a_RequestedInCR_PO":     "",
            "a_EB4ZF_PO_Comment":     "",
            "a_ZF4EB_PO_Comment":     "",
            "RequirementParent":      "",
        })
    return g


def build_package_rxml(pkg):
    """
    Build a single packageRxml/<name>.rxml ElementTree for one package.
    Structure mirrors reference: <root><Project_Offline depth=0><PackageName depth=1>...
    """
    root = ET.Element("root")
    top = _sub(root, "Project_Offline")
    top.set("depth", "0")
    pkg_elem = _sub(top, pkg["xml_name"])
    pkg_elem.set("depth", "1")
    _build_group_types(pkg_elem)
    _build_group_attributes(pkg_elem)
    _sub(pkg_elem, "GROUP_ATTRIBUTEVALUES")
    _build_group_fileinfo(pkg_elem, pkg["prefix"], pkg["module"], pkg["description"])
    _sub(pkg_elem, "GROUP_FORMALMODULES")
    _sub(pkg_elem, "GROUP_LINKMODULES")
    _sub(pkg_elem, "GROUP_PASSEDATTRIBUTES")
    _sub(pkg_elem, "GROUP_PICTURES")
    _sub(pkg_elem, "GROUP_OBJECT_IDS")
    _build_group_objects(pkg_elem, pkg["reqs"])
    return ET.ElementTree(root)


def build_manifest_rxml(pkg_filenames):
    """
    Build the top-level requirement_collection.rxml manifest.
    It only lists the relative paths to all packageRxml files and has
    an ADDITIONAL_INFORMATION stub — matching the reference project layout.
    """
    root = ET.Element("root")
    pfp = _sub(root, "PACKAGE_FILE_PATHES")
    for fname in pkg_filenames:
        _sub(pfp, "ELEMENT", {"PATH": "packageRxml\\" + fname})
    ai = _sub(root, "ADDITIONAL_INFORMATION")
    _sub(ai, "CUSTOM_COMPONENTS")
    _sub(ai, "IMPORT_FILE_PATHS")
    return ET.ElementTree(root)


def build_rxml(packages):
    """Legacy: build monolithic rxml (kept for compatibility, not used in __main__)."""
    root = ET.Element("root")
    top = _sub(root, "Project_Offline")
    top.set("depth", "0")
    for pkg in packages:
        pkg_elem = _sub(top, pkg["xml_name"])
        pkg_elem.set("depth", "1")
        _build_group_types(pkg_elem)
        _build_group_attributes(pkg_elem)
        _sub(pkg_elem, "GROUP_ATTRIBUTEVALUES")
        _build_group_fileinfo(pkg_elem, pkg["prefix"], pkg["module"], pkg["description"])
        _sub(pkg_elem, "GROUP_FORMALMODULES")
        _sub(pkg_elem, "GROUP_LINKMODULES")
        _sub(pkg_elem, "GROUP_PASSEDATTRIBUTES")
        _sub(pkg_elem, "GROUP_PICTURES")
        _sub(pkg_elem, "GROUP_OBJECT_IDS")
        _build_group_objects(pkg_elem, pkg["reqs"])
    return ET.ElementTree(root)

def build_ixml():
    root = ET.Element("root")
    analyze = _sub(root, "ANALYZE")
    for tag in ["WHAT_DONE", "WHERE_DONE", "WHAT_IMPACT", "TEST_ATTRIBUTE",
                "WHERE_DONE_CATEGORY", "WHERE_DONE_VALUE", "WHERE_DONE_ARCHITECTURE_UNIT"]:
        _sub(analyze, tag)
    relation = _sub(root, "RELATION")
    for tag in ["DEPENDS_ON", "DEPENDS_ON_REASON"]:
        _sub(relation, tag)
    return ET.ElementTree(root)


def write_xml(tree, path, declaration=True):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if LXML:
        tree.write(path, xml_declaration=declaration, encoding="UTF-8", pretty_print=True)
    else:
        if sys.version_info[0] >= 3:
            ET.indent(tree.getroot())
        if declaration:
            with open(path, "wb") as f:
                f.write(b"<?xml version='1.0' encoding='UTF-8'?>\n")
                tree.write(f, encoding="unicode" if sys.version_info[0] >= 3 else "UTF-8")
        else:
            tree.write(path, encoding="UTF-8")
    print("Written: {}".format(path))


def count_reqs(packages):
    total = 0
    for pkg in packages:
        for (section, heading, text, req_type, eb_status, zf_status) in pkg["reqs"]:
            if req_type in ("functional requirement", "non functional requirement", "information"):
                total += 1
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Generating DOORS rxml from DSF source files...")
    print("DSF source: {}".format(DSF_DIR))
    print("Output:     {}".format(OUT_DIR))
    print("lxml available: {}".format(LXML))

    packages = load_dsf_packages()
    if not packages:
        print("ERROR: No DSF files loaded from {}".format(DSF_DIR))
        sys.exit(1)

    os.makedirs(PKG_DIR, exist_ok=True)
    os.makedirs(RTF_DIR, exist_ok=True)

    # Write one packageRxml file per package
    pkg_filenames = []
    for pkg in packages:
        fname = "requirement_collection_{}.rxml".format(pkg["xml_name"])
        pkg_path = os.path.join(PKG_DIR, fname)
        tree = build_package_rxml(pkg)
        write_xml(tree, pkg_path)
        pkg_filenames.append(fname)

    # Include DSI rxml in manifest if it already exists (generated by generate_dsi_elements.py)
    dsi_fname = "requirement_collection_DSI.rxml"
    if os.path.exists(os.path.join(PKG_DIR, dsi_fname)) and dsi_fname not in pkg_filenames:
        pkg_filenames.append(dsi_fname)

    # Write manifest requirement_collection.rxml
    manifest = build_manifest_rxml(pkg_filenames)
    write_xml(manifest, RXML_PATH)

    # Write requirement_additional_informations.ixml only if it does not exist yet.
    # After initial creation, generate_dsi_elements.py owns the ixml content (it
    # populates WHERE_DONE_CATEGORY, TEST_ATTRIBUTE, WHERE_DONE_ARCHITECTURE_UNIT
    # etc.).  Overwriting here would silently erase all those DSI entries.
    if not os.path.exists(IXML_PATH):
        ixml_tree = build_ixml()
        write_xml(ixml_tree, IXML_PATH)
    else:
        print("Skipped (already exists): {}".format(IXML_PATH))

    n_func  = sum(1 for p in packages for (s, h, t, rt, e, z, *_) in p["reqs"] if rt == "functional requirement")
    n_nfunc = sum(1 for p in packages for (s, h, t, rt, e, z, *_) in p["reqs"] if rt == "non functional requirement")
    n_info  = sum(1 for p in packages for (s, h, t, rt, e, z, *_) in p["reqs"] if rt == "information")
    n_head  = sum(1 for p in packages for (s, h, t, rt, e, z, *_) in p["reqs"] if rt == "" and h)

    print("\nSummary:")
    print("  Packages (sub-modules): {}".format(len(packages)))
    print("  Headings:               {}".format(n_head))
    print("  Functional reqs:        {}".format(n_func))
    print("  Non-functional reqs:    {}".format(n_nfunc))
    print("  Information items:      {}".format(n_info))
    print("  Total requirements:     {}".format(n_func + n_nfunc + n_info))
    print("\nLoad with:")
    print("  cd D:\\Projekte\\ZFF\\tools\\requirementProcessTool_2.1.0")
    print("  python EAAReqGui\\mainGui.py -i \"{}\"".format(RXML_PATH))


if __name__ == "__main__":
    main()


