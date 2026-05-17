# holidays.py – Public holiday computation for new-project calendar setup.
#
# Provides holiday lists (date, name) tuples for Germany (national + state),
# France, India, Romania, China and Japan.
# The helper add_holidays_to_calendar() inserts them into an MPXJ
# ProjectCalendar as non-working calendar exceptions.

from __future__ import annotations

import datetime
from typing import List, Tuple

HolidayList = List[Tuple[datetime.date, str]]


# --------------------------------------------------------------------------- #
# Calendar helpers                                                              #
# --------------------------------------------------------------------------- #

def _easter(year: int) -> datetime.date:
    """Western Easter Sunday (Meeus/Jones/Butcher algorithm, Gregorian)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day   = (h + l - 7 * m + 114) % 31 + 1
    return datetime.date(year, month, day)


def _orthodox_easter(year: int) -> datetime.date:
    """Orthodox Easter Sunday (Julian, converted to Gregorian by +13 days)."""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day   = (d + e + 114) % 31 + 1
    return datetime.date(year, month, day) + datetime.timedelta(days=13)


def _buss_und_bettag(year: int) -> datetime.date:
    """Buß- und Bettag: Wednesday before 23 November (Saxony)."""
    nov23 = datetime.date(year, 11, 23)
    # weekday(): Mon=0 … Wed=2
    days_back = (nov23.weekday() - 2) % 7
    return nov23 - datetime.timedelta(days=days_back)


def _nth_weekday(year: int, month: int, n: int, weekday: int) -> datetime.date:
    """Return the n-th occurrence (1-based) of *weekday* (Mon=0…Sun=6) in month."""
    first  = datetime.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + datetime.timedelta(days=offset + 7 * (n - 1))


def default_holiday_years() -> range:
    """Sensible range of years to cover for a new project (current−2 … current+12)."""
    cy = datetime.date.today().year
    return range(cy - 2, cy + 13)


# --------------------------------------------------------------------------- #
# Germany – national holidays (all 16 states)                                  #
# --------------------------------------------------------------------------- #

def german_national_holidays(years) -> HolidayList:
    """Public holidays common to all German federal states."""
    result: HolidayList = []
    for y in years:
        e = _easter(y)
        result += [
            (datetime.date(y, 1, 1),            "Neujahr"),
            (e - datetime.timedelta(days=2),     "Karfreitag"),
            (e + datetime.timedelta(days=1),     "Ostermontag"),
            (datetime.date(y, 5, 1),             "Tag der Arbeit"),
            (e + datetime.timedelta(days=39),    "Christi Himmelfahrt"),
            (e + datetime.timedelta(days=50),    "Pfingstmontag"),
            (datetime.date(y, 10, 3),            "Tag der Deutschen Einheit"),
            (datetime.date(y, 12, 25),           "1. Weihnachtstag"),
            (datetime.date(y, 12, 26),           "2. Weihnachtstag"),
        ]
    return result


# --------------------------------------------------------------------------- #
# Germany – state-specific extra holidays (beyond national ones)                #
# --------------------------------------------------------------------------- #

def german_state_extra_holidays(state: str, years) -> HolidayList:
    """Additional public holidays specific to the given German federal state.

    Only the holidays that are *additional* to the German national holidays are
    returned so that a derived child calendar does not duplicate entries from
    the parent Standard calendar.
    """
    result: HolidayList = []
    for y in years:
        e  = _easter(y)
        cc = e + datetime.timedelta(days=60)   # Fronleichnam / Corpus Christi

        if state == "Baden-Württemberg":
            result += [
                (datetime.date(y, 1, 6),  "Heilige Drei Könige"),
                (cc,                      "Fronleichnam"),
                (datetime.date(y, 11, 1), "Allerheiligen"),
            ]

        elif state == "Bayern":
            result += [
                (datetime.date(y, 1, 6),  "Heilige Drei Könige"),
                (cc,                      "Fronleichnam"),
                (datetime.date(y, 8, 15), "Mariä Himmelfahrt"),
                (datetime.date(y, 11, 1), "Allerheiligen"),
            ]

        elif state == "Berlin":
            result += [
                (datetime.date(y, 3, 8), "Internationaler Frauentag"),
            ]

        elif state == "Brandenburg":
            result += [
                (datetime.date(y, 10, 31), "Reformationstag"),
            ]

        elif state == "Bremen":
            result += [
                (datetime.date(y, 10, 31), "Reformationstag"),
            ]

        elif state == "Hamburg":
            result += [
                (datetime.date(y, 10, 31), "Reformationstag"),
            ]

        elif state == "Hessen":
            result += [
                (cc, "Fronleichnam"),
            ]

        elif state == "Mecklenburg-Vorpommern":
            result += [
                (datetime.date(y, 10, 31), "Reformationstag"),
            ]

        elif state == "Niedersachsen":
            result += [
                (datetime.date(y, 10, 31), "Reformationstag"),
            ]

        elif state == "Rheinland-Pfalz":
            result += [
                (cc,                       "Fronleichnam"),
                (datetime.date(y, 11, 1),  "Allerheiligen"),
            ]

        elif state == "Saarland":
            result += [
                (cc,                       "Fronleichnam"),
                (datetime.date(y, 8, 15),  "Mariä Himmelfahrt"),
                (datetime.date(y, 11, 1),  "Allerheiligen"),
            ]

        elif state == "Sachsen":
            result += [
                (datetime.date(y, 10, 31), "Reformationstag"),
                (_buss_und_bettag(y),      "Buß- und Bettag"),
            ]

        elif state == "Sachsen-Anhalt":
            result += [
                (datetime.date(y, 1, 6),   "Heilige Drei Könige"),
                (datetime.date(y, 10, 31), "Reformationstag"),
            ]

        elif state == "Schleswig-Holstein":
            result += [
                (datetime.date(y, 10, 31), "Reformationstag"),
            ]

        elif state == "Thüringen":
            if y >= 2019:
                result.append((datetime.date(y, 9, 20), "Weltkindertag"))
            result += [
                (datetime.date(y, 10, 31), "Reformationstag"),
            ]

    return result


# --------------------------------------------------------------------------- #
# France                                                                        #
# --------------------------------------------------------------------------- #

def france_holidays(years) -> HolidayList:
    result: HolidayList = []
    for y in years:
        e = _easter(y)
        result += [
            (datetime.date(y, 1, 1),           "Jour de l'An"),
            (e + datetime.timedelta(days=1),   "Lundi de Pâques"),
            (datetime.date(y, 5, 1),           "Fête du Travail"),
            (datetime.date(y, 5, 8),           "Victoire 1945"),
            (e + datetime.timedelta(days=39),  "Ascension"),
            (e + datetime.timedelta(days=50),  "Lundi de Pentecôte"),
            (datetime.date(y, 7, 14),          "Fête Nationale"),
            (datetime.date(y, 8, 15),          "Assomption"),
            (datetime.date(y, 11, 1),          "Toussaint"),
            (datetime.date(y, 11, 11),         "Armistice"),
            (datetime.date(y, 12, 25),         "Noël"),
        ]
    return result


# --------------------------------------------------------------------------- #
# India (fixed national + major movable holidays for 2018-2040)                #
# --------------------------------------------------------------------------- #

_INDIA_HOLI = {
    2018: (3, 2),  2019: (3, 21), 2020: (3, 10), 2021: (3, 29),
    2022: (3, 18), 2023: (3, 8),  2024: (3, 25), 2025: (3, 14),
    2026: (3, 3),  2027: (3, 22), 2028: (3, 11), 2029: (3, 1),
    2030: (3, 20), 2031: (3, 9),  2032: (2, 27), 2033: (3, 17),
    2034: (3, 6),  2035: (3, 25), 2036: (3, 13), 2037: (3, 3),
    2038: (3, 22), 2039: (3, 11), 2040: (2, 29),
}

_INDIA_DIWALI = {
    2018: (11, 7),  2019: (10, 27), 2020: (11, 14), 2021: (11, 4),
    2022: (10, 24), 2023: (11, 12), 2024: (11, 1),  2025: (10, 20),
    2026: (11, 8),  2027: (10, 29), 2028: (10, 17), 2029: (11, 5),
    2030: (10, 26), 2031: (11, 14), 2032: (11, 2),  2033: (10, 22),
    2034: (11, 10), 2035: (10, 31), 2036: (11, 18), 2037: (11, 8),
    2038: (10, 28), 2039: (11, 16), 2040: (11, 5),
}

_INDIA_EID_FITR = {
    2018: (6, 15),  2019: (6, 5),   2020: (5, 24), 2021: (5, 13),
    2022: (5, 2),   2023: (4, 21),  2024: (4, 10), 2025: (3, 30),
    2026: (3, 20),  2027: (3, 9),   2028: (2, 26), 2029: (2, 14),
    2030: (2, 4),   2031: (1, 24),  2032: (1, 13), 2033: (1, 2),
    2034: (12, 22), 2035: (12, 11), 2036: (12, 1), 2037: (11, 20),
    2038: (11, 10), 2039: (10, 31), 2040: (10, 19),
}


def india_holidays(years) -> HolidayList:
    """Major Indian national and public holidays.

    Fixed dates are generated for every year in *years*.
    Movable dates (Holi, Diwali, Eid al-Fitr) are pre-computed for 2018-2040;
    years outside that range will only include the fixed holidays.
    Dates are approximate for movable holidays and may vary by 1-2 days
    depending on regional moon sighting.
    """
    result: HolidayList = []
    for y in years:
        # Fixed national holidays
        result += [
            (datetime.date(y, 1, 26), "Republic Day"),
            (datetime.date(y, 8, 15), "Independence Day"),
            (datetime.date(y, 10, 2), "Gandhi Jayanti"),
        ]
        # Movable holidays
        if y in _INDIA_HOLI:
            m, d = _INDIA_HOLI[y]
            result.append((datetime.date(y, m, d), "Holi"))
        if y in _INDIA_DIWALI:
            m, d = _INDIA_DIWALI[y]
            result.append((datetime.date(y, m, d), "Diwali"))
        if y in _INDIA_EID_FITR:
            m, d = _INDIA_EID_FITR[y]
            if 1 <= m <= 12:
                result.append((datetime.date(y, m, d), "Eid al-Fitr (approx.)"))
    return result


# --------------------------------------------------------------------------- #
# Romania                                                                       #
# --------------------------------------------------------------------------- #

def romania_holidays(years) -> HolidayList:
    result: HolidayList = []
    for y in years:
        oe = _orthodox_easter(y)
        result += [
            (datetime.date(y, 1, 1),             "Anul Nou (1 Ianuarie)"),
            (datetime.date(y, 1, 2),             "Anul Nou (2 Ianuarie)"),
            (datetime.date(y, 1, 24),            "Unirea Principatelor Române"),
            (oe - datetime.timedelta(days=2),    "Vinerea Mare"),
            (oe + datetime.timedelta(days=1),    "A doua zi de Paști"),
            (datetime.date(y, 5, 1),             "Ziua Muncii"),
            (datetime.date(y, 6, 1),             "Ziua Copilului"),
            (oe + datetime.timedelta(days=50),   "Rusalii"),
            (oe + datetime.timedelta(days=51),   "A doua zi de Rusalii"),
            (datetime.date(y, 8, 15),            "Adormirea Maicii Domnului"),
            (datetime.date(y, 11, 30),           "Sfântul Andrei"),
            (datetime.date(y, 12, 1),            "Ziua Națională"),
            (datetime.date(y, 12, 25),           "Crăciun (1)"),
            (datetime.date(y, 12, 26),           "Crăciun (2)"),
        ]
    return result


# --------------------------------------------------------------------------- #
# China (fixed + movable holidays for 2018-2040)                               #
# --------------------------------------------------------------------------- #

_CHINA_SPRING_FESTIVAL = {
    2018: (2, 16), 2019: (2, 5),  2020: (1, 25), 2021: (2, 12),
    2022: (2, 1),  2023: (1, 22), 2024: (2, 10), 2025: (1, 29),
    2026: (2, 17), 2027: (2, 6),  2028: (1, 26), 2029: (2, 13),
    2030: (2, 3),  2031: (1, 23), 2032: (2, 11), 2033: (1, 31),
    2034: (2, 19), 2035: (2, 8),  2036: (1, 28), 2037: (2, 15),
    2038: (2, 4),  2039: (1, 24), 2040: (2, 12),
}

_CHINA_QINGMING = {
    2018: (4, 5),  2019: (4, 5),  2020: (4, 4),  2021: (4, 4),
    2022: (4, 5),  2023: (4, 5),  2024: (4, 4),  2025: (4, 4),
    2026: (4, 5),  2027: (4, 5),  2028: (4, 4),  2029: (4, 4),
    2030: (4, 5),  2031: (4, 5),  2032: (4, 4),  2033: (4, 4),
    2034: (4, 5),  2035: (4, 5),  2036: (4, 4),  2037: (4, 4),
    2038: (4, 5),  2039: (4, 5),  2040: (4, 4),
}

_CHINA_DRAGON_BOAT = {
    2018: (6, 18), 2019: (6, 7),  2020: (6, 25), 2021: (6, 14),
    2022: (6, 3),  2023: (6, 22), 2024: (6, 10), 2025: (5, 31),
    2026: (6, 19), 2027: (6, 9),  2028: (5, 28), 2029: (6, 16),
    2030: (6, 5),  2031: (6, 24), 2032: (6, 12), 2033: (6, 2),
    2034: (6, 20), 2035: (6, 10), 2036: (5, 30), 2037: (6, 18),
    2038: (6, 7),  2039: (5, 28), 2040: (6, 15),
}

_CHINA_MID_AUTUMN = {
    2018: (9, 24), 2019: (9, 13), 2020: (10, 1), 2021: (9, 21),
    2022: (9, 10), 2023: (9, 29), 2024: (9, 17), 2025: (10, 6),
    2026: (9, 25), 2027: (9, 15), 2028: (10, 3), 2029: (9, 22),
    2030: (9, 12), 2031: (10, 1), 2032: (9, 19), 2033: (9, 8),
    2034: (9, 27), 2035: (9, 17), 2036: (10, 4), 2037: (9, 24),
    2038: (9, 14), 2039: (10, 3), 2040: (9, 22),
}


def china_holidays(years) -> HolidayList:
    """Chinese public holidays.

    Fixed dates are included for every year.  Spring Festival (3 days),
    Qingming, Dragon Boat Festival and Mid-Autumn Festival are pre-computed
    for 2018-2040.
    """
    result: HolidayList = []
    for y in years:
        result += [
            (datetime.date(y, 1, 1),  "New Year's Day"),
            (datetime.date(y, 5, 1),  "Labour Day"),
            (datetime.date(y, 10, 1), "National Day (Day 1)"),
            (datetime.date(y, 10, 2), "National Day (Day 2)"),
            (datetime.date(y, 10, 3), "National Day (Day 3)"),
        ]
        if y in _CHINA_SPRING_FESTIVAL:
            m, d = _CHINA_SPRING_FESTIVAL[y]
            sf = datetime.date(y, m, d)
            result += [
                (sf,                                  "Spring Festival (Day 1)"),
                (sf + datetime.timedelta(days=1),     "Spring Festival (Day 2)"),
                (sf + datetime.timedelta(days=2),     "Spring Festival (Day 3)"),
            ]
        if y in _CHINA_QINGMING:
            m, d = _CHINA_QINGMING[y]
            result.append((datetime.date(y, m, d), "Qingming (Tomb-Sweeping Day)"))
        if y in _CHINA_DRAGON_BOAT:
            m, d = _CHINA_DRAGON_BOAT[y]
            result.append((datetime.date(y, m, d), "Dragon Boat Festival"))
        if y in _CHINA_MID_AUTUMN:
            m, d = _CHINA_MID_AUTUMN[y]
            result.append((datetime.date(y, m, d), "Mid-Autumn Festival"))
    return result


# --------------------------------------------------------------------------- #
# Japan                                                                         #
# --------------------------------------------------------------------------- #

_JAPAN_VERNAL = {
    2018: 21, 2019: 21, 2020: 20, 2021: 20, 2022: 21, 2023: 21,
    2024: 20, 2025: 20, 2026: 20, 2027: 21, 2028: 20, 2029: 20,
    2030: 20, 2031: 21, 2032: 20, 2033: 20, 2034: 20, 2035: 21,
    2036: 20, 2037: 20, 2038: 20, 2039: 21, 2040: 20,
}

_JAPAN_AUTUMNAL = {
    2018: 23, 2019: 23, 2020: 22, 2021: 23, 2022: 23, 2023: 23,
    2024: 22, 2025: 23, 2026: 23, 2027: 23, 2028: 22, 2029: 23,
    2030: 23, 2031: 23, 2032: 22, 2033: 23, 2034: 23, 2035: 23,
    2036: 22, 2037: 23, 2038: 23, 2039: 23, 2040: 22,
}


def japan_holidays(years) -> HolidayList:
    """Japanese national holidays.

    Equinox days are pre-computed for 2018-2040; years outside that range
    will not include those two holidays.
    """
    result: HolidayList = []
    for y in years:
        result += [
            (datetime.date(y, 1, 1),            "New Year's Day"),
            (_nth_weekday(y, 1, 2, 0),          "Coming of Age Day"),   # 2nd Mon Jan
            (datetime.date(y, 2, 11),           "National Foundation Day"),
            (datetime.date(y, 2, 23),           "Emperor's Birthday"),
        ]
        if y in _JAPAN_VERNAL:
            result.append((datetime.date(y, 3, _JAPAN_VERNAL[y]), "Vernal Equinox Day"))
        result += [
            (datetime.date(y, 4, 29), "Showa Day"),
            (datetime.date(y, 5, 3),  "Constitution Memorial Day"),
            (datetime.date(y, 5, 4),  "Greenery Day"),
            (datetime.date(y, 5, 5),  "Children's Day"),
            (_nth_weekday(y, 7, 3, 0),  "Marine Day"),              # 3rd Mon Jul
            (datetime.date(y, 8, 11),   "Mountain Day"),
            (_nth_weekday(y, 9, 3, 0),  "Respect for the Aged Day"),# 3rd Mon Sep
        ]
        if y in _JAPAN_AUTUMNAL:
            result.append((datetime.date(y, 9, _JAPAN_AUTUMNAL[y]), "Autumnal Equinox Day"))
        result += [
            (_nth_weekday(y, 10, 2, 0), "Sports Day"),              # 2nd Mon Oct
            (datetime.date(y, 11, 3),   "Culture Day"),
            (datetime.date(y, 11, 23),  "Labour Thanksgiving Day"),
        ]
    return result


# --------------------------------------------------------------------------- #
# MPXJ helper                                                                   #
# --------------------------------------------------------------------------- #

def add_holidays_to_calendar(cal, holidays: HolidayList) -> None:
    """Add *holidays* as non-working calendar exceptions to an MPXJ ProjectCalendar.

    *cal* is a ``org.mpxj.ProjectCalendar`` Java object (JPype).
    Entries whose date already exists as an exception are silently skipped.
    """
    from java.time import LocalDate  # type: ignore

    # Collect already-present exception dates to avoid duplicates
    existing: set = set()
    try:
        for ex in cal.getCalendarExceptions():
            try:
                existing.add(str(ex.getFromDate())[:10])
            except Exception:
                pass
    except Exception:
        pass

    for d, name in holidays:
        key = str(d)            # "YYYY-MM-DD"
        if key in existing:
            continue
        try:
            ld = LocalDate.of(d.year, d.month, d.day)
            ex = cal.addCalendarException(ld, ld)
            ex.setName(name)
            existing.add(key)
        except Exception as exc:
            print(f"[WARN] holidays: could not add '{name}' ({d}): {exc}")
