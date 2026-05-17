r"""
generate_dsi_elements.py

Generates DSI (Detailed Software Implementation) child requirements for each
functional/non-functional requirement in the rxml, and populates the ixml with
TEST_ATTRIBUTE, WHAT_DONE, and WHERE_DONE_ARCHITECTURE_UNIT entries.

The DSI OBJECTS are added to a new "InheritedDetailedRequirements" container
in the main rxml, with one sub-package per source-package, mirroring the
structure found in the reference project.

Run with venv Python:
    venv\Scripts\python.exe tools\generate_dsi_elements.py
"""
from __future__ import print_function

import os
import sys
import time
import copy

from lxml import etree as ET # type: ignore

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
REQ_DIR = os.path.join(PROJECT_ROOT, 'documentation', 'requirements')
RXML_PATH = os.path.join(REQ_DIR, 'requirement_collection.rxml')        # manifest
IXML_PATH = os.path.join(REQ_DIR, 'requirement_additional_informations.ixml')
PKG_DIR   = os.path.join(REQ_DIR, 'packageRxml')
DSI_RXML_PATH = os.path.join(PKG_DIR, 'requirement_collection_DSI.rxml')

# ---------------------------------------------------------------------------
# Mapping: package name -> primary source file(s)
# Used to populate DSI Object_Text and WHERE_DONE_ARCHITECTURE_UNIT.
# This is architectural knowledge that is not stored in the DSF files.
# Each package lists ALL source files that implement its requirements.
# One DSI child element is generated per source file per requirement.
# ---------------------------------------------------------------------------
PACKAGE_SRC_MAP = {
    'System_Overview': [
        ('src/main.py',      'Application entry point, main() and JDK setup'),
        ('src/ui.py',        'Main window layout, MainWindow class'),
        ('src/app_tabs.py',  'Tab management and view switching'),
        ('src/logic.py',     'Core application logic, ProjectLogic class'),
        ('src/ribbon.py',    'Office-style ribbon, ProjectRibbon class'),
        ('src/toolbar.py',   'Main toolbar, ProjectToolBar class'),
        ('src/menu.py',      'Menu bar, ProjectMenuBar class'),
        ('src/icons.py',     'Icon factory functions'),
        ('src/_version.py',  'Build version string, BUILD_VERSION constant'),
    ],
    'File_Management': [
        ('src/file_handler.py',   'File open/save/import/export, ProjectFileHandler class'),
        ('src/history_manager.py','Undo/redo history snapshots, HistoryManager class'),
        ('src/dialogs.py',        'Project information dialog, ProjectInfoDialog class'),
        ('src/logic.py',          'Project create/open/close logic, ProjectLogic class'),
    ],
    'Task_Management': [
        ('src/views/task_view.py',       'Split-pane task+Gantt view, TaskView class'),
        ('src/views/task_sheet_view.py', 'Task sheet table, TaskSheetView class'),
        ('src/logic.py',                 'Task CRUD and WBS operations, ProjectLogic class'),
        ('src/dialogs.py',               'Task information dialog, TaskDialog class'),
    ],
    'Gantt_Chart': [
        ('src/views/gantt_view.py',  'Gantt chart rendering and interaction, GanttView class'),
        ('src/views/timeline_view.py','Timeline strip, TimelineView class'),
        ('src/views/hour_mode.py',   'Hourly zoom mode, HourModeHeader class'),
        ('src/export_gantt.py',      'SVG/PlantUML export, export_gantt_svg() / export_gantt_plantuml()'),
    ],
    'Team_Planner': [
        ('src/views/team_planner_view.py', 'Team planner swimlane view, TeamPlannerView class'),
        ('src/logic.py',                   'Resource assignment logic, ProjectLogic class'),
        ('src/views/hour_mode.py',         'Shared hourly zoom utilities, HourModeHeader class'),
    ],
    'Resource_Management': [
        ('src/views/resource_view.py',                   'Resource sheet, ResourceView class'),
        ('src/views/resource_usage_graph_view.py',       'Resource usage graph, ResourceUsageGraphView class'),
        ('src/views/resource_usage_histogram_view.py',   'Resource usage histogram strip, ResourceUsageHistogramView and compute_histogram_data()'),
        ('src/logic.py',                                 'Resource management methods, ProjectLogic class'),
        ('src/dialogs.py',                               'Resource information dialog, ResourceDialog class'),
    ],
    'Advanced_Features': [
        ('src/baseline_manager.py',       'Baseline storage and comparison functions'),
        ('src/views/baseline_view.py',    'Baseline comparison view, BaselineView class'),
        ('src/history_manager.py',        'Undo/redo stack, HistoryManager class'),
        ('src/views/gantt_view.py',       'Gantt drag-reschedule and split-task rendering, GanttView'),
        ('src/views/timeline_view.py',    'Timeline pin/unpin, TimelineView class'),
        ('src/views/team_planner_view.py','Team planner drag-reschedule, TeamPlannerView class'),
        ('src/progress_worker.py',        'Modal progress dialog framework, WorkerThread / run_with_progress() / run_indeterminate() / record_timing()'),
        ('src/ui.py',                     'Long-running operation dispatch, _JiraSyncWorker / run_with_progress integrations in MainWindow'),
        ('src/holidays.py',               'Holiday calendar management, HolidayManager class'),
    ],
    'App_Debug': [
        ('src/app_debug.py', 'Central debug flag and project-state dump, is_debug() / set_debug() / dump_project_state()'),
    ],
    'Confluence_Integration': [
        ('src/integrations/confluence_calendar_integration.py',
         'Confluence calendar sync, ConfluenceCalendarSync class'),
        ('src/settings_manager.py',  'Confluence settings persistence, SettingsManager class'),
        ('src/settings_dialogs.py',  'Confluence config dialog, ConfluenceCalendarConfigDialog'),
    ],
    'Secondary_Calendar': [
        ('src/integrations/secondary_calendar_integration.py',
         'Secondary calendar integration, SecondaryCalendarIntegration class'),
        ('src/settings_manager.py',  'Secondary calendar settings persistence, SettingsManager class'),
    ],
    'Kee_Pass_Integration': [
        ('src/integrations/keepass_integration.py',
         'KeePass credential lookup, KeePassManager class'),
        ('src/settings_manager.py',  'KeePass settings persistence, SettingsManager class'),
        ('src/settings_dialogs.py',  'KeePass config dialog, KeePassConfigDialog'),
    ],
    'Enterprise_Custom_Fields': [
        ('src/settings_manager.py',  'Enterprise custom field persistence and accessors, SettingsManager class'),
        ('src/logic.py',             'MPXJ enterprise custom fields on summary task (UID=0), ProjectLogic class'),
        ('src/file_handler.py',      'Transparent JSON-object expand/re-serialize for sidecar .custom-props.json, ProjectFileHandler class'),
    ],
    'Active_Directory_Integration': [
        ('src/integrations/ad_integration.py',
         'Active Directory lookup via PowerShell, ad_integration module'),
        ('src/settings_manager.py',  'AD integration settings, SettingsManager class'),
        ('src/dialogs.py',           'AD lookup dialog, ResourceDialog AD integration'),
    ],
    'Email_Integration': [
        ('src/integrations/email_integration.py',
         'SMTP email integration with KeePass credentials, email_integration module'),
        ('src/settings_manager.py',  'Email integration settings, SettingsManager class'),
        ('src/settings_dialogs.py',  'Email config dialog, EmailConfigDialog'),
    ],
    'Jira_Integration': [
        ('src/integrations/jira_integration.py',
         'Jira API connectivity and credential management, test_connection() / get_jira_client()'),
        ('src/integrations/jira_sync.py',
         'Jira↔Project sync and push engine, run_sync() / run_push() / load_sidecar_task_data() / save_sidecar_task_data()'),
        ('src/settings_manager.py',  'Jira integration settings, SettingsManager class'),
        ('src/settings_dialogs.py',  'Jira config dialogs, JiraSyncConfigDialog / JiraServersDialog / JiraServerEditDialog'),
    ],
    'Version_Control': [
        ('src/integrations/version_control_integration.py',
         'VCS integration (Git & SVN), VersionControlIntegration class'),
        ('src/settings_manager.py',  'VCS settings persistence, SettingsManager class'),
        ('src/settings_dialogs.py',  'VCS config dialog, VcsConfigDialog'),
    ],
    'Export_Import': [
        ('src/export_gantt.py',          'PlantUML/SVG export, export_gantt_plantuml() / export_gantt_svg()'),
        ('src/import_plantuml.py',       'PlantUML import, import_plantuml()'),
        ('src/views/dependency_view.py', 'Dependency view, DependencyView class'),
    ],
    'Critical_Path_Method': [
        ('src/views/gantt_view.py',          'CPM computation engine, _compute_critical_ids()'),
        ('src/views/cpm_results_view.py',    'CPM results panel, CpmResultsView class'),
        ('src/settings_dialogs.py',          'CPM settings dialog, CpmSettingsDialog class'),
        ('src/settings_manager.py',          'CPM settings persistence, SettingsManager CPM methods'),
        ('src/ribbon.py',                    'CPM Report ribbon button and email-gated state, ProjectRibbon._cpm_exp_btn / set_email_actions_enabled()'),
        ('src/ui.py',                        'CPM report integration, MainWindow._update_email_actions_state()'),
    ],
    'Non_Functional_Requirements': [
        ('src/_version.py',        'Build version string, BUILD_VERSION constant'),
        ('src/stylesheet.py',      'Application stylesheet, Office blue look-and-feel'),
        ('src/settings_manager.py','Settings persistence via QSettings, SettingsManager class'),
        ('src/settings_dialogs.py','Settings UI dialogs, KeePassConfigDialog / ConfluenceCalendarConfigDialog'),
        ('src/app_debug.py',       'Debug and logging support, set_debug() / dump_project_state()'),
        ('src/logic.py',           'Core maintainability constraints, ProjectLogic class'),
    ],
}

