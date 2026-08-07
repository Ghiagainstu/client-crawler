"""Normalize raw parsed items into the standard schema used by the
dashboard + Notion, and deduplicate by URL."""
from __future__ import annotations

from datetime import datetime, timezone
import re

DATE_FORMATS = ["%d %b, %Y", "%d %B, %Y", "%b %d, %Y", "%Y-%m-%d"]


def parse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    # last resort: extract a year-month-day pattern
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def normalize(client: str, raw_items: list[dict], media_source: str,
              media_source_url: str) -> list[dict]:
    out = []
    seen = set()
    for it in raw_items:
        url = it.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        published = parse_date(it.get("date_raw", ""))
        out.append({
            "client": client,
            "source_url": url,
            "title": it.get("title", ""),
            "published_at": published,
            "summary": it.get("summary", ""),
            "content": it.get("content", ""),
            "media_source": media_source,
            "media_source_url": media_source_url,
            "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    return out
