# Raspberry Pi 5 — house BLE listener

AdGuard DNS runs on `` (`:5453` TCP and UDP, UI `:8088`). This Pi starts Theengs and node_exporter. `ENABLE_monitor_ADGUARD=1` is the old local DNS copy.

This host (`solar-broker` in the homelab) lives **in the house**. Mosquitto
and Home Assistant run on **``**. The Pi 4 (`solar-broker`) is the Victron
radio in another building and cannot hear house Bluetooth.

Same git repo as the Pi 4. Set **`HOST_ROLE=monitor`** in `.env` (or let deploy
auto-detect this LAN IP) and run:

```bash
sudo bash scripts/deploy.sh
```

That starts:

| Job | What it does |
|-----|----------------|
| **AdGuard Home** | Moved to `:5453` TCP and UDP (UI `:8088`). Not started here unless `ENABLE_monitor_ADGUARD=1`. |
| **adguard-exporter** | Prometheus `:9617` (needs `hosts/monitor/adguard-exporter.password`) |
| **node_exporter** | Host metrics `:9100` |
| **Theengs Gateway** | House **BLE** → MQTT on **`:1883`** (`home/TheengsGateway-monitor/BTtoMQTT`) |

It does **not** run Home Assistant, Mosquitto, or Victron. It is **not** a
router: the AXE300 stays DHCP/NAT. Wi-Fi thermostats (Ecobee, Rheem) already
talk IP to HA; add **HomeKit Device** / **EcoNet** on **``**, not here.

Optional: if a house-bank **VE.Direct USB** shunt is plugged into this Pi,
set `ENABLE_BMS_SUPERVISOR=1` in `.env` (see [docs/solar-broker_BMS_SOFTWARE.md](../../docs/solar-broker_BMS_SOFTWARE.md)).
`MQTT_HOST` stays the `` broker; do not run a second Home Assistant here.

## First-time `.env` on this Pi

```bash
cp dotenv.sample .env && chmod 600 .env
```

```text
HOST_ROLE=monitor
MQTT_HOST=solar-broker
MQTT_PORT=1883
MQTT_USER=victron
MQTT_PASSWORD=change-me
```

`MQTT_HOST` must be the **``** broker. `127.0.0.1` here is this Pi, not the broker.

If AdGuard and Theengs were started earlier from the **monitoring** repo
(`~/monitoring/hosts/monitor-dns/`), deploy copies `mqtt.env` and
`adguard-exporter.password` from that folder when they are missing here.

## MQTT file for Theengs

`hosts/monitor/mqtt.env` is gitignored. Deploy writes it from `.env`, or you can
generate it on the Pi 4 and copy it over:

```bash
# on the Pi 4
sudo bash scripts/write_monitor_mqtt_env.sh /tmp/monitor-theengs-mqtt.env
```

## Govee H5082 bridge (plugs the Pi 4 cannot reach)

The Pi 5 can run the same `govee_h5082` bridge as the Pi 4, for the plugs listed
in `/home/operator/.config/plug-bridge.env` (`plug_PLUGS=plug-4`, adapter `hci0`).
It keeps its own `/home/operator/.govee-plug-keys` (mode 600) with only those plugs'
lines, pasted by hand with `nano`. There is no SSH key to the Pi 4, so scp from here
failed. Live since 2026-09-28 (Pi 5 owns `plug-4`).

- The venv needs bleak: `~/govee-ble-venv/bin/pip install bleak paho-mqtt` (as `operator`).
  It only had paho-mqtt and dbus-fast, so the bridge failed with `No module named 'bleak'`.
- Install with `sudo bash scripts/install_plug_bridge.sh --host monitor`. It checks the venv
  first, installs the unit as `h5082-mqtt`, and replaces `h5082-rssi-monitor`.
- Then reload MQTT in HA (**Settings > Devices & services > MQTT > ⋮ > Reload**).
- Check with `journalctl -u h5082-mqtt -n 30`. This Pi's clock/timezone was an hour off,
  so `--since` can miss lines. Optional: `sudo timedatectl set-timezone America/New_York`.
- `mosquitto_sub` is not installed here: `sudo apt install -y mosquitto-clients`, then
  `set -a; source hosts/monitor/mqtt.env; set +a` (`MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`,
  `MQTT_PASSWORD`). Steps and how to
move a plug: [docs/plug_MULTI_BRIDGE.md](../../docs/plug_MULTI_BRIDGE.md).

## Prometheus

Scrape jobs stay in the **monitoring** repo (`prometheus.yml` on ``):
`node-remote` `:9100`, `adguard-remote` `:9617`.
