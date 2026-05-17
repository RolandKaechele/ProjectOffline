# export_gantt.py - Export Gantt chart to SVG and PlantUML formats
#
# Exports:
#   export_gantt_svg(canvas, output_path)
#       Full Gantt chart (all visible tasks) → single SVG file
#   export_resource_gantt_svg(canvas, output_dir)
#       One SVG per resource (tasks assigned to that resource) → multiple SVG files
#   export_gantt_plantuml(canvas, output_path)
#       Full Gantt chart → PlantUML @startgantt file

import os
import re

from PyQt5.QtSvg import QSvgGenerator          # type: ignore
from PyQt5.QtGui import (                       # type: ignore
    QPainter, QColor, QFont, QPen, QPolygon, QBrush
)
from PyQt5.QtCore import Qt, QRect, QSize, QPoint, QDate  # type: ignore

# Re-use helpers and visual constants from the Gantt canvas module
from gantt_view import (                        # type: ignore
    _to_qdate, _compute_finish_date, _date_to_col,
    _get_visible_tasks, _get_non_working_dates, _compute_critical_ids,
    _normalize_schedule,
    ROW_HEIGHT, HEADER_MONTH_H, HEADER_WEEK_H, HEADER_HEIGHT, BASELINE_THICK,
)

# ------------------------------------------------------------------ #
# Layout constants for exports (task-name column is included)        #
# ------------------------------------------------------------------ #
EXPORT_LABEL_W = 220    # width of the task-name column in exported SVGs
_INDENT_PX     = 12     # indentation per outline level


# ================================================================== #
#  Public API                                                         #
# ================================================================== #

def export_gantt_svg(canvas, output_path: str) -> None:
    """Export the full visible Gantt chart to *output_path* as an SVG file."""
    _render_gantt_svg(
        path=output_path,
        tasks=canvas.tasks,
        project_start=canvas.project_start,
        total_days=canvas.total_days,
        day_width=canvas.day_width,
        show_sundays=canvas.show_sundays,
        non_working_dates=canvas._non_working_dates,
        critical_ids=canvas._critical_ids,
        show_resource_units=canvas.show_resource_units,
        title="Gantt Chart",
    )


def export_resource_gantt_svg(canvas, output_dir: str) -> int:
    """Export one SVG per work resource to *output_dir*.

    Only tasks that have at least one assignment to the resource are
    included.  Returns the number of SVG files written.
    """
    project = getattr(canvas, '_project', None)

    # Build resource → task list mapping directly from assignments
    res_tasks: dict = {}   # resource_name (str) → [task, ...]
    for task in canvas.tasks:
        try:
            for ass in task.getResourceAssignments():
                res = ass.getResource()
                if res is None:
                    continue
                rname = str(res.getName()) if res.getName() is not None else ""
                if not rname:
                    continue
                res_tasks.setdefault(rname, [])
                if task not in res_tasks[rname]:
                    res_tasks[rname].append(task)
        except Exception:
            pass

    if not res_tasks:
        return 0

    os.makedirs(output_dir, exist_ok=True)
    count = 0
    for rname, tasks in res_tasks.items():
        safe_name = _safe_filename(rname)
        path = os.path.join(output_dir, f"{safe_name}_gantt.svg")

        # Recompute timeline bounds for this resource's tasks
        starts   = [_to_qdate(t.getStart()) for t in tasks]
        starts   = [s for s in starts if s]
        finishes = [_compute_finish_date(t) for t in tasks]
        finishes = [f for f in finishes if f]

        if not starts:
            continue

        r_start     = min(starts)
        r_max_fin   = max(finishes) if finishes else r_start
        r_total_days = max(r_start.daysTo(r_max_fin) + 14, 30)

        r_non_working = _get_non_working_dates(None, r_start, r_total_days)
        r_critical    = canvas._critical_ids  # re-use project-wide critical set

        _render_gantt_svg(
            path=path,
            tasks=tasks,
            project_start=r_start,
            total_days=r_total_days,
            day_width=canvas.day_width,
            show_sundays=canvas.show_sundays,
            non_working_dates=r_non_working,
            critical_ids=r_critical,
            show_resource_units=canvas.show_resource_units,
            title=f"Gantt – {rname}",
        )
        count += 1

    return count


