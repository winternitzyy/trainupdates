"""Look at c2c's website to find where its route status ("Via Basildon: Severe
disruptions") comes from. Prints matching snippets and likely data URLs."""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
BASE = "https://www.c2c-online.co.uk/"
WORDS = ("Via Basildon", "Via Rainham", "Via Ockendon", "Severe disruption", "Good service",
         "disruption", "admin-ajax", "wp-json", "service-status", "line-status", "travel-update")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def show(label, body, words=WORDS, limit=3):
    for word in words:
        for m in list(re.finditer(re.escape(word), body, re.I))[:limit]:
            print(f"  [{label}:{word}] ..." + " ".join(body[max(0, m.start() - 150): m.end() + 150].split()) + "...")


home = get(BASE)
# 1. WordPress REST API routes mentioning status/disruption
try:
    index = json.loads(get(BASE + "wp-json/"))
    routes = [r for r in index.get("routes", {}) if re.search(r"disrupt|status|incident|travel|line|service|alert", r, re.I)]
    print("== wp-json routes:", len(index.get("routes", {})), "total; relevant:")
    for r in routes[:60]:
        print("  route:", r)
except Exception as e:
    print("== wp-json:", e)

# 2. Scripts from c2c's own site that mention the widget
scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', home)
inline = re.findall(r"<script[^>]*>(.*?)</script>", home, re.S)
print(f"== {len(scripts)} script files, {len(inline)} inline scripts")
for s in inline:
    if re.search(r"disrupt|status|ajax|wp-json", s, re.I):
        show("inline", s, limit=2)
for src in scripts:
    url = urllib.parse.urljoin(BASE, src)
    if "c2c-online" not in url:
        continue
    try:
        js = get(url)
    except Exception as e:
        print("  script", url, e)
        continue
    if re.search(r"disrupt|Severe|Via Basildon|service-status|line-status", js, re.I):
        print("== script", url, len(js), "chars")
        show("js", js, words=("disrupt", "Severe", "Via ", "ajax", "wp-json", "fetch(", "/api/", "action:"), limit=4)
