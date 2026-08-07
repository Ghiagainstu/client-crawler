#!/usr/bin/env python3
"""Client onboarding web form for the news crawler.

Lets a human clearly see WHICH fields are needed to add a new site, submit
them, and hands the structured request to the agent (火哥的绿龙虾) which then
writes the parser, registers it, runs the crawler and syncs Notion/dashboard.

Run:
  venv/bin/python onboard/app.py                 # http://localhost:8777
  PORT=9000 venv/bin/python onboard/app.py       # custom port (env)
  venv/bin/python onboard/app.py --port 9000     # custom port (arg)

Note: 8765 is 火哥's personal site — do NOT use it here. Default is 8777.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from flask import Flask, request, render_template_string

HERE = os.path.dirname(os.path.abspath(__file__))
REQUESTS_DIR = os.path.join(HERE, "requests")
QUEUE = os.path.join(HERE, "queue.jsonl")
os.makedirs(REQUESTS_DIR, exist_ok=True)

app = Flask(__name__)

FORM_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>新增客户爬虫 · 录入</title>
<style>
  :root{--bg:#f5f7fa;--card:#fff;--ink:#1f2933;--muted:#6b7280;--line:#e5e7eb;--accent:#2563eb;--accent-soft:#eff6ff}
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink);line-height:1.5}
  .wrap{max-width:720px;margin:0 auto;padding:28px 20px 60px}
  h1{font-size:22px;margin:0 0 4px}
  .sub{color:var(--muted);font-size:14px;margin:0 0 20px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:22px;box-shadow:0 1px 3px rgba(16,24,40,.08)}
  .field{margin-bottom:18px}
  label{display:block;font-weight:600;font-size:14px;margin-bottom:6px}
  .req::after{content:" *";color:#dc2626}
  .help{color:var(--muted);font-size:12.5px;margin:4px 0 0}
  input[type=text],textarea,select{width:100%;padding:10px 12px;border:1px solid var(--line);border-radius:9px;font-size:14px;font-family:inherit;background:#fff;color:var(--ink)}
  textarea{resize:vertical;min-height:70px}
  .row{display:flex;gap:14px;flex-wrap:wrap}
  .row .field{flex:1;min-width:240px}
  .check{display:flex;align-items:center;gap:8px;font-size:14px}
  .check input{width:16px;height:16px}
  button{background:var(--accent);color:#fff;border:0;border-radius:10px;padding:12px 22px;font-size:15px;font-weight:600;cursor:pointer}
  button:hover{filter:brightness(.95)}
  .ex{color:var(--accent);font-size:12px}
  code{background:var(--accent-soft);padding:1px 6px;border-radius:5px;font-size:12.5px}
</style>
</head>
<body><div class="wrap">
  <h1>新增客户爬虫 · 录入</h1>
  <p class="sub">填写下面字段，提交后由「火哥的绿龙虾」接手：写解析器 → 接入爬虫 → 同步看板与 Notion。带 <span style="color:#dc2626">*</span> 为必填。</p>
  <form class="card" method="post" action="/submit">
    <div class="row">
      <div class="field">
        <label class="req">客户标识 (client key)</label>
        <input type="text" name="client" placeholder="sasol" pattern="[a-z0-9_-]+" required>
        <p class="help">英文小写、无空格，作为配置键与看板分组。例：<span class="ex">sasol</span></p>
      </div>
      <div class="field">
        <label class="req">客户显示名</label>
        <input type="text" name="name" placeholder="Sasol" required>
        <p class="help">看板/Notion 里展示的名称。例：<span class="ex">Sasol</span></p>
      </div>
    </div>
    <div class="row">
      <div class="field">
        <label class="req">网站根地址</label>
        <input type="text" name="base_url" placeholder="https://www.sasol.com" required>
        <p class="help">客户官网根域名。例：<span class="ex">https://www.sasol.com</span></p>
      </div>
      <div class="field">
        <label class="req">新闻/文章列表页 URL</label>
        <input type="text" name="list_url" placeholder="https://www.sasol.com/media-centre/media-releases" required>
        <p class="help">列出新闻稿的页面（爬虫从这里取条目）。例：<span class="ex">/media-centre/media-releases</span></p>
      </div>
    </div>
    <div class="row">
      <div class="field">
        <label>来源媒体名称</label>
        <input type="text" name="media_source" placeholder="Sasol Media Centre">
        <p class="help">留空则用显示名。看板里“来源媒体”显示的文字。</p>
      </div>
      <div class="field">
        <label>来源媒体链接</label>
        <input type="text" name="media_source_url" placeholder="https://www.sasol.com/media-centre/media-releases">
        <p class="help">留空则用列表页 URL。看板里“来源媒体”点击跳转到此。</p>
      </div>
    </div>
    <div class="field">
      <label class="check"><input type="checkbox" name="fetch_articles" value="1" checked> 抓取全文正文（不仅是标题/摘要）</label>
      <p class="help">勾选后爬虫会进入每篇文章取完整内容；不勾则只取列表中的标题与摘要。</p>
    </div>
    <div class="row">
      <div class="field">
        <label>抓取频率</label>
        <select name="frequency">
          <option value="weekly">每周</option>
          <option value="daily">每日</option>
          <option value="custom">自定义/按需</option>
        </select>
        <p class="help">当前调度在服务器侧统一设置；此处仅备注你的偏好。</p>
      </div>
      <div class="field">
        <label>备注 / 特殊说明</label>
        <textarea name="notes" placeholder="例如：列表页是 JS 动态加载的；需要翻页；某些文章在子域名下…"></textarea>
        <p class="help">任何帮我更快写对解析器的信息都行。</p>
      </div>
    </div>
    <button type="submit">提交给火哥的绿龙虾 →</button>
  </form>
</div></body>
</html>"""