def export_gantt_plantuml(canvas, output_path: str) -> None:
    """Export the full visible Gantt chart to *output_path* as a PlantUML file."""
    tasks = canvas.tasks
    if not tasks or canvas.project_start is None:
        _write_text(output_path, "@startgantt\n@endgantt\n")
        return

    lines = ["@startgantt"]

    # Choose a time scale based on total project span
    total = canvas.total_days
    if total > 365:
        lines.append("printscale monthly")
    elif total > 90:
        lines.append("printscale weekly")
    else:
        lines.append("printscale daily")

    # Project start
    ps = canvas.project_start.toString("yyyy-MM-dd")
    lines.append(f"Project starts {ps}")
    lines.append("")

    # Collect task id → PlantUML alias for dependency links
    alias_map: dict = {}   # task_id (str) → alias (str)

    for task in tasks:
        name = str(task.getName()) if task.getName() else "(unnamed)"
        start = _to_qdate(task.getStart())
        finish = _compute_finish_date(task)
        if start is None:
            continue

        # Build a stable alias from the task ID
        try:
            tid = str(task.getID())
        except Exception:
            tid = name[:20]
        alias = f"T{tid}"
        alias_map[tid] = alias

        # Sanitize name (PlantUML uses [...] — strip brackets inside names)
        safe_name = name.replace("[", "(").replace("]", ")")

        is_milestone = False
        try:
            is_milestone = bool(task.getMilestone())
        except Exception:
            pass

        is_summary = False
        try:
            is_summary = bool(task.getSummary())
        except Exception:
            pass

        outline_level = 1
        try:
            ol = task.getOutlineLevel()
            if ol is not None:
                outline_level = int(str(ol))
        except Exception:
            pass

        if is_milestone:
            ds = start.toString("yyyy-MM-dd")
            lines.append(f"[{safe_name}] as [{alias}] happens at {ds}")
        else:
            ds = start.toString("yyyy-MM-dd")
            if finish:
                calendar_days = max(1, start.daysTo(finish))
            else:
                calendar_days = 1
            lines.append(f"[{safe_name}] as [{alias}] starts {ds} and lasts {calendar_days} days")

            # Percentage complete — use alias as identifier (display name is not the key)
            try:
                pct_raw = task.getPercentageComplete()
                if pct_raw is not None:
                    pct_val = int(float(str(pct_raw).replace("%", "")))
                    pct_val = max(0, min(100, pct_val))
                    if pct_val > 0:
                        lines.append(f"[{alias}] is {pct_val}% completed")
            except Exception:
                pass

            # Color — use alias as identifier
            try:
                task_id_int = int(tid)
                if task_id_int in canvas._critical_ids:
                    lines.append(f"[{alias}] is colored in Salmon")
                elif is_summary:
                    lines.append(f"[{alias}] is colored in Silver/Black")
            except Exception:
                pass

    # Dependency links (Finish-to-Start) — use aliases as identifiers, not display names.
    # PlantUML treats the ALIAS (second part of "as") as the task key for all references.
    lines.append("")
    for task in tasks:
        try:
            preds = task.getPredecessors()
            if not preds:
                continue
        except Exception:
            continue

        tid = str(task.getID()) if task.getID() is not None else ""
        succ_alias = alias_map.get(tid)
        if not succ_alias:
            continue

        for rel in preds:
            try:
                rel_type = str(rel.getType())
            except Exception:
                rel_type = "FINISH_START"
            if rel_type not in ("FS", "FINISH_START"):
                continue
            pred_task = rel.getPredecessorTask()
            if pred_task is None:
                continue
            pid = str(pred_task.getID()) if pred_task.getID() is not None else ""
            pred_alias = alias_map.get(pid)
            if not pred_alias:
                continue
            lines.append(f"[{succ_alias}] starts after [{pred_alias}]'s end")

    lines.append("")
    lines.append("@endgantt")
    _write_text(output_path, "\n".join(lines) + "\n")


