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
    # 北海道は北北海道・南北海道に、東京は東東京・西東京に分割して別「都道府県」として扱う
    ("minamihokkaido", "南北海道", 12, 1), ("kitahokkaido", "北北海道", 13, 1),
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
    ("nishitokyo", "西東京", 12, 8), ("higashitokyo", "東東京", 13, 8),
    ("nagasaki", "長崎", 1, 9), ("kumamoto", "熊本", 2, 9), ("oita", "大分", 3, 9),
    ("ehime", "愛媛", 5, 9), ("kagawa", "香川", 6, 9),
    ("wakayama", "和歌山", 7, 9), ("nara", "奈良", 8, 9), ("mie", "三重", 9, 9),
    ("kanagawa", "神奈川", 12, 9), ("chiba", "千葉", 13, 9),
    ("kagoshima", "鹿児島", 2, 10), ("miyazaki", "宮崎", 3, 10),
    ("kochi", "高知", 5, 10), ("tokushima", "徳島", 6, 10),
    ("tottori", "鳥取", 5, 7), ("shimane", "島根", 4, 7),
    ("okinawa", "沖縄", 1, 11),
]
assert len(PREFS) == 49, f"都道府県(北海道は南北、東京は東西に分割)は49のはず: {len(PREFS)}"
assert len({(c, r) for _, _, c, r in PREFS}) == 49, "地図タイルの座標が重複"
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
DEFAULT_PARAMS = {"pB8": 10, "pB4": 20, "pRU": 40, "pCH": 80, "cap": 5, "mcap": 10,
                  "wc": 2, "streak": 10, "uu": 5, "ucap": 15, "utcap": 0, "uwin": 20,
                  "cwin": 20, "inact": 0, "excluded": "2020"}

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

def load_defunct(path):
    """defunct.csv(学校名,消滅年,備考)→ {表示名: 消滅年}。無ければ空。
    学校名はランキング表示名(alias適用後の名前)で書く"""
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            cells = [x.strip() for x in line.strip().split(",")]
            if len(cells) < 2 or cells[0] in ("", "学校名") or cells[0].startswith("#"):
                continue
            if cells[1].isdigit():
                out[cells[0]] = int(cells[1])
    return out

DEFAULT_SOURCES = "出典: 各大会の公式記録・トーナメント表に基づき運営者が集計 / 点差係数の設計参考: World Football Elo Ratings(eloratings.net方式)"

def load_sources(path):
    """sources.txt(出典表記の1行テキスト)。無ければ既定文"""
    if not os.path.exists(path):
        return DEFAULT_SOURCES
    return open(path, encoding="utf-8").read().strip()

def render_app(datadir, rows_text, scores, *, title, desc, scope, pref_base,
               seo_title=None, seo_desc=None):
    """app_template.html にデータと文言を注入して対話型アプリのHTMLを返す"""
    params = load_config(os.path.join(datadir, "config.csv"))
    aliases = load_aliases(os.path.join(datadir, "aliases.csv"))
    sources = load_sources(os.path.join(datadir, "sources.txt"))
    defunct = load_defunct(os.path.join(datadir, "defunct.csv"))
    tpl = open(os.path.join(ROOT, "app_template.html"), encoding="utf-8").read()
    for ph in ("__IH_CSV__", "__TH_JSON__", "__PARAMS_JSON__", "__ALIASES_JSON__",
               "__DEFUNCT_JSON__",
               "__APP_TITLE__", "__APP_DESC__", "__APP_SCOPE__", "__APP_SOURCES__"):
        assert ph in tpl, f"テンプレートにプレースホルダがありません: {ph}"
    for bad in ("`", "${"):
        assert bad not in rows_text, f"CSVに使用できない文字: {bad}"
    # SEO用: <title>・og:title・meta descriptionだけ検索向けの文言に差し替える
    # (画面上の見出しに出る __APP_TITLE__/__APP_DESC__ は title/desc のまま)
    if seo_title:
        tpl = tpl.replace("<title>__APP_TITLE__</title>", f"<title>{seo_title}</title>", 1)
        tpl = tpl.replace('content="__APP_TITLE__"', f'content="{seo_title}"', 1)
    if seo_desc:
        tpl = tpl.replace('content="__APP_DESC__"', f'content="{seo_desc}"', 1)
    app = (tpl
           .replace("__IH_CSV__", rows_text)
           .replace("__TH_JSON__", json.dumps(scores, ensure_ascii=False, separators=(",", ":")))
           .replace("__PARAMS_JSON__", json.dumps(params, ensure_ascii=False, separators=(",", ":")))
           .replace("__ALIASES_JSON__", json.dumps(aliases, ensure_ascii=False, separators=(",", ":")))
           .replace("__DEFUNCT_JSON__", json.dumps(defunct, ensure_ascii=False, separators=(",", ":")))
           .replace("__APP_TITLE__", title)
           .replace("__APP_DESC__", desc)
           .replace("__APP_SCOPE__", scope)
           .replace("__APP_SOURCES__", sources)
           .replace("__PREF_BASE__", pref_base))
    return app

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
          '<a href="/about">サイトについて</a>|<a href="/privacy">プライバシーポリシー</a>|'
          '<a href="/disclaimer">免責事項</a>|<a href="/contact">お問い合わせ</a></nav>'
          f'<p style="margin:6px 0 0">&copy; 2026 {SITE_NAME}</p></footer>')

