# 論文取得アプリ (paper_fetcher)

設定ファイルで指定したジャーナルから定期的に新着論文を取得し、SQLite に蓄積して、
スマホからも見られる静的サイト（GitHub Pages）として公開するツールです。

## 仕組み（アーキテクチャ）
```
  ┌─ fetcher.py ──────────────┐     ┌─ build_site.py ─┐     ┌─ git push ─┐
  │ 各APIから取得              │     │ DBの直近3か月を  │     │ docs/ を   │
  │  → 重複排除して papers.db  │ ──▶ │ HTML1枚に埋込み  │ ──▶ │ GitHubへ   │ ──▶ GitHub Pages
  │  → 抄録を補完              │     │  (docs/index.html)│     └────────────┘        (スマホで閲覧)
  └───────────────────────────┘     └──────────────────┘
        この3つを daily.sh が毎日まとめて実行（launchd で自動起動）
```
- **データは `papers.db`(SQLite) に一元管理**。`fetcher.py` が書き、`build_site.py` が読む。
- **閲覧用ページはサーバー不要の静的HTML1枚**。検索・既読管理などはページ内 JavaScript が
  ブラウザ内(localStorage)で処理するので、ログインもバックエンドも要りません。
- 各ファイルの役割は [fetcher.py](fetcher.py) / [build_site.py](build_site.py) /
  [daily.sh](daily.sh) の冒頭コメントに詳述しています。

## 取得元
- **Crossref** — ISSN を指定すればほぼ全出版社のジャーナルに対応（無料・キー不要）
- **arXiv** — カテゴリ指定でプレプリントを取得
- **J-STAGE** — 日本の学会誌（Crossref に無い和文誌）。雑誌コード(cdjournal)で指定

### 抄録の補完
抄録が取得元のメタデータに無い場合、`fetch_abstracts: true`（既定）なら自動で補います:
- **J-STAGE 誌** … 記事ページから抄録を抜き出す（検索 API は抄録を返さないため）
- **Crossref 誌** … OpenAlex に DOI で照会（Elsevier 等は Crossref に抄録を出さないため）

補完対象は「表示される直近 `display_months` か月分」だけなので軽量。まだ取れないもの
（公開直後で索引化前など）は、翌日以降の実行で自動的にリトライされ順次埋まります。

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
  crossref:                 # 英文誌など（ISSN で指定）
    enabled: true
    rows: 60                # 1誌あたり取得する最新件数
    years_back: 2           # これより古い論文は取り込まない
    journals:
      - name: "Food Policy"
        issn: "0306-9192"
  jstage:                   # 日本の学会誌（雑誌コードで指定）
    enabled: true
    years_back: 3
    journals:
      - name: "農業経済研究"
        cdjournal: "nokei"

keywords: []          # タイトル/抄録のキーワード絞り込み（空なら全件）
display_months: 3     # サイトに表示する直近の月数（DB には全件残る）
fetch_abstracts: true # 抄録が無いものを自動補完するか
```

## 実行
```bash
.venv/bin/python fetcher.py            # 取得して保存・通知
.venv/bin/python fetcher.py --dry-run  # 取得のみ（保存・通知しない）
.venv/bin/python fetcher.py --list     # 保存済みを一覧表示
```

新着論文は `new_papers.log` に追記され、データは `papers.db`(SQLite) に保存されます。

## ブラウザで閲覧
`build_site.py` で生成した `docs/index.html` を開くだけです。ローカルで確認するには
簡易サーバーを立てます（`file://` だと一部ブラウザで制約があるため）:
```bash
.venv/bin/python build_site.py                       # 最新のHTMLを生成
.venv/bin/python -m http.server 8000 --directory docs # http://localhost:8000 で開く
```
ページ上で、タイトル・著者・抄録・リンクの表示、検索、雑誌/取得元での絞り込み、
既読/未読の管理、新着(NEW)ハイライトが使えます（すべてブラウザ内で動作）。

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

## 定期実行（毎日自動）
macOS では launchd（標準のスケジューラ）で毎朝8時に `daily.sh`（取得→生成→push）を
実行します。設定ファイルは `~/Library/LaunchAgents/com.paperfetcher.daily.plist`。

```bash
# 登録 / 解除
launchctl load   ~/Library/LaunchAgents/com.paperfetcher.daily.plist
launchctl unload ~/Library/LaunchAgents/com.paperfetcher.daily.plist

launchctl list | grep paperfetcher                      # 登録確認
launchctl kickstart -k gui/$(id -u)/com.paperfetcher.daily  # 今すぐ手動実行（テスト）
tail -f cron.log                                        # 実行ログを見る
```
実行時刻を変えるには plist の `Hour`/`Minute` を編集し、`unload`→`load` し直します。
8時に Mac がスリープ/電源オフでも、launchd は次に起動した時に取りこぼし分を実行します。

> Linux 等で cron を使う場合:
> `0 8 * * * /path/to/paper_fetcher/daily.sh >> /path/to/paper_fetcher/cron.log 2>&1`
