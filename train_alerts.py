"""Send an SMS when c2c or the Suffragette line has problems.

Checks the TfL Unified API for line status, then texts you through PureSMS
when a line's status changes, for example from Good Service to Severe Delays
and back again. It saves the last status it saw so it does not text you
about the same problem twice.

Environment variables:
  PURESMS_API_KEY, PURESMS_SENDER, ALERT_TO_NUMBER
      Required for sending SMS. PURESMS_SENDER is a sender set up in your
      PureSMS dashboard. ALERT_TO_NUMBER is in +44 format; separate several
      recipients with commas.
  TFL_APP_KEY      Optional TfL API key (higher rate limits).
  TRAIN_LINES      Optional, defaults to "c2c,suffragette".
  STATE_FILE       Optional, defaults to "state.json".
  DRY_RUN          If set to "1", print messages instead of sending them.
  TEST_SMS         If set to "1", only send a test SMS with the current status.
  WEEKLY_PREVIEW   If set to "1", only send the coming weekend's preview now.
  TEST_AFTER_SHABBAT  If set to "1", only send a test of the after-Shabbat text,
                   using an example disruption if every line is running normally.
  RUN_MINUTES      Keep checking for this many minutes (default 0 = check once).
  CHECK_SECONDS    Seconds between checks when looping (default 60).
  QUIET_HOURS      UK-time window with no checks, e.g. "00:00-05:00" (default).
                   Set to "" to check around the clock.
  SHABBAT          No texts over Shabbat and Yom Tov in Westcliff-on-Sea, from
                   candle lighting until the end; then one text if a line is
                   still disrupted. On by default; set to "0" to turn off.
  SHABBAT_CANDLE_MINUTES  Minutes before sunset for candle lighting (default 18).
  SHABBAT_END_MINUTES     Minutes after sunset when Shabbat/Yom Tov ends (default 72).
  SHABBAT_MARGIN_MINUTES  Extra minutes added before and after (default 5).
"""

import json
import re
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import shabbat

TFL_URL = "https://api.tfl.gov.uk/Line/{lines}/Status"
TFL_RANGE_URL = "https://api.tfl.gov.uk/Line/{lines}/Status/{start}/to/{end}"
UK = ZoneInfo("Europe/London")
PURESMS_URL = "https://connect-api.divergent.cloud/sms/send"
GOOD_SERVICE = 10
SMS_PREFIX = "Train Alerts: "
USER_AGENT = "trainupdates/1.0 (+https://github.com/winternitzyy/trainupdates)"


def fetch_statuses(lines, app_key=None, day=None):
    """Current status, or the planned status for a whole day if given."""
    if day:
        url = TFL_RANGE_URL.format(lines=",".join(lines), start=f"{day:%Y-%m-%d}T00:00",
                                   end=f"{day:%Y-%m-%d}T23:59")
    else:
        url = TFL_URL.format(lines=",".join(lines))
    if app_key:
        url += "?" + urllib.parse.urlencode({"app_key": app_key})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with open_url(req) as resp:
        return parse_statuses(json.load(resp))


def open_url(req):
    """urlopen that prints the response body on HTTP errors, to make failures readable."""
    try:
        return urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        print(f"HTTP {e.code} from {req.full_url.split('?')[0]}: {body}", file=sys.stderr)
        raise


def parse_statuses(data):
    """Map line id -> {"name", "ok", "summary", "reasons"} from a TfL response."""
    result = {}
    for line in data:
        statuses = line.get("lineStatuses") or []
        ok = all(s.get("statusSeverity") == GOOD_SERVICE for s in statuses)
        descriptions = sorted({s.get("statusSeverityDescription", "Unknown") for s in statuses
                               if ok or s.get("statusSeverity") != GOOD_SERVICE})
        reasons = []
        for s in statuses:
            reason = strip_line_name((s.get("reason") or "").strip(), line)
            if reason and reason not in reasons:
                reasons.append(reason)
        result[line["id"]] = {
            "name": line.get("name", line["id"]),
            "ok": ok,
            "summary": ", ".join(descriptions) or "Unknown",
            "reasons": reasons,
            "since": None if ok else disruption_start(statuses),
        }
    return result


def _parse_tfl_time(value):
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=ZoneInfo("UTC"))