# Package prefix is now read directly from rxml GROUP_FILEINFO/FILEINFO[@Prefix]
# instead of a static dict, so changes to generate_rxml_requirements.py are
# automatically reflected here.

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_req_id(prefix, id_status):
    """Convert ID.Status to a requirement ID, mirroring RequirementObject.getReqId().

    For numeric IDs (e.g. '3.0') the package prefix is prepended:
        '3.0' + 'PO-GEN-' -> 'PO-GEN-003'
    For alphanumeric DSF IDs the ID is returned as-is (already fully qualified):
        'PO-NFR-001.0' -> 'PO-NFR-001'
        'PO-BASE-001.0' -> 'PO-BASE-001'   (even when prefix is 'PO-ADV-')
    """
    id_part = id_status.split('.')[0]
    try:
        return '{}{:03d}'.format(prefix, int(id_part))
    except ValueError:
        # Alphanumeric IDs are already fully-qualified requirement IDs.
        return id_part


def is_requirement_obj(obj):
    """Return True if this OBJECTS element is a functional req (not NFR/heading/info).

    Non-functional requirements do not receive DSI elements or architecture
    linkage — they describe quality constraints, not implementable features.
    """
    rtype = obj.get('aRequirementObjectType', '')
    return rtype == 'functional requirement'


