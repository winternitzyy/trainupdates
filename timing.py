"""Record which source reported each c2c disruption first.

A disruption ("episode") starts when any source shows a problem and ends once
all of them have been clear for 10 minutes. For each one we note:
  - c2c website: the first minute our checker saw c2c's alert
  - TfL: the first minute TfL showed c2c as disrupted
  - National Rail: when National Rail created the incident (from the feed)
and append a row to disruption_log.csv.
"""

import csv
import os
from datetime import datetime, timedelta

SOURCES = (("c2c", "c2c website"), ("tfl", "TfL"), ("nr", "National Rail"))
CLEAR_MINUTES = 10
COLUMNS = ["date", "c2c_website", "tfl", "national_rail", "first", "lead_minutes",
           "c2c_title", "national_rail_summary", "ended"]


def update(episode, now, c2c_bad, c2c_title, tfl_bad, nr_active):
    """Fold one check into the open episode. Returns (episode, finished_row or None).
    nr_active is a list of active unplanned National Rail incidents (or [])."""
    bad = c2c_bad or tfl_bad or bool(nr_active)
    if episode is None:
        if not bad:
            return None, None
        episode = {"c2c": None, "tfl": None, "nr": None, "c2c_title": "", "nr_summary": ""}
    stamp = now.isoformat()
    if c2c_bad and not episode["c2c"]:
        episode["c2c"], episode["c2c_title"] = stamp, c2c_title or ""
    if tfl_bad and not episode["tfl"]:
        episode["tfl"] = stamp
    for i in nr_active or []:
        created = i.get("created") or i.get("start")
        if created and (not episode["nr"] or created.isoformat() < episode["nr"]):
            episode["nr"], episode["nr_summary"] = created.isoformat(), i.get("summary", "")
    if bad:
        episode["clear_since"] = None
        return episode, None
    episode["clear_since"] = episode.get("clear_since") or stamp
    clear_since = datetime.fromisoformat(episode["clear_since"])
    if now - clear_since < timedelta(minutes=CLEAR_MINUTES):
        return episode, None
    return None, to_row(episode, clear_since)


def to_row(episode, ended):
    times = {key: datetime.fromisoformat(episode[key]).astimezone(ended.tzinfo)
             for key, _ in SOURCES if episode.get(key)}
    order = sorted(times, key=times.get)
    names = dict(SOURCES)
    lead = ""
    later = [k for k in order if times[k] != times[order[0]]] if order else []
    if later:
        lead = str(round((times[later[0]] - times[order[0]]).total_seconds() / 60))
    elif len(order) > 1:
        lead = "0"
    first_time = times[order[0]] if order else ended
    return {
        "date": f"{first_time:%Y-%m-%d}",
        "c2c_website": f"{times['c2c']:%H:%M}" if "c2c" in times else "",
        "tfl": f"{times['tfl']:%H:%M}" if "tfl" in times else "",
        "national_rail": f"{times['nr']:%H:%M}" if "nr" in times else "",
        "first": " & ".join(names[k] for k in order if times[k] == times[order[0]]) if order else "",
        "lead_minutes": lead,
        "c2c_title": episode.get("c2c_title", ""),
        "national_rail_summary": episode.get("nr_summary", ""),
        "ended": f"{ended:%H:%M}",
    }


def append(row, path="disruption_log.csv"):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow(row)
