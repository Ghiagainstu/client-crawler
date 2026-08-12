#!/usr/bin/env python3
"""Client news crawler CLI.

Examples
--------
  python cli.py --client sasol                 # crawl all, fetch article bodies
  python cli.py --client sasol --limit 5       # only first 5 listings
  python cli.py --client sasol --no-articles   # list + summary only
  python cli.py --client sasol --notion        # also push to Notion (needs env)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from crawler.core import fetch
from crawler import browser as browser_mod
from crawler.parsers import get_parser, BASE_URL
from crawler import pipeline
from crawler import notion_sync
from crawler import kb_export
from crawler import site_crawler


def fetch_for(client_cfg: dict, url: str, *, session=None, timeout: int = 30,
              delay: float = 1.0, check_robots: bool = True) -> str:
    """Fetch a URL, routing through Playwright when the client needs it.

    Clients protected by a bot/WAF (e.g. Akamai) set ``engine: playwright`` in
    sites.yaml; everything else stays on the lightweight ``requests`` path so
    existing clients (sasol) are untouched.
    """
    if client_cfg.get("engine") == "playwright":
        proxy = os.environ.get("CRAWLER_PROXY")  # optional egress proxy on server
        channel = client_cfg.get("browser_channel")  # e.g. "chrome" for Akamai
        return browser_mod.fetch(url, proxy=proxy, timeout=timeout, wait=3.0,
                                 channel=channel)
    return fetch(url, session=session, timeout=timeout, delay=delay,
                 check_robots=check_robots)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cli")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="client key in config/sites.yaml")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config", "sites.yaml"))
    ap.add_argument("--mode", choices=["news", "site"], default="news",
                    help="news = list-page crawl (default, weekly); site = full-site structured crawl (manual)")
    ap.add_argument("--resume", action="store_true",
                    help="site mode: skip URLs already captured in the checkpoint file")
    ap.add_argument("--limit", type=int, default=0, help="news: max listings; site: max pages (0=config default)")
    ap.add_argument("--no-articles", action="store_true", help="skip fetching article bodies")
    ap.add_argument("--notion", action="store_true", help="push results to Notion (needs env)")
    ap.add_argument("--out", default=None, help="output JSON path (default data/<client>/<date>.json)")
    args = ap.parse_args()

    cfg_all = load_config(args.config)
    if args.client not in cfg_all.get("clients", {}):
        log.error("client '%s' not found. Known: %s", args.client, list(cfg_all["clients"]))
        sys.exit(1)
    c = cfg_all["clients"][args.client]

    # ---- full-site structured crawl (manual trigger) ----
    if args.mode == "site":
        log.info("site mode: structured full-site crawl for %s", args.client)
        result = site_crawler.crawl_site(
            args.client, c,
            max_pages=(args.limit if args.limit else None),
            max_depth=int(c.get("site_max_depth", 3)),
            resume=args.resume,
        )
        exp = site_crawler.export_site(args.client, result)
        # rebuild the 8082 dashboard so the new "全站结构" view shows up
        try:
            from dashboard import build as dash_build
            here = os.path.dirname(os.path.abspath(__file__))
            dash_build.main([
                "--data-dir", os.path.join(here, "data"),
                "--out", os.path.join(here, "dashboard", "index.html"),
            ])
        except Exception as e:  # noqa: BLE001
            log.warning("dashboard rebuild failed (non-fatal): %s", e)
        print(f"\n=== site: {result['total_pages']} pages, "
              f"{len(result['sections'])} sections ===")
        for sec, items in sorted(result["sections"].items(),
                                 key=lambda x: -len(x[1])):
            print(f"- {sec}: {len(items)} 页")
        print(f"\nlocal: {exp['local']}")
        root = os.environ.get("S_DRIVE_ROOT")
        if root:
            print(f"S: {os.path.join(root, args.client, 'site')}/")
        return

    parser = get_parser(c["parser"])
    base = BASE_URL.get(c["parser"], "")
    media_source = c.get("media_source", args.client)
    media_source_url = c.get("media_source_url", c.get("list_url", ""))
    fetch_articles = c.get("fetch_articles", True) and not args.no_articles
    delay = float(c.get("article_delay", 1.0))

    log.info("crawling %s from %s", args.client, c["list_url"])
    list_html = fetch_for(c, c["list_url"])
    raw_items = parser.parse_list(list_html)
    if args.limit:
        raw_items = raw_items[:args.limit]
    log.info("parsed %d listings", len(raw_items))

    if fetch_articles and hasattr(parser, "parse_article"):
        for i, it in enumerate(raw_items, 1):
            try:
                ah = fetch_for(c, it["url"])
                body = parser.parse_article(ah)
                it["content"] = body.get("content", "")
                log.info("[%d/%d] body %d chars: %s", i, len(raw_items),
                         len(it["content"]), it["title"][:50])
            except Exception as e:  # noqa: BLE001
                log.warning("article fetch failed %s: %s", it["url"], e)
                it["content"] = ""
            time.sleep(delay)

    items = pipeline.normalize(args.client, raw_items, media_source, media_source_url)

    out = args.out or os.path.join(
        os.path.dirname(__file__), "data", args.client,
        f"{date.today().isoformat()}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    log.info("wrote %d items -> %s", len(items), out)

    # Export to S: drive (raw archive + KB scaffold). Server-side, no AI needed.
    # Skips gracefully if S_DRIVE_ROOT is unset or the share is unreachable.
    try:
        kb_export.export_client(
            args.client, items,
            media_source=media_source,
            category=c.get("category", "news"),
            date_str=date.today().isoformat(),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("kb_export failed (non-fatal): %s", e)

    if args.notion:
        notion_sync.sync_items(items)

    # quick stdout summary
    print(f"\n=== {args.client}: {len(items)} items ===")
    for it in items[:10]:
        print(f"- [{it['published_at']}] {it['title'][:70]}  ({len(it['content'])} chars body)")


if __name__ == "__main__":
    main()
