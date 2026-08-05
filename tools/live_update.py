# -*- coding: utf-8 -*-
"""夏の地方大会の速報データを取得し、当年の行を各県のデータに反映する。

データ源: 朝日新聞デジタル「バーチャル高校野球」(vk.sportsbull.jp)の
試合データJSON(JSONP)。試合が終了した準々決勝以降のみを反映する。
- 準々決勝の敗者 → ベスト8 / 準決勝の敗者 → ベスト4 / 決勝 → 優勝・準優勝+得点
- 準々決勝4+準決勝2+決勝が揃い整合検証を通ったら scores.json にも出力
  (揃うまでは「成績のみモード」の部分行として集計される)
実行: python tools/live_update.py   (毎日1回、GitHub Actionsから)
"""
import io
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIST_URL = "https://vk.sportsbull.jp/koshien/all-games/"
JSON_BASE = "https://www.asahicom.jp/koshien/contents/virtualbaseball/site/chihou_game_day"
UA = {"User-Agent": "Mozilla/5.0 (koshien-ranking.com data sync; once daily)"}
DELAY = 0.4

# 速報側のブロックID → 当サイトのデータslug(記載なしはID=slug)
SLUG_MAP = {
    "nhokkaido": "kitahokkaido",
    "shokkaido": "minamihokkaido",
    "etokyo": "higashitokyo",
    "wtokyo": "nishitokyo",
}
# 速報側の校名表記 → 当サイトの表記(略記・字体ゆれの正規化。実際の改称はaliases.csvで扱う)
NAME_MAP = {
    "霞ケ浦": "霞ヶ浦",
    "東北学院榴ケ岡": "東北学院榴ヶ岡",
    "関東第一": "関東一",        # 正式名は関東第一だが当サイトの歴史データは関東一表記
    "駒大": "駒大高",            # 駒澤大学高(西東京)
    "大商大": "大商大高",
    "常磐大": "常磐大高",
    "エナジックスポーツ": "エナジック",
    "梼原": "檮原",
}

JST = timezone(timedelta(hours=9))
HDR = "年,ブロック,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点"


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def get_jsonp(url):
    d = get(url)
    m = re.search(r"\((.*)\)\s*;?\s*$", d, re.S)
    return json.loads(m.group(1) if m else d)


def scores_valid(th):
    """アプリの対戦モード検証(jH)と同等のチェック(pref_integrate.pyと同じ)"""
    if len(th.get("qf", [])) != 4 or len(th.get("sf", [])) != 2 or not th.get("f"):
        return False
    games = th["qf"] + th["sf"] + [th["f"]]
    for g in games:
        if not str(g.get("a", "")).strip() or not str(g.get("b", "")).strip():
            return False
        try:
            a, b = int(g["as"]), int(g["bs"])
        except (ValueError, TypeError):
            return False
        if a == b or g["a"].strip() == g["b"].strip():
            return False
    w = lambda g: g["a"] if int(g["as"]) > int(g["bs"]) else g["b"]
    qfw = [w(g) for g in th["qf"]]
    if not all(x in qfw for x in (th["sf"][0]["a"], th["sf"][0]["b"], th["sf"][1]["a"], th["sf"][1]["b"])):
        return False
    if not all(x in [w(g) for g in th["sf"]] for x in (th["f"]["a"], th["f"]["b"])):
        return False
    allqf = [g["a"].strip() for g in th["qf"]] + [g["b"].strip() for g in th["qf"]]
    return len(set(allqf)) == 8


def fetch_blocks():
    """開催ブロック一覧(ID, 表示名)をナビから読む(記念大会の分割も自動で現れる)"""
    d = get(LIST_URL)
    pairs = re.findall(
        r'<li class="([a-z0-9]+)"><a href="/koshien/[a-z0-9]+/">\s*'
        r'<span class="prefName">([^<]+)</span>', d)
    seen, out = set(), []
    for bid, name in pairs:
        if bid not in seen:
            seen.add(bid)
            out.append((bid, name.strip()))
    return out


