#!/bin/bash
# Configures the native systemd-managed Ollama service with flash attention
# and KV-cache quantization, so the setting is applied consistently instead
# of hand-edited on VRAM-constrained hardware. Docker Compose installations
# configure the same environment through docker-compose.yml.
#
# Usage: sudo ./scripts/configure-ollama.sh [KV_CACHE_TYPE]
#   KV_CACHE_TYPE defaults to q8_0. Use f16 to disable quantization, or
#   q4_0 for a more aggressive (lower-quality) cache.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "This script edits /etc/systemd/system and restarts a system service — run it with sudo." >&2
  exit 1
fi

KV_CACHE_TYPE="${1:-q8_0}"
DROPIN_DIR="/etc/systemd/system/ollama.service.d"
DROPIN_FILE="$DROPIN_DIR/override.conf"

DESIRED_CONTENT="[Service]
Environment=\"OLLAMA_FLASH_ATTENTION=1\"
Environment=\"OLLAMA_KV_CACHE_TYPE=${KV_CACHE_TYPE}\"
"

if [ -f "$DROPIN_FILE" ] && [ "$(cat "$DROPIN_FILE")" == "$(printf '%s' "$DESIRED_CONTENT")" ]; then
  echo "Drop-in already up to date at $DROPIN_FILE — nothing to change."
else
  mkdir -p "$DROPIN_DIR"
  printf '%s' "$DESIRED_CONTENT" > "$DROPIN_FILE"
  echo "Wrote $DROPIN_FILE"
  systemctl daemon-reload
  systemctl restart ollama
  echo "Reloaded and restarted ollama.service"
fi

sleep 1
ACTIVE_ENV="$(systemctl show ollama -p Environment --value)"

if echo "$ACTIVE_ENV" | grep -q "OLLAMA_FLASH_ATTENTION=1" && \
   echo "$ACTIVE_ENV" | grep -q "OLLAMA_KV_CACHE_TYPE=${KV_CACHE_TYPE}"; then
  echo "Verified: OLLAMA_FLASH_ATTENTION=1 and OLLAMA_KV_CACHE_TYPE=${KV_CACHE_TYPE} are live."
else
  echo "Warning: expected environment variables not found in the running service. Got:" >&2
  echo "$ACTIVE_ENV" >&2
  exit 1
fi
