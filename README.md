# 埼玉高校野球 通算ランキング

埼玉県の高校野球の戦績データベースサイト。

## ファイル構成

| ファイル | 内容 |
|---|---|
| `index.html` | サイト本体(prototype.htmlにメタ情報とフッターを追加したもの) |
| `prototype.html` | 原本(公開対象外にしてもよい) |
| `about.html` | サイトについて(運営者情報) |
| `privacy.html` | プライバシーポリシー(AdSense審査に必須) |
| `disclaimer.html` | 免責事項 |
| `contact.html` | お問い合わせ(※Googleフォームの URL 差し替えが必要) |
| `robots.txt` / `sitemap.xml` | 検索エンジン向け(※ドメイン取得後に URL 差し替えが必要) |

## 公開手順(残りの作業)

### 1. GitHubアカウントの作成とプッシュ
1. https://github.com/ でアカウント作成
2. 新規リポジトリ作成(例: `saitama-hsbb`、Public)
3. このフォルダで以下を実行:
   ```
   git remote add origin https://github.com/<ユーザー名>/saitama-hsbb.git
   git push -u origin main
   ```
   (初回プッシュ時にブラウザでGitHubログインを求められます)

### 2. Cloudflare Pagesで公開
1. https://dash.cloudflare.com/ でアカウント作成
2. Workers & Pages → Create → Pages → Connect to Git
3. 上記リポジトリを選択、ビルド設定はすべて空欄のまま(静的サイトのため)→ Deploy
4. `https://<プロジェクト名>.pages.dev` で公開される

### 3. 独自ドメイン(AdSense申請に必須)
1. Cloudflare Registrar 等でドメイン取得(年1,000〜2,000円程度)
2. Pagesプロジェクト → Custom domains → ドメインを接続
3. `robots.txt` と `sitemap.xml` の `REPLACE-WITH-YOUR-DOMAIN` を実際のドメインに差し替えてプッシュ

### 4. 公開後すぐやること
- Googleフォームでお問い合わせフォームを作成し、`contact.html` のリンクを差し替え
- Google Search Console にサイトを登録し、sitemap.xml を送信
