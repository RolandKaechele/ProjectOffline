# Requirements Management

This directory is the single source of truth for all Project Offline requirements.

## Directory Layout

```
documentation/requirements/
├── README.md                                   ← this file
├── dsf/                                        ← EDIT HERE – hand-maintained sources
│   ├── PO_00_nfr.dsf                           Non-Functional Requirements
│   ├── PO_01_system_overview.dsf               System Overview
│   ├── PO_02_app_debug.dsf                     App Debug Dump (Ctrl+D, --debug flag)
│   ├── PO_03_file_management.dsf
│   ├── PO_04_task_management.dsf
│   ├── PO_05_gantt_chart.dsf
│   ├── PO_06_team_planner.dsf
│   ├── PO_07_resource_management.dsf
│   ├── PO_08_advanced_features.dsf
│   ├── PO_09_confluence_integration.dsf    Confluence Calendar Sync
│   ├── PO_10_secondary_calendar.dsf        Secondary Calendar Integration
│   ├── PO_11_keepass_integration.dsf       KeePass Credential Management
│   ├── PO_12_enterprise_custom_fields.dsf  Enterprise Custom Fields
│   ├── PO_13_active_directory_integration.dsf  Active Directory Integration
│   ├── PO_14_email_integration.dsf         Email Integration
│   ├── PO_15_jira_integration.dsf          Jira Integration, J2P Sync, P2J Push
│   ├── PO_16_version_control.dsf           Version Control (Git & SVN)
│   ├── PO_17_export_import.dsf
│   └── PO_18_critical_path_method.dsf
├── packageRxml/                                ← GENERATED – do not edit
│   ├── requirement_collection_<Package>.rxml   one per DSF file
│   └── requirement_collection_DSI.rxml         cross-reference (DSI) file
├── requirement_collection.rxml                 ← GENERATED – manifest / loader entry point
└── requirement_additional_informations.ixml    ← GENERATED – WHERE_DONE linkages
```

**Never edit files under `packageRxml/` or the two generated root files directly.**
All changes go into the `dsf/` source files, then the database is regenerated.


## Regenerating the Requirements Database

After editing any DSF file, run the single entry-point script:

```powershell
venv\Scripts\python.exe tools\regenerate_requirements.py
```

This performs **two steps in the correct dependency order**:

| Step | Script | Input | Output |
| ---- | ------ | ----- | ------ |
| 1 | `tools/generate_rxml_requirements.py` | `dsf/*.dsf` | `packageRxml/*.rxml`, manifest `requirement_collection.rxml` |
| 2 | `tools/generate_dsi_elements.py` | manifest + `requirement_additional_informations.ixml` | `packageRxml/requirement_collection_DSI.rxml`, updated ixml |

Expected console output (counts will vary):

```
Step 1/2: generate_rxml_requirements
...
  Packages (sub-modules): 19
  Functional reqs:        587
  Total requirements:     649

Step 2/2: generate_dsi_elements
...
  DSI requirements created:  2517
```

> A non-zero exit code from step 1 is benign when the ixml already exists
> ("Skipped (already exists)"). Exit 0 from `regenerate_requirements.py`
> means both steps completed without error.


## DSF File Format

DSF files are **UTF-8 encoded tab-separated text** with XML-like section tags.
Open them in any text editor that preserves tabs (VS Code works perfectly).

### File skeleton

```
<FILEINFO>
Scriptversion    Encoding    Module    Prefix    Description    …
    UTF-8    <module>    PO    <description>    …
</FILEINFO>
<TYPES>
Name    Basetype    …
t_Status_Sup    Enumeration    …    open,clarify,approved,to be deleted
t_Status_ZF    Enumeration    …    new,modified,to be clarified,aligned,to be deleted
</TYPES>
<ATTRIBUTES>
Name    Type    Definitions    Default
a_EB_PO_Status    t_Status_Sup
a_ZF_PO_Status    t_Status_ZF
</ATTRIBUTES>
… (ATTRIBUTEVALUES, PICTURES, PASSEDATTRIBUTES, LINKMODULES, FORMALMODULES, OBJECT_IDS – leave as-is) …
<OBJECTS>
Object_Heading    Object_Text    aRequirementObjectType    Section_number    ID.Status    aResponsibility    a_EB_PO_Status    a_ZF_PO_Status
… rows …
</OBJECTS>
```

