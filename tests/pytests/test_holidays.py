"""Tests for holidays.py — Public holiday computation module.

Covers:
  - Internal helpers: _easter(), _buss_und_bettag(), _nth_weekday()
  - default_holiday_years()
  - german_national_holidays()
  - german_state_extra_holidays()  (per-state spot checks)
  - france_holidays(), india_holidays(), romania_holidays(),
    china_holidays(), japan_holidays()
  - add_holidays_to_calendar()  (MPXJ mocked)

No JVM or Qt is required — all MPXJ objects are replaced with MagicMock.
"""

import datetime
import sys
import os
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import holidays as hol


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestEasterCalculation:
    def test_known_easter_2025(self):
        """Western Easter 2025 is April 20 (Gregorian)."""
        assert hol._easter(2025) == datetime.date(2025, 4, 20)

    def test_easter_is_sunday(self):
        for year in [2020, 2021, 2022, 2023, 2024, 2025, 2026]:
            assert hol._easter(year).weekday() == 6, f"Easter {year} should be Sunday"

    def test_easter_in_march_or_april(self):
        for year in range(2020, 2031):
            m = hol._easter(year).month
            assert m in (3, 4), f"Easter {year} month={m} expected 3 or 4"


class TestBussUndBettag:
    def test_result_is_wednesday(self):
        """Buß- und Bettag is always a Wednesday."""
        for year in range(2020, 2030):
            d = hol._buss_und_bettag(year)
            assert d.weekday() == 2, f"{year}: {d} is not Wednesday"

    def test_before_nov_23(self):
        """Buß- und Bettag falls on or before November 23 (it IS Nov 23 when that date is a Wednesday)."""
        for year in range(2020, 2030):
            d = hol._buss_und_bettag(year)
            assert d <= datetime.date(year, 11, 23)
            assert d >= datetime.date(year, 11, 16)


class TestNthWeekday:
    def test_first_monday_january_2025(self):
        """First Monday of January 2025 is January 6."""
        assert hol._nth_weekday(2025, 1, 1, 0) == datetime.date(2025, 1, 6)

    def test_second_monday_january_2025(self):
        """Second Monday of January 2025 is January 13."""
        assert hol._nth_weekday(2025, 1, 2, 0) == datetime.date(2025, 1, 13)


# ---------------------------------------------------------------------------
# default_holiday_years
# ---------------------------------------------------------------------------

class TestDefaultHolidayYears:
    def test_returns_range(self):
        result = hol.default_holiday_years()
        assert isinstance(result, range)

    def test_starts_at_current_year_minus_2(self):
        cy = datetime.date.today().year
        result = hol.default_holiday_years()
        assert result.start == cy - 2

    def test_ends_at_current_year_plus_12(self):
        """Range covers 15 years: (cy-2) … (cy+12) inclusive."""
        cy = datetime.date.today().year
        result = hol.default_holiday_years()
        assert (cy + 12) in result


# ---------------------------------------------------------------------------
# German national holidays
# ---------------------------------------------------------------------------

class TestGermanNationalHolidays:
    def test_returns_list(self):
        result = hol.german_national_holidays([2025])
        assert isinstance(result, list)

    def test_nine_holidays_per_year(self):
        result = hol.german_national_holidays([2025])
        assert len(result) == 9

    def test_neujahr_is_jan_1(self):
        result = hol.german_national_holidays([2025])
        dates_names = {name: d for d, name in result}
        assert dates_names["Neujahr"] == datetime.date(2025, 1, 1)

    def test_tag_der_deutschen_einheit_is_oct_3(self):
        result = hol.german_national_holidays([2025])
        dates_names = {name: d for d, name in result}
        assert dates_names["Tag der Deutschen Einheit"] == datetime.date(2025, 10, 3)

    def test_entries_are_date_str_tuples(self):
        result = hol.german_national_holidays([2025])
        for item in result:
            assert isinstance(item, tuple)
            assert isinstance(item[0], datetime.date)
            assert isinstance(item[1], str)


