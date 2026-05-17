# baseline_manager.py - Baseline tracking business logic
#
# Provides set_baseline, clear_baseline, get_active_baselines and per-task
# variance helpers for comparing the current schedule against any of the 11
# baseline slots (Baseline 0 through Baseline 10).
#
# MPXJ Python API notes (via JPype):
#   task.getBaselineStart()            — slot 0 start
#   task.getBaselineStart(int n)       — slot n start  (1-10)
#   task.setBaselineStart(ldt)         — set slot 0 start
#   task.set(TaskField.BASELINE1_START, ldt) — set slot 1 start
#   props.getBaselineDate()            — when slot 0 was captured
#   props.getBaselineDate(int n)       — when slot n was captured
#
# See documentation/mpxj/Baselines.md for the full reference.


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------

def baseline_label(number: int) -> str:
    """Human-readable label for a baseline slot (0 → 'Baseline', 1 → 'Baseline 1' …)."""
    return "Baseline" if number == 0 else f"Baseline {number}"


# ---------------------------------------------------------------------------
# TaskField name arrays (indexed 0-10)
# ---------------------------------------------------------------------------

_START_FIELDS:    list[str] = ["BASELINE_START"]    + [f"BASELINE{n}_START"    for n in range(1, 11)]
_FINISH_FIELDS:   list[str] = ["BASELINE_FINISH"]   + [f"BASELINE{n}_FINISH"   for n in range(1, 11)]
_DURATION_FIELDS: list[str] = ["BASELINE_DURATION"] + [f"BASELINE{n}_DURATION" for n in range(1, 11)]

_DATE_PROP_FIELDS: list[str] = ["BASELINE_DATE"] + [f"BASELINE{n}_DATE" for n in range(1, 11)]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _task_field(name: str):
    """Return a Java TaskField constant by name, or None on failure."""
    try:
        from org.mpxj import TaskField  # type: ignore
        return TaskField.valueOf(name)
    except Exception:
        return None


def _props_field(name: str):
    """Return a Java ProjectPropertiesField constant by name, or None on failure."""
    try:
        from org.mpxj import ProjectPropertiesField  # type: ignore
        return ProjectPropertiesField.valueOf(name)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def set_baseline(project, number: int = 0) -> None:
    """Snapshot the current schedule into baseline slot *number* (0–10).

    Copies Start, Finish and Duration for every named task into the
    corresponding baseline attributes, then records today's date in
    ProjectProperties so the slot shows as 'set'.
    """
    if project is None:
        return
    if not 0 <= number <= 10:
        raise ValueError(f"Baseline number must be 0-10, got {number}")

    if number == 0:
        # Slot 0 has dedicated setters
        for task in project.getTasks():
            if task.getName() is None:
                continue
            try:
                task.setBaselineStart(task.getStart())
                task.setBaselineFinish(task.getFinish())
                task.setBaselineDuration(task.getDuration())
            except Exception as exc:
                print(f"[WARN] set_baseline(0) task '{task.getName()}': {exc}")
    else:
        sf = _task_field(_START_FIELDS[number])
        ff = _task_field(_FINISH_FIELDS[number])
        df = _task_field(_DURATION_FIELDS[number])
        for task in project.getTasks():
            if task.getName() is None:
                continue
            try:
                if sf is not None:
                    task.set(sf, task.getStart())
                if ff is not None:
                    task.set(ff, task.getFinish())
                if df is not None:
                    task.set(df, task.getDuration())
            except Exception as exc:
                print(f"[WARN] set_baseline({number}) task '{task.getName()}': {exc}")

    # Record capture timestamp in ProjectProperties
    try:
        from java.time import LocalDateTime  # type: ignore
        now  = LocalDateTime.now()
        props = project.getProjectProperties()
        if number == 0:
            props.setBaselineDate(now)
        else:
            props.setBaselineDate(number, now)
    except Exception as exc:
        print(f"[WARN] set_baseline({number}) capture date: {exc}")


def clear_baseline(project, number: int = 0) -> None:
    """Remove all baseline data for slot *number* (0–10)."""
    if project is None:
        return
    if not 0 <= number <= 10:
        raise ValueError(f"Baseline number must be 0-10, got {number}")

    if number == 0:
        for task in project.getTasks():
            if task.getName() is None:
                continue
            try:
                task.setBaselineStart(None)
                task.setBaselineFinish(None)
                task.setBaselineDuration(None)
            except Exception as exc:
                print(f"[WARN] clear_baseline(0) task '{task.getName()}': {exc}")
    else:
        sf = _task_field(_START_FIELDS[number])
        ff = _task_field(_FINISH_FIELDS[number])
        df = _task_field(_DURATION_FIELDS[number])
        for task in project.getTasks():
            if task.getName() is None:
                continue
            try:
                if sf is not None:
                    task.set(sf, None)
                if ff is not None:
                    task.set(ff, None)
                if df is not None:
                    task.set(df, None)
            except Exception as exc:
                print(f"[WARN] clear_baseline({number}) task '{task.getName()}': {exc}")

    # Clear capture date
    try:
        props = project.getProjectProperties()
        if number == 0:
            props.setBaselineDate(None)
        else:
            props.setBaselineDate(number, None)
    except Exception as exc:
        print(f"[WARN] clear_baseline({number}) capture date: {exc}")