# Google AdSense(サイト確認・広告配信用)。全ページの<head>に入れる
ADSENSE = ('<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js'
           '?client=ca-pub-6908671930198074" crossorigin="anonymous"></script>')

def add_adsense(doc):
    """</head> の直前にAdSenseコードを差し込む"""
    return doc.replace("</head>", ADSENSE + "</head>", 1)

def add_canonical(doc, path):
    """</head> の直前にcanonicalタグを差し込む(アプリ型ページ用)"""
    tag = f'<link rel="canonical" href="{BASE_URL}{quote(path)}">'
    return doc.replace("</head>", tag + "</head>", 1)

# 共有ボタン(X・LINE・リンクコピー)。全ページ共通・自己完結(外部スクリプトなし)。
# URLとタイトルは表示時にJSで取るので、どのページにも同じスニペットをそのまま注入できる
# 共有先URLはクリック時にJSで組み立てて開く(静的hrefを持たせない)。
# 広告ブロッカーのSNSフィルタは a[href*="twitter.com/intent"] のような
# 要素非表示ルールを持つため、hrefがあるとボタン自体が消されることがある
SHARE_SNIPPET = (
    '<div id="pgbtns" style="position:fixed;bottom:14px;right:12px;z-index:9998;'
    'display:flex;flex-direction:column;gap:8px;">'
    '<button type="button" data-sv="x" aria-label="Xでポストする" title="Xでポストする"'
    ' style="width:40px;height:40px;border-radius:50%;background:#000;color:#fff;'
    'border:0;cursor:pointer;font-weight:bold;font-size:18px;padding:0;'
    'box-shadow:0 1px 4px rgba(0,0,0,0.3);font-family:sans-serif">X</button>'
    '<button type="button" data-sv="line" aria-label="LINEで送る" title="LINEで送る"'
    ' style="width:40px;height:40px;border-radius:50%;background:#06C755;color:#fff;'
    'border:0;cursor:pointer;font-weight:bold;font-size:10px;padding:0;'
    'box-shadow:0 1px 4px rgba(0,0,0,0.3);font-family:sans-serif">LINE</button>'
    '<button type="button" data-sv="cp" aria-label="リンクをコピー" title="リンクをコピー"'
    ' style="width:40px;height:40px;border-radius:50%;background:#fff;color:#334155;'
    'border:1px solid #cbd5e1;cursor:pointer;font-size:16px;padding:0;'
    'box-shadow:0 1px 4px rgba(0,0,0,0.3)">&#128279;</button>'
    '</div>'
    '<script>(function(){'
    'var bx=document.querySelectorAll("#pgbtns button");'
    'function opn(u){window.open(u,"_blank","noopener")}'
    'for(var i=0;i<bx.length;i++){bx[i].onclick=function(){'
    'var u=encodeURIComponent(location.href),t=encodeURIComponent(document.title),'
    'k=this.getAttribute("data-sv"),b=this;'
    'if(k==="x"){opn("https://x.com/intent/tweet?text="+t+"&url="+u)}'
    'else if(k==="line"){opn("https://social-plugins.line.me/lineit/share?url="+u)}'
    'else if(navigator.clipboard){navigator.clipboard.writeText(location.href)'
    '.then(function(){b.textContent="\\u2713";'
    'setTimeout(function(){b.textContent="\\uD83D\\uDD17"},1200)})}'
    '}}})();</script>'
)

def add_share(doc):
    """</body> の直前に共有ボタンを差し込む(全ページ共通)"""
    i = doc.rindex("</body>")
    return doc[:i] + SHARE_SNIPPET + doc[i:]

def esc(s):
    return html.escape(str(s), quote=True)

def page(title, desc, canonical_path, body, nav="", noindex=False):
    robots = '\n<meta name="robots" content="noindex">' if noindex else ""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">{robots}
