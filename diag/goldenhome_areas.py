"""Print Golden Home's area dropdown (Greek name → URL slug) for each Athens region page.

Runner-only diagnostic used to build ``GoldenHomeCollector.AREA_SLUGS``. Polite: 4–7 s apart.
"""

from __future__ import annotations

import random
import re
import time

import requests

from scout.collectors.base import USER_AGENT

REGIONS = [
    "athens-center",
    "athens-northern-suburbs",
    "athina-southern-suburbs",
    "athens-western-suburbs",
    "athens-eastern-suburbs",
    "piraeus-suburbs",
]
ITEM = re.compile(r'class="dropdown-item" href="/property/pwlisi/(perioxi-[a-z0-9-]+)">([^<]+?)\s*</a>')

s = requests.Session()
s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "el-GR,el;q=0.9"})
for region in REGIONS:
    r = s.get(f"https://goldenhome.gr/property/pwlisi/perioxi-{region}", timeout=30)
    print(f"=== {region} {r.status_code} {len(r.text)}")
    for slug, name in dict.fromkeys(ITEM.findall(r.text)):
        print(f"AREA {region} | {slug} | {name.strip()}")
    time.sleep(random.uniform(4, 7))
