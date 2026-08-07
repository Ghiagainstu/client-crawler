"""Export crawled items to the S: drive (Client Knowledge Base + raw archive).

Reads S_DRIVE_ROOT from env. On the Ubuntu server this is the local path backing
the Windows S: share, e.g. /media/theeggsh/SSD-2/AI-Report. If unset, export is
skipped with a warning (non-fatal, so the weekly crawl still succeeds).

Per client <slug>, writes:
  <S_DRIVE_ROOT>/<slug>/<category>/<date>.json      # raw archive (goal 3)
  <S_DRIVE_ROOT>/Obsidian/<slug>/KB/                # KB scaffold (goal 1)
      00-Index.md
      01-Facts-产品事实层.md
      02-Selling-Points-卖点主张层.md
      03-Compliance-合规层.md

Design note: this module only lays down STRUCTURE + the raw archive. It never
overwrites existing KB layer files, so manual / WorkBuddy-side AI edits are
preserved. AI extraction of facts (->01) and selling points (->02) is done by
the WorkBuddy side (which can also reach S:), per the agreed option-3 split.
"""
from __future__ import annotations

import os
import json
import logging
from datetime import date

log = logging.getLogger("crawler.kb")


def export_client(client: str, items: list[dict], *, media_source: str = "",
                  category: str = "news", date_str: str | None = None,
                  root: str | None = None) -> bool:
    root = root or os.environ.get("S_DRIVE_ROOT")
    if not root:
        log.warning("S_DRIVE_ROOT not set; skipping KB/archive export for %s", client)
        return False
    if not items:
        log.info("no items for %s; nothing to export", client)
        return False
    date_str = date_str or date.today().isoformat()

    # 1) Raw archive (goal 3): S:/<client>/<category>/<date>.json
    arc_dir = os.path.join(root, client, category)
    os.makedirs(arc_dir, exist_ok=True)
    arc_path = os.path.join(arc_dir, f"{date_str}.json")
    with open(arc_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    log.info("archived %d items -> %s", len(items), arc_path)

    # 2) KB scaffold (goal 1): S:/Obsidian/<client>/KB/  (idempotent)
    kb_dir = os.path.join(root, "Obsidian", client, "KB")
    os.makedirs(kb_dir, exist_ok=True)
    _ensure_index(kb_dir, client, media_source)
    _ensure_layer(
        kb_dir, "01-Facts-产品事实层.md", "术语库 / 产品事实层",
        "每条事实 = 一个来源（one fact = one source）。\n"
        "由 WorkBuddy 侧 AI 抽取自动填充；手动补充也行。\n"
        "建议每条格式：`- <事实陈述> ｜ 来源: [[标题]](<url>)`",
    )
    _ensure_layer(
        kb_dir, "02-Selling-Points-卖点主张层.md", "卖点主张层",
        "每条卖点链接 [[01-Facts-产品事实层]] 的事实。\n"
        "status: suggested（待火哥审后改 approved 才供 agent 消费）。\n"
        "由 WorkBuddy 侧 AI 抽取自动填充。",
    )
    _ensure_layer(
        kb_dir, "03-Compliance-合规层.md", "合规层（锁定）",
        "仅火哥 / Review Agent 可编辑。\n"
        "存放广告法合规红线、禁用词、行业限制等。",
    )
    log.info("KB scaffold ensured at %s", kb_dir)
    return True


def _ensure_index(kb_dir: str, client: str, media_source: str) -> None:
    p = os.path.join(kb_dir, "00-Index.md")
    if os.path.exists(p):
        return
    content = (
        f"# Client Knowledge Base — {client}\n\n"
        f"- **Owner**: 火哥\n"
        f"- **媒体来源**: {media_source or client}\n"
        f"- **结构**:\n"
        f"  - `01-Facts-产品事实层.md` — 术语库 / 产品事实（one fact = one source）\n"
        f"  - `02-Selling-Points-卖点主张层.md` — 卖点主张（链接 01，status: approved 才供 agent）\n"
        f"  - `03-Compliance-合规层.md` — 合规层（锁定，仅火哥 / Review Agent）\n"
        f"- **维护**: 抓取内容由 client-crawler 自动归档到原始数据区（`<client>/<category>/<date>.json`）；"
        f"事实 / 卖点由 WorkBuddy 侧 AI 抽取填入 01 / 02。\n"
    )
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)


def _ensure_layer(kb_dir: str, filename: str, title: str, note: str) -> None:
    p = os.path.join(kb_dir, filename)
    if os.path.exists(p):
        return
    content = (
        f"# {title}\n\n"
        f"> {note}\n\n"
        f"<!-- 由 pipeline 自动维护文件头；以下内容由 AI / 手动追加，勿删此头 -->\n"
    )
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
