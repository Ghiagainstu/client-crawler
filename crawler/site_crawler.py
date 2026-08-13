"""Full-site structured crawler.

Discovers a client's URLs (sitemap.xml first, BFS fallback), classifies each
page into a section by its URL path, extracts clean main-text content, and
writes a *categorized* archive so you can clearly see "what the site has".

This is intentionally separate from the news crawler (cli.py --mode news):
  - news  : one list page -> items (+ article bodies)  -> weekly, auto
  - site  : whole site  -> sections of full-text pages  -> manual trigger

Outputs (categorized by section):
  S_DRIVE_ROOT/<client>/site/<date>.json        full grouped payload
  S_DRIVE_ROOT/<client>/site/<date>_index.json  section outline (titles+urls)
  data/<client>/site/<date>.json                local copy (always written)

Usage:
  python cli.py --client sasol --mode site
  python cli.py --client sasol --mode site --limit 50   # cap pages for a pilot
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, urljoin, urlunparse, parse_qsl, urlencode
from xml.etree import ElementTree as ET

import yaml
from bs4 import BeautifulSoup

from crawler.core import fetch, can_fetch, DEFAULT_HEADERS
from crawler import browser as browser_mod

log = logging.getLogger("crawler.site")

# Assets / non-HTML we never want to treat as a content page.
_SKIP_EXT = {
    "css", "js", "png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "zip", "rar", "tar",
    "gz", "mp4", "mp3", "wav", "avi", "mov", "woff", "woff2", "ttf", "eot",
    "xml", "json", "rss", "txt", "csv",
}
# Query params that are tracking-only; dropped when normalizing for dedup.
_TRACK_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                 "utm_content", "fbclid", "gclid", "ref", "_ga", "mc_cid",
                 "mc_eid", "igshid", "wt_mc", "wt_zmc"}
_CHROME_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form",
                "noscript", "iframe", "svg", "button"}


def _normalize(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return ""
    q = [(k, v) for k, v in parse_qsl(p.query)
         if k.lower() not in _TRACK_PARAMS]
    new = p._replace(fragment="", query=urlencode(q))
    return urlunparse(new).rstrip("/")


def _is_content_url(url: str, netloc: str, path_prefix: str | None = None) -> bool:
    if not url:
        return False
    p = urlparse(url)
    if p.netloc != netloc:
        return False
    if path_prefix and not p.path.startswith(path_prefix):
        # scope the crawl to a sub-tree (e.g. the English area /global/en)
        return False
    if p.path.lower().endswith(tuple("." + e for e in _SKIP_EXT)):
        return False
    return True


def _make_fetch_fn(cfg: dict):
    """Return a fetch callable matching ``core.fetch``'s signature.

    For Akamai-protected clients (``engine: playwright``) it routes through the
    real-browser engine; otherwise it falls back to the lightweight ``requests``
    path so non-WAF clients (sasol) are untouched.
    """
    if cfg.get("engine") == "playwright":
        channel = cfg.get("browser_channel")
        proxy = os.environ.get("CRAWLER_PROXY")
        def _browser_fetch(url, *, session=None, delay=0.0,
                           check_robots=True, timeout=30, **_extra):
            return browser_mod.fetch(url, proxy=proxy, timeout=timeout,
                                     wait=3.0, channel=channel)
        return _browser_fetch
    return fetch


def _discover_sitemap(base_url: str, session=None, fetch_fn=None,
                      path_prefix: str | None = None) -> list[str]:
    """Return URLs listed in sitemap.xml (handles sitemap index too)."""
    _fetch = fetch_fn or fetch
    out: list[str] = []
    base = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    # generic root sitemaps always tried; robots-declared ones are scoped to the
    # crawl prefix so we don't fetch every locale's sitemap (e.g. just /global/en)
    seeds = [base + "/sitemap.xml", base + "/sitemap_index.xml"]
    # robots.txt often declares the real sitemap location via "Sitemap:" lines
    try:
        robots_txt = _fetch(base + "/robots.txt", session=session,
                            delay=0.1, check_robots=False, timeout=10)
        for line in robots_txt.splitlines():
            if line.lower().startswith("sitemap:"):
                sm = line.split(":", 1)[1].strip()
                if not sm:
                    continue
                if path_prefix and not urlparse(sm).path.startswith(path_prefix):
                    continue  # skip other locales' sitemaps
                seeds.insert(0, sm)
    except Exception as e:  # noqa: BLE001
        log.debug("robots.txt sitemap peek failed: %s", e)
    seen = set()
    for seed in seeds:
        try:
            xml = _fetch(seed, session=session, delay=0.2, check_robots=False)
        except Exception as e:  # noqa: BLE001
            log.debug("sitemap fetch failed %s: %s", seed, e)
            continue
        try:
            root = ET.fromstring(xml.encode("utf-8"))
        except Exception:
            continue
        # sitemap index -> nested <sitemap><loc>
        for loc in root.iter():
            tag = loc.tag.lower()
            if tag.endswith("loc"):
                u = loc.text.strip()
                if u and u not in seen:
                    seen.add(u)
                    out.append(u)
    # If we only got nested sitemaps, fetch those too (one level).
    if out and out[0].endswith((".xml",)) and "sitemap" in out[0]:
        nested = []
        for sm in list(out):
            try:
                x = _fetch(sm, session=session, delay=0.2, check_robots=False)
                r = ET.fromstring(x.encode("utf-8"))
                for loc in r.iter():
                    if loc.tag.lower().endswith("loc"):
                        u = loc.text.strip()
                        if u and u not in seen:
                            seen.add(u)
                            nested.append(u)
            except Exception:
                pass
        out = nested or out
    return out


def discover_urls(base_url: str, netloc: str, max_pages: int,
                  max_depth: int = 3, session=None,
                  path_prefix: str | None = None, fetch_fn=None,
                  priority: list | None = None) -> list[str]:
    """sitemap first, then BFS from base_url to fill the cap.

    ``path_prefix`` (e.g. ``/global/en``) restricts the crawl to a URL sub-tree
    so a client can crawl "the English site" rather than the whole domain.
    ``fetch_fn`` lets Akamai-protected clients route through the browser engine.
    ``priority`` is an optional list of first-path-segments to surface first
    (e.g. ["products", "knowledge"]) so high-value sections aren't starved by
    the alphabetical cap — otherwise a 300-page cap on a big site can miss the
    whole product area.
    """
    _fetch = fetch_fn or fetch
    found = set()
    for u in _discover_sitemap(base_url, session=session, fetch_fn=fetch_fn,
                               path_prefix=path_prefix):
        n = _normalize(u)
        if _is_content_url(n, netloc, path_prefix):
            found.add(n)
    log.info("sitemap yielded %d content URLs", len(found))

    if len(found) < max_pages:
        log.info("BFS from %s (depth=%d) to fill cap", base_url, max_depth)
        visited = set(found)
        frontier = [base_url]
        depth = 0
        while frontier and depth < max_depth and len(found) < max_pages:
            nxt = []
            for url in frontier:
                try:
                    html = _fetch(url, session=session, delay=0.3, check_robots=True)
                except Exception as e:  # noqa: BLE001
                    log.warning("BFS fetch failed %s: %s", url, e)
                    continue
                soup = BeautifulSoup(html, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    if href.startswith(("mailto:", "tel:", "javascript:")):
                        continue
                    absu = urljoin(url, href)
                    n = _normalize(absu)
                    if (_is_content_url(n, netloc, path_prefix)
                            and n not in visited):
                        visited.add(n)
                        found.add(n)
                        nxt.append(n)
                        if len(found) >= max_pages:
                            break
            frontier = nxt
            depth += 1
    if not priority:
        return sorted(found)[:max_pages]
    # surface priority sections first (stable within each), then the rest
    def _path_seg(u: str) -> str:
        parts = [p for p in urlparse(u).path.split("/") if p]
        if path_prefix:
            pre = [p for p in path_prefix.split("/") if p]
            if parts[:len(pre)] == pre:
                parts = parts[len(pre):]
        return parts[0] if parts else ""
    def _sort_key(u: str):
        seg = _path_seg(u)
        if seg in priority:
            return (0, priority.index(seg), u)
        return (1, 0, u)
    return sorted(found, key=_sort_key)[:max_pages]


def classify_section(url: str, aliases: dict | None = None,
                     path_prefix: str | None = None) -> str:
    parts = [p for p in urlparse(url).path.split("/") if p]
    if not parts:
        return "home"
    # skip the locale/scoping prefix (e.g. global/en) so sections reflect the
    # real site structure rather than every page collapsing to "global"
    if path_prefix:
        pre = [p for p in path_prefix.split("/") if p]
        if parts[:len(pre)] == pre:
            parts = parts[len(pre):]
    if not parts:
        return "home"
    seg = parts[0]
    if aliases and seg in aliases:
        return aliases[seg]
    return seg


def _best_content_node(soup: BeautifulSoup):
    """readability-lite: the container with the most words."""
    body = soup.body or soup
    for tag in _CHROME_TAGS:
        for el in body.find_all(tag):
            el.decompose()
    # drop boilerplate-prone containers by class keyword (sidebars, breadcrumbs,
    # related/quick links, share/social, cookie banners, menus)
    _BLAH = ("sidebar", "related", "breadcrumb", "quick", "menu", "share",
             "social", "cookie", "banner", "promo", "cta", "newsletter",
             "footer", "header", "nav")
    for el in list(body.find_all(class_=True)):
        try:
            cls_list = el.get("class") or []
        except Exception:
            continue
        cls = " ".join(cls_list).lower()
        if any(k in cls for k in _BLAH):
            try:
                el.decompose()
            except Exception:
                pass
    candidates = []
    for el in body.find_all(["article", "main", "section", "div"]):
        text = el.get_text(" ", strip=True)
        words = len(text.split())
        if words > 30:  # ignore thin boilerplate blocks
            candidates.append((words, el))
    if not candidates:
        # fallback: whole body text
        return body
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def extract_content(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    title = ""
    if soup.title:
        title = soup.title.get_text(" ", strip=True)
    h1 = soup.find("h1")
    if not title and h1:
        title = h1.get_text(" ", strip=True)
    node = _best_content_node(soup)
    text = node.get_text("\n", strip=True) if node else ""
    # collapse blank lines + drop consecutive duplicate lines (breadcrumb/title echo)
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    deduped = []
    for ln in lines:
        if deduped and ln == deduped[-1]:
            continue
        deduped.append(ln)
    text = "\n".join(deduped)
    text = re.sub(r"\n{3,}", "\n\n", text)
    desc = soup.find("meta", attrs={"name": "description"})
    meta_desc = desc.get("content", "").strip() if desc else ""
    return {
        "url": url,
        "title": title,
        "meta_description": meta_desc,
        "text": text,
        "word_count": len(text.split()),
    }


def _save_checkpoint(result: dict, path: str) -> None:
    """Persist partial progress so an interrupted long crawl can resume."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        log.info("checkpoint saved: %s (%d pages)", path, result["total_pages"])
    except Exception as e:  # noqa: BLE001
        log.warning("checkpoint save failed: %s", e)