# ================================================================== #
#  Internal rendering helpers                                         #
# ================================================================== #

def _render_gantt_svg(
    path: str,
    tasks: list,
    project_start: QDate,
    total_days: int,
    day_width: int,
    show_sundays: bool,
    non_working_dates: set,
    critical_ids: set,
    show_resource_units: bool,
    title: str = "",
) -> None:
    """Draw a complete Gantt chart (header + rows with task names) to an SVG file."""
    if not tasks or project_start is None:
        return

    vis_cols = _date_to_col(project_start, project_start.addDays(total_days), show_sundays)
    svg_w    = EXPORT_LABEL_W + vis_cols * day_width
    n_rows   = len(tasks)
    svg_h    = HEADER_HEIGHT + n_rows * ROW_HEIGHT

    gen = QSvgGenerator()
    gen.setFileName(path)
    gen.setSize(QSize(svg_w, svg_h))
    gen.setViewBox(QRect(0, 0, svg_w, svg_h))
    if title:
        gen.setTitle(title)

    p = QPainter()
    p.begin(gen)
    p.setRenderHint(QPainter.Antialiasing)

    # ---- calendar header ----
    _draw_header(p, project_start, total_days, day_width, show_sundays,
                 non_working_dates, EXPORT_LABEL_W, svg_w)

    # ---- task rows ----
    bar_rects = []
    for i, task in enumerate(tasks):
        br = _draw_task_row(p, i, task, project_start, day_width, show_sundays,
                            non_working_dates, critical_ids, show_resource_units,
                            total_days, EXPORT_LABEL_W, svg_w)
        bar_rects.append(br)

    # ---- dependency arrows ----
    _draw_dependency_arrows(p, tasks, bar_rects)

    # ---- today line ----
    today = QDate.currentDate()
    if project_start and today >= project_start:
        tc = _date_to_col(project_start, today, show_sundays)
        tx = EXPORT_LABEL_W + tc * day_width
        p.setPen(QPen(QColor(0, 168, 0), 2, Qt.SolidLine))
        p.drawLine(tx, HEADER_HEIGHT, tx, HEADER_HEIGHT + n_rows * ROW_HEIGHT)

    p.end()