### `<OBJECTS>` column reference

| Column | Required | Allowed values | Notes |
| ------ | -------- | -------------- | ----- |
| `Object_Heading` | for headings | free text | Non-empty ⇒ section heading node. Leave blank for requirement / info rows. |
| `Object_Text` | for reqs | free text | The requirement sentence. Empty for heading rows. |
| `aRequirementObjectType` | yes | `functional requirement` \| `non functional requirement` \| `information` \| *(empty for headings)* | Determines node type in the tool. |
| `Section_number` | yes | `1`, `1.1`, `2.3.1`, … | Drives the tree hierarchy. Must match the heading section it belongs to. |
| `ID.Status` | yes | `<PREFIX>-NNN.0` | See [ID rules](#id-rules) below. Headings use the pattern `1_Heading.0` / `1_1_Heading.0`. |
| `aResponsibility` | yes | `Not relevant` | Always `Not relevant` for this project. |
| `a_EB_PO_Status` | for reqs | `approved` \| `open` \| `clarify` \| `to be deleted` \| *(empty)* | Approval status from EB side. Use `approved` for completed requirements. |
| `a_ZF_PO_Status` | for reqs | `aligned` \| `new` \| `modified` \| `to be clarified` \| `to be deleted` \| *(empty)* | Alignment status from ZF side. Use `aligned` for completed requirements. |


## ID Rules

### Requirement IDs

Each functional requirement carries a unique ID of the form:

```
PO-<CATEGORY>-<NNN>.0
```

Examples: `PO-BASE-009.0`, `PO-J2P-047.0`, `PO-VCS-042.0`

**Category prefixes per DSF file:**

| DSF file | Category prefixes used |
| -------- | ---------------------- |
| `PO_00_nfr.dsf` | `PO-NFR-` |
| `PO_01_system_overview.dsf` | `PO-GEN-`, `PO-INFO-` |
| `PO_02_App_Debug.dsf` | `PO-DBG-` |
| `PO_03_file_management.dsf` | `PO-FILE-` |
| `PO_04_task_management.dsf` | `PO-TASK-` |
| `PO_05_gantt_chart.dsf` | `PO-GANTT-` |
| `PO_06_team_planner.dsf` | `PO-TP-` |
| `PO_07_resource_management.dsf` | `PO-RES-` |
| `PO_08_advanced_features.dsf` | `PO-BASE-`, `PO-TL-`, `PO-SPLIT-`, `PO-ADV-` |
| `PO_09_confluence_integration.dsf` | `PO-CONF-` |
| `PO_10_secondary_calendar.dsf` | `PO-SC-` |
| `PO_11_keepass_integration.dsf` | `PO-KP-` |
| `PO_12_enterprise_custom_fields.dsf` | `PO-ECF-` |
| `PO_13_active_directory_integration.dsf` | `PO-AD-` |
| `PO_14_email_integration.dsf` | `PO-EMAIL-` |
| `PO_15_jira_integration.dsf` | `PO-JIRA-`, `PO-J2P-`, `PO-P2J-` |
| `PO_16_version_control.dsf` | `PO-VCS-` |
| `PO_17_export_import.dsf` | `PO-EXP-` |
| `PO_18_critical_path_method.dsf` | `PO-CPM-` |

**Rules:**

- IDs are **never reused**. If a requirement is deleted, its ID is retired permanently.
- If requirement *content* changes significantly, **create a new ID** rather than updating the existing one.
- The numeric part is zero-padded to 3 digits: `001`, `047`, etc.
- Always append `.0` – this is the DOORS status suffix.
- To find the next free number, search the DSF file for the highest existing number for that prefix and increment by 1.

### Heading IDs

Heading rows use a derived ID, not the `PO-…` scheme:

```
<depth1>_Heading.0            e.g. 1_Heading.0
<depth1>_<depth2>_Heading.0   e.g. 1_1_Heading.0
```

Information items use the same `PO-<CAT>-INFO-NNN.0` pattern as requirements.

### IDs in generated rxml

The generated `packageRxml/*.rxml` files use **sequential integer IDs** (e.g., `1.0`, `2.0`, `335.0`).
These integers are internal to the requirementProcessTool and are **not** the DSF IDs.
Headings and information items also consume integer IDs.
Do not rely on the integer sequence; always identify requirements by their `PO-…` ID in the DSF source.


## Adding a New Requirement

1. **Open the correct DSF file** for the feature area (see table above).
2. **Find the right section** (sub-chapter). New requirements belong under the sub-chapter that describes the feature. If no suitable sub-chapter exists, add a new heading row first.
3. **Determine the next free ID number** for the relevant prefix:

   ```powershell
   Select-String -Path "documentation\requirements\dsf\PO_16_version_control.dsf" -Pattern "PO-VCS-\d+" | ForEach-Object { $_.Matches[0].Value } | Sort-Object | Select-Object -Last 1
   ```

4. **Insert a new row** in the `<OBJECTS>` section at the correct position (immediately after the last requirement of the same sub-chapter). Columns are tab-separated:

   ```
   [TAB]<requirement text>[TAB]functional requirement[TAB]<section>[TAB]PO-<CAT>-<NNN>.0[TAB]Not relevant[TAB]approved[TAB]aligned
   ```

   The leading tab means `Object_Heading` is empty (this is a requirement row, not a heading row).
5. **Save the DSF file** (UTF-8, keep tab separators – do not let the editor convert tabs to spaces).
6. **Regenerate** the database:

   ```powershell
   venv\Scripts\python.exe tools\regenerate_requirements.py
   ```

7. **Verify** the new requirement appears in the generated rxml:

   ```powershell
   Select-String -Path "documentation\requirements\packageRxml\requirement_collection_<Package>.rxml" -Pattern "<keyword from requirement text>"
   ```

### Example: adding `PO-VCS-045.0`

Current last VCS requirement in `PO_16_version_control.dsf` is `PO-VCS-044.0` at section `1.8.4`.
Adding a new requirement for section `8.8.5`:

```
[TAB]The VCS module shall expose a git_status() function returning a list of modified tracked files.[TAB]functional requirement[TAB]8.8.5[TAB]PO-VCS-045.0[TAB]Not relevant[TAB]approved[TAB]aligned
```


## Adding a New Sub-Chapter (Heading)

Insert two rows: a heading row and optionally an information row, followed by requirement rows.

```
<heading text, e.g. "8.8.5 Git Status">    [TAB][TAB]<section, e.g. 8.8.5>[TAB]<depth>_Heading.0[TAB]Not relevant[TAB][TAB]
[TAB]<description text>[TAB]information[TAB]<section>.1[TAB]PO-<CAT>-INFO-NNN.0[TAB]Not relevant[TAB][TAB]
```

Heading row format: `Object_Heading` is non-empty, `Object_Text` is empty, `aRequirementObjectType` is empty.


## Modifying an Existing Requirement

- **Minor wording fixes** (typos, grammar): update `Object_Text` in place; keep the same ID.
- **Semantic changes** (scope, behaviour, acceptance criteria): create a new requirement with a new ID. Mark the old one `to be deleted` in `a_EB_PO_Status` / `a_ZF_PO_Status` until the next release, then remove it.
- **Never change an ID.Status value** once it has been published in a release.


## DSI (Detailed Software Implementation) Elements

The `packageRxml/requirement_collection_DSI.rxml` is **fully generated** by step 2 of the regeneration pipeline. It creates one DSI child element per functional requirement per source file listed in `tools/generate_dsi_elements.py` → `PACKAGE_SRC_MAP`.

- **Newly added requirements** appear in the DSI with an empty `RequirementParent` linkage until they are explicitly traced to source files.
- To add or update source-file traceability for a package, edit `PACKAGE_SRC_MAP` in `tools/generate_dsi_elements.py` and re-run the regeneration.
- The ixml file (`requirement_additional_informations.ixml`) stores `WHERE_DONE` entries. It is re-generated on every run; manual edits are overwritten.


## Checklist for Every PR that Touches Requirements

```
- [ ] Verified that the change doesn't break requirements nor DSIs.
- [ ] Added new requirements to DSF (documentation/requirements/dsf/).
      IDs placed in the correct sub-chapter; no IDs reused.
- [ ] Regenerated requirements database:
        venv\Scripts\python.exe tools\regenerate_requirements.py
      Output shows no errors; functional req count increased as expected.
- [ ] Checked that DSIs aren't broken (regeneration log shows 2500+ DSI
      entries created without errors).
```