<link rel="canonical" href="{BASE_URL}{quote(canonical_path)}">
<style>{CSS}</style>
{ADSENSE}
</head>
<body>
<header><a href="/">{SITE_NAME}</a>
<nav>{nav}</nav></header>
<main>
{body}
</main>
{FOOTER}
{SHARE_SNIPPET}
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
    tinfo = _yagura_info(slug)

    keys = {f"{r['year']}|{r['block']}" for r in rows}
    orphan = [k for k in scores if k not in keys]
    if orphan:
        print(f"[warn] {slug}: scores.json にあるが results.csv にない大会:", orphan)

    nav = (f'<a href="{base}/">{name}大会トップ</a>'
           f'<a href="{base}/schools/">学校別戦績</a><a href="{base}/years/">年度別結果</a>')
    if tinfo:
        nav += f'<a href="{base}/tournament/">トーナメント速報</a>'

    def school_href(n):
        return f"{base}/schools/{n}"

    def school_link(n):
        return f'<a href="{esc(school_href(n))}">{esc(n)}</a>' if n else ""

    def year_href(y):
        return f"{base}/years/{y}"

    def year_label(r):
        return r["year"] + (f"({r['block']})" if r["block"] else "")

    outbase = os.path.join(ROOT, slug)
    shutil.rmtree(os.path.join(outbase, "schools"), ignore_errors=True)
    shutil.rmtree(os.path.join(outbase, "years"), ignore_errors=True)
    os.makedirs(os.path.join(outbase, "schools"))
    os.makedirs(os.path.join(outbase, "years"))

    # --- アプリ本体(index.html) ---
    app = render_app(
        os.path.join(ROOT, "data", slug), rows_text, scores,
        title=f"{name}高校野球 通算ランキング",
        desc=f"{name}の高校野球の戦績データベース。学校別の通算成績ランキングや年度別のトーナメント結果をまとめています。",
        scope=f"夏の{name}大会",
        pref_base=base,
        seo_title=(f"{name}高校野球 通算ランキング | {tinfo['year']}年 {name}大会 トーナメント表・結果速報"
                   if tinfo else None),
        seo_desc=(f"{name}の高校野球の戦績データベース。{tinfo['year']}年夏の{name}大会の"
                  "トーナメント表・結果速報を毎日更新。学校別の通算成績ランキングや年度別の結果も。"
                  if tinfo else None))
    # 左上に「トップページへ戻る」ボタン(県ページのみ)
    back_btn = (
        '<a href="/" style="position:fixed;top:10px;left:10px;z-index:9999;'
        'background:rgba(255,255,255,0.92);color:#1e293b;border:1px solid #cbd5e1;'
        'border-radius:9999px;padding:6px 14px;font-size:13px;font-weight:bold;'
        f'text-decoration:none;font-family:{FONT};box-shadow:0 1px 4px rgba(0,0,0,0.2)">'
        '&#8592; トップページ</a>')
    app = app.replace("<body>", "<body>" + back_btn, 1)
    app = add_share(add_adsense(add_canonical(app, f"/{slug}/")))
    app = add_bracket(app, "pref", slug)
    with open(os.path.join(outbase, "index.html"), "w", encoding="utf-8", newline="") as f:
        f.write(app)

    rec = school_records(rows)

    # --- 学校別ページ ---
    # 掲載2回以下の学校は内容が薄い(表1〜2行)ため検索インデックス対象から外す
    # (ページ自体は生成し、サイト内リンクからは従来どおり見られる)
    thin_schools = {sname for sname, entries in rec.items() if len(entries) <= 2}
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
            f.write(page(f"{sname} の戦績({name}) | {SITE_NAME}", desc, school_href(sname), body, nav,
                         noindex=(sname in thin_schools)))

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
    tpath = build_tournament_page("pref", slug, school_names=set(rec.keys()))
    if tpath:
        paths.append(tpath)
    paths += [school_href(n) for n in sorted(rec.keys()) if n not in thin_schools]
    paths += [year_href(y) for y in years]
    print(f"  {slug}: 大会 {len(rows)} / 学校 {len(rec)} / 年度 {len(years)}")
    return paths

# ---------------- トップページ ----------------

def split_pref(name):
    """「校名(都道府県)」→ (校名, 都道府県)。()が無ければ都道府県は空"""
    m = re.match(r"^(.*?)(?:[((](.*?)[))])?$", name)
    return (m.group(1), m.group(2) or "")

FONT = 'ui-sans-serif,system-ui,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif'

def japan_map_section(active):
    """タイル型の日本地図セクション(インラインスタイル。アプリページにも静的ページにも埋め込める)"""
    tile_base = ("display:flex;align-items:center;justify-content:center;border-radius:6px;"
                 "font-size:11px;line-height:1.2;text-align:center;text-decoration:none;padding:2px")
    tiles = []
    for slug, name, col, row in PREFS:
        pos = f"grid-column:{col};grid-row:{row};{tile_base}"
        if slug in active:
            tiles.append(f'<a href="/{slug}/" style="{pos};background:#1d4ed8;color:#fff;font-weight:bold">{esc(name)}</a>')
        else:
            tiles.append(f'<span style="{pos};background:#e2e8f0;color:#94a3b8" title="準備中">{esc(name)}</span>')
    active_names = "、".join(PREF_NAME[s] for s in active)
    return (
        f'<section style="background:#f8fafc;padding:32px 16px;font-family:{FONT};line-height:1.9">'
        '<h2 style="max-width:860px;margin:0 auto;font-size:1.1rem;color:#1e293b;'
        'border-left:5px solid #1e293b;padding-left:10px">都道府県大会の通算ランキングはこちら</h2>'
        '<p style="max-width:860px;margin:12px auto 20px;font-size:14px;color:#1e293b">'
        '地図の都道府県をクリックすると、各都道府県大会(地方大会)のベスト8以上を対象にした'
        '通算ランキング・学校別戦績・年度別結果が見られます。北海道は北北海道・南北海道に分けて扱います。'
        f'(現在公開中: {esc(active_names)})</p>'
        '<div style="overflow-x:auto;padding:4px 0">'
        '<div style="display:grid;grid-template-columns:repeat(13,44px);grid-auto-rows:44px;'
        'gap:4px;justify-content:center;min-width:640px">' + "".join(tiles) + "</div></div>"
        '<p style="text-align:center;font-size:12px;color:#64748b;margin-top:8px">'
        '■ 青:公開中 / ■ 灰:準備中(順次公開予定)</p></section>')

