#!/usr/bin/env bash
# solar-broker Theengs only when ENABLE_solar-broker_THEENGS=1 and THEENGS_ADAPTER differs from BLE_ADAPTER.
# Sourced from scripts/deploy.sh after victron_ble2mqtt is up.
# Compose profiles: https://docs.docker.com/compose/how-tos/profiles/
# BlueZ Adapter StartDiscovery: https://manpages.ubuntu.com/manpages/noble/man5/org.bluez.Adapter.5.html
# Do not pass --remove-orphans.
# shellcheck shell=bash

: "${ENABLE_solar-broker_THEENGS:=0}"

solar-broker_theengs_compose() {
  docker compose --profile solar-theengs -f "$ROOT_DIR/hosts/solar-broker/docker-compose.theengs.yml" "$@"
}

stop_solar-broker_theengs_stack() {
  local msg="$1"
  echo "[deploy] ${msg}"
  (cd "$ROOT_DIR/hosts/solar-broker" && solar-broker_theengs_compose down) || true
}

deploy_solar-broker_theengs_stack_if_enabled() {
  [[ "${HOST_ROLE:-solar-broker}" == "solar-broker" ]] || return 0
  if [[ ! -f "$ROOT_DIR/hosts/solar-broker/docker-compose.theengs.yml" ]]; then
    echo "[deploy] hosts/solar-broker/docker-compose.theengs.yml missing -- skip solar-broker Theengs." >&2
    return 0
  fi
  local reason
  if ! reason="$(python3 "$ROOT_DIR/scripts/solar-broker_ble_exclusive.py")"; then
    stop_solar-broker_theengs_stack "solar-broker Theengs not started (${reason}). Compose --profile solar-theengs down so reboot cannot restore it (restart unless-stopped: https://docs.docker.com/engine/containers/start-containers-automatically/)."
    return 0
  fi
  echo "[deploy] ${reason}"
  if [[ ! -f "$ROOT_DIR/hosts/solar-broker/mqtt.env" ]]; then
    echo "[deploy] Writing hosts/solar-broker/mqtt.env from .env (MQTT_PASSWORD not printed)."
    python3 "$ROOT_DIR/scripts/write_theengs_mqtt_env.py" "$ROOT_DIR/.env" "$ROOT_DIR/hosts/solar-broker/mqtt.env" "${MQTT_HOST:-solar-broker}"
  fi
  echo "[deploy] Starting solar-broker Theengs on THEENGS_ADAPTER=${THEENGS_ADAPTER} (profile solar-theengs)."
  (cd "$ROOT_DIR/hosts/solar-broker" && solar-broker_theengs_compose up -d)
}
