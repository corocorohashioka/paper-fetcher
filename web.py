#!/usr/bin/env python3
"""論文取得アプリの Web UI.

papers.db に保存された論文をブラウザで一覧表示する。
タイトル・アブストラクト・リンクを表示し、キーワード検索と取得元での絞り込みができる。

使い方:
    .venv/bin/python web.py        # http://127.0.0.1:5000 で起動
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from flask import Flask, render_template_string, request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "papers.db"

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>論文一覧</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Hiragino Sans", "Helvetica Neue", Arial, sans-serif;
    max-width: 860px; margin: 0 auto; padding: 24px 16px 64px;
    line-height: 1.6; color: #1a1a1a; background: #fafafa;
  }
  @media (prefers-color-scheme: dark) {
    body { color: #e6e6e6; background: #161616; }
    .card { background: #1f1f1f !important; border-color: #333 !important; }
    input, select { background: #1f1f1f; color: #e6e6e6; border-color: #444; }
    .meta { color: #9a9a9a !important; }
    a { color: #6cb6ff; }
  }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: #888; font-size: 13px; margin-bottom: 20px; }
  form { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }
  input[type=text] {
    flex: 1; min-width: 200px; padding: 9px 12px; font-size: 15px;
    border: 1px solid #ccc; border-radius: 8px;
  }
  select, button {
    padding: 9px 12px; font-size: 15px; border: 1px solid #ccc;
    border-radius: 8px; background: #fff; cursor: pointer;
  }
  button { background: #2563eb; color: #fff; border-color: #2563eb; }
  .card {
    background: #fff; border: 1px solid #e5e5e5; border-radius: 12px;
    padding: 16px 18px; margin-bottom: 14px;
  }
  .title { font-size: 17px; font-weight: 600; margin: 0 0 6px; }
  .title a { color: inherit; text-decoration: none; }
  .title a:hover { text-decoration: underline; }
  .meta { color: #777; font-size: 13px; margin-bottom: 10px; }
  .tag {
    display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 999px;
    background: #eef2ff; color: #4338ca; margin-right: 6px; vertical-align: middle;
  }
  .abstract { font-size: 14px; color: #333; margin: 8px 0 12px; }
  @media (prefers-color-scheme: dark) { .abstract { color: #cfcfcf; }
    .tag { background: #312e81; color: #c7d2fe; } }
  .abstract.empty { color: #aaa; font-style: italic; }
  .link { font-size: 14px; }
  .empty-state { text-align: center; color: #888; padding: 48px 0; }
</style>
</head>
<body>
  <h1>論文一覧</h1>
  <div class="sub">保存済み {{ total }} 件 / 表示 {{ papers|length }} 件</div>

  <form method="get">
    <input type="text" name="q" value="{{ q }}"
           placeholder="タイトル・アブストラクトを検索">
    <select name="source" onchange="this.form.submit()">
      <option value="" {{ '' if sel_source else 'selected' }}>すべての取得元</option>
      {% for s in sources %}
      <option value="{{ s }}" {{ 'selected' if sel_source == s else '' }}>{{ s }}</option>
      {% endfor %}
    </select>
    <button type="submit">検索</button>
  </form>

  {% if papers %}
    {% for p in papers %}
    <div class="card">
      <div class="title"><a href="{{ p.url }}" target="_blank" rel="noopener">{{ p.title }}</a></div>
      <div class="meta">
        <span class="tag">{{ p.source }}</span>{{ p.journal }} · {{ p.published }}
      </div>
      {% if p.abstract %}
        <div class="abstract">{{ p.abstract }}</div>
      {% else %}
        <div class="abstract empty">（アブストラクトなし）</div>
      {% endif %}
      <div class="link"><a href="{{ p.url }}" target="_blank" rel="noopener">論文を開く →</a></div>
    </div>
    {% endfor %}
  {% else %}
    <div class="empty-state">該当する論文がありません。</div>
  {% endif %}
</body>
</html>
"""


def get_sources(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT source FROM papers ORDER BY source").fetchall()
    return [r[0] for r in rows]


@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    source = request.args.get("source", "").strip()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]

    sql = "SELECT title, abstract, journal, source, published, url FROM papers"
    where, params = [], []
    if q:
        where.append("(title LIKE ? OR abstract LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if source:
        where.append("source = ?")
        params.append(source)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY published DESC, fetched_at DESC LIMIT 300"

    papers = conn.execute(sql, params).fetchall()
    sources = get_sources(conn)
    conn.close()

    return render_template_string(
        PAGE, papers=papers, total=total, q=q, sel_source=source, sources=sources
    )


if __name__ == "__main__":
    if not DB_PATH.exists():
        print("papers.db が見つかりません。先に fetcher.py を実行してください。")
    app.run(host="127.0.0.1", port=5000, debug=False)