TOP_FOOTER = (
    f'<footer style="background:#1e293b;color:#cbd5e1;padding:24px 16px;text-align:center;'
    f'font-family:{FONT};font-size:13px;line-height:2.2"><nav>'
    '<a href="/saitama/" style="color:#cbd5e1;margin:0 10px;text-decoration:none">埼玉大会</a>|'
    '<a href="/about" style="color:#cbd5e1;margin:0 10px;text-decoration:none">サイトについて</a>|'
    '<a href="/privacy" style="color:#cbd5e1;margin:0 10px;text-decoration:none">プライバシーポリシー</a>|'
    '<a href="/disclaimer" style="color:#cbd5e1;margin:0 10px;text-decoration:none">免責事項</a>|'
    '<a href="/contact" style="color:#cbd5e1;margin:0 10px;text-decoration:none">お問い合わせ</a></nav>'
    f'<p style="margin:6px 0 0">&copy; 2026 {SITE_NAME}</p></footer>')

def build_top(active):
    """トップページ: 甲子園データがあれば埼玉と同じ対話型アプリ + 日本地図。無ければ準備中表示"""
    koshien_dir = os.path.join(ROOT, "data", "koshien")
    results = os.path.join(koshien_dir, "results.csv")
    map_html = japan_map_section(set(active))

    if not os.path.exists(results):
        body = ('<h1>甲子園 通算ランキング(春・夏総合)</h1>'
                '<div class="notice">甲子園(春・夏)の通算ランキングは現在データを準備中です。</div>')
        desc = "高校野球の通算ランキング。甲子園と都道府県大会のベスト8以上を対象に集計。"
        out = page(f"{SITE_NAME} | 甲子園&都道府県大会", desc, "/", body + map_html,
                   '<a href="/saitama/">埼玉大会</a>')
        with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        return False

    # 学校名から「(都道府県)」を外してアプリ用CSVを再構成(名寄せのため)
    rows = parse_results_csv(results)
    lines = ["年,大会,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点"]
    for r in rows:
        b4 = (r["b4"] + ["", ""])[:2]
        b8 = (r["b8"] + ["", "", "", ""])[:4]
        cells = ([r["year"], r["block"], split_pref(r["ch"])[0], split_pref(r["ru"])[0]]
                 + [split_pref(s)[0] for s in b4] + [split_pref(s)[0] for s in b8]
                 + [r["ws"], r["ls"]])
        lines.append(",".join(cells))
    ih_text = "\n".join(lines)

    scores = load_scores(os.path.join(koshien_dir, "scores.json"))
    tinfo = _yagura_info("koshien")
    tname = "選抜" if tinfo and tinfo["season"] == "春" else "選手権"
    app = render_app(
        koshien_dir, ih_text, scores,
        title="全国高等学校野球部ランキング(春・夏総合)",
        desc=("甲子園(春の選抜・夏の選手権)のベスト8以上を対象にした高校野球の通算ランキング。"
              "都道府県大会のランキングも掲載。"),
        scope="春・夏の甲子園",
        pref_base="",
        seo_title=(f"甲子園 通算ランキング | {tinfo['year']}年 {tname}大会 トーナメント表・結果速報"
                   if tinfo else None),
        seo_desc=(f"甲子園(春の選抜・夏の選手権)の高校野球通算ランキングと、{tinfo['year']}年 "
                  f"{tname}大会のトーナメント表・結果速報を毎日更新。都道府県大会のランキングも掲載。"
                  if tinfo else None))

    # フッターを「日本地図セクション + サイト共通フッター」に差し替える
    fs = app.rindex("<footer style=")
    fe = app.rindex("</footer>") + len("</footer>")
    app = app[:fs] + map_html + TOP_FOOTER + app[fe:]
    app = add_share(add_adsense(add_canonical(app, "/")))
    app = add_bracket(app, "top")
    app = add_live_widget(app)

    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8", newline="") as f:
        f.write(app)
    return True


# ---------------- トーナメントタブ(全大会のブラケット+順位注記) ----------------

import sys as _sys
_sys.path.insert(0, os.path.join(ROOT, "tools"))
import rank_engine as _RE
import bracket_full as _BF

BRACKET_WINDOWS = [5, 10, 20, 30, 50, 0]   # 0=全期間
_BRACKET_JS_CACHE = {}