def get_active_baselines(project) -> dict:
    """Return {slot_number: iso_date_str} for every baseline slot that has been set.

    A slot is considered 'set' if its ProjectProperties capture date is non-null,
    OR if at least one task has a non-null baseline start for that slot.
    """
    result: dict[int, str] = {}
    if project is None:
        return result

    try:
        props = project.getProjectProperties()
        for n in range(11):
            try:
                d = props.getBaselineDate() if n == 0 else props.getBaselineDate(n)
                if d is not None:
                    result[n] = str(d)[:19].replace("T", " ")
            except Exception:
                pass
    except Exception:
        pass

    # Fallback: if no date recorded, check whether any task has baseline start data
    if not result:
        tasks = [t for t in project.getTasks() if t.getName() is not None]
        for n in range(11):
            for task in tasks:
                try:
                    bs = task.getBaselineStart() if n == 0 else task.getBaselineStart(n)
                    if bs is not None:
                        result[n] = "(no date)"
                        break
                except Exception:
                    pass

    return result


# ---------------------------------------------------------------------------
# Per-task helpers
# ---------------------------------------------------------------------------

def get_baseline_start(task, number: int = 0):
    """Return Java LocalDateTime for task baseline start in slot *number*, or None."""
    try:
        return task.getBaselineStart() if number == 0 else task.getBaselineStart(number)
    except Exception:
        return None


def get_baseline_finish(task, number: int = 0):
    """Return Java LocalDateTime for task baseline finish in slot *number*, or None."""
    try:
        return task.getBaselineFinish() if number == 0 else task.getBaselineFinish(number)
    except Exception:
        return None


def get_baseline_duration(task, number: int = 0):
    """Return Java Duration for task baseline duration in slot *number*, or None."""
    try:
        return task.getBaselineDuration() if number == 0 else task.getBaselineDuration(number)
    except Exception:
        return None


def get_variance_between(task, n_a: int, n_b: int) -> dict:
    """Compute variance between two baseline slots for *task*.

    n_a is the reference ("from") baseline; n_b is the comparison ("to") baseline.
    Returns the same structure as get_variance().
    """
    bs_a = get_baseline_start(task, n_a)
    bf_a = get_baseline_finish(task, n_a)
    bd_a = get_baseline_duration(task, n_a)
    bs_b = get_baseline_start(task, n_b)
    bf_b = get_baseline_finish(task, n_b)
    bd_b = get_baseline_duration(task, n_b)

    result: dict = {"start_days": None, "finish_days": None, "duration_pct": None}

    try:
        if bs_a is not None and bs_b is not None:
            from java.time.temporal import ChronoUnit  # type: ignore
            result["start_days"] = int(ChronoUnit.DAYS.between(bs_a, bs_b))
    except Exception:
        pass

    try:
        if bf_a is not None and bf_b is not None:
            from java.time.temporal import ChronoUnit  # type: ignore
            result["finish_days"] = int(ChronoUnit.DAYS.between(bf_a, bf_b))
    except Exception:
        pass

    try:
        if bd_a is not None and bd_b is not None:
            a_d = float(str(bd_a.getDuration()))
            b_d = float(str(bd_b.getDuration()))
            if a_d > 0:
                result["duration_pct"] = round((b_d - a_d) / a_d * 100.0, 1)
    except Exception:
        pass

    return result


def get_variance(task, number: int = 0) -> dict:
    """Compute schedule variance for *task* against baseline slot *number*.

    Returns a dict:
        start_days   (int | None)   — positive = current is later than baseline
        finish_days  (int | None)   — positive = current is later than baseline
        duration_pct (float | None) — positive = longer than baseline
    """
    b_start  = get_baseline_start(task, number)
    b_finish = get_baseline_finish(task, number)
    b_dur    = get_baseline_duration(task, number)

    result: dict = {"start_days": None, "finish_days": None, "duration_pct": None}

    try:
        c_start = task.getStart()
        if b_start is not None and c_start is not None:
            from java.time.temporal import ChronoUnit  # type: ignore
            result["start_days"] = int(ChronoUnit.DAYS.between(b_start, c_start))
    except Exception:
        pass

    try:
        c_finish = task.getFinish()
        if b_finish is not None and c_finish is not None:
            from java.time.temporal import ChronoUnit  # type: ignore
            result["finish_days"] = int(ChronoUnit.DAYS.between(b_finish, c_finish))
    except Exception:
        pass

    try:
        c_dur = task.getDuration()
        if b_dur is not None and c_dur is not None:
            b_days = float(str(b_dur.getDuration()))
            a_days = float(str(c_dur.getDuration()))
            if b_days > 0:
                result["duration_pct"] = round((a_days - b_days) / b_days * 100.0, 1)
    except Exception:
        pass

    return result