def disruption_start(statuses):
    """Earliest time TfL says a non-Good-Service status began, as ISO text, or None."""
    starts = []
    for s in statuses:
        if s.get("statusSeverity") == GOOD_SERVICE:
            continue
        times = [_parse_tfl_time(p.get("fromDate")) for p in s.get("validityPeriods") or []]
        times.append(_parse_tfl_time((s.get("disruption") or {}).get("created")))
        times.append(_parse_tfl_time(s.get("created")))
        starts += [t for t in times if t and t.year > 2000]
    return min(starts).isoformat() if starts else None


def format_still_disrupted(status, limit=400):
    """"c2c: Severe Delays since Sat 14:32. Signal failure at Upminster. Still disrupted." """
    text = f"{status['name']}: {status['summary']}"
    if status.get("since"):
        since = datetime.fromisoformat(status["since"]).astimezone(UK)
        text += f" since {since:%a %H:%M}"
    text += "."
    if status["reasons"]:
        text += " " + " ".join(status["reasons"])
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text + " Still disrupted."


def strip_line_name(reason, line):
    """Drop TfL's leading "SUFFRAGETTE LINE:" or "C2C:" since the text already names the line."""
    for name in {line.get("name", ""), line["id"]}:
        if name:
            reason = re.sub(rf"^{re.escape(name)}(\s+line)?\s*:\s*", "", reason, flags=re.I)
    return reason


def build_messages(previous, current):
    """Return SMS texts for lines whose status changed since the last run."""
    messages = []
    for line_id, now in current.items():
        before = previous.get(line_id)
        if before is None:
            # On the first run, only report a line that already has problems.
            if not now["ok"]:
                messages.append(format_problem(now))
            continue
        if now["ok"] and not before["ok"]:
            messages.append(f"{now['name']}: back to Good Service.")
        elif not now["ok"] and (before["ok"] or now["summary"] != before["summary"]
                                or now["reasons"] != before["reasons"]):
            messages.append(format_problem(now))
    return messages


def format_problem(status, limit=600):
    text = f"{status['name']}: {status['summary']}."
    if status["reasons"]:
        text += " " + " ".join(status["reasons"])
    return text if len(text) <= limit else text[: limit - 3] + "..."


def send_sms(body, api_key, sender, to_number):
    data = json.dumps({"sender": sender, "recipient": to_number, "content": body}).encode()
    req = urllib.request.Request(PURESMS_URL, data=data, method="POST")
    req.add_header("X-Api-Key", api_key)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", USER_AGENT)
    with open_url(req) as resp:
        resp.read()


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path, state):
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def in_quiet_hours(window, now=None):
    """True if UK local time is inside window "HH:MM-HH:MM" (may cross midnight)."""
    if not window:
        return False
    now = now or datetime.now(UK)
    start, end = (datetime.strptime(t.strip(), "%H:%M").time() for t in window.split("-"))
    t = now.time()
    return start <= t < end if start < end else t >= start or t < end


def coming_weekend(now):
    """Saturday and Sunday of the coming weekend."""
    saturday = (now + timedelta(days=(5 - now.weekday()) % 7 or 7)).date()
    return [saturday, saturday + timedelta(days=1)]


def weekly_due(now, last_sent):
    """True from Thursday 18:00 UK time until that week's weekend preview is sent."""
    week = now.strftime("%G-W%V")
    return now.weekday() == 3 and now.hour >= 18 and last_sent != week


LEADING_DATE = re.compile(
    r"^(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s+\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+(?:\s+\d{4})?\s*[,:.-]?\s*",
    re.I)


def strip_leading_date(reason):
    """Drop a leading "Sunday 18 October," since the message already says which day."""
    rest = LEADING_DATE.sub("", reason, count=1)
    return rest[:1].upper() + rest[1:] if rest else reason


def format_day(day, statuses):
    parts = []
    for s in statuses.values():
        if s["ok"]:
            parts.append(f"{s['name']}: running normally, no planned works.")
        else:
            s = dict(s, reasons=[strip_leading_date(r) for r in s["reasons"]])
            parts.append(format_problem(s, limit=400))
    return f"{day:%a %-d %b}: " + " ".join(parts)


def format_weekly(days_statuses):
    return "Train status for the coming weekend.\n" + "\n".join(
        format_day(day, statuses) for day, statuses in days_statuses)


def send_weekly(lines, days, dry_run):
    key = os.environ.get("TFL_APP_KEY")
    send_all([format_weekly([(d, fetch_statuses(lines, key, day=d)) for d in days])], dry_run)


