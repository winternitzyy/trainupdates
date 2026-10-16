"""c2c's own live status, as shown on c2c-online.co.uk ("Via Basildon: Severe
disruptions" and the alert box). This is the same data the website loads, so it
is usually ahead of TfL and National Rail. It is not an official API and may
change without notice; callers fall back to TfL if it fails.
"""

import html
import json
import re
import urllib.parse
import urllib.request

URL = "https://www.c2c-online.co.uk/wp/wp-admin/admin-ajax.php"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124 Safari/537.36 trainupdates")
ROUTES = ("basildon", "rainham", "ockendon")


def fetch(url=URL):
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode({"action": "get_c2c_status"}).encode(),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*",
                 "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.c2c-online.co.uk/"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _paragraphs(content):
    parts = re.split(r"</p>|<br\s*/?>|</li>|\n", content or "", flags=re.I)
    return [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", p)).split()) for p in parts]


def alert_text(content, limit=320):
    """The facts at the top of a c2c alert: what happened and the impact,
    stopping before the standard customer advice."""
    kept = []
    for p in _paragraphs(content):
        if not p:
            continue
        if p.lower().startswith("customer advice"):
            break
        if p.endswith((":", "?")):  # headings like "Impact:" or "What's Happened?"
            continue
        kept.append(p if p.endswith((".", "!")) else p + ".")
    text = " ".join(kept)
    return text if len(text) <= limit else text[: limit - 3].rsplit(" ", 1)[0] + "..."


def to_status(data):
    """Turn c2c's status into the same shape as a TfL line status."""
    alerts = [a for a in data.get("alerts") or [] if a.get("severity") in ("minor", "severe")]
    alerts += list(data.get("emergency_announcements") or [])
    if not alerts:
        return {"name": "c2c", "ok": True, "summary": "Good Service", "reasons": [], "since": None,
                "source": "c2c"}
    severe = any(a.get("severity", "severe") == "severe" for a in alerts)
    reasons = []
    for a in alerts:
        title = " ".join((a.get("title") or "").split())
        text = alert_text(a.get("content"))
        reasons.append(f"{title}: {text}" if title and text else title or text)
    groups = data.get("route_groups") or {}
    hit = [r for r in ROUTES if (groups.get(r) or {}).get("badge") in ("minor", "severe")]
    if hit and len(hit) < len(ROUTES):
        reasons.append("Affected: " + ", ".join(f"via {r.capitalize()}" for r in hit) + ".")
    return {"name": "c2c", "ok": False, "summary": "Severe disruption" if severe else "Minor disruption",
            "reasons": reasons, "since": None, "source": "c2c"}
