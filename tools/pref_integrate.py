# -*- coding: utf-8 -*-
"""都道府県予選の抽出(汎用): python pref_integrate.py <県ローマ字> <県名漢字>
単独開催のみ採用(合同大会は大会名キーワードで除外)"""
import os, re, glob, json, io, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_koya import row_cells

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = os.path.dirname(os.path.abspath(__file__))

PREF = sys.argv[1] if len(sys.argv) > 1 else "kanagawa"
KANJI = sys.argv[2] if len(sys.argv) > 2 else "神奈川"
# force=<ページ名>: 出典側の題字ミス等でホワイトリストに合わない単独開催ページを明示的に採用
FORCE = {a.split("=", 1)[1] for a in sys.argv[3:] if a.startswith("force=")}
DIR = os.path.join(BASE, PREF)
# 単独開催の判定はホワイトリスト方式:
# 大会名の末尾が「(記念)?(東西南北)?<県名>大会」に完全一致する場合のみ採用。
# (南関東・京浜・神静・北陸・信越…など各地方の合同大会は自動的に外れる)
# 2019年以降の「第N回全国高等学校野球選手権大会」のように地区名を含まない題も許容
# (一県一代表時代のみの形式のため単独と判定し、ブロックはURL末尾から取る)
ALLOW_RE = None  # main で KANJI から構築
SFX_BLOCK = {"e": "東", "w": "西", "n": "北", "s": "南"}

_z = "０１２３４５６７８９（）"
_h = "0123456789()"
Z2H = str.maketrans(_z, _h)

def norm(s):
    return s.translate(Z2H)

def clean_name(s):
    # 原典の補助記号(末尾ピリオド等)を除去: 「藤沢.」→「藤沢」
    return s.strip().rstrip(".．・")

def kai_to_year(kai):
    # 第27回=1941(中止年、地方大会のみ一部開催)、第28回=1946
    return 1914 + kai if kai <= 27 else 1918 + kai

ROUND_LBL = re.compile(r"^[0-9０-９一二三四五１-９]+回戦$")
DATE_LBL = re.compile(r"^\d+月\d+日$")
BOX_NEED = {"決勝": 2, "準決勝": 4, "準々決勝": 8, "準々": 8}

def parse_box(rows):
    """イニングスコア表から各ラウンドの(得点,校名)列を抽出。
    決勝2・準決勝4・準々決勝8が揃えばブラケットより信頼できる一次ソースになる。
    変種A: 校名がラウンド名と同じ列、合計は「計」列 / 変種B: 合計がラウンド名の列、校名がその右隣。
    1つのヘッダ行に複数の表が横並びの場合(左→右の順で試合が並ぶ)にも対応。"""
    def is_num(s):
        return bool(s) and bool(re.fullmatch(r"\d+", norm(s)))
    out = {"決勝": [], "準決勝": [], "準々決勝": []}
    for i, cells in enumerate(rows):
        # 本物のスコア表ヘッダはイニング番号列(1,2,3…)を持つ。
        # ブラケットのラウンド名ヘッダ(番号なし)を誤認しないための必須条件
        nums = {norm(t) for _, t in cells if t and re.fullmatch(r"[\d０-９]+", t)}
        if not {"1", "2", "3"} <= nums:
            continue
        labels = []
        sumcols = [c for c, t in cells if t == "計"]
        for c, t in cells:
            if t in BOX_NEED:
                labels.append((c, "準々決勝" if t == "準々" else t))
        for li, (L, lbl) in enumerate(labels):
            nxt = labels[li + 1][0] if li + 1 < len(labels) else 10 ** 6
            sumcol = next((sc for sc in sumcols if L < sc < nxt), None)
            j = i + 1
            while j < len(rows) and len(out[lbl]) < BOX_NEED[lbl]:
                rc = dict(rows[j])
                v = rc.get(L)
                fusen = any(t == "不戦勝" for c, t in rows[j] if L < c < nxt)
                if v is None:
                    # 不戦勝の勝者行は合計欄が無い(勝敗はbuild_recordが次ラウンド名から推定)
                    if fusen:
                        nm = next((t for c, t in sorted(rows[j]) if L < c <= L + 6
                                   and t and not is_num(t) and t != "不戦勝"), None)
                        if nm:
                            out[lbl].append((None, clean_name(nm)))
                    j += 1
                    continue
                if is_num(v):
                    nm = next((t for c, t in sorted(rows[j]) if L < c <= L + 6
                               and t and not is_num(t) and t != "不戦勝"), None)
                    if not nm:
                        break
                    # 不戦勝の試合はスコア無し扱い(勝敗は次ラウンド出場から推定される)
                    out[lbl].append((None if fusen else norm(v), clean_name(nm)))
                elif sumcol is not None and is_num(rc.get(sumcol)):
                    out[lbl].append((norm(rc[sumcol]), clean_name(v)))
                elif fusen and not is_num(v):
                    out[lbl].append((None, clean_name(v)))
                else:
                    break
                j += 1
    return out

