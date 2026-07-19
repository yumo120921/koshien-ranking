# -*- coding: utf-8 -*-
"""bibijr.vivian.jp/koya の年度別ページを丁寧に取得する
ページ番号 = (西暦 + 1725 - 1900)*10 + 季節番号? → 実際は X1=春, X2=夏 で X=年-1725
1967春=2421 → X=242 → 年 = X + 1725
1915 → X=190, 2025 → X=300
"""
import time
import urllib.request
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "koya")
os.makedirs(OUT, exist_ok=True)

def fetch(num):
    path = os.path.join(OUT, f"{num}.htm")
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return "cached"
    url = f"https://bibijr.vivian.jp/koya/{num}.htm"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (data-research; contact via site form)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 3000:
            return f"small({len(data)})"
        open(path, "wb").write(data)
        return f"ok({len(data)})"
    except Exception as e:
        return f"err({type(e).__name__} {getattr(e, 'code', '')})"

results = {}
for x in range(190, 301):  # 1915..2025
    year = x + 1725
    for season in (1, 2):
        num = x * 10 + season
        r = fetch(num)
        results[num] = (year, "春" if season == 1 else "夏", r)
        if r.startswith("ok"):
            time.sleep(0.7)

ok = sum(1 for _, _, r in results.values() if r.startswith(("ok", "cached")))
print("fetched/cached:", ok, "of", len(results))
for num, (year, season, r) in sorted(results.items()):
    if not r.startswith(("ok", "cached")):
        print("MISS", num, year, season, r)