# ---------------------------------------------------------------------------
# German state extra holidays
# ---------------------------------------------------------------------------

class TestGermanStateExtraHolidays:
    def test_bw_has_fronleichnam(self):
        result = hol.german_state_extra_holidays("Baden-Württemberg", [2025])
        names = [n for _, n in result]
        assert "Fronleichnam" in names

    def test_bw_has_heilige_drei_koenige(self):
        result = hol.german_state_extra_holidays("Baden-Württemberg", [2025])
        names = [n for _, n in result]
        assert "Heilige Drei Könige" in names

    def test_by_has_maria_himmelfahrt(self):
        result = hol.german_state_extra_holidays("Bayern", [2025])
        names = [n for _, n in result]
        assert "Mariä Himmelfahrt" in names

    def test_sachsen_has_buss_und_bettag(self):
        result = hol.german_state_extra_holidays("Sachsen", [2025])
        names = [n for _, n in result]
        assert "Buß- und Bettag" in names

    def test_thueringen_weltkindertag_from_2019(self):
        before = hol.german_state_extra_holidays("Thüringen", [2018])
        names_before = [n for _, n in before]
        assert "Weltkindertag" not in names_before
        after = hol.german_state_extra_holidays("Thüringen", [2019])
        names_after = [n for _, n in after]
        assert "Weltkindertag" in names_after

    def test_unknown_state_returns_empty(self):
        result = hol.german_state_extra_holidays("Atlantis", [2025])
        assert result == []


# ---------------------------------------------------------------------------
# France
# ---------------------------------------------------------------------------

class TestFranceHolidays:
    def test_returns_list(self):
        assert isinstance(hol.france_holidays([2025]), list)

    def test_eleven_holidays_per_year(self):
        result = hol.france_holidays([2025])
        assert len(result) == 11

    def test_fete_nationale_july_14(self):
        result = hol.france_holidays([2025])
        dates_names = {name: d for d, name in result}
        assert dates_names["Fête Nationale"] == datetime.date(2025, 7, 14)


# ---------------------------------------------------------------------------
# India
# ---------------------------------------------------------------------------

class TestIndiaHolidays:
    def test_returns_list(self):
        assert isinstance(hol.india_holidays([2025]), list)

    def test_republic_day_jan_26(self):
        result = hol.india_holidays([2025])
        dates_names = {name: d for d, name in result}
        assert dates_names["Republic Day"] == datetime.date(2025, 1, 26)

    def test_diwali_present_for_known_year(self):
        result = hol.india_holidays([2025])
        names = [n for _, n in result]
        assert "Diwali" in names

    def test_only_fixed_holidays_for_out_of_range_year(self):
        """Year 2050 is outside the movable-date lookup tables → only fixed dates."""
        result = hol.india_holidays([2050])
        names = [n for _, n in result]
        assert "Diwali" not in names
        assert "Republic Day" in names


# ---------------------------------------------------------------------------
# Romania
# ---------------------------------------------------------------------------

class TestRomaniaHolidays:
    def test_returns_list(self):
        assert isinstance(hol.romania_holidays([2025]), list)

    def test_ziua_nationala_dec_1(self):
        result = hol.romania_holidays([2025])
        dates_names = {name: d for d, name in result}
        assert dates_names["Ziua Națională"] == datetime.date(2025, 12, 1)

    def test_contains_craciun(self):
        result = hol.romania_holidays([2025])
        names = [n for _, n in result]
        assert "Crăciun (1)" in names


# ---------------------------------------------------------------------------
# China
# ---------------------------------------------------------------------------

class TestChinaHolidays:
    def test_returns_list(self):
        assert isinstance(hol.china_holidays([2025]), list)

    def test_national_day_oct_1(self):
        result = hol.china_holidays([2025])
        dates_names = {name: d for d, name in result}
        assert dates_names["National Day (Day 1)"] == datetime.date(2025, 10, 1)

    def test_spring_festival_present_for_known_year(self):
        result = hol.china_holidays([2025])
        names = [n for _, n in result]
        assert "Spring Festival (Day 1)" in names

    def test_only_fixed_holidays_for_out_of_range_year(self):
        result = hol.china_holidays([2050])
        names = [n for _, n in result]
        assert "Spring Festival (Day 1)" not in names
        assert "National Day (Day 1)" in names


