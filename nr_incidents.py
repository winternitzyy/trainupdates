"""National Rail Knowledgebase Incidents feed (via the Rail Data Marketplace).

The feed lists live disruptions and planned engineering works for every train
company. It is about 3 MB, so it is fetched at most every 5 minutes, as the
Rail Data Marketplace recommends.
"""

import gzip
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

URL = "https://api1.raildata.org.uk/1010-knowlegebase-incidents-xml-feed1_0/incidents.xml"
MAX_AGE_SECONDS = 300
USER_AGENT = "trainupdates/1.0 (+https://github.com/winternitzyy/trainupdates)"

_cache = {"at": 0.0, "incidents": None}


def _tag(el):
    return el.tag.split("}")[-1]


def _first(el, name):
    for e in el.iter():
        if _tag(e) == name:
            return (e.text or "").strip()
    return ""


def _time(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None
    except ValueError:
        return None


def parse(body):
    """List of incidents from the feed's XML (gzip-compressed or not)."""
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    root = ET.fromstring(body.lstrip(b"\xef\xbb\xbf \r\n\t"))
    incidents = []
    for el in root:
        description = re.sub(r"<[^>]+>", " ", _first(el, "Description"))
        incidents.append({
            "number": _first(el, "IncidentNumber"),
            "planned": _first(el, "Planned").lower() == "true",
            "cleared": _first(el, "ClearedIncident").lower() == "true",
            "start": _time(_first(el, "StartTime")),
            "end": _time(_first(el, "EndTime")),
            "summary": " ".join(_first(el, "Summary").split()),
            "description": " ".join(description.split()),
            "operators": {(e.text or "").strip() for e in el.iter() if _tag(e) == "OperatorRef"},
        })
    return incidents


def fetch(key=None, url=None):
    key = key or os.environ["NR_INCIDENTS_KEY"]
    req = urllib.request.Request(url or os.environ.get("NR_INCIDENTS_URL") or URL,
                                 headers={"x-apikey": key, "User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return parse(resp.read())


def get(max_age=MAX_AGE_SECONDS):
    """Incidents, re-fetched only if the cached copy is older than max_age seconds."""
    if _cache["incidents"] is None or time.monotonic() - _cache["at"] > max_age:
        _cache["incidents"] = fetch()
        _cache["at"] = time.monotonic()
    return _cache["incidents"]


def configured():
    return bool(os.environ.get("NR_INCIDENTS_KEY"))


def for_operator(incidents, code):
    return [i for i in incidents if code in i["operators"]]


def active_unplanned(incidents, now):
    """Unplanned incidents happening now, earliest first."""
    found = [i for i in incidents
             if not i["planned"] and not i["cleared"]
             and (i["start"] is None or i["start"] <= now)
             and (i["end"] is None or i["end"] > now)]
    return sorted(found, key=lambda i: i["start"] or now)


def planned_on(incidents, day, tz):
    """Planned works that cover `day` (a date), in start order."""
    found = []
    for i in incidents:
        if not i["planned"] or i["cleared"] or i["start"] is None:
            continue
        end = i["end"] or i["start"]
        if i["start"].astimezone(tz).date() <= day <= end.astimezone(tz).date():
            found.append(i)
    return sorted(found, key=lambda i: i["start"])
