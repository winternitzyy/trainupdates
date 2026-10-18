"""Ask TfL's Journey Planner for full journeys between Westcliff and South
Tottenham, now and on a future date, and print what it gives back."""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

UA = "trainupdates-probe"
UK = ZoneInfo("Europe/London")
STATIONS = {"WCF": "910GWCLIFF", "STO": "910GSTOTNHM"}


def journeys(frm, to, when):
    params = {"date": f"{when:%Y%m%d}", "time": f"{when:%H%M}", "timeIs": "Departing",
              "mode": "national-rail,overground", "journeyPreference": "LeastTime"}
    url = (f"https://api.tfl.gov.uk/Journey/JourneyResults/{STATIONS[frm]}/to/{STATIONS[to]}?"
           + urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def hm(value):
    return value[11:16] if value else "?"


now = datetime.now(UK)
sunday = (now + timedelta(days=(6 - now.weekday()) % 7 or 7)).replace(hour=10, minute=0)
for frm, to, when in (("WCF", "STO", now), ("STO", "WCF", now), ("WCF", "STO", sunday)):
    status, data = journeys(frm, to, when)
    print(f"\n===== {frm} -> {to}, leaving after {when:%a %d %b %H:%M} (HTTP {status})")
    if status != 200:
        print(json.dumps(data)[:1500])
        continue
    for j in (data.get("journeys") or [])[:3]:
        print(f"-- {hm(j.get('startDateTime'))} -> {hm(j.get('arrivalDateTime'))}, {j.get('duration')} min")
        for leg in j.get("legs") or []:
            dep, arr = leg.get("departurePoint") or {}, leg.get("arrivalPoint") or {}
            route = ", ".join(o.get("name", "") for o in leg.get("routeOptions") or [])
            print(f"   {hm(leg.get('departureTime'))} {dep.get('commonName')} [{dep.get('platformName') or ''}] -> "
                  f"{hm(leg.get('arrivalTime'))} {arr.get('commonName')} [{arr.get('platformName') or ''}] | "
                  f"mode={(leg.get('mode') or {}).get('id')} route={route} disrupted={leg.get('isDisrupted')}")
            print(f"     {(leg.get('instruction') or {}).get('summary')}")
            for d in leg.get("disruptions") or []:
                print(f"     ! {d.get('category')}: {(d.get('description') or '')[:200]}")
            for w in leg.get("plannedWorks") or []:
                print(f"     ! works: {(w.get('description') or '')[:200]}")
    if data.get("journeys"):
        print("journey fields:", sorted(data["journeys"][0]))
        print("leg fields:", sorted(data["journeys"][0]["legs"][0]))
