"""Hitachi High-Tech news parser (English: global/en).

List page : https://www.hitachi-hightech.com/global/en/news/
Article   : https://www.hitachi-hightech.com/global/en/news/nr20260804.html
            https://www.hitachi-hightech.com/global/en/news/csr-20260724.html

The site sits behind Akamai WAF, so the HTML is fetched via Playwright driving
a real Chrome (``engine: playwright`` + ``browser_channel: chrome`` in
sites.yaml). Article detail pages are ``/global/en/news/<type><date>.html``;
the list page itself and the ``backnumber`` archive index are excluded.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE = "https://www.hitachi-hightech.com"

# Detail pages: /global/en/news/<name>.html (name has letters + digits).
_DETAIL_RE = re.compile(r"/global/en/news/[^/]+\.html$", re.I)
# Pages that are NOT single articles.
_EXCLUDE = ("backnumber",)


def _abs(href: str) -> str:
    return href if href.startswith("http") else urljoin(BASE, href)


def _date_from_url(url: str) -> str:
    m = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return ""


def _scan_date(node) -> str:
    for _ in range(4):
        if node is None:
            break
        txt = node.get_text(" ", strip=True)
        m = re.search(r"(\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}\s+[A-Za-z]{3,}\s+\d{4})", txt)
        if m:
            return m.group(1)
        node = node.parent
    return ""


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not _DETAIL_RE.search(href):
            continue
        if any(x in href for x in _EXCLUDE):
            continue
        url = _abs(href)
        if url.rstrip("/") == BASE + "/global/en/news/":
            continue
        title = a.get_text(" ", strip=True)
        if not title or len(title) < 5:
            continue
        if url in seen:
            continue
        seen.add(url)
        items.append({
            "title": title,
            "url": url,
            "date_raw": _date_from_url(url) or _scan_date(a),
            "summary": "",
        })
    return items


def parse_article(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    container = soup.find("article") or soup.find("main") or soup.body
    paras: list[str] = []
    if container:
        for p in container.find_all("p"):
            t = p.get_text(" ", strip=True)
            if t:
                paras.append(t)
    content = "\n\n".join(paras)
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    return {"content": content, "article_title": title}
