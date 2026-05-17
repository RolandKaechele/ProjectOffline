# holidays.py

Pure-Python module that computes public-holiday date lists for a set of supported
countries and German federal states, and provides a helper to install those holidays
into an MPXJ `ProjectCalendar`.

No external library is required — all movable dates (Easter, Buß-und-Bettag, etc.)
are either computed algorithmically or hardcoded for the range 2018–2040.

## Public API

### `default_holiday_years() → range`

Returns a rolling range of years centred on the current calendar year:

```
range(current_year − 2, current_year + 13)
```

Callers pass this to any holiday-collection function to get a consistent,
forward-looking holiday set without having to manage the year range themselves.

---

### `german_national_holidays(years) → list[date]`

Returns all German nation-wide public holidays for the given years.

| Holiday | Date rule |
| ------- | --------- |
| New Year's Day | 1 Jan |
| Good Friday | Easter − 2 days |
| Easter Monday | Easter + 1 day |
| Labour Day | 1 May |
| Ascension Day | Easter + 39 days |
| Whit Monday | Easter + 50 days |
| German Unity Day | 3 Oct |
| Christmas Day | 25 Dec |
| 2nd Christmas Day | 26 Dec |

**Parameters**

| Name | Type | Description |
| ---- | ---- | ----------- |
| `years` | iterable of int | Calendar years to compute holidays for |

**Returns** `list[datetime.date]` — sorted, deduplicated list of holiday dates.

---

### `german_state_extra_holidays(state, years) → list[date]`

Returns the *extra* public holidays for one German federal state (i.e. holidays that
are **not** already in the national list).

**Supported states**

| Value | State |
| ----- | ----- |
| `"Baden-Württemberg"` | Epiphany (6 Jan), Corpus Christi, All Saints' Day (1 Nov) |
| `"Bayern"` | Epiphany, Corpus Christi, Assumption (15 Aug), All Saints', Buß-und-Bettag |
| `"Berlin"` | International Women's Day (8 Mar) |
| `"Brandenburg"` | Reformation Day (31 Oct) |
| `"Bremen"` | Reformation Day |
| `"Hamburg"` | Reformation Day |
| `"Hessen"` | Corpus Christi |
| `"Mecklenburg-Vorpommern"` | Reformation Day |
| `"Niedersachsen"` | Reformation Day |
| `"Nordrhein-Westfalen"` | Corpus Christi, All Saints' |
| `"Rheinland-Pfalz"` | Corpus Christi, Assumption, All Saints' |
| `"Saarland"` | Corpus Christi, Assumption, All Saints' |
| `"Sachsen"` | Corpus Christi, Reformation Day, Buß-und-Bettag |
| `"Sachsen-Anhalt"` | Epiphany, Reformation Day |
| `"Schleswig-Holstein"` | Reformation Day |
| `"Thüringen"` | Children's Day (20 Sep), Reformation Day |

Returns `[]` for unknown state values (no exception raised).

**Parameters**

| Name | Type | Description |
| ---- | ---- | ----------- |
| `state` | str | German federal state name (one of the 15 listed above) |
| `years` | iterable of int | Calendar years to compute holidays for |

**Returns** `list[datetime.date]`

---

### `france_holidays(years=None) → list[date]`

Returns French public holidays for the given years (defaults to
`default_holiday_years()` when `years` is omitted).

| Holiday | Date rule |
| ------- | --------- |
| New Year's Day | 1 Jan |
| Easter Monday | Easter + 1 |
| Labour Day | 1 May |
| Victory in Europe | 8 May |
| Ascension | Easter + 39 |
| Whit Monday | Easter + 50 |
| Bastille Day | 14 Jul |
| Assumption | 15 Aug |
| All Saints' | 1 Nov |
| Armistice Day | 11 Nov |
| Christmas | 25 Dec |

---

### `india_holidays(years=None) → list[date]`

Returns Indian national/public holidays for the given years.

| Holiday | Date |
| ------- | ---- |
| New Year's Day | 1 Jan |
| Republic Day | 26 Jan |
| Independence Day | 15 Aug |
| Gandhi Jayanti | 2 Oct |
| Christmas | 25 Dec |

Note: Movable religious festivals (Diwali, Holi, Eid, etc.) are not included because
their Gregorian dates vary annually and are not hardcoded.

---

### `romania_holidays(years=None) → list[date]`

Returns Romanian public holidays for the given years.