def crawl_site(client: str, cfg: dict, *, max_pages: int | None = None,
               delay: float | None = None, max_depth: int = 3,
               resume: bool = False, checkpoint_every: int = 25) -> dict:
    """Full-site structured crawl with checkpoint + resume.

    A checkpoint is written to data/<client>/site/.inprogress.json every
    `checkpoint_every` pages, so if the run is killed mid-way the progress is
    not lost. Pass resume=True to skip URLs already captured in that file.
    """
    base = cfg.get("base_url") or cfg.get("list_url")
    if not base:
        raise ValueError(f"client {client} needs base_url/list_url")
    netloc = urlparse(base).netloc
    max_pages = max_pages or int(cfg.get("site_max_pages", 500))
    delay = delay or float(cfg.get("site_delay", 0.5))
    aliases = cfg.get("site_sections") or {}
    path_prefix = cfg.get("site_path_prefix")  # e.g. /global/en -> English-only
    priority = cfg.get("site_priority")  # e.g. ["products", "knowledge"] first
    fetch_fn = _make_fetch_fn(cfg)  # playwright engine for Akamai clients
    cp_path = os.path.join("data", client, "site", ".inprogress.json")
    resume_from = cp_path if resume else None

    # resume: reload already-captured pages/sections
    pages: list[dict] = []
    sections: dict[str, list[dict]] = {}
    seen_urls: set[str] = set()
    if resume_from and os.path.exists(resume_from):
        try:
            prev = json.load(open(resume_from, encoding="utf-8"))
            for sec, items in prev.get("sections", {}).items():
                sections.setdefault(sec, []).extend(items)
                for it in items:
                    pages.append(it)
                    seen_urls.add(it["url"])
            log.info("resumed from %s: %d pages already done", resume_from, len(pages))
        except Exception as e:  # noqa: BLE001
            log.warning("resume load failed: %s", e)

    log.info("discovering up to %d pages for %s (%s)", max_pages, client, base)
    urls = discover_urls(base, netloc, max_pages, max_depth,
                         path_prefix=path_prefix, fetch_fn=fetch_fn,
                         priority=priority)
    urls = [u for u in urls if u not in seen_urls]
    log.info("discovered %d new URLs (%d already done)", len(urls), len(seen_urls))

    # Akamai-protected (playwright) clients can't have robots.txt fetched by
    # urllib — it gets the WAF block page, which RobotFileParser reads as a
    # blanket "disallow all". For those we skip the urllib robots gate (their
    # real robots.txt is "User-agent: * Allow: /" anyway).
    respect_robots = cfg.get("engine") != "playwright"
    done = 0
    for i, url in enumerate(urls, 1):
        if respect_robots and not can_fetch(url):
            log.info("robots disallows %s — skip", url)
            continue
        try:
            html = fetch_fn(url, delay=delay, check_robots=True)
        except Exception as e:  # noqa: BLE001
            log.warning("fetch failed %s: %s", url, e)
            continue
        c = extract_content(html, url)
        sec = classify_section(url, aliases, path_prefix)
        c["section"] = sec
        sections.setdefault(sec, []).append(c)
        pages.append(c)
        done += 1
        if checkpoint_every and done % checkpoint_every == 0:
            _save_checkpoint({
                "client": client, "base_url": base,
                "crawled_at": datetime.now(timezone.utc).isoformat(),
                "total_pages": len(pages), "sections": sections,
            }, cp_path)
        if i % 25 == 0:
            log.info("progress %d/%d", i, len(urls))
        time.sleep(delay)

    result = {
        "client": client,
        "base_url": base,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "total_pages": len(pages),
        "sections": sections,
    }
    # success: drop the checkpoint file
    if os.path.exists(cp_path):
        try:
            os.remove(cp_path)
        except Exception:  # noqa: BLE001
            pass
    return result


