#!/usr/bin/env python3
"""Build the client news dashboard (self-contained index.html) from data/*.json.

The crawler writes data/<client>/<date>.json. This script aggregates all of them
into a single static dashboard that the Ubuntu box serves over the LAN, so the
team can browse each client's weekly news with clickable media sources.

It also consumes dashboard/_status.json (written by run_weekly.sh) to show the
last crawl run time and per-client counts in the header.

Usage:
  python dashboard/build.py
  python dashboard/build.py --data-dir data --out dashboard/index.html
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))


def load_items(data_dir: str):
    items = []
    for path in sorted(glob.glob(os.path.join(data_dir, "*", "*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                rows = json.load(f)
        except Exception as e:  # noqa: BLE001
            print("skip", path, e)
            continue
        if isinstance(rows, list):
            items.extend(rows)
    return items


def load_sites(data_dir: str):
    """Read each client's site crawl index (data/<client>/site/*_index.json)."""
    sites = []
    for path in sorted(glob.glob(os.path.join(data_dir, "*", "site", "*_index.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                idx = json.load(f)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(idx, dict) and idx.get("sections"):
            sites.append(idx)
    return sites


def _load_status(here: str):
    sp = os.path.join(here, "_status.json")
    if os.path.exists(sp):
        try:
            with open(sp, encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            pass
    return {}


def pdate(it):
    try:
        return datetime.strptime(it.get("published_at", "1970-01-01"), "%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return datetime(1970, 1, 1)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>客户每周新闻汇总</title>
<style>
  :root{
    --bg:#f5f7fa; --card:#ffffff; --ink:#1f2933; --muted:#6b7280;
    --line:#e5e7eb; --accent:#2563eb; --accent-soft:#eff6ff;
    --badge:#0f766e; --shadow:0 1px 3px rgba(16,24,40,.08),0 1px 2px rgba(16,24,40,.06);
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
       background:var(--bg);color:var(--ink);line-height:1.55}
  header{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.92);backdrop-filter:blur(6px);
         border-bottom:1px solid var(--line);padding:16px 24px}
  .wrap{max-width:1180px;margin:0 auto;padding:0 24px}
  h1{font-size:20px;margin:0 0 4px}
  .sub{color:var(--muted);font-size:13px}
  .controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px}
  .chips{display:flex;flex-wrap:wrap;gap:8px}
  .chip{border:1px solid var(--line);background:#fff;color:var(--ink);padding:5px 12px;border-radius:999px;
        font-size:13px;cursor:pointer;transition:.15s}
  .chip:hover{border-color:var(--accent)}
  .chip.active{background:var(--accent);border-color:var(--accent);color:#fff}
  .search{flex:1;min-width:200px;padding:8px 12px;border:1px solid var(--line);border-radius:8px;font-size:14px}
  .meta{color:var(--muted);font-size:13px;margin:14px 0 6px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px;padding:8px 0 40px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:var(--shadow);
        display:flex;flex-direction:column;gap:8px}
  .card .top{display:flex;justify-content:space-between;align-items:center;gap:8px}
  .badge{background:var(--accent-soft);color:var(--badge);font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px}
  .date{color:var(--muted);font-size:12px;white-space:nowrap}
  .title{font-size:15px;font-weight:600;margin:0}
  .title a{color:var(--ink);text-decoration:none}
  .title a:hover{color:var(--accent);text-decoration:underline}
  .summary{font-size:13px;color:#374151;margin:0}
  .links{display:flex;gap:14px;margin-top:auto;padding-top:6px;border-top:1px dashed var(--line);font-size:13px}
  .links a{color:var(--accent);text-decoration:none}
  .links a:hover{text-decoration:underline}
  .empty{color:var(--muted);padding:40px;text-align:center}
  .addbtn{display:inline-block;margin-left:14px;background:var(--accent);color:#fff;
          font-size:13px;font-weight:600;padding:5px 13px;border-radius:8px;text-decoration:none;
          vertical-align:middle}
  .addbtn:hover{filter:brightness(.95)}
  .addbtn.alt{background:var(--badge)}
  .tabs{display:flex;gap:8px;margin-top:10px}
  .site-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;box-shadow:var(--shadow);margin:14px 0}
  .site-head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px}
  .site-root{color:var(--accent);text-decoration:none;font-size:13px;word-break:break-all}
  .site-root:hover{text-decoration:underline}
  .section{border-top:1px dashed var(--line);padding:8px 0}
  .section summary{cursor:pointer;display:flex;align-items:center;gap:10px;font-weight:600;font-size:14px}
  .sec-count{color:var(--muted);font-weight:400;font-size:12px}
  .page-list{list-style:none;margin:8px 0 0;padding:0 0 0 18px}
  .page-list li{display:flex;justify-content:space-between;gap:12px;padding:4px 0;border-bottom:1px solid var(--line);font-size:13px}
  .page-list li a{color:var(--ink);text-decoration:none}
  .page-list li a:hover{color:var(--accent);text-decoration:underline}
  .wc{color:var(--muted);font-size:12px;white-space:nowrap}
  code{background:var(--accent-soft);padding:1px 6px;border-radius:5px;font-size:12px}
</style>
</head>
<body>
<header><div class="wrap">
  <h1>客户站点看板</h1>
  <a class="addbtn" href="/add">＋ 添加爬虫</a>
  <a class="addbtn alt" href="http://192.168.0.147:8080/" target="_blank" rel="noopener">AI-Report 看板 ↗</a>
  <div class="sub" id="sub">加载中…</div>
  <div class="controls">
    <div class="chips" id="chips"></div>
    <input class="search" id="q" placeholder="搜索标题 / 摘要 / 客户…" oninput="render()">
  </div>
  <div class="tabs">
    <span class="chip active" id="tab-site" onclick="setTab('site')">🗂️ 全站结构</span>
    <span class="chip" id="tab-news" onclick="setTab('news')">📰 每周新闻</span>
  </div>
</div></header>
<main class="wrap">
  <div id="view-news">
    <div class="meta" id="meta"></div>
    <div class="grid" id="grid"></div>
  </div>
  <div id="view-site" style="display:none">
    <div class="meta" id="site-meta"></div>
    <div id="sites"></div>
  </div>
</main>
<script>
const DB = /*__DATA__*/;
const esc = s => (s||"").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let activeClient = "ALL";
function buildChips(){
  const chips = document.getElementById("chips");
  const all = ["ALL", ...DB.clients];
  chips.innerHTML = all.map(c=>{
    const label = c==="ALL" ? "全部" : c;
    return `<span class="chip ${c===activeClient?'active':''}" onclick="setClient('${esc(c)}')">${esc(label)}</span>`;
  }).join("");
}
function setClient(c){ activeClient=c; buildChips(); render(); }
function render(){
  const q = document.getElementById("q").value.trim().toLowerCase();
  let items = DB.items;
  if(activeClient!=="ALL") items = items.filter(i=>i.client===activeClient);
  if(q) items = items.filter(i=>
     (i.title||"").toLowerCase().includes(q) ||
     (i.summary||"").toLowerCase().includes(q) ||
     (i.client||"").toLowerCase().includes(q));
  document.getElementById("meta").textContent =
     `共 ${items.length} 条 · 客户 ${DB.clients.length} 个`;
  const grid = document.getElementById("grid");
  if(!items.length){ grid.innerHTML = `<div class="empty">没有匹配的新闻</div>`; return; }
  grid.innerHTML = items.map(i=>{
    const src = i.media_source_url ? `<a href="${esc(i.media_source_url)}" target="_blank" rel="noopener">来源媒体 ↗</a>` : "";
    const orig = i.source_url ? `<a href="${esc(i.source_url)}" target="_blank" rel="noopener">原文 ↗</a>` : "";
    return `<div class="card">
      <div class="top"><span class="badge">${esc(i.client)}</span><span class="date">${esc(i.published_at||"")}</span></div>
      <h3 class="title"><a href="${esc(i.source_url||'#')}" target="_blank" rel="noopener">${esc(i.title)}</a></h3>
      <p class="summary">${esc(i.summary||"")}</p>
      <div class="links">${src}${orig}</div>
    </div>`;
  }).join("");
}
const st = DB.status || {};
let sub = "由 client-crawler 自动生成 · 数据来自各客户官网";
if (st && st.last_run) {
  const parts = ["上次运行 " + st.last_run];
  if (st.clients) parts.push("条数 " + Object.entries(st.clients).map(e=>e[0]+" "+e[1]).join(" · "));
  if (st.empty_clients && st.empty_clients.length) parts.push("⚠️ 0条: " + st.empty_clients.join(","));
  sub = parts.join(" ｜ ");
}
document.getElementById("sub").textContent = sub;
buildChips(); render();

let activeTab = "site";
function setTab(t){
  activeTab = t;
  document.getElementById("tab-news").classList.toggle("active", t==="news");
  document.getElementById("tab-site").classList.toggle("active", t==="site");
  document.getElementById("view-news").style.display = t==="news" ? "" : "none";
  document.getElementById("view-site").style.display = t==="site" ? "" : "none";
  if(t==="site") renderSites();
}
function renderSites(){
  const wrap = document.getElementById("sites");
  const sites = DB.sites || [];
  if(!sites.length){
    wrap.innerHTML = `<div class="empty">还没有全站结构数据。运行 <code>python cli.py --client &lt;key&gt; --mode site</code> 后会自动出现在这里。</div>`;
    document.getElementById("site-meta").textContent = "";
    return;
  }
  let total = 0; sites.forEach(s => total += s.total_pages);
  document.getElementById("site-meta").textContent =
     `共 ${sites.length} 个站点 · ${total} 页正文 · 点击板块展开页面`;
  wrap.innerHTML = sites.map(s=>{
    const secs = Object.entries(s.sections||{}).sort((a,b)=>b[1].count-a[1].count);
    return `<div class="site-card">
      <div class="site-head">
        <span class="badge">${esc(s.client)}</span>
        <a class="site-root" href="${esc(s.base_url||'#')}" target="_blank" rel="noopener">${esc(s.base_url||"")}</a>
        <a class="site-root" href="/ai-report/${esc(s.client)}" target="_blank" rel="noopener">📄 AI 报告 ↗</a>
        <span class="date">${s.total_pages} 页 · ${esc((s.crawled_at||"").slice(0,10))}</span>
      </div>
      ${secs.map(([name,info])=>`
        <details class="section">
          <summary><span class="sec-name">${esc(name)}</span><span class="sec-count">${info.count} 页</span></summary>
          <ul class="page-list">${info.pages.map(p=>`<li><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title||'(无标题)')}</a><span class="wc">${p.word_count||0} 字</span></li>`).join("")}</ul>
        </details>`).join("")}
    </div>`;
  }).join("");
}
setTab("site");
</script>
</body>
</html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(HERE, "..", "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "index.html"))
    args = ap.parse_args(argv)

    items = load_items(args.data_dir)
    items.sort(key=pdate, reverse=True)
    clients = sorted({it.get("client", "") for it in items if it.get("client")})
    status = _load_status(HERE)
    sites = load_sites(args.data_dir)
    payload = json.dumps({"clients": clients, "items": items, "status": status, "sites": sites}, ensure_ascii=False)
    out = HTML_TEMPLATE.replace("/*__DATA__*/", payload)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Built {args.out}: {len(items)} items, clients={clients}")


if __name__ == "__main__":
    main()