| Holiday | Date |
| ------- | ---- |
| New Year's Day | 1 Jan |
| Day after New Year | 2 Jan |
| Unification Day | 24 Jan |
| Orthodox Easter (Sat) | Orthodox Easter − 1 |
| Orthodox Easter | Orthodox Easter |
| Orthodox Easter Monday | Orthodox Easter + 1 |
| Labour Day | 1 May |
| Children's Day | 1 Jun |
| Whit Sunday (Orthodox) | Orthodox Easter + 49 |
| Whit Monday (Orthodox) | Orthodox Easter + 50 |
| Dormition of the Theotokos | 15 Aug |
| St Andrew's Day | 30 Nov |
| National Day | 1 Dec |
| Christmas | 25 Dec |
| 2nd Christmas | 26 Dec |

---

### `china_holidays(years=None) → list[date]`

Returns Chinese statutory public holidays for the given years.

| Holiday | Date |
| ------- | ---- |
| New Year's Day | 1 Jan |
| Spring Festival (CN New Year) | 1–7 Feb (fixed approximation) |
| Tomb Sweeping Day | 5 Apr |
| Labour Day | 1–5 May |
| Dragon Boat Festival | 10–12 Jun (fixed approximation) |
| National Day Golden Week | 1–7 Oct |

Note: The exact dates of lunar-based holidays vary year to year; this implementation
uses fixed Gregorian approximations.

---

### `japan_holidays(years=None) → list[date]`

Returns Japanese public holidays for the given years.

| Holiday | Date |
| ------- | ---- |
| New Year's Day | 1 Jan |
| Coming of Age Day | 2nd Monday of Jan |
| National Foundation Day | 11 Feb |
| Emperor's Birthday | 23 Feb |
| Vernal Equinox | 20 Mar |
| Shōwa Day | 29 Apr |
| Constitution Memorial Day | 3 May |
| Greenery Day | 4 May |
| Children's Day | 5 May |
| Marine Day | 3rd Monday of Jul |
| Mountain Day | 11 Aug |
| Respect for the Aged Day | 3rd Monday of Sep |
| Autumnal Equinox | 23 Sep |
| Sports Day | 2nd Monday of Oct |
| Culture Day | 3 Nov |
| Labour Thanksgiving Day | 23 Nov |
| Christmas Eve (observance) | 24 Dec |

---

### `add_holidays_to_calendar(cal, holidays)`

Installs a list of `datetime.date` objects as non-working exception days in an MPXJ
`ProjectCalendar`.

```python
add_holidays_to_calendar(project_calendar, german_national_holidays(default_holiday_years()))
```

For each date a `ProjectCalendarException` covering exactly that day is added to the
calendar with working type `NON_WORKING`.  If the date already has an exception it is
silently skipped.

**Parameters**

| Name | Type | Description |
| ---- | ---- | ----------- |
| `cal` | `ProjectCalendar` (MPXJ Java object) | Target calendar |
| `holidays` | iterable of `datetime.date` | Holiday dates to mark non-working |

---

## Internal Helpers

These functions are used internally; they are not part of the public API.

### `_easter(year) → date`

Anonymous Gregorian Easter date using the Anonymous Gregorian algorithm (O(1), valid
for the Gregorian calendar).

### `_orthodox_easter(year) → date`

Julian calendar Easter converted to the Gregorian calendar using the Julian-to-
Gregorian offset for the 21st century (13 days).

### `_buss_und_bettag(year) → date`

Computes the German Day of Repentance and Prayer — the Wednesday before 23 November.
If 23 November itself is a Wednesday it is returned directly.

### `_nth_weekday(year, month, n, weekday) → date`

Returns the n-th occurrence of `weekday` (0=Monday … 6=Sunday) in the given month.
Used for movable holidays such as Coming of Age Day in Japan and Sports Day.

## Coverage

The module has **90% test coverage** (43 tests in `tests/test_holidays.py`, IDs
HOL-01–HOL-43).  The uncovered lines are exclusively the fallback branches for years
outside the hardcoded 2018–2040 range of movable dates.

## Usage Example

```python
from holidays import (
    german_national_holidays,
    german_state_extra_holidays,
    add_holidays_to_calendar,
    default_holiday_years,
)

years = default_holiday_years()
cal = project.addCalendar()
cal.setName("Standard (Deutschland)")

# National holidays
add_holidays_to_calendar(cal, german_national_holidays(years))

# State-specific extras (Bavaria)
add_holidays_to_calendar(cal, german_state_extra_holidays("Bayern", years))
```
