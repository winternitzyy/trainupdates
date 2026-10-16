"""Look at c2c's website to find where its route status ("Via Basildon: Severe
disruptions") comes from. Prints matching snippets and likely data URLs."""
import re
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
PAGES = sys.argv[1:] or ["https://www.c2c-online.co.uk/", "https://www.c2c-online.co.uk/travel-updates/"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.headers.get("Content-Type"), resp.read().decode("utf-8", "replace")


for url in PAGES:
    try:
        status, ctype, body = get(url)
    except urllib.error.HTTPError as e:
        print(f"== {url}: HTTP {e.code}")
        continue
    except Exception as e:
        print(f"== {url}: {e}")
        continue
    print(f"== {url}: HTTP {status} {ctype} {len(body)} chars")
    for word in ("Via Basildon", "Via Rainham", "Via Ockendon", "Severe disruption", "Good service",
                 "Cancellations to services"):
        for m in list(re.finditer(re.escape(word), body, re.I))[:2]:
            snippet = " ".join(body[max(0, m.start() - 200): m.end() + 200].split())
            print(f"  [{word}] ...{snippet}...")
    urls = set(re.findall(r'["\'](/[^"\'\s]*(?:api|status|disruption|incident|service-update|travel)[^"\'\s]*)["\']', body, re.I))
    urls |= set(re.findall(r'https?://[^"\'\s<>]*(?:api|status|disruption|incident)[^"\'\s<>]*', body, re.I))
    for u in sorted(urls)[:40]:
        print("  url:", u)
