# Devices — add, skip, or remove

This is the **only page** you need to turn gear on or off.

After any change, on **that** Pi (`HOST_ROLE=solar-broker` or `monitor`):

```bash
cd ~/victron-ble2mqtt-integration
sudo bash scripts/deploy.sh
```

Secrets stay in `.env` and `victron-secrets.env` (never commit those files).

---

## Catalog

| Device | How it connects | Default | Turn **on** | Turn **off** / remove |
|--------|-----------------|---------|-------------|------------------------|
| **Victron** SmartShunt / MPPT | Bluetooth (BLE) | On, if you set keys | Add MAC + `ADVKEY_*` | Delete that device block and its `ADVKEY_*` line |
| **solar-broker host** (CPU, temp, Wi‑Fi) | Built into the Victron container | On with Victron | Nothing extra | Stop `victron_ble2mqtt` (you also lose Victron) |
| **Sungold SPH302480A** | USB Modbus (read-only) | **Off** | `ENABLE_SUNGOLD=1` + USB | `ENABLE_SUNGOLD=0` or unplug USB. **This site: emergency dolly cart** (2x 24 V 100 Ah), not T2/KU (2026-09-11). |
| **Pi battery supervisor** | VE.Direct USB (read-only Text) | **Off** | `ENABLE_BMS_SUPERVISOR=1` + USB | `ENABLE_BMS_SUPERVISOR=0` or unplug USB. Bench/spare pack first; not T2/KU/well v1. See [solar-broker_BMS_SOFTWARE.md](solar-broker_BMS_SOFTWARE.md). |
| **Home Assistant** | Browser `:8123` on **``** | On (`` only) | `docker-compose.homeassistant.yml` on `` | Do **not** enable HA on solar-broker/monitor. Do **not** run `scripts/deploy.sh` on ``. |
| **House BLE sensors** (Govee, Xiaomi, …) | BLE on **Pi 5** → MQTT on **``** | Off until Pi 5 deploy | `HOST_ROLE=monitor` on the house Pi | `docker compose … down` on Pi 5 |
| **Solar-site Govee** (e.g. H5075 `AA:BB:CC:DD:EE:FF`) | BLE on **Pi 4** Theengs → same broker | **Off.** Needs a **second** HCI (`ENABLE_solar-broker_THEENGS=1` + `THEENGS_ADAPTER` ≠ `BLE_ADAPTER`). **Cells dead 2026-09-14** | USB dongle + env + `sudo bash scripts/deploy.sh` | leave `ENABLE_solar-broker_THEENGS=0` (deploy runs Compose `--profile solar-theengs down`) |
| **Ecobee / Rheem / other Wi‑Fi HVAC** | HomeKit Device / EcoNet (LAN), not BLE | Not this repo | HA → Settings → Devices & services | Remove the integration in HA |
| **Refoss / Govee / other HA gear** | Home Assistant integrations | Not this repo | HA → Settings → Devices & services | Remove the integration in HA |
| **Away-from-home view** | vpn VPN (optional) | Off (not in deploy) | Install vpn on **``** + phone ([vpn.md](vpn.md)) | Uninstall / log out of vpn |