SUCCESS_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>已提交</title>
<style>
  body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f7fa;color:#1f2933;margin:0}
  .wrap{max-width:720px;margin:0 auto;padding:40px 20px}
  .card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:24px;box-shadow:0 1px 3px rgba(16,24,40,.08)}
  h1{font-size:20px;margin:0 0 10px;color:#0f766e}
  pre{background:#0f172a;color:#e2e8f0;padding:16px;border-radius:10px;overflow:auto;font-size:12.5px}
  .next{color:#6b7280;font-size:14px;margin-top:14px}
  a{color:#2563eb}
</style></head><body><div class="wrap"><div class="card">
  <h1>✓ 已提交，火哥的绿龙虾会接手</h1>
  <p class="next">下面是录入的数据（已保存到请求队列）。下一步：写解析器 → 接入爬虫 → 同步看板与 Notion。</p>
  <pre>{{data}}</pre>
  <p class="next">你可以关闭本页。如需再添加，<a href="/">返回录入页</a>。</p>
</div></div></body></html>"""


def _slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "-", s)
    return s.strip("-") or "site"


@app.route("/")
def index():
    return render_template_string(FORM_HTML)


@app.route("/submit", methods=["POST"])
def submit():
    f = request.form
    client = _slug(f.get("client", ""))
    name = (f.get("name") or "").strip()
    base_url = (f.get("base_url") or "").strip()
    list_url = (f.get("list_url") or "").strip()

    errors = []
    if not client:
        errors.append("客户标识无效（需英文小写/数字/连字符）")
    if not name:
        errors.append("缺少客户显示名")
    if not base_url.startswith("http"):
        errors.append("网站根地址需以 http(s):// 开头")
    if not list_url.startswith("http"):
        errors.append("列表页 URL 需以 http(s):// 开头")

    if errors:
        return ("<h3>提交有误：</h3><ul>" +
                "".join(f"<li>{e}</li>" for e in errors) +
                '</ul><p><a href="/">返回修改</a></p>'), 400

    media_source = (f.get("media_source") or name).strip()
    media_source_url = (f.get("media_source_url") or list_url).strip()
    req = {
        "client": client,
        "name": name,
        "base_url": base_url,
        "list_url": list_url,
        "media_source": media_source,
        "media_source_url": media_source_url,
        "fetch_articles": f.get("fetch_articles") == "1",
        "frequency": f.get("frequency", "weekly"),
        "notes": (f.get("notes") or "").strip(),
        "status": "pending",
        "submitted_at": datetime.now().isoformat(timespec="seconds"),
    }

    # Persist
    with open(os.path.join(REQUESTS_DIR, f"{client}.json"), "w", encoding="utf-8") as fp:
        json.dump(req, fp, ensure_ascii=False, indent=2)
    with open(QUEUE, "a", encoding="utf-8") as fp:
        fp.write(json.dumps(req, ensure_ascii=False) + "\n")

    return render_template_string(SUCCESS_HTML, data=json.dumps(req, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8777")),
                    help="listen port (default 8777; 8765 is 火哥's personal site)")
    ap.add_argument("--host", default="0.0.0.0", help="bind host (default 0.0.0.0)")
    args = ap.parse_args()
    app.run(host=args.host, port=args.port, debug=False)
