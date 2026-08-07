"""Sasol media-releases parser.

List page : https://www.sasol.com/media-centre/media-releases
Item HTML :
  <div class="press-release-listing">
    <div class="imagebox"><img .../></div>
    <div class="press-content">
      <div class="title"><a href="...">TITLE</a></div>
      <div class="body"><p>...teaser...</p></div>
      <div class="date">05 Aug, 2026</div>
    </div>
  </div>

Article page body lives in <div class="page-descriptiom"> (site's own typo).
"""
from __future__ import annotations

from bs4 import BeautifulSoup
from datetime import datetime

BASE = "https://www.sasol.com"
LIST_URL = BASE + "/media-centre/media-releases"


def _abs(href: str) -> str:
    if href.startswith("http"):
        return href
    return BASE + href


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    items = []
    for box in soup.select("div.press-release-listing"):
        a = box.select_one("div.title a")
        if not a:
            continue
        date_el = box.select_one("div.date")
        body_el = box.select_one("div.body")
        items.append({
            "title": a.get_text(" ", strip=True),
            "url": _abs(a.get("href", "")),
            "date_raw": date_el.get_text(" ", strip=True) if date_el else "",
            "summary": body_el.get_text(" ", strip=True) if body_el else "",
        })
    return items


def parse_article(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    desc = soup.select_one("div.page-descriptiom")
    paras = []
    if desc:
        for p in desc.find_all("p"):
            t = p.get_text(" ", strip=True)
            if t:
                paras.append(t)
    content = "\n\n".join(paras)
    # title fallback: page <h1>
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else ""
    return {"content": content, "article_title": title}
