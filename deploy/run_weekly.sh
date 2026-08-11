#!/usr/bin/env bash
# Weekly crawl on Ubuntu. Crawl output goes to the S: drive (kb_export) and to
# data/ for the dashboard — NO GitHub for data. GitHub is used ONLY to pull the
# latest code (parsers/config) pushed by WorkBuddy.
set -euo pipefail
APP_DIR="${1:-/opt/client-crawler}"
cd "$APP_DIR"

echo "==> Pulling latest code (parsers/config from WorkBuddy)"
git pull --ff-only || true

echo "==> Crawling all configured clients"
CLIENTS=$(./venv/bin/python -c "import yaml;print(' '.join(yaml.safe_load(open('config/sites.yaml'))['clients'].keys()))")
EMPTY=()
for c in $CLIENTS; do
  echo "---- client: $c ----"
  out=$(./venv/bin/python cli.py --client "$c" 2>&1)
  echo "$out"
  n=$(echo "$out" | sed -n 's/.*=== .*: \([0-9]*\) items ===.*/\1/p' | tail -1)
  n=${n:-0}
  if [ "$n" -eq 0 ]; then EMPTY+=("$c"); fi
  echo "    -> this run: $n items"
done

echo "==> Building dashboard (dashboard/index.html)"
./venv/bin/python dashboard/build.py

echo "==> Writing run status"
LAST_RUN="$(date +%FT%T)"
EMPTY_STR="${EMPTY[*]:-}"
./venv/bin/python - "$LAST_RUN" "$EMPTY_STR" <<'PY'
import json, os, sys, glob, yaml
last_run = sys.argv[1]
empty = sys.argv[2].split() if sys.argv[2] else []
cfg = yaml.safe_load(open('config/sites.yaml'))
counts = {}
for c in cfg['clients']:
    d = os.path.join('data', c)
    n = 0
    if os.path.isdir(d):
        for f in glob.glob(os.path.join(d, '*.json')):
            try:
                n += len(json.load(open(f)))
            except Exception:
                pass
    counts[c] = n
status = {"last_run": last_run, "clients": counts,
          "empty_clients": empty, "status": "warn" if empty else "ok"}
# local copy for build.py (no S_DRIVE_ROOT needed to render the dashboard)
with open(os.path.join("dashboard", "_status.json"), "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)
# S: drive copy for the agent + LAN access
root = os.environ.get("S_DRIVE_ROOT")
if root:
    out = os.path.join(root, "_crawler_status")
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
print("status:", status)
PY

echo "==> Alerting on empty clients (if webhook configured)"
if [ -n "${WECOM_WEBHOOK:-}" ]; then
  EMPTY_NOW=$(./venv/bin/python -c "import json;print(','.join(json.load(open('dashboard/_status.json')).get('empty_clients',[])))")
  if [ -n "$EMPTY_NOW" ]; then
    MSG="⚠️ client-crawler 周跑：$EMPTY_NOW 抓取到 0 条，请检查站点/选择器是否失效。"
    curl -s -m 10 -H "Content-Type: application/json" \
      -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"$MSG\"}}" "$WECOM_WEBHOOK" || true
  fi
fi

echo "==> Done. Dashboard at :8082. Data + KB on S: drive. WorkBuddy syncs Notion/AI from S: (no GitHub for data)."