def export_site(client: str, result: dict, category: str = "site",
                date_str: str | None = None) -> dict:
    from datetime import date as _date
    date_str = date_str or _date.today().isoformat()
    # local copy (always)
    local_dir = os.path.join("data", client, category)
    os.makedirs(local_dir, exist_ok=True)
    local_path = os.path.join(local_dir, f"{date_str}.json")
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    # index outline: section -> count + page titles/urls (the "what's here" view)
    index = {
        "client": result["client"],
        "base_url": result["base_url"],
        "crawled_at": result["crawled_at"],
        "total_pages": result["total_pages"],
        "sections": {},
    }
    for sec, items in result["sections"].items():
        index["sections"][sec] = {
            "count": len(items),
            "pages": [{"title": it["title"], "url": it["url"],
                       "word_count": it["word_count"]} for it in items],
        }

    # persist the index + markdown outline locally too, so the 8082 dashboard
    # (dashboard/build.py -> load_sites reads data/<client>/site/*_index.json)
    # can render the 全站结构 tab without depending on the S: mount.
    with open(os.path.join(local_dir, f"{date_str}_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    with open(os.path.join(local_dir, f"{date_str}_index.md"), "w", encoding="utf-8") as f:
        f.write(_md_outline(result, index))

    root = os.environ.get("S_DRIVE_ROOT")
    if root:
        out_dir = os.path.join(root, client, category)
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f"{date_str}.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        with open(os.path.join(out_dir, f"{date_str}_index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        # also drop a markdown outline for quick human reading
        md = [_md_outline(result, index)]
        with open(os.path.join(out_dir, f"{date_str}_index.md"), "w", encoding="utf-8") as f:
            f.write(md[0])
    return {"local": local_path, "result": result, "index": index}


def _md_outline(result: dict, index: dict) -> str:
    lines = [f"# {result['client']} 站点结构（{result['total_pages']} 页）",
             f"- 根地址：{result['base_url']}",
             f"- 抓取时间：{result['crawled_at']}", "", "## 板块总览", ""]
    for sec, info in sorted(index["sections"].items(), key=lambda x: -x[1]["count"]):
        lines.append(f"### {sec}（{info['count']} 页）")
        for p in info["pages"][:30]:
            t = p["title"] or "(无标题)"
            lines.append(f"- [{t}]({p['url']})  ")
        if info["count"] > 30:
            lines.append(f"- … 其余 {info['count'] - 30} 页见 JSON")
        lines.append("")
    return "\n".join(lines)
