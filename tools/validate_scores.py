# -*- coding: utf-8 -*-
"""全データのscores.jsonをアプリの対戦モード検証(jH)と同等のルールで検査する。
python tools/validate_scores.py            … data/ 配下すべて
python tools/validate_scores.py <slug...>  … 指定slugのみ
問題が無ければ何も出力しない(終了コード0)。"""
import glob
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def check(slug):
    path = os.path.join(ROOT, "data", slug, "scores.json")
    if not os.path.exists(path):
        return 0
    bad = 0
    d = json.load(open(path, encoding="utf-8"))
    for k, th in sorted(d.items()):
        err = None
        if len(th.get("qf", [])) != 4 or len(th.get("sf", [])) != 2 or not th.get("f"):
            err = f"試合数不足 qf{len(th.get('qf', []))}/sf{len(th.get('sf', []))}/f{bool(th.get('f'))}"
        else:
            games = th["qf"] + th["sf"] + [th["f"]]
            for g in games:
                if not str(g.get("a", "")).strip() or not str(g.get("b", "")).strip():
                    err = "校名未入力"
                elif not str(g.get("as", "")).strip() or not str(g.get("bs", "")).strip():
                    err = "スコア未入力"
                elif int(g["as"]) == int(g["bs"]):
                    err = "同点"
                elif g["a"].strip() == g["b"].strip():
                    err = "同一校対戦"
                if err:
                    break
            if not err:
                w = lambda g: g["a"] if int(g["as"]) > int(g["bs"]) else g["b"]
                qfw = [w(g) for g in th["qf"]]
                sfp = [th["sf"][0]["a"], th["sf"][0]["b"], th["sf"][1]["a"], th["sf"][1]["b"]]
                if not all(x in qfw for x in sfp):
                    err = "準決勝出場校がQF勝者と不一致"
                elif not all(x in [w(g) for g in th["sf"]] for x in (th["f"]["a"], th["f"]["b"])):
                    err = "決勝出場校がSF勝者と不一致"
                else:
                    allqf = [g["a"].strip() for g in th["qf"]] + [g["b"].strip() for g in th["qf"]]
                    if len(set(allqf)) != 8:
                        err = "QF8校に重複"
        if err:
            print(slug, k, "→", err)
            bad += 1
    return bad

slugs = sys.argv[1:] or sorted(
    os.path.basename(os.path.dirname(p))
    for p in glob.glob(os.path.join(ROOT, "data", "*", "scores.json")))
total = sum(check(s) for s in slugs)
sys.exit(1 if total else 0)
