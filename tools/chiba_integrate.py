# -*- coding: utf-8 -*-
"""千葉予選ページをパースして data/chiba/ 用の results.csv / scores.json を生成"""
import os, re, glob, json, io, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_koya import row_cells

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(BASE, "chiba")

_z = "０１２３４５６７８９（）"
_h = "0123456789()"
Z2H = str.maketrans(_z, _h)

def norm(s):
    return s.translate(Z2H)

def kai_to_year(kai):
    return 1914 + kai if kai <= 26 else 1918 + kai

ROUND_LBL = re.compile(r"^[0-9０-９一二三四五１-９]+回戦$")

def parse_chiba(path):
    rows = row_cells(path)
    title = None
    # ヘッダー(第N回…大会)
    for cells in rows[:30]:
        joined = norm("".join(t for _, t in cells))
        m = re.search(r"第(\d+)回(全国高等学校野球選手権|全国中等学校優勝野球)(.*?大会)", joined)
        if m:
            title = m.group(0)
            break
    # ブラケットのヘッダー行
    hdr = None
    for i, cells in enumerate(rows):
        texts = {t for _, t in cells}
        if "決勝" in texts and "準決勝" in texts and ("準々決勝" in texts or "準々" in texts):
            hdr = (i, cells)
            break
    if hdr is None:
        return title, None
    hi, hcells = hdr
    hdr_labels = {t for _, t in hcells if t}
    cols = {}
    for c, t in hcells:
        key = "準々決勝" if t == "準々" else t
        if key in ("決勝", "準決勝", "準々決勝"):
            cols[key] = c
    # レイアウト判定: 旧=決勝が左端(スコアH+1,名前H+3) / 新=決勝が右端(名前H,スコアはHと次列の間)
    new_layout = cols["決勝"] > cols["準々決勝"]
    hdr_cols_sorted = sorted(c for c, t in hcells if t)
    def next_col(hc):
        bigger = [c for c in hdr_cols_sorted if c > hc]
        return bigger[0] if bigger else 10 ** 6
    rounds = {"決勝": [], "準決勝": [], "準々決勝": []}
    for j in range(hi + 1, len(rows)):
        # 次のセクションヘッダー(ヘッダー行に無いN回戦ラベル)に達したら終了
        stop = False
        for _, t in rows[j]:
            if t and ROUND_LBL.fullmatch(norm(t)) and t not in hdr_labels:
                stop = True
                break
        if stop:
            break
        cells = dict(rows[j])
        for rd, hc in cols.items():
            if new_layout:
                nm = cells.get(hc)
                if not nm:
                    continue
                sc = None
                for c2, t2 in rows[j]:
                    if hc < c2 < next_col(hc) and re.fullmatch(r"\d+", norm(t2 or "")):
                        sc = norm(t2)
                if nm and not re.fullmatch(r"\d+", norm(nm)):
                    rounds[rd].append((sc, nm))
            else:
                sc = cells.get(hc + 1)
                nm = cells.get(hc + 3)
                if nm and sc is not None:
                    sc2 = norm(sc)
                    rounds[rd].append((sc2 if re.fullmatch(r"\d+", sc2) else None, nm))
    return title, rounds

def build_record(rounds, warn):
    def pair_games(entries, expect, next_names):
        if len(entries) != expect:
            warn.append(f"想定外の件数 {expect}→{len(entries)}")
        games = []
        for i in range(0, len(entries) - 1, 2):
            (sa, a), (sb, b) = entries[i], entries[i + 1]
            if sa is not None and sb is not None:
                if int(sa) >= int(sb):
                    games.append({"a": a, "as": sa, "b": b, "bs": sb, "noscore": False})
                else:
                    games.append({"a": b, "as": sb, "b": a, "bs": sa, "noscore": False})
            else:
                # 不戦勝など: 次のラウンドに名前がある方を勝者とする
                if a in next_names:
                    games.append({"a": a, "as": "", "b": b, "bs": "", "noscore": True})
                elif b in next_names:
                    games.append({"a": b, "as": "", "b": a, "bs": "", "noscore": True})
                else:
                    warn.append(f"不戦勝の勝者不明: {a} vs {b}")
        return games
    f_names = {nm for _, nm in rounds["決勝"]}
    sf_names = {nm for _, nm in rounds["準決勝"]}
    f = pair_games(rounds["決勝"], 2, set())
    sf = pair_games(rounds["準決勝"], 4, f_names)
    qf = pair_games(rounds["準々決勝"], 8, sf_names)
    if not f or f[0]["noscore"]:
        return None
    fin = f[0]
    b4 = [g["b"] for g in sf]
    b8 = [g["b"] for g in qf]
    def gj(g):
        return {"a": g["a"], "as": g["as"], "b": g["b"], "bs": g["bs"]}
    return {"ch": fin["a"], "ru": fin["b"], "ws": fin["as"], "ls": fin["bs"],
            "b4": b4[:2] + [""] * (2 - len(b4[:2])),
            "b8": b8[:4] + [""] * (4 - len(b8[:4])),
            "scores": {"qf": [gj(g) for g in qf if not g["noscore"]],
                       "sf": [gj(g) for g in sf if not g["noscore"]],
                       "f": gj(fin)}}

