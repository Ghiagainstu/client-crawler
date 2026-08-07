#!/usr/bin/env bash
# Deploy client-news-crawler on Ubuntu 20.04/22.04/24.04.
# Safe to re-run (idempotent). Run as the user who will own the app,
# or as root to also install systemd units.
#
# Usage:
#   bash deploy/install.sh [APP_DIR] [SERVICE_USER]
#   e.g.  sudo bash deploy/install.sh /opt/client-crawler deploy
#
# Pre-req: copy the whole repo to APP_DIR first (scp / git clone / tarball).
set -euo pipefail

APP_DIR="${1:-/opt/client-crawler}"
SERVICE_USER="${2:-$(id -un)}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> App dir : $APP_DIR"
echo "==> Owner   : $SERVICE_USER"

mkdir -p "$APP_DIR"
# sync source into APP_DIR if invoked from outside it
if [ "$(realpath "$HERE")" != "$(realpath "$APP_DIR")" ]; then
  cp -r "$HERE"/. "$APP_DIR"/
fi
cd "$APP_DIR"

echo "==> Creating venv + installing deps"
python3 -m venv venv
./venv/bin/pip install -U pip -q
./venv/bin/pip install -r requirements.txt -q

echo "==> Notion sync is handled by WorkBuddy (Notion MCP) — no token needed on this server."

# Smoke test
./venv/bin/python cli.py --client sasol --limit 1 --no-articles
echo "==> Smoke test OK"

# Install systemd units if running as root
if [ "$(id -u)" -eq 0 ]; then
  echo "==> Installing systemd units (root)"
  sed "s#__APP_DIR__#$APP_DIR#g; s#__USER__#$SERVICE_USER#g" \
      "$HERE/deploy/client-crawler.service" > /etc/systemd/system/client-crawler.service
  sed "s#__APP_DIR__#$APP_DIR#g; s#__USER__#$SERVICE_USER#g" \
      "$HERE/deploy/client-crawler.timer" > /etc/systemd/system/client-crawler.timer
  sed "s#__APP_DIR__#$APP_DIR#g; s#__USER__#$SERVICE_USER#g" \
      "$HERE/deploy/dashboard.service" > /etc/systemd/system/dashboard.service
  systemctl daemon-reload
  systemctl enable --now client-crawler.timer
  systemctl enable --now dashboard.service
  echo "==> Timer enabled: weekly Monday 09:00. Dashboard+添加爬虫: http://<host-ip>:8080 (form at /add)"
  echo "    Status: systemctl status client-crawler.timer ; systemctl status dashboard.service"
else
  echo "==> Not root: skip systemd. To enable manually:"
  echo "    sudo cp $HERE/deploy/client-crawler.service $HERE/deploy/client-crawler.timer $HERE/deploy/dashboard.service /etc/systemd/system/"
  echo "    sudo sed -i \"s#__APP_DIR__#$APP_DIR#g; s#__USER__#$(id -un)#g\" /etc/systemd/system/client-crawler.service /etc/systemd/system/client-crawler.timer /etc/systemd/system/dashboard.service"
  echo "    sudo systemctl daemon-reload && sudo systemctl enable --now client-crawler.timer dashboard.service"
  echo "    Or cron for crawl: 0 9 * * 1  cd $APP_DIR && $APP_DIR/deploy/run_weekly.sh $APP_DIR >> /var/log/crawler.log 2>&1"
  echo "    Dashboard (no root): cd $APP_DIR && python3 dashboard/server.py"
fi

echo "==> DONE. Output JSON: $APP_DIR/data/<client>/<date>.json"
