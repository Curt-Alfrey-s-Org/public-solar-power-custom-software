# Pi 5 house edge — DNS + BLE into `` Home Assistant

Mosquitto and Home Assistant run on **`` (`solar-broker`)**. The **Pi 4**
(`HOST_ROLE=solar-broker`) is the Victron BLE / Sungold USB radio in another building.
Planned move (2026-10-07, parts on the way, not installed): Pi 4 to the basement, Sungold USB to the house Pi 5. [SOLAR_POWER_BALANCE.md](SOLAR_POWER_BALANCE.md#planned-install-operator-2026-10-07).
The **Pi 5** (`HOST_ROLE=monitor`) is the house BLE listener. It does not
run a second Home Assistant, and it does not run AdGuard. DNS is AdGuard Home
on **`:5453`** TCP and UDP (setup UI `:8088`). `ENABLE_monitor_ADGUARD` defaults to 0.

```
House BLE  ──► Theengs on Pi 5 ──► Mosquitto on  :1883 ──► HA Container
Solar-site BLE (optional, 2nd HCI) ──► Theengs on Pi 4 ──► same broker
LAN DNS    ──► AdGuard on  (:5453 TCP and UDP / UI :8088)
Victron    ──► victron_ble2mqtt on Pi 4 ──► same broker
Optional house VE.Direct USB ──► bms_supervisor on Pi 5 ──► same broker (ENABLE_BMS_SUPERVISOR=1)
```

**Autoheal on monitor:** `scripts/deploy_monitor.sh` starts repo-root `docker-compose.autoheal.yml` when `ENABLE_AUTOHEAL=1` (default). AdGuard's healthcheck now lives with the `` compose. Official `theengs/gateway` has **no** image HEALTHCHECK ([gateway-docker Dockerfile](https://github.com/theengs/gateway-docker/blob/main/Dockerfile)); do not invent a Docker probe for monitor Theengs. MQTT LWT stays broker availability ([Theengs use](https://gateway.theengs.io/use/use.html)). A retained LWT `online` can linger after an MQTT [keep-alive timeout](https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html) while logs show `Failed to send message` / `Disconnected from MQTT broker`. Recreate **only** `theengs-gateway` with [`docker compose up --force-recreate`](https://docs.docker.com/reference/cli/docker/compose/up/) (no `--remove-orphans`). `restart: unless-stopped` covers process **exit** only ([restart policy](https://docs.docker.com/engine/containers/start-containers-automatically/)). Do not pass `--remove-orphans` (would drop AdGuard/Theengs from a single-file compose project).

solar-broker Theengs (`hosts/solar-broker/docker-compose.theengs.yml`) is **off by default**. Victron
owns onboard `hci0`. BlueZ allows one `StartDiscovery` session per client per adapter
([org.bluez.Adapter](https://manpages.ubuntu.com/manpages/noble/man5/org.bluez.Adapter.5.html));
Theengs docs are silent on sharing that adapter. `scripts/deploy.sh` on solar-broker starts
Victron, then `scripts/start_solar-broker_theengs_if_enabled.sh`: unless `ENABLE_solar-broker_THEENGS=1`
**and** `THEENGS_ADAPTER` differs from `BLE_ADAPTER`, it runs
[`docker compose --profile solar-theengs down`](https://docs.docker.com/compose/how-tos/profiles/)
so a leftover `unless-stopped` container cannot return on reboot.
**This site (2026-09-14):** the H5075 at `AA:BB:CC:DD:EE:FF` has dead cells — HA
tiles stay Unknown until the cells are replaced
([MQTT sensor](https://www.home-assistant.io/integrations/sensor.mqtt/)).
Do not start solar-broker Theengs on `hci0` to refresh those tiles. Do not add a Theengs
HEALTHCHECK. Do not pass `--remove-orphans`. Do not `up -d theengs-gateway`
(Compose auto-enables that profile). House Theengs on monitor is unchanged.

Installer: `sudo bash scripts/deploy.sh` on each Pi (role from `.env` or LAN IP).
Compose files: [hosts/monitor/](../hosts/monitor/). Operator notes: [hosts/monitor/README.md](../hosts/monitor/README.md).

Prometheus scrape config for `:9100` / `:9617` stays in the **monitoring** repo
on `solar-broker`.