class _RankSource:
    """1データセット分のランキング計算(結果はウィンドウ別にキャッシュ)"""

    def __init__(self, datadir, strip=False):
        self.rows = parse_results_csv(os.path.join(datadir, "results.csv"))
        if strip:
            for r in self.rows:
                r["ch"] = split_pref(r["ch"])[0]
                r["ru"] = split_pref(r["ru"])[0]
                r["b4"] = [split_pref(x)[0] for x in r["b4"]]
                r["b8"] = [split_pref(x)[0] for x in r["b8"]]
        self.scores = load_scores(os.path.join(datadir, "scores.json"))
        params = load_config(os.path.join(datadir, "config.csv"))
        aliases = load_aliases(os.path.join(datadir, "aliases.csv"))
        self.defunct = load_defunct(os.path.join(datadir, "defunct.csv"))
        self.alias = _RE.make_alias_fn(aliases)
        self.full = _RE.compute_full(self.rows, self.scores, params, aliases)
        self.as_of = self.full["years"][-1] if self.full["years"] else None
        self._rk = {}
        self._appy = {}

    def rank(self, name, w):
        if w not in self._rk:
            self._rk[w] = _RE.ranks(_RE.window_table(self.full, w), self.defunct, self.as_of)
        hit = self._rk[w].get(self.alias(name))
        return hit[0] if hit else None

    def _app_years(self, block):
        """(大会系列ごとの)学校→ベスト8以上の年リスト"""
        if block not in self._appy:
            t = self.alias
            m = {}
            for r in self.rows:
                if block is not None and r["block"] != block:
                    continue
                y = int(r["year"])
                for x in [r["ch"], r["ru"]] + r["b4"] + r["b8"]:
                    if x:
                        m.setdefault(t(x), set()).add(y)
            self._appy[block] = {k: sorted(v) for k, v in m.items()}
        return self._appy[block]

    @staticmethod
    def _fmt_appearance(yrs, year):
        yrs = [y for y in yrs if y <= year]
        if len(yrs) <= 1:
            return "初"
        run, i = 1, len(yrs) - 1
        while i > 0 and yrs[i] - yrs[i - 1] == 1:
            run += 1
            i -= 1
        if run >= 2:
            return f"{run}年連続{len(yrs)}回目"
        return f"{year - yrs[-2]}年ぶり{len(yrs)}回目"

    def appearance(self, name, year, block=None):
        """当該年時点の「N年ぶり/連続M回目」(ベスト8以上ベース)"""
        return self._fmt_appearance(self._app_years(block).get(self.alias(name), []), year)

    def appearance_as_champion(self, name, year):
        """優勝年ベースの出場歴(夏の甲子園出場=県大会優勝の回数に一致)"""
        if not hasattr(self, "_champ_years"):
            m = {}
            for r in self.rows:
                if (r["ch"] or "").strip():
                    m.setdefault(self.alias(r["ch"]), set()).add(int(r["year"]))
            self._champ_years = {k: sorted(v) for k, v in m.items()}
        return self._fmt_appearance(self._champ_years.get(self.alias(name), []), year)

_rank_sources = {}

def _get_source(slug):
    """slug='koshien'は県名を外した甲子園データ"""
    if slug not in _rank_sources:
        _rank_sources[slug] = _RankSource(os.path.join(ROOT, "data", slug), strip=(slug == "koshien"))
    return _rank_sources[slug]

def _winner_idx(g):
    return 0 if int(g["as"]) > int(g["bs"]) else 1

def _orient(th):
    """scoresエントリを左右ブラケット構造に並べる"""
    f = th["f"]
    def w(g):
        return g["a"] if _winner_idx(g) == 0 else g["b"]
    sfL = next(g for g in th["sf"] if w(g) == f["a"])
    sfR = next(g for g in th["sf"] if g is not sfL)
    def side(sf):
        qf1 = next(g for g in th["qf"] if w(g) == sf["a"])
        qf2 = next(g for g in th["qf"] if w(g) == sf["b"])
        teams = [qf1["a"], qf1["b"], qf2["a"], qf2["b"]]
        games = {"qf": [{"s": [int(qf1["as"]), int(qf1["bs"])], "w": _winner_idx(qf1)},
                        {"s": [int(qf2["as"]), int(qf2["bs"])], "w": _winner_idx(qf2)}],
                 "sf": {"s": [int(sf["as"]), int(sf["bs"])], "w": _winner_idx(sf)}}
        return teams, games
    tL, gL = side(sfL)
    tR, gR = side(sfR)
    fgame = {"s": [int(f["as"]), int(f["bs"])], "w": _winner_idx(f)}
    return tL, tR, gL, gR, fgame, w(f)

_PREF_SLUG = {name: slug for slug, name, _, _ in PREFS}

def _cross_source_for(name, pref):
    """トップ用: 学校の所属県のRankSource(北海道・東京は両分割を在籍確認)"""
    if pref in _PREF_SLUG:
        slugs = [_PREF_SLUG[pref]]
    elif pref == "北海道":
        slugs = ["kitahokkaido", "minamihokkaido"]
    elif pref == "東京":
        slugs = ["higashitokyo", "nishitokyo"]
    else:
        return None
    fallback = None
    for sg in slugs:
        if os.path.isdir(os.path.join(ROOT, "data", sg)):
            cand = _get_source(sg)
            if cand.alias(name) in cand.full["schools"]:
                return cand
            fallback = fallback or cand
    return fallback