def _draw_header(painter: QPainter, project_start: QDate, total_days: int,
                 day_width: int, show_sundays: bool, non_working_dates: set,
                 label_width: int, total_w: int) -> None:
    """Draw the two-row calendar header (month band + day numbers)."""
    font_bold  = QFont("Segoe UI", 9, QFont.Bold)
    font_small = QFont("Segoe UI", 7)

    # Task-name column header background
    painter.fillRect(0, 0, label_width, HEADER_HEIGHT, QColor(236, 243, 251))
    painter.setPen(QPen(QColor(100, 140, 200), 1))
    painter.setFont(font_bold)
    painter.setPen(QColor(40, 70, 130))
    painter.drawText(QRect(6, 0, label_width - 8, HEADER_MONTH_H),
                     Qt.AlignVCenter | Qt.AlignLeft, "Task Name")

    # ---- Month band ----
    d   = 0
    col = 0
    while d < total_days:
        date         = project_start.addDays(d)
        end_of_month = QDate(date.year(), date.month(), date.daysInMonth())
        cal_span     = min(date.daysTo(end_of_month) + 1, total_days - d)
        vis_span     = sum(
            1 for dd in range(d, d + cal_span)
            if show_sundays or project_start.addDays(dd).dayOfWeek() != 7
        )
        if vis_span == 0:
            d += cal_span
            continue
        x        = label_width + col * day_width
        month_px = vis_span * day_width
        bg = QColor(210, 228, 252) if date.month() % 2 == 0 else QColor(195, 215, 245)
        painter.fillRect(x, 0, month_px, HEADER_MONTH_H, bg)
        painter.setPen(QColor(26, 63, 122))
        painter.setFont(font_bold)
        label = date.toString("MMM yyyy") if month_px > 64 else date.toString("MMM")
        painter.drawText(QRect(x + 3, 0, month_px - 6, HEADER_MONTH_H),
                         Qt.AlignVCenter | Qt.AlignLeft, label)
        painter.setPen(QPen(QColor(140, 175, 215), 1))
        painter.drawLine(x, 0, x, HEADER_HEIGHT)
        col += vis_span
        d   += cal_span

    # ---- Day numbers ----
    painter.setFont(font_small)
    col = 0
    for d in range(total_days):
        date = project_start.addDays(d)
        dow  = date.dayOfWeek()
        if not show_sundays and dow == 7:
            continue
        x   = label_width + col * day_width
        col += 1
        iso = date.toString(Qt.ISODate)
        if dow == 6 or iso in non_working_dates:
            bg = QColor(215, 222, 238)
        elif dow == 1:
            bg = QColor(230, 240, 254)
        else:
            bg = QColor(242, 247, 255)
        painter.fillRect(x, HEADER_MONTH_H, day_width, HEADER_WEEK_H, bg)
        if day_width >= 14:
            painter.setPen(QColor(80, 100, 140))
            painter.drawText(QRect(x, HEADER_MONTH_H, day_width, HEADER_WEEK_H),
                             Qt.AlignCenter, str(date.day()))
        elif day_width >= 8 and dow == 1:
            painter.setPen(QColor(80, 100, 140))
            painter.drawText(QRect(x, HEADER_MONTH_H, day_width * 5, HEADER_WEEK_H),
                             Qt.AlignLeft | Qt.AlignVCenter,
                             f"W{date.weekNumber()[0]}")
        painter.setPen(QPen(QColor(215, 225, 240), 1))
        painter.drawLine(x, HEADER_MONTH_H, x, HEADER_HEIGHT)

    # Separator between label column and timeline
    painter.setPen(QPen(QColor(100, 140, 200), 1))
    painter.drawLine(label_width, 0, label_width, HEADER_HEIGHT)

    # Heavy bottom border
    painter.setPen(QPen(QColor(43, 87, 154), 2))
    painter.drawLine(0, HEADER_HEIGHT - 1, total_w, HEADER_HEIGHT - 1)