def fetch_block_games(bid, year, today):
    """終了済みの準々決勝以降の試合を返す: {round: [game...]}"""
    days = get_jsonp(f"{JSON_BASE}/chihou_game_days_{bid}.json")
    time.sleep(DELAY)
    ymd_list = []
    for ent in days.get("result", {}).get("info", []):
        if int(ent.get("year", 0)) != year:
            continue
        m = int(ent["month"])
        for dd in ent.get("date", []):
            ymd = f"{year}{m:02d}{int(dd['day']):02d}"
            if ymd <= today:
                ymd_list.append(ymd)
    games = {}  # (round, frozenset(pair)) -> game (後の日付を優先=再試合対応)
    for ymd in ymd_list:
        try:
            day = get_jsonp(f"{JSON_BASE}/chihou_game_day_{ymd}_{bid}.json")
        except Exception:
            time.sleep(DELAY)
            continue
        time.sleep(DELAY)
        for info in day.get("result", {}).get("info", []):
            for g in info.get("game_list", []):
                rd = (g.get("round_name") or "").strip()
                if rd not in ("準々決勝", "準決勝", "決勝"):
                    continue
                if str(g.get("status_id")) != "3":  # 3=試合終了のみ採用
                    continue
                a = NAME_MAP.get(g.get("school_name1", "").strip(), g.get("school_name1", "").strip())
                b = NAME_MAP.get(g.get("school_name2", "").strip(), g.get("school_name2", "").strip())
                try:
                    sa, sb = int(g.get("score_sum1")), int(g.get("score_sum2"))
                except (TypeError, ValueError):
                    continue
                if not a or not b or a == b or sa == sb:
                    continue
                if sa < sb:
                    a, b, sa, sb = b, a, sb, sa
                games[(rd, frozenset((a, b)))] = {
                    "round": rd, "a": a, "as": str(sa), "b": b, "bs": str(sb), "ymd": ymd}
    out = {"準々決勝": [], "準決勝": [], "決勝": []}
    for g in sorted(games.values(), key=lambda x: x["ymd"]):
        out[g["round"]].append(g)
    return out


