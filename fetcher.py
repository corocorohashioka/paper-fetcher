#!/usr/bin/env python3
"""論文取得アプリ.

設定ファイル(config.yaml)で指定したジャーナルから定期的に論文を取得し、
SQLite で重複を排除して新着のみを保存・通知する。

使い方:
    python3 fetcher.py                 # 1回実行（cron などから定期実行）
    python3 fetcher.py --config x.yaml # 設定ファイルを指定
    python3 fetcher.py --list          # 保存済みの新着論文を一覧表示
    python3 fetcher.py --dry-run       # 取得するが保存・通知はしない
"""
from __future__ import annotations

import argparse
import datetime as dt
import smtplib
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from pathlib import Path

import requests
import yaml

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "papers.db"
LOG_PATH = BASE_DIR / "new_papers.log"

# Crossref / arXiv は連絡先メールを付けると優先レーンで処理される（任意）。
USER_AGENT = "paper-fetcher/1.0 (mailto:souichirou.coc.0619@gmail.com)"
REQUEST_TIMEOUT = 30


@dataclass
class Paper:
    """1本の論文を表す。source+source_id で一意に識別する。"""

    source: str            # "crossref" / "arxiv"
    source_id: str         # DOI や arXiv ID
    title: str
    authors: str
    journal: str
    published: str         # ISO 形式の日付文字列
    url: str
    abstract: str = ""

    @property
    def key(self) -> tuple[str, str]:
        return (self.source, self.source_id)


