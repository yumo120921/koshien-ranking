# -*- coding: utf-8 -*-
"""アプリ(app_template.html)のランキング計算エンジンのPython移植。

対話型アプリ内のJS実装(zH/nM/BH/FH/tM/n1)と同じ結果を返すことを目的とし、
ビルド時の静的な順位付け(トーナメントタブの注記など)に使う。
検証: tools/live_update.py 等とは独立。レンダリング済みページとの一致テスト済み。
"""
import json
import math
import os
import re


def _round_js(x):
    """JSのMath.round(0.5は正の無限大方向)"""
    return math.floor(x + 0.5)


def make_alias_fn(aliases):
    """n1相当: 別名の連鎖を解決する関数を返す"""
    m = {a["from"]: a["to"] for a in aliases}

    def t(name):
        name = (name or "").strip()
        seen = set()
        while name in m and name not in seen:
            seen.add(name)
            name = m[name]
        return name
    return t


def _row_data(row, scores_entry, t):
    """tM相当: 1大会分の levels / wins / champion を返す"""
    levels = {}
    wins = []

    def bump(name, lv):
        if name:
            levels[name] = max(levels.get(name, 0), lv)

    if scores_entry:  # 対戦モード(jH)
        th = scores_entry

        def w(g):
            return g["a"] if int(g["as"]) > int(g["bs"]) else g["b"]

        def l(g):
            return g["b"] if int(g["as"]) > int(g["bs"]) else g["a"]

        for g in th["qf"]:
            bump(t(l(g)), 1)
        for g in th["sf"]:
            bump(t(l(g)), 2)
        bump(t(l(th["f"])), 3)
        bump(t(w(th["f"])), 4)
        for g in th["qf"] + th["sf"] + [th["f"]]:
            wins.append({"winner": t(w(g)), "loser": t(l(g)),
                         "margin": abs(int(g["as"]) - int(g["bs"]))})
        return {"levels": levels, "wins": wins, "champion": t(w(th["f"])), "partial": False}

    # 成績のみモード(LH)
    names = [(row["ch"], 4), (row["ru"], 3)] + \
        [(x, 2) for x in row["b4"]] + [(x, 1) for x in row["b8"]]
    names = [(n, lv) for n, lv in names if (n or "").strip()]
    for n, lv in names:
        bump(t(n), lv)
    champion = None
    if (row["ch"] or "").strip():
        champion = t(row["ch"])
        ws, ls = (row["ws"] or "").strip(), (row["ls"] or "").strip()
        has_ru = bool((row["ru"] or "").strip())
        if ws.isdigit() and ls.isdigit():
            wins.append({"winner": champion, "loser": t(row["ru"]) if has_ru else "",
                         "margin": int(ws) - int(ls)})
        elif has_ru:
            wins.append({"winner": champion, "loser": t(row["ru"]), "margin": None})
    return {"levels": levels, "wins": wins, "champion": champion,
            "partial": len(names) < 8}


def _nm(schools, year_nums):
    """nM相当: 継続の失効処理と合計・並び替え"""
    if not year_nums:
        return []
    last = year_nums[-1]
    idx = {y: i for i, y in enumerate(year_nums)}
    table = []
    for sc in schools:
        per = sc["perYear"]
        if not per:
            continue
        d = {p["year"]: p for p in per}
        base = sum(p["base"] for p in per)
        margin = sum(p["margin"] for p in per)
        upset = sum(p["upset"] for p in per)
        champs = sum(1 for p in per if p["level"] == 4)
        cont = 0
        if last in d:
            b = idx[last]
            while b >= 0 and year_nums[b] in d:
                cont += d[year_nums[b]]["cont"]
                b -= 1
        table.append({"school": sc["school"], "base": base, "margin": margin,
                      "upset": upset, "cont": cont, "champs": champs,
                      "total": base + margin + upset + cont})
    # JSのlocaleCompare(ja)は完全再現できないが、同点同優勝数の並びのみに影響
    table.sort(key=lambda c: (-c["total"], -c["champs"], c["school"]))
    return table


