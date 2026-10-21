"""Show c2c trains on National Rail's staff boards (LDBSVWS) at Westcliff and
Barking for the next 2 hours, with cancellations and delays."""
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
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read()[:300]!r}")
        return None


now = datetime.now(UK)
print("now", now)
# Look back at this morning too: the staff boards accept a past time.
times = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in (6, 8)] + [now]
for when in times:
  print(f"\n########## board from {when:%H:%M}")
  for frm, to in (("WCF", "BKG"), ("BKG", "WCF"), ("WCF", "FST"), ("FST", "WCF")):
    data = get(f"/GetArrDepBoardWithDetails/{frm}/{when:%Y%m%dT%H%M%S}", numRows=40, filterCRS=to,
               filterType="to", timeWindow=120)
    services = (data or {}).get("trainServices") or []
    cancelled = [s for s in services if s.get("isCancelled")]
    print(f"\n===== {frm} -> {to}: {len(services)} trains, {len(cancelled)} cancelled; "
          f"nrccMessages: {[ (m.get('Value') or m.get('value') or str(m))[:200] for m in (data or {}).get('nrccMessages') or []]}")
    for s in services:
        print(f"  {s.get('std','')[11:16]} etd={str(s.get('etd'))[11:16]} atd={str(s.get('atd'))[11:16]} "
              f"cancelled={s.get('isCancelled')} type={s.get('departureType')} "
              f"cancel={s.get('cancelReason')} delay={s.get('delayReason')} "
              f"-> {[d.get('crs') for d in s.get('destination') or []]}")