def box_complete(out):
    if not (len(out["決勝"]) == 2 and len(out["準決勝"]) == 4
            and len(out["準々決勝"]) == 8):
        return False
    # 同点ペアがあるスコア表は延長打ち切り等の不完全表なので不採用
    # (ブラケット側の最終スコアにフォールバックさせる)
    for rd in out.values():
        for i in range(0, len(rd) - 1, 2):
            sa, sb = rd[i][0], rd[i + 1][0]
            if sa is not None and sb is not None and int(sa) == int(sb):
                return False
    return True

def scores_valid(th):
    """アプリの対戦モード検証(jH)と同等のチェック"""
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

def parse_champion(rows):
    """冒頭の「優勝 ○○」行から優勝校名を取る(リーグ戦年度などブラケットが無いページ用)"""
    for cells in rows[:20]:
        seq = sorted(cells)
        for k, (c, t) in enumerate(seq):
            if t == "優勝" and k + 1 < len(seq) and seq[k + 1][1]:
                return clean_name(seq[k + 1][1])
    return None

def parse_pref(path):
    rows = row_cells(path)
    title = None
    for cells in rows[:30]:
        joined = norm("".join(t for _, t in cells))
        m = re.search(r"第(\d+)回(全国高等学校野球選手権|全国中等学校優勝野球)(.*?大会)", joined)
        if m:
            title = m.group(0)
            break
    box_all = parse_box(rows)
    box = box_all if box_complete(box_all) else None
    champ = parse_champion(rows)
    final2 = box_all["決勝"] if len(box_all["決勝"]) == 2 else None
    hdr = None
    for i, cells in enumerate(rows):
        texts = {t for _, t in cells}
        if "決勝" in texts and "準決勝" in texts and ("準々決勝" in texts or "準々" in texts):
            hdr = (i, cells)
            break
    if hdr is None:
        # 4校制など準々決勝が無いブラケット(決勝+準決勝のみ)も許容
        # (誤検出対策: 採用時に main 側でスコア表の決勝と優勝・準優勝を照合する)
        for i, cells in enumerate(rows):
            texts = {t for _, t in cells}
            if "決勝" in texts and "準決勝" in texts and "計" not in texts:
                hdr = (i, cells)
                break
    if hdr is None:
        return title, None, box, champ, final2
    hi, hcells = hdr
    hdr_labels = {t for _, t in hcells if t}
    cols = {}
    for c, t in hcells:
        key = "準々決勝" if t == "準々" else t
        if key in ("決勝", "準決勝", "準々決勝"):
            cols[key] = c
    new_layout = cols["決勝"] > cols.get("準々決勝", cols["準決勝"])
    hdr_cols_sorted = sorted(c for c, t in hcells if t)
    def next_col(hc):
        bigger = [c for c in hdr_cols_sorted if c > hc]
        return bigger[0] if bigger else 10 ** 6
    # 区間終端を先に確定: ヘッダの再出現(=別セクション)、イニングスコア表の開始、
    # またはヘッダに無いN回戦ラベルの出現で打ち切る
    end = len(rows)
    for j in range(hi + 1, len(rows)):
        texts_j = {t for _, t in rows[j] if t}
        if ("決勝" in texts_j and "準決勝" in texts_j) or \
           ("計" in texts_j and texts_j & set(BOX_NEED)) or \
           any(t.endswith("リーグ") or t.endswith("予選") for t in texts_j) or \
           any(ROUND_LBL.fullmatch(norm(t)) and t not in hdr_labels for t in texts_j):
            end = j
            break
    # 旧レイアウトの列オフセット検出: (得点,校名) = (+1,+3) か (+0,+2)
    # (別セクションの列パターンを数えないよう、確定した区間内のみ走査する)
    off = (1, 3)
    if not new_layout:
        hits = {(1, 3): 0, (0, 2): 0}
        for j in range(hi + 1, end):
            cells = dict(rows[j])
            for hc in cols.values():
                for so, no in hits:
                    sc, nm = cells.get(hc + so), cells.get(hc + no)
                    if sc and nm and re.fullmatch(r"\d+", norm(sc)) and not re.fullmatch(r"\d+", norm(nm)):
                        hits[(so, no)] += 1
        off = max(hits, key=hits.get)
    rounds = {"決勝": [], "準決勝": [], "準々決勝": []}
    for j in range(hi + 1, end):
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
                if nm and not re.fullmatch(r"\d+", norm(nm)) and not DATE_LBL.fullmatch(norm(nm)):
                    rounds[rd].append((sc, clean_name(nm)))
            else:
                sc = cells.get(hc + off[0])
                nm = cells.get(hc + off[1])
                if nm and sc is not None:
                    sc2 = norm(sc)
                    rounds[rd].append((sc2 if re.fullmatch(r"\d+", sc2) else None, clean_name(nm)))
    return title, rounds, box, champ, final2

