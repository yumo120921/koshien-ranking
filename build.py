# -*- coding: utf-8 -*-
"""
高校野球 通算ランキング — サイトビルドスクリプト(全国対応版)

データソース:
  data/koshien.csv          … 甲子園(春・夏)の年度別成績 → トップページのランキング表(無ければ「準備中」表示)
                              列: 年,大会,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点
                              「大会」列は 春 / 夏。学校名は「校名(都道府県)」形式も可
  data/<県slug>/results.csv … 都道府県大会の年度別成績(例: data/saitama/results.csv)
  data/<県slug>/scores.json … 準々決勝以降のスコア詳細("年|ブロック" → {qf,sf,f})

生成物:
  index.html                … トップ(甲子園総合ランキング + 日本地図)
  <県slug>/index.html       … 県別アプリ(app_template.html にデータ注入)
  <県slug>/schools/*.html   … 学校別戦績ページ
  <県slug>/years/*.html     … 年度別結果ページ
  sitemap.xml

使い方: data/ を編集したら  python build.py  → git add -A / commit / push
"""
import csv, json, html, os, re, shutil
from collections import defaultdict
from datetime import date
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://koshien-ranking.com"
SITE_NAME = "高校野球 通算ランキング"

# ---------------- 都道府県定義 (slug, 表示名, タイル列, タイル行) ----------------

PREFS = [
    ("hokkaido", "北海道", 13, 1),
    ("aomori", "青森", 13, 2), ("akita", "秋田", 12, 3), ("iwate", "岩手", 13, 3),
    ("yamagata", "山形", 12, 4), ("miyagi", "宮城", 13, 4),
    ("niigata", "新潟", 12, 5), ("fukushima", "福島", 13, 5),
    ("ishikawa", "石川", 8, 6), ("toyama", "富山", 9, 6),
    ("gunma", "群馬", 11, 6), ("tochigi", "栃木", 12, 6), ("ibaraki", "茨城", 13, 6),
    ("kyoto", "京都", 7, 7), ("fukui", "福井", 8, 7), ("gifu", "岐阜", 9, 7),
    ("nagano", "長野", 10, 7), ("yamanashi", "山梨", 11, 7), ("saitama", "埼玉", 12, 7),
    ("saga", "佐賀", 1, 8), ("fukuoka", "福岡", 2, 8),
    ("yamaguchi", "山口", 3, 8), ("hiroshima", "広島", 4, 8), ("okayama", "岡山", 5, 8),
    ("hyogo", "兵庫", 6, 8), ("osaka", "大阪", 7, 8), ("shiga", "滋賀", 8, 8),
    ("aichi", "愛知", 10, 8), ("shizuoka", "静岡", 11, 8),
    ("tokyo", "東京", 12, 8), ("chiba", "千葉", 13, 8),
    ("nagasaki", "長崎", 1, 9), ("kumamoto", "熊本", 2, 9), ("oita", "大分", 3, 9),
    ("ehime", "愛媛", 5, 9), ("kagawa", "香川", 6, 9),
    ("wakayama", "和歌山", 7, 9), ("nara", "奈良", 8, 9), ("mie", "三重", 9, 9),
    ("kanagawa", "神奈川", 12, 9),
    ("kagoshima", "鹿児島", 2, 10), ("miyazaki", "宮崎", 3, 10),
    ("kochi", "高知", 5, 10), ("tokushima", "徳島", 6, 10),
    ("tottori", "鳥取", 5, 7), ("shimane", "島根", 4, 7),
    ("okinawa", "沖縄", 1, 11),
]
assert len(PREFS) == 47, f"都道府県は47のはず: {len(PREFS)}"
PREF_NAME = {slug: name for slug, name, _, _ in PREFS}

# ---------------- データ読み込み ----------------

def parse_results_csv(path, has_tournament_col=False):
    """results.csv / koshien.csv を読む。has_tournament_col=True なら2列目を大会名(春/夏)として扱う"""
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("年"):
                continue
            c = [x.strip() for x in line.split(",")]
            while len(c) < 12:
                c.append("")
            if not c[0].isdigit():
                continue
            rows.append({
                "year": c[0], "block": c[1],
                "ch": c[2], "ru": c[3],
                "b4": [x for x in c[4:6] if x],
                "b8": [x for x in c[6:10] if x],
                "ws": c[10], "ls": c[11],
            })
    return rows