def _draw_task_row(painter: QPainter, row: int, task,
                   project_start: QDate, day_width: int, show_sundays: bool,
                   non_working_dates: set, critical_ids: set,
                   show_resource_units: bool,
                   total_days: int, label_width: int, total_w: int):
    """Draw one task row (background + name label + bar).  Returns bar geometry tuple."""
    y_top = HEADER_HEIGHT + row * ROW_HEIGHT

    # Row background (alternating)
    bg = QColor(245, 249, 255) if row % 2 == 0 else QColor(255, 255, 255)
    painter.fillRect(0, y_top, total_w, ROW_HEIGHT, bg)

    # Column shading for weekends / non-working days
    col = 0
    for d in range(total_days):
        date = project_start.addDays(d)
        dow  = date.dayOfWeek()
        if not show_sundays and dow == 7:
            continue
        x   = label_width + col * day_width
        col += 1
        iso = date.toString(Qt.ISODate)
        if dow == 6 or iso in non_working_dates:
            painter.fillRect(x, y_top, day_width, ROW_HEIGHT,
                             QColor(205, 215, 235, 140))

    # Separator between label column and timeline
    painter.setPen(QPen(QColor(180, 200, 230), 1))
    painter.drawLine(label_width, y_top, label_width, y_top + ROW_HEIGHT)

    # Row bottom border
    painter.setPen(QPen(QColor(220, 228, 240), 1))
    painter.drawLine(0, y_top + ROW_HEIGHT - 1, total_w, y_top + ROW_HEIGHT - 1)

    # Task name label
    name = str(task.getName()) if task.getName() else ""
    outline_level = 1
    try:
        ol = task.getOutlineLevel()
        if ol is not None:
            outline_level = int(str(ol))
    except Exception:
        pass
    is_summary = False
    try:
        is_summary = bool(task.getSummary())
    except Exception:
        pass

    indent = max(0, outline_level - 1) * _INDENT_PX
    font_name = QFont("Segoe UI", 8)
    if is_summary:
        font_name.setBold(True)
    painter.setFont(font_name)
    painter.setPen(QColor(20, 20, 20))
    painter.drawText(QRect(indent + 6, y_top, label_width - indent - 8, ROW_HEIGHT),
                     Qt.AlignVCenter | Qt.AlignLeft, name)

    # Bar geometry
    start_date  = _to_qdate(task.getStart())
    if not start_date:
        return (row, None, None, y_top, ROW_HEIGHT)

    finish_date = _compute_finish_date(task)
    if not finish_date:
        return (row, None, None, y_top, ROW_HEIGHT)

    x1 = label_width + _date_to_col(project_start, start_date, show_sundays) * day_width
    x2 = label_width + _date_to_col(project_start, finish_date, show_sundays) * day_width
    bar_w = max(x2 - x1, day_width)
    bar_h = ROW_HEIGHT - 8
    bar_y = y_top + 4

    # Baseline strip
    try:
        b1 = _to_qdate(task.getBaselineStart())
        b2 = _to_qdate(task.getBaselineFinish())
        if b1 and b2:
            bx1 = label_width + _date_to_col(project_start, b1, show_sundays) * day_width
            bx2 = label_width + _date_to_col(project_start, b2, show_sundays) * day_width
            painter.fillRect(bx1, bar_y + bar_h - BASELINE_THICK,
                             max(bx2 - bx1, day_width), BASELINE_THICK * 2,
                             QColor(80, 80, 200, 160))
    except Exception:
        pass

    is_milestone = False
    try:
        is_milestone = bool(task.getMilestone())
    except Exception:
        pass

    _tid = task.getID()
    try:
        is_critical = int(str(_tid)) in critical_ids if _tid is not None else False
    except Exception:
        is_critical = False

    if is_milestone:
        mid_x = x1 + bar_w // 2
        mid_y = bar_y + bar_h // 2
        s     = bar_h // 2
        diamond = QPolygon([
            QPoint(mid_x,     mid_y - s),
            QPoint(mid_x + s, mid_y),
            QPoint(mid_x,     mid_y + s),
            QPoint(mid_x - s, mid_y),
        ])
        painter.setBrush(QBrush(QColor(20, 20, 20)))
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.drawPolygon(diamond)

    elif is_summary:
        bar_dark = QColor(40, 40, 40)
        thin_h   = 7
        tri_w    = 9
        tri_h    = 10
        bar_top  = bar_y + 3
        x_right  = x1 + bar_w
        painter.setBrush(QBrush(bar_dark))
        painter.setPen(Qt.NoPen)
        painter.drawRect(x1, bar_top, bar_w, thin_h)
        painter.drawPolygon(QPolygon([
            QPoint(x1,          bar_top + thin_h),
            QPoint(x1 + tri_w,  bar_top + thin_h),
            QPoint(x1,          bar_top + thin_h + tri_h),
        ]))
        painter.drawPolygon(QPolygon([
            QPoint(x_right,         bar_top + thin_h),
            QPoint(x_right - tri_w, bar_top + thin_h),
            QPoint(x_right,         bar_top + thin_h + tri_h),
        ]))

    else:
        color = QColor(255, 120, 100) if is_critical else QColor(157, 195, 230)
        painter.fillRect(x1, bar_y, bar_w, bar_h, color)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(color.darker(120), 1))
        painter.drawRect(x1, bar_y, bar_w, bar_h)

        # Progress line
        try:
            pct_raw = task.getPercentageComplete()
            if pct_raw is not None:
                pct_val = float(str(pct_raw).replace("%", "")) / 100.0
                if pct_val > 0:
                    prog_w = int(bar_w * min(pct_val, 1.0))
                    mid_y  = bar_y + bar_h // 2
                    painter.setPen(QPen(QColor(0, 0, 0), 2))
                    painter.drawLine(x1, mid_y, x1 + prog_w, mid_y)
        except Exception:
            pass

        # Resource label
        res_parts = []
        try:
            for ass in task.getResourceAssignments():
                res = ass.getResource()
                if res is None:
                    continue
                rname = str(res.getName()) if res.getName() is not None else ""
                u = ass.getUnits()
                u_val = float(str(u)) if u is not None else 100.0
                if rname:
                    if show_resource_units:
                        res_parts.append(f"{rname} [{int(u_val)}%]")
                    else:
                        res_parts.append(rname)
        except Exception:
            pass

        if res_parts and day_width >= 6:
            label_x = x1 + bar_w + 4
            painter.setPen(QColor(40, 40, 40))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(QRect(label_x, bar_y, 200, bar_h),
                             Qt.AlignVCenter | Qt.AlignLeft,
                             ", ".join(res_parts))

    return (row, x1, x1 + bar_w, bar_y, bar_h)


