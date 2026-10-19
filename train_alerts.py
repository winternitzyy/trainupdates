"""Send an SMS when c2c or the Suffragette line has problems.

Checks the TfL Unified API for line status, then texts you when a line's
status changes, for example from Good Service to Severe Delays
and back again. It saves the last status it saw so it does not text you
about the same problem twice.

Texts go out one of two ways:
  NTFY_TOPIC       If set, each text is published to this ntfy topic, and a
                   phone running ntfy + Tasker sends it as an SMS from its SIM.
  NTFY_SERVER      Optional, defaults to "https://ntfy.sh".
  NTFY_TOKEN       Optional access token, if the topic is protected.
  PURESMS_API_KEY, PURESMS_SENDER, ALERT_TO_NUMBER
      Used when NTFY_TOPIC is not set, or as a backup if ntfy can't be
      reached. PURESMS_SENDER is a sender set up in your PureSMS dashboard.
      ALERT_TO_NUMBER is in +44 format; separate several with commas.

Environment variables:
  TFL_APP_KEY      Optional TfL API key (higher rate limits).
  C2C_WEBSITE      Live c2c status comes from c2c's own website (the status
                   box on c2c-online.co.uk), which is usually first to report
                   problems. On by default; set to "0" to use TfL only.
  NR_INCIDENTS_KEY Optional Rail Data Marketplace key for National Rail's
                   Knowledgebase Incidents feed. When set, c2c alerts use
                   National Rail's explanation, and the weekend preview takes
                   c2c planned works from National Rail. TfL is the fallback.
  NR_LDB_KEY       Optional Rail Data Marketplace key for National Rail's staff
                   departure boards. When set, c2c texts list the next trains
                   WCF-BKG and BKG-STO both ways (for the Suffragette line, TfL is the fallback).
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

import c2c_status
import live_trains
import nr_incidents
import shabbat
import timing

TFL_URL = "https://api.tfl.gov.uk/Line/{lines}/Status"
TFL_RANGE_URL = "https://api.tfl.gov.uk/Line/{lines}/Status/{start}/to/{end}"
UK = ZoneInfo("Europe/London")
PURESMS_URL = "https://connect-api.divergent.cloud/sms/send"
NTFY_SERVER = "https://ntfy.sh"
GOOD_SERVICE = 10
NR_OPERATORS = {"c2c": "CC"}  # TfL line id -> National Rail operator code
SMS_PREFIX = "Traincliff Alerts: "
BOARDS_INTRO = "This is currently displayed on the departure boards: "
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
    if shown_reasons(status):
        text += " " + " ".join(shown_reasons(status))
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return text + " Still disrupted." + (" " + status["live"] if status.get("live") else "")


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
            messages.append(f"{now['name']}: back to Good Service."
                            + (" " + now["live"] if now.get("live") else ""))
        elif not now["ok"] and before["ok"]:
            messages.append(format_problem(now))
        elif not now["ok"] and (now["summary"] != before["summary"] or now["reasons"] != before["reasons"]):
            # The line was already disrupted; this is new information about it.
            messages.append("Update: " + format_problem(now))
    return messages


def shown_reasons(status):
    """National Rail's explanation if we have one, otherwise TfL's reason, as sentences."""
    reasons = status.get("nr_reasons") or status["reasons"]
    return [r if r.endswith((".", "!", "?")) or r.startswith("http") else r + "." for r in reasons]


def format_problem(status, limit=600):
    text = f"{status['name']}: {status['summary']}."
    if shown_reasons(status):
        text += " " + " ".join(shown_reasons(status))
    text = text if len(text) <= limit else text[: limit - 3] + "..."
    return text + (" " + status["live"] if status.get("live") else "")


def add_live_trains(current, previous=None, every_line=False):
    """Add how the next trains on our journey are running to each disrupted line,
    and to each line that was disrupted at the last check (it may have just recovered)."""
    previous = previous or {}
    for line_id, status in current.items():
        was_bad = not (previous.get(line_id) or {}).get("ok", True)
        if not line_id.startswith("_") and (every_line or not status["ok"] or was_bad):
            live = live_trains.check(line_id, app_key=os.environ.get("TFL_APP_KEY"))
            if live and not status["ok"]:
                live = BOARDS_INTRO + live
            status["live"] = live
    return current


def drop_live_trains(current):
    """The live board text is only for the text being sent; don't keep it."""
    for line_id, status in current.items():
        if not line_id.startswith("_"):
            status.pop("live", None)
    return current


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


def describe_day(status):
    """What one line looks like on one day, without the line's name."""
    if status["ok"]:
        return "running normally, no planned works."
    reasons = [r if r.endswith((".", "!", "?")) else r + "."
               for r in (strip_leading_date(r) for r in status["reasons"])]
    text = " ".join([f"{status['summary']}."] + reasons)
    return text if len(text) <= 400 else text[:397] + "..."


