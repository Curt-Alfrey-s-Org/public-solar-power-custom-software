#!/usr/bin/env bash
# Pi 5 house-edge stack: Theengs BLE→MQTT, node_exporter.
# AdGuard DNS runs on . ENABLE_monitor_ADGUARD=1 starts the old local copy.
# Invoked by scripts/deploy.sh when HOST_ROLE=monitor. Safe to re-run.
set -Eeuo pipefail
IFS=$'\n\t'

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"
monitor="$ROOT_DIR/hosts/monitor"
LEGACY_MONITORING="${monitor_LEGACY_MONITORING:-/home/operator/monitoring/hosts/monitor-dns}"
solar-broker_MQTT_LAN="${solar-broker_MQTT_LAN:-solar-broker}"

need_cmd() { command -v "$1" >/dev/null 2>&1; }

apt_install() {
  local pkgs=("$@")
  if ! need_cmd apt-get; then
    echo "[deploy-monitor] apt-get not available; install ${pkgs[*]} manually." >&2
    return 1
  fi
  sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${pkgs[@]}"
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[deploy-monitor] run as root: sudo bash scripts/deploy.sh  (HOST_ROLE=monitor)" >&2
  exit 1
fi

if [[ -f ./.env ]]; then set -a; . ./.env; set +a; fi

echo "[deploy-monitor] HOST_ROLE=monitor — Theengs + node_exporter (AdGuard is on ; no HA / Victron / Mosquitto here)"

if ! need_cmd curl; then apt_install curl ca-certificates gnupg || true; fi
if ! need_cmd docker; then
  echo "[deploy-monitor] Installing Docker..."
  apt_install docker.io || true
  sudo systemctl enable --now docker || true
fi
if ! docker compose version >/dev/null 2>&1; then
  apt_install docker-compose-plugin || apt_install docker-compose || true
fi
if ! need_cmd bluetoothctl; then
  apt_install bluez rfkill dbus || true
fi
sudo systemctl enable --now bluetooth 2>/dev/null || true
sudo rfkill unblock bluetooth || true

mkdir -p /opt/adguard/conf /opt/adguard/work "$monitor"

# Adopt secrets from the earlier monitoring-repo layout, if present.
if [[ -d "$LEGACY_MONITORING" ]]; then
  if [[ ! -s "$monitor/adguard-exporter.password" && -s "$LEGACY_MONITORING/adguard-exporter.password" ]]; then
    echo "[deploy-monitor] Copying AdGuard exporter password from $LEGACY_MONITORING"
    cp -a "$LEGACY_MONITORING/adguard-exporter.password" "$monitor/adguard-exporter.password"
  fi
  if [[ ! -f "$monitor/mqtt.env" && -f "$LEGACY_MONITORING/mqtt.env" ]]; then
    echo "[deploy-monitor] Copying Theengs mqtt.env from $LEGACY_MONITORING"
    cp -a "$LEGACY_MONITORING/mqtt.env" "$monitor/mqtt.env"
  fi
fi

if [[ ! -f "$monitor/mqtt.env" ]]; then
  if [[ ! -f "$ROOT_DIR/.env" ]]; then
    echo "[deploy-monitor] missing .env and hosts/monitor/mqtt.env — copy dotenv.sample and set MQTT_* to the Pi 4 broker." >&2
    exit 1
  fi
  python3 "$ROOT_DIR/scripts/write_theengs_mqtt_env.py" "$ROOT_DIR/.env" "$monitor/mqtt.env" "$solar-broker_MQTT_LAN"
fi
chmod 600 "$monitor/mqtt.env" 2>/dev/null || true

mqtt_host="$(awk -F= '/^MQTT_HOST=/{print $2; exit}' "$monitor/mqtt.env" | tr -d '\r')"
local_ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
if [[ -z "$mqtt_host" || "$mqtt_host" == "localhost" || "$mqtt_host" == "127.0.0.1" ]]; then
  echo "[deploy-monitor] mqtt.env MQTT_HOST must be the Pi 4 LAN IP ($solar-broker_MQTT_LAN), not loopback." >&2
  exit 1
fi
if [[ -n "$local_ip" && "$mqtt_host" == "$local_ip" ]]; then
  echo "[deploy-monitor] mqtt.env MQTT_HOST=$mqtt_host is this Pi — Theengs must publish to the Pi 4 broker." >&2
  exit 1
fi

if [[ -s "$monitor/adguard-exporter.password" ]]; then
  if [[ "$(tail -c1 "$monitor/adguard-exporter.password" | wc -l)" -ne 0 ]]; then
    printf '%s' "$(cat "$monitor/adguard-exporter.password")" > "$monitor/adguard-exporter.password.tmp"
    mv "$monitor/adguard-exporter.password.tmp" "$monitor/adguard-exporter.password"
  fi
  chmod 600 "$monitor/adguard-exporter.password"
fi

echo "[deploy-monitor] starting node_exporter"
docker compose -f "$monitor/docker-compose.node-exporter.yml" up -d

: "${ENABLE_monitor_ADGUARD:=0}"
if [[ "${ENABLE_monitor_ADGUARD}" == "1" ]]; then
  echo "[deploy-monitor] starting AdGuard Home (ENABLE_monitor_ADGUARD=1)"
  docker compose -f "$monitor/docker-compose.adguard.yml" up -d adguardhome
else
  echo "[deploy-monitor] AdGuard stays on  (ENABLE_monitor_ADGUARD=0). Stopping a local copy if one is here."
  docker compose -f "$monitor/docker-compose.adguard.yml" stop adguardhome adguard-exporter >/dev/null 2>&1 || true
fi
if [[ "${ENABLE_monitor_ADGUARD}" == "1" && -s "$monitor/adguard-exporter.password" ]]; then
  echo "[deploy-monitor] starting adguard-exporter"
  docker compose --profile exporter -f "$monitor/docker-compose.adguard.yml" up -d
elif [[ "${ENABLE_monitor_ADGUARD}" == "1" ]]; then
  lan="${local_ip:-<monitor-ip>}"
  echo "[deploy-monitor] no hosts/monitor/adguard-exporter.password — exporter skipped."
  echo "[deploy-monitor] If the wizard is still open: http://${lan}:3000  (admin port 8080, DNS 53, user operator)"
  echo "[deploy-monitor] Then: printf '%s' 'PASSWORD' | sudo tee $monitor/adguard-exporter.password >/dev/null"
  echo "[deploy-monitor]         sudo chmod 600 $monitor/adguard-exporter.password && sudo bash scripts/deploy.sh"
fi

echo "[deploy-monitor] starting Theengs BLE gateway → $mqtt_host:1883"
docker compose -f "$monitor/docker-compose.theengs.yml" up -d
sleep 2
logpath="$(docker inspect --format='{{.LogPath}}' monitor-theengs-gateway 2>/dev/null || true)"
if [[ -n "$logpath" && -f "$logpath" ]]; then
  : > "$logpath" || true
fi

echo ""
echo "[deploy-monitor] containers:"
docker ps --filter name=monitor- --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
echo ""
echo "[deploy-monitor] node_exporter :9100   (AdGuard DNS is :5453, UI :8088)"
echo "[deploy-monitor] Theengs topic home/TheengsGateway-monitor/BTtoMQTT  (decoded BLE only)"
echo "[deploy-monitor] Wi-Fi HVAC (Ecobee/Rheem) is not forwarded here — add HomeKit Device / EcoNet on Pi 4 HA."

: "${ENABLE_AUTOHEAL:=1}"
if [[ "${ENABLE_AUTOHEAL:-1}" == "1" ]]; then
  echo "[deploy-monitor] starting autoheal (restarts unhealthy containers labeled autoheal=true) ..."
  docker compose -f "$ROOT_DIR/docker-compose.autoheal.yml" up -d
fi

# Optional VE.Direct USB shunt on house Pi (same broker on ; does not run HA here).
# shellcheck source=scripts/start_bms_supervisor_if_enabled.sh
source "$ROOT_DIR/scripts/start_bms_supervisor_if_enabled.sh"
deploy_bms_supervisor_stack_if_enabled

echo "[deploy-monitor] Done."
