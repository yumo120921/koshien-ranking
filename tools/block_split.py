# -*- coding: utf-8 -*-
"""ブロック分割県のデータを2データセットに分ける(北海道用、東京と同方式)。
python block_split.py <結果プレフィックス> <ブロック1> <出力1> <ブロック2> <出力2> <統一期注記>
統一期(ブロック空欄)の大会は両方に含める。"""
import io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))
src, b1, out1, b2, out2, note = sys.argv[1:7]

HDR = "年,ブロック,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点"
rows = []
for line in open(os.path.join(BASE, f"{src}_results.csv"), encoding="utf-8"):
    line = line.rstrip("\n")
    if not line or line.startswith("#") or line.startswith("年"):
        continue
    rows.append(line.split(","))
scores = json.load(open(os.path.join(BASE, f"{src}_scores.json"), encoding="utf-8"))

for side, outdir in ((b1, out1), (b2, out2)):
    lines = [f"# {side}{note}", "# 出典: bibijr.vivian.jp(高校野球データベース)のトーナメント表より集計", HDR]
    out_scores = {}
    n_uni = n_own = 0
    for c in rows:
        year, block = c[0], c[1]
        if block not in ("", side):
            continue
        lines.append(",".join([year, ""] + c[2:]))
        sc = scores.get(f"{year}|{block}")
        if sc:
            out_scores[f"{year}|"] = sc
        n_own += bool(block)
        n_uni += not block
    d = os.path.join(BASE, outdir)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{outdir}_results.csv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(d, f"{outdir}_scores.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out_scores, f, ensure_ascii=False, indent=1)
    print(f"{outdir}: 統一期 {n_uni} + {side} {n_own} = {n_uni + n_own}大会 / scores {len(out_scores)}")
