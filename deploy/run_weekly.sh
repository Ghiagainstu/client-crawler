#!/usr/bin/env bash
# Weekly crawl on Ubuntu, then push crawl output back to GitHub so WorkBuddy
# can sync new items to Notion via Notion MCP. This server needs NO Notion token.
set -euo pipefail
APP_DIR="${1:-/opt/client-crawler}"
cd "$APP_DIR"

echo "==> Crawling client news"
./venv/bin/python cli.py --client sasol

echo "==> Pushing data/ to GitHub (force-add; data/ is gitignored locally)"
git add -f data/ 2>/dev/null || true
if git diff --cached --quiet; then
  echo "==> No new data to push"
else
  git -c user.name="client-crawler" -c user.email="crawler@local" \
    commit -m "crawl: $(date +%F)" >/dev/null
  if git push >/dev/null 2>&1; then
    echo "==> Data pushed to GitHub"
  else
    echo "==> git push failed - check server git credential for github.com"
  fi
fi
echo "==> Done. WorkBuddy will sync new items to Notion."
