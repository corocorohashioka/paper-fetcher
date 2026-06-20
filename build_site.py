#!/usr/bin/env python3
"""papers.db から静的な HTML を生成する（GitHub Pages 公開用）.

サーバー不要。検索・絞り込みはページ内の JavaScript で動く。
出力先: docs/index.html （GitHub Pages の公開フォルダ）

使い方:
    .venv/bin/python build_site.py
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "papers.db"
OUT_DIR = BASE_DIR / "docs"
OUT_FILE = OUT_DIR / "index.html"

MAX_PAPERS = 1000  # ページに埋め込む最大件数（新着順）


def load_papers() -> list[dict]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT title, abstract, journal, source, published, url FROM papers "
        "ORDER BY published DESC, fetched_at DESC LIMIT ?",
        (MAX_PAPERS,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


HTML = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>論文一覧</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, "Hiragino Sans", "Helvetica Neue", Arial, sans-serif;
    max-width: 860px; margin: 0 auto; padding: 24px 16px 64px;
    line-height: 1.6; color: #1a1a1a; background: #fafafa;
  }}
  @media (prefers-color-scheme: dark) {{
    body {{ color: #e6e6e6; background: #161616; }}
    .card {{ background: #1f1f1f; border-color: #333; }}
    input, select {{ background: #1f1f1f; color: #e6e6e6; border-color: #444; }}
    .meta {{ color: #9a9a9a; }}
    a {{ color: #6cb6ff; }}
    .abstract {{ color: #cfcfcf; }}
    .tag {{ background: #312e81; color: #c7d2fe; }}
  }}
  h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .sub {{ color: #888; font-size: 13px; margin-bottom: 20px; }}
  .controls {{ display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }}
  input[type=text] {{
    flex: 1; min-width: 200px; padding: 9px 12px; font-size: 15px;
    border: 1px solid #ccc; border-radius: 8px;
  }}
  select {{
    padding: 9px 12px; font-size: 15px; border: 1px solid #ccc;
    border-radius: 8px; background: #fff;
  }}
  .card {{
    background: #fff; border: 1px solid #e5e5e5; border-radius: 12px;
    padding: 16px 18px; margin-bottom: 14px;
  }}
  .title {{ font-size: 17px; font-weight: 600; margin: 0 0 6px; }}
  .title a {{ color: inherit; text-decoration: none; }}
  .title a:hover {{ text-decoration: underline; }}
  .meta {{ color: #777; font-size: 13px; margin-bottom: 10px; }}
  .tag {{
    display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 999px;
    background: #eef2ff; color: #4338ca; margin-right: 6px; vertical-align: middle;
  }}
  .abstract {{ font-size: 14px; color: #333; margin: 8px 0 12px; }}
  .abstract.empty {{ color: #aaa; font-style: italic; }}
  .link {{ font-size: 14px; }}
  .empty-state {{ text-align: center; color: #888; padding: 48px 0; }}
</style>
</head>
<body>
  <h1>論文一覧</h1>
  <div class="sub">更新: {updated} ／ <span id="count">{total}</span> 件</div>

  <div class="controls">
    <input type="text" id="q" placeholder="タイトル・アブストラクトを検索"
           oninput="render()">
    <select id="source" onchange="render()">
      <option value="">すべての取得元</option>
    </select>
  </div>

  <div id="list"></div>

  <script>
    const PAPERS = {data};

    function esc(s) {{
      return (s || "").replace(/[&<>"']/g, c => ({{
        "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));
    }}

    // 取得元プルダウンを構築
    const sel = document.getElementById("source");
    [...new Set(PAPERS.map(p => p.source))].sort().forEach(s => {{
      const o = document.createElement("option");
      o.value = s; o.textContent = s; sel.appendChild(o);
    }});

    function render() {{
      const q = document.getElementById("q").value.toLowerCase().trim();
      const src = document.getElementById("source").value;
      const filtered = PAPERS.filter(p => {{
        if (src && p.source !== src) return false;
        if (q) {{
          const hay = (p.title + " " + (p.abstract || "")).toLowerCase();
          if (!hay.includes(q)) return false;
        }}
        return true;
      }});
      document.getElementById("count").textContent = filtered.length;
      const list = document.getElementById("list");
      if (!filtered.length) {{
        list.innerHTML = '<div class="empty-state">該当する論文がありません。</div>';
        return;
      }}
      list.innerHTML = filtered.map(p => `
        <div class="card">
          <div class="title"><a href="${{esc(p.url)}}" target="_blank" rel="noopener">${{esc(p.title)}}</a></div>
          <div class="meta"><span class="tag">${{esc(p.source)}}</span>${{esc(p.journal)}} · ${{esc(p.published)}}</div>
          ${{p.abstract
              ? `<div class="abstract">${{esc(p.abstract)}}</div>`
              : `<div class="abstract empty">（アブストラクトなし）</div>`}}
          <div class="link"><a href="${{esc(p.url)}}" target="_blank" rel="noopener">論文を開く →</a></div>
        </div>`).join("");
    }}
    render();
  </script>
</body>
</html>
"""


def main() -> None:
    papers = load_papers()
    OUT_DIR.mkdir(exist_ok=True)
    html = HTML.format(
        updated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        total=len(papers),
        data=json.dumps(papers, ensure_ascii=False),
    )
    OUT_FILE.write_text(html, encoding="utf-8")
    # GitHub Pages が Jekyll 処理をスキップするためのマーカー
    (OUT_DIR / ".nojekyll").touch()
    print(f"{OUT_FILE} を生成しました（{len(papers)} 件）")


if __name__ == "__main__":
    main()