def main():
    # 全国データ(koya)の千葉代表を年→校名集合で用意(優勝校の照合用)
    champs_check = {}
    km_path = os.path.join(BASE, "koya_master.json")
    if os.path.exists(km_path):
        km = json.load(open(km_path, encoding="utf-8"))
        for num, obj in km.items():
            meta = obj.get("meta") or {}
            if meta.get("name") != "夏" or not meta.get("year"):
                continue
            names = set()
            for g in obj.get("games", []):
                for side, d in (("a", "da"), ("b", "db")):
                    if "千葉" in (g.get(d) or ""):
                        names.add(g[side])
            if names:
                champs_check[meta["year"]] = names

    records = []
    inventory = []
    for path in sorted(glob.glob(os.path.join(DIR, "*.htm"))):
        name = os.path.basename(path).replace(".htm", "")
        m = re.match(r"(\d+)([ew]?)$", name)
        if not m:
            continue
        kai = int(m.group(1))
        sfx = m.group(2)
        title, rounds = parse_chiba(path)
        inventory.append((kai, sfx, title))
        if not title or rounds is None:
            continue
        if "南関東" in title or "東関東" in title or "北関東" in title or "関東大会" in title:
            continue
        block = "東" if ("東千葉" in title or sfx == "e") else ("西" if ("西千葉" in title or sfx == "w") else "")
        warn = []
        rec = build_record(rounds, warn)
        if rec is None:
            print("SKIP(決勝なし)", name, title)
            continue
        year = kai_to_year(kai)
        rec.update({"year": year, "block": block, "kai": kai})
        if warn:
            print("WARN", year, block, warn)
        # 優勝校を全国データの千葉代表と照合
        chk = champs_check.get(year)
        if chk is not None and not block and rec["ch"] not in chk:
            print(f"CHECK MISMATCH {year}: 優勝 {rec['ch']} が全国データの千葉代表 {sorted(chk)} に見つからない")
        records.append(rec)

    # 除外された(=千葉単独でない)回の一覧
    print("---- 除外・不明ページ ----")
    for kai, sfx, title in sorted(inventory):
        if title and ("南関東" in title or "東関東" in title):
            print(f"第{kai}回{sfx}: {title} → 除外")
        elif not title:
            print(f"第{kai}回{sfx}: タイトル不明 → 除外")

    records.sort(key=lambda r: (r["year"], r["block"]))
    print("採用:", len(records), "大会 / 範囲:", records[0]["year"], "-", records[-1]["year"])

    lines = ["# 千葉単独開催の選手権千葉大会のみ収録(南関東・東関東大会の年は対象外)",
             "# 出典: bibijr.vivian.jp(高校野球データベース)のトーナメント表より集計",
             "年,ブロック,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点"]
    scores = {}
    for r in records:
        cells = [str(r["year"]), r["block"], r["ch"], r["ru"]] + r["b4"] + r["b8"] + [r["ws"], r["ls"]]
        lines.append(",".join(cells))
        scores[f"{r['year']}|{r['block']}"] = r["scores"]
    with open(os.path.join(BASE, "chiba_results.csv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(BASE, "chiba_scores.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(scores, f, ensure_ascii=False, indent=1)
    print("CSV rows:", len(lines) - 3, "/ scores keys:", len(scores))

if __name__ == "__main__":
    main()
