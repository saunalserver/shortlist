#!/usr/bin/env bash
# Jooble API key check/swap. Key: free at https://jooble.org/api, 500 requests LIFETIME.
# Usage:
#   scripts/jooble_key.sh check          # spends 1 request of the key, prints ALIVE/DEAD
#   scripts/jooble_key.sh set <NEW_KEY>  # validates new key, then swaps it into pipeline/.env
# No service restart needed — each pipeline run (07:00/19:00 timer) reads .env fresh.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=".env"

probe() {  # probe <key> -> exit 0 alive, exit 1 dead, prints detail
  local code
  code=$(curl -s -o /tmp/jooble_probe.json -w "%{http_code}" -X POST \
    "https://jooble.org/api/$1" -H "Content-Type: application/json" \
    -d '{"keywords":"operations specialist","location":"Vancouver, BC","page":1}')
  case "$code" in
    200) echo "ALIVE (HTTP 200, test query matched $(python3 -c "import json;print(json.load(open('/tmp/jooble_probe.json'))['totalCount'])") jobs)"; return 0 ;;
    402|403) echo "DEAD (HTTP $code — lifetime quota exhausted): $1"; return 1 ;;
    *) echo "UNEXPECTED HTTP $code: $(head -c 200 /tmp/jooble_probe.json)"; return 1 ;;
  esac
}

case "${1:-}" in
  check)
    probe "$(grep '^JOOBLE_API_KEY=' "$ENV_FILE" | cut -d= -f2-)"
    ;;
  set)
    [ -n "${2:-}" ] || { echo "usage: $0 set <NEW_KEY>"; exit 1; }
    probe "$2" || { echo "new key failed validation — .env left unchanged"; exit 1; }
    sed -i "s|^JOOBLE_API_KEY=.*|JOOBLE_API_KEY=$2|" "$ENV_FILE"
    echo "swapped into $ENV_FILE — effective next run"
    ;;
  *)
    echo "usage: $0 check | set <NEW_KEY>"; exit 1 ;;
    esac
