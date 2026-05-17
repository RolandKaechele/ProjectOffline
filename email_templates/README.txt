Email Templates — Project Offline
===================================

This folder contains email templates that are loaded by the Email Export
feature (REPORT ribbon → Gantt Export / Resource SVG / Timeline Export dropdowns).

Template File Format
--------------------
Each template is a UTF-8 JSON file with the following keys:

  "name"      (string, required)
      Display name shown in the template dropdown.

  "subject"   (string, required)
      Email subject line. Supports placeholders (see below).

  "body"      (string, required)
      Email body in plain text. Used as the plain-text fallback in all
      email clients. Supports placeholders.

  "body_html" (string, optional)
      Email body in HTML. When present the message is sent as a
      multipart/related MIME message so the SVG export is embedded
      directly in the HTML body (inline image) AND also attached as a
      downloadable SVG file.  Supports placeholders including the special
      {svg_inline} token (see below).

Supported Placeholders
----------------------
  {resource_name}    — Name of the resource (for per-resource bulk send)
  {project_name}     — Project name from the open .xml file
  {project_manager}  — Project Offline field (from project properties)
  {date}             — Today's date in YYYY-MM-DD format
  {view_name}        — Name of the view being exported (e.g. "Gantt Chart")
  {svg_inline}       — (body_html only) Replaced with an <img src="cid:...">
                       tag that renders the exported SVG inline in the HTML
                       body. Place it wherever you want the chart to appear.

Example Template (with HTML body)
----------------------------------
  {
    "name": "My Custom Template",
    "subject": "Project Update: {project_name} ({date})",
    "body": "Dear {resource_name},\n\nPlease find attached the latest schedule.\n\nRegards,\n{project_manager}",
    "body_html": "<html><body><p>Dear <strong>{resource_name}</strong>,</p><p>Below is the latest schedule for <strong>{project_name}</strong>:</p><p>{svg_inline}</p><p>Regards,<br/>{project_manager}</p></body></html>"
  }

MIME Structure (when body_html is present)
------------------------------------------
  multipart/mixed
    multipart/related
      multipart/alternative
        text/plain   ← body (plain-text fallback)
        text/html    ← body_html (rendered by HTML-capable clients)
      image/svg+xml  ← SVG embedded inline (Content-ID referenced by {svg_inline})
    image/svg+xml    ← SVG attached as downloadable file

Notes
-----
- Templates are optional. If no template is selected you can compose
  the subject and body freely in the Email Export dialog.
- If body_html is omitted the message is sent as plain text with a
  file attachment only (backward-compatible).
- Any .json file in this folder is loaded as a template on startup.
- Files with invalid JSON are silently skipped.
- Changes to this folder take effect the next time the Email Export
  dialog is opened.
