# -*- coding: utf-8 -*-
"""全ページをパースして results.csv / scores.json を生成し、既存CSVと照合する"""
import os, re, glob, json, io, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_koya import row_cells

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(BASE, "koya")
REPO = r"D:\WEBSITES\HighschoolBaseballDatabase"

ROUNDS = {"1回戦", "2回戦", "3回戦", "準々決勝", "準々", "準決勝", "決勝",
          "１回戦", "２回戦", "３回戦"}

# 全角→半角(数字・英字・記号)
_z = "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ（）－"
_h = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz()-"
Z2H = str.maketrans(_z, _h)

def norm(s):
    return s.translate(Z2H)

def parse_page(path):
    rows = row_cells(path)
    meta = {"kai": None, "name": None, "year": None}
    games = []
    for cells in rows:
        texts = [norm(t) for _, t in cells]
        joined = "".join(texts)
        if meta["year"] is None and any(k in joined for k in ("選抜", "選手権", "優勝野球")):
            m = re.search(r"第(\d+)回", joined)
            y = re.search(r"(19\d\d|20\d\d)", joined)
            if m and y and "出場" in joined:
                meta["kai"] = int(m.group(1))
                meta["name"] = "春" if "選抜" in joined else "夏"
                meta["year"] = int(y.group(1))
        if texts and texts[0] in ROUNDS and len(texts) >= 5:
            try:
                seq = texts[1:]
                da = seq[0] if seq[0].startswith("(") else None
                i = 1 if da else 0
                team_a = seq[i]; i += 1
                sa = seq[i]; i += 1
                if i < len(seq) and seq[i] == "-": i += 1
                sb = seq[i]; i += 1
                team_b = seq[i]; i += 1
                db = seq[i] if i < len(seq) and seq[i].startswith("(") else None
                if not (re.fullmatch(r"\d+", sa) and re.fullmatch(r"\d+", sb)):
                    continue
                rd = texts[0].replace("１", "1").replace("２", "2").replace("３", "3")
                if rd == "準々":
                    rd = "準々決勝"
                games.append({"round": rd, "a": team_a, "as": sa, "b": team_b, "bs": sb,
                              "da": (da or "").strip("()"), "db": (db or "").strip("()")})
            except (IndexError, ValueError):
                continue
    return meta, games

def pref_of(district):
    """地区表記から都道府県(最後の・区切り)を取る。中黒は全角・半角・カナ中点に対応"""
    if not district:
        return ""
    return re.split(r"[・･·]", district)[-1]

def build_record(meta, games, warn):
    """1大会分のレコード: 優勝/準優勝/B4/B8(県付き) + scores"""
    def decisive(rd):
        return [g for g in games if g["round"] == rd and g["as"] != g["bs"]]
    finals = decisive("決勝")
    sfs = decisive("準決勝")
    qfs = decisive("準々決勝")
    if len(finals) != 1:
        warn.append(f"決勝が{len(finals)}試合")
        if not finals:
            return None
    f = finals[-1]
    win, lose = (("a", "b") if int(f["as"]) > int(f["bs"]) else ("b", "a"))
    ch = (f[win], pref_of(f["d" + win]))
    ru = (f[lose], pref_of(f["d" + lose]))
    if len(sfs) != 2:
        warn.append(f"準決勝が{len(sfs)}試合")
    b4 = []
    for g in sfs:
        l = "b" if int(g["as"]) > int(g["bs"]) else "a"
        if g[l] not in (ch[0], ru[0]):
            b4.append((g[l], pref_of(g["d" + l])))
    if len(qfs) not in (0, 4):
        warn.append(f"準々決勝が{len(qfs)}試合")
    b8 = []
    for g in qfs:
        l = "b" if int(g["as"]) > int(g["bs"]) else "a"
        b8.append((g[l], pref_of(g["d" + l])))
    def game_json(g):
        # 勝者をaに揃える
        if int(g["as"]) >= int(g["bs"]):
            return {"a": g["a"], "as": g["as"], "b": g["b"], "bs": g["bs"]}
        return {"a": g["b"], "as": g["bs"], "b": g["a"], "bs": g["as"]}
    scores = {"qf": [game_json(g) for g in qfs],
              "sf": [game_json(g) for g in sfs],
              "f": game_json(f)}
    return {"year": meta["year"], "season": meta["name"],
            "ch": ch, "ru": ru, "b4": b4[:2], "b8": b8[:4],
            "ws": f[win + "s"], "ls": f[lose + "s"], "scores": scores}

def fmt(name_pref):
    return f"{name_pref[0]}({name_pref[1]})" if name_pref[1] else name_pref[0]

