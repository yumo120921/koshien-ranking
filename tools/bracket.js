/* トーナメントタブの描画+アニメーション(全ページ共通・自己構結)
   データはビルド時に window.__BRACKET__ として注入される。
   大会エントリ: 旧来のベスト8形式(teams/games)と、全校形式(type:"full"、
   座標・パスはビルド時にPython側で計算済み)の2種類がある */
(function () {
  "use strict";
  var B = window.__BRACKET__;
  if (!B) return;
  var REDUCED = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ベスト8レイアウト定数(viewBox座標) */
  var W8 = 1100, H8 = 560;
  var X0L = 254, X1L = 356, X2L = 458, XC8 = 550;
  var X0R = W8 - X0L, X1R = W8 - X1L, X2R = W8 - X2L;
  var TY = [100, 210, 340, 450];
  var MID = [(TY[0] + TY[1]) / 2, (TY[2] + TY[3]) / 2];
  var SFY = (MID[0] + MID[1]) / 2;
  var BLACK = "#1e293b", RED = "#dc2626", SUB = "#64748b";

  function el(tag, attrs, parent) {
    var e = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  function rankText(name, w) {
    var sc = B.schools[name] || { own: {}, cross: {} };
    var o = sc.own[w], c = sc.cross[w];
    var t1 = B.ownLabel + (o ? o + "位" : "圏外");
    var t2 = (sc.crossLabel || B.crossLabel) + (c ? c + "位" : "圏外");
    return t1 + " ／ " + t2;
  }

  function rankShort(name, w) {
    var sc = B.schools[name];
    var o = sc && sc.own[w];
    return o ? B.ownLabel + o + "位" : "";
  }

  function rankTriple(name, w, app) {
    var sc = B.schools[name] || { own: {}, cross: {} };
    var o = sc.own[w], c = sc.cross[w];
    var parts = [B.ownLabel + (o ? o + "位" : "圏外"),
                 (sc.crossLabel || B.crossLabel) + (c ? c + "位" : "圏外")];
    if (app) parts.push(app);
    return parts.join("/");
  }

  function render(root, ti) {
    ti = ti || 0;
    var T = B.tournaments[ti];
    var isFull = T.type === "full";
    root.innerHTML = "";
    root.dataset.done = "1";
    var wrap = document.createElement("div");
    wrap.style.cssText = "background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px 12px 8px;";
    root.appendChild(wrap);

    /* ヘッダ: タイトル + 大会/期間プルダウン + 再生 */
    var head = document.createElement("div");
    head.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 4px 6px;";
    head.innerHTML =
      '<div style="font-weight:bold;font-size:16px;color:#14532d">' + T.title + "</div>" +
      '<select id="bkt-tour" style="border:1px solid #cbd5e1;border-radius:6px;padding:3px 6px;font-size:12px">' +
      B.tournaments.map(function (t, i) {
        return '<option value="' + i + '"' + (i === ti ? " selected" : "") + ">" + t.label + "</option>";
      }).join("") + "</select>" +
      (B.textUrl ? '<a href="' + B.textUrl + '" style="font-size:12px;color:#1d4ed8;white-space:nowrap">結果一覧・速報ページ</a>' : "") +
      '<div style="margin-left:auto;display:flex;align-items:center;gap:6px;font-size:12px;color:#475569">' +
      "順位の集計期間 <select id=\"bkt-win\" style=\"border:1px solid #cbd5e1;border-radius:6px;padding:3px 6px;font-size:12px\">" +
      B.windows.map(function (w) {
        return '<option value="' + w + '"' + (w === B.defaultWindow ? " selected" : "") + ">" +
          (w ? "直近" + w + "年" : "全期間") + "</option>";
      }).join("") +
      '</select><button id="bkt-replay" style="border:1px solid #cbd5e1;background:#fff;border-radius:6px;padding:3px 10px;font-size:12px;cursor:pointer">▶ 再生</button></div>';
    wrap.appendChild(head);

    var scroller = document.createElement("div");
    scroller.style.cssText = "overflow-x:auto;overflow-y:auto;max-height:82vh;";
    wrap.appendChild(scroller);
    var vw = isFull ? T.W : W8, vh = isFull ? T.H : H8;
    var svg = el("svg", { viewBox: "0 0 " + vw + " " + vh,
      style: "min-width:760px;width:100%;display:block" }, scroller);

    var note = document.createElement("p");
    note.style.cssText = "margin:6px 4px 4px;font-size:11px;color:#94a3b8";
    note.textContent = isFull
      ? "※ 全出場校のトーナメント(毎日自動更新)。順位は現在(最新年時点)のランキング、回数は当サイト収録の都道府県大会優勝記録から算出(収録範囲外の古い出場は含まない)。"
      : "※ 出場回数・年数は当サイト収録データ(ベスト8以上)基準。順位は現在(最新年時点)のランキング。";
    wrap.appendChild(note);

    /* 共通: スライドインCSS */
    var css = document.createElementNS("http://www.w3.org/2000/svg", "style");
    css.textContent =
      "@keyframes bktin{to{opacity:1;transform:translateX(0)}}" +
      ".bteam{opacity:0;animation:bktin .45s ease-out forwards}" +
      ".bL{transform:translateX(-70px)}.bR{transform:translateX(70px)}" +
      (REDUCED ? ".bteam{animation-duration:.01s}" : "");
    svg.appendChild(css);

    /* 共通: パスのアニメーション */
    function drawPath(d, color, width) {
      return el("path", { d: d, stroke: color, "stroke-width": width, fill: "none", "stroke-linecap": "square", "stroke-linejoin": "miter" }, svg);
    }
    function animatePath(p, dur, delay) {
      var len = p.getTotalLength();
      p.style.strokeDasharray = len;
      if (REDUCED) { p.style.strokeDashoffset = 0; return; }
      if (p.animate) {
        p.style.strokeDashoffset = 0;
        p.animate([{ strokeDashoffset: len }, { strokeDashoffset: 0 }],
                  { duration: dur, delay: delay, easing: "linear", fill: "backwards" });
      } else {
        p.style.strokeDashoffset = len;
        void p.getBoundingClientRect();
        p.style.transition = "stroke-dashoffset " + dur + "ms linear " + delay + "ms";
        void p.getBoundingClientRect();
        p.style.strokeDashoffset = 0;
      }
    }

    /* 共通: スコアラベル(0からのカウントアップ) */
    var scoreNodes = [];
    function scoreLabel(x, y, game, fs) {
      var g = el("g", { opacity: 0 }, svg);
      var t = el("text", { x: x, y: y, "text-anchor": "middle", "font-size": fs, "font-family": "sans-serif", "font-weight": "bold" }, g);
      var s0 = el("tspan", { fill: game.w === 0 ? RED : BLACK }, t);
      var sep = el("tspan", { fill: "#94a3b8" }, t); sep.textContent = "-";
      var s1 = el("tspan", { fill: game.w === 1 ? RED : BLACK }, t);
      s0.textContent = "0"; s1.textContent = "0";
      scoreNodes.push({ g: g, s0: s0, s1: s1, game: game });
      return scoreNodes.length - 1;
    }
    function showScore(idx) {
      var n = scoreNodes[idx];
      n.g.setAttribute("opacity", 1);
      if (REDUCED) { n.s0.textContent = n.game.s[0]; n.s1.textContent = n.game.s[1]; return; }
      var t0 = performance.now(), D = 380;
      function tick(now) {
        var r = Math.max(0, Math.min(1, (now - t0) / D)); r = 1 - (1 - r) * (1 - r);
        n.s0.textContent = Math.round(n.game.s[0] * r);
        n.s1.textContent = Math.round(n.game.s[1] * r);
        if (r < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    }

    /* イベント(モード共通) */
    head.querySelector("#bkt-win").addEventListener("change", function () {
      var w = this.value;
      svg.querySelectorAll(".bkt-rank").forEach(function (t) { t.textContent = rankText(t.__name, w); });
      svg.querySelectorAll(".bkt-rankfull").forEach(function (t) {
        var r = rankShort(t.__name, w);
        if (t.__app) { t.textContent = rankTriple(t.__name, w, t.__app); }
        else { t.textContent = r ? (t.__side === "R" ? r + "　" : "　" + r) : ""; }
      });
    });
    head.querySelector("#bkt-tour").addEventListener("change", function () { render(root, +this.value); });
    head.querySelector("#bkt-replay").addEventListener("click", function () { render(root, ti); });

    if (isFull) { renderFull(); return; }
    renderQF8();

    /* ---------- 全校モード(座標はビルド時計算済み) ---------- */
    function renderFull() {
      var stagger = REDUCED ? 0 : Math.min(8, 700 / Math.max(1, T.teams.length));
      T.teams.forEach(function (t, i) {
        var isL = t.cs ? t.cs === "L" : t.an === "start";
        var g = el("g", { "class": "bteam " + (isL ? "bL" : "bR") }, svg);
        g.style.animationDelay = (REDUCED ? 0 : (i % (T.teams.length / 2 | 0)) * stagger / 1000) + "s";
        var txt = el("text", { x: t.x, y: t.y + 4, "text-anchor": t.an, "font-size": 12,
          "font-weight": "bold", fill: "#0f172a", "font-family": "sans-serif" }, g);
        if (t.c) { txt.textContent = t.n; txt.setAttribute("font-size", 11.5); return; }
        var r0 = rankShort(t.n, String(B.defaultWindow));
        if (t.app) {
          // 甲子園: 校名の下に「総合〇位/県〇位/〇年ぶり〇回目」を1行で
          txt.textContent = t.n;
          var t2 = el("text", { x: t.x, y: t.y + 14.5, "text-anchor": t.an, "font-size": 9,
            fill: SUB, "font-family": "sans-serif", "class": "bkt-rankfull" }, g);
          t2.__name = t.n;
          t2.__app = t.app;
          t2.textContent = rankTriple(t.n, String(B.defaultWindow), t.app);
        } else {
          // 県: 順位は常にトーナメント図側: 左側=校名の右、右側=校名の左
          var rs = el("tspan", { "font-size": 9.5, "font-weight": "normal", fill: SUB, "class": "bkt-rankfull" });
          rs.__name = t.n;
          rs.__side = isL ? "L" : "R";
          var nm = el("tspan", {});
          nm.textContent = t.n;
          rs.textContent = r0 ? (isL ? "　" + r0 : r0 + "　") : "";
          if (isL) { txt.appendChild(nm); txt.appendChild(rs); }
          else { txt.appendChild(rs); txt.appendChild(nm); }
        }
      });
      (T.labels || []).forEach(function (l) {
        el("text", { x: l.x, y: l.y, "text-anchor": "middle", "font-size": 10,
          fill: SUB, "font-family": "sans-serif" }, svg).textContent = l.t;
      });
      var T_TEAM = REDUCED ? 0 : 750;
      var D_LV = 240, GAP_LV = 60;
      var maxBLv = 0, maxRLv = 0;
      T.blacks.forEach(function (b) { if (b.lv > maxBLv) maxBLv = b.lv; });
      T.reds.forEach(function (r) { if (r.lv > maxRLv) maxRLv = r.lv; });
      T.blacks.forEach(function (b) {
        animatePath(drawPath(b.d, BLACK, 1.6), D_LV, T_TEAM + b.lv * (D_LV + GAP_LV));
      });
      var T_RED = T_TEAM + (maxBLv + 1) * (D_LV + GAP_LV) + 200;
      var R_LV = 300, RGAP = 80;
      T.reds.forEach(function (r) {
        animatePath(drawPath(r.d, RED, 2.6), R_LV, T_RED + r.lv * (R_LV + RGAP));
      });
      T.scores.forEach(function (s) {
        var g = el("g", { opacity: 0 }, svg);
        var t = el("text", { x: s.x, y: s.y, "text-anchor": s.an || "middle",
          "font-size": 10, "font-family": "sans-serif", "font-weight": "bold",
          fill: s.w ? RED : BLACK }, g);
        t.textContent = REDUCED ? s.v : "0";
        setTimeout(function () {
          g.setAttribute("opacity", 1);
          if (REDUCED) return;
          var t0 = performance.now(), D = 380;
          (function tick(now) {
            var r = Math.max(0, Math.min(1, (now - t0) / D));
            r = 1 - (1 - r) * (1 - r);
            t.textContent = Math.round(s.v * r);
            if (r < 1) requestAnimationFrame(tick);
          })(performance.now());
        }, REDUCED ? 0 : T_RED + s.lv * (R_LV + RGAP) + R_LV * 0.55);
      });
      var C = T.center || {};
      if (C.x) {
        el("text", { x: C.x, y: (C.poleTop || 50) - 26, "text-anchor": "middle", "font-size": 13, fill: SUB, "font-family": "sans-serif" }, svg)
          .textContent = "決勝";
        if (C.champion) {
          var champG = el("g", { opacity: 0 }, svg);
          el("text", { x: C.x, y: (C.poleTop || 50) - 8, "text-anchor": "middle", "font-size": 15, fill: RED, "font-family": "sans-serif", "font-weight": "bold" }, champG)
            .textContent = "🏆 " + C.champion + " 優勝";
          var TF = T_RED + (maxRLv + 1) * (R_LV + RGAP) + 150;
          setTimeout(function () { champG.setAttribute("opacity", 1); }, REDUCED ? 0 : TF);
        }
      }
    }

    /* ---------- ベスト8モード(従来) ---------- */
    function renderQF8() {
      function teamG(team, side, i) {
        var y = TY[i], g = el("g", { "class": "bteam " + (side === "L" ? "bL" : "bR") }, svg);
        g.style.animationDelay = (REDUCED ? 0 : i * 0.09 + (side === "R" ? 0.05 : 0)) + "s";
        var x = side === "L" ? 10 : W8 - 10, anchor = side === "L" ? "start" : "end";
        el("text", { x: x, y: y - 2, "text-anchor": anchor, "font-size": 16, "font-weight": "bold", fill: "#0f172a", "font-family": "sans-serif" }, g)
          .textContent = team.name;
        var t2 = el("text", { x: x, y: y + 15, "text-anchor": anchor, "font-size": 10.5, fill: SUB, "font-family": "sans-serif", "class": "bkt-rank" }, g);
        t2.textContent = rankText(team.name, String(B.defaultWindow));
        t2.__name = team.name;
        el("text", { x: x, y: y + 29, "text-anchor": anchor, "font-size": 10.5, fill: SUB, "font-family": "sans-serif" }, g)
          .textContent = "ベスト8: " + team.app;
      }
      T.teams.L.forEach(function (t, i) { teamG(t, "L", i); });
      T.teams.R.forEach(function (t, i) { teamG(t, "R", i); });

      function pathsFor(side) {
        var x0 = side === "L" ? X0L : X0R, x1 = side === "L" ? X1L : X1R, x2 = side === "L" ? X2L : X2R;
        var P = { black: [], redQF: [], redSF: null };
        for (var i = 0; i < 4; i++) P.black.push("M" + x0 + " " + TY[i] + " L" + x1 + " " + TY[i]);
        for (var p = 0; p < 2; p++) {
          P.black.push("M" + x1 + " " + TY[p * 2] + " L" + x1 + " " + TY[p * 2 + 1]);
          P.black.push("M" + x1 + " " + MID[p] + " L" + x2 + " " + MID[p]);
        }
        P.black.push("M" + x2 + " " + MID[0] + " L" + x2 + " " + MID[1]);
        P.black.push("M" + x2 + " " + SFY + " L" + XC8 + " " + SFY);
        var games = T.games[side];
        for (var q = 0; q < 2; q++) {
          var wIdx = games.qf[q].w, wy = TY[q * 2 + wIdx];
          P.redQF.push("M" + x0 + " " + wy + " L" + x1 + " " + wy + " L" + x1 + " " + MID[q] + " L" + x2 + " " + MID[q]);
        }
        var sfW = games.sf.w, wy2 = MID[sfW];
        P.redSF = "M" + x2 + " " + wy2 + " L" + x2 + " " + SFY + " L" + XC8 + " " + SFY;
        return P;
      }
      var PL = pathsFor("L"), PR = pathsFor("R");
      var champSide = T.games.f.w === 0 ? "L" : "R";

      var scoreIdx = { L: [], R: [] }, sfIdx = {}, fIdx;
      ["L", "R"].forEach(function (side) {
        var x1 = side === "L" ? X1L : X1R, x2 = side === "L" ? X2L : X2R;
        for (var q = 0; q < 2; q++) scoreIdx[side].push(scoreLabel(x1, MID[q] - 8, T.games[side].qf[q], 14));
        sfIdx[side] = scoreLabel(x2, SFY - 8, T.games[side].sf, 14);
      });
      fIdx = scoreLabel(XC8, SFY + 42, T.games.f, 22);

      el("text", { x: XC8, y: SFY - 60, "text-anchor": "middle", "font-size": 13, fill: SUB, "font-family": "sans-serif" }, svg).textContent = "決勝";
      var champG = el("g", { opacity: 0 }, svg);
      el("text", { x: XC8, y: SFY - 36, "text-anchor": "middle", "font-size": 15, fill: RED, "font-family": "sans-serif", "font-weight": "bold" }, champG)
        .textContent = "🏆 " + T.champion + " 優勝";

      var T_TEAM = REDUCED ? 0 : 650;
      var D_H = 420, D_J = 380, D_C = 350;
      [PL, PR].forEach(function (P) {
        P.blackEls = P.black.map(function (d) { return drawPath(d, BLACK, 2); });
      });
      [PL, PR].forEach(function (P) {
        P.blackEls.slice(0, 4).forEach(function (p) { animatePath(p, D_H, T_TEAM); });
        P.blackEls.slice(4, 8).forEach(function (p) { animatePath(p, D_J, T_TEAM + D_H); });
        P.blackEls.slice(8).forEach(function (p) { animatePath(p, D_C, T_TEAM + D_H + D_J); });
      });
      var T_RED = T_TEAM + D_H + D_J + D_C + 150;
      var R_QF = 700, R_SF = 550;
      [["L", PL], ["R", PR]].forEach(function (sp) {
        var side = sp[0], P = sp[1];
        P.redQF.forEach(function (d, q) {
          var p = drawPath(d, RED, 3.2);
          animatePath(p, R_QF, T_RED);
          setTimeout(function () { showScore(scoreIdx[side][q]); }, REDUCED ? 0 : T_RED + R_QF * 0.45);
        });
        var pr = drawPath(P.redSF, RED, 3.2);
        animatePath(pr, R_SF, T_RED + R_QF + 100);
        setTimeout(function () { showScore(sfIdx[side]); }, REDUCED ? 0 : T_RED + R_QF + 100 + R_SF * 0.4);
      });
      var T_F = T_RED + R_QF + 100 + R_SF + 200;
      var fx2 = champSide === "L" ? X2L : X2R;
      var pf = drawPath("M" + fx2 + " " + SFY + " L" + XC8 + " " + SFY, RED, 4);
      animatePath(pf, 350, T_F);
      setTimeout(function () { showScore(fIdx); champG.setAttribute("opacity", 1); }, REDUCED ? 0 : T_F + 300);
    }
  }

  /* タブが開かれ #bracket-root がマウントされたら描画(タブ切替のたびに再生) */
  new MutationObserver(function () {
    var root = document.getElementById("bracket-root");
    if (root && !root.dataset.done) render(root);
  }).observe(document.body, { childList: true, subtree: true });
  /* 静的ページ(速報ページ)では #bracket-root が最初から存在するので即描画 */
  var r0 = document.getElementById("bracket-root");
  if (r0 && !r0.dataset.done) render(r0);
})();
