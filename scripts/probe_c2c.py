"""Fetch c2c's own live status (the "Via Basildon: Severe disruptions" widget on
c2c-online.co.uk) and print it."""
import json
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
BASE = "https://www.c2c-online.co.uk/"


def fetch(url, data=None):
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": UA, "Accept": "*/*", "X-Requested-With": "XMLHttpRequest", "Referer": BASE})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


home = fetch(BASE)
m = re.search(r'id=["\']service-status-js["\'][^>]*data-url=["\']([^"\']+)', home) or \
    re.search(r'data-url=["\']([^"\']+)["\'][^>]*id=["\']service-status-js', home)
ajax = urllib.parse.urljoin(BASE, m.group(1)) if m else urllib.parse.urljoin(BASE, "/wp/wp-admin/admin-ajax.php")
print("status URL:", ajax, "(found in page)" if m else "(guessed)")
raw = fetch(ajax, urllib.parse.urlencode({"action": "get_c2c_status"}).encode())
print("response:", len(raw), "chars")
data = json.loads(raw)
print("keys:", sorted(data) if isinstance(data, dict) else type(data))
print(json.dumps(data, indent=1)[:6000])
