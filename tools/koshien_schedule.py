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

from name_map import NAME_MAP  # 表記ゆれの正規化(関東第一→関東一 等)

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
        a = NAME_MAP.get(a, a)
        b = NAME_MAP.get(b, b)
        # 未確定(空欄)の試合も枠構造として必要なので保存する
        def _pref(t):
            t = (t or "")
            return t.split("（")[1].rstrip("）").strip() if "（" in t else ""
        games.append({"num": int(g.get("number") or 0),
                      "round": (g.get("tournament") or "").strip(),
                      "date": str(g.get("game_date") or ""),
                      "a": a, "b": b,
                      "ap": _pref(g.get("team1")), "bp": _pref(g.get("team3")),
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


def upsert_koshien_results():
    """決勝まで終了した全国大会の成績を data/koshien/results.csv と scores.json に反映する。
    トップページ(春夏総合ランキング)の集計は results.csv が源泉のため、
    これが無いと当年の甲子園がランキングに反映されない"""
    ypath = os.path.join(ROOT, "data", "koshien", "yagura.json")
    if not os.path.exists(ypath):
        return
    yg = json.load(open(ypath, encoding="utf-8"))
    games = yg.get("games") or []

    def _done(g):
        return (g.get("a") and g.get("b") and str(g.get("as", "")).isdigit()
                and str(g.get("bs", "")).isdigit() and int(g["as"]) != int(g["bs"]))

    qf = sorted((g for g in games if g["round"] == "準々決勝"), key=lambda g: g["num"])
    sf = sorted((g for g in games if g["round"] == "準決勝"), key=lambda g: g["num"])
    fi = [g for g in games if g["round"] == "決勝"]
    if len(qf) != 4 or len(sf) != 2 or len(fi) != 1 or not all(map(_done, qf + sf + fi)):
        print("koshien/results.csv: 大会未了のため追記なし")
        return
    fi = fi[0]
    dates = [str(g.get("date", "")) for g in games if re.fullmatch(r"\d{8}", str(g.get("date", "")))]
    if not dates:
        return
    year = max(dates)[:4]
    season = "春" if max(int(d[4:6]) for d in dates) <= 5 else "夏"

    def _win(g):
        return ("a", "b") if int(g["as"]) > int(g["bs"]) else ("b", "a")

    def _label(g, side):
        name, pref = g[side], g.get(side + "p", "")
        return f"{name}({pref})" if pref else name

    w, l = _win(fi)
    ch, ru = _label(fi, w), _label(fi, l)
    ws, ls = (fi["as"], fi["bs"]) if w == "a" else (fi["bs"], fi["as"])
    b4 = [_label(g, _win(g)[1]) for g in sf]
    b8 = [_label(g, _win(g)[1]) for g in qf]
    line = ",".join([year, season, ch, ru] + b4 + b8 + [str(ws), str(ls)])

    cpath = os.path.join(ROOT, "data", "koshien", "results.csv")
    lines = open(cpath, encoding="utf-8").read().rstrip("\n").split("\n")
    prefix = f"{year},{season},"
    hit = [i for i, x in enumerate(lines) if x.startswith(prefix)]
    if hit:
        if lines[hit[0]] == line:
            print(f"koshien/results.csv: {year}{season} 変更なし")
        else:
            lines[hit[0]] = line
            print(f"koshien/results.csv: {year}{season} を更新")
    else:
        lines.append(line)
        print(f"koshien/results.csv: {year}{season} を追記 (優勝 {ch})")
    open(cpath, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")

    spath = os.path.join(ROOT, "data", "koshien", "scores.json")
    scores = json.load(open(spath, encoding="utf-8")) if os.path.exists(spath) else {}
    ent = {"qf": [{"a": g["a"], "as": g["as"], "b": g["b"], "bs": g["bs"]} for g in qf],
           "sf": [{"a": g["a"], "as": g["as"], "b": g["b"], "bs": g["bs"]} for g in sf],
           "f": {"a": fi["a"], "as": fi["as"], "b": fi["b"], "bs": fi["bs"]}}
    key = f"{year}|{season}"
    if scores.get(key) != ent:
        scores[key] = ent
        json.dump(scores, open(spath, "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, indent=1)
        print(f"koshien/scores.json: {key} を更新")


if __name__ == "__main__":
    main()
    fetch_zenkoku_yagura()
    upsert_koshien_results()
