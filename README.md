# 論文取得アプリ (paper_fetcher)

設定ファイルで指定したジャーナルから定期的に新着論文を取得し、SQLite で重複を
排除して保存・通知するツールです。

## 取得元
- **Crossref** — ISSN を指定すればほぼ全出版社のジャーナルに対応（無料・キー不要）
- **arXiv** — カテゴリ指定でプレプリントを取得

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

## 定期実行（cron）
`crontab -e` に以下を追記すると毎朝 8 時に実行されます（パスは環境に合わせて変更）:
```
0 8 * * * /Users/asadasoichiro/claudeworks/paper_fetcher/.venv/bin/python /Users/asadasoichiro/claudeworks/paper_fetcher/fetcher.py >> /Users/asadasoichiro/claudeworks/paper_fetcher/cron.log 2>&1
```

macOS では端末に「フルディスクアクセス」権限が必要な場合があります
（システム設定 → プライバシーとセキュリティ）。
