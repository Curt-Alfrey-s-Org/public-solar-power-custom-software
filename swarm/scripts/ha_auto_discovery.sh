#!/usr/bin/env sh
set -eu

HOST="${MQTT_HOST:-solar-broker}"
PORT="${MQTT_PORT:-1883}"
USER="${MQTT_USER:-victron}"
PASS="${MQTT_PASSWORD:-changeme}"
ROOT="${TOPIC_ROOT:-victron}"

# mirror the MQTT stream for visibility
exec mosquitto_sub -h "$HOST" -p "$PORT" -u "$USER" -P "$PASS" -v -t "${ROOT}/#"