def main():
    records = {}
    for path in sorted(glob.glob(os.path.join(DIR, "*.htm"))):
        meta, games = parse_page(path)
        if meta["year"] is None or not games:
            continue
        warn = []
        rec = build_record(meta, games, warn)
        if rec is None:
            print("SKIP", os.path.basename(path), meta, warn)
            continue
        key = (rec["year"], rec["season"])
        if key in records:
            print("DUP", key, os.path.basename(path))
            continue
        rec["warn"] = warn
        records[key] = rec
        if warn:
            print("WARN", key, warn)

    print("tournaments parsed:", len(records))
    yrs = sorted({y for y, _ in records})
    print("range:", yrs[0], "-", yrs[-1])

    # ---- 既存CSVと照合 ----
    old = {}
    with open(os.path.join(REPO, "data", "koshien", "results.csv"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("年"):
                continue
            c = line.split(",")
            old[(int(c[0]), c[1])] = c

    diffs = []
    for key, c in sorted(old.items()):
        if key not in records:
            diffs.append(f"{key}: サイトにデータなし(既存維持)")
            continue
        r = records[key]
        new_cells = [str(r["year"]), r["season"], fmt(r["ch"]), fmt(r["ru"])]
        b4 = [fmt(x) for x in r["b4"]] + ["", ""]
        b8 = [fmt(x) for x in r["b8"]] + ["", "", "", ""]
        new_cells += b4[:2] + b8[:4] + [r["ws"], r["ls"]]
        # 順不同の列(B4, B8)はセットで比較
        def names(cells, i, j):
            return {re.sub(r"\(.*?\)", "", x) for x in cells[i:j] if x}
        prob = []
        for label, i, j in [("優勝", 2, 3), ("準優勝", 3, 4)]:
            if re.sub(r"\(.*?\)", "", c[i]) != re.sub(r"\(.*?\)", "", new_cells[i]):
                prob.append(f"{label}: {c[i]} → {new_cells[i]}")
        if names(c, 4, 6) != names(new_cells, 4, 6):
            prob.append(f"B4: {c[4:6]} → {new_cells[4:6]}")
        if names(c, 6, 10) != names(new_cells, 6, 10):
            prob.append(f"B8: {c[6:10]} → {new_cells[6:10]}")
        if (c[10], c[11]) != (r["ws"], r["ls"]):
            prob.append(f"決勝スコア: {c[10]}-{c[11]} → {r['ws']}-{r['ls']}")
        if prob:
            diffs.append(f"{key}: " + " / ".join(prob))

    print("---- 照合結果(既存CSVとの差分) ----")
    for d in diffs:
        print(d)

    # ---- 出力 ----
    lines = ["# 学校名は大会当時の名称で記録する。改名前後の同一校は aliases.csv に「旧名,現名」を登録すると",
             "# ランキング上は同一校として合算され、最新の校名で表示される(例: 光星学院→八戸学院光星)",
             "# 出典: bibijr.vivian.jp(高校野球データベース)のトーナメント表より集計",
             "年,大会,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点"]
    all_keys = sorted(set(list(records.keys()) + list(old.keys())),
                      key=lambda k: (k[0], 0 if k[1] == "春" else 1))
    for key in all_keys:
        if key in records:
            r = records[key]
            b4 = [fmt(x) for x in r["b4"]] + ["", ""]
            b8 = [fmt(x) for x in r["b8"]] + ["", "", "", ""]
            cells = [str(r["year"]), r["season"], fmt(r["ch"]), fmt(r["ru"])] + b4[:2] + b8[:4] + [r["ws"], r["ls"]]
        else:
            cells = old[key]
        lines.append(",".join(cells))
    with open(os.path.join(BASE, "results_new.csv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    scores = {f"{y}|{s}": records[(y, s)]["scores"] for (y, s) in sorted(records)}
    with open(os.path.join(BASE, "scores_new.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(scores, fh, ensure_ascii=False, indent=1)

    print("CSV rows:", len(lines) - 4, "/ scores keys:", len(scores))

    # 新出の校名一覧(エイリアス検討用)
    known = set()
    for c in old.values():
        for x in c[2:10]:
            if x:
                known.add(re.sub(r"\(.*?\)", "", x))
    new_names = set()
    for r in records.values():
        for np in [r["ch"], r["ru"]] + r["b4"] + r["b8"]:
            if np[0] not in known:
                new_names.add(np[0])
    print("---- 新出の校名(", len(new_names), ") ----")
    print("、".join(sorted(new_names)))

if __name__ == "__main__":
    main()
