# -*- coding: utf-8 -*-
"""都道府県予選ページの取得(汎用): python pref_fetch.py <県ローマ字>"""
import time, os, sys, urllib.request

pref = sys.argv[1] if len(sys.argv) > 1 else "kanagawa"
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, pref)
os.makedirs(OUT, exist_ok=True)

def fetch(name):
    path = os.path.join(OUT, f"{name}.htm")
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return "cached"
    url = f"https://bibijr.vivian.jp/{pref}/{name}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (data-research)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) < 3000:
            return "small"
        open(path, "wb").write(data)
        time.sleep(0.7)
        return "ok"
    except Exception as e:
        time.sleep(0.4)
        return f"err({getattr(e, 'code', type(e).__name__)})"

results = {}
for n in range(1, 108):
    r = fetch(str(n))
    results[str(n)] = r
    if not r.startswith(("ok", "cached")):
        for sfx in ("e", "w", "n", "s"):
            r2 = fetch(f"{n}{sfx}")
            results[f"{n}{sfx}"] = r2

ok = sorted(k for k, v in results.items() if v.startswith(("ok", "cached")))
miss = sorted(k for k, v in results.items() if not v.startswith(("ok", "cached")))
print("ok:", len(ok))
print(" ".join(ok))
print("miss:", len(miss))
print(" ".join(miss))
