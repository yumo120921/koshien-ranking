# 埼玉高校野球 通算ランキング

埼玉県の高校野球(夏の埼玉大会)の戦績データベースサイト。
公開URL: https://koshien-ranking.com (Cloudflare Workers、pushで自動デプロイ)

## データの更新方法

1. `data/results.csv` を編集する(Excel/メモ帳可。UTF-8で保存すること)
   - 列: `年,ブロック,優勝,準優勝,ベスト4,ベスト4,ベスト8,ベスト8,ベスト8,ベスト8,決勝勝者得点,決勝敗者得点`
   - ブロック列は通常空欄。ブロック制の年のみ `A`/`B`/`東`/`西`/`南`/`北` を入れる
2. 準々決勝以降のスコア詳細は `data/scores.json` を編集する(キーは `"年|ブロック"`)
3. ビルドを実行: `python build.py`
   - index.html(アプリ)へのデータ注入、学校別・年度別ページ、sitemap.xml がすべて再生成される
4. 反映: `git add -A` → `git commit -m "データ更新"` → `git push`

## ファイル構成

| パス | 内容 | 手で編集する? |
|---|---|---|
| `data/results.csv` | 年度別成績(データの原本) | **する** |
| `data/scores.json` | 準々決勝以降のスコア詳細(データの原本) | **する** |
| `build.py` | サイト生成スクリプト | 機能追加時のみ |
| `app_template.html` | アプリのテンプレート(データ部はプレースホルダ) | しない |
| `index.html` | アプリ本体 | **しない(build.pyが生成)** |
| `schools/` `years/` `sitemap.xml` | 学校別・年度別ページ | **しない(build.pyが生成)** |
| `about.html` ほか固定ページ | サイト情報・ポリシー類 | 必要に応じて |
| `prototype.html` | 初期の原本(保存用、配信されない) | しない |
| `.assetsignore` | 配信対象から除外するファイルの一覧 | 必要に応じて |
| `wrangler.jsonc` | Cloudflare Workers設定 | しない |

## 公開・収益化の進捗

- [x] Cloudflare Workersで公開(2026-07)
- [x] 独自ドメイン koshien-ranking.com 接続
- [x] Google Search Console登録・sitemap送信
- [x] プライバシーポリシー等のAdSense必須ページ
- [x] 学校別(106校)・年度別(77年)の静的ページ生成
- [ ] Google AdSense申請
- [ ] 合格後: ads.txt設置、広告ユニット配置