def send_all(messages, dry_run):
    if dry_run:
        for m in messages:
            print(f"[DRY RUN] SMS: {SMS_PREFIX}{m}", flush=True)
        return
    api_key = os.environ["PURESMS_API_KEY"]
    sender = os.environ["PURESMS_SENDER"]
    recipients = [n.strip() for n in os.environ["ALERT_TO_NUMBER"].split(",") if n.strip()]
    for m in messages:
        for to in recipients:
            send_sms(SMS_PREFIX + m, api_key, sender, to)
        print(f"Sent SMS: {SMS_PREFIX}{m}", flush=True)


def after_shabbat(lines, label, dry_run):
    """First check after Shabbat or Yom Tov: one text listing any lines still disrupted."""
    current = fetch_statuses(lines, os.environ.get("TFL_APP_KEY"))
    problems = [format_still_disrupted(s) for s in current.values() if not s["ok"]]
    print(f"After {label}: " + ("; ".join(problems) or "all lines Good Service"), flush=True)
    if problems:
        send_all([" ".join(problems)], dry_run)
    return current


def check_once(lines, previous, dry_run):
    """Check the lines, text any changes, and return the state to keep."""
    current = fetch_statuses(lines, os.environ.get("TFL_APP_KEY"))
    messages = build_messages(previous, current)
    stamp = datetime.now(UK).strftime("%H:%M")
    print(f"{stamp} " + "; ".join(f"{s['name']}: {s['summary']}" for s in current.values()), flush=True)
    if messages:
        send_all(messages, dry_run)
    return current


def main():
    lines = [l.strip() for l in os.environ.get("TRAIN_LINES", "c2c,suffragette").split(",") if l.strip()]
    state_file = os.environ.get("STATE_FILE", "state.json")
    dry_run = os.environ.get("DRY_RUN") == "1"
    run_minutes = float(os.environ.get("RUN_MINUTES") or 0)
    interval = float(os.environ.get("CHECK_SECONDS") or 60)
    quiet = os.environ.get("QUIET_HOURS", "00:00-05:00")

    if os.environ.get("WEEKLY_PREVIEW") == "1":
        send_weekly(lines, coming_weekend(datetime.now(UK)), dry_run)
        return 0

    if os.environ.get("TEST_AFTER_SHABBAT") == "1":
        current = fetch_statuses(lines, os.environ.get("TFL_APP_KEY"))
        problems = [format_still_disrupted(s) for s in current.values() if not s["ok"]]
        if not problems:
            problems = ["c2c: Severe Delays since Sat 14:32. Signal failure at Upminster. "
                        "Still disrupted. (example)"]
        send_all(["TEST. " + " ".join(problems)], dry_run)
        return 0

    if os.environ.get("TEST_SMS") == "1":
        current = fetch_statuses(lines, os.environ.get("TFL_APP_KEY"))
        status = "; ".join(f"{v['name']}: {v['summary']}" for v in current.values())
        send_all([f"Test message. {status}"], dry_run)
        return 0

    shabbat_on = os.environ.get("SHABBAT", "1") != "0"
    candle_minutes = float(os.environ.get("SHABBAT_CANDLE_MINUTES") or 18)
    end_minutes = float(os.environ.get("SHABBAT_END_MINUTES") or 72)
    margin = float(os.environ.get("SHABBAT_MARGIN_MINUTES") or 5)

    state = load_state(state_file)
    deadline = time.monotonic() + run_minutes * 60
    while True:
        now = datetime.now(UK)
        rest = shabbat_on and shabbat.in_rest_period(now, candle_minutes, end_minutes, margin)
        if rest:
            print(f"{rest}, not checking.", flush=True)
            if state.get("_after_shabbat") != rest:
                state["_after_shabbat"] = rest
                save_state(state_file, state)
        elif in_quiet_hours(quiet, now):
            print("Quiet hours, not checking.", flush=True)
        else:
            try:
                if weekly_due(now, state.get("_weekly")):
                    send_weekly(lines, coming_weekend(now), dry_run)
                    state["_weekly"] = now.strftime("%G-W%V")
                    save_state(state_file, state)
                markers = {k: v for k, v in state.items() if k.startswith("_")}
                label = markers.pop("_after_shabbat", None)
                if label:
                    new_state = after_shabbat(lines, label if isinstance(label, str) else "Shabbat", dry_run)
                else:
                    new_state = check_once(lines, state, dry_run)
                state = {**new_state, **markers}
                save_state(state_file, state)
            except (urllib.error.URLError, OSError, ValueError) as e:
                # Keep the old state so a failed SMS is retried on the next check.
                if run_minutes <= 0:
                    raise
                print(f"Check failed, will retry: {e}", file=sys.stderr, flush=True)
        if time.monotonic() + interval >= deadline:
            break
        time.sleep(interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
