# Node-RED solar diagram (``)

HA stays authoritative for sensors. Node-RED reads HA and provides the **editable** diagram canvas.

## One-time setup

1. `cd /home/operator/victron-ble2mqtt-integration`
2. `bash scripts/setup-nodered-solar-env.sh` (HA token from alfa-ai secrets + NR admin hash), or copy `nodered.env.example` manually.
3. `bash scripts/deploy-nodered-solar.sh  # systemd user nodered-solar.service on :1880`
4. Open **http://solar-broker/** (vpn: same port on the `` name).

ufw (if enabled): allow LAN `1880/tcp` from `solar-broker/24` only.


## Panel strings (diagram tab, operator 2026-10-08 evening)

Physical layout tonight ([SOLAR_POWER_BALANCE.md](SOLAR_POWER_BALANCE.md) install in progress). T2 has no MPPT. The 100/50 is on KU.

| String | Bus | Charger | Panels |
|--------|-----|---------|--------|
| 2s5p | KU | SmartSolar MPPT **100/50** (`sensor.victron-mppt-1_*`) | the only charger in use; 2s5p; 4 panels still on the way |
| (unused) | -- | three BlueSolar **75/15** | present, not charging. One still has `sensor.victron-mppt-1_*` |
| (none) | T2 | no charger | T2 PV in the computed page is 0 W |

The diagram still has eight legacy panel boxes. Row 1 (panels 1+2) is the KU 100/50, not a drawing of all ten panels. The live poll reads `sensor.victron-mppt-1_solar_power`. Computed meters set `battery-1-100_50_w` from that sensor, `battery-2-pv_w` = 0, and the Prometheus key `battery-2-mppt_w` = 0. That key does not publish a 75/15. **Retired:** `-> KU PWM`, and 8-panel equal-share est in `scripts/nodered_solar_computed.js`.

Deploy after `git pull` on ``: `bash scripts/deploy-nodered-solar.sh`. That script writes `nodered-data/flows.json` from `flows/solar_plant_diagram.json` and `flows/solar_computed_meters.json`, then restarts the user service. Node-RED loads `flowFile` on start ([runtime configuration](https://nodered.org/docs/user-guide/runtime/configuration)). The admin API can import flows ([POST /flows](https://nodered.org/docs/api/admin/methods/)); this repo uses the script, not a hand edit of the running runtime.

After editing positions in the editor, export to `flows/solar_plant_diagram.json`.
## Edit the diagram

1. Open the **Solar plant diagram** tab.
2. Drag nodes and wires to match the physical layout ([SOLAR_POWER_BALANCE.md](SOLAR_POWER_BALANCE.md)).
3. Add a clamp: create the HA template sensor first (`config/packages/solar_plant.yaml`), then duplicate a poll node triple (function / http / status) and wire it.
4. **Deploy** in Node-RED, then export: **Menu > Export > current flow** into `flows/solar_plant_diagram.json` and commit.

Green node status shows live HA state. Red `no HA token` means fix `nodered.env` and restart the container.

## Sync with HA package changes

After `install_solar_plant_ha.sh`, reload Node-RED or wait for the 5s poll -- no NR change unless you add new entities to the canvas.


## Solar computed meters (derived tiles)

Tab **Solar computed meters** polls HA `/api/states` every 5s and runs `scripts/nodered_solar_computed.js`.

Open **http://solar-broker/solar/computed** for HTML tiles (site totals, jumper, Sungold; legacy 8-panel / PWM est retired until NR script update).

**http://solar-broker/solar/metrics** is the same cached object as Prometheus text ([exposition format](https://prometheus.io/docs/instrumenting/exposition_formats/)). It does not recalculate. Grafana on `` scrapes it. The [http in](https://nodered.org/docs/user-guide/nodes) / [http response](https://nodered.org/docs/user-guide/nodes) nodes are the official Node-RED HTTP endpoints.

Site solar in HA stays **device-only**; do not re-add those template sensors to `solar_plant.yaml`.

Policy: [SOLAR_HA_NODERED_SPLIT.md](SOLAR_HA_NODERED_SPLIT.md).
