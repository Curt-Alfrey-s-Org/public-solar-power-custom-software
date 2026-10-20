#!/usr/bin/env bash
# Deprecated: HA 2026+ rejects YAML broker settings (broker/port/username/password).
# Use scripts/ha_enable_mqtt_integration.sh instead.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[ha_fix_mqtt_localhost] YAML MQTT is invalid on HA 2026+; running ha_enable_mqtt_integration.sh" >&2
exec bash "${ROOT}/scripts/ha_enable_mqtt_integration.sh" "$@"
