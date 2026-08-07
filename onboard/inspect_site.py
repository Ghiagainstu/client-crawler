#!/usr/bin/env python3
"""Agent helper: inspect a client's list page to finalize parser selectors.

Fetches config/sites.yaml -> clients[<client>].list_url, then prints:
  - page <title>
  - count of anchors with href
  - the most common container tag.class patterns that wrap an <a href>
    (these are candidate ITEM_SELECTOR values)

Usage:
  venv/bin/python onboard/inspect_site.py <client>
"""
from __future__ import annotations

import os
import sys
from collections import Counter

import yaml
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from crawler.core import fetch  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: inspect_site.py <client>")
        return 2
    client = sys.argv[1]
    cfg = yaml.safe_load(open(os.path.join(ROOT, "config", "sites.yaml"), encoding="utf-8"))
    clients = cfg.get("clients", {})
    if client not in clients:
        print(f"client '{client}' not in sites.yaml. known: {list(clients)}")
        return 1
    list_url = clients[client]["list_url"]
    print(f"fetching {list_url} ...")
    html = fetch(list_url)
    soup = BeautifulSoup(html, "lxml")

    print("page title:", (soup.title.get_text(" ", strip=True) if soup.title else "(none)"))
    anchors = soup.select("a[href]")
    print(f"anchors with href: {len(anchors)}")

    # Candidate containers: count EVERY classed ancestor of every link so the
    # real repeating item container (e.g. div.press-release-listing) surfaces.
    containers: Counter[str] = Counter()
    seen_struct = {"body", "header", "footer", "nav", "main", "section", "article",
                   "ul", "li", "div", "span", "a"}
    for a in anchors:
        node = a.parent
        while node is not None and node.name != "[document]":
            cls = node.get("class")
            if cls:
                sel = node.name + "." + ".".join(cls)
                containers[sel] += 1
            node = node.parent

    # Repeating containers (appear >=3 times) are the likely item wrappers.
    # Filter out page-chrome classes (nav/header/megamenu/...) so the real
    # news-item container surfaces.
    CHROME = ("megamenu", "menu", "nav", "header", "footer", "region", "block",
              "container", "field", "paragraph", "dialog", "body", "html", "span",
              "row", "column", "inner", "clearfix", "widescreen", "canvas",
              "settings", "layout", "wrapper", "main-", "-main")
    repeaters = [(s, n) for s, n in containers.items()
                 if n >= 3 and not any(c in s for c in CHROME)]
    print("\nCandidate ITEM_SELECTOR containers (tag.class -> count, appears >=3, non-chrome):")
    if repeaters:
        for sel, n in sorted(repeaters, key=lambda x: -x[1])[:20]:
            print(f"  {n:4d}  {sel}")
    else:
        print("  (none repeated >=3 after filtering chrome — list may be JS-rendered)")
        print("  raw top containers:")
        for sel, n in containers.most_common(12):
            print(f"  {n:4d}  {sel}")

    # Sample links that look like article pages (same netloc, path suggests a post).
    from urllib.parse import urlparse
    base_netloc = urlparse(list_url).netloc
    import re as _re
    sample_links: list[tuple[str, str]] = []
    seen_href = set()
    year_re = _re.compile(r"/20\d\d/")
    art_re = _re.compile(r"/news|/media|/press|/blog|/article|/post|/20\d\d", _re.I)
    for a in anchors:
        href = a.get("href", "")
        if not href:
            continue
        full = href if href.startswith("http") else (list_url.rstrip("/") + href)
        if urlparse(full).netloc != base_netloc:
            continue
        # year-based press-release links first; otherwise generic article-ish
        if not (year_re.search(full) or art_re.search(full)):
            continue
        if full in seen_href:
            continue
        seen_href.add(full)
        txt = a.get_text(" ", strip=True)
        if txt:
            sample_links.append((txt[:60], full[:90]))
        if len(sample_links) >= 12:
            break

    print("\nSample article-like links (title | href):")
    if sample_links:
        for t, h in sample_links:
            print(f"  - {t!r}  {h}")
    else:
        print("  (no article-like links matched — manual inspection of the page may be needed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
