#!/usr/bin/env python3
"""Combined LAN dashboard + crawler onboarding server (Ubuntu :8082).

NOTE: port 8080 is taken by nginx (the pre-existing "AI-Report" customer
weekly-news dashboard). Flask serves on 8082 to avoid the conflict.

Serves the team on the LAN from a single port:
  GET  /        -> news summary dashboard (dashboard/index.html, built by build.py)
  GET  /add     -> onboarding form (add a new crawler)
  POST /submit  -> save submission, then push the snapshot to GitHub so the
                   agent (火哥的绿龙虾) can pick it up, scaffold the parser and
                   let the weekly crawl pick up the new client.

Replaces the old `python -m http.server` static server: it cannot handle the
form POST. Deployed by deploy/dashboard.service (venv python). Requires flask
(in requirements.txt).

Run (standalone / dev):
  venv/bin/python dashboard/server.py            # :8082
  PORT=9000 venv/bin/python dashboard/server.py  # custom port
"""
from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))             # dashboard/
ROOT = os.path.dirname(HERE)                                   # repo root
sys.path.insert(0, ROOT)
from flask import Flask, request, render_template_string, send_from_directory

from onboard.app import FORM_HTML, SUCCESS_HTML, save_submission

HERE = os.path.dirname(os.path.abspath(__file__))
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

    pushed = _push_submission(req["client"])
    note = "（已推送到 GitHub，火哥的绿龙虾会接手）" if pushed else "（本地已保存；推送未成功，请告知火哥）"
    return render_template_string(
        SUCCESS_HTML,
        data=__import__("json").dumps(req, ensure_ascii=False, indent=2) + "\n\n" + note,
    )


def _push_submission(client: str) -> bool:
    """Bridge to the agent: force-add the submission snapshot and push to GitHub.

    The server already has a github.com push credential (run_weekly.sh uses it
    for data/). Submissions are low-frequency, so a simple pull-then-push is
    safe enough. Set CLIENT_CRAWLER_NO_PUSH=1 to disable (dev/testing).
    """
    if os.environ.get("CLIENT_CRAWLER_NO_PUSH"):
        print("[submit] push disabled by env (CLIENT_CRAWLER_NO_PUSH)")
        return False
    req_file = os.path.join(ROOT, "onboard", "requests", f"{client}.json")
    if not os.path.exists(req_file):
        return False
    try:
        subprocess.run(["git", "pull", "--ff-only"], cwd=ROOT, check=False,
                        capture_output=True, timeout=60)
        subprocess.run(["git", "add", "-f", req_file], cwd=ROOT, check=True,
                       capture_output=True, timeout=30)
        subprocess.run(["git", "-c", "user.name=client-crawler",
                        "-c", "user.email=crawler@local", "commit",
                        "-m", f"onboard: {client}"], cwd=ROOT, check=False,
                       capture_output=True, timeout=30)
        r = subprocess.run(["git", "push"], cwd=ROOT, capture_output=True, timeout=60)
        ok = r.returncode == 0
        print(f"[submit] pushed submission {client}: {ok}")
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"[submit] push failed: {e}")
        return False


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8082")),
                    help="listen port (default 8082; 8080 is taken by nginx AI-Report)")
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    app.run(host=args.host, port=args.port, debug=False)