# ---------------------------------------------------------------------------
# Japan
# ---------------------------------------------------------------------------

class TestJapanHolidays:
    def test_returns_list(self):
        assert isinstance(hol.japan_holidays([2025]), list)

    def test_new_years_day(self):
        result = hol.japan_holidays([2025])
        dates_names = {name: d for d, name in result}
        assert dates_names["New Year's Day"] == datetime.date(2025, 1, 1)

    def test_vernal_equinox_for_known_year(self):
        result = hol.japan_holidays([2025])
        names = [n for _, n in result]
        assert "Vernal Equinox Day" in names

    def test_coming_of_age_day_is_second_monday_january(self):
        """Coming of Age Day = 2nd Monday of January."""
        result = hol.japan_holidays([2025])
        dates_names = {name: d for d, name in result}
        d = dates_names["Coming of Age Day"]
        assert d.weekday() == 0           # Monday
        assert 8 <= d.day <= 14           # second Monday


# ---------------------------------------------------------------------------
# add_holidays_to_calendar
# ---------------------------------------------------------------------------

class TestAddHolidaysToCalendar:
    """add_holidays_to_calendar() inserts exceptions into an MPXJ calendar mock."""

    def _make_cal(self):
        cal = MagicMock()
        cal.getCalendarExceptions.return_value = []
        return cal

    def test_calls_add_calendar_exception(self):
        """Each holiday triggers addCalendarException on the calendar."""
        cal = self._make_cal()
        holidays = [(datetime.date(2025, 1, 1), "Neujahr")]
        with patch.dict('sys.modules', {'java.time': MagicMock()}):
            import java.time as jt
            jt.LocalDate.of.return_value = MagicMock()
            hol.add_holidays_to_calendar(cal, holidays)
        cal.addCalendarException.assert_called_once()

    def test_sets_exception_name(self):
        """The name from the holiday list is passed to ex.setName()."""
        cal = self._make_cal()
        holidays = [(datetime.date(2025, 10, 3), "Tag der Deutschen Einheit")]
        mock_ex = MagicMock()
        cal.addCalendarException.return_value = mock_ex
        with patch.dict('sys.modules', {'java.time': MagicMock()}):
            import java.time as jt
            jt.LocalDate.of.return_value = MagicMock()
            hol.add_holidays_to_calendar(cal, holidays)
        mock_ex.setName.assert_called_once_with("Tag der Deutschen Einheit")

    def test_skips_duplicate_dates(self):
        """A date already in the exception list is not added a second time."""
        existing_ex = MagicMock()
        existing_ex.getFromDate.return_value = MagicMock()
        existing_ex.getFromDate.return_value.__str__ = lambda _: "2025-01-01"
        cal = self._make_cal()
        cal.getCalendarExceptions.return_value = [existing_ex]

        holidays = [
            (datetime.date(2025, 1, 1), "Neujahr"),   # duplicate
            (datetime.date(2025, 5, 1), "Tag der Arbeit"),  # new
        ]
        with patch.dict('sys.modules', {'java.time': MagicMock()}):
            import java.time as jt
            jt.LocalDate.of.return_value = MagicMock()
            hol.add_holidays_to_calendar(cal, holidays)
        # Only the non-duplicate should be added
        assert cal.addCalendarException.call_count == 1

    def test_empty_holiday_list_adds_nothing(self):
        """An empty holiday list results in no addCalendarException calls."""
        cal = self._make_cal()
        with patch.dict('sys.modules', {'java.time': MagicMock()}):
            hol.add_holidays_to_calendar(cal, [])
        cal.addCalendarException.assert_not_called()
