# -*- coding: utf-8 -*-
"""年表ページに載っている残りのトーナメントページを取得"""
import time, os, re, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "koya")

nums = set()
raw = open(os.path.join(BASE, "nenpyou2.htm"), "rb").read().decode("shift_jis", errors="replace")
for m in re.finditer(r'href="[^"]*?(\d+)\.htm"', raw):
    nums.add(int(m.group(1)))
# 2025年の候補も追加で試す
nums.update([4071, 4072])

todo = sorted(n for n in nums if n >= 1000 and not (
    os.path.exists(os.path.join(OUT, f"{n}.htm")) and os.path.getsize(os.path.join(OUT, f"{n}.htm")) > 5000))
print("to fetch:", len(todo))

for n in todo:
    url = f"https://bibijr.vivian.jp/koya/{n}.htm"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (data-research)"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if len(data) > 3000:
            open(os.path.join(OUT, f"{n}.htm"), "wb").write(data)
            status = f"ok({len(data)})"
        else:
            status = "small"
    except Exception as e:
        status = f"err({getattr(e, 'code', type(e).__name__)})"
    print(n, status)
    time.sleep(0.7)
