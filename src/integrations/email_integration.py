# email_integration.py - SMTP email functionality with secure credential handling.
#
# Sends SVG exports (Gantt overview, Team Planner snapshot, Resource Usage graph)
# as email attachments via SMTP without leaving the application.
#
# Authentication
# --------------
# Credentials are retrieved from KeePass — no passwords stored in QSettings.
# - KeePass unlocked → retrieve username and password from configured entry.
# - KeePass locked   → prompt user to unlock KeePass first.
#
# Configuration (QSettings)
# -------------------------
# Multiple SMTP configurations are stored as a JSON list under "email/configs".
# The active configuration name is stored under "email/active_config_name".
# Legacy single-config keys (email/smtp_server etc.) are migrated automatically.
#
# Public API
# ----------
#   is_configured(config=None)                       -> bool
#   send_email(to, subject, body, attachments, config=None) -> tuple[bool, str]
#   test_connection(config=None)                     -> tuple[bool, str]
#   get_config_summary()                             -> dict   (for app_debug.py dump)
#   get_active_config()                              -> dict | None
#
# See documentation/email_integration.md for full details.

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional

# Used for inline image (SVG) MIME parts
_MIME_SVG_MAINTYPE = "image"
_MIME_SVG_SUBTYPE  = "svg+xml"

from app_debug import is_debug as _is_debug  # type: ignore

# ---------------------------------------------------------------------------
# Module-level history tracking (for debug dump)
# ---------------------------------------------------------------------------
_last_send_result:   Optional[dict] = None
_last_test_result:   Optional[dict] = None
_last_export_result: Optional[dict] = None  # set by ui.py open_email_export / open_email_export_bulk


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _get_settings_manager():
    """Return a SettingsManager instance (reads from shared QSettings registry)."""
    try:
        from settings_manager import SettingsManager  # type: ignore
        return SettingsManager()
    except Exception:
        return None


def get_active_config() -> Optional[dict]:
    """Return the active email configuration dict, or None if not configured."""
    sm = _get_settings_manager()
    if sm is None:
        return None
    result = sm.get_active_email_config()
    return result if isinstance(result, dict) else None


def _resolve_config(config: Optional[dict]) -> Optional[dict]:
    """Return *config* if given, otherwise fall back to the active config."""
    if config is not None:
        return config
    return get_active_config()


def _get_smtp_server(config: Optional[dict] = None) -> str:
    cfg = _resolve_config(config)
    if cfg:
        return cfg.get("smtp_server", "")
    # Legacy fallback
    sm = _get_settings_manager()
    return sm.get_email_smtp_server() if sm else ""


def _get_smtp_port(config: Optional[dict] = None) -> int:
    cfg = _resolve_config(config)
    if cfg:
        return int(cfg.get("smtp_port", 587))
    sm = _get_settings_manager()
    return sm.get_email_smtp_port() if sm else 587


def _get_smtp_use_tls(config: Optional[dict] = None) -> bool:
    cfg = _resolve_config(config)
    if cfg:
        return bool(cfg.get("smtp_use_tls", True))
    sm = _get_settings_manager()
    return sm.get_email_smtp_use_tls() if sm else True


def _get_sender_address(config: Optional[dict] = None) -> str:
    """Return the From address, formatted as 'Name <address>' when sender_name is set."""
    cfg = _resolve_config(config)
    if cfg:
        address = cfg.get("sender_address", "")
        name    = cfg.get("sender_name", "").strip()
        if name and address:
            from email.utils import formataddr  # stdlib, always available
            return formataddr((name, address))
        return address
    sm = _get_settings_manager()
    return sm.get_email_sender_address() if sm else ""


def _get_keepass_entry(config: Optional[dict] = None) -> str:
    cfg = _resolve_config(config)
    if cfg:
        entry = cfg.get("keepass_entry", "")
        if entry:
            return entry
        # No per-account entry — fall back to global setting
    sm = _get_settings_manager()
    return sm.get_email_keepass_entry() if sm else ""


# Legacy single-config setters (kept for backward compat; update active config in list)
def set_smtp_server(server: str):
    sm = _get_settings_manager()
    if sm is not None:
        sm.set_email_smtp_server(server)


