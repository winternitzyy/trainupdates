"""Compare shabbat.py with Hebcal for Westcliff-on-Sea: Yom Tov dates, candle
lighting and end times (72 minutes after sunset). Needs internet access."""
import json
import sys
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, ".")
from shabbat import LATITUDE, LONGITUDE, is_rest_day, rest_period, yom_tov

YEARS = range(2026, 2037)
worst = 0
problems = []
for year in YEARS:
    url = ("https://www.hebcal.com/hebcal?v=1&cfg=json&maj=on&min=off&mod=off&nx=off&ss=off&mf=off"
           f"&i=off&c=on&b=18&m=72&geo=pos&latitude={LATITUDE}&longitude={LONGITUDE}"
           f"&tzid=Europe/London&year={year}")
    req = urllib.request.Request(url, headers={"User-Agent": "trainupdates-verify"})
    items = json.load(urllib.request.urlopen(req, timeout=30))["items"]

    hebcal_yt = {datetime.fromisoformat(i["date"][:10]).date(): i["title"]
                 for i in items if i.get("yomtov")}
    ours_yt = set()
    d = datetime(year, 1, 1).date()
    while d.year == year:
        if yom_tov(d):
            ours_yt.add(d)
        d += timedelta(1)
    for day in sorted(set(hebcal_yt) ^ ours_yt):
        problems.append(f"Yom Tov mismatch {day}: hebcal={hebcal_yt.get(day)} ours={yom_tov(day)}")

    for i in items:
        when = datetime.fromisoformat(i["date"])
        day = when.date()
        if i["category"] == "candles" and not is_rest_day(day):
            ours = rest_period(day + timedelta(1))[0]
        elif i["category"] == "havdalah":
            ours = rest_period(day)[1]
        else:
            continue
        diff = (ours - when).total_seconds() / 60
        worst = max(worst, abs(diff))
        if abs(diff) > 3:
            problems.append(f"{i['category']} {day}: hebcal {when:%H:%M} ours {ours.astimezone(when.tzinfo):%H:%M}")
    print(f"{year}: {len(hebcal_yt)} Yom Tov days checked")

print(f"Largest time difference: {worst:.1f} minutes")
print("\n".join(problems) or "No problems found")
sys.exit(1 if problems else 0)
