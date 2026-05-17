"""
playwright_review_html.py
=========================
Review HTML files in documentation/presentation/ and documentation/user_documentation/
using Playwright Chromium.

For each file the script:
  1. Opens the page in a headless Chromium browser
  2. Waits for all iframes to finish loading
  3. Captures a full-page screenshot (PNG)
  4. Collects:
       - Console errors / warnings
       - Broken images (naturalWidth == 0)
       - Missing iframe title attributes
       - JavaScript page errors
       - Encoding errors (U+FFFD replacement character, stray zero-width chars)
  5. Writes a plain-text report to temp/playwright_review_report_<flag>.txt
  6. Writes an HTML report to tests/documentation/playwright_review_html_<flag>.html

Usage:
    python tools/playwright_review_html.py [--presentation] [--user-docs] [--all]
    (default: --all)

Screenshots are saved to temp/playwright_screenshots/<flag>/<dir>/<filename>.png
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

# ── Unicode confusable / ambiguous character detection ──────────────────────
# A small representative set of common confusables that look like ASCII but
# are actually different Unicode code points (common copy-paste pitfalls from
# PDF/Word sources, or HTML character-entity mistakes).
CONFUSABLE_RANGES = [
    # Latin lookalikes
    (0x00C0, 0x024F),   # Latin Extended-A/B — intentional in most docs, only flag non-latin context
    # Greek letters that look like latin
    0x0391, 0x0392, 0x0395, 0x0396, 0x0397, 0x0399, 0x039A, 0x039C, 0x039D,
    0x039F, 0x03A1, 0x03A4, 0x03A5, 0x03A7,
    # Cyrillic letters that look like latin
    0x0410, 0x0412, 0x0415, 0x041A, 0x041C, 0x041D, 0x041E, 0x0420, 0x0421,
    0x0422, 0x0425, 0x0430, 0x0435, 0x043E, 0x0440, 0x0441, 0x0443, 0x0445,
    # Smart quotes / curly quotes that should be HTML entities
    0x2018, 0x2019, 0x201C, 0x201D,
    # Em dash / en dash as raw chars (should be &mdash; / &ndash;)
    0x2013, 0x2014,
    # Non-breaking space as visible character confusion
    0x00A0,
    # Zero-width characters
    0x200B, 0x200C, 0x200D, 0xFEFF,
    # Replacement character
    0xFFFD,
]

# Characters we always want to flag (encoding errors, zero-width spaces/non-joiners, BOM)
# NOTE: U+200D (ZWJ) is intentionally excluded — commonly used in emoji sequences.
# NOTE: em/en dashes (U+2013/2014) and smart quotes (U+2018-201D) are intentionally
#       excluded — they are valid UTF-8 content in HTML text and often rendered from
#       &mdash;/&ndash;/&ldquo; etc. entities.
ALWAYS_FLAG = {
    0x200B,   # Zero Width Space
    0x200C,   # Zero Width Non-Joiner
    0xFEFF,   # BOM / Zero Width No-Break Space (in content)
    0x00AD,   # Soft Hyphen (invisible, confusing in copy-paste)
    0xFFFD,   # Replacement character (encoding error)
}

# Characters that are suspicious when they appear in otherwise-ASCII text
SUSPICIOUS_NON_ASCII = set(ALWAYS_FLAG)


def find_suspicious_chars(text: str) -> list[tuple[int, str, str]]:
    """Return list of (pos, char, description) for suspicious Unicode in text."""
    findings = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        if cp == 0xFFFD:
            findings.append((i, ch, "replacement character U+FFFD (encoding error)"))
        elif cp in ALWAYS_FLAG:
            name = {
                0x200B: "zero-width space U+200B",
                0x200C: "zero-width non-joiner U+200C",
                0xFEFF: "BOM/ZWNBSP U+FEFF in content",
                0x00AD: "soft hyphen U+00AD",
            }.get(cp, f"zero-width/control U+{cp:04X}")
            findings.append((i, ch, name))
    return findings


# ── JS snippets executed in the browser ──────────────────────────────────────

JS_COLLECT_ISSUES = """
() => {
    const issues = [];

    // 1. Broken images
    document.querySelectorAll('img').forEach(img => {
        if (!img.complete || img.naturalWidth === 0) {
            issues.push({type: 'broken_img', src: img.src || img.getAttribute('src'), alt: img.alt});
        }
        if (!img.hasAttribute('alt')) {
            issues.push({type: 'missing_alt', src: img.src || img.getAttribute('src')});
        }
    });

    // 2. Broken iframes (src set but contentDocument inaccessible for cross-origin,
    //    but for local file:// they should all be accessible)
    document.querySelectorAll('iframe').forEach(fr => {
        const doc = fr.contentDocument;
        if (!doc) {
            issues.push({type: 'iframe_no_doc', src: fr.src || fr.getAttribute('src')});
        }
    });

    // 3. Empty anchors (links with no text and no title)
    document.querySelectorAll('a[href]').forEach(a => {
        const text = a.textContent.trim();
        const title = a.getAttribute('title') || '';
        const hasImg = a.querySelector('img') !== null;
        if (!text && !title && !hasImg) {
            issues.push({type: 'empty_link', href: a.getAttribute('href')});
        }
    });

    // 4. Elements with overflow (content clipped)
    // (lightweight check — only flag direct body children with scrollHeight > clientHeight)
    Array.from(document.body.children).forEach(el => {
        const style = getComputedStyle(el);
        if ((style.overflow === 'hidden' || style.overflowY === 'hidden')
                && el.scrollHeight > el.clientHeight + 5) {
            issues.push({type: 'overflow_hidden', tag: el.tagName, id: el.id || '', cls: el.className || ''});
        }
    });

    return issues;
}
"""

JS_GET_VISIBLE_TEXT = """
() => {
    // Collect text from all visible text nodes (skip script/style)
    const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
        {
            acceptNode(node) {
                const tag = node.parentElement && node.parentElement.tagName;
                if (tag === 'SCRIPT' || tag === 'STYLE') return NodeFilter.FILTER_REJECT;
                // Check visibility
                const el = node.parentElement;
                if (!el) return NodeFilter.FILTER_REJECT;
                const style = getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') return NodeFilter.FILTER_REJECT;
                return NodeFilter.FILTER_ACCEPT;
            }
        }
    );
    const parts = [];
    let node;
    while ((node = walker.nextNode())) {
        parts.push(node.textContent);
    }
    return parts.join('');
}
"""

JS_IFRAME_TITLES = """
() => {
    const result = [];
    document.querySelectorAll('iframe').forEach(fr => {
        result.push({
            src: fr.getAttribute('src') || '',
            title: fr.getAttribute('title') || '',
            width: fr.width, height: fr.height
        });
    });
    return result;
}
"""


async def review_file(page, file_path: Path, screenshots_dir: Path, report_lines: list) -> dict:
    """Review one HTML file. Returns a structured result dict and appends to report_lines."""
    url = file_path.as_uri()

    result = {
        "file": file_path.name,
        "checks": [],   # list of {"severity": "error"|"warning"|"info", "icon": str, "text": str}
        "iframe_count": 0,
        "nav_error": False,
    }

    report_lines.append(f"\n{'='*72}")
    report_lines.append(f"FILE: {file_path.relative_to(file_path.parent.parent)}")
    report_lines.append(f"{'='*72}")

    console_messages = []
    page.on("console", lambda msg: console_messages.append((msg.type, msg.text)))
    page_errors = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception as e:
        msg = f"Navigation error: {e}"
        report_lines.append(f"  ❌ {msg}")
        result["checks"].append({"severity": "error", "icon": "❌", "text": msg})
        result["nav_error"] = True
        return result

    try:
        await page.wait_for_timeout(1200)
    except Exception:
        pass

    # Screenshot
    screenshot_path = screenshots_dir / (file_path.stem + ".png")
    try:
        await page.screenshot(path=str(screenshot_path), full_page=True, timeout=15000)
        report_lines.append(f"  📸 Screenshot: {screenshot_path.name}")
    except Exception as e:
        report_lines.append(f"  ⚠️  Screenshot failed: {e}")

    # DOM issues
    try:
        dom_issues = await page.evaluate(JS_COLLECT_ISSUES)
        for issue in dom_issues:
            t = issue.get("type")
            if t == "broken_img":
                msg = f"Broken image: src={issue.get('src')} alt={issue.get('alt')}"
                report_lines.append(f"  ❌ {msg}")
                result["checks"].append({"severity": "error", "icon": "❌", "text": msg})
            elif t == "missing_alt":
                msg = f"Missing alt attribute: src={issue.get('src')}"
                report_lines.append(f"  ⚠️  {msg}")
                result["checks"].append({"severity": "warning", "icon": "⚠️", "text": msg})
            elif t == "iframe_no_doc":
                msg = f"iframe inaccessible (cross-origin?): src={issue.get('src')}"
                report_lines.append(f"  ⚠️  {msg}")
                result["checks"].append({"severity": "warning", "icon": "⚠️", "text": msg})
            elif t == "empty_link":
                msg = f"Empty link (no text, no title, no img): href={issue.get('href')}"
                report_lines.append(f"  ⚠️  {msg}")
                result["checks"].append({"severity": "warning", "icon": "⚠️", "text": msg})
            elif t == "overflow_hidden":
                msg = f"Content clipped (overflow:hidden): &lt;{issue.get('tag')} id={issue.get('id')} class={issue.get('cls')}&gt;"
                report_lines.append(f"  ⚠️  Content clipped: <{issue.get('tag')} id={issue.get('id')}>")
                result["checks"].append({"severity": "warning", "icon": "⚠️", "text": msg})
    except Exception as e:
        report_lines.append(f"  ⚠️  DOM issue collection failed: {e}")

    # Visible text — encoding errors only
    try:
        visible_text = await page.evaluate(JS_GET_VISIBLE_TEXT)
        findings = find_suspicious_chars(visible_text)
        seen: set = set()
        for pos, ch, desc in findings:
            key = (ch, desc)
            if key not in seen:
                seen.add(key)
                ctx_start = max(0, pos - 20)
                ctx_end = min(len(visible_text), pos + 20)
                ctx = visible_text[ctx_start:ctx_end].replace("\n", " ")
                msg = f"Encoding error — char '{ch}' ({desc}): &hellip;{ctx}&hellip;"
                report_lines.append(f"  ❌ Encoding error — char '{ch}' ({desc}): ...{ctx}...")
                result["checks"].append({"severity": "error", "icon": "❌", "text": msg})
    except Exception as e:
        report_lines.append(f"  ⚠️  Text scan failed: {e}")

    # Console errors/warnings
    for msg_type, msg_text in console_messages:
        if msg_type == "error":
            msg = f"Console error: {msg_text}"
            report_lines.append(f"  ❌ {msg}")
            result["checks"].append({"severity": "error", "icon": "❌", "text": msg})
        elif msg_type == "warning":
            msg = f"Console warning: {msg_text}"
            report_lines.append(f"  ⚠️  {msg}")
            result["checks"].append({"severity": "warning", "icon": "⚠️", "text": msg})

    # Page errors
    for err in page_errors:
        msg = f"JS page error: {err}"
        report_lines.append(f"  ❌ {msg}")
        result["checks"].append({"severity": "error", "icon": "❌", "text": msg})

    # iframe titles
    try:
        iframes = await page.evaluate(JS_IFRAME_TITLES)
        result["iframe_count"] = len(iframes)
        if iframes:
            report_lines.append(f"  📋 iframes ({len(iframes)}):")
        for fr in iframes:
            src = fr.get("src", "")
            if not fr.get("title"):
                msg = f"iframe missing title attribute: src={src}"
                report_lines.append(f"       ⚠️  No title: src={src}")
                result["checks"].append({"severity": "warning", "icon": "⚠️", "text": msg})
    except Exception as e:
        report_lines.append(f"  ⚠️  iframe check failed: {e}")

    # Recurse into same-origin iframes
    try:
        for frame in page.frames[1:]:
            frame_url = frame.url
            if not frame_url or frame_url == "about:blank":
                continue
            fname = Path(frame_url).name
            try:
                frame_issues = await frame.evaluate(JS_COLLECT_ISSUES)
                for issue in frame_issues:
                    t = issue.get("type")
                    if t == "broken_img":
                        msg = f"[iframe {fname}] Broken image: src={issue.get('src')}"
                        report_lines.append(f"  ❌ {msg}")
                        result["checks"].append({"severity": "error", "icon": "❌", "text": msg})
                    elif t == "missing_alt":
                        msg = f"[iframe {fname}] Missing alt: src={issue.get('src')}"
                        report_lines.append(f"  ⚠️  {msg}")
                        result["checks"].append({"severity": "warning", "icon": "⚠️", "text": msg})

                frame_text = await frame.evaluate(JS_GET_VISIBLE_TEXT)
                frame_findings = find_suspicious_chars(frame_text)
                seen2: set = set()
                for pos, ch, desc in frame_findings:
                    key = (ch, desc)
                    if key not in seen2:
                        seen2.add(key)
                        ctx_start = max(0, pos - 20)
                        ctx_end = min(len(frame_text), pos + 20)
                        ctx = frame_text[ctx_start:ctx_end].replace("\n", " ")
                        msg = f"[iframe {fname}] Encoding error — '{ch}' ({desc}): &hellip;{ctx}&hellip;"
                        report_lines.append(f"  ❌ [iframe {fname}] Encoding error: '{ch}' ({desc})")
                        result["checks"].append({"severity": "error", "icon": "❌", "text": msg})
            except Exception:
                pass
    except Exception:
        pass

    has_errors = any(c["severity"] == "error" for c in result["checks"])
    has_warnings = any(c["severity"] == "warning" for c in result["checks"])
    if not has_errors and not has_warnings:
        report_lines.append("  ✅ No issues found")
        result["checks"].append({"severity": "pass", "icon": "✅", "text": "No issues found"})

    return result


def generate_html_report(dir_results: list[dict], flag_name: str, generated_at: str) -> str:
    """
    Generate an HTML report matching the style of tests/pytests/documentation/*.html.
    dir_results: list of {"dir_name": str, "dir_path_rel": str, "files": [result_dict, ...]}
    """
    total_files = sum(len(d["files"]) for d in dir_results)
    total_errors = sum(
        sum(1 for c in f["checks"] if c["severity"] == "error")
        for d in dir_results for f in d["files"]
    )
    total_warnings = sum(
        sum(1 for c in f["checks"] if c["severity"] == "warning")
        for d in dir_results for f in d["files"]
    )
    total_passed = sum(
        1 for d in dir_results for f in d["files"]
        if not any(c["severity"] in ("error", "warning") for c in f["checks"])
    )
    total_failed = sum(
        1 for d in dir_results for f in d["files"]
        if any(c["severity"] == "error" for c in f["checks"])
    )
    total_warned = total_files - total_passed - total_failed
    scope_label = {"all": "All directories", "presentation": "Presentation only",
                   "user_docs": "User documentation only"}.get(flag_name, flag_name)

    # ── Nav items ──
    nav_sections_html = ""
    for dr in dir_results:
        nav_sections_html += f'  <span class="nav-section">{dr["dir_name"]}</span>\n'
        for fr in dr["files"]:
            anchor = _file_anchor(dr["dir_name"], fr["file"])
            has_err = any(c["severity"] == "error" for c in fr["checks"])
            has_warn = any(c["severity"] == "warning" for c in fr["checks"])
            status_icon = "❌ " if has_err else ("⚠️ " if has_warn else "✅ ")
            nav_sections_html += f'  <a href="#{anchor}">{status_icon}{fr["file"]}</a>\n'

    # ── Module blocks ──
    modules_html = ""
    for dr in dir_results:
        dir_errors = sum(
            sum(1 for c in f["checks"] if c["severity"] == "error") for f in dr["files"]
        )
        dir_warnings = sum(
            sum(1 for c in f["checks"] if c["severity"] == "warning") for f in dr["files"]
        )
        dir_passed = sum(
            1 for f in dr["files"]
            if not any(c["severity"] in ("error", "warning") for c in f["checks"])
        )
        badge_parts = [f'{len(dr["files"])} files']
        if dir_errors:
            badge_parts.append(f'{dir_errors} ❌')
        if dir_warnings:
            badge_parts.append(f'{dir_warnings} ⚠️')
        if not dir_errors and not dir_warnings:
            badge_parts.append('✅ all clean')
        badge_text = ' &nbsp;|&nbsp; '.join(badge_parts)

        chapters_html = ""
        for fr in dr["files"]:
            anchor = _file_anchor(dr["dir_name"], fr["file"])
            has_err = any(c["severity"] == "error" for c in fr["checks"])
            has_warn = any(c["severity"] == "warning" for c in fr["checks"])
            file_icon = "❌" if has_err else ("⚠️" if has_warn else "✅")
            err_cnt = sum(1 for c in fr["checks"] if c["severity"] == "error")
            warn_cnt = sum(1 for c in fr["checks"] if c["severity"] == "warning")

            if has_err or has_warn:
                summary_parts = []
                if err_cnt:
                    summary_parts.append(f'{err_cnt} error{"s" if err_cnt > 1 else ""}')
                if warn_cnt:
                    summary_parts.append(f'{warn_cnt} warning{"s" if warn_cnt > 1 else ""}')
                if fr["iframe_count"]:
                    summary_parts.append(f'{fr["iframe_count"]} iframe{"s" if fr["iframe_count"] > 1 else ""}')
                ch_badge = ' &nbsp;&middot;&nbsp; '.join(summary_parts)
                ch_badge_cls = "error" if has_err else "warn"
            else:
                ch_badge = "No issues"
                if fr["iframe_count"]:
                    ch_badge += f' &nbsp;&middot;&nbsp; {fr["iframe_count"]} iframe{"s" if fr["iframe_count"] > 1 else ""}'
                ch_badge_cls = "pass"

            # Build check rows
            checks_html = ""
            for chk in fr["checks"]:
                sev = chk["severity"]
                row_cls = {"error": "check-error", "warning": "check-warn",
                           "pass": "check-pass", "info": "check-info"}.get(sev, "check-info")
                checks_html += (
                    f'<div class="check-row {row_cls}">'
                    f'<span class="check-icon">{chk["icon"]}</span>'
                    f'<span class="check-text">{chk["text"]}</span>'
                    f'</div>\n'
                )

            chapters_html += f"""
<div class="chapter" id="{anchor}">
  <div class="chapter-header" onclick="toggle(this)">
    <span class="arrow">&#9660;</span>
    <span class="ch-icon">{file_icon}</span>
    <h3>{fr["file"]}</h3>
    <span class="ch-badge {ch_badge_cls}">{ch_badge}</span>
  </div>
  <div class="chapter-body">
{checks_html}  </div>
</div>"""

        modules_html += f"""
<div class="module" id="{_dir_anchor(dr["dir_name"])}">
  <div class="module-header">
    <h2>&#128196; {dr["dir_path_rel"]}</h2>
    <span class="badge">{badge_text}</span>
  </div>
  <div class="module-desc">Playwright Chromium review: broken images, missing iframe titles, JS errors, encoding errors (U+FFFD, stray zero-width chars).</div>
{chapters_html}
</div>"""

    # ── Stat color helpers ──
    err_color = "#dc3545" if total_failed else "var(--pass)"
    warn_color = "#fd7e14" if total_warned else "#198754"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HTML Review Report &#8212; Playwright Chromium</title>
<style>
  :root {{
    --accent:  #0069d9;
    --pass:    #198754;
    --bg-sec:  #f8f9fa;
    --border:  #dee2e6;
    --code-bg: #e9ecef;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 14px;
    color: #212529;
    background: #fff;
    padding: 0 0 60px;
  }}
  header {{
    background: var(--accent);
    color: #fff;
    padding: 24px 40px 18px;
  }}
  header h1 {{ font-size: 1.8em; font-weight: 600; }}
  header p  {{ margin-top: 6px; opacity: .85; }}
  .page-body {{ display: flex; align-items: flex-start; }}
  nav {{
    position: sticky; top: 0; max-height: 100vh; overflow-y: auto;
    width: 200px; min-width: 200px;
    background: var(--bg-sec); border-right: 1px solid var(--border);
    padding: 14px 10px;
    display: flex; flex-direction: column; gap: 2px;
    z-index: 100; flex-shrink: 0;
  }}
  nav .nav-section {{
    font-size: .68em; text-transform: uppercase; letter-spacing: .08em;
    color: #999; padding: 8px 6px 3px; margin-top: 6px;
  }}
  nav .nav-section:first-child {{ margin-top: 0; }}
  nav a {{
    color: var(--accent); text-decoration: none; font-size: .8em;
    padding: 3px 8px; border-radius: 3px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block;
  }}
  nav a:hover {{ background: #dce8fb; }}
  nav a.active {{ background: var(--accent); color: #fff; font-weight: 600; }}
  main {{ flex: 1; padding: 28px 32px 0; min-width: 0; }}
  .stats {{
    display: flex; gap: 24px; flex-wrap: wrap;
    margin-bottom: 28px;
    background: var(--bg-sec); border: 1px solid var(--border);
    border-radius: 6px; padding: 14px 20px;
  }}
  .stat {{ text-align: center; }}
  .stat-n {{ font-size: 1.6em; font-weight: 700; }}
  .stat-l {{ font-size: .75em; color: #666; margin-top: 2px; }}
  .module {{
    border: 1px solid var(--border); border-radius: 6px;
    margin-bottom: 32px; overflow: hidden;
  }}
  .module-header {{
    background: var(--accent); color: #fff;
    padding: 10px 18px; display: flex; align-items: baseline; gap: 12px;
  }}
  .module-header h2 {{ font-size: 1em; font-weight: 600; }}
  .module-header .badge {{
    background: rgba(255,255,255,.25); border-radius: 12px;
    padding: 1px 9px; font-size: .78em;
  }}
  .module-desc {{
    background: #e8f0fe; border-bottom: 1px solid var(--border);
    padding: 8px 18px; font-style: italic; color: #444; font-size: .88em;
  }}
  .chapter {{ border-bottom: 1px solid var(--border); }}
  .chapter:last-child {{ border-bottom: none; }}
  .chapter-header {{
    background: var(--bg-sec); padding: 8px 18px; cursor: pointer;
    display: flex; align-items: center; gap: 10px; user-select: none;
  }}
  .chapter-header:hover {{ background: #e9ecef; }}
  .chapter-header h3 {{ font-size: .92em; font-weight: 600; color: #333; flex: 1; }}
  .arrow {{ font-size: .8em; color: #888; transition: transform .2s; }}
  .chapter-header.collapsed .arrow {{ transform: rotate(-90deg); }}
  .ch-icon {{ font-size: 1em; flex-shrink: 0; }}
  .ch-badge {{
    margin-left: auto; border-radius: 10px;
    padding: 2px 10px; font-size: .75em; white-space: nowrap; font-weight: 600;
  }}
  .ch-badge.pass    {{ background: #d1e7dd; color: #0a3622; border: 1px solid #a3cfbb; }}
  .ch-badge.warn    {{ background: #fff3cd; color: #664d03; border: 1px solid #ffda6a; }}
  .ch-badge.error   {{ background: #f8d7da; color: #58151c; border: 1px solid #f1aeb5; }}
  .chapter-body {{ padding: 8px 18px 12px; display: flex; flex-direction: column; gap: 4px; }}
  .check-row {{
    display: flex; align-items: flex-start; gap: 8px;
    padding: 5px 10px; border-radius: 4px; font-size: .87em;
  }}
  .check-error  {{ background: #fff5f5; border: 1px solid #f1aeb5; }}
  .check-warn   {{ background: #fffbf0; border: 1px solid #ffda6a; }}
  .check-pass   {{ background: #f0fff4; border: 1px solid #a3cfbb; }}
  .check-info   {{ background: var(--bg-sec); border: 1px solid var(--border); }}
  .check-icon   {{ flex-shrink: 0; font-size: .95em; margin-top: 1px; }}
  .check-text   {{ font-family: "Consolas", monospace; font-size: .9em; color: #333; word-break: break-all; }}
  code {{
    background: var(--code-bg); border-radius: 3px;
    padding: 1px 4px; font-family: "Consolas",monospace; font-size: .9em;
  }}
</style>
</head>
<body>

<header>
  <h1>&#127760; HTML Review Report &#8212; Playwright Chromium</h1>
  <p>Generated: {generated_at} &nbsp;|&nbsp; Browser: Chromium headless &nbsp;|&nbsp; Scope: {scope_label}</p>
</header>

<div class="page-body">

<nav>
{nav_sections_html}
</nav>

<main>

<div class="stats">
  <div class="stat"><div class="stat-n" style="color:var(--accent)">{total_files}</div><div class="stat-l">Files</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--pass)">{total_passed}</div><div class="stat-l">Passed</div></div>
  <div class="stat"><div class="stat-n" style="color:{err_color}">{total_failed}</div><div class="stat-l">Failed</div></div>
  <div class="stat"><div class="stat-n" style="color:{warn_color}">{total_warned}</div><div class="stat-l">Warnings</div></div>
  <div class="stat"><div class="stat-n" style="color:var(--accent)">{total_errors}</div><div class="stat-l">Errors</div></div>
  <div class="stat"><div class="stat-n" style="color:{warn_color}">{total_warnings}</div><div class="stat-l">Warnings&nbsp;(total)</div></div>
</div>

{modules_html}

</main>
</div><!-- /.page-body -->
<script>
function toggle(hdr) {{
  hdr.classList.toggle('collapsed');
  const body = hdr.nextElementSibling;
  body.style.display = body.style.display === 'none' ? '' : 'none';
}}
(function () {{
  const navLinks = Array.from(document.querySelectorAll('nav a[href^="#"]'));
  const targets  = navLinks.map(a => document.getElementById(a.getAttribute('href').slice(1))).filter(Boolean);
  function onScroll() {{
    let cur = targets[0];
    for (const m of targets) {{
      if (m.getBoundingClientRect().top <= 80) cur = m;
    }}
    navLinks.forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + cur.id));
  }}
  window.addEventListener('scroll', onScroll, {{ passive: true }});
  onScroll();
}})();
</script>
</body>
</html>"""
    return html


def _file_anchor(dir_name: str, filename: str) -> str:
    stem = Path(filename).stem
    prefix = "pres" if dir_name == "presentation" else "udoc"
    return f"{prefix}_{stem}"


def _dir_anchor(dir_name: str) -> str:
    return dir_name.replace(" ", "_").replace("/", "_")


async def main():
    parser = argparse.ArgumentParser(description="Playwright HTML reviewer")
    parser.add_argument("--presentation", action="store_true")
    parser.add_argument("--user-docs", action="store_true")
    parser.add_argument("--all", action="store_true", default=True)
    args = parser.parse_args()

    root = Path(__file__).parent.parent
    pres_dir = root / "documentation" / "presentation"
    udoc_dir = root / "documentation" / "user_documentation"
    temp_dir = root / "temp"
    temp_dir.mkdir(exist_ok=True)

    # Determine active flag name for output file naming
    if args.presentation and not args.user_docs:
        flag_name = "presentation"
    elif args.user_docs and not args.presentation:
        flag_name = "user_docs"
    else:
        flag_name = "all"

    screenshots_root = temp_dir / "playwright_screenshots" / flag_name

    target_dirs = []
    if args.presentation or args.all:
        target_dirs.append(("presentation", pres_dir))
    if args.user_docs or args.all:
        target_dirs.append(("user_documentation", udoc_dir))

    import datetime
    generated_at = datetime.datetime.now().isoformat(timespec="seconds")

    report_lines = [
        "Playwright HTML Review Report",
        f"Generated: {generated_at}",
        f"Browser: Chromium (headless)",
        "",
    ]

    from playwright.async_api import async_playwright

    dir_results = []

    total_files = sum(len(list(dp.glob("*.html"))) for _, dp in target_dirs)
    print(f"[playwright] Launching Chromium … ({total_files} files to review)", flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-web-security',
                '--allow-file-access-from-files',
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1400, "height": 900},
            ignore_https_errors=True,
        )
        page = await context.new_page()
        print(f"[playwright] Browser ready.", flush=True)

        file_idx = 0
        for dir_name, dir_path in target_dirs:
            html_files = sorted(dir_path.glob("*.html"))
            screenshots_dir = screenshots_root / dir_name
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            print(f"\n[dir] {dir_path.relative_to(root)}  ({len(html_files)} files)", flush=True)
            report_lines.append(f"\n{'#'*72}")
            report_lines.append(f"# DIRECTORY: {dir_path.relative_to(root)}")
            report_lines.append(f"# {len(html_files)} HTML files")
            report_lines.append(f"{'#'*72}")

            file_results = []
            for html_file in html_files:
                file_idx += 1
                print(f"  [{file_idx}/{total_files}] {html_file.name} …", end=" ", flush=True)
                result = await review_file(page, html_file, screenshots_dir, report_lines)
                has_err  = any(c["severity"] == "error"   for c in result["checks"])
                has_warn = any(c["severity"] == "warning" for c in result["checks"])
                status = "❌" if has_err else ("⚠️" if has_warn else "✅")
                print(status, flush=True)
                file_results.append(result)

            dir_results.append({
                "dir_name": dir_name,
                "dir_path_rel": str(dir_path.relative_to(root)),
                "files": file_results,
            })

        await browser.close()
    print(f"\n[playwright] Browser closed.", flush=True)

    # ── Text report ──
    report_path = temp_dir / f"playwright_review_report_{flag_name}.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print("\n".join(report_lines))
    print(f"\nReport written to: {report_path}")
    print(f"Screenshots in:    {screenshots_root}")

    # ── HTML report (only for --all) ──
    if flag_name == "all":
        html_report_dir = root / "tests" / "documentation"
        html_report_dir.mkdir(parents=True, exist_ok=True)
        html_report_path = html_report_dir / f"playwright_review_html_{flag_name}.html"
        html_content = generate_html_report(dir_results, flag_name, generated_at)
        html_report_path.write_text(html_content, encoding="utf-8")
        print(f"HTML report:       {html_report_path}")

    # Exit with error code if any issues were found
    has_errors   = any(c["severity"] == "error"   for d in dir_results for f in d["files"] for c in f["checks"])
    has_warnings = any(c["severity"] == "warning" for d in dir_results for f in d["files"] for c in f["checks"])
    if has_errors or has_warnings:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