def compute_full(rows, scores, params, aliases):
    """zH相当。rows: parse_results_csvの行(block込み)。scoresキーは "年|ブロック"。"""
    t = make_alias_fn(aliases)
    excluded = set()
    for tok in re.split(r"[,、\s]+", str(params.get("excluded", ""))):
        if tok.strip().isdigit():
            excluded.add(int(tok))

    groups = {}
    for row in rows:
        if not str(row["year"]).isdigit():
            continue
        y = int(row["year"])
        if y in excluded:
            continue
        key = f"{row['year']}|{row.get('block', '')}"
        d = _row_data(row, scores.get(key), t)
        if not d["levels"]:
            continue
        g = groups.setdefault(y, {"levels": {}, "wins": [], "champions": []})
        for n, lv in d["levels"].items():
            g["levels"][n] = max(g["levels"].get(n, 0), lv)
        g["wins"].extend(d["wins"])
        if d["champion"] and d["champion"] not in g["champions"]:
            g["champions"].append(d["champion"])

    years = sorted(groups)
    per_school = {}
    dcum, pcont, hlast, mstreak = {}, {}, {}, {}
    lv_pts = [0, params["pB8"], params["pB4"], params["pRU"], params["pCH"]]

    def prev_year(v):
        g = v - 1
        while g in excluded:
            g -= 1
        return g

    for v in years:
        g = groups[v]
        x = prev_year(v)
        E = groups.get(x)
        standings = sorted(
            ([T, dcum[T] + (pcont.get(T, 0) if hlast.get(T) == x else 0)]
             for T in dcum),
            key=lambda kv: -kv[1])
        standings = [(T, tot) for T, tot in standings if tot > 0]
        O = {T: i + 1 for i, (T, _) in enumerate(standings)}
        I = len(standings)
        L = {}
        for T, H in g["levels"].items():
            base = lv_pts[H]
            mywins = [w for w in g["wins"] if w["winner"] == T]
            mm = sum(min(w["margin"], params["cap"]) for w in mywins
                     if w["margin"] is not None)
            margin = min(mm, params["mcap"] if params["mcap"] > 0 else float("inf"))
            cont = 0
            if E:
                R = E["levels"].get(T, 0)
                cont = params["wc"] * R * H if R > 0 else 0
            if H == 4:
                rec = mstreak.get(T)
                P = rec["n"] + 1 if rec and rec["year"] == x else 1
                mstreak[T] = {"year": v, "n": P}
                if E and P >= 3:
                    cont += params["streak"] * (P - 2)
            k = 0
            if I > 0:
                R = O.get(T, I + 1)
                for w in mywins:
                    K = O.get(w["loser"], I + 1)
                    if K < R:
                        q = _round_js(min(params["uu"] * math.log2(R / K), params["ucap"]))
                        if q > 0:
                            k += q
            upset = min(k, params["utcap"]) if params["utcap"] > 0 else k
            per_school.setdefault(T, {"school": T, "perYear": []})["perYear"].append(
                {"year": v, "level": H, "base": base, "margin": margin,
                 "cont": cont, "upset": upset})
            L[T] = {"hard": base + margin + upset, "cont": cont}
        for T, val in L.items():
            if hlast.get(T) != x:
                pcont[T] = 0
            pcont[T] = pcont.get(T, 0) + val["cont"]
            dcum[T] = dcum.get(T, 0) + val["hard"]
            hlast[T] = v

    return {"schools": per_school, "years": years, "params": params}


def window_table(full, n):
    """FH+nM相当。n<=0または全期間以上なら全期間"""
    years = full["years"]
    params = full["params"]
    if not n or n <= 0 or n >= len(years):
        win_years = years
        zm = zn = 1.0
    else:
        win_years = years[-n:]
        zm = min(1, n / params["uwin"]) if params["uwin"] > 0 else 1
        zn = min(1, n / params["cwin"]) if params["cwin"] > 0 else 1
    wset = set(win_years)
    schools = []
    for sc in full["schools"].values():
        per = [p for p in sc["perYear"] if p["year"] in wset]
        if zm < 1 or zn < 1:
            per = [
                (dict(p,
                      upset=_round_js(p["upset"] * zm) if zm < 1 else p["upset"],
                      cont=_round_js(p["cont"] * zn) if zn < 1 else p["cont"])
                 if (p["upset"] > 0 or p["cont"] > 0) else p)
                for p in per]
        if per:
            schools.append({"school": sc["school"], "perYear": per})
    return _nm(schools, win_years)


def ranks(table, defunct=None, as_of=None):
    """BH相当+消滅校除外。{学校: (順位, 合計点)}"""
    rows = table
    if defunct:
        rows = [r for r in table
                if not (r["school"] in defunct and (as_of is None or defunct[r["school"]] <= as_of))]
    out = {}
    prev_total, prev_rank = None, 0
    for i, r in enumerate(rows):
        rank = prev_rank if r["total"] == prev_total else i + 1
        out[r["school"]] = (rank, r["total"])
        prev_total, prev_rank = r["total"], rank
    return out