# ------------------------------------------------------------------------
# データベース
# ------------------------------------------------------------------------
def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS papers (
            source     TEXT NOT NULL,
            source_id  TEXT NOT NULL,
            title      TEXT,
            authors    TEXT,
            journal    TEXT,
            published  TEXT,
            url        TEXT,
            abstract   TEXT,
            fetched_at TEXT,
            PRIMARY KEY (source, source_id)
        )
        """
    )
    conn.commit()


def already_seen(conn: sqlite3.Connection, paper: Paper) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM papers WHERE source = ? AND source_id = ?",
        paper.key,
    )
    return cur.fetchone() is not None


def save_paper(conn: sqlite3.Connection, paper: Paper) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO papers
            (source, source_id, title, authors, journal, published, url, abstract, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            paper.source,
            paper.source_id,
            paper.title,
            paper.authors,
            paper.journal,
            paper.published,
            paper.url,
            paper.abstract,
            dt.datetime.now().isoformat(timespec="seconds"),
        ),
    )


# ------------------------------------------------------------------------
# 取得元: Crossref
# ------------------------------------------------------------------------
def fetch_crossref(journal: dict, rows: int, since: dt.date) -> list[Paper]:
    """ISSN 指定のジャーナルから since 以降に公開された論文を取得する。"""
    issn = str(journal["issn"]).strip()
    name = journal.get("name", issn)
    url = f"https://api.crossref.org/journals/{issn}/works"
    params = {
        "filter": f"from-pub-date:{since.isoformat()}",
        "sort": "published",
        "order": "desc",
        "rows": rows,
    }
    resp = requests.get(
        url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    items = resp.json().get("message", {}).get("items", [])

    papers: list[Paper] = []
    for it in items:
        doi = it.get("DOI", "")
        if not doi:
            continue
        title_list = it.get("title") or [""]
        authors = ", ".join(
            f"{a.get('given', '')} {a.get('family', '')}".strip()
            for a in it.get("author", [])
        )
        date_parts = (
            it.get("published", {}).get("date-parts")
            or it.get("published-online", {}).get("date-parts")
            or it.get("published-print", {}).get("date-parts")
            or [[1970, 1, 1]]
        )[0]
        # date-parts は [year] / [year, month] / [year, month, day] のいずれか
        y = date_parts[0]
        m = date_parts[1] if len(date_parts) > 1 else 1
        d = date_parts[2] if len(date_parts) > 2 else 1
        published = f"{y:04d}-{m:02d}-{d:02d}"
        papers.append(
            Paper(
                source="crossref",
                source_id=doi,
                title=title_list[0].strip(),
                authors=authors,
                journal=name,
                published=published,
                url=it.get("URL", f"https://doi.org/{doi}"),
                abstract=_strip_tags(it.get("abstract", "")),
            )
        )
    return papers


# ------------------------------------------------------------------------
# 取得元: arXiv
# ------------------------------------------------------------------------
_ATOM = {"a": "http://www.w3.org/2005/Atom"}


def fetch_arxiv(category: str, max_results: int) -> list[Paper]:
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"cat:{category}",
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": max_results,
    }
    resp = requests.get(
        url, params=params, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    papers: list[Paper] = []
    for entry in root.findall("a:entry", _ATOM):
        arxiv_id = _text(entry, "a:id")
        published = _text(entry, "a:published")[:10]  # YYYY-MM-DD
        authors = ", ".join(
            _text(a, "a:name") for a in entry.findall("a:author", _ATOM)
        )
        papers.append(
            Paper(
                source="arxiv",
                source_id=arxiv_id,
                title=" ".join(_text(entry, "a:title").split()),
                authors=authors,
                journal=f"arXiv:{category}",
                published=published,
                url=arxiv_id,
                abstract=" ".join(_text(entry, "a:summary").split()),
            )
        )
    return papers


# ------------------------------------------------------------------------
# 取得元: J-STAGE（日本の学会誌。Crossref に無い和文誌に対応）
# ------------------------------------------------------------------------
def _jstage_bilingual(parent: ET.Element, path: str) -> str:
    """<要素><ja>..</ja><en>..</en></要素> から ja 優先でテキストを取り出す。"""
    el = parent.find(path, _ATOM)
    if el is None:
        return ""
    for lang in ("a:ja", "a:en"):
        sub = el.find(lang, _ATOM)
        if sub is not None and sub.text and sub.text.strip():
            return sub.text.strip()
    return ""


def fetch_jstage(journal: dict, year_from: int) -> list[Paper]:
    """J-STAGE WebAPI で雑誌コード(cdjournal)から論文を取得する。"""
    cd = str(journal["cdjournal"]).strip()
    name = journal.get("name", cd)
    params = {
        "service": 3,            # 3 = 論文検索
        "cdjournal": cd,
        "pubyearfrom": year_from,
        "count": 1000,
    }
    resp = requests.get(
        "https://api.jstage.jst.go.jp/searchapi/do",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    papers: list[Paper] = []
    for entry in root.findall("a:entry", _ATOM):
        title = _jstage_bilingual(entry, "a:article_title")
        url = _jstage_bilingual(entry, "a:article_link") or _text(entry, "a:id")
        doi = _text(entry, "a:doi")
        published = _text(entry, "a:updated")[:10]  # YYYY-MM-DD

        authors = []
        for au in entry.findall("a:author", _ATOM):
            nm = _text(au, "a:ja/a:name") or _text(au, "a:en/a:name")
            if nm:
                authors.append(nm)

        if not title:
            continue
        papers.append(
            Paper(
                source="jstage",
                source_id=doi or url,
                title=title,
                authors=", ".join(authors),
                journal=name,
                published=published,
                url=url,
                abstract="",  # J-STAGE 検索 API は抄録を返さない
            )
        )
    return papers


# ------------------------------------------------------------------------
# フィルタ・ユーティリティ
# ------------------------------------------------------------------------
def matches_keywords(paper: Paper, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = f"{paper.title} {paper.abstract}".lower()
    return any(kw.lower() in haystack for kw in keywords)


def within_lookback(paper: Paper, since: dt.date) -> bool:
    try:
        return dt.date.fromisoformat(paper.published) >= since
    except ValueError:
        return True  # 日付不明なものは取りこぼさないよう通す


def _text(parent: ET.Element, path: str) -> str:
    el = parent.find(path, _ATOM)
    return el.text.strip() if el is not None and el.text else ""


def _strip_tags(s: str) -> str:
    """Crossref の abstract に含まれる JATS タグを雑に除去する。"""
    if not s:
        return ""
    out, depth = [], 0
    for ch in s:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split())


# ------------------------------------------------------------------------
# 通知
# ------------------------------------------------------------------------
def format_papers(papers: list[Paper]) -> str:
    lines = []
    for i, p in enumerate(papers, 1):
        lines.append(f"{i}. {p.title}")
        lines.append(f"   {p.journal} | {p.published}")
        if p.authors:
            lines.append(f"   {p.authors}")
        lines.append(f"   {p.url}")
        lines.append("")
    return "\n".join(lines)


def notify(papers: list[Paper], email_cfg: dict) -> None:
    body = format_papers(papers)

    # 常にファイルへ追記（履歴）
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"\n===== {dt.datetime.now().isoformat(timespec='seconds')} "
                f"({len(papers)}件) =====\n")
        f.write(body)

    if not email_cfg.get("enabled"):
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"[論文取得] 新着 {len(papers)} 件 "\
                     f"({dt.date.today().isoformat()})"
    msg["From"] = email_cfg.get("from_addr") or email_cfg["username"]
    msg["To"] = email_cfg["to_addr"]

    with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
        server.starttls()
        server.login(email_cfg["username"], email_cfg["password"])
        server.send_message(msg)
    print(f"メールを {email_cfg['to_addr']} に送信しました。")


# ------------------------------------------------------------------------
# メイン
# ------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect(cfg: dict) -> list[Paper]:
    """設定に従い全取得元から論文を集める。"""
    lookback = int(cfg.get("lookback_days", 7))
    since = dt.date.today() - dt.timedelta(days=lookback)
    keywords = cfg.get("keywords") or []
    sources = cfg.get("sources", {})

    collected: list[Paper] = []

    cr = sources.get("crossref", {})
    if cr.get("enabled"):
        for journal in cr.get("journals", []):
            try:
                got = fetch_crossref(journal, cr.get("rows", 50), since)
                print(f"  Crossref [{journal.get('name')}]: {len(got)} 件取得")
                collected.extend(got)
            except Exception as e:  # noqa: BLE001 - 1誌の失敗で全体を止めない
                print(f"  ! Crossref [{journal.get('name')}] 失敗: {e}",
                      file=sys.stderr)
            time.sleep(1)  # API へのレート配慮

    ax = sources.get("arxiv", {})
    if ax.get("enabled"):
        for cat in ax.get("categories", []):
            try:
                got = fetch_arxiv(cat, ax.get("max_results", 50))
                # arXiv は日付指定取得ができないので lookback で期間を絞る
                got = [p for p in got if within_lookback(p, since)]
                print(f"  arXiv [{cat}]: {len(got)} 件取得")
                collected.extend(got)
            except Exception as e:  # noqa: BLE001
                print(f"  ! arXiv [{cat}] 失敗: {e}", file=sys.stderr)
            time.sleep(3)  # arXiv は 3 秒以上の間隔を推奨

    js = sources.get("jstage", {})
    if js.get("enabled"):
        # 刊行頻度が低い（季刊等）ため lookback は適用せず、
        # 直近数年分を取り込んで DB の重複排除で新着を判定する。
        year_from = dt.date.today().year - int(js.get("years_back", 2))
        for journal in js.get("journals", []):
            try:
                got = fetch_jstage(journal, year_from)
                print(f"  J-STAGE [{journal.get('name')}]: {len(got)} 件取得")
                collected.extend(got)
            except Exception as e:  # noqa: BLE001
                print(f"  ! J-STAGE [{journal.get('name')}] 失敗: {e}",
                      file=sys.stderr)
            time.sleep(1)

    # キーワードでフィルタ（期間絞り込みは各取得元で実施済み）
    return [p for p in collected if matches_keywords(p, keywords)]


def run(cfg: dict, dry_run: bool = False) -> None:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    print(f"[{dt.datetime.now().isoformat(timespec='seconds')}] 取得開始")
    papers = collect(cfg)

    # 重複排除（DB 未登録のもののみ新着）
    seen_in_run: set[tuple[str, str]] = set()
    new_papers: list[Paper] = []
    for p in papers:
        if p.key in seen_in_run or already_seen(conn, p):
            continue
        seen_in_run.add(p.key)
        new_papers.append(p)

    print(f"新着: {len(new_papers)} 件 (取得 {len(papers)} 件中)")

    if dry_run:
        print("--dry-run のため保存・通知はしません。")
        print(format_papers(new_papers))
        conn.close()
        return

    for p in new_papers:
        save_paper(conn, p)
    conn.commit()

    if new_papers:
        notify(new_papers, cfg.get("email", {}))
    conn.close()


def list_saved(limit: int = 30) -> None:
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    rows = conn.execute(
        "SELECT title, journal, published, url FROM papers "
        "ORDER BY fetched_at DESC, published DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    if not rows:
        print("保存済みの論文はまだありません。")
        return
    for title, journal, published, url in rows:
        print(f"- {title}\n  {journal} | {published} | {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ジャーナルから論文を定期取得する")
    parser.add_argument("--config", default=str(BASE_DIR / "config.yaml"))
    parser.add_argument("--dry-run", action="store_true",
                        help="取得するが保存・通知しない")
    parser.add_argument("--list", action="store_true",
                        help="保存済み論文を一覧表示")
    args = parser.parse_args()

    if args.list:
        list_saved()
        return

    cfg = load_config(Path(args.config))
    run(cfg, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