def format_weekly(days_statuses):
    """One entry per line. Lines whose works are dated themselves (National Rail)
    list each work once; others say "Sat: ... Sun: ..." unless both days match."""
    days = [d for d, _ in days_statuses]
    span = f"{days[0]:%a %-d}" + (f" & {days[-1]:%a %-d %b}" if len(days) > 1 else f" {days[0]:%b}")
    parts = [f"Train status for the coming weekend ({span})."]
    for line_id, first in days_statuses[0][1].items():
        per_day = [statuses[line_id] for _, statuses in days_statuses if line_id in statuses]
        if first.get("nr_planned"):
            works = list(dict.fromkeys(r for st in per_day for r in st["reasons"]))
            text = ("Planned works. " + " ".join(w if w.endswith((".", "!", "?")) else w + "." for w in works)
                    if works else "running normally, no planned works.")
        else:
            texts = [describe_day(st) for st in per_day]
            if len(set(texts)) == 1:
                text = texts[0]
            else:
                text = " ".join(f"{d:%a}: {t}" for d, t in zip(days, texts))
        parts.append(f"{first['name']}: {text}")
    return "\n".join(parts)


def add_nr_planned_works(day, statuses):
    """Replace TfL's planned status with National Rail's planned works where we can."""
    if not nr_incidents.configured():
        return statuses
    try:
        incidents = nr_incidents.get()
    except Exception as e:  # keep TfL's view if National Rail is unavailable
        print(f"National Rail feed unavailable, using TfL: {e}", file=sys.stderr, flush=True)
        return statuses
    for line_id, code in NR_OPERATORS.items():
        if line_id in statuses:
            works = nr_incidents.planned_on(nr_incidents.for_operator(incidents, code), day, UK)
            summaries = list(dict.fromkeys(w["summary"] for w in works))
            statuses[line_id] = dict(statuses[line_id], ok=not works, summary="Planned works",
                                     reasons=summaries, nr_reasons=None, nr_planned=True)
    return statuses


def send_weekly(lines, days, dry_run):
    key = os.environ.get("TFL_APP_KEY")
    send_all([format_weekly([(d, add_nr_planned_works(d, fetch_statuses(lines, key, day=d)))
                             for d in days])], dry_run)


C2C_KEEP_MINUTES = 15  # how long to trust the last c2c reading if the website is down


def apply_c2c_website(current, previous, now=None):
    """Replace TfL's c2c status with c2c's own. If c2c's website can't be read,
    keep the last c2c reading for a while so a blip doesn't look like a change."""
    if "c2c" not in current or os.environ.get("C2C_WEBSITE", "1") == "0":
        return current
    now = now or datetime.now(UK)
    before = (previous or {}).get("c2c") or {}
    try:
        status = c2c_status.to_status(c2c_status.fetch())
    except Exception as e:
        fetched = before.get("fetched")
        if before.get("source") == "c2c" and fetched and \
                now - datetime.fromisoformat(fetched) < timedelta(minutes=C2C_KEEP_MINUTES):
            print(f"c2c website unavailable, keeping last reading: {e}", file=sys.stderr, flush=True)
            current["c2c"] = dict(before)
        else:
            print(f"c2c website unavailable, using TfL: {e}", file=sys.stderr, flush=True)
        return current
    status["fetched"] = now.isoformat()
    if not status["ok"]:
        # Keep the time we first saw this disruption (National Rail may refine it).
        status["since"] = before.get("since") if not before.get("ok", True) and before.get("since") \
            else now.isoformat()
    current["c2c"] = status
    return current


def add_nr_explanations(current, now=None):
    """For disrupted lines, add National Rail's summary of what is happening."""
    if not nr_incidents.configured():
        return current
    disrupted = [l for l in NR_OPERATORS if l in current and not current[l]["ok"]]
    if not disrupted:
        return current
    try:
        incidents = nr_incidents.get()
    except Exception as e:  # texts fall back to TfL's reason
        print(f"National Rail feed unavailable, using TfL: {e}", file=sys.stderr, flush=True)
        return current
    now = now or datetime.now(UK)
    for line_id in disrupted:
        active = nr_incidents.active_unplanned(nr_incidents.for_operator(incidents, NR_OPERATORS[line_id]), now)
        if active:
            if current[line_id].get("source") != "c2c":
                current[line_id]["nr_reasons"] = list(dict.fromkeys(i["summary"] for i in active))
            if active[0]["start"]:
                current[line_id]["since"] = active[0]["start"].isoformat()
    return current


def send_ntfy(body, topic, server=None, token=None):
    url = f"{(server or NTFY_SERVER).rstrip('/')}/{urllib.parse.quote(topic)}"
    req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST")
    req.add_header("User-Agent", USER_AGENT)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with open_url(req) as resp:
        resp.read()


def send_puresms(body):
    api_key = os.environ["PURESMS_API_KEY"]
    sender = os.environ["PURESMS_SENDER"]
    for to in [n.strip() for n in os.environ["ALERT_TO_NUMBER"].split(",") if n.strip()]:
        send_sms(body, api_key, sender, to)


