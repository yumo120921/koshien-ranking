# -*- coding: utf-8 -*-
"""
埼玉高校野球 通算ランキング — サイトビルドスクリプト

データソース:
  data/results.csv  … 年度別成績(年,ブロック,優勝,準優勝,ベスト4×2,ベスト8×4,決勝勝者得点,決勝敗者得点)
  data/scores.json  … 準々決勝以降のスコア詳細("年|ブロック" → {qf,sf,f})

生成物:
  index.html        … アプリ本体(app_template.html にデータを注入)
  schools/*.html    … 学校別戦績ページ + schools/index.html(一覧)
  years/*.html      … 年度別結果ページ + years/index.html(一覧)
  sitemap.xml

使い方: data/ を編集したら  python build.py  → git add -A / commit / push
"""
import csv, json, html, os, re, shutil
from collections import defaultdict
from datetime import date
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE_URL = "https://koshien-ranking.com"
SITE_NAME = "埼玉高校野球 通算ランキング"
TOURNAMENT = "夏の高校野球 埼玉大会"

# ---------------- データ読み込み ----------------

def load_rows():
    rows = []
    with open(os.path.join(ROOT, "data", "results.csv"), encoding="utf-8") as f:
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

def load_scores():
    with open(os.path.join(ROOT, "data", "scores.json"), encoding="utf-8") as f:
        return json.load(f)

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
"""

FOOTER = ('<footer><nav>'
          '<a href="/schools/">学校別戦績</a>|<a href="/years/">年度別結果</a>|'
          '<a href="/about.html">サイトについて</a>|<a href="/privacy.html">プライバシーポリシー</a>|'
          '<a href="/disclaimer.html">免責事項</a>|<a href="/contact.html">お問い合わせ</a></nav>'
          f'<p style="margin:6px 0 0">&copy; 2026 {SITE_NAME}</p></footer>')

def esc(s):
    return html.escape(str(s), quote=True)

def page(title, desc, canonical_path, body):
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)} | {SITE_NAME}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE_URL}{quote(canonical_path)}">
<style>{CSS}</style>
</head>
<body>
<header><a href="/">{SITE_NAME}</a>
<nav><a href="/schools/">学校別戦績</a><a href="/years/">年度別結果</a></nav></header>
<main>
{body}
</main>
{FOOTER}
</body>
</html>
"""

def school_href(name):
    return f"/schools/{name}.html"

def school_link(name):
    return f'<a href="{esc(school_href(name))}">{esc(name)}</a>' if name else ""

def year_label(row):
    return row["year"] + (f"({row['block']})" if row["block"] else "")

def year_href(year):
    return f"/years/{year}.html"

# ---------------- 集計 ----------------

RANKS = [("ch", "優勝"), ("ru", "準優勝"), ("b4", "ベスト4"), ("b8", "ベスト8")]

def school_records(rows):
    rec = defaultdict(list)  # name -> [(row, rank_label)]
    for r in rows:
        if r["ch"]: rec[r["ch"]].append((r, "優勝"))
        if r["ru"]: rec[r["ru"]].append((r, "準優勝"))
        for s in r["b4"]: rec[s].append((r, "ベスト4"))
        for s in r["b8"]: rec[s].append((r, "ベスト8"))
    return rec

# ---------------- 生成: 学校ページ ----------------