def set_smtp_port(port: int):
    sm = _get_settings_manager()
    if sm is not None:
        sm.set_email_smtp_port(port)


def set_smtp_use_tls(use_tls: bool):
    sm = _get_settings_manager()
    if sm is not None:
        sm.set_email_smtp_use_tls(use_tls)


def set_sender_address(address: str):
    sm = _get_settings_manager()
    if sm is not None:
        sm.set_email_sender_address(address)


def set_keepass_entry(entry: str):
    sm = _get_settings_manager()
    if sm is not None:
        sm.set_email_keepass_entry(entry)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_configured(config: Optional[dict] = None) -> bool:
    """Return True when all required SMTP settings have been configured.

    Pass *config* to check a specific configuration dict rather than the
    active configuration from QSettings.
    """
    server = _get_smtp_server(config)
    sender = _get_sender_address(config)
    entry = _get_keepass_entry(config)
    return bool(server and sender and entry)


def _get_credentials(config: Optional[dict] = None) -> tuple[str, str]:
    """Retrieve SMTP username and password from KeePass for *config*.

    Returns (username, password) when successful, or ("", "") on failure.
    """
    try:
        from integrations import keepass_integration  # type: ignore
        if not keepass_integration.is_unlocked():
            return "", ""
        entry_title = _get_keepass_entry(config)
        if not entry_title:
            return "", ""
        username, password = keepass_integration.get_credentials(entry_title)
        return username, password
    except Exception as exc:
        if _is_debug():
            print(f"[email_integration] Failed to retrieve credentials: {exc}")
        return "", ""


