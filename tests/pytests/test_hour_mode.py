"""Tests for views/hour_mode.py — Hourly zoom mode helper functions and header widget.

Helper functions (read_work_hours, working_day_count, date_to_working_day_idx,
datetime_to_hourly_x) are tested without QApplication requirement.

HourModeHeader widget tests require the session-scoped 'qapp' fixture.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch
from PyQt5.QtCore import QDate, QTime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# conftest.py is auto-loaded by pytest, but we need the path for imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from conftest import make_mock_ldt


# ---------------------------------------------------------------------------
# read_work_hours()
# ---------------------------------------------------------------------------

class TestReadWorkHours:
    def test_returns_default_when_no_calendar(self):
        from hour_mode import read_work_hours
        project = MagicMock()
        project.getDefaultCalendar.return_value = None
        result = read_work_hours(project)
        assert result == (8, 17, 9, frozenset())  # 8am to 5pm, 9 hours, no breaks

    def test_returns_default_when_none_project(self):
        from hour_mode import read_work_hours
        result = read_work_hours(None)
        assert result == (8, 17, 9, frozenset())

    def test_reads_work_hours_from_calendar(self):
        from hour_mode import read_work_hours
        project = MagicMock()
        calendar = MagicMock()
        # Mock Java LocalTime objects
        start_time = MagicMock()
        start_time.getHour.return_value = 9
        finish_time = MagicMock()
        finish_time.getHour.return_value = 18
        
        hours = MagicMock()
        hours.getStart.return_value = start_time
        hours.getEnd.return_value = finish_time
        
        calendar.getCalendarHours.return_value = [hours]
        project.getDefaultCalendar.return_value = calendar
        
        result = read_work_hours(project)
        assert result == (9, 18, 9, frozenset())  # 9am to 6pm, 9 hours, no breaks

    def test_handles_empty_calendar_hours_list(self):
        from hour_mode import read_work_hours
        project = MagicMock()
        calendar = MagicMock()
        calendar.getCalendarHours.return_value = []
        project.getDefaultCalendar.return_value = calendar
        
        result = read_work_hours(project)
        assert result == (8, 17, 9, frozenset())

    def test_handles_exception_gracefully(self):
        from hour_mode import read_work_hours
        project = MagicMock()
        project.getDefaultCalendar.side_effect = Exception("Calendar error")
        
        result = read_work_hours(project)
        assert result == (8, 17, 9, frozenset())


# ---------------------------------------------------------------------------
# working_day_count()
# ---------------------------------------------------------------------------

class TestWorkingDayCount:
    def test_zero_days_returns_zero(self):
        from hour_mode import working_day_count
        start = QDate(2025, 1, 6)  # Monday
        result = working_day_count(start, 0)
        assert result == 0

    def test_one_weekday_returns_one(self):
        from hour_mode import working_day_count
        monday = QDate(2025, 1, 6)
        result = working_day_count(monday, 1)
        assert result == 1

    def test_five_days_monday_to_friday(self):
        from hour_mode import working_day_count
        monday = QDate(2025, 1, 6)
        result = working_day_count(monday, 5)
        assert result == 5

    def test_seven_days_includes_weekend(self):
        from hour_mode import working_day_count
        monday = QDate(2025, 1, 6)
        result = working_day_count(monday, 7)
        assert result == 5  # Only weekdays counted

    def test_fourteen_days_two_work_weeks(self):
        from hour_mode import working_day_count
        monday = QDate(2025, 1, 6)
        result = working_day_count(monday, 14)
        assert result == 10

    def test_starts_on_saturday(self):
        from hour_mode import working_day_count
        saturday = QDate(2025, 1, 11)
        result = working_day_count(saturday, 3)  # Sat, Sun, Mon
        assert result == 1  # Only Monday counts

    def test_starts_on_sunday(self):
        from hour_mode import working_day_count
        sunday = QDate(2025, 1, 12)
        result = working_day_count(sunday, 2)  # Sun, Mon
        assert result == 1  # Only Monday counts


# ---------------------------------------------------------------------------
# date_to_working_day_idx()
# ---------------------------------------------------------------------------

class TestDateToWorkingDayIdx:
    def test_same_date_returns_zero(self):
        from hour_mode import date_to_working_day_idx
        monday = QDate(2025, 1, 6)
        result = date_to_working_day_idx(monday, monday)
        assert result == 0

    def test_next_weekday_returns_one(self):
        from hour_mode import date_to_working_day_idx
        monday = QDate(2025, 1, 6)
        tuesday = QDate(2025, 1, 7)
        result = date_to_working_day_idx(tuesday, monday)
        assert result == 1

    def test_friday_after_monday_returns_four(self):
        from hour_mode import date_to_working_day_idx
        monday = QDate(2025, 1, 6)
        friday = QDate(2025, 1, 10)
        result = date_to_working_day_idx(friday, monday)
        assert result == 4

    def test_weekend_days_not_counted(self):
        from hour_mode import date_to_working_day_idx
        friday = QDate(2025, 1, 10)
        monday_next = QDate(2025, 1, 13)
        result = date_to_working_day_idx(monday_next, friday)
        assert result == 1  # Only Monday next week is 1 working day from Friday

    def test_two_weeks_later(self):
        from hour_mode import date_to_working_day_idx
        monday1 = QDate(2025, 1, 6)
        monday2 = QDate(2025, 1, 20)  # 10 working days later
        result = date_to_working_day_idx(monday2, monday1)
        assert result == 10


# ---------------------------------------------------------------------------
# datetime_to_hourly_x()
# ---------------------------------------------------------------------------

class TestDatetimeToHourlyX:
    def test_start_of_day_first_working_day(self):
        from hour_mode import datetime_to_hourly_x
        # Monday 8am
        dt = make_mock_ldt(2025, 1, 6, 8, 0)
        start = QDate(2025, 1, 6)
        # Parameters: java_datetime, project_start, day_width, work_hour_start, clock_day_span, show_off_hours
        result = datetime_to_hourly_x(dt, start, 40, 8, 9, False)
        assert result == 0

    def test_noon_on_first_day(self):
        from hour_mode import datetime_to_hourly_x
        # Monday 12pm (4 hours into workday)
        dt = make_mock_ldt(2025, 1, 6, 12, 0)
        start = QDate(2025, 1, 6)
        # Parameters: java_datetime, project_start, day_width, work_hour_start, clock_day_span, show_off_hours
        result = datetime_to_hourly_x(dt, start, 40, 8, 9, False)
        assert result == 4 * 40  # 160 pixels

    def test_end_of_day_first_working_day(self):
        from hour_mode import datetime_to_hourly_x
        # Monday 5pm: clamped to 16:59 by the function (end-of-day boundary)
        dt = make_mock_ldt(2025, 1, 6, 17, 0)
        start = QDate(2025, 1, 6)
        result = datetime_to_hourly_x(dt, start, 40, 8, 9, False)
        assert result == pytest.approx(9 * 40, abs=1)

    def test_second_working_day_start(self):
        from hour_mode import datetime_to_hourly_x
        # Tuesday 8am (9 hours from Monday start)
        dt = make_mock_ldt(2025, 1, 7, 8, 0)
        start = QDate(2025, 1, 6)
        # Parameters: java_datetime, project_start, day_width, work_hour_start, clock_day_span, show_off_hours
        result = datetime_to_hourly_x(dt, start, 40, 8, 9, False)
        assert result == 9 * 40  # 360 pixels

    def test_before_work_hours_clamps_to_start(self):
        from hour_mode import datetime_to_hourly_x
        # Monday 6am (before work hours)
        dt = make_mock_ldt(2025, 1, 6, 6, 0)
        start = QDate(2025, 1, 6)
        # Parameters: java_datetime, project_start, day_width, work_hour_start, clock_day_span, show_off_hours
        result = datetime_to_hourly_x(dt, start, 40, 8, 9, False)
        # Should clamp to start of day (8am) which is x=0
        assert result < 40  # Close to 0

    def test_after_work_hours_uses_actual_hour(self):
        from hour_mode import datetime_to_hourly_x
        # Monday 8pm (overtime)
        dt = make_mock_ldt(2025, 1, 6, 20, 0)
        start = QDate(2025, 1, 6)
        # Parameters: java_datetime, project_start, day_width, work_hour_start, clock_day_span, show_off_hours
        # With show_off_hours=True, should show 24-hour clock
        result = datetime_to_hourly_x(dt, start, 40, 0, 24, True)
        # 20 hours from midnight = 800 pixels
        assert result == 20 * 40


# ---------------------------------------------------------------------------
# HourModeHeader widget
# ---------------------------------------------------------------------------

@pytest.fixture
def hour_header(qapp):
    """Return a fresh HourModeHeader widget configured for testing."""
    from hour_mode import HourModeHeader
    start = QDate(2025, 1, 6)  # Monday
    header = HourModeHeader(header_height=42)
    # Configure it with project parameters
    header.configure(start, 10, 40, 8, 9, frozenset())
    return header


class TestHourModeHeaderInit:
    def test_widget_is_created(self, qapp):
        from hour_mode import HourModeHeader
        header = HourModeHeader(header_height=42)
        assert header is not None

    def test_has_correct_height(self, hour_header):
        # Should have configured height
        assert hour_header.height() == 42

    def test_stores_project_start(self, hour_header):
        from PyQt5.QtCore import QDate
        # After configure() is called, should store project_start
        assert hour_header._project_start == QDate(2025, 1, 6)

    def test_stores_work_days(self, hour_header):
        # After configure(start, 10, ...) total_days should be 10
        assert hour_header._total_days == 10

    def test_stores_work_hours(self, hour_header):
        # After configure(..., work_hour_start=8, clock_day_span=9, ...)
        assert hour_header._work_hour_start == 8
        assert hour_header._clock_day_span == 9

    def test_stores_pixels_per_hour(self, hour_header):
        # After configure(..., day_width=40, ...)
        assert hour_header._day_width == 40


class TestHourModeHeaderPaintEvent:
    def test_paint_does_not_crash(self, qapp, hour_header):
        from PyQt5.QtGui import QPaintEvent
        from PyQt5.QtCore import QRect
        # Trigger paint event
        event = QPaintEvent(QRect(0, 0, hour_header.width(), hour_header.height()))
        hour_header.paintEvent(event)
        # If we get here without exception, paint succeeded
        assert True

    def test_calculates_total_width(self, qapp):
        from hour_mode import HourModeHeader
        header = HourModeHeader(header_height=42)
        start = QDate(2025, 1, 6)
        # Configure with 5 total days, 40px day_width, work_hour_start=8, clock_day_span=9
        header.configure(start, 5, 40, 8, 9, frozenset())
        # Width calculation depends on implementation
        # Just verify it has some reasonable width
        assert header.width() > 0
