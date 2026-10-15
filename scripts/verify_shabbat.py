"""Compare shabbat.py's times with Hebcal's for Westcliff-on-Sea."""
import json
import sys
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, ".")
from shabbat import LATITUDE, LONGITUDE, shabbat_times

worst = 0
for year in (2026, 2027):
    url = ("https://www.hebcal.com/hebcal?v=1&cfg=json&maj=off&min=off&mod=off&nx=off&ss=off&mf=off"
           f"&c=on&M=on&b=18&geo=pos&latitude={LATITUDE}&longitude={LONGITUDE}"
           f"&tzid=Europe/London&year={year}")
    req = urllib.request.Request(url, headers={"User-Agent": "trainupdates-verify"})
    items = json.load(urllib.request.urlopen(req, timeout=30))["items"]
    candles = {datetime.fromisoformat(i["date"]).date(): datetime.fromisoformat(i["date"])
               for i in items if i["category"] == "candles"}
    havdalah = {datetime.fromisoformat(i["date"]).date(): datetime.fromisoformat(i["date"])
                for i in items if i["category"] == "havdalah"}
    for day, hc_start in sorted(candles.items()):
        if day.weekday() != 4:
            continue
        sat = day + timedelta(days=1)
        if sat not in havdalah:
            continue
        start, end = shabbat_times(day)
        ds = (start - hc_start).total_seconds() / 60
        de = (end - havdalah[sat]).total_seconds() / 60
        worst = max(worst, abs(ds), abs(de))
        print(f"{day}  hebcal {hc_start:%H:%M}-{havdalah[sat]:%H:%M}  ours "
              f"{start.astimezone(hc_start.tzinfo):%H:%M}-{end.astimezone(hc_start.tzinfo):%H:%M}"
              f"  diff {ds:+.1f} / {de:+.1f} min")
print(f"Largest difference: {worst:.1f} minutes")