def load_scores(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# ランキング計算パラメータの既定値(config.csv が無い場合に使用)
DEFAULT_PARAMS = {"pB8": 10, "pB4": 20, "pRU": 40, "pCH": 80, "cap": 5,
                  "wc": 2, "streak": 10, "uu": 5, "ucap": 15, "excluded": "2020"}

def load_config(path):
    """config.csv(キー,値,説明)→ パラメータdict。無ければ既定値"""
    params = dict(DEFAULT_PARAMS)
    if not os.path.exists(path):
        return params
    with open(path, encoding="utf-8") as f:
        for line in f:
            cells = [x.strip() for x in line.strip().split(",")]
            if len(cells) < 2 or cells[0] in ("", "キー") or cells[0].startswith("#"):
                continue
            key, val = cells[0], cells[1]
            if key not in DEFAULT_PARAMS:
                print(f"[warn] config.csv: 未知のキー {key} は無視します")
                continue
            if key == "excluded":
                params[key] = val.replace(";", ",").replace("、", ",")
            else:
                params[key] = float(val) if "." in val else int(val)
    return params

def load_aliases(path):
    """aliases.csv(統合前,統合後)→ [{'from':..,'to':..}]。無ければ空"""
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            cells = [x.strip() for x in line.strip().split(",")]
            if len(cells) < 2 or cells[0] in ("", "統合前") or cells[0].startswith("#"):
                continue
            out.append({"from": cells[0], "to": cells[1]})
    return out

def active_prefs():
    """data/<slug>/results.csv が存在する都道府県の一覧"""
    out = []
    for slug, name, col, row in PREFS:
        if os.path.exists(os.path.join(ROOT, "data", slug, "results.csv")):
            out.append(slug)
    return out

# ---------------- ページ共通部品 ----------------

CSS = """
body{margin:0;font-family:ui-sans-serif,system-ui,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;color:#1e293b;background:#f8fafc;line-height:1.9}
header{background:#1e293b;color:#fff;padding:14px 16px}
header a{color:#fff;text-decoration:none;font-weight:bold}
header nav{margin-top:4px;font-size:13px}
header nav a{font-weight:normal;color:#cbd5e1;margin-right:14px}
main{max-width:860px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:1.4rem;border-bottom:3px solid #1e293b;padding-bottom:8px}
h2{font-size:1.1rem;margin-top:2em;border-left:5px solid #1e293b;padding-left:10px}
table{border-collapse:collapse;width:100%;background:#fff;font-size:14px}
th,td{border:1px solid #cbd5e1;padding:6px 10px;text-align:left}
th{background:#e2e8f0;white-space:nowrap}
td.num,th.num{text-align:right}
a{color:#1d4ed8}
.cards{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}
.card{background:#fff;border:1px solid #cbd5e1;border-radius:8px;padding:10px 18px;text-align:center;min-width:96px}
.card b{display:block;font-size:1.5rem}
.card span{font-size:12px;color:#64748b}
.tablewrap{overflow-x:auto}
.pager{display:flex;justify-content:space-between;margin-top:24px;font-size:14px}
footer{background:#1e293b;color:#cbd5e1;padding:24px 16px;text-align:center;font-size:13px;line-height:2.2;margin-top:32px}
footer a{color:#cbd5e1;margin:0 10px;text-decoration:none}
.note{font-size:12px;color:#64748b}
.notice{background:#fef9c3;border:1px solid #facc15;border-radius:8px;padding:14px 18px;font-size:14px}
.mapwrap{overflow-x:auto;padding:4px 0}
.jmap{display:grid;grid-template-columns:repeat(13,44px);grid-auto-rows:44px;gap:4px;justify-content:center;min-width:640px}
.jmap a,.jmap span{display:flex;align-items:center;justify-content:center;border-radius:6px;font-size:11px;line-height:1.2;text-align:center;text-decoration:none;padding:2px}
.jmap a{background:#1d4ed8;color:#fff;font-weight:bold}
.jmap a:hover{background:#1e40af}
.jmap span{background:#e2e8f0;color:#94a3b8}
.maplegend{font-size:12px;color:#64748b;text-align:center;margin-top:8px}
"""

FOOTER = ('<footer><nav>'
          '<a href="/">トップ</a>|<a href="/saitama/">埼玉大会</a>|'
          '<a href="/about.html">サイトについて</a>|<a href="/privacy.html">プライバシーポリシー</a>|'
          '<a href="/disclaimer.html">免責事項</a>|<a href="/contact.html">お問い合わせ</a></nav>'
          f'<p style="margin:6px 0 0">&copy; 2026 {SITE_NAME}</p></footer>')

def esc(s):
    return html.escape(str(s), quote=True)

def page(title, desc, canonical_path, body, nav=""):
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE_URL}{quote(canonical_path)}">
<style>{CSS}</style>
</head>
<body>
<header><a href="/">{SITE_NAME}</a>
<nav>{nav}</nav></header>
<main>
{body}
</main>
{FOOTER}
</body>
</html>
"""

RANKS = [("ch", "優勝"), ("ru", "準優勝"), ("b4", "ベスト4"), ("b8", "ベスト8")]

def school_records(rows):
    rec = defaultdict(list)
    for r in rows:
        if r["ch"]: rec[r["ch"]].append((r, "優勝"))
        if r["ru"]: rec[r["ru"]].append((r, "準優勝"))
        for s in r["b4"]: rec[s].append((r, "ベスト4"))
        for s in r["b8"]: rec[s].append((r, "ベスト8"))
    return rec

def ranking_rows(rec):
    order = sorted(rec.items(), key=lambda kv: (
        -sum(1 for _, l in kv[1] if l == "優勝"),
        -sum(1 for _, l in kv[1] if l == "準優勝"),
        -len(kv[1]), kv[0]))
    out = []
    for i, (name, entries) in enumerate(order, 1):
        cnt = {label: sum(1 for _, l in entries if l == label) for _, label in RANKS}
        out.append((i, name, cnt, len(entries)))
    return out

# ---------------- 都道府県セクション生成 ----------------

def build_pref(slug):
    name = PREF_NAME[slug]
    tournament = f"夏の高校野球 {name}大会"
    base = f"/{slug}"
    rows = parse_results_csv(os.path.join(ROOT, "data", slug, "results.csv"))
    scores = load_scores(os.path.join(ROOT, "data", slug, "scores.json"))
    rows_text = open(os.path.join(ROOT, "data", slug, "results.csv"), encoding="utf-8").read().strip()

    keys = {f"{r['year']}|{r['block']}" for r in rows}
    orphan = [k for k in scores if k not in keys]
    if orphan:
        print(f"[warn] {slug}: scores.json にあるが results.csv にない大会:", orphan)

    nav = (f'<a href="{base}/">{name}大会トップ</a>'
           f'<a href="{base}/schools/">学校別戦績</a><a href="{base}/years/">年度別結果</a>')

    def school_href(n):
        return f"{base}/schools/{n}.html"

    def school_link(n):
        return f'<a href="{esc(school_href(n))}">{esc(n)}</a>' if n else ""

    def year_href(y):
        return f"{base}/years/{y}.html"

    def year_label(r):
        return r["year"] + (f"({r['block']})" if r["block"] else "")

    outbase = os.path.join(ROOT, slug)
    shutil.rmtree(os.path.join(outbase, "schools"), ignore_errors=True)
    shutil.rmtree(os.path.join(outbase, "years"), ignore_errors=True)
    os.makedirs(os.path.join(outbase, "schools"))
    os.makedirs(os.path.join(outbase, "years"))

    params = load_config(os.path.join(ROOT, "data", slug, "config.csv"))
    aliases = load_aliases(os.path.join(ROOT, "data", slug, "aliases.csv"))

    # --- アプリ本体(index.html) ---
    tpl = open(os.path.join(ROOT, "app_template.html"), encoding="utf-8").read()
    for ph in ("__IH_CSV__", "__TH_JSON__", "__PARAMS_JSON__", "__ALIASES_JSON__"):
        assert ph in tpl, f"テンプレートにプレースホルダがありません: {ph}"
    for bad in ("`", "${"):
        assert bad not in rows_text, f"CSVに使用できない文字: {bad}"
    th_js = json.dumps(scores, ensure_ascii=False, separators=(",", ":"))
    app = tpl.replace("__IH_CSV__", rows_text).replace("__TH_JSON__", th_js)
    app = app.replace("__PARAMS_JSON__", json.dumps(params, ensure_ascii=False, separators=(",", ":")))
    app = app.replace("__ALIASES_JSON__", json.dumps(aliases, ensure_ascii=False, separators=(",", ":")))
    app = app.replace("__PREF_BASE__", base)
    with open(os.path.join(outbase, "index.html"), "w", encoding="utf-8", newline="") as f:
        f.write(app)

    rec = school_records(rows)

    # --- 学校別ページ ---
    for sname, entries in rec.items():
        entries.sort(key=lambda e: (int(e[0]["year"]), e[0]["block"]))
        counts = {label: sum(1 for _, l in entries if l == label) for _, label in RANKS}
        first, last = entries[0][0]["year"], entries[-1][0]["year"]
        cards = "".join(f'<div class="card"><b>{counts[label]}</b><span>{label}</span></div>'
                        for _, label in RANKS)
        cards += f'<div class="card"><b>{len(entries)}</b><span>ベスト8以上</span></div>'
        trs = []
        for r, label in entries:
            extra = ""
            if label == "優勝" and r["ws"]:
                extra = f'決勝 {esc(r["ws"])}-{esc(r["ls"])} {school_link(r["ru"])}'
            elif label == "準優勝" and r["ws"]:
                extra = f'決勝 {esc(r["ls"])}-{esc(r["ws"])} {school_link(r["ch"])}'
            trs.append(f'<tr><td><a href="{year_href(r["year"])}">{esc(year_label(r))}</a></td>'
                       f'<td>{label}</td><td>{extra}</td></tr>')
        table = ('<div class="tablewrap"><table><tr><th>年</th><th>成績</th><th>決勝スコア</th></tr>'
                 + "".join(trs) + "</table></div>")
        bits = [f"{label} {counts[label]}回" for _, label in RANKS if counts[label]]
        desc = (f"{sname}の{tournament}戦績。{('、'.join(bits))}"
                f"(ベスト8以上{len(entries)}回、{first}年〜{last}年)。年度別の成績一覧。")
        body = (f"<h1>{esc(sname)} の戦績({name})</h1>"
                f"<p>{esc(sname)}の{tournament}におけるベスト8以上の成績一覧です"
                f"(初出は{first}年、直近は{last}年)。</p>"
                f'<div class="cards">{cards}</div>'
                f"<h2>年度別成績</h2>{table}"
                '<p class="note">※ ブロック表記(A・B、東西南北など)は、大会が複数代表制で行われた年度の各ブロックを表します。</p>')
        with open(os.path.join(outbase, "schools", f"{sname}.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(page(f"{sname} の戦績({name}) | {SITE_NAME}", desc, school_href(sname), body, nav))

    # --- 学校別一覧 ---
    rk = ranking_rows(rec)
    trs = []
    for i, sname, cnt, total in rk:
        trs.append(f'<tr><td class="num">{i}</td><td>{school_link(sname)}</td>'
                   f'<td class="num">{cnt["優勝"]}</td><td class="num">{cnt["準優勝"]}</td>'
                   f'<td class="num">{cnt["ベスト4"]}</td><td class="num">{cnt["ベスト8"]}</td>'
                   f'<td class="num">{total}</td></tr>')
    table = ('<div class="tablewrap"><table>'
             '<tr><th class="num">#</th><th>学校</th><th class="num">優勝</th><th class="num">準優勝</th>'
             '<th class="num">ベスト4</th><th class="num">ベスト8</th><th class="num">B8以上計</th></tr>'
             + "".join(trs) + "</table></div>")
    body = (f"<h1>{name} 学校別 通算成績一覧</h1>"
            f"<p>{tournament}のベスト8以上に入った全{len(rk)}校の通算成績です。"
            f'学校名をクリックすると年度別の詳細が見られます。'
            f'<a href="{base}/">{name}大会トップ</a>では条件を変えた集計もできます。</p>' + table)
    desc = f"{tournament}の学校別通算成績一覧。優勝・準優勝・ベスト4・ベスト8の回数を全{len(rk)}校分掲載。"
    with open(os.path.join(outbase, "schools", "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page(f"{name} 学校別 通算成績一覧 | {SITE_NAME}", desc, f"{base}/schools/", body, nav))

    # --- 年度別ページ ---
    def games_table(caption, games):
        trs = []
        for g in games or []:
            if not g or not (g.get("a") or g.get("b")):
                continue
            trs.append(f'<tr><td>{school_link(g.get("a",""))}</td>'
                       f'<td class="num">{esc(g.get("as",""))} - {esc(g.get("bs",""))}</td>'
                       f'<td>{school_link(g.get("b",""))}</td></tr>')
        if not trs:
            return ""
        return (f"<h2>{esc(caption)}</h2>"
                '<div class="tablewrap"><table><tr><th>勝者</th><th class="num">スコア</th><th>敗者</th></tr>'
                + "".join(trs) + "</table></div>")

    by_year = defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)
    years = sorted(by_year.keys(), key=int)

    for idx, y in enumerate(years):
        yrows = sorted(by_year[y], key=lambda r: r["block"])
        sections, champs = [], []
        for r in yrows:
            head = f"{r['block']}ブロック" if r["block"] else ""
            champs.append(r["ch"] + (f"({r['block']})" if r["block"] else ""))
            sec = f"<h2>{esc(head)}優勝校・上位進出校</h2>" if head else "<h2>優勝校・上位進出校</h2>"
            final_score = f" (決勝 {esc(r['ws'])}-{esc(r['ls'])})" if r["ws"] else ""
            sec += ('<div class="tablewrap"><table>'
                    f'<tr><th>優勝</th><td>{school_link(r["ch"])}{final_score}</td></tr>'
                    f'<tr><th>準優勝</th><td>{school_link(r["ru"])}</td></tr>'
                    f'<tr><th>ベスト4</th><td>{"、".join(school_link(s) for s in r["b4"])}</td></tr>'
                    f'<tr><th>ベスト8</th><td>{"、".join(school_link(s) for s in r["b8"])}</td></tr>'
                    "</table></div>")
            th = scores.get(f"{y}|{r['block']}")
            if th:
                pre = f"{r['block']}ブロック " if r["block"] else ""
                sec += games_table(f"{pre}決勝", [th.get("f")])
                sec += games_table(f"{pre}準決勝", th.get("sf"))
                sec += games_table(f"{pre}準々決勝", th.get("qf"))
            sections.append(sec)
        prev_a = f'<a href="{year_href(years[idx-1])}">&laquo; {years[idx-1]}年</a>' if idx > 0 else "<span></span>"
        next_a = f'<a href="{year_href(years[idx+1])}">{years[idx+1]}年 &raquo;</a>' if idx < len(years)-1 else "<span></span>"
        pager = f'<div class="pager">{prev_a}<a href="{base}/years/">年度一覧</a>{next_a}</div>'
        note = ""
        if len(yrows) > 1:
            note = ('<p class="note">※ この年度は大会がブロック制(複数代表)で行われたため、'
                    'ブロックごとに掲載しています。</p>')
        body = (f"<h1>{y}年 {tournament} の結果</h1>"
                f"<p>{y}年の{tournament}のベスト8以上の結果です。優勝は{esc('、'.join(champs))}。</p>"
                + note + "".join(sections) + pager)
        desc = f"{y}年{tournament}の結果。優勝{('、'.join(champs))}。ベスト8以上の成績と準々決勝以降のスコア。"
        with open(os.path.join(outbase, "years", f"{y}.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(page(f"{y}年 {tournament} の結果 | {SITE_NAME}", desc, year_href(y), body, nav))

    # --- 年度別一覧 ---
    trs = []
    for y in reversed(years):
        for r in sorted(by_year[y], key=lambda r: r["block"]):
            score = f'{esc(r["ws"])}-{esc(r["ls"])}' if r["ws"] else ""
            trs.append(f'<tr><td><a href="{year_href(y)}">{esc(year_label(r))}</a></td>'
                       f'<td>{school_link(r["ch"])}</td><td class="num">{score}</td>'
                       f'<td>{school_link(r["ru"])}</td></tr>')
    table = ('<div class="tablewrap"><table>'
             '<tr><th>年</th><th>優勝</th><th class="num">決勝スコア</th><th>準優勝</th></tr>'
             + "".join(trs) + "</table></div>")
    body = (f"<h1>{name} 年度別 結果一覧</h1>"
            f"<p>{tournament}の{years[0]}年から{years[-1]}年までの決勝結果一覧です。"
            f"年をクリックするとベスト8以上の詳細が見られます。</p>" + table)
    desc = f"{tournament}の年度別結果一覧({years[0]}年〜{years[-1]}年)。歴代優勝校・準優勝校と決勝スコア。"
    with open(os.path.join(outbase, "years", "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page(f"{name} 年度別 結果一覧 | {SITE_NAME}", desc, f"{base}/years/", body, nav))

    paths = [f"{base}/", f"{base}/schools/", f"{base}/years/"]
    paths += [school_href(n) for n in sorted(rec.keys())]
    paths += [year_href(y) for y in years]
    print(f"  {slug}: 大会 {len(rows)} / 学校 {len(rec)} / 年度 {len(years)}")
    return paths

# ---------------- トップページ ----------------

def split_pref(name):
    """「校名(都道府県)」→ (校名, 都道府県)。()が無ければ都道府県は空"""
    m = re.match(r"^(.*?)(?:[((](.*?)[))])?$", name)
    return (m.group(1), m.group(2) or "")

def koshien_section():
    path = os.path.join(ROOT, "data", "koshien.csv")
    if not os.path.exists(path):
        return ('<div class="notice">甲子園(春・夏)の通算ランキングは現在データを準備中です。'
                '公開までしばらくお待ちください。</div>'), False
    rows = parse_results_csv(path)
    # 「大会」列は block フィールドに入る(春/夏)
    rec = school_records(rows)
    rk = ranking_rows(rec)
    trs = []
    for i, name, cnt, total in rk:
        school, pref = split_pref(name)
        trs.append(f'<tr><td class="num">{i}</td><td>{esc(school)}</td><td>{esc(pref)}</td>'
                   f'<td class="num">{cnt["優勝"]}</td><td class="num">{cnt["準優勝"]}</td>'
                   f'<td class="num">{cnt["ベスト4"]}</td><td class="num">{cnt["ベスト8"]}</td>'
                   f'<td class="num">{total}</td></tr>')
    yrs = sorted({int(r["year"]) for r in rows})
    caption = (f"<p>春の選抜・夏の選手権のベスト8以上を対象にした通算成績です。"
               f"現在は{yrs[0]}年〜{yrs[-1]}年の{len(rows)}大会分を収録しており、順次拡充予定です"
               "(2020年は春・夏とも中止)。</p>")
    return (caption + '<div class="tablewrap"><table>'
            '<tr><th class="num">#</th><th>学校</th><th>都道府県</th><th class="num">優勝</th>'
            '<th class="num">準優勝</th><th class="num">ベスト4</th><th class="num">ベスト8</th>'
            '<th class="num">B8以上計</th></tr>' + "".join(trs) + "</table></div>"), True

def japan_map(active):
    tiles = []
    for slug, name, col, row in PREFS:
        style = f"grid-column:{col};grid-row:{row}"
        if slug in active:
            tiles.append(f'<a href="/{slug}/" style="{style}">{esc(name)}</a>')
        else:
            tiles.append(f'<span style="{style}" title="準備中">{esc(name)}</span>')
    return ('<div class="mapwrap"><div class="jmap">' + "".join(tiles) + "</div></div>"
            '<p class="maplegend">■ 青:公開中 / ■ 灰:準備中(順次公開予定)</p>')

def build_top(active):
    ranking_html, has_data = koshien_section()
    active_names = "、".join(PREF_NAME[s] for s in active)
    body = (
        "<h1>甲子園 通算ランキング(春・夏総合)</h1>"
        + ranking_html +
        "<h2>都道府県大会の通算ランキングはこちら</h2>"
        "<p>地図の都道府県をクリックすると、各都道府県大会(地方大会)のベスト8以上を対象にした"
        "通算ランキング・学校別戦績・年度別結果が見られます。"
        f"(現在公開中: {esc(active_names)})</p>"
        + japan_map(set(active))
    )
    desc = ("高校野球の通算ランキング。春の選抜・夏の選手権(甲子園)と都道府県大会のベスト8以上を対象に、"
            "学校別の優勝・準優勝・ベスト4・ベスト8回数を集計。")
    nav = '<a href="/saitama/">埼玉大会</a>'
    out = page(f"{SITE_NAME} | 甲子園&都道府県大会", desc, "/", body, nav)
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    return has_data

# ---------------- sitemap ----------------

def build_sitemap(all_paths):
    today = date.today().isoformat()
    urls = "\n".join(
        f"  <url><loc>{BASE_URL}{quote(p)}</loc><lastmod>{today}</lastmod></url>"
        for p in all_paths)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + urls + "\n</urlset>\n")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(xml)
    return len(all_paths)

# ---------------- main ----------------

def main():
    active = active_prefs()
    paths = ["/", "/about.html", "/privacy.html", "/disclaimer.html", "/contact.html"]
    for slug in active:
        paths += build_pref(slug)
    has_koshien = build_top(active)
    n = build_sitemap(paths)
    print(f"OK: 都道府県 {len(active)} ({', '.join(active)}) / 甲子園データ: {'あり' if has_koshien else '準備中'} / sitemap {n} URLs")

if __name__ == "__main__":
    main()
