#!/usr/bin/env bash
# Writes Theengs mqtt.env for the Pi 5. Never prints MQTT_PASSWORD.
# Broker default is  (canonical Mosquitto). Override with MQTT_LAN=.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/hosts/monitor/mqtt.env}"
ENV_FILE="${VICTRON_ENV:-$ROOT/.env}"
MQTT_LAN="${MQTT_LAN:-${solar-broker_MQTT_LAN:-solar-broker}}"
exec python3 "$ROOT/scripts/write_theengs_mqtt_env.py" "$ENV_FILE" "$OUT" "$MQTT_LAN"
