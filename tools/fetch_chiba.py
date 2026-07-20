# -*- coding: utf-8 -*-
"""千葉予選ページを取得(回次1〜107、404なら東西分割 e/w を試す)"""
import time, os, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "chiba")
os.makedirs(OUT, exist_ok=True)

def fetch(name):
    path = os.path.join(OUT, f"{name}.htm")
    if os.path.exists(path) and os.path.getsize(path) > 5000:
        return "cached"
    url = f"https://bibijr.vivian.jp/chiba/{name}"
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
        for sfx in ("e", "w"):
            r2 = fetch(f"{n}{sfx}")
            results[f"{n}{sfx}"] = r2

ok = sorted(k for k, v in results.items() if v.startswith(("ok", "cached")))
miss = sorted(k for k, v in results.items() if not v.startswith(("ok", "cached")))
print("ok:", len(ok))
print(" ".join(ok))
print("miss:", len(miss))
print(" ".join(miss))
