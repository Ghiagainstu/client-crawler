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

echo "==> Preparing .env (secrets) — fill NOTION_* if you use Notion sync"
if [ ! -f "$APP_DIR/.env" ]; then
  cat > "$APP_DIR/.env" <<'EOF'
# Notion sync (optional). Leave blank to skip sync.
# Get token from https://www.notion.com/my-integrations
NOTION_TOKEN=
NOTION_DATABASE_ID=
EOF
  chmod 600 "$APP_DIR/.env"
  chown "$SERVICE_USER":"$SERVICE_USER" "$APP_DIR/.env" 2>/dev/null || true
fi

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
  systemctl daemon-reload
  systemctl enable --now client-crawler.timer
  echo "==> Timer enabled: weekly Monday 09:00. Status: systemctl status client-crawler.timer"
else
  echo "==> Not root: skip systemd. To enable manually, copy deploy/*.service/.timer to /etc/systemd/system"
  echo "    and run: systemctl daemon-reload && systemctl enable --now client-crawler.timer"
  echo "    Or use cron: 0 9 * * 1  cd $APP_DIR && $APP_DIR/venv/bin/python cli.py --client sasol --notion >> /var/log/crawler.log 2>&1"
fi

echo "==> DONE. Output JSON: $APP_DIR/data/<client>/<date>.json"