def puresms_configured():
    return all(os.environ.get(k) for k in ("PURESMS_API_KEY", "PURESMS_SENDER", "ALERT_TO_NUMBER"))


# Characters outside the standard SMS alphabet make a text use 70-character parts
# instead of 160, and some phones won't send long texts like that.
PLAIN = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "-",
         "\u2026": "...", "\u2192": " to ", "\u00a0": " ", "\u2022": "-"}


def plain_text(body):
    """Swap curly quotes, long dashes and the like for plain characters."""
    return "".join(PLAIN.get(c, c) for c in body)


def send_all(messages, dry_run):
    topic = os.environ.get("NTFY_TOPIC")
    for m in messages:
        body = plain_text(SMS_PREFIX + m)
        if dry_run:
            print(f"[DRY RUN] SMS via {'ntfy' if topic else 'PureSMS'}: {body}", flush=True)
            continue
        if topic:
            try:
                send_ntfy(body, topic, os.environ.get("NTFY_SERVER"), os.environ.get("NTFY_TOKEN"))
                print(f"Sent via ntfy: {body}", flush=True)
                continue
            except (urllib.error.URLError, OSError) as e:
                if not puresms_configured():
                    raise
                print(f"ntfy failed ({e}), sending through PureSMS instead.", file=sys.stderr, flush=True)
        send_puresms(body)
        print(f"Sent SMS: {body}", flush=True)


def after_shabbat(lines, label, dry_run):
    """First check after Shabbat or Yom Tov: one text listing any lines still disrupted."""
    current = add_nr_explanations(apply_c2c_website(fetch_statuses(lines, os.environ.get("TFL_APP_KEY")), {}))
    add_live_trains(current)
    problems = [format_still_disrupted(s) for s in current.values() if not s["ok"]]
    print(f"After {label}: " + ("; ".join(problems) or "all lines Good Service"), flush=True)
    if problems:
        send_all([" ".join(problems)], dry_run)
    return drop_live_trains(current)


def check_once(lines, previous, dry_run):
    """Check the lines, text any changes, and return the state to keep."""
    tfl = fetch_statuses(lines, os.environ.get("TFL_APP_KEY"))
    tfl_c2c_bad = "c2c" in tfl and not tfl["c2c"]["ok"]
    current = add_nr_explanations(apply_c2c_website(tfl, previous))
    messages = build_messages(previous, current)
    if messages:
        # Only look at the live boards when we are about to send a text.
        messages = build_messages(previous, add_live_trains(current, previous))
    stamp = datetime.now(UK).strftime("%H:%M")
    print(f"{stamp} " + "; ".join(f"{s['name']}: {s['summary']}" for s in current.values()), flush=True)
    if messages:
        send_all(messages, dry_run)
    drop_live_trains(current)
    current["_episode"] = track_sources(previous.get("_episode"), current, tfl_c2c_bad)
    return current


def track_sources(episode, current, tfl_c2c_bad, now=None):
    """Log which source reported each c2c disruption first. Never breaks the checks."""
    try:
        now = now or datetime.now(UK)
        c2c = current.get("c2c") or {}
        c2c_bad = c2c.get("source") == "c2c" and not c2c.get("ok", True)
        nr_active = []
        if nr_incidents.configured():
            try:
                nr_active = nr_incidents.active_unplanned(
                    nr_incidents.for_operator(nr_incidents.get(), NR_OPERATORS["c2c"]), now)
            except Exception:
                pass
        title = (c2c.get("reasons") or [""])[0].split(":")[0] if c2c_bad else ""
        episode, row = timing.update(episode, now, c2c_bad, title, tfl_c2c_bad, nr_active)
        if row:
            timing.append(row, os.environ.get("DISRUPTION_LOG", "disruption_log.csv"))
            print(f"Logged disruption: first reported by {row['first']} "
                  f"(c2c {row['c2c_website'] or '-'}, TfL {row['tfl'] or '-'}, "
                  f"National Rail {row['national_rail'] or '-'})", flush=True)
        return episode
    except Exception as e:
        print(f"Source tracking failed: {e}", file=sys.stderr, flush=True)
        return episode


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
        current = add_live_trains(add_nr_explanations(
            apply_c2c_website(fetch_statuses(lines, os.environ.get("TFL_APP_KEY")), {})))
        problems = [format_still_disrupted(s) for s in current.values() if not s["ok"]]
        if not problems:
            problems = ["c2c: Severe Delays since Sat 14:32. Signal failure at Upminster. "
                        "Still disrupted. (example)"]
        send_all(["TEST. " + " ".join(problems)], dry_run)
        return 0

    if os.environ.get("TEST_SMS") == "1":
        current = add_live_trains(add_nr_explanations(
            apply_c2c_website(fetch_statuses(lines, os.environ.get("TFL_APP_KEY")), {})), every_line=True)
        status = " ".join(format_problem(v) for v in current.values())
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
                state = {**markers, **new_state}
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
