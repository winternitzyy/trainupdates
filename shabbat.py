"""Shabbat start and end times, calculated from the sun's position.

Candle lighting is a set number of minutes before sunset on Friday (18 by
default). Shabbat ends at nightfall on Saturday, when the sun is a set number
of degrees below the horizon (8.5 by default). These match Hebcal's defaults.
The sun calculation is within 3 minutes of Hebcal (see scripts/verify_shabbat.py),
so in_shabbat adds a safety margin either side, 5 minutes by default.
"""

import math
from datetime import date, datetime, time, timedelta, timezone

# Westcliff-on-Sea
LATITUDE = 51.5393
LONGITUDE = 0.6906


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


def shabbat_times(friday, candle_minutes=18, end_degrees=8.5):
    """(candle lighting, Shabbat ends) as UTC datetimes for the Shabbat starting on `friday`."""
    start = sunset(friday) - timedelta(minutes=candle_minutes)
    end = _sun_below_horizon_utc(friday + timedelta(days=1), end_degrees)
    return start, end


def in_shabbat(now, candle_minutes=18, end_degrees=8.5, margin_minutes=5):
    """True if `now` (timezone-aware) is between candle lighting and the end of Shabbat,
    widened by `margin_minutes` at both ends."""
    local = now.astimezone(timezone.utc)
    weekday = local.weekday()
    if weekday not in (4, 5):
        return False
    friday = local.date() - timedelta(days=weekday - 4)
    start, end = shabbat_times(friday, candle_minutes, end_degrees)
    margin = timedelta(minutes=margin_minutes)
    return start - margin <= now < end + margin


if __name__ == "__main__":
    import sys
    from zoneinfo import ZoneInfo

    uk = ZoneInfo("Europe/London")
    first = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    friday = first + timedelta(days=(4 - first.weekday()) % 7)
    for i in range(int(sys.argv[2]) if len(sys.argv) > 2 else 4):
        f = friday + timedelta(weeks=i)
        start, end = shabbat_times(f)
        print(f"{f}  candles {start.astimezone(uk):%H:%M}  ends {end.astimezone(uk):%a %H:%M}")
