# -*- coding: utf-8 -*-
"""全校トーナメント(ヤグラ)のレイアウト計算。

data/<slug>/yagura.json(都道府県: スロット二分木)または data/koshien/yagura.json
(全国: 勝ち上がり連鎖)から、描画用のパス・座標をすべて計算してJSONを返す。
描画そのもの(SVG生成・アニメーション)は tools/bracket.js のfullモードが行う。

注意: ヤグラのゲーム番号はレベルごとのブロック連番(例: 256枠なら
1回戦=1..128, 2回戦=129..192, …, 準決勝=253-254, 決勝=255)だが、
各ゲームの team1/team2 の並びは子スロットの順序と対応しない。
そのため供給元(どの子ゲームの勝者か)は勝者名の照合で解決する。
"""
import math

ROW_H = 20        # 1校あたりの行高
NAME_W = 150      # 校名欄の幅
COL_W = 46        # 1ラウンドあたりの横幅
CENTER_GAP = 90   # 中央(決勝)の幅
TOP_PAD = 84
BOTTOM_PAD = 30

ROUND_ORDER = ["1回戦", "2回戦", "3回戦", "4回戦", "5回戦", "6回戦",
               "準々決勝", "準決勝", "決勝"]


def _is_num(s):
    return bool(s) and str(s).strip().isdigit()


def _done(g):
    return _is_num(g["as"]) and _is_num(g["bs"]) and int(g["as"]) != int(g["bs"])


def _winner(g):
    return g["a"] if int(g["as"]) > int(g["bs"]) else g["b"]


