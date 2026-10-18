#!/bin/sh
set -eu
ADMIN_ACCESS_TOKEN=${ADMIN_ACCESS_TOKEN:-}
if [ "${#ADMIN_ACCESS_TOKEN}" -lt 32 ]; then
  echo 'Set a random ADMIN_ACCESS_TOKEN of at least 32 characters in the host environment.' >&2
  exit 1
fi
if [ ! -f "${MEET_INVENTORY_PATH:-$ADMIN_STORAGE_DIR/meet_inventory.json}" ]; then
  python -m backend.prepare_meet_sources --download --output "$ADMIN_STORAGE_DIR"
fi
exec uvicorn backend.meet_main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