def _bracket_json(kind, slug=None):
    """kind='pref'|'top'。全大会分の描画用JSON(dict)。データ無しならNone"""
    src = _get_source(slug if kind == "pref" else "koshien")
    cands = [k for k in src.scores if k.split("|")[0].isdigit()]
    if not cands:
        return None
    if kind == "pref":
        cands.sort(key=lambda k: (int(k.split("|")[0]), k.split("|")[1]), reverse=True)
    else:
        cands.sort(key=lambda k: (int(k.split("|")[0]), k.split("|")[1] == "夏"), reverse=True)

    # トップ用: 校名→都道府県(全収録行の「校名(県)」から。最新年を優先)
    pref_of = {}
    pref_of_yagura = {}
    if kind == "top":
        raw = parse_results_csv(os.path.join(ROOT, "data", "koshien", "results.csv"))
        for r in sorted(raw, key=lambda r: int(r["year"])):
            for cell in [r["ch"], r["ru"]] + r["b4"] + r["b8"]:
                nm, pref = split_pref(cell)
                if pref:
                    pref_of[nm] = pref

    schools = {}

    def add_school(name):
        if name in schools:
            return
        e = {"own": {str(w): src.rank(name, w) for w in BRACKET_WINDOWS}}
        if kind == "pref":
            csrc = _get_source("koshien")
            e["cross"] = {str(w): csrc.rank(name, w) for w in BRACKET_WINDOWS}
        else:
            pref = pref_of_yagura.get(name) or pref_of.get(name, "")
            csrc = _cross_source_for(name, pref)
            if csrc:
                e["cross"] = {str(w): csrc.rank(name, w) for w in BRACKET_WINDOWS}
            else:
                e["cross"] = {str(w): None for w in BRACKET_WINDOWS}
            e["crossLabel"] = pref or "県"
        schools[name] = e

    tournaments = []
    for key in cands:
        year, block = int(key.split("|")[0]), key.split("|")[1]
        try:
            tL, tR, gL, gR, fgame, champ = _orient(src.scores[key])
        except (StopIteration, KeyError, ValueError, TypeError):
            continue
        if kind == "pref":
            label = f"{year}年" + (f"({block})" if block else "")
            title = f"{year}年 選手権{PREF_NAME[slug]}大会" + (f"({block})" if block else "")
            app_block = None
        else:
            label = f"{year}年 {'選抜' if block == '春' else '選手権'}"
            title = f"{year}年 {'選抜' if block == '春' else '選手権'}大会(甲子園)"
            app_block = block
        for n in tL + tR:
            add_school(n)
        def side_entries(names):
            return [{"name": n, "app": src.appearance(n, year, app_block)} for n in names]
        tournaments.append({"label": label, "title": title, "champion": champ,
                            "teams": {"L": side_entries(tL), "R": side_entries(tR)},
                            "games": {"L": gL, "R": gR, "f": fgame}})
    # 当年の全校ヤグラがあれば、その年の大会をfullモードに差し替え(無ければ先頭に追加)
    text_url = None
    ypath = os.path.join(ROOT, "data", slug if kind == "pref" else "koshien", "yagura.json")
    if os.path.exists(ypath):
        try:
            yg = json.load(open(ypath, encoding="utf-8"))
        except Exception:
            yg = None
        if yg and yg.get("games"):
            own_alias = src.alias

            def _rank_of(name):
                r = src.rank(name, 20)
                return f"{'県' if kind == 'pref' else '総合'}{r}位" if r else None

            full = _BF.build_full(yg, kind, _rank_of)
            if full and kind == "top":
                # ヤグラデータの所属県表記を優先(ベスト8歴が無い学校も県を特定できる)
                for g in yg["games"]:
                    if g.get("a") and g.get("ap"):
                        pref_of_yagura[g["a"]] = g["ap"]
                    if g.get("b") and g.get("bp"):
                        pref_of_yagura[g["b"]] = g["bp"]
            if full:
                yyear = yg.get("year")
                if not yyear:
                    dates = [g.get("date", "") for g in yg["games"] if g.get("date")]
                    yyear = int(max(dates)[:4]) if dates else None
                nteam = yg.get("team_count") or len(full["teams"])
                if kind == "pref":
                    full["title"] = f"{yyear}年 選手権{PREF_NAME[slug]}大会(全{nteam}校)"
                    lbl = f"{yyear}年(全{nteam}校)"
                else:
                    months = {int(g["date"][4:6]) for g in yg["games"]
                              if re.fullmatch(r"\d{8}", str(g.get("date", "")))}
                    season = "春" if months and max(months) <= 5 else "夏"
                    tname = "選抜" if season == "春" else "選手権"
                    full["title"] = f"{yyear}年 {tname}大会(甲子園・全{nteam}校)"
                    lbl = f"{yyear}年 {tname}(全{nteam}校)"
                    # 出場歴(何年ぶり/連続何回目)を各校に付与。
                    # 夏は「都道府県大会優勝=甲子園出場」なので所属県の優勝年基準で数える。
                    # 春(選抜)は選考制のため、当サイト収録(ベスト8以上)基準にフォールバック
                    for te in full["teams"]:
                        csrc = _cross_source_for(te["n"], pref_of_yagura.get(te["n"]) or pref_of.get(te["n"], ""))
                        if season == "夏" and csrc is not None:
                            te["app"] = csrc.appearance_as_champion(te["n"], yyear)
                        else:
                            te["app"] = src.appearance(te["n"], yyear, season)
                full["label"] = lbl
                full["champion"] = (full.get("center") or {}).get("champion", "")
                # 同年の既存(ベスト8)エントリを置換、無ければ先頭に挿入
                repl = None
                for i, t in enumerate(tournaments):
                    if t["title"].startswith(f"{yyear}年"):
                        repl = i
                        break
                # fullモードの校名にも順位注記辞書を使えるよう学校を登録
                for te in full["teams"]:
                    add_school(te["n"])
                if repl is not None:
                    tournaments[repl] = full
                else:
                    tournaments.insert(0, full)
                text_url = f"/{slug}/tournament/" if kind == "pref" else "/koshien/tournament/"
    if not tournaments:
        return None
    out = {"ownLabel": "県" if kind == "pref" else "総合",
            "crossLabel": "総合" if kind == "pref" else "県",
            "windows": BRACKET_WINDOWS, "defaultWindow": 20,
            "schools": schools, "tournaments": tournaments}
    if text_url:
        out["textUrl"] = text_url
    return out

