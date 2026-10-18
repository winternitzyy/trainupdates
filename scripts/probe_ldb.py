"""Read National Rail's staff departure boards (LDBSVWS) for c2c between
Westcliff and Barking, and print what they give back."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = ("https://api1.raildata.org.uk/1010-live-arrival-and-departure-boards---staff-version1_0/"
        "LDBSVWS/api/20220120")
UK = ZoneInfo("Europe/London")
KEY = os.environ["NR_LDB_KEY"]


def get(path, **params):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"x-apikey": KEY, "User-Agent": "trainupdates-probe",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            print(f"HTTP {r.status} {r.headers.get('Content-Type')}")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read()[:500]!r}")
        return None


now = datetime.now(UK).strftime("%Y%m%dT%H%M%S")
for frm, to in (("WCF", "BKG"), ("BKG", "WCF")):
    for endpoint in ("GetDepBoardWithDetails", "GetArrDepBoardWithDetails"):
        print(f"\n===== {endpoint} {frm} -> {to}")
        data = get(f"/{endpoint}/{frm}/{now}", numRows=6, filterCRS=to, filterType="to", timeWindow=120)
        if not data:
            continue
        print("board fields:", sorted(data))
        services = data.get("trainServices") or []
        print(f"{len(services)} services")
        if services:
            print("service fields:", sorted(services[0]))
        for s in services[:4]:
            print({k: s.get(k) for k in ("std", "etd", "atd", "platform", "isCancelled", "cancelReason",
                                         "delayReason", "operatorCode", "departureType", "platformIsHidden")},
                  "->", [d.get("crs") or d.get("locationName") for d in s.get("destination") or []])
        if services:
            print("first service raw:", json.dumps(services[0])[:1500])
        break  # one endpoint that works is enough
