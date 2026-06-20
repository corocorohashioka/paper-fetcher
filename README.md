# 論文取得アプリ (paper_fetcher)

設定ファイルで指定したジャーナルから定期的に新着論文を取得し、SQLite で重複を
排除して保存・通知するツールです。

## 取得元
- **Crossref** — ISSN を指定すればほぼ全出版社のジャーナルに対応（無料・キー不要）
- **arXiv** — カテゴリ指定でプレプリントを取得
- **J-STAGE** — 日本の学会誌（Crossref に無い和文誌）。雑誌コード(cdjournal)で指定
  （注: J-STAGE 検索 API は抄録を返さないため、和文誌はアブストラクトなしで表示されます）

## セットアップ
```bash
cd paper_fetcher
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 対象ジャーナルの指定
`config.yaml` を編集します。各ジャーナルの ISSN は
[issn.org](https://portal.issn.org) で検索できます。

```yaml
sources:
  crossref:
    enabled: true
    journals:
      - name: "Nature"
        issn: "1476-4687"
keywords: []          # タイトル/抄録のキーワード絞り込み（空なら全件）
lookback_days: 7      # 何日前までを新着とするか
```

## 実行
```bash
.venv/bin/python fetcher.py            # 取得して保存・通知
.venv/bin/python fetcher.py --dry-run  # 取得のみ（保存・通知しない）
.venv/bin/python fetcher.py --list     # 保存済みを一覧表示
```

新着論文は `new_papers.log` に追記され、データは `papers.db`(SQLite) に保存されます。

## Web UI で閲覧
保存済み論文をブラウザで一覧できます。タイトル・アブストラクト・リンクを表示し、
キーワード検索と取得元での絞り込みができます。
```bash
.venv/bin/python web.py
```
起動後、ブラウザで http://127.0.0.1:5000 を開きます。
（一部のニュース記事などはアブストラクトが提供されず「アブストラクトなし」と表示されます）

## メール通知（任意）
`config.yaml` の `email.enabled` を `true` にし、Gmail の場合は
[アプリパスワード](https://myaccount.google.com/apppasswords)を `password` に設定します。

## スマホから見る（GitHub Pages 方式）
常時稼働サーバーを使わず、1日1回 DB から静的 HTML を生成して GitHub に push し、
GitHub Pages で公開します。スマホからどこでも閲覧でき、Mac がスリープでも見られます。
検索・絞り込みはページ内 JavaScript で動きます。

> 注意: 無料アカウントの GitHub Pages は **公開**（URL を知る人は誰でも閲覧可）です。
> 公開されるのは論文のタイトル・アブストラクト・リンクのみで、`config.yaml` や
> `papers.db` は `.gitignore` で除外され push されません。

### 初回セットアップ
```bash
# 静的サイトを生成
.venv/bin/python build_site.py

# GitHub にリポジトリを作成して push（リポジトリは事前に GitHub 上で作成）
git remote add origin https://github.com/<あなたのユーザー名>/<リポジトリ名>.git
git push -u origin main
```
push 後、GitHub のリポジトリ画面で **Settings → Pages → Build and deployment**:
- Source: `Deploy from a branch`
- Branch: `main` / フォルダ `/docs` を選んで Save

数分後、`https://<ユーザー名>.github.io/<リポジトリ名>/` で閲覧できます。
このURLをスマホのホーム画面に追加すればアプリのように使えます。

### 毎日自動更新
`daily.sh` が「取得 → サイト生成 → push」を一括で行います。下記の cron 例を参照。

## 定期実行（cron）
`crontab -e` に以下を追記すると毎朝 8 時に「取得 → サイト生成 → push」を実行します:
```
0 8 * * * /Users/asadasoichiro/claudeworks/paper_fetcher/daily.sh >> /Users/asadasoichiro/claudeworks/paper_fetcher/cron.log 2>&1
```
（GitHub Pages を使わずローカル保存だけで良ければ、`daily.sh` の代わりに
`.venv/bin/python fetcher.py` を指定してください）

macOS では端末に「フルディスクアクセス」権限が必要な場合があります
（システム設定 → プライバシーとセキュリティ）。
