# -*- coding: utf-8 -*-
"""koyaページのパーサ: ヘッダー(大会名/回/年) + 全試合一覧(回戦,地区,校名,スコア)を抽出"""
import os, re, glob, json
from html.parser import HTMLParser

ROUNDS = {"1回戦", "2回戦", "3回戦", "準々決勝", "準決勝", "決勝",
          "１回戦", "２回戦", "３回戦"}

class GridParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.cur_row = None
        self.cur_cell = None
        self.cell_attrs = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.cur_row = []
        elif tag == "td" and self.cur_row is not None:
            d = dict(attrs)
            self.cell_attrs = (int(d.get("colspan", 1)), int(d.get("rowspan", 1)))
            self.cur_cell = []

    def handle_endtag(self, tag):
        if tag == "tr" and self.cur_row is not None:
            self.rows.append(self.cur_row)
            self.cur_row = None
        elif tag == "td" and self.cur_cell is not None:
            text = "".join(self.cur_cell)
            text = re.sub(r"[\s 　]+", "", text)
            self.cur_row.append((text, self.cell_attrs[0], self.cell_attrs[1]))
            self.cur_cell = None

    def handle_data(self, data):
        if self.cur_cell is not None:
            self.cur_cell.append(data)

def row_cells(path):
    """各行の (col, text) リストを返す(rowspan/colspan展開)"""
    raw = open(path, "rb").read()
    html = raw.decode("shift_jis", errors="replace")
    p = GridParser()
    p.feed(html)
    occupied = {}
    rows_out = []
    for r, row in enumerate(p.rows):
        c = 0
        cells = []
        for text, cs, rs in row:
            while occupied.get((r, c)):
                c += 1
            for dr in range(rs):
                for dc in range(cs):
                    occupied[(r + dr, c + dc)] = True
            if text:
                cells.append((c, text))
            c += cs
        rows_out.append(cells)
    return rows_out

Z2H = str.maketrans("0123456789()", "0123456789()")

def norm(s):
    return s.translate(Z2H)

def parse_page(path):
    rows = row_cells(path)
    meta = {"kai": None, "name": None, "year": None}
    games = []
    for cells in rows:
        texts = [norm(t) for _, t in cells]
        joined = "".join(texts)
        # ヘッダー: 第 N 回 <大会名> YYYY(昭NN)年
        if meta["year"] is None:
            m = re.search(r"第(\d+)回", joined)
            y = re.search(r"(\d{4})\(", joined)
            if m and y and ("選抜" in joined or "選手権" in joined):
                meta["kai"] = int(m.group(1))
                meta["name"] = "春" if "選抜" in joined else "夏"
                meta["year"] = int(y.group(1))
        # 試合行: [回戦, (地区A), 校A, sA, -, sB, 校B, (地区B), ...]
        if texts and texts[0] in ROUNDS:
            try:
                seq = texts[1:]
                # (地区A)
                da = seq[0] if seq[0].startswith("(") else None
                i = 1 if da else 0
                team_a = seq[i]; i += 1
                sa = seq[i]; i += 1
                if seq[i] == "-": i += 1
                sb = seq[i]; i += 1
                team_b = seq[i]; i += 1
                db = seq[i] if i < len(seq) and seq[i].startswith("(") else None
                rd = texts[0].replace("１", "1").replace("２", "2").replace("３", "3")
                games.append({
                    "round": rd,
                    "a": team_a, "as": sa, "b": team_b, "bs": sb,
                    "da": (da or "").strip("()"), "db": (db or "").strip("()"),
                })
            except (IndexError, ValueError):
                pass
    return meta, games

if __name__ == "__main__":
    import io, sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "koya")
    target = sys.argv[1] if len(sys.argv) > 1 else "2431"
    meta, games = parse_page(os.path.join(DIR, f"{target}.htm"))
    print(meta)
    for g in games:
        print(g["round"], g["da"], g["a"], g["as"], "-", g["bs"], g["b"], g["db"])