def send_email(
    to: "str | list[str]",
    subject: str,
    body: str,
    attachments: Optional[list[tuple[str, bytes]]] = None,
    config: Optional[dict] = None,
    *,
    body_html: Optional[str] = None,
    inline_images: Optional[list[tuple[str, str, bytes]]] = None,
) -> tuple[bool, str]:
    """Send an email with optional file attachments via SMTP.

    Args:
        to: Recipient email address(es) — single string or list of strings.
        subject: Email subject line.
        body: Email body text (plain-text fallback, always required).
        attachments: Optional list of (filename, file_bytes) tuples to attach as
            downloadable files.
        config: Email configuration dict to use. Uses the active configuration
                from QSettings when None.
        body_html: Optional HTML version of the body.  When provided the message
            uses a multipart/related structure so inline images can be referenced
            via ``cid:`` URIs.
        inline_images: Optional list of (content_id, filename, image_bytes) tuples
            to embed as inline MIME parts (e.g. an SVG rendered directly in the
            HTML body via ``<img src="cid:{content_id}">``.  Only meaningful when
            *body_html* is also provided.

    Returns:
        (success, error_message) tuple. error_message is empty on success.
    """
    global _last_send_result

    if isinstance(to, str):
        to_list = [to]
    else:
        to_list = list(to)

    if not to_list:
        _last_send_result = {"success": False, "error": "No recipient addresses provided"}
        return False, "No recipient addresses provided"

    if not is_configured(config):
        msg = "Email integration is not fully configured (server, sender, or KeePass entry missing)"
        _last_send_result = {"success": False, "error": msg}
        return False, msg

    username, password = _get_credentials(config)
    if not username or not password:
        msg = "Failed to retrieve SMTP credentials from KeePass (database locked or entry not found)"
        _last_send_result = {"success": False, "error": msg}
        return False, msg

    try:
        sender = _get_sender_address(config)

        if body_html:
            # ----------------------------------------------------------------
            # Multipart structure that supports inline images + file attachment:
            #   multipart/mixed
            #     multipart/related
            #       multipart/alternative
            #         text/plain   (body — plain-text fallback)
            #         text/html    (body_html — displayed when client supports HTML)
            #       [inline_images: image/svg+xml with Content-ID, one per image]
            #     [attachments: application/octet-stream, one per file]
            # ----------------------------------------------------------------
            root = MIMEMultipart("mixed")
            root["From"]    = sender
            root["To"]      = ", ".join(to_list)
            root["Subject"] = subject

            related = MIMEMultipart("related")

            alt = MIMEMultipart("alternative")
            alt.attach(MIMEText(body, "plain", "utf-8"))
            alt.attach(MIMEText(body_html, "html", "utf-8"))
            related.attach(alt)

            for img_cid, img_filename, img_bytes in (inline_images or []):
                img_part = MIMEBase(_MIME_SVG_MAINTYPE, _MIME_SVG_SUBTYPE)
                img_part.set_payload(img_bytes)
                encoders.encode_base64(img_part)
                img_part.add_header("Content-ID", f"<{img_cid}>")
                img_part.add_header(
                    "Content-Disposition", "inline", filename=img_filename
                )
                related.attach(img_part)

            root.attach(related)

            for att_filename, att_bytes in (attachments or []):
                att = MIMEBase("application", "octet-stream")
                att.set_payload(att_bytes)
                encoders.encode_base64(att)
                att.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {att_filename}",
                )
                root.attach(att)

            msg = root

        else:
            # ----------------------------------------------------------------
            # Plain-text message (backward-compatible path)
            # ----------------------------------------------------------------
            msg = MIMEMultipart()
            msg["From"]    = sender
            msg["To"]      = ", ".join(to_list)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))

            for filename, file_bytes in (attachments or []):
                part = MIMEBase("application", "octet-stream")
                part.set_payload(file_bytes)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {filename}",
                )
                msg.attach(part)

        n_inline = len(inline_images or [])
        n_attach = len(attachments or [])
        if _is_debug():
            print(f"[email_integration] Message built: {len(to_list)} recipient(s), "
                  f"{n_inline} inline image(s), {n_attach} file attachment(s), "
                  f"HTML body: {body_html is not None}")
    except Exception as exc:
        error = f"Failed to build email message: {exc}"
        _last_send_result = {"success": False, "error": error}
        return False, error

    try:
        server = _get_smtp_server(config)
        port = _get_smtp_port(config)
        use_tls = _get_smtp_use_tls(config)

        if _is_debug():
            print(f"[email_integration] Connecting to {server}:{port} (TLS: {use_tls})")

        smtp = smtplib.SMTP(server, port, timeout=30)
        smtp.ehlo()

        if use_tls:
            if smtp.has_extn("STARTTLS"):
                smtp.starttls()
                smtp.ehlo()
            elif _is_debug():
                print("[email_integration] Warning: Server does not support STARTTLS")

        try:
            smtp.login(username, password)
            if _is_debug():
                print(f"[email_integration] Authenticated as '{username}'")
        except smtplib.SMTPAuthenticationError as exc:
            error = f"SMTP authentication failed: {exc}"
            if _is_debug():
                print(f"[email_integration] {error}")
            smtp.quit()
            _last_send_result = {"success": False, "error": error}
            return False, error

        smtp.sendmail(msg["From"], to_list, msg.as_string())
        smtp.quit()

        if _is_debug():
            print(f"[email_integration] Email sent successfully to {to_list}")

        _last_send_result = {
            "success": True,
            "to": to_list,
            "subject": subject,
            "attachments": len(attachments or []),
        }
        return True, ""

    except smtplib.SMTPException as exc:
        error = f"SMTP error: {exc}"
        if _is_debug():
            print(f"[email_integration] {error}")
        _last_send_result = {"success": False, "error": error}
        return False, error
    except Exception as exc:
        error = f"Unexpected error sending email: {exc}"
        if _is_debug():
            print(f"[email_integration] {error}")
        _last_send_result = {"success": False, "error": error}
        return False, error


