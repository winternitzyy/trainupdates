"""Show TfL's live departures at Barking, South Tottenham and Westcliff, to see
which lines TfL has live boards for."""
import json
import urllib.parse
import urllib.request

UA = "trainupdates-probe"


def get(path, **params):
    url = "https://api.tfl.gov.uk" + path + ("?" + urllib.parse.urlencode(params) if params else "")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return json.load(r)


for name in ("Westcliff",):
    res = get(f"/StopPoint/Search/{urllib.parse.quote(name)}", modes="overground,national-rail")
    for m in res.get("matches", [])[:5]:
        print(f"{name}: {m.get('id')} | {m.get('name')} | modes={m.get('modes')}")

for sid, line in (("910GBARKING", "suffragette"), ("910GSTOTNHM", "suffragette")):
    path = f"/StopPoint/{sid}/ArrivalDepartures"
    try:
        data = get(path, lineIds=line)
    except Exception as e:
        print(f"\n== {sid} {line}: error {e}")
        continue
    print(f"\n== {sid} {line}: {len(data)} entries")
    statuses = sorted({d.get("departureStatus") for d in data})
    print("statuses seen:", statuses)
    for d in sorted(data, key=lambda d: d.get("scheduledTimeOfDeparture") or "~")[:8]:
        print({k: d.get(k) for k in ("destinationName", "scheduledTimeOfDeparture", "estimatedTimeOfDeparture",
                                     "departureStatus", "minutesAndSecondsToDeparture")})
