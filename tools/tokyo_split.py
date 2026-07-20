# -*- coding: utf-8 -*-
"""東京の抽出結果を東東京・西東京の2データセットに分割する。
1973年以前(東西分離前)の東京大会は両方に含める(ユーザー指定)。"""
import io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))

HDR = "年,ブロック,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点"
COMMENTS = {
    "東": ["# 東東京: 1974年以降の選手権東東京大会 + 1973年以前の東京大会(東西共通で両ランキングに算入)",
           "# 単独開催のみ収録(関東・京浜・神静・甲神静・南関東大会の年は対象外)。1923-30年はリーグ戦等のため優勝(・準優勝)のみ",
           "# 出典: bibijr.vivian.jp(高校野球データベース)のトーナメント表より集計"],
    "西": ["# 西東京: 1974年以降の選手権西東京大会 + 1973年以前の東京大会(東西共通で両ランキングに算入)",
           "# 単独開催のみ収録(関東・京浜・神静・甲神静・南関東大会の年は対象外)。1923-30年はリーグ戦等のため優勝(・準優勝)のみ",
           "# 出典: bibijr.vivian.jp(高校野球データベース)のトーナメント表より集計"],
}
OUTDIR = {"東": "higashitokyo", "西": "nishitokyo"}

rows = []
for line in open(os.path.join(BASE, "tokyo_results.csv"), encoding="utf-8"):
    line = line.rstrip("\n")
    if not line or line.startswith("#") or line.startswith("年"):
        continue
    rows.append(line.split(","))
scores = json.load(open(os.path.join(BASE, "tokyo_scores.json"), encoding="utf-8"))

for side in ("東", "西"):
    out_lines = COMMENTS[side] + [HDR]
    out_scores = {}
    n_uni = n_own = 0
    for c in rows:
        year, block = c[0], c[1]
        if block not in ("", side):
            continue
        cells = [year, ""] + c[2:]
        out_lines.append(",".join(cells))
        sc = scores.get(f"{year}|{block}")
        if sc:
            out_scores[f"{year}|"] = sc
        if block:
            n_own += 1
        else:
            n_uni += 1
    d = os.path.join(BASE, OUTDIR[side])
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "results.csv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out_lines) + "\n")
    with open(os.path.join(d, "scores.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out_scores, f, ensure_ascii=False, indent=1)
    print(f"{OUTDIR[side]}: 統一期 {n_uni} + {side}東京 {n_own} = {n_uni + n_own}大会 / scores {len(out_scores)}")