def is_functional_req(obj):
    rtype = obj.get('aRequirementObjectType', '')
    return rtype == 'functional requirement'


def make_dsi_package_elem(pkg_name, creation_ts):
    """Build a DSI sub-package XML element for InheritedDetailedRequirements."""
    pkg_tag = '{}_nbsp_-_nbsp_PO'.format(pkg_name)
    pkg_elem = ET.Element(pkg_tag, depth='1')

    # GROUP_TYPES
    gt = ET.SubElement(pkg_elem, 'GROUP_TYPES')
    ET.SubElement(gt, 'TYPES', Basetype='Enumeration', Name='t_Status_EB',
                  Strings='open,clarify,approved,to be deleted')
    ET.SubElement(gt, 'TYPES', Basetype='Enumeration', Name='t_Status_ZF',
                  Strings='new,modified,to be clarified,aligned,to be deleted')
    ET.SubElement(gt, 'TYPES', Basetype='Enumeration', Name='teVariant',
                  Strings='')

    # GROUP_ATTRIBUTES
    ga = ET.SubElement(pkg_elem, 'GROUP_ATTRIBUTES')
    ET.SubElement(ga, 'ATTRIBUTES', Name='a_EB_Variant', Type='teVariant')
    ET.SubElement(ga, 'ATTRIBUTES', Name='a_EB_PO_Status', Type='t_Status_EB')
    ET.SubElement(ga, 'ATTRIBUTES', Name='a_ZF_PO_Status', Type='t_Status_ZF')

    # GROUP_FILEINFO
    gfi = ET.SubElement(pkg_elem, 'GROUP_FILEINFO')
    ET.SubElement(gfi, 'FILEINFO',
                  Creation_Date=str(creation_ts),
                  Creator='generate_dsi_elements.py',
                  Prefix='DSI',
                  Version_number='1.0')

    # GROUP_OBJECTS (populated later)
    go = ET.SubElement(pkg_elem, 'GROUP_OBJECTS')

    return pkg_elem, go


