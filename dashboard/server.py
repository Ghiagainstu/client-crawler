#!/usr/bin/env python3
"""Combined LAN dashboard + crawler onboarding server (Ubuntu :8082).

NOTE: port 8080 is taken by nginx (the pre-existing "AI-Report" customer
weekly-news dashboard). Flask serves on 8082 to avoid the conflict.

Serves the team on the LAN from a single port:
  GET  /        -> news summary dashboard (dashboard/index.html, built by build.py)
  GET  /add     -> onboarding form (add a new crawler)
  POST /submit  -> save submission, then sync the snapshot to the S: drive queue
                   (S_DRIVE_ROOT/_crawler_queue) so the agent (火哥的绿龙虾) can
                   pick it up directly from the LAN share — no GitHub round-trip
                   for submissions or crawl data. GitHub is kept ONLY for code
                   distribution (WorkBuddy pushes parsers, the server git pulls).

Replaces the old `python -m http.server` static server: it cannot handle the
form POST. Deployed by deploy/dashboard.service (venv python). Requires flask
(in requirements.txt).

Run (standalone / dev):
  venv/bin/python dashboard/server.py            # :8082
  PORT=9000 venv/bin/python dashboard/server.py  # custom port
"""
from __future__ import annotations

import os
import sys
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))             # dashboard/
ROOT = os.path.dirname(HERE)                                   # repo root
sys.path.insert(0, ROOT)
from flask import Flask, request, render_template_string, send_from_directory

from onboard.app import FORM_HTML, SUCCESS_HTML, save_submission

DASHBOARD_HTML = os.path.join(HERE, "index.html")

app = Flask(__name__)


@app.route("/")
def dashboard():
    if not os.path.exists(DASHBOARD_HTML):
        return ("看板尚未生成（先跑一次 deploy/run_weekly.sh）。<br>"
                '<a href="/add">添加爬虫 →</a>'), 200
    return send_from_directory(HERE, "index.html")


@app.route("/add")
def add():
    return render_template_string(FORM_HTML)


@app.route("/submit", methods=["POST"])
def submit():
    errors, req = save_submission(request.form)
    if errors:
        return ("<h3>提交有误：</h3><ul>" +
                "".join(f"<li>{e}</li>" for e in errors) +
                '</ul><p><a href="/add">返回修改</a></p>'), 400

    synced = _sync_submission_to_s(req["client"])
    note = "（已同步到 S: 盘队列，火哥的绿龙虾会接手）" if synced else "（本地已保存；S: 盘未配置，请告知火哥）"
    return render_template_string(
        SUCCESS_HTML,
        data=__import__("json").dumps(req, ensure_ascii=False, indent=2) + "\n\n" + note,
    )


@app.route("/ai-report/")
@app.route("/ai-report/<client>")
def ai_report(client: str | None = None):
    """Entry point for 火哥的绿龙虾 (WorkBuddy) AI analysis reports.

    The green-lobster WorkBuddy automation writes a self-contained HTML report
    to S_DRIVE_ROOT/<client>/site/<date>_ai_report.html after it analyzes the
    Friday full-site crawl. This route serves it over the LAN so the 8080
    AI-Report hub can link here. Date-agnostic: it always shows the latest
    report for a client.

      GET /ai-report/            -> list clients that have an AI report
      GET /ai-report/<client>   -> latest AI report HTML for that client
    """
    root = os.environ.get("S_DRIVE_ROOT")
    if not root:
        return ("AI 报告依赖 S_DRIVE_ROOT（S: 盘）未配置。", 200)
    if client is None:
        rows = []
        for c in sorted(os.listdir(root)):
            cdir = os.path.join(root, c, "site")
            if not os.path.isdir(cdir):
                continue
            reps = sorted(f for f in os.listdir(cdir) if f.endswith("_ai_report.html"))
            if reps:
                rows.append(f'<li><a href="/ai-report/{c}">{c}</a> '
                            f'（{len(reps)} 份，最新 {reps[-1].replace("_ai_report.html","")}）</li>')
        if not rows:
            return ("尚无绿龙虾 AI 分析报告。周一自动化会基于周五全站爬取数据生成。", 200)
        return ("<h3>绿龙虾·全站 AI 分析报告</h3><ul>" + "".join(rows) + "</ul>", 200)
    cdir = os.path.join(root, client, "site")
    if not os.path.isdir(cdir):
        return (f"客户 {client} 没有 site 数据。", 200)
    reps = sorted(f for f in os.listdir(cdir) if f.endswith("_ai_report.html"))
    if not reps:
        return (f"客户 {client} 暂无 AI 分析报告（周一自动化生成后会出现在这里）。", 200)
    return send_from_directory(cdir, reps[-1])


def _sync_submission_to_s(client: str) -> bool:
    """Bridge to the agent via the S: drive (no GitHub for data).

    Copy the submission snapshot + append to the queue under S_DRIVE_ROOT so the
    agent (火哥的绿龙虾) can pick it up directly from the LAN share — no GitHub
    round-trip for submissions or crawl data. GitHub is kept ONLY for code
    distribution (WorkBuddy pushes parsers, the server git pulls).
    """
    root = os.environ.get("S_DRIVE_ROOT")
    if not root:
        print("[submit] S_DRIVE_ROOT not set; submission stays local only")
        return False
    req_file = os.path.join(ROOT, "onboard", "requests", f"{client}.json")
    if not os.path.exists(req_file):
        return False
    try:
        qdir = os.path.join(root, "_crawler_queue", "requests")
        os.makedirs(qdir, exist_ok=True)
        shutil.copy2(req_file, os.path.join(qdir, f"{client}.json"))
        qlog = os.path.join(root, "_crawler_queue", "queue.jsonl")
        with open(req_file, encoding="utf-8") as f:
            data = f.read().strip()
        if data:
            with open(qlog, "a", encoding="utf-8") as f:
                f.write(data + "\n")
        print(f"[submit] synced submission {client} to S: drive queue")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[submit] S: sync failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8082")),
                    help="listen port (default 8082; 8080 is taken by nginx AI-Report)")
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    app.run(host=args.host, port=args.port, debug=False)