def build_school_pages(rows, rec):
    outdir = os.path.join(ROOT, "schools")
    shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir)

    for name, entries in rec.items():
        entries.sort(key=lambda e: (int(e[0]["year"]), e[0]["block"]))
        counts = {label: sum(1 for _, l in entries if l == label) for _, label in RANKS}
        first = entries[0][0]["year"]
        last = entries[-1][0]["year"]

        cards = "".join(
            f'<div class="card"><b>{counts[label]}</b><span>{label}</span></div>'
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

        summary_bits = [f"{label} {counts[label]}回" for _, label in RANKS if counts[label]]
        desc = (f"{name}の{TOURNAMENT}戦績。{('、'.join(summary_bits))}"
                f"(ベスト8以上{len(entries)}回、{first}年〜{last}年)。年度別の成績一覧。")

        body = (f"<h1>{esc(name)} の戦績</h1>"
                f"<p>{esc(name)}の{TOURNAMENT}におけるベスト8以上の成績一覧です"
                f"(初出は{first}年、直近は{last}年)。</p>"
                f'<div class="cards">{cards}</div>'
                f"<h2>年度別成績</h2>{table}"
                '<p class="note">※ 1961〜1974年のA・Bおよび1998・2008・2018年の東西南北は、'
                '大会がブロック制で行われた年度の各ブロックを表します。</p>')

        with open(os.path.join(outdir, f"{name}.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(page(f"{name} の戦績", desc, school_href(name), body))

    # 一覧(通算ランキング表)
    order = sorted(rec.items(), key=lambda kv: (
        -sum(1 for _, l in kv[1] if l == "優勝"),
        -sum(1 for _, l in kv[1] if l == "準優勝"),
        -len(kv[1]), kv[0]))
    trs = []
    for i, (name, entries) in enumerate(order, 1):
        cnt = {label: sum(1 for _, l in entries if l == label) for _, label in RANKS}
        trs.append(f'<tr><td class="num">{i}</td><td>{school_link(name)}</td>'
                   f'<td class="num">{cnt["優勝"]}</td><td class="num">{cnt["準優勝"]}</td>'
                   f'<td class="num">{cnt["ベスト4"]}</td><td class="num">{cnt["ベスト8"]}</td>'
                   f'<td class="num">{len(entries)}</td></tr>')
    table = ('<div class="tablewrap"><table>'
             '<tr><th class="num">#</th><th>学校</th><th class="num">優勝</th><th class="num">準優勝</th>'
             '<th class="num">ベスト4</th><th class="num">ベスト8</th><th class="num">B8以上計</th></tr>'
             + "".join(trs) + "</table></div>")
    body = (f"<h1>学校別 通算成績一覧</h1>"
            f"<p>{TOURNAMENT}のベスト8以上に入った全{len(order)}校の通算成績です。"
            f"学校名をクリックすると年度別の詳細が見られます。"
            f'トップページの<a href="/">通算ランキング</a>では条件を変えた集計もできます。</p>'
            + table)
    desc = f"{TOURNAMENT}の学校別通算成績一覧。優勝・準優勝・ベスト4・ベスト8の回数を全{len(order)}校分掲載。"
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page("学校別 通算成績一覧", desc, "/schools/", body))
    return [name for name, _ in rec.items()]

# ---------------- 生成: 年度ページ ----------------

def games_table(caption, games):
    trs = []
    for g in games:
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

def build_year_pages(rows, scores):
    outdir = os.path.join(ROOT, "years")
    shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir)

    by_year = defaultdict(list)
    for r in rows:
        by_year[r["year"]].append(r)
    years = sorted(by_year.keys(), key=int)

    for idx, y in enumerate(years):
        yrows = sorted(by_year[y], key=lambda r: r["block"])
        sections = []
        champs = []
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
                sec += games_table(f"{pre}準決勝", th.get("sf") or [])
                sec += games_table(f"{pre}準々決勝", th.get("qf") or [])
            sections.append(sec)

        prev_a = f'<a href="{year_href(years[idx-1])}">&laquo; {years[idx-1]}年</a>' if idx > 0 else "<span></span>"
        next_a = f'<a href="{year_href(years[idx+1])}">{years[idx+1]}年 &raquo;</a>' if idx < len(years)-1 else "<span></span>"
        pager = f'<div class="pager">{prev_a}<a href="/years/">年度一覧</a>{next_a}</div>'

        note = ""
        if len(yrows) > 1:
            note = ('<p class="note">※ この年度は大会がブロック制(複数代表)で行われたため、'
                    'ブロックごとに掲載しています。</p>')

        body = (f"<h1>{y}年 {TOURNAMENT} の結果</h1>"
                f"<p>{y}年の{TOURNAMENT}のベスト8以上の結果です。優勝は{esc('、'.join(champs))}。</p>"
                + note + "".join(sections) + pager)
        desc = f"{y}年{TOURNAMENT}の結果。優勝{('、'.join(champs))}。ベスト8以上の成績と準々決勝以降のスコア。"
        with open(os.path.join(outdir, f"{y}.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(page(f"{y}年 {TOURNAMENT} の結果", desc, year_href(y), body))

    # 一覧
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
    body = (f"<h1>年度別 結果一覧</h1>"
            f"<p>{TOURNAMENT}の{years[0]}年から{years[-1]}年までの決勝結果一覧です。"
            f"年をクリックするとベスト8以上の詳細が見られます。</p>" + table)
    desc = f"{TOURNAMENT}の年度別結果一覧({years[0]}年〜{years[-1]}年)。歴代優勝校・準優勝校と決勝スコア。"
    with open(os.path.join(outdir, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(page("年度別 結果一覧", desc, "/years/", body))
    return years

# ---------------- 生成: index.html(アプリ) ----------------

def build_app(rows_text, scores):
    tpl = open(os.path.join(ROOT, "app_template.html"), encoding="utf-8").read()
    assert "__IH_CSV__" in tpl and "__TH_JSON__" in tpl
    for bad in ("`", "${"):
        assert bad not in rows_text, f"CSVに使用できない文字が含まれています: {bad}"
    th_js = json.dumps(scores, ensure_ascii=False, separators=(",", ":"))
    out = tpl.replace("__IH_CSV__", rows_text).replace("__TH_JSON__", th_js)
    with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8", newline="") as f:
        f.write(out)

# ---------------- 生成: sitemap ----------------

def build_sitemap(school_names, years):
    today = date.today().isoformat()
    paths = ["/", "/schools/", "/years/", "/about.html", "/privacy.html",
             "/disclaimer.html", "/contact.html"]
    paths += [school_href(n) for n in sorted(school_names)]
    paths += [year_href(y) for y in years]
    urls = "\n".join(
        f"  <url><loc>{BASE_URL}{quote(p)}</loc><lastmod>{today}</lastmod></url>"
        for p in paths)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + urls + "\n</urlset>\n")
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(xml)
    return len(paths)

# ---------------- main ----------------

def main():
    rows = load_rows()
    scores = load_scores()
    rows_text = open(os.path.join(ROOT, "data", "results.csv"), encoding="utf-8").read().strip()

    # 整合性チェック
    keys = {f"{r['year']}|{r['block']}" for r in rows}
    orphan = [k for k in scores if k not in keys]
    missing = sorted(k for k in keys if k not in scores)
    if orphan:
        print("[warn] scores.json にあるが results.csv にない大会:", orphan)
    if missing:
        print("[info] スコア詳細が未登録の大会:", missing)

    rec = school_records(rows)
    build_app(rows_text, scores)
    names = build_school_pages(rows, rec)
    years = build_year_pages(rows, scores)
    n = build_sitemap(names, years)
    print(f"OK: 大会 {len(rows)} / 学校ページ {len(names)} / 年度ページ {len(years)} / sitemap {n} URLs")

if __name__ == "__main__":
    main()