def make_dsi_objects_elem(req_id, id_status, section, text, dsi_idx):
    """Create an OBJECTS element for a DSI child requirement."""
    dsi_req_id = '{}_DSI_{}'.format(req_id, dsi_idx)
    obj = ET.Element('OBJECTS')
    obj.set('ID.Status', id_status)
    obj.set('Object_Heading', '')
    obj.set('Object_Text', text)
    obj.set('RequirementParent', req_id)
    obj.set('Section_number', section)
    obj.set('aRequirementObjectType', '')
    obj.set('a_EB_Variant', '')
    obj.set('a_EB_PO_Status', '')
    obj.set('a_ZF_PO_Status', '')
    obj.set('RequirementID', dsi_req_id)
    return obj, dsi_req_id


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def generate():
    print('Loading manifest rxml: {}'.format(RXML_PATH))
    parser = ET.XMLParser(remove_blank_text=False)
    manifest_tree = ET.parse(RXML_PATH, parser)
    manifest_root = manifest_tree.getroot()

    # Read package file paths from manifest
    pfp_elem = manifest_root.find('PACKAGE_FILE_PATHES')
    if pfp_elem is None:
        print('ERROR: manifest has no PACKAGE_FILE_PATHES element')
        sys.exit(1)

    # Load each package rxml and collect the package elements
    orig_packages = []
    for elem in pfp_elem.findall('ELEMENT'):
        rel_path = elem.get('PATH', '').replace('\\', os.sep)
        # Skip the DSI file itself — it's output, not source
        if os.path.basename(rel_path) == 'requirement_collection_DSI.rxml':
            continue
        pkg_file = os.path.join(REQ_DIR, rel_path)
        if not os.path.exists(pkg_file):
            print('  WARNING: package file not found: {}'.format(pkg_file))
            continue
        pkg_tree = ET.parse(pkg_file, parser)
        pkg_file_root = pkg_tree.getroot()
        # Structure: <root><Project_Offline depth=0><PackageName depth=1>...
        for child in pkg_file_root:
            for grandchild in child:
                if grandchild.find('GROUP_OBJECTS') is not None:
                    orig_packages.append(grandchild)

    print('Found {} original packages'.format(len(orig_packages)))

    print('Loading ixml: {}'.format(IXML_PATH))
    ixml_tree = ET.parse(IXML_PATH, parser)
    ixml_root = ixml_tree.getroot()

    analyze_elem = ixml_root.find('ANALYZE')
    if analyze_elem is None:
        print('ERROR: no ANALYZE element in ixml')
        sys.exit(1)

    test_attr_elem = analyze_elem.find('TEST_ATTRIBUTE')
    what_done_elem = analyze_elem.find('WHAT_DONE')
    where_cat_elem = analyze_elem.find('WHERE_DONE_CATEGORY')
    where_val_elem = analyze_elem.find('WHERE_DONE_VALUE')
    where_arch_elem = analyze_elem.find('WHERE_DONE_ARCHITECTURE_UNIT')
    what_impact_elem = analyze_elem.find('WHAT_IMPACT')

    # Create if missing
    if test_attr_elem is None:
        test_attr_elem = ET.SubElement(analyze_elem, 'TEST_ATTRIBUTE')
    if what_done_elem is None:
        what_done_elem = ET.SubElement(analyze_elem, 'WHAT_DONE')
    if where_cat_elem is None:
        where_cat_elem = ET.SubElement(analyze_elem, 'WHERE_DONE_CATEGORY')
    if where_val_elem is None:
        where_val_elem = ET.SubElement(analyze_elem, 'WHERE_DONE_VALUE')
    if where_arch_elem is None:
        where_arch_elem = ET.SubElement(analyze_elem, 'WHERE_DONE_ARCHITECTURE_UNIT')
    if what_impact_elem is None:
        what_impact_elem = ET.SubElement(analyze_elem, 'WHAT_IMPACT')

    # Clear existing DSI entries (regenerate from scratch)
    for elem in [test_attr_elem, what_done_elem, where_cat_elem,
                 where_val_elem, where_arch_elem, what_impact_elem]:
        for child in list(elem):
            elem.remove(child)

    # Build DSI rxml: <root><InheritedDetailedRequirements depth=0>...
    dsi_root_elem = ET.Element('root')
    idr = ET.SubElement(dsi_root_elem, 'InheritedDetailedRequirements', depth='0')

    creation_ts = int(time.time())

    # Accumulators for ixml entries (sorted alphabetically by req_id)
    test_attr_entries = []   # (dsi_req_id, type_str)
    what_done_entries = []   # (req_id, text)
    what_impact_entries = [] # (req_id, text)
    where_cat_entries = []   # dsi_req_id
    where_arch_entries = []  # (dsi_req_id, arch_unit)
    req_arch_entries  = []   # (req_id, arch_unit) — parent req gets all its DSI arch units

    # Single global requirement counter: ID.Status = {global_req_counter}.{dsi_index}
    # This matches the reference format where decimal encodes the DSI index.
    global_req_counter = 1

    for pkg_elem_orig in orig_packages:
        pkg_name = pkg_elem_orig.tag
        # Non-functional requirements get no DSI elements but do receive an
        # architecture-unit linkage of 'non-functional' in the ixml.
        if pkg_name == 'Non_Functional_Requirements':
            gfi = pkg_elem_orig.find('GROUP_FILEINFO')
            fi_elem = gfi.find('FILEINFO') if gfi is not None else None
            prefix = fi_elem.get('Prefix', 'PO-NFR-') if fi_elem is not None else 'PO-NFR-'
            go_orig = pkg_elem_orig.find('GROUP_OBJECTS')
            nfr_objs = [obj for obj in (go_orig.findall('OBJECTS') if go_orig is not None else [])
                        if obj.get('aRequirementObjectType', '') == 'non functional requirement']
            for obj in nfr_objs:
                req_id = get_req_id(prefix, obj.get('ID.Status', ''))
                req_arch_entries.append((req_id, 'non-functional'))
            print('  Package {} - {} NFRs -> architecture unit = non-functional'.format(
                pkg_name, len(nfr_objs)))
            continue
        # Derive prefix from rxml FILEINFO rather than a static dict
        gfi = pkg_elem_orig.find('GROUP_FILEINFO')
        fi_elem = gfi.find('FILEINFO') if gfi is not None else None
        prefix = fi_elem.get('Prefix', 'PO-') if fi_elem is not None else 'PO-'
        src_files = PACKAGE_SRC_MAP.get(pkg_name, [('src/logic.py', 'Core logic')])

        # Build DSI sub-package
        dsi_pkg, dsi_go = make_dsi_package_elem(pkg_name, creation_ts)
        idr.append(dsi_pkg)

        # Get all OBJECTS in this package
        go_orig = pkg_elem_orig.find('GROUP_OBJECTS')
        if go_orig is None:
            continue
        all_objs = go_orig.findall('OBJECTS')

        req_objs = [obj for obj in all_objs if is_requirement_obj(obj)]

        # heading object for the DSI sub-package (fixed non-numeric ID per reference)
        heading_obj = ET.Element('OBJECTS')
        heading_obj.set('ID.Status', '0_Heading.0')
        heading_obj.set('Object_Heading', pkg_name.replace('_', ' ') + ' - Implementation')
        heading_obj.set('Object_Text', '')
        heading_obj.set('RequirementParent', '')
        heading_obj.set('Section_number', '1')
        heading_obj.set('aRequirementObjectType', 'heading')
        heading_obj.set('a_EB_Variant', '')
        heading_obj.set('a_EB_PO_Status', '')
        heading_obj.set('a_ZF_PO_Status', '')
        heading_obj.set('RequirementID', 'DSI000_Heading')
        dsi_go.append(heading_obj)

        print('  Package {} - {} reqs x {} src files -> generating DSI elements'.format(
            pkg_name, len(req_objs), len(src_files)))

        req_idx = 1
        for req_obj in req_objs:
            id_status = req_obj.get('ID.Status', '')
            req_id = get_req_id(prefix, id_status)
            req_heading = req_obj.get('Object_Heading', '').strip()
            if not req_heading:
                req_heading = req_obj.get('Object_Text', '').strip()
                if len(req_heading) > 80:
                    req_heading = req_heading[:77] + '...'

            dsi_type = 'Integration' if is_functional_req(req_obj) else ''
            all_files_text = ', '.join(os.path.basename(f) for f, _ in src_files)
            what_done_text = 'Implemented in: {}. {}'.format(
                all_files_text,
                '; '.join(d for _, d in src_files))

            what_done_entries.append((req_id, what_done_text))
            what_impact_entries.append((req_id, 'Implementation across: {}'.format(all_files_text)))

            for dsi_i, (src_file, src_desc) in enumerate(src_files):
                src_basename = os.path.splitext(os.path.basename(src_file))[0]
                if req_heading:
                    dsi_text = '[{}] {} -- {} ({})'.format(
                        req_id, req_heading, src_file, src_desc)
                else:
                    dsi_text = '[{}] {} ({})'.format(req_id, src_file, src_desc)

                # ID.Status = {req_base}.{dsi_index} — matches reference project convention
                # The decimal encodes the DSI index so the tool can count children correctly.
                dsi_id_status = '{}.{}'.format(global_req_counter, dsi_i)
                dsi_section = '1.{}.{}'.format(req_idx, dsi_i + 1)

                dsi_obj, dsi_req_id = make_dsi_objects_elem(
                    req_id, dsi_id_status, dsi_section, dsi_text, dsi_i)
                dsi_go.append(dsi_obj)

                test_attr_entries.append((dsi_req_id, dsi_type))
                where_cat_entries.append(dsi_req_id)
                where_arch_entries.append((dsi_req_id, src_basename))
                # Parent req gets all its DSI architecture units
                req_arch_entries.append((req_id, src_basename))

            global_req_counter += 1
            req_idx += 1

    # Sort alphabetically by ID
    test_attr_entries.sort(key=lambda x: x[0])
    what_done_entries.sort(key=lambda x: x[0])
    what_impact_entries.sort(key=lambda x: x[0])
    where_cat_entries.sort()
    where_arch_entries.sort(key=lambda x: x[0])
    req_arch_entries.sort(key=lambda x: x[0])

    # Populate ixml TEST_ATTRIBUTE
    for dsi_id, dsi_type in test_attr_entries:
        ET.SubElement(test_attr_elem, 'ELEMENT', REQ_ID=dsi_id, TYPE=dsi_type)

    # Populate ixml WHAT_DONE
    for req_id, text in what_done_entries:
        ET.SubElement(what_done_elem, 'ELEMENT', REQ_ID=req_id, TEXT=text)

    # Populate ixml WHAT_IMPACT
    for req_id, text in what_impact_entries:
        ET.SubElement(what_impact_elem, 'ELEMENT', REQ_ID=req_id, TEXT=text)

    # Populate ixml WHERE_DONE_CATEGORY
    for dsi_id in where_cat_entries:
        ET.SubElement(where_cat_elem, 'ELEMENT', REQ_ID=dsi_id, CATEGORY='source code')

    # Populate ixml WHERE_DONE_VALUE
    for dsi_id in where_cat_entries:
        ET.SubElement(where_val_elem, 'ELEMENT', REQ_ID=dsi_id, VALUE='')

    # Populate ixml WHERE_DONE_ARCHITECTURE_UNIT (DSI elements)
    for dsi_id, arch_unit in where_arch_entries:
        ET.SubElement(where_arch_elem, 'ELEMENT', REQ_ID=dsi_id,
                      ARCHITECTURE_UNIT=arch_unit)
    # Populate ixml WHERE_DONE_ARCHITECTURE_UNIT (parent requirements — one entry per arch unit)
    for req_id, arch_unit in req_arch_entries:
        ET.SubElement(where_arch_elem, 'ELEMENT', REQ_ID=req_id,
                      ARCHITECTURE_UNIT=arch_unit)

    # Write DSI rxml to packageRxml/requirement_collection_DSI.rxml
    os.makedirs(PKG_DIR, exist_ok=True)
    print('Writing DSI rxml: {}'.format(DSI_RXML_PATH))
    dsi_tree = ET.ElementTree(dsi_root_elem)
    dsi_tree.write(DSI_RXML_PATH, xml_declaration=True, encoding='UTF-8',
                   pretty_print=True)

    # Add DSI rxml to manifest (if not already listed)
    dsi_rel_path = 'packageRxml\\requirement_collection_DSI.rxml'
    existing_paths = [e.get('PATH', '') for e in pfp_elem.findall('ELEMENT')]
    if dsi_rel_path not in existing_paths:
        # Fix tails so the new entry aligns with its siblings (4 spaces)
        if len(pfp_elem) > 0:
            pfp_elem[-1].tail = '\n    '  # previous last → indent to new element
        dsi_entry = ET.SubElement(pfp_elem, 'ELEMENT', PATH=dsi_rel_path)
        dsi_entry.tail = '\n  '           # new last → indent for closing </PACKAGE_FILE_PATHES>
    print('Writing manifest rxml: {}'.format(RXML_PATH))
    manifest_tree.write(RXML_PATH, xml_declaration=True, encoding='UTF-8',
                        pretty_print=True)

    # Write ixml
    print('Writing ixml: {}'.format(IXML_PATH))
    ixml_tree.write(IXML_PATH, xml_declaration=True, encoding='UTF-8',
                    pretty_print=True)

    print('Done.')
    print('  DSI requirements created:              {}'.format(len(test_attr_entries)))
    print('  WHAT_DONE entries:                     {}'.format(len(what_done_entries)))
    print('  WHERE_DONE_CATEGORY entries:           {}'.format(len(where_cat_entries)))
    print('  WHERE_DONE_ARCHITECTURE_UNIT (DSI):    {}'.format(len(where_arch_entries)))
    print('  WHERE_DONE_ARCHITECTURE_UNIT (parent): {}'.format(len(req_arch_entries)))


if __name__ == '__main__':
    generate()