def build_record(rounds, warn):
    def pair_games(entries, expect, next_names):
        if entries and len(entries) != expect:
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
    # 少数校の大会では同一校が複数ラウンドに現れることがある。
    # アプリは1行内の重複校名を「未完成」として弾くため、重複は上位の成績のみ残す
    seen = {fin["a"], fin["b"]}
    b4 = [x if x and x not in seen and not seen.add(x) else "" for x in b4]
    b8 = [x if x and x not in seen and not seen.add(x) else "" for x in b8]
    return {"ch": fin["a"], "ru": fin["b"], "ws": fin["as"], "ls": fin["bs"],
            "b4": b4[:2] + [""] * (2 - len(b4[:2])),
            "b8": b8[:4] + [""] * (4 - len(b8[:4])),
            "scores": {"qf": [gj(g) for g in qf if not g["noscore"]],
                       "sf": [gj(g) for g in sf if not g["noscore"]],
                       "f": gj(fin)}}

def main():
    champs_check = {}
    km_path = os.path.join(BASE, "koya_master.json")
    if os.path.exists(km_path):
        km = json.load(open(km_path, encoding="utf-8"))
        for num, obj in km.items():
            meta = obj.get("meta") or {}
            if meta.get("name") != "夏" or not meta.get("year"):
                continue
            pairs = set()
            for g in obj.get("games", []):
                for side, d in (("a", "da"), ("b", "db")):
                    if KANJI in (g.get(d) or ""):
                        pairs.add((g[d], g[side]))
            if pairs:
                champs_check[meta["year"]] = pairs

    records = []
    inventory = []
    included_pages = set()
    for path in sorted(glob.glob(os.path.join(DIR, "*.htm"))):
        name = os.path.basename(path).replace(".htm", "")
        m = re.match(r"(\d+)([ewns]?)$", name)
        if not m:
            continue
        kai = int(m.group(1))
        sfx = m.group(2)
        title, rounds, box, champ, final2 = parse_pref(path)
        inventory.append((kai, sfx, title))
        if not title:
            continue
        tail = re.search(r"回(?:全国高等学校野球選手権|全国中等学校優勝野球)(.*?大会)", title).group(1)
        m2 = re.fullmatch(r"(?:記念)?([東西南北]?)" + re.escape(KANJI) + r"大会", tail)
        if m2:
            block = m2.group(1)
        elif re.fullmatch(r"(?:記念)?大会", tail):
            block = ""  # 地区名なしの新形式(2019年以降) → 単独開催
        elif name in FORCE:
            block = ""
            print(f"FORCE {name}: 題字「{title}」を単独開催として採用")
        else:
            continue  # 合同大会など
        if not block and sfx:
            block = SFX_BLOCK[sfx]
        warn = []
        if box is not None:
            # スコア表が完全ならそれを一次ソースにし、ブラケット解析結果と照合する
            rec = build_record(box, warn)
            if rounds is not None:
                brec = build_record(rounds, [])
                if brec is not None:
                    if brec["ch"] != rec["ch"]:
                        print(f"CHECK BOX/枠不一致 {name}: 優勝 {rec['ch']}(表) vs {brec['ch']}(枠)")
                    if set(b for b in brec["b8"] if b) != set(b for b in rec["b8"] if b):
                        print(f"CHECK BOX/枠不一致 {name}: B8 {sorted(set(rec['b8']))} vs {sorted(set(brec['b8']))}")
        elif rounds is not None:
            rec = build_record(rounds, warn)
            # ブラケット誤検出対策(地区予選の枠や中止年を拾わないための審判):
            # 1) 冒頭の優勝行が無い/一致しない → 不採用
            # 2) スコア表の決勝(同点でない場合のみ)と優勝・準優勝が食い違う → 不採用
            if rec is not None:
                f2 = None
                if final2 is not None:
                    (sa, a), (sb, b) = final2
                    if int(sa) != int(sb):  # 同点のスコア表は情報無しとして無視
                        f2 = (a, b) if int(sa) > int(sb) else (b, a)
                if champ is not None:
                    if rec["ch"] != champ:
                        print(f"CHECK 優勝行と不一致 {name}: 枠={rec['ch']} 優勝行={champ} → ブラケット破棄")
                        rec = None
                    elif f2 is not None and f2[0] == champ and (rec["ch"], rec["ru"]) != f2:
                        # スコア表の決勝も優勝行と同じ勝者を示す=本物の決勝。準優勝の食い違いは
                        # ブラケットが別の枠(予選等)である証拠なので破棄する。
                        # (勝者が優勝行と違うスコア表は決勝以外の表なので無視)
                        print(f"CHECK 枠決勝/スコア表不一致 {name}: {rec['ch']}-{rec['ru']}(枠) vs {f2[0]}-{f2[1]}(表) → ブラケット破棄")
                        rec = None
                elif f2 is not None:
                    if (rec["ch"], rec["ru"]) != f2:
                        print(f"CHECK 枠決勝/スコア表不一致 {name}: {rec['ch']}-{rec['ru']}(枠) vs {f2[0]}-{f2[1]}(表) → ブラケット破棄")
                        rec = None
                elif not rounds["準々決勝"]:
                    print(f"CHECK 審判情報なし {name}: 準々決勝を欠く簡易ブラケットのため破棄")
                    rec = None
        else:
            rec = None
        if rec is None:
            # ブラケットが無い年度(リーグ戦等): 優勝(+決勝スコアがあれば準優勝)のみの部分レコード
            if champ:
                rec = {"ch": champ, "ru": "", "ws": "", "ls": "",
                       "b4": ["", ""], "b8": ["", "", "", ""], "scores": None}
                if final2:
                    (sa, a), (sb, b) = final2
                    wnm, wsc, lnm, lsc = (a, sa, b, sb) if int(sa) >= int(sb) else (b, sb, a, sa)
                    if wnm == champ:
                        rec.update({"ru": lnm, "ws": wsc, "ls": lsc})
                    else:
                        # 優勝行と勝者が違うスコア表は決勝以外の表なので採用しない
                        print(f"CHECK 優勝/決勝表不一致 {name}: {champ} vs {wnm} → スコア表は無視")
                print(f"NOTE {name}: ブラケットなし → 優勝のみ収録 ({rec['ch']}"
                      + (f" 対 {rec['ru']} {rec['ws']}-{rec['ls']})" if rec["ru"] else ")"))
            else:
                print("SKIP(決勝なし)", name, title)
                continue
        year = kai_to_year(kai)
        rec.update({"year": year, "block": block, "kai": kai})
        if warn:
            print("WARN", year, block, warn)
        chk = champs_check.get(year)
        if chk is not None:
            # 地区名(例: 東東京)が一致する代表校と照合。分割年でない場合は県名のみで照合
            expected = (block + KANJI) if block else KANJI
            cand = {nm for d, nm in chk if expected in d}
            if cand and rec["ch"] not in cand:
                print(f"CHECK MISMATCH {year}{block}: 優勝 {rec['ch']} が全国データの{expected}代表 {sorted(cand)} に見つからない")
        records.append(rec)
        included_pages.add((kai, sfx))

    print("---- 除外ページ ----")
    for kai, sfx, title in sorted(inventory):
        if (kai, sfx) not in included_pages:
            print(f"第{kai}回{sfx}: {title or 'タイトル不明'} → 除外")

    records.sort(key=lambda r: (r["year"], r["block"]))
    print("採用:", len(records), "大会 / 範囲:", records[0]["year"], "-", records[-1]["year"])

    lines = [f"# {KANJI}単独開催の選手権{KANJI}大会のみ収録(合同予選の年は対象外)",
             "# 出典: bibijr.vivian.jp(高校野球データベース)のトーナメント表より集計",
             "年,ブロック,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点"]
    scores = {}
    for r in records:
        cells = [str(r["year"]), r["block"], r["ch"], r["ru"]] + r["b4"] + r["b8"] + [r["ws"], r["ls"]]
        lines.append(",".join(cells))
        sc = r["scores"]
        # 不戦勝などで試合が欠けた/整合しない大会はスコア詳細を出力しない
        # (アプリの対戦モードは全8+4+2校のスコアが揃い勝ち上がりが整合しないと
        #  「未完成」扱いで集計から丸ごと除外されるため、成績のみモードに落とす)
        if sc and scores_valid(sc):
            scores[f"{r['year']}|{r['block']}"] = sc
        elif sc:
            print(f"NOTE {r['year']}{r['block']}: 不戦勝・不整合等により対戦スコアは非出力(成績のみモード)")
    with open(os.path.join(BASE, f"{PREF}_results.csv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(BASE, f"{PREF}_scores.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(scores, f, ensure_ascii=False, indent=1)
    print("CSV rows:", len(lines) - 3, "/ scores keys:", len(scores))

if __name__ == "__main__":
    main()
