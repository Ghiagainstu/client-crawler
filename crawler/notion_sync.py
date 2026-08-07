"""Sync normalized items to a Notion database via the REST API.

Configuration (env, never hardcoded):
  NOTION_TOKEN        - internal integration secret (secret_xxx)
  NOTION_DATABASE_ID  - target database id

The integration must have "Insert content" access to the database.
Requires: pip install requests  (already in venv)
"""
from __future__ import annotations

import os
import logging
import requests

log = logging.getLogger("crawler.notion")

NOTION_API = "https://api.notion.com/v1"
MAX_TEXT = 1900  # Notion rich-text block limit headroom


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _chunks(text: str, n: int = MAX_TEXT):
    for i in range(0, len(text), n):
        yield text[i:i + n]


def sync_items(items: list[dict], database_id: str | None = None) -> int:
    token = os.environ.get("NOTION_TOKEN")
    db = database_id or os.environ.get("NOTION_DATABASE_ID")
    if not token or not db:
        log.info("Notion sync skipped: NOTION_TOKEN / NOTION_DATABASE_ID not set.")
        return 0

    created = 0
    for it in items:
        # Truncate content into <=1900-char blocks for page body
        body = it.get("content") or it.get("summary") or ""
        children = []
        for ch in _chunks(body):
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": ch}}]},
            })
        if len(children) > 100:  # Notion caps children per create
            children = children[:100]

        payload = {
            "parent": {"database_id": db},
            "properties": {
                "Name": {"title": [{"text": {"content": it.get("title", "")[:200]}}]},
                "Client": {"select": {"name": it.get("client", "")}},
                "Published": {"date": {"start": it["published_at"]}} if it.get("published_at") else {},
                "Media Source": {"rich_text": [{"text": {"content": it.get("media_source", "")[:200]}}]},
                "Source URL": {"url": it.get("source_url", "")},
            },
            "children": children,
        }
        # strip empty optional props
        payload["properties"] = {k: v for k, v in payload["properties"].items() if v}
        try:
            r = requests.post(f"{NOTION_API}/pages", headers=_headers(), json=payload, timeout=20)
            r.raise_for_status()
            created += 1
        except Exception as e:  # noqa: BLE001
            log.error("Notion create failed for '%s': %s", it.get("title"), e)
    log.info("Notion: created %d / %d items", created, len(items))
    return created
