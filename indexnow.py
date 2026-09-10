"""Tell IndexNow-enabled search engines (Bing, Yandex, Seznam, Naver…) which
pages changed today, using the lastmod dates getposts.py writes to sitemap.xml.

Run after the push so the key file and the new pages are already deployed.
"""
import re
import sys
from datetime import datetime as dt, timezone

import requests

HOST = "ransom.privtools.eu"
KEY = "d3a4a6359504691e94c479986c276179"  # must match ./<KEY>.txt at the site root

today = dt.now(tz=timezone.utc).strftime('%Y-%m-%d')

with open('./sitemap.xml', encoding='utf-8') as f:
    sitemap = f.read()

urls = [
    loc for loc, lastmod in re.findall(r'<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>', sitemap)
    if lastmod.startswith(today)
]

if not urls:
    print("No pages changed today — nothing to submit")
    sys.exit(0)

r = requests.post(
    "https://api.indexnow.org/indexnow",
    json={
        "host": HOST,
        "key": KEY,
        "keyLocation": f"https://{HOST}/{KEY}.txt",
        "urlList": urls[:10000],
    },
    timeout=60,
)
print(f"IndexNow: submitted {len(urls)} URLs → HTTP {r.status_code}")
# 200/202 = accepted. Anything else is logged but not fatal: indexing is best effort.
