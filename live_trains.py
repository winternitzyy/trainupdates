"""How the next trains are actually running on our journey, from live
departure boards. Only checked once a line is reported as disrupted, and added
to that line's text, e.g.
"BKG→STO: 14:05 cancelled, 14:20 3 minutes delayed, 14:35 on time."
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
TFL_BOARD_URL = "https://api.tfl.gov.uk/StopPoint/{stop}/ArrivalDepartures"
USER_AGENT = "trainupdates/1.0 (+https://github.com/winternitzyy/trainupdates)"
TRAINS = 3

# line -> boards to check: (from, to as station codes, TfL stop code, line id on that board,
# text that is in the destination name of trains going our way)
BOARDS = {
    "suffragette": [
        ("BKG", "STO", "910GBARKING", "suffragette", "Gospel Oak"),
        ("STO", "BKG", "910GSTOTNHM", "suffragette", "Barking"),
    ],
}


def _time(value):
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=ZoneInfo("UTC"))


def fetch_board(stop, line, app_key=None):
    params = {"lineIds": line}
    if app_key:
        params["app_key"] = app_key
    url = TFL_BOARD_URL.format(stop=stop) + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


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
        return f"{frm}→{to}: no trains shown."
    return f"{frm}→{to}: " + ", ".join(describe_train(*t) for t in trains) + "."


def check(line, now=None, app_key=None):
    """Text about the next trains on our journey for `line`, or "" if we have no
    boards for it or they can't be read. Never raises."""
    now = now or datetime.now(UK)
    parts = []
    for frm, to, stop, board_line, toward in BOARDS.get(line, []):
        try:
            board = fetch_board(stop, board_line, app_key)
        except Exception as e:
            print(f"Live board {frm} failed: {e}", flush=True)
            continue
        parts.append(describe_board(frm, to, next_trains(board, toward, now)))
    return " ".join(parts)
