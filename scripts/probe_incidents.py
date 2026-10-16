"""Fetch the National Rail Knowledgebase Incidents feed once and summarise it.

Used to check access and the feed's format. Needs NR_INCIDENTS_KEY.
"""
import os
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

URL = os.environ.get("NR_INCIDENTS_URL",
                     "https://api1.raildata.org.uk/1010-knowlegebase-incidents-xml-feed1_0/incidents.xml")
key = os.environ.get("NR_INCIDENTS_KEY")
if not key:
    sys.exit("NR_INCIDENTS_KEY is not set")

body = None
for header in ("x-apikey", "apikey"):
    req = urllib.request.Request(URL, headers={header: key, "User-Agent": "trainupdates-probe",
                                               "Accept": "application/xml"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read()
            print(f"OK with header {header}: HTTP {resp.status}, {len(body)} bytes")
            break
    except urllib.error.HTTPError as e:
        print(f"Header {header}: HTTP {e.code} {e.read()[:300]!r}")
if body is None:
    sys.exit(1)

root = ET.fromstring(body)
strip = lambda tag: tag.split("}")[-1]
print("Root:", strip(root.tag), "children:", len(root))
incidents = list(root)
if incidents:
    print("First incident fields:", sorted({strip(e.tag) for e in incidents[0].iter()}))


def text(el, name):
    for e in el.iter():
        if strip(e.tag) == name:
            return (e.text or "").strip()
    return ""


def operators(el):
    return {(e.text or "").strip() for e in el.iter() if strip(e.tag) in ("OperatorRef", "OperatorName")}


print()
c2c = [i for i in incidents if operators(i) & {"CC", "c2c"}]
print(f"{len(incidents)} incidents in total, {len(c2c)} affecting c2c")
for i in c2c:
    desc = re.sub(r"<[^>]+>", " ", text(i, "Description"))
    print("---")
    print("Planned:", text(i, "Planned"), "| Cleared:", text(i, "ClearedIncident"),
          "| Start:", text(i, "StartTime"), "| End:", text(i, "EndTime"),
          "| Updated:", text(i, "LastChangedDate") or text(i, "ChangeHistory"))
    print("Summary:", text(i, "Summary"))
    print("Description:", " ".join(desc.split())[:400])