def add_bracket(doc, kind, slug=None, self_page=False):
    """アプリページにブラケットのデータと描画スクリプトを注入"""
    data = _bracket_json(kind, slug)
    if data is None:
        return doc
    if self_page:
        data.pop("textUrl", None)
    if "js" not in _BRACKET_JS_CACHE:
        _BRACKET_JS_CACHE["js"] = open(os.path.join(ROOT, "tools", "bracket.js"), encoding="utf-8").read()
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    snippet = ("<script>window.__BRACKET__=" + payload + ";</script>"
               "<script>" + _BRACKET_JS_CACHE["js"] + "</script>")
    return doc.replace("</body>", snippet + "</body>", 1)


# ---------------- トーナメント速報の専用ページ ----------------

def _yagura_info(dirslug):
    """data/<dirslug>/yagura.json の要約(年・季節)。無ければNone"""
    path = os.path.join(ROOT, "data", dirslug, "yagura.json")
    if not os.path.exists(path):
        return None
    try:
        yg = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    if not yg.get("games"):
        return None
    dates = [str(g.get("date", "")) for g in yg["games"]
             if re.fullmatch(r"\d{8}", str(g.get("date", "")))]
    year = yg.get("year") or (int(max(dates)[:4]) if dates else None)
    if not year:
        return None
    months = {int(d[4:6]) for d in dates}
    season = "春" if months and max(months) <= 5 else "夏"
    return {"yg": yg, "year": year, "season": season}


def _fmt_mmdd(d):
    d = str(d or "")
    return f"{int(d[4:6])}月{int(d[6:8])}日" if re.fullmatch(r"\d{8}", d) else ""


