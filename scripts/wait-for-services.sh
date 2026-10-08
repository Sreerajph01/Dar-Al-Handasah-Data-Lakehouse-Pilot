#!/usr/bin/env bash
# =============================================================================
# scripts/wait-for-services.sh — wait for a list of host:port pairs to be ready
# Usage: ./wait-for-services.sh host1:port1 host2:port2 ...
# =============================================================================
set -euo pipefail

TIMEOUT=${WAIT_TIMEOUT:-300}
SLEEP_INTERVAL=3

wait_for() {
  local host="$1"
  local port="$2"
  local elapsed=0

  echo "Waiting for ${host}:${port} ..."
  while ! nc -z "${host}" "${port}" 2>/dev/null; do
    if [[ ${elapsed} -ge ${TIMEOUT} ]]; then
      echo "ERROR: Timed out waiting for ${host}:${port} after ${TIMEOUT}s" >&2
      exit 1
    fi
    sleep "${SLEEP_INTERVAL}"
    elapsed=$((elapsed + SLEEP_INTERVAL))
  done
  echo "  ✓ ${host}:${port} is ready (${elapsed}s)"
}

for target in "$@"; do
  host="${target%%:*}"
  port="${target##*:}"
  wait_for "${host}" "${port}"
done

echo "All services ready."
