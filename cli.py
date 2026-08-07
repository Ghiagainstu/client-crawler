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
from crawler.parsers import get_parser, BASE_URL
from crawler import pipeline
from crawler import notion_sync
from crawler import kb_export

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("cli")


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--client", required=True, help="client key in config/sites.yaml")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(__file__), "config", "sites.yaml"))
    ap.add_argument("--limit", type=int, default=0, help="max listings to process (0=all)")
    ap.add_argument("--no-articles", action="store_true", help="skip fetching article bodies")
    ap.add_argument("--notion", action="store_true", help="push results to Notion (needs env)")
    ap.add_argument("--out", default=None, help="output JSON path (default data/<client>/<date>.json)")
    args = ap.parse_args()

    cfg_all = load_config(args.config)
    if args.client not in cfg_all.get("clients", {}):
        log.error("client '%s' not found. Known: %s", args.client, list(cfg_all["clients"]))
        sys.exit(1)
    c = cfg_all["clients"][args.client]

    parser = get_parser(c["parser"])
    base = BASE_URL.get(c["parser"], "")
    media_source = c.get("media_source", args.client)
    media_source_url = c.get("media_source_url", c.get("list_url", ""))
    fetch_articles = c.get("fetch_articles", True) and not args.no_articles
    delay = float(c.get("article_delay", 1.0))

    log.info("crawling %s from %s", args.client, c["list_url"])
    list_html = fetch(c["list_url"])
    raw_items = parser.parse_list(list_html)
    if args.limit:
        raw_items = raw_items[:args.limit]
    log.info("parsed %d listings", len(raw_items))

    if fetch_articles and hasattr(parser, "parse_article"):
        for i, it in enumerate(raw_items, 1):
            try:
                ah = fetch(it["url"])
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
