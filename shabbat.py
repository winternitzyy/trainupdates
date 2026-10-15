"""Shabbat and Yom Tov start and end times for Westcliff-on-Sea.

A rest period is a run of consecutive Shabbat and Yom Tov days (diaspora, so
two-day festivals). It starts at candle lighting on the evening before, a set
number of minutes before sunset (18 by default), and ends a set number of
minutes after sunset on the last day (72 by default, Rabbeinu Tam).

The sun calculation is within 3 minutes of Hebcal (see scripts/verify_shabbat.py),
so in_rest_period adds a safety margin either side, 5 minutes by default.
"""

import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# Westcliff-on-Sea
LATITUDE = 51.5393
LONGITUDE = 0.6906
UK = ZoneInfo("Europe/London")


def _sun_below_horizon_utc(day, degrees, latitude=LATITUDE, longitude=LONGITUDE):
    """UTC time on `day` when the setting sun is `degrees` below the horizon."""
    jd = datetime.combine(day, time(12), timezone.utc).timestamp() / 86400 + 2440587.5
    n = round(jd - 2451545.0 + 0.0008)
    j_star = n - longitude / 360
    m = (357.5291 + 0.98560028 * j_star) % 360
    mr = math.radians(m)
    c = 1.9148 * math.sin(mr) + 0.02 * math.sin(2 * mr) + 0.0003 * math.sin(3 * mr)
    lam = math.radians((m + c + 180 + 102.9372) % 360)
    transit = 2451545.0 + j_star + 0.0053 * math.sin(mr) - 0.0069 * math.sin(2 * lam)
    decl = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))
    lat = math.radians(latitude)
    cos_w = ((math.sin(math.radians(-degrees)) - math.sin(lat) * math.sin(decl))
             / (math.cos(lat) * math.cos(decl)))
    w = math.degrees(math.acos(max(-1.0, min(1.0, cos_w))))
    event = transit + w / 360
    return datetime.fromtimestamp((event - 2440587.5) * 86400, timezone.utc)


def sunset(day):
    return _sun_below_horizon_utc(day, 0.833)


# Hebrew calendar (Dershowitz & Reingold, Calendrical Calculations).
# Python's date.toordinal() uses the same day numbering ("fixed dates").
HEBREW_EPOCH = -1373427


def _elapsed_days(year):
    months = (235 * year - 234) // 19
    parts = 12084 + 13753 * months
    days = 29 * months + parts // 25920
    return days + 1 if (3 * (days + 1)) % 7 < 3 else days


def _rosh_hashanah(year):
    """Gregorian date of 1 Tishri of Hebrew `year`."""
    ny0, ny1, ny2 = _elapsed_days(year - 1), _elapsed_days(year), _elapsed_days(year + 1)
    correction = 2 if ny2 - ny1 == 356 else 1 if ny1 - ny0 == 382 else 0
    return date.fromordinal(HEBREW_EPOCH + ny1 + correction)


def _yom_tov_names(hebrew_year):
    """{date: name} of the diaspora Yom Tov days in Hebrew `hebrew_year`."""
    rh = _rosh_hashanah(hebrew_year)
    pesach = _rosh_hashanah(hebrew_year + 1) - timedelta(days=163)
    days = {
        "Rosh Hashanah": [rh, rh + timedelta(1)],
        "Yom Kippur": [rh + timedelta(9)],
        "Sukkot": [rh + timedelta(14), rh + timedelta(15)],
        "Shemini Atzeret": [rh + timedelta(21)],
        "Simchat Torah": [rh + timedelta(22)],
        "Pesach": [pesach, pesach + timedelta(1), pesach + timedelta(6), pesach + timedelta(7)],
        "Shavuot": [pesach + timedelta(50), pesach + timedelta(51)],
    }
    return {d: name for name, ds in days.items() for d in ds}


_cache = {}


def yom_tov(day):
    """Name of the Yom Tov on `day`, or None."""
    year = day.year + 3760
    if year not in _cache:
        _cache[year] = {}
        for y in (year - 1, year, year + 1):
            _cache[year].update(_yom_tov_names(y))
    return _cache[year].get(day)


def is_rest_day(day):
    return day.weekday() == 5 or yom_tov(day) is not None


def rest_period(day, candle_minutes=18, end_minutes=72):
    """(start, end, label) of the rest period containing `day`, or None if it is not one."""
    if not is_rest_day(day):
        return None
    first = last = day
    while is_rest_day(first - timedelta(1)):
        first -= timedelta(1)
    while is_rest_day(last + timedelta(1)):
        last += timedelta(1)
    start = sunset(first - timedelta(1)) - timedelta(minutes=candle_minutes)
    end = sunset(last) + timedelta(minutes=end_minutes)
    days = [first + timedelta(i) for i in range((last - first).days + 1)]
    festivals = list(dict.fromkeys(yom_tov(d) for d in days if yom_tov(d)))
    has_shabbat = any(d.weekday() == 5 for d in days)
    names = (["Shabbat"] if has_shabbat else []) + festivals
    label = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return start, end, label


def in_rest_period(now, candle_minutes=18, end_minutes=72, margin_minutes=5):
    """Label ("Shabbat", "Pesach", "Shabbat and Sukkot", ...) if `now` is within a
    Shabbat or Yom Tov, widened by `margin_minutes` at both ends; otherwise None."""
    today = now.astimezone(UK).date()
    margin = timedelta(minutes=margin_minutes)
    for day in (today - timedelta(1), today, today + timedelta(1)):
        period = rest_period(day, candle_minutes, end_minutes)
        if period and period[0] - margin <= now < period[1] + margin:
            return period[2]
    return None


if __name__ == "__main__":
    import sys

    first = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    seen = set()
    for i in range(days):
        period = rest_period(first + timedelta(i))
        if period and period[:2] not in seen:
            seen.add(period[:2])
            start, end, label = period
            print(f"{label}: {start.astimezone(UK):%a %d %b %H:%M} to {end.astimezone(UK):%a %d %b %H:%M}")