def _draw_dependency_arrows(painter: QPainter, tasks: list, bar_rects: list) -> None:
    """Draw FS dependency arrows between task bars."""
    id_map = {}
    for task, br in zip(tasks, bar_rects):
        tid = task.getID()
        if tid is not None and br[1] is not None:
            id_map[int(str(tid))] = br

    pen = QPen(QColor(30, 30, 30), 1, Qt.SolidLine)
    pen.setCapStyle(Qt.RoundCap)

    for task, br in zip(tasks, bar_rects):
        if br[1] is None:
            continue
        _, x1, x2, bar_y, bar_h = br
        try:
            preds = task.getPredecessors()
            if not preds:
                continue
            for rel in preds:
                try:
                    rel_type = str(rel.getType())
                except Exception:
                    rel_type = "FINISH_START"
                if rel_type not in ("FS", "FINISH_START"):
                    continue
                pred_task = rel.getPredecessorTask()
                if pred_task is None:
                    continue
                pid = int(str(pred_task.getID()))
                if pid not in id_map:
                    continue
                _, px1, px2, p_bar_y, p_bar_h = id_map[pid]
                ah = 4
                if bar_y >= p_bar_y:
                    pred_exit_y = p_bar_y + p_bar_h
                    enter_y     = bar_y
                    approach_y  = enter_y - 5
                    painter.setPen(pen)
                    painter.drawLine(px2, pred_exit_y, px2, approach_y)
                    painter.drawLine(px2, approach_y,  x1,  approach_y)
                    painter.drawLine(x1,  approach_y,  x1,  enter_y)
                    painter.setBrush(QBrush(QColor(20, 20, 20)))
                    painter.setPen(Qt.NoPen)
                    painter.drawPolygon(QPolygon([
                        QPoint(x1,      enter_y),
                        QPoint(x1 - ah, enter_y - ah),
                        QPoint(x1 + ah, enter_y - ah),
                    ]))
                else:
                    pred_exit_y = p_bar_y
                    enter_y     = bar_y + bar_h
                    approach_y  = enter_y + 5
                    painter.setPen(pen)
                    painter.drawLine(px2, pred_exit_y, px2, approach_y)
                    painter.drawLine(px2, approach_y,  x1,  approach_y)
                    painter.drawLine(x1,  approach_y,  x1,  enter_y)
                    painter.setBrush(QBrush(QColor(20, 20, 20)))
                    painter.setPen(Qt.NoPen)
                    painter.drawPolygon(QPolygon([
                        QPoint(x1,      enter_y),
                        QPoint(x1 - ah, enter_y + ah),
                        QPoint(x1 + ah, enter_y + ah),
                    ]))
                painter.setBrush(Qt.NoBrush)
                painter.setPen(pen)
        except Exception:
            pass


# ================================================================== #
#  Utility helpers                                                    #
# ================================================================== #

def _safe_filename(name: str) -> str:
    """Return a filesystem-safe version of *name*."""
    safe = re.sub(r'[\\/:*?"<>|]', '_', name)
    safe = safe.strip(". ")
    return safe or "resource"


def _write_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
