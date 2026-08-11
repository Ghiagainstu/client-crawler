#!/usr/bin/env bash
# Nightly submission-check + on-demand crawl (pure code; NO AI runtime needed).
# Triggered daily at 19:00 by crawler-check.timer — this script never calls the
# hermes/WorkBuddy AI; it only runs bash + the crawler. The AI onboarding step
# (writing a parser + adding the client to config/sites.yaml) is a SEPARATE task
# that WorkBuddy performs when it picks the submission up from the S: drive.
#
# Behaviour:
#   - Reads S_DRIVE_ROOT/_crawler_queue/requests/<client>.json (8082/add form).
#   - For each submission whose client is ALREADY onboarded in config/sites.yaml,
#     crawl it ONCE per submission. Idempotency = a marker file whose mtime is
#     compared against the request file: if the agent (re)edits the submission,
#     the request file gets newer and we re-crawl.
#   - Submissions NOT yet onboarded are left for the agent (skipped, not marked).
#   - Rebuilds the dashboard + run status afterwards so new data shows up.
set -euo pipefail
shopt -s nullglob   # bare globs expand to nothing when unmatched (no literal "*.json")
APP_DIR="${1:-/opt/client-crawler}"
cd "$APP_DIR"

ROOT="${S_DRIVE_ROOT:-}"
if [ -z "$ROOT" ]; then
  echo "[check] S_DRIVE_ROOT not set (.env missing?) — server writes the queue to the S: drive, so there is nothing to check here."
  exit 0
fi

QUEUE_DIR="$ROOT/_crawler_queue"
REQ_DIR="$QUEUE_DIR/requests"
PROC_DIR="$QUEUE_DIR/processed"
if [ ! -d "$REQ_DIR" ]; then
  echo "[check] no submission queue dir at $REQ_DIR; nothing to do."
  exit 0
fi
mkdir -p "$PROC_DIR"

# Distinct client keys present in the queue (one file per client).
CLIENTS=""
for f in "$REQ_DIR"/*.json; do
  b="$(basename "$f")"
  CLIENTS="${CLIENTS:+$CLIENTS }$b"
done
CLIENTS="$(echo "$CLIENTS" | sed 's#\.json$##' | tr ' ' '\n' | sort -u | tr '\n' ' ')"
if [ -z "${CLIENTS// /}" ]; then
  echo "[check] submission queue empty."
  exit 0
fi

# Onboarded clients from sites.yaml (parser already written by the agent).
ONBOARDED=$(./venv/bin/python -c "import yaml;print(' '.join(yaml.safe_load(open('config/sites.yaml'))['clients'].keys()))")

CRAWLED_ANY=0
for c in $CLIENTS; do
  req="$REQ_DIR/$c.json"
  if ! echo " $ONBOARDED " | grep -q " $c "; then
    echo "[check] $c: not onboarded yet — skipped (agent writes the parser + sites.yaml entry)."
    continue
  fi
  # Idempotency: skip if a processed marker exists AND the request file is not newer.
  marker="$PROC_DIR/$c.marker"
  if [ -f "$marker" ] && [ ! "$req" -nt "$marker" ]; then
    echo "[check] $c: crawl already done for current submission ($marker up to date) — skip."
    continue
  fi
  echo "---- crawling submitted client: $c ----"
  ./venv/bin/python cli.py --client "$c" 2>&1 || echo "[check] $c crawl error (non-fatal, continuing)"
  touch "$marker"
  CRAWLED_ANY=1
done

if [ "$CRAWLED_ANY" -eq 1 ]; then
  echo "[check] rebuilding dashboard + run status"
  ./venv/bin/python dashboard/build.py
  LAST_RUN="$(date +%FT%T)"
  ./venv/bin/python - "$LAST_RUN" "$ROOT" <<'PY'
import json, os, sys, glob, yaml
last_run, root = sys.argv[1], sys.argv[2]
cfg = yaml.safe_load(open('config/sites.yaml'))
counts = {}
for c in cfg['clients']:
    d = os.path.join('data', c); n = 0
    if os.path.isdir(d):
        for f in glob.glob(os.path.join(d, '*.json')):
            try:
                n += len(json.load(open(f)))
            except Exception:
                pass
    counts[c] = n
status = {"last_run": last_run, "clients": counts,
          "empty_clients": [c for c, n in counts.items() if n == 0],
          "status": "warn" if any(n == 0 for n in counts.values()) else "ok"}
with open(os.path.join("dashboard", "_status.json"), "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)
out = os.path.join(root, "_crawler_status"); os.makedirs(out, exist_ok=True)
with open(os.path.join(out, "status.json"), "w", encoding="utf-8") as f:
    json.dump(status, f, ensure_ascii=False, indent=2)
print("status:", status)
PY
else
  echo "[check] no new/onboarded submissions to crawl this run."
fi

echo "[check] done."