def fetch_yagura(bid, slug, year):
    """組み合わせヤグラ(全校分)を取得して data/<slug>/yagura.json に保存。変更があればTrue"""
    try:
        j = get_jsonp(f"https://www.asahicom.jp/koshien/contents/virtualbaseball/site/chihou_yagura_info/{bid}.json")
    except Exception:
        return False
    time.sleep(DELAY)
    res = j.get("result") or []
    if not res or j.get("status") != "OK":
        return False
    r = res[0]
    games = []
    for side in (r.get("game") or {}).values():
        for g in side:
            a = NAME_MAP.get((g.get("team1") or "").strip(), (g.get("team1") or "").strip())
            b = NAME_MAP.get((g.get("team2") or "").strip(), (g.get("team2") or "").strip())
            if not a and not b:
                continue
            games.append({"num": int(g["num"]), "round": (g.get("round") or "").strip(),
                          "a": a, "b": b,
                          "as": (g.get("score1") or "").strip(), "bs": (g.get("score2") or "").strip()})
    if not games:
        return False
    out = {"year": year, "slots": int(r.get("chusenflag") or 0),
           "team_count": int(r.get("team") or 0), "games": sorted(games, key=lambda x: x["num"])}
    path = os.path.join(ROOT, "data", slug, "yagura.json")
    old = None
    if os.path.exists(path):
        try:
            old = json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    if out != old:
        json.dump(out, open(path, "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, separators=(",", ":"))
        return True
    return False


def known_names(slug):
    names = set()
    p = os.path.join(ROOT, "data", slug, "results.csv")
    for line in open(p, encoding="utf-8"):
        if line.startswith("#") or line.startswith("年"):
            continue
        for nm in line.rstrip("\n").split(",")[2:10]:
            if nm:
                names.add(nm)
    ap = os.path.join(ROOT, "data", slug, "aliases.csv")
    if os.path.exists(ap):
        for line in open(ap, encoding="utf-8"):
            for nm in line.rstrip("\n").split(","):
                names.add(nm.strip())
    return names


def upsert(slug, year, rounds):
    """results.csv の当年行と scores.json を更新。変更があれば True"""
    f = rounds["決勝"][0] if rounds["決勝"] else None
    b4 = [g["b"] for g in rounds["準決勝"]][:2]
    b8 = [g["b"] for g in rounds["準々決勝"]][:4]
    cells = [str(year), "",
             f["a"] if f else "", f["b"] if f else ""] + \
        b4 + [""] * (2 - len(b4)) + b8 + [""] * (4 - len(b8)) + \
        [f["as"] if f else "", f["bs"] if f else ""]
    if not any(cells[2:10]):
        return False
    row = ",".join(cells)

    path = os.path.join(ROOT, "data", slug, "results.csv")
    lines = open(path, encoding="utf-8").read().rstrip("\n").split("\n")
    out, replaced, changed = [], False, False
    for line in lines:
        c = line.split(",")
        if not line.startswith("#") and not line.startswith("年") \
                and c[0] == str(year) and len(c) > 1 and c[1] == "":
            if line != row:
                changed = True
            out.append(row)
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(row)
        changed = True
    if changed:
        with open(path, "w", encoding="utf-8", newline="\n") as fp:
            fp.write("\n".join(out) + "\n")

    # スコア詳細(完全に揃った場合のみ)
    th = {"qf": [{"a": g["a"], "as": g["as"], "b": g["b"], "bs": g["bs"]} for g in rounds["準々決勝"]],
          "sf": [{"a": g["a"], "as": g["as"], "b": g["b"], "bs": g["bs"]} for g in rounds["準決勝"]],
          "f": {"a": f["a"], "as": f["as"], "b": f["b"], "bs": f["bs"]} if f else None}
    if scores_valid(th):
        sp = os.path.join(ROOT, "data", slug, "scores.json")
        sc = json.load(open(sp, encoding="utf-8"))
        key = f"{year}|"
        if sc.get(key) != th:
            sc[key] = th
            json.dump(sc, open(sp, "w", encoding="utf-8", newline="\n"),
                      ensure_ascii=False, indent=1)
            changed = True
    return changed


def main():
    now = datetime.now(JST)
    year, today = now.year, now.strftime("%Y%m%d")
    print(f"live_update {now:%Y-%m-%d %H:%M} JST / 対象年={year}")
    blocks = fetch_blocks()
    time.sleep(DELAY)
    print(f"開催ブロック: {len(blocks)}")
    changed_any = []
    for bid, bname in blocks:
        slug = SLUG_MAP.get(bid, bid)
        if not os.path.isdir(os.path.join(ROOT, "data", slug)):
            print(f"WARN 未対応ブロック {bid}({bname}) → data/{slug} が無いためスキップ")
            continue
        try:
            rounds = fetch_block_games(bid, year, today)
        except Exception as e:
            print(f"WARN {bid}({bname}) 取得失敗: {type(e).__name__}: {e}")
            continue
        n = sum(len(v) for v in rounds.values())
        if n == 0:
            if fetch_yagura(bid, slug, year):
                changed_any.append(slug + "(ヤグラ)")
            continue
        kn = known_names(slug)
        for v in rounds.values():
            for g in v:
                for nm in (g["a"], g["b"]):
                    if nm not in kn:
                        print(f"NOTE {bname}: 未知の校名「{nm}」(新規校なら正常。表記ゆれならNAME_MAPかaliases.csvに追加)")
        yg = fetch_yagura(bid, slug, year)
        if yg:
            changed_any.append(slug + "(ヤグラ)")
        if upsert(slug, year, rounds):
            fin = rounds["決勝"]
            state = f"優勝 {fin[0]['a']}" if fin else \
                f"QF{len(rounds['準々決勝'])}/SF{len(rounds['準決勝'])} 終了"
            print(f"UPDATE {bname}({slug}): {state}")
            changed_any.append(slug)
    print(f"更新: {len(changed_any)}ブロック" + (f" → {' '.join(changed_any)}" if changed_any else "(変更なし)"))


if __name__ == "__main__":
    main()
