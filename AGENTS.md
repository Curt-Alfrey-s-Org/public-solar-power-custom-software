# Agent instructions — victron-ble2mqtt-integration

## Scope

- **Home / IoT edge:** Victron BLE → MQTT, Home Assistant, Mosquitto on a Raspberry Pi 4; optional **Pi 5** house edge (`HOST_ROLE=monitor`: AdGuard DNS + Theengs BLE gateway).
- **Not automatic cluster membership:** Do **not** add the Pi to the **Petals** GPU cluster or **CPU worker fleet** unless the operator explicitly asks.

## Working with alfa-ai and monitoring

- Open **alfa-ai**, **victron-ble2mqtt-integration**, and **monitoring** in one **Cursor multi-root workspace** (sibling paths on the dev host, e.g. under `/home/operator/`) so analysis and edits can span repos.
- Hub policy and hub layout: **`alfa-ai/docs/HUB_ARTIFACTS.md`** (GitHub or local clone).
- After changing deploy or Docker on the Pi, align **monitoring** scrape config via **`monitoring/hosts/solar-broker-victron/README.md`**.

## Home Assistant MQTT (HA 2026+)

Broker settings in `configuration.yaml` / `mqtt.yaml` are **invalid**. Use `scripts/ha_enable_mqtt_integration.sh` (UI config entry). Do not follow older `ha_fix_mqtt_localhost.sh` / `FORCE_HA_MQTT_YAML` YAML writers. After editing `/opt/homeassistant/.storage` while HA is running, restart the `homeassistant` container.

## Doc map

- [README.md](README.md) — first-time / YouTube install
- [docs/DEVICES.md](docs/DEVICES.md) — add / remove Victron, Sungold, HA-only devices
- [docs/monitor_HOUSE_EDGE.md](docs/monitor_HOUSE_EDGE.md) — Pi 5 AdGuard + house BLE → Pi 4 MQTT
- [hosts/README.md](hosts/README.md) — `HOST_ROLE=solar-broker` vs `monitor`
- [docs/vpn.md](docs/vpn.md) — optional away-from-home Home Assistant (no host IPs or names in git)
- [docs/sungold-inverter-1.md](docs/sungold-inverter-1.md) — Sungold USB Modbus sidecar (optional; this site not connected)
- [docs/SOLAR_POWER_BALANCE.md](docs/SOLAR_POWER_BALANCE.md) — 24 V watt in vs watt out (A3 = total load)
- [docs/solar-broker_BMS_SOFTWARE.md](docs/solar-broker_BMS_SOFTWARE.md) — Pi battery supervisor sidecar (VE.Direct observe-only v1; default off; do not replace pack BMS)
- [docs/SOLAR_ARRAY_SOLARK.md](docs/SOLAR_ARRAY_SOLARK.md) — planned 48 V island (isolated from A/B)
- [docs/ALFA_CLUSTER_INTEGRATION.md](docs/ALFA_CLUSTER_INTEGRATION.md) — hub + Cursor + Prometheus wiring
- [docs/ENGINEERING_STANDARDS_PLAN.md](docs/ENGINEERING_STANDARDS_PLAN.md) — phased plan: Compose health + supervision, deploy hygiene, CI, security
- [DEPLOY.md](DEPLOY.md) — installer behaviour and flags