def build_tournament_page(kind, slug=None, school_names=None, active=None):
    """最新大会の速報ページ(/{slug}/tournament/ ・ /koshien/tournament/)。
    トーナメント図(対話型)に加えて、検索エンジンが読めるテキストの結果一覧を載せる"""
    dirslug = slug if kind == "pref" else "koshien"
    info = _yagura_info(dirslug)
    if not info:
        return None
    yg, year, season = info["yg"], info["year"], info["season"]
    nteam_s = f"全{yg['team_count']}校" if yg.get("team_count") else ""
    if kind == "pref":
        name = PREF_NAME[slug]
        tourname = f"夏の高校野球 {name}大会"
        urlpath = f"/{slug}/tournament/"
        outdir = os.path.join(ROOT, slug, "tournament")
        back = f'<a href="/{slug}/">{name}大会トップ(通算ランキング)</a>'
        nav = (f'<a href="/{slug}/">{name}大会トップ</a>'
               f'<a href="/{slug}/schools/">学校別戦績</a><a href="/{slug}/years/">年度別結果</a>')
    else:
        tourname = "春の甲子園(選抜大会)" if season == "春" else "夏の甲子園(選手権大会)"
        urlpath = "/koshien/tournament/"
        outdir = os.path.join(ROOT, "koshien", "tournament")
        back = '<a href="/">春夏総合ランキング(トップページ)</a>'
        nav = '<a href="/">春夏総合ランキング</a>'
    h1 = f"{year}年 {tourname} トーナメント表・結果速報"

    def team_html(nm, pref):
        if kind == "pref":
            if school_names and nm in school_names:
                return f'<a href="/{slug}/schools/{esc(nm)}">{esc(nm)}</a>'
            return esc(nm)
        label = f"{nm}({pref})" if pref else nm
        sg = _PREF_SLUG.get(pref)
        if sg and active and sg in active:
            return f'<a href="/{sg}/">{esc(label)}</a>'
        return esc(label)

    played, upcoming, order = {}, [], {}
    champion = ""
    for g in yg["games"]:
        a, b = (g.get("a") or "").strip(), (g.get("b") or "").strip()
        if not (a and b):
            continue
        rnd = g.get("round") or ""
        num = int(g.get("num") or 0)
        try:
            sa, sb = int(g["as"]), int(g["bs"])
        except (KeyError, ValueError, TypeError):
            upcoming.append((num, rnd, g.get("date"), a, g.get("ap", ""), b, g.get("bp", "")))
            continue
        order[rnd] = min(order.get(rnd, num), num)
        played.setdefault(rnd, []).append((num, g.get("date"), a, g.get("ap", ""), sa, sb, b, g.get("bp", "")))
        if rnd == "決勝":
            champion = a if sa > sb else b

    secs = []
    for rnd in sorted(played, key=lambda r: -order[r]):   # 決勝側(最新)から
        trs = []
        for num, d, a, ap, sa, sb, b, bp in sorted(played[rnd], key=lambda t: t[0]):
            ah, bh = team_html(a, ap), team_html(b, bp)
            if sa >= sb:
                ah = f"<b>{ah}</b>"
            if sb >= sa:
                bh = f"<b>{bh}</b>"
            trs.append(f'<tr><td>{_fmt_mmdd(d)}</td><td>{ah}</td>'
                       f'<td class="num" style="white-space:nowrap">{sa} - {sb}</td><td>{bh}</td></tr>')
        secs.append(f"<h2>{esc(rnd)}の結果</h2>"
                    '<div class="tablewrap"><table><tr><th>日付</th><th>学校</th>'
                    '<th class="num">スコア</th><th>学校</th></tr>' + "".join(trs) + "</table></div>")

    up_html = ""
    if upcoming:
        trs = [f'<tr><td>{_fmt_mmdd(d)}</td><td>{esc(rnd)}</td>'
               f'<td>{team_html(a, ap)} × {team_html(b, bp)}</td></tr>'
               for num, rnd, d, a, ap, b, bp in sorted(upcoming)]
        up_html = ('<h2>今後の対戦カード(組み合わせ)</h2>'
                   '<div class="tablewrap"><table><tr><th>日付</th><th>回戦</th><th>対戦</th></tr>'
                   + "".join(trs) + "</table></div>")

    champ_line = f"<p>優勝: <b>{esc(champion)}</b></p>" if champion else ""
    body = (f"<h1>{esc(h1)}</h1>"
            f"<p>{year}年の{tourname}のトーナメント表(組み合わせ)と試合結果の速報ページです"
            + (f"({nteam_s})" if nteam_s else "") +
            "。結果は毎日自動で更新されます。トーナメント図の校名の脇には通算ランキングでの順位も表示しています。"
            f"通算成績や過去の大会結果は{back}へ。</p>"
            + champ_line +
            '<div id="bracket-root" style="margin:16px 0"></div>'
            + up_html + "".join(secs))
    desc = (f"{year}年 {tourname}のトーナメント表(組み合わせ)と試合結果の速報。"
            + (f"{nteam_s}の" if nteam_s else "") +
            "各試合のスコアと勝ち上がりを毎日更新。学校別の通算成績ランキングも掲載。")
    out = page(f"{h1} | {SITE_NAME}", desc, urlpath, body, nav)
    out = add_bracket(out, kind, slug, self_page=True)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    return urlpath


# ---------------- 甲子園ライブ配信ウィジェット(トップページ) ----------------

def add_live_widget(doc):
    """試合中はライブ配信リンク、普段は次の試合日時を表示。
    日程は data/koshien/schedule.json(tools/koshien_schedule.py が毎日更新)、
    表示・判定ロジックは tools/live_widget.html(プレースホルダ置換で注入)"""
    sp = os.path.join(ROOT, "data", "koshien", "schedule.json")
    tp = os.path.join(ROOT, "tools", "live_widget.html")
    if not os.path.exists(sp) or not os.path.exists(tp):
        return doc
    days = json.load(open(sp, encoding="utf-8")).get("days") or []
    if not days:
        return doc
    snippet = open(tp, encoding="utf-8").read().replace(
        "__SCHEDULE_JSON__", json.dumps(days, ensure_ascii=False, separators=(",", ":")))
    return doc.replace("<body>", "<body>" + snippet, 1)

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
    paths = ["/", "/about", "/privacy", "/disclaimer", "/contact"]
    for slug in active:
        paths += build_pref(slug)
    has_koshien = build_top(active)
    tp = build_tournament_page("top", active=set(active))
    if tp:
        paths.append(tp)
    n = build_sitemap(paths)
    print(f"OK: 都道府県 {len(active)} ({', '.join(active)}) / 甲子園データ: {'あり' if has_koshien else '準備中'} / sitemap {n} URLs")

if __name__ == "__main__":
    main()