Running system in this catalog. Planned install (2026-10-07, parts on the way, not installed): [SOLAR_POWER_BALANCE.md](SOLAR_POWER_BALANCE.md#planned-install-operator-2026-10-07).

Victron and Sungold both publish into the **same** Mosquitto broker. They do not replace each other.

The house Pi 5 (`HOST_ROLE=monitor`) publishes decoded BLE into that same broker. Wi-Fi HVAC does not use Theengs.

```
Victron BLE (Pi 4 radio)               ──► victron_ble2mqtt ──┐
Sungold USB                            ──► sungold_modbus_ro ─┼──► Mosquitto :1883 ──► Home Assistant
solar-broker metrics                            ──► victron_ble2mqtt ──┤
House BLE (Pi 5 radio)                 ──► Theengs Gateway ───┤
Solar-site Govee (Pi 4, optional 2nd HCI) ──► Theengs Gateway ─┤
BMS supervisor (optional USB)          ──► bms_supervisor ──────┘
```

---

## Victron (Bluetooth)

You need **two** things per device:

1. **MAC address** (Bluetooth ID), e.g. `AA:BB:CC:DD:EE:FF`
2. **Advertisement key** (exactly **32 hex characters**) from VictronConnect
   Instant Readout Details ([keshavdv/victron-ble](https://github.com/keshavdv/victron-ble)).
   Do **not** truncate a longer paste. A 33-character value decrypts as garbage
   (impossible volts/amps/watts). If HA shows Battery 1 at hundreds of volts
   while the MPPT is ~26 V, re-copy the key from the app.

Home Assistant shows numeric sensors at **tenths** (`display_precision: 1` in
the entity registry — same as the entity **Display precision** UI). MQTT
Victron discovery still sets
[`suggested_display_precision: 1`](https://www.home-assistant.io/integrations/sensor.mqtt/#suggested_display_precision)
for A/V/W; the registry override covers Refoss, Sungold, templates, energy, and
percent. Apply on `` with HA stopped: `bash scripts/apply_ha_display_precision.sh`
([SOLAR_HA_DASHBOARD.md](SOLAR_HA_DASHBOARD.md)). Change individuals later in
the entity UI.

MQTT discovery `name` strings follow VictronConnect readout wording
([SmartShunt operation](https://www.victronenergy.com/media/pg/SmartShunt/en/operation.html),
[BlueSolar MPPT 75/15 monitoring](https://www.victronenergy.com/media/pg/Manual_BlueSolar_MPPT_75-10_up_to_100-20/en/monitoring.html)).
`uid` values stay fixed so Home Assistant `entity_id`s do not rename.

**BlueSolar Instant Readout is not the VictronConnect status screen.** Ads are a
short AES payload ([keshavdv/victron-ble](https://github.com/keshavdv/victron-ble/blob/v0.9.2/victron_ble/devices/solar_charger.py)
`SolarCharger.parse_decrypted`). VictronConnect solar **voltage** and solar
**current** appear only while the app is GATT-connected
([manual 7.3.1](https://www.victronenergy.com/media/pg/Manual_BlueSolar_MPPT_75-10_up_to_100-20/en/monitoring.html)).
Those fields are **not** in the advertisement, so MQTT/HA cannot invent them.
Panel voltage on a cable is VE.Direct TEXT `VPV` (mV)
([protocol 3.34](https://www.victronenergy.com/upload/documents/VE.Direct-Protocol-3.34.pdf)).
This site's BLE dongle sits on that VE.Direct port; do **not** unplug it for USB
`VPV` or Instant Readout stops.
### Pending Instant Readout keys (operator 2026-10-02)

Add only from VictronConnect **Product info** -> **Instant Readout details** ([official steps](https://www.victronenergy.com/media/pg/VictronConnect_app/en/stored-trends---instant-readout.html)). Do **not** commit placeholder MACs or keys.

| Charger | Bus | Status |
|---------|-----|--------|
| SmartSolar MPPT **100/50** | KU (HQ2239JTRKU) | Live on KU (2s5p now; 4 panels still on the way). MAC `AA:BB:CC:DD:EE:FF`. HA `sensor.victron-mppt-1_*` on Site solar KU. |
| BlueSolar MPPT **75/15** (second) | KU (HQ2239JTRKU) | Not in MQTT yet |
| Paired BlueSolar **75/15** rev3 | KU | Live as `Solar-controller` / `sensor.victron-mppt-1_*` |

Planned (not installed): all three 75/15 chargers unused, and the 100/50 array moves to 8 suitcase panels 2s4p. Same section: [SOLAR_POWER_BALANCE.md](SOLAR_POWER_BALANCE.md#planned-install-operator-2026-10-07).

Install in progress (2026-10-08 evening): the 100/50 row's T2 bus is no longer the current step. That charger is on KU (2s5p now; 4 panels still on the way). The three 75/15 chargers are not removed. [Install in progress](SOLAR_POWER_BALANCE.md#install-in-progress-operator-2026-10-08-evening).

| Instant Readout field | HA MQTT name | Solar dashboard (this site) |
|-----------------------|--------------|-----------------------------|
| `battery_charging_current` | Battery current | yes |
| `battery_voltage` | Battery voltage | yes |
| `charge_state` | Battery state | yes |
| `charger_error` | (parsed, not a Solar tile) | no extra tile |
| `external_device_load` | Load output | yes |
| `solar_power` | Solar power | yes |
| `yield_today` | Solar yield | yes |
| (derived V x I) | Battery power | yes |
| (derived V x load A) | Load output power | yes |
| RSSI | RSSI | yes |
| solar voltage / solar current | **not in BLE ads** | not an entity |


SmartSolar MPPT **100/50** tiles sit under the Site solar **KU 24 V** heading. Its tiles are every Instant Readout entity: battery current, voltage, state, battery power, solar power, solar yield, and RSSI. Panel voltage and current are still not in the advertisement.

The sidecar must import `override/victron_ble2mqtt/mqtt.py` (bind mount).
Compose sets `PYTHONSAFEPATH=1` so `python -m` does not prepend image `WORKDIR /app`
and shadow that override ([PYTHONSAFEPATH](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONSAFEPATH)).
After editing `mqtt.py`, recreate only `victron_ble2mqtt` (not `deploy.sh`):

```bash
sudo docker compose -f docker-compose.victron.yml up -d --force-recreate victron_ble2mqtt
```

Do not pass `--remove-orphans` (Sungold is a separate compose project).

### Find the MAC

Close VictronConnect on your phone, then on the Pi:

```bash
sudo bluetoothctl scan on
```

Wait 20 seconds. Note the address next to your SmartShunt / MPPT. `Ctrl+C` to stop.

### Add a device

1. Edit `override/victron_ble2mqtt/user_settings_data.py`.
2. Add a block to the `devices` list (this repo’s MACs are **examples** — use yours):

```python
    {
        "mac": "AA:BB:CC:DD:EE:FF",
        "type": "SmartShunt",   # or "BlueSolar" for an MPPT
        "name": "Battery 3",
    },
```

3. Edit `victron-secrets.env` and add a key. The name becomes `ADVKEY_` + the name in `SCREAMING_SNAKE`:

```text
ADVKEY_BATTERY_3=0123456789abcdef0123456789abcdef
```

`Battery 1` → `ADVKEY_BATTERY_1`  
`Solar-controller` → `ADVKEY_victron-mppt-1`

4. Re-run `sudo bash scripts/deploy.sh`.

### Remove a device

1. Delete that block from `user_settings_data.py`.
2. Delete its `ADVKEY_*` line from `victron-secrets.env`.
3. Re-run deploy.

You do not need to wipe Home Assistant. Old MQTT entities may linger until you remove them under **Settings → Devices & services → MQTT**.

### Victron still missing in HA?

Home Assistant MQTT sensors stay **Unknown** until a **state** payload arrives.
Discovery config can be retained while state is not
([MQTT sensor](https://www.home-assistant.io/integrations/sensor.mqtt/)).

- Close the VictronConnect app (it can starve Instant Readout ads).
- Confirm `sudo bluetoothctl show` says **Powered: yes**.
- Weak built-in radio: plug a USB Bluetooth dongle, set `BLE_ADAPTER=hci1` in `.env`, recreate `victron_ble2mqtt`.
- solar-broker onboard Bluetooth is **exclusive** to `victron_ble2mqtt`. BlueZ allows **one** `StartDiscovery` session per client per adapter; `StopDiscovery` releases only that client ([org.bluez.Adapter](https://manpages.ubuntu.com/manpages/noble/man5/org.bluez.Adapter.5.html)). Official Theengs docs document [`--adapter`](https://gateway.theengs.io/use/use.html) and [`--blacklist` / `BLACKLIST`](https://gateway.theengs.io/use/use.html) but are **silent** on sharing one adapter with another scanner — do not run solar-broker Theengs on the same HCI as Victron. Default `ENABLE_solar-broker_THEENGS=0`; `scripts/deploy.sh` runs Compose [`--profile solar-theengs down`](https://docs.docker.com/compose/how-tos/profiles/) so `restart: unless-stopped` cannot bring Theengs back on reboot ([restart policy](https://docs.docker.com/engine/containers/start-containers-automatically/)). Opt-in only with a USB adapter: `ENABLE_solar-broker_THEENGS=1` and `THEENGS_ADAPTER` different from `BLE_ADAPTER` (usually `hci1` vs `hci0`). Do not `docker compose up -d theengs-gateway` (Compose auto-enables that service's profile). Do not add Victron `ADVKEY_*` or bindkeys to Theengs. If Bleak logs `BLE scanner start timed out`, the process retries every 15s (`BLE_SCANNER_START_RETRY_SEC`); that is recovery for a leftover BlueZ session, not permission to share HCI. The solar-broker runs this opt-in (since 2026-10-02): Theengs on `hci1` is the only gateway that hears the solar-site Govee thermometer `hygrometer-1`, and its `BLACKLIST` in `hosts/solar-broker/docker-compose.theengs.yml` lists all four Victron units (`AA:BB:CC:DD:EE:FF`, `AA:BB:CC:DD:EE:FF`, `AA:BB:CC:DD:EE:FF`, `AA:BB:CC:DD:EE:FF`). `hci1` is also the H5082 plug bridge's adapter; BlueZ shares one discovery procedure between all sessions on an adapter and merges their filters, so Theengs adds no second scan.
- `victron-ble` 0.9.2 drops identical Instant Readout payloads forever (`_seen_data` in [scanner.py](https://github.com/keshavdv/victron-ble/blob/v0.9.2/victron_ble/scanner.py)). The sidecar discards that de-dupe on each publish throttle so a stable bus still refreshes HA after a broker/HA restart.
- Pi host metrics (`iwconfig`, CPU, eth0/wlan0/vpn) run in `asyncio.to_thread` on a **60s** default (`SYSTEM_POLL_THROTTLE_SEC`), not on every BLE packet ([`asyncio.to_thread`](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread)). Container `healthy` requires **dual BLE liveness** via Compose [healthcheck](https://docs.docker.com/reference/compose-file/services/#healthcheck) (`test` exec-form `CMD`, `start_period` 180s for Bleak 30s+30s plus first Instant Readout): `BLE_SCANNER_OK_FILE` exists after `BLE scanner started`, `BLE_PUBLISH_HEARTBEAT_FILE` touched after each successful Instant Readout MQTT publish (default max age `BLE_PUBLISH_MAX_AGE_SEC=600`), plus the system-info `HEARTBEAT_FILE` (event loop + MQTT client still running). `restart: unless-stopped` does not restart an `unhealthy` but still-running process ([restart policy](https://docs.docker.com/engine/containers/start-containers-automatically/)); autoheal does, and only after Engine marks `unhealthy` ([HEALTHCHECK](https://docs.docker.com/reference/dockerfile/#healthcheck)). autoheal's `AUTOHEAL_CONTAINER_LABEL` is the **label name** `autoheal` (filter `autoheal=true`); do not set the env to `autoheal=true` ([autoheal entrypoint](https://github.com/willfarrell/docker-autoheal/blob/master/docker-entrypoint)).
- After editing `override/victron_ble2mqtt/__main__.py` or `mqtt.py`, recreate **only** `victron_ble2mqtt` (no `--remove-orphans`). Confirm logs contain `BLE scanner started` and `Throttled publish` (or state topics updating).

---

## Sungold inverter

**Read-only.** This sidecar never writes settings to the inverter. Change settings on the front panel.

Full hardware notes: [sungold-inverter-1.md](sungold-inverter-1.md).

### Turn on

1. USB-B cable from the inverter to the Pi.
2. Confirm the stick is seen:

```bash
lsusb | grep -i '1a86\|ch340'
```

3. In `.env`:

```text
ENABLE_SUNGOLD=1
SUNGOLD_SERIAL_DEVICE=/dev/sungold
```

4. `sudo bash scripts/deploy.sh`  
   Deploy installs the udev rule that creates `/dev/sungold`.
5. Check: `bash scripts/sungold_smoke.sh` and `docker logs -f sungold_modbus_ro`.
6. On ``: wait until MQTT discovery is in the entity registry, **then** stop HA and run `sudo python3 scripts/ha_label_sungold_solar.py` — HA label **Sungold** and a **Sungold** heading whose tiles use live `unique_id`s (`sungold-inverter-1-pv1-voltage`, not `sensor.sungold-inverter-1_pv_voltage`).

### Turn off

In `.env`:

```text
ENABLE_SUNGOLD=0
```

Then `sudo bash scripts/deploy.sh`. Victron and Home Assistant keep running.

---

## Solar-site BLE (Pi 4 radio → this Mosquitto)

Govee thermometers at the Victron gear (e.g. H5075 `AA:BB:CC:DD:EE:FF`) use **Pi 4
Theengs** (`hosts/solar-broker/docker-compose.theengs.yml`), not the house Pi 5 radio. That
gateway is **off by default** so Victron Instant Readout keeps the onboard adapter
([org.bluez.Adapter](https://manpages.ubuntu.com/manpages/noble/man5/org.bluez.Adapter.5.html)).
This site (2026-09-14): H5075 cells are dead — HA tiles stay Unknown until
replaced ([MQTT sensor](https://www.home-assistant.io/integrations/sensor.mqtt/)).
Do not start solar-broker Theengs on `hci0` to "fix" those tiles.

To run solar-site Theengs you need a **second** Bluetooth adapter, then in `.env`:

```text
ENABLE_solar-broker_THEENGS=1
BLE_ADAPTER=hci0
THEENGS_ADAPTER=hci1
```

Then `sudo bash scripts/deploy.sh` on Pi 4 (guard in `scripts/solar-broker_ble_exclusive.py`).
Do not `docker compose up` Theengs by service name. Topic: `home/TheengsGateway-solar-broker/BTtoMQTT`
(LWT `home/TheengsGateway-solar-broker/LWT`). H5072/H5075 need **active** scan
([Govee BLE](https://www.home-assistant.io/integrations/govee_ble/)). Do not add a Docker
HEALTHCHECK (official `theengs/gateway` has none —
[gateway-docker Dockerfile](https://github.com/theengs/gateway-docker/blob/main/Dockerfile)).
If Theengs logs `org.bluez.Error.InProgress` on Victron's adapter, set
`ENABLE_solar-broker_THEENGS=0` and re-run deploy. Retained **`online`** on `LWT_TOPIC`
([`-Lt` / `LWT_TOPIC`](https://gateway.theengs.io/use/use.html)) is MQTT availability, not proof of
`BTtoMQTT` publishes. Do **not** add `expire_after` on retained MQTT sensor state in HA.

---

## House BLE (Pi 5 radio → this Mosquitto)

The Pi 4 cannot hear Bluetooth in the house. Clone **this same repo** on the Pi 5,
set `HOST_ROLE=monitor` (or use LAN IP `solar-broker`), and run `sudo bash scripts/deploy.sh`.

That starts **Theengs Gateway**, which publishes decoded sensors to **this** broker.
Do **not** run a second Home Assistant on the Pi 5. Do **not** put Victron `ADVKEY_*`
keys on Theengs.

Full notes: [monitor_HOUSE_EDGE.md](monitor_HOUSE_EDGE.md), [hosts/monitor/README.md](../hosts/monitor/README.md).
Topic: `home/TheengsGateway-monitor/BTtoMQTT`. Retained LWT `online` can stay set after an MQTT
[keep-alive timeout](https://docs.oasis-open.org/mqtt/mqtt/v5.0/os/mqtt-v5.0-os.html)
while logs show `Failed to send message`. Recreate **only** that gateway (no `--remove-orphans`):

```bash
cd ~/victron-ble2mqtt-integration/hosts/monitor
sudo docker compose -f docker-compose.theengs.yml up -d --force-recreate theengs-gateway
```

([`docker compose up --force-recreate`](https://docs.docker.com/reference/cli/docker/compose/up/)).
Confirm `BTtoMQTT` payloads, not only LWT.

## Wi‑Fi HVAC (Ecobee, Rheem)

These are **not** Victron-style BLE. Add them on the **existing** Home Assistant on **``** (`:8123`). Do not add a second HA on the Pi 4 or Pi 5.

### Ecobee (local)

Use **HomeKit Device**, not **HomeKit Bridge**, and not **ecobee** (that one is cloud).

1. If the thermostat is in **Apple Home**, remove it there first. HomeKit allows only one controller.
2. On the thermostat: **Menu → Settings → HomeKit → Enable pairing**. The 8-digit code appears on screen (often `XXXX-XXXX`; in HA type `XXX-XX-XXX` or the 8 digits).
3. In HA: **Settings → Devices & services**. If it is not already discovered, **Add integration → HomeKit Device**.
4. Enter the pairing code. You should get a `climate.*` entity plus any Eco sensors.

`configuration.yaml` on **``** (`/opt/homeassistant`) must include `zeroconf:` (or `default_config:`) so mDNS discovery works ([HomeKit Device](https://www.home-assistant.io/integrations/homekit_controller/)). HA and the thermostat must be on the same LAN subnet.

Cloud fallback (internet, more features): **Add integration → ecobee** with the ecobee.com email/password. Leave **API key** blank. **HA 2026.6+** is required for that login (MFA / Auth0). 2026.4.x crashes with “Unknown error occurred” (`IndexError` in python-ecobee-api 0.3.2). This stack pins **2026.7.3**. SMS/push MFA is unsupported; use an authenticator app.

### Rheem heat-pump water heater (cloud)

1. Confirm the heater is in the **EcoNet** app and you can log in there.
2. **Settings → Devices & services → Add integration → Rheem EcoNet Products**.
3. Use the **same** EcoNet email and password as the app (password usually needs a special character).

You get a `water_heater.*` entity. EcoNet does **not** report tank temperature. It is cloud (ClearBlade), not BLE.

If add/login fails with “Unknown error” / “invalid login” **after** HA is on **2026.7+**, the container no longer trusts Rheem’s old DigiCert G1 chain. Run `sudo bash scripts/ha_econet_trust_g1.sh`, set `HA_SSL_CERT_FILE=/config/ssl/ca-bundle+g1.pem` in `.env`, and recreate the `homeassistant` container. Official notes: [EcoNet SSL troubleshooting](https://www.home-assistant.io/integrations/econet/#ssl-certificate-verification-failed-home-assistant-container-installs). Do not disable TLS.

## Home Assistant–only devices (Refoss, Govee, …)

Add these in the Home Assistant UI, not in this git repo:

**Settings → Devices & services → Add integration**

They do not need `ENABLE_*` flags here. Removing them is also done in that same HA screen.

This site's meter-1: **never add A3+B2**. **10-11 Sep:** A3 was the KU / cargo-trailer load leg; B2 a branch on that leg. **15 Sep:** A3/B2 match Sungold **AC input** (same 10.40 A as the cart LCD); KU trailer AC was unmetered in that shot. Live log: [SOLAR_POWER_BALANCE.md](SOLAR_POWER_BALANCE.md). Official product name is **Refoss Smart Energy Monitor, meter-1**; HA channel labels are **A1-C6** ([Refoss integration](https://www.home-assistant.io/integrations/refoss/)). Apply HA labels/headings on `` with HA stopped: `sudo python3 scripts/ha_label_victron_refoss.py`.

Home Assistant must be connected to MQTT for **Victron / Sungold / Pi host / house BLE (Theengs)** sensors. The installer does that for you (HA 2026+). Do not paste broker settings into `configuration.yaml`.

---

## Away from home (vpn)

Not a device in this repo. Install vpn on **``** and on your phone to open the **same** Home Assistant dashboard on cellular. Do not put vpn keys or machine names in git. Full steps: [vpn.md](vpn.md).

---

## Home Assistant itself

Canonical HA is the Container on **``** ([alfa-ai HOMEASSISTANT_105_OPERATOR](https://github.com/example/alfa-ai/blob/main/docs/HOMEASSISTANT_105_OPERATOR.md)). On a Pi, leave `ENABLE_HOME_ASSISTANT=0` so `deploy.sh` does not start a second instance.

| Flag in Pi `.env` | Result |
|-------------------|--------|
| `ENABLE_HOME_ASSISTANT=0` | No HA container on the Pi (MQTT collectors still run) |
| `ENABLE_HOME_ASSISTANT=1` | **Do not use on this cluster** — would start HA on the Pi |

---

## Checklist for a YouTube / new-user setup

Copy this and tick as you go:

- [ ] Pi on the network; `hostname -I` written down
- [ ] `git clone` + `cp dotenv.sample .env`
- [ ] `MQTT_HOST=solar-broker` / `MQTT_USER` / `MQTT_PASSWORD` set
- [ ] Victron: MACs in `user_settings_data.py`, keys in `victron-secrets.env`
- [ ] `sudo bash scripts/deploy.sh` finished on **solar-broker**; `docker ps` shows `victron_ble2mqtt` (not `homeassistant`)
- [ ] Browser: Home Assistant on **`:8123`** — account created
- [ ] MQTT devices visible in HA
- [ ] Sungold only if USB is plugged: `ENABLE_SUNGOLD=1`
- [ ] Optional away-from-home: [vpn.md](vpn.md) (no keys in git)

---

## Adding a *new kind* of device to this repo (developers)

If you are building another sidecar (not just another Victron MAC):

1. Add a row to the **Catalog** table above.
2. Default it **off** (`ENABLE_YOURDEVICE=0` in `dotenv.sample`).
3. Gate it in `scripts/deploy.sh` the same way as Sungold.
4. Link a short `docs/YOURDEVICE.md` from this page and from the README table.
5. Do not change Victron BLE or write to inverters unless the operator asks.

Beginners should not need that path. Use the catalog switches.
