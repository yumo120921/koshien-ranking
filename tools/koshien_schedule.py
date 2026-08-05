# -*- coding: utf-8 -*-
"""甲子園(全国大会)の試合日程を取得して data/koshien/schedule.json に保存する。

出典: バーチャル高校野球の全国大会試合リストJSON(選抜・選手権とも開催中の大会が入る)。
トップページの「ライブ配信」ウィジェットが参照する。毎日1回、GitHub Actionsから実行。
"""
import io
import json
import os
import re
import sys
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://www.asahicom.jp/koshien/contents/virtualbaseball/site/zenkoku_all_game_list.json"
OUT = os.path.join(ROOT, "data", "koshien", "schedule.json")


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (koshien-ranking.com data sync; once daily)"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r"\((.*)\)\s*;?\s*$", raw, re.S)
    j = json.loads(m.group(1) if m else raw)
    days = []
    for d in j.get("data", []):
        if d.get("all_cancel_flg"):
            continue  # 中止日
        date = str(d.get("game_date", ""))
        if not re.fullmatch(r"\d{8}", date):
            continue
        times = []
        for g in d.get("game_list", []):
            t = (g.get("playball_time") or "").strip()
            if re.fullmatch(r"\d{1,2}:\d{2}", t) and not g.get("no_game"):
                times.append(t)
        if times:
            days.append({"date": date, "times": sorted(set(times), key=lambda x: (len(x), x))})
    out = {"days": days}
    old = None
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            pass
    if out != old:
        json.dump(out, open(OUT, "w", encoding="utf-8", newline="\n"), ensure_ascii=False, indent=1)
        print(f"schedule.json 更新: {len(days)}日分")
    else:
        print("schedule.json 変更なし")


def fetch_zenkoku_yagura():
    """全国大会(甲子園)の全試合リストを data/koshien/yagura.json に保存"""
    url = "https://www.asahicom.jp/koshien/contents/virtualbaseball/site/zenkoku_yagura.json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (koshien-ranking.com data sync; once daily)"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    m = re.search(r"\((.*)\)\s*;?\s*$", raw, re.S)
    j = json.loads(m.group(1) if m else raw)
    games = []
    for g in j.get("info", []):
        a = (g.get("team1") or "").split("（")[0].strip()
        b = (g.get("team3") or "").split("（")[0].strip()
        # 未確定(空欄)の試合も枠構造として必要なので保存する
        games.append({"num": int(g.get("number") or 0),
                      "round": (g.get("tournament") or "").strip(),
                      "date": str(g.get("game_date") or ""),
                      "a": a, "b": b,
                      "as": (g.get("score1") or "").strip(),
                      "bs": (g.get("score3") or "").strip()})
    if not games:
        return
    out = {"games": games}
    path = os.path.join(ROOT, "data", "koshien", "yagura.json")
    old = None
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    if out != old:
        json.dump(out, open(path, "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, separators=(",", ":"))
        print(f"koshien/yagura.json 更新: {len(games)}試合")
    else:
        print("koshien/yagura.json 変更なし")


if __name__ == "__main__":
    main()
    fetch_zenkoku_yagura()
