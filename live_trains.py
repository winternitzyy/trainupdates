"""How the next trains are actually running on our journey, from live
departure boards. Only checked once a line is reported as disrupted, and added
to that line's text, e.g.
"STO to BKG: 14:05 cancelled, 14:20 3 minutes delayed, 14:35 on time."

Boards come from National Rail's staff departure boards (needs NR_LDB_KEY).
For the Suffragette line, TfL's board (no key needed) is the fallback.
"""

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
TFL_BOARD_URL = "https://api.tfl.gov.uk/StopPoint/{stop}/ArrivalDepartures"
LDB_URL = ("https://api1.raildata.org.uk/1010-live-arrival-and-departure-boards---staff-version1_0/"
           "LDBSVWS/api/20220120/GetArrDepBoardWithDetails/{crs}/{time}")
USER_AGENT = "trainupdates/1.0 (+https://github.com/winternitzyy/trainupdates)"
TRAINS = 3
# Board alerts: any cancelled train, or this many trains LATE_MINUTES+ late, due in the next hour.
WINDOW_MINUTES = 60
LATE_MINUTES = 5
ALERT_LATE = 2

# line -> boards to check, from and to as station codes: both directions of each leg
# of our WCF–BKG–STO journey. National Rail's board is used first; a TfL stop is the
# fallback if it can't be read. TfL boards list both directions, so trains going our
# way are picked by text in their destination name.
BOARDS = {
    "suffragette": [
        {"from": "STO", "to": "BKG", "national_rail": True, "tfl_stop": "910GSTOTNHM", "toward": "Barking"},
        {"from": "BKG", "to": "STO", "national_rail": True, "tfl_stop": "910GBARKING", "toward": "Gospel Oak"},
    ],
    "c2c": [
        {"from": "WCF", "to": "BKG", "national_rail": True},
        {"from": "BKG", "to": "WCF", "national_rail": True},
    ],
}


def _time(value, tz=ZoneInfo("UTC")):
    """TfL times are UTC ("...Z"); National Rail times are UK local with no zone."""
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=tz)


def fetch_board(stop, line, app_key=None):
    params = {"lineIds": line}
    if app_key:
        params["app_key"] = app_key
    url = TFL_BOARD_URL.format(stop=stop) + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_national_rail(frm, to, now, key=None):
    key = key or os.environ["NR_LDB_KEY"]
    url = (LDB_URL.format(crs=frm, time=now.astimezone(UK).strftime("%Y%m%dT%H%M%S")) + "?"
           + urllib.parse.urlencode({"numRows": 10, "filterCRS": to, "filterType": "to", "timeWindow": 120}))
    req = urllib.request.Request(url, headers={"x-apikey": key, "User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def next_national_rail_trains(board, now, count=TRAINS):
    """Like next_trains, for a National Rail staff board already filtered to our direction."""
    trains = []
    for s in (board or {}).get("trainServices") or []:
        scheduled = _time(s.get("std"), UK)
        if scheduled is None or s.get("atd") or not s.get("isPassengerService", True):
            continue  # arriving here only, already left, or not a passenger train
        estimated = _time(s.get("etd"), UK)
        if (estimated or scheduled) < now - timedelta(minutes=1):
            continue
        if s.get("isCancelled") or s.get("filterLocationCancelled"):
            delay = None
        elif estimated is None:
            delay = -1 if (s.get("departureType") or "").lower() == "delayed" else 0
        else:
            delay = max(0, int((estimated - scheduled).total_seconds() // 60))
        trains.append((scheduled, delay))
    trains.sort(key=lambda t: t[0])
    return trains[:count]


def next_trains(board, toward, now, count=TRAINS):
    """The next `count` departures heading `toward`, as (scheduled, delay), where delay is
    minutes late, None if cancelled, or -1 if late by an amount TfL doesn't give."""
    trains = []
    for d in board:
        if toward.lower() not in (d.get("destinationName") or "").lower():
            continue
        scheduled = _time(d.get("scheduledTimeOfDeparture"))
        if scheduled is None:
            continue
        status = (d.get("departureStatus") or "").lower()
        estimated = _time(d.get("estimatedTimeOfDeparture"))
        cancelled = status == "cancelled"
        if (estimated or scheduled) < now - timedelta(minutes=1):
            continue  # already left
        if cancelled:
            delay = None
        elif estimated is None:
            delay = -1 if status == "delayed" else 0
        else:
            delay = max(0, int((estimated - scheduled).total_seconds() // 60))
        trains.append((scheduled, delay))
    trains.sort(key=lambda t: t[0])
    return trains[:count]


def describe_train(scheduled, delay):
    text = f"{scheduled.astimezone(UK):%H:%M}"
    if delay is None:
        return text + " cancelled"
    if delay == -1:
        return text + " delayed"
    if delay == 0:
        return text + " on time"
    return text + f" {delay} minute{'s' if delay != 1 else ''} delayed"


def describe_board(frm, to, trains):
    if not trains:
        return f"{frm} to {to}: no trains shown."
    return f"{frm} to {to}: " + ", ".join(describe_train(*t) for t in trains) + "."


def read_boards(line, now, app_key=None, count=TRAINS):
    """[(board, trains)] for each board of `line`; trains is None if the board can't be read."""
    result = []
    for b in BOARDS.get(line, []):
        trains = None
        if b.get("national_rail") and os.environ.get("NR_LDB_KEY"):
            try:
                trains = next_national_rail_trains(fetch_national_rail(b["from"], b["to"], now), now, count)
            except Exception as e:
                print(f"National Rail board {b['from']} failed: {e}", flush=True)
        if trains is None and b.get("tfl_stop"):
            try:
                trains = next_trains(fetch_board(b["tfl_stop"], line, app_key), b["toward"], now, count)
            except Exception as e:
                print(f"TfL board {b['from']} failed: {e}", flush=True)
        result.append((b, trains))
    return result


def check(line, now=None, app_key=None):
    """Text about the next trains on our journey for `line`, or "" if we have no
    boards for it or they can't be read. Never raises."""
    now = now or datetime.now(UK)
    return " ".join(describe_board(b["from"], b["to"], trains)
                    for b, trains in read_boards(line, now, app_key) if trains is not None)


def is_late(delay):
    return delay == -1 or (delay is not None and delay >= LATE_MINUTES)


def find_problems(boards, now):
    """Cancelled and late trains due in the next WINDOW_MINUTES on [(board, trains)].
    Alert if any train is cancelled or ALERT_LATE trains are late."""
    end = now + timedelta(minutes=WINDOW_MINUTES)
    parts, cancelled, late = [], [], 0
    for b, trains in boards:
        bad = [t for t in trains if t[0] <= end and (t[1] is None or is_late(t[1]))]
        cancelled += [f"{b['from']} {t[0].astimezone(UK):%H:%M}" for t in bad if t[1] is None]
        late += sum(1 for t in bad if t[1] is not None)
        if bad:
            parts.append(f"{b['from']} to {b['to']}: " + ", ".join(describe_train(*t) for t in bad) + ".")
    return {"alert": bool(cancelled) or late >= ALERT_LATE, "cancelled": cancelled, "late": late,
            "text": " ".join(parts)}


def board_problems(line, now=None, app_key=None):
    """find_problems for `line`'s boards, or None if none of them could be read. Never raises."""
    now = now or datetime.now(UK)
    try:
        boards = [(b, trains) for b, trains in read_boards(line, now, app_key, count=None) if trains is not None]
        return find_problems(boards, now) if boards else None
    except Exception as e:
        print(f"Board check for {line} failed: {e}", flush=True)
        return None
