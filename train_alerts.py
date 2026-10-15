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
  TEST_SMS         If set to "1", also send a test SMS with the current status.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

TFL_URL = "https://api.tfl.gov.uk/Line/{lines}/Status"
PURESMS_URL = "https://connect-api.divergent.cloud/sms/send"
GOOD_SERVICE = 10
USER_AGENT = "trainupdates/1.0 (+https://github.com/winternitzyy/trainupdates)"


def fetch_statuses(lines, app_key=None):
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
        descriptions = sorted({s.get("statusSeverityDescription", "Unknown") for s in statuses})
        reasons = []
        for s in statuses:
            reason = (s.get("reason") or "").strip()
            if reason and reason not in reasons:
                reasons.append(reason)
        result[line["id"]] = {
            "name": line.get("name", line["id"]),
            "ok": ok,
            "summary": ", ".join(descriptions) or "Unknown",
            "reasons": reasons,
        }
    return result


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


def main():
    lines = [l.strip() for l in os.environ.get("TRAIN_LINES", "c2c,suffragette").split(",") if l.strip()]
    state_file = os.environ.get("STATE_FILE", "state.json")
    dry_run = os.environ.get("DRY_RUN") == "1"

    current = fetch_statuses(lines, os.environ.get("TFL_APP_KEY"))
    previous = load_state(state_file)
    messages = build_messages(previous, current)

    for line_id, s in current.items():
        print(f"{s['name']}: {s['summary']}")

    if os.environ.get("TEST_SMS") == "1":
        status = "; ".join(f"{v['name']}: {v['summary']}" for v in current.values())
        messages = [f"Test from train alerts. {status}"] + messages

    if messages:
        if dry_run:
            for m in messages:
                print(f"[DRY RUN] SMS: {m}")
        else:
            api_key = os.environ["PURESMS_API_KEY"]
            sender = os.environ["PURESMS_SENDER"]
            recipients = [n.strip() for n in os.environ["ALERT_TO_NUMBER"].split(",") if n.strip()]
            for m in messages:
                for to in recipients:
                    send_sms(m, api_key, sender, to)
                print(f"Sent SMS: {m}")
    else:
        print("No changes, no SMS sent.")

    save_state(state_file, current)
    return 0


if __name__ == "__main__":
    sys.exit(main())
