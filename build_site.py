#!/usr/bin/env python3
"""papers.db から静的な HTML を1枚生成する（GitHub Pages 公開用）.

== 仕組み ==
    DB の論文(直近 display_months か月分)を JSON にして HTML に丸ごと埋め込む。
    ページを開くと、その JSON を元に JavaScript が一覧を描画する。
    → サーバー不要。HTML ファイル1枚だけで完結するので GitHub Pages で配信できる。

== ページ内 JS が担う機能（すべてクライアント側＝閲覧する端末内で完結） ==
    - 検索（タイトル・著者・抄録）／雑誌・取得元での絞り込み
    - 既読/未読の管理        … 既読IDの集合を localStorage に保存（端末ごと）
    - 新着(NEW)ハイライト    … 「前回ページを開いた時刻」より後に取得された論文に印
    これらの状態はブラウザ内(localStorage)に持つので、サーバーもログインも不要。

出力先: docs/index.html（と Jekyll 抑止用の docs/.nojekyll）

使い方:
    .venv/bin/python build_site.py
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import sqlite3
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "papers.db"
CONFIG_PATH = BASE_DIR / "config.yaml"
OUT_DIR = BASE_DIR / "docs"
OUT_FILE = OUT_DIR / "index.html"

MAX_PAPERS = 2000  # ページに埋め込む最大件数（新着順）


def _months_ago(d: dt.date, months: int) -> dt.date:
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12
        y -= 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return d.replace(year=y, month=m, day=day)


def display_cutoff() -> dt.date:
    months = 3
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as f:
            months = int((yaml.safe_load(f) or {}).get("display_months", 3))
    return _months_ago(dt.date.today(), months)


def load_papers() -> list[dict]:
    if not DB_PATH.exists():
        return []
    cutoff = display_cutoff().isoformat()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT source, source_id, title, authors, abstract, journal, published, "
        "url, fetched_at FROM papers WHERE published >= ? "
        "ORDER BY published DESC, fetched_at DESC LIMIT ?",
        (cutoff, MAX_PAPERS),
    ).fetchall()
    conn.close()
    papers = []
    for r in rows:
        d = dict(r)
        # 既読管理用の安定したID（source + DOI/arXiv ID）。なければ URL。
        d["id"] = f"{d['source']}:{d['source_id']}" if d["source_id"] else d["url"]
        papers.append(d)
    return papers


HTML = r"""<!doctype html>
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
    .card { background: #1f1f1f; border-color: #333; }
    input, select, button.ghost { background: #1f1f1f; color: #e6e6e6; border-color: #444; }
    .meta { color: #9a9a9a; }
    a { color: #6cb6ff; }
    .abstract { color: #cfcfcf; }
    .tag { background: #312e81; color: #c7d2fe; }
  }
  h1 { font-size: 22px; margin: 0 0 4px; }
  .sub { color: #888; font-size: 13px; margin-bottom: 16px; }
  .sub b { color: #2563eb; }
  .controls { display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap; align-items: center; }
  input[type=text] {
    flex: 1; min-width: 180px; padding: 9px 12px; font-size: 15px;
    border: 1px solid #ccc; border-radius: 8px;
  }
  select {
    padding: 9px 12px; font-size: 15px; border: 1px solid #ccc;
    border-radius: 8px; background: #fff;
  }
  .toolbar { display: flex; gap: 14px; align-items: center; margin-bottom: 22px;
             flex-wrap: wrap; font-size: 14px; }
  .toolbar label { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
  button.ghost {
    padding: 7px 12px; font-size: 13px; border: 1px solid #ccc;
    border-radius: 8px; background: #fff; cursor: pointer;
  }
  .card {
    background: #fff; border: 1px solid #e5e5e5; border-radius: 12px;
    padding: 16px 18px; margin-bottom: 14px; position: relative;
    border-left: 4px solid transparent; transition: opacity .15s;
  }
  .card.is-new { border-left-color: #2563eb; }
  .card.read { opacity: .5; }
  .title { font-size: 17px; font-weight: 600; margin: 0 0 6px; padding-right: 90px; }
  .title a { color: inherit; text-decoration: none; }
  .title a:hover { text-decoration: underline; }
  .badge-new {
    display: inline-block; font-size: 11px; font-weight: 700; padding: 1px 7px;
    border-radius: 999px; background: #ef4444; color: #fff; margin-right: 6px;
    vertical-align: middle;
  }
  .authors { font-size: 13px; color: #555; margin: 0 0 4px; }
  @media (prefers-color-scheme: dark) { .authors { color: #b8b8b8; } }
  .meta { color: #777; font-size: 13px; margin-bottom: 10px; }
  .tag {
    display: inline-block; font-size: 11px; padding: 1px 8px; border-radius: 999px;
    background: #eef2ff; color: #4338ca; margin-right: 6px; vertical-align: middle;
  }
  .abstract { font-size: 14px; color: #333; margin: 8px 0 12px; }
  .abstract.empty { color: #aaa; font-style: italic; }
  .link { font-size: 14px; }
  .toggle-read {
    position: absolute; top: 14px; right: 16px;
    font-size: 12px; padding: 4px 10px; border-radius: 8px;
    border: 1px solid #ccc; background: transparent; color: #666; cursor: pointer;
  }
  .card.read .toggle-read { color: #2563eb; border-color: #2563eb; }
  .empty-state { text-align: center; color: #888; padding: 48px 0; }
</style>
</head>
<body>
  <h1>論文一覧</h1>
  <div class="sub">更新: __UPDATED__ ／ 全 __TOTAL__ 件・未読 <b id="unread">0</b> 件</div>

  <div class="controls">
    <input type="text" id="q" placeholder="タイトル・著者・アブストラクトを検索" oninput="render()">
    <select id="journal" onchange="render()">
      <option value="">すべての雑誌</option>
    </select>
    <select id="source" onchange="render()">
      <option value="">すべての取得元</option>
    </select>
  </div>

  <div class="toolbar">
    <label><input type="checkbox" id="unreadOnly" onchange="render()"> 未読のみ表示</label>
    <button class="ghost" onclick="markAllRead()">すべて既読にする</button>
    <button class="ghost" onclick="markAllUnread()">すべて未読に戻す</button>
  </div>

  <div id="list"></div>

  <script>
    const PAPERS = __PAPERS_DATA__;
    const LS_READ = "pf_read_v1";        // 既読IDの集合
    const LS_LASTVISIT = "pf_lastvisit_v1"; // 前回表示時刻（新着判定用）

    function esc(s) {
      return (s || "").replace(/[&<>"']/g, c => ({
        "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
    }

    // --- 既読状態（localStorage） ---
    function loadRead() {
      try { return new Set(JSON.parse(localStorage.getItem(LS_READ) || "[]")); }
      catch (e) { return new Set(); }
    }
    function saveRead() { localStorage.setItem(LS_READ, JSON.stringify([...readSet])); }
    let readSet = loadRead();

    // --- 新着判定: 前回開いた時刻より後に取得された論文を NEW とする ---
    const prevRaw = localStorage.getItem(LS_LASTVISIT);
    const prevVisit = prevRaw ? parseInt(prevRaw, 10) : null;
    const firstVisit = prevVisit === null;
    const newIds = new Set();
    if (!firstVisit) {
      PAPERS.forEach(p => {
        if (p.fetched_at && new Date(p.fetched_at).getTime() > prevVisit) {
          newIds.add(p.id);
        }
      });
    }
    // 今回の表示時刻を記録（次回はこれより後の論文が新着になる）
    localStorage.setItem(LS_LASTVISIT, String(Date.now()));

    // --- 取得元プルダウン ---
    const sel = document.getElementById("source");
    [...new Set(PAPERS.map(p => p.source))].sort().forEach(s => {
      const o = document.createElement("option");
      o.value = s; o.textContent = s; sel.appendChild(o);
    });

    // --- 雑誌プルダウン（件数つき） ---
    const jsel = document.getElementById("journal");
    const jcount = {};
    PAPERS.forEach(p => { jcount[p.journal] = (jcount[p.journal] || 0) + 1; });
    Object.keys(jcount).sort().forEach(j => {
      const o = document.createElement("option");
      o.value = j; o.textContent = `${j} (${jcount[j]})`; jsel.appendChild(o);
    });

    // --- 既読トグル ---
    function toggleRead(id) {
      if (readSet.has(id)) readSet.delete(id); else readSet.add(id);
      saveRead(); render();
    }
    function markRead(id) { readSet.add(id); saveRead(); render(); }
    // 「すべて〜」は現在フィルターで表示中の論文だけを対象にする
    function markAllRead() {
      currentFiltered().forEach(p => readSet.add(p.id)); saveRead(); render();
    }
    function markAllUnread() {
      currentFiltered().forEach(p => readSet.delete(p.id)); saveRead(); render();
    }

    function updateUnreadCount() {
      const n = PAPERS.filter(p => !readSet.has(p.id)).length;
      document.getElementById("unread").textContent = n;
    }

    // 検索・雑誌・取得元・未読のみ の各条件で現在表示すべき論文を返す
    function currentFiltered() {
      const q = document.getElementById("q").value.toLowerCase().trim();
      const src = document.getElementById("source").value;
      const jr = document.getElementById("journal").value;
      const unreadOnly = document.getElementById("unreadOnly").checked;
      return PAPERS.filter(p => {
        if (src && p.source !== src) return false;
        if (jr && p.journal !== jr) return false;
        if (unreadOnly && readSet.has(p.id)) return false;
        if (q) {
          const hay = (p.title + " " + (p.authors || "") + " " + (p.abstract || "")).toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });
    }

    function render() {
      const filtered = currentFiltered();
      updateUnreadCount();
      const list = document.getElementById("list");
      if (!filtered.length) {
        list.innerHTML = '<div class="empty-state">該当する論文がありません。</div>';
        return;
      }
      list.innerHTML = filtered.map(p => {
        const isRead = readSet.has(p.id);
        const isNew = newIds.has(p.id) && !isRead;
        const cls = "card" + (isRead ? " read" : "") + (isNew ? " is-new" : "");
        return `
        <div class="${cls}" data-id="${esc(p.id)}">
          <button class="toggle-read" data-toggle>${isRead ? "未読に戻す" : "既読にする"}</button>
          <div class="title">${isNew ? '<span class="badge-new">NEW</span>' : ""}<a class="paper-link" href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a></div>
          ${p.authors ? `<div class="authors">${esc(p.authors)}</div>` : ""}
          <div class="meta"><span class="tag">${esc(p.source)}</span>${esc(p.journal)} · ${esc(p.published)}</div>
          ${p.abstract
              ? `<div class="abstract">${esc(p.abstract)}</div>`
              : `<div class="abstract empty">（アブストラクトなし）</div>`}
          <div class="link"><a class="paper-link" href="${esc(p.url)}" target="_blank" rel="noopener">論文を開く →</a></div>
        </div>`;
      }).join("");
    }

    // クリック委譲: 既読ボタン / 論文リンク（開いたら自動で既読に）
    document.getElementById("list").addEventListener("click", e => {
      const card = e.target.closest(".card");
      if (!card) return;
      const id = card.getAttribute("data-id");
      if (e.target.closest("[data-toggle]")) {
        e.preventDefault();
        toggleRead(id);
      } else if (e.target.closest("a.paper-link")) {
        markRead(id);  // ナビゲーションは止めない（別タブで開く）
      }
    });

    render();
  </script>
</body>
</html>
"""


def main() -> None:
    papers = load_papers()
    OUT_DIR.mkdir(exist_ok=True)
    # </script> でスクリプトタグが閉じないようにエスケープ
    data = json.dumps(papers, ensure_ascii=False).replace("</", "<\\/")
    html = (
        HTML.replace("__UPDATED__", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
        .replace("__TOTAL__", str(len(papers)))
        .replace("__PAPERS_DATA__", data)
    )
    OUT_FILE.write_text(html, encoding="utf-8")
    (OUT_DIR / ".nojekyll").touch()
    print(f"{OUT_FILE} を生成しました（{len(papers)} 件）")


if __name__ == "__main__":
    main()