def build_pref_full(yg):
    """スロット番号方式(chusenflag)の県ヤグラ → 汎用ノード構造"""
    slots = yg.get("slots") or 0
    if slots < 4 or (slots & (slots - 1)) != 0:
        return None
    levels = int(math.log2(slots))
    sizes = [slots >> (i + 1) for i in range(levels)]
    offsets = [sum(sizes[:i]) for i in range(levels)]

    def locate(num):
        for lv in range(levels):
            if offsets[lv] < num <= offsets[lv] + sizes[lv]:
                return lv, num - offsets[lv]
        return None, None

    nodes = {}
    for g in yg["games"]:
        lv, pos = locate(g["num"])
        if lv is None:
            continue
        w = 2 << lv                           # このゲームが覆うリーフ幅(レベル0=2枠)
        leaf_start = (pos - 1) * w + 1
        nodes[(lv, pos)] = {"lv": lv, "pos": pos, "a": g["a"], "b": g["b"],
                            "as": g["as"], "bs": g["bs"], "round": g["round"],
                            "leafStart": leaf_start, "leafW": w,
                            "side": "L" if leaf_start + w - 1 <= slots // 2 else
                                    ("R" if leaf_start > slots // 2 else "C")}
    if not nodes:
        return None
    for node in nodes.values():
        lv, pos = node["lv"], node["pos"]
        node["kids"] = [nodes.get((lv - 1, pos * 2 - 1)), nodes.get((lv - 1, pos * 2))]
        # 子スロットのリーフ開始位置(空きスロットの整列キーに使う)
        half = node["leafW"] // 2
        node["kidLeaf"] = [node["leafStart"], node["leafStart"] + half]
    _resolve_feeds(nodes.values())
    final = max(nodes.values(), key=lambda n: n["lv"])
    return {"nodes": list(nodes.values()), "final": final, "levels": levels}


def _resolve_feeds(nodes):
    """各ゲームのa/bの供給元(子ゲーム or 出場校)を勝者名の照合で決める"""
    for n in nodes:
        kids = n["kids"]
        wins = {}
        for k in kids:
            if k is not None and _done(k):
                wins[_winner(k)] = k
        fa = wins.get(n["a"]) if n["a"] else None
        fb = wins.get(n["b"]) if n["b"] else None
        rem = [k for k in kids if k is not None and k is not fa and k is not fb]
        # 名前で特定できないが子は存在する場合(表記ゆれ・未確定): 残りを割当
        if fa is None and rem and (n["a"] or fb is not None or len(rem) == 2):
            if n["a"] and len(kids) == 2 and kids[0] is not None and kids[1] is not None:
                fa = rem.pop(0)
            elif not n["a"] and rem:
                fa = rem.pop(0)
        if fb is None and rem:
            if (n["b"] and len(kids) == 2 and kids[0] is not None and kids[1] is not None) or not n["b"]:
                fb = rem.pop(0)
        n["feedA"], n["feedB"] = fa, fb
        # 出場校(リーフ)の整列キー: 空いている子スロットのリーフ位置
        used = {id(fa), id(fb)}
        free_leafs = [n["kidLeaf"][i] for i, k in enumerate(kids)
                      if k is None or id(k) not in used]
        n["freeLeafs"] = sorted(free_leafs) if free_leafs else [n.get("leafStart", 0)]


def build_chain_full(yg):
    """全国(甲子園): 1〜3回戦は固定ヤグラ(通し番号のスロット木)。
    準々決勝以降は各試合後の抽選で決まるため、組み合わせが入り次第
    勝者名の連鎖で接続して描画する(未定の間は中央を空けておく)。"""
    SLOT_ROUNDS = ["1回戦", "2回戦", "3回戦"]
    UPPER_ROUNDS = ["準々決勝", "準決勝", "決勝"]
    by_round = {}
    for g in sorted(yg["games"], key=lambda x: x["num"]):
        by_round.setdefault(g["round"], []).append(g)
    lower = [r for r in SLOT_ROUNDS if r in by_round]
    if not lower:
        return None
    counts = [len(by_round[r]) for r in lower]
    # 末尾が倍々になっている区間の先頭を探す(それより下は接続回戦)
    bi = len(counts) - 1
    while bi > 0 and counts[bi - 1] == counts[bi] * 2:
        bi -= 1
    if bi > 1:
        return None
    has_attach = bi == 1
    base_games = by_round[lower[bi]]
    leaf_slots = len(base_games) * 2 * (2 if has_attach else 1)
    slot_levels = int(math.log2(leaf_slots))
    sizes = [leaf_slots >> (i + 1) for i in range(slot_levels)]
    offsets = [sum(sizes[:i]) for i in range(slot_levels)]

    pseudo = []
    base_level = 1 if has_attach else 0
    for li, r in enumerate(lower[bi:]):
        lv = base_level + li
        for j, g in enumerate(by_round[r]):
            pseudo.append(dict(g, num=offsets[lv] + j + 1))
    if has_attach:
        first = by_round[lower[0]]
        base_sides = []
        for j, g in enumerate(base_games):
            base_sides.append(g["a"])
            base_sides.append(g["b"])
        winners = {}
        for g in first:
            if _done(g):
                winners[_winner(g)] = g["num"]
        assigned, used = {}, set()
        for si, nm in enumerate(base_sides):
            if nm and nm in winners:
                assigned[winners[nm]] = si
                used.add(si)
        free = [si for si, nm in enumerate(base_sides) if not nm and si not in used]
        rest = sorted(g["num"] for g in first if g["num"] not in assigned)
        for num, si in zip(rest, free):
            assigned[num] = si
        for g in first:
            si = assigned.get(g["num"])
            if si is not None:
                pseudo.append(dict(g, num=si + 1))

    struct = build_pref_full({"slots": leaf_slots, "games": pseudo})
    if struct is None:
        return None
    nodes = struct["nodes"]
    lower_levels = base_level + len(lower) - bi
    levels = lower_levels + len(UPPER_ROUNDS)   # 準々決勝〜決勝の列は常に確保

    # 勝者名 → 最後に勝ったノード
    last_win = {}
    for n in sorted(nodes, key=lambda x: x["lv"]):
        if _done(n):
            last_win[_winner(n)] = n

    final = None
    seq = 0
    for ui, r in enumerate(UPPER_ROUNDS):
        for g in by_round.get(r, []):
            if not (g["a"] or g["b"]):
                continue
            node = {"lv": lower_levels + ui, "a": g["a"], "b": g["b"],
                    "as": g["as"], "bs": g["bs"], "round": r,
                    "feedA": last_win.get(g["a"]) if g["a"] else None,
                    "feedB": last_win.get(g["b"]) if g["b"] else None,
                    "freeLeafs": [], "seq": 10000 + seq}
            seq += 1
            if r == "決勝":
                node["side"] = "C"
                final = node
            else:
                fa, fb = node["feedA"], node["feedB"]
                node["side"] = (fa or fb or {}).get("side", "L")
            nodes.append(node)
            if _done(node):
                last_win[_winner(node)] = node
    return {"nodes": nodes, "final": final, "levels": levels}


def layout(struct, rank_of=None):
    """ノード構造 → 描画データ(teams/blacks/reds/scores/中央)"""
    nodes = struct["nodes"]
    levels = struct["levels"]
    final = struct["final"]

    # 出場校(リーフ)の収集: フィードが無い側の非空チーム名
    teams = {"L": [], "R": []}
    seen = set()
    for n in sorted(nodes, key=lambda x: (x["lv"], x.get("leafStart", x.get("seq", 0)))):
        free = list(n["freeLeafs"])
        for which, f in (("a", n["feedA"]), ("b", n["feedB"])):
            name = n[which]
            if f is not None or not name or name in seen:
                continue
            key = free.pop(0) if free else n.get("leafStart", 0)
            seen.add(name)
            side = n["side"]
            if side == "C":
                side = "L" if which == "a" else "R"
            teams[side].append({"name": name, "key": key})
    for side in ("L", "R"):
        teams[side].sort(key=lambda t: t["key"])

    rows = max(len(teams["L"]), len(teams["R"]), 1)
    H = TOP_PAD + rows * ROW_H + BOTTOM_PAD
    W = 2 * (NAME_W + COL_W * levels) + CENTER_GAP
    XC = W / 2

    def col_x(side, lv):
        return NAME_W + (lv + 1) * COL_W if side == "L" else W - NAME_W - (lv + 1) * COL_W

    ty = {}
    out_teams = []
    for side in ("L", "R"):
        for i, t in enumerate(teams[side]):
            y = TOP_PAD + i * ROW_H
            ty[t["name"]] = (side, y)
            out_teams.append({"n": t["name"], "x": 8 if side == "L" else W - 8,
                              "y": y, "an": "start" if side == "L" else "end"})

    blacks, reds, scores = [], [], []
    center = {}

    def seg(x1, y1, x2, y2):
        return f"M{round(x1, 1)} {round(y1, 1)} L{round(x2, 1)} {round(y2, 1)}"

    def feed_xy(n, which):
        f = n["feedA"] if which == "a" else n["feedB"]
        if f is not None and "jy" in f:
            return f["jx"], f["jy"]
        name = n[which]
        if name in ty:
            side, y = ty[name]
            return (NAME_W if side == "L" else W - NAME_W), y
        return None, None

    for n in sorted(nodes, key=lambda x: x["lv"]):
        if final is not None and n is final:
            continue
        side = n["side"]
        if side == "C":
            continue
        ax, ay = feed_xy(n, "a")
        bx, by = feed_xy(n, "b")
        jx = col_x(side, n["lv"])
        if ay is not None:
            blacks.append({"d": seg(ax, ay, jx, ay), "lv": n["lv"]})
        if by is not None:
            blacks.append({"d": seg(bx, by, jx, by), "lv": n["lv"]})
        if ay is None or by is None:
            continue
        jy = (ay + by) / 2
        n["jx"], n["jy"] = jx, jy
        blacks.append({"d": seg(jx, ay, jx, by), "lv": n["lv"]})
        if _done(n):
            wtop = int(n["as"]) > int(n["bs"])
            wx, wy = (ax, ay) if wtop else (bx, by)
            nxt = col_x(side, n["lv"] + 1) if n["lv"] + 1 < levels else \
                (XC - CENTER_GAP / 2 if side == "L" else XC + CENTER_GAP / 2)
            reds.append({"d": f"M{round(wx, 1)} {round(wy, 1)} L{jx} {round(wy, 1)} "
                              f"L{jx} {round(jy, 1)} L{round(nxt, 1)} {round(jy, 1)}",
                         "lv": n["lv"]})
            scores.append({"x": jx, "y": round(jy - 5, 1), "a": int(n["as"]),
                           "b": int(n["bs"]), "w": 0 if wtop else 1, "lv": n["lv"]})

    if final is not None:
        ax, ay = feed_xy(final, "a")
        bx, by = feed_xy(final, "b")
        if ay is not None and by is not None:
            cy = (ay + by) / 2
            pole_top = TOP_PAD - 34
            blacks.append({"d": seg(ax, ay, XC, ay), "lv": final["lv"]})
            blacks.append({"d": seg(bx, by, XC, by), "lv": final["lv"]})
            if abs(ay - by) > 0.5:
                blacks.append({"d": seg(XC, ay, XC, by), "lv": final["lv"]})
            blacks.append({"d": seg(XC, min(ay, by), XC, pole_top), "lv": final["lv"]})
            center = {"x": XC, "cy": round(cy, 1), "poleTop": pole_top}
            if _done(final):
                a_wins = int(final["as"]) > int(final["bs"])
                wx, wy = (ax, ay) if a_wins else (bx, by)
                reds.append({"d": f"M{round(wx, 1)} {round(wy, 1)} L{XC} {round(wy, 1)} "
                                  f"L{XC} {pole_top}", "lv": final["lv"]})
                center["score"] = {"a": int(final["as"]), "b": int(final["bs"]),
                                   "w": 0 if a_wins else 1}
                center["champion"] = _winner(final)

    losers = set()
    for n in nodes:
        if _done(n):
            losers.add(n["b"] if int(n["as"]) > int(n["bs"]) else n["a"])
    for t in out_teams:
        if t["n"] in losers:
            t["out"] = 1

    return {"type": "full", "W": round(W), "H": round(H), "levels": levels,
            "nameW": NAME_W, "rowH": ROW_H,
            "teams": out_teams, "blacks": blacks, "reds": reds,
            "scores": scores, "center": center}


def build_full(yg, kind, rank_of=None):
    struct = build_pref_full(yg) if kind == "pref" else build_chain_full(yg)
    if struct is None:
        return None
    return layout(struct, rank_of)
