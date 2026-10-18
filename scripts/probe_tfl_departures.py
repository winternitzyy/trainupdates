"""Find TfL's stop codes for Barking and South Tottenham and show the next
Suffragette line departures between them."""
import json
import urllib.parse
import urllib.request

UA = "trainupdates-probe"


def get(path, **params):
    url = "https://api.tfl.gov.uk" + path + ("?" + urllib.parse.urlencode(params) if params else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return json.load(r)


stops = {}
for name in ("Barking", "South Tottenham"):
    res = get(f"/StopPoint/Search/{urllib.parse.quote(name)}", modes="overground,national-rail")
    for m in res.get("matches", [])[:5]:
        print(f"{name}: {m.get('id')} | {m.get('name')} | modes={m.get('modes')}")
    best = next((m for m in res.get("matches", []) if m.get("id", "").startswith("910G")), None) or \
        (res.get("matches") or [{}])[0]
    stops[name] = best.get("id")
print("chosen:", stops)

for frm, to in (("Barking", "South Tottenham"), ("South Tottenham", "Barking")):
    sid = stops[frm]
    for path in (f"/StopPoint/{sid}/ArrivalDepartures", ):
        try:
            data = get(path, lineIds="suffragette")
        except Exception as e:
            print(path, "error:", e)
            continue
        print(f"\n== {frm} -> {to}: {len(data)} entries from {path}")
        if data:
            print("fields:", sorted(data[0]))
        for d in sorted(data, key=lambda d: d.get("scheduledTimeOfDeparture") or "")[:6]:
            print({k: d.get(k) for k in ("destinationName", "scheduledTimeOfDeparture", "estimatedTimeOfDeparture",
                                         "departureStatus", "minutesAndSecondsToDeparture", "platformName",
                                         "cause")})