def test_connection(config: Optional[dict] = None) -> tuple[bool, str]:
    """Test SMTP connection and authentication without sending an email.

    Args:
        config: Email configuration dict to use. Uses the active configuration
                from QSettings when None.

    Returns:
        (success, error_message) tuple. error_message is empty on success.
    """
    global _last_test_result

    if _is_debug():
        print("[email_integration] Reading configuration:")
        print(f"  Server: '{_get_smtp_server(config)}'")
        print(f"  Port: {_get_smtp_port(config)}")
        print(f"  Use TLS: {_get_smtp_use_tls(config)}")
        print(f"  Sender: '{_get_sender_address(config)}'")
        print(f"  KeePass Entry: '{_get_keepass_entry(config)}'")
        print(f"  is_configured(): {is_configured(config)}")

    if not is_configured(config):
        msg = "Email integration is not fully configured (server, sender, or KeePass entry missing)"
        _last_test_result = {"success": False, "error": msg}
        return False, msg

    username, password = _get_credentials(config)
    if not username or not password:
        msg = "Failed to retrieve SMTP credentials from KeePass (database locked or entry not found)"
        _last_test_result = {"success": False, "error": msg}
        return False, msg

    try:
        server = _get_smtp_server(config)
        port = _get_smtp_port(config)
        use_tls = _get_smtp_use_tls(config)

        if _is_debug():
            print(f"[email_integration] Testing connection to {server}:{port} (TLS: {use_tls})")

        smtp = smtplib.SMTP(server, port, timeout=30)
        code, _ = smtp.ehlo()

        if _is_debug():
            print(f"[email_integration] EHLO accepted (code {code})")

        if use_tls:
            if smtp.has_extn("STARTTLS"):
                smtp.starttls()
                smtp.ehlo()
                if _is_debug():
                    print("[email_integration] STARTTLS negotiated")
            elif _is_debug():
                print("[email_integration] Warning: Server does not support STARTTLS")

        try:
            smtp.login(username, password)
            if _is_debug():
                print(f"[email_integration] Authenticated as '{username}'")
        except smtplib.SMTPAuthenticationError as exc:
            error = f"SMTP authentication failed: {exc}"
            if _is_debug():
                print(f"[email_integration] {error}")
            smtp.quit()
            _last_test_result = {"success": False, "error": error}
            return False, error

        smtp.quit()

        _last_test_result = {"success": True, "server": server, "port": port, "username": username}
        return True, ""

    except smtplib.SMTPException as exc:
        error = f"SMTP error: {exc}"
        if _is_debug():
            print(f"[email_integration] {error}")
        _last_test_result = {"success": False, "error": error}
        return False, error
    except Exception as exc:
        error = f"Unexpected error testing connection: {exc}"
        if _is_debug():
            print(f"[email_integration] {error}")
        _last_test_result = {"success": False, "error": error}
        return False, error


def get_config_summary() -> dict:
    """Return a summary of email integration configuration for debug dump.

    Passwords and KeePass entry names are never included.
    Includes legacy top-level keys (configured, smtp_server, …) for backward
    compatibility alongside the new multi-config fields.
    """
    sm = _get_settings_manager()
    configs = sm.get_email_configs() if sm and hasattr(sm, "get_email_configs") else []
    if isinstance(configs, list):
        safe_configs = [
            {
                "name": c.get("name", ""),
                "smtp_server": c.get("smtp_server", ""),
                "smtp_port": c.get("smtp_port", 587),
                "smtp_use_tls": c.get("smtp_use_tls", True),
                "keepass_entry_set": bool(c.get("keepass_entry", "")),
            }
            for c in configs if isinstance(c, dict)
        ]
    else:
        safe_configs = []

    active_name = ""
    if sm and hasattr(sm, "get_active_email_config_name"):
        _n = sm.get_active_email_config_name()
        if isinstance(_n, str):
            active_name = _n

    active = get_active_config()  # already guarded by isinstance(dict)

    return {
        # Legacy keys (backward compat with existing tests and app_debug.py)
        "configured": is_configured(),
        "smtp_server": _get_smtp_server(),
        "smtp_port": _get_smtp_port(),
        "smtp_use_tls": _get_smtp_use_tls(),
        "sender_address": _get_sender_address(),
        "keepass_entry_set": bool(_get_keepass_entry()),
        # Multi-config fields
        "num_configs": len(safe_configs),
        "active_config_name": active_name,
        "active_configured": is_configured(active),
        "configs": safe_configs,
        "last_send":   _last_send_result,
        "last_test":   _last_test_result,
        "last_export": _last_export_result,
    }


def get_last_send_result() -> Optional[dict]:
    """Return the result dict of the last send_email() call, or None."""
    return _last_send_result


def get_last_test_result() -> Optional[dict]:
    """Return the result dict of the last test_connection() call, or None."""
    return _last_test_result
