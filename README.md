# Solar MQTT / Home Assistant integration (public snapshot)

Victron BLE (and optional Sungold / BMS sidecars) publishing to MQTT for **Home Assistant** on your
LAN. This repository is a **scrubbed snapshot**; see `docs/PUBLIC_SNAPSHOT.md`.

## Configure before you run

1. **Install your own MQTT broker** (for example Mosquitto) on your LAN.
2. Copy `swarm/example/.env.example` to `.env` (or use the env example that matches your stack) and set broker host, user, and password. Do not commit `.env`.
3. Copy `config/hosts.example.env` to `config/hosts.env` and set `SOLAR_BROKER_HOST` to your broker address (RFC 5737 example in that file).
4. Copy `config/entities.example.yaml` and rename entity ids in your Home Assistant packages / MQTT discovery to match your devices ([MQTT naming](https://www.home-assistant.io/integrations/mqtt/)).

---

# victron-ble2mqtt-integration

## What it is

A **Raspberry Pi home-energy stack**. It listens to your solar / battery gear, sends the numbers to a local MQTT broker (Mosquitto), and shows them in **Home Assistant** — the dashboard you open in a browser or on your phone (`http://YOUR-PI-IP:8123`).

The same repo also runs on a **second Pi in the house** (`HOST_ROLE=monitor`): LAN DNS (AdGuard) and a Bluetooth gateway that forwards house BLE into the Pi 4 broker. The Pi 4 cannot hear those radios from another building. Details: [docs/monitor_HOUSE_EDGE.md](docs/monitor_HOUSE_EDGE.md).

It is meant to run **on your LAN**, not in a vendor cloud. At home you open Home Assistant on Wi‑Fi; **away from home** you use an optional VPN so you can review the same numbers without opening the dashboard to the public internet. You do not need to know GitHub to use it; the install steps below are copy-and-paste on the Pi. Use an optional VPN away from home, and do not publish the dashboard on the public internet.

One installer (`scripts/deploy.sh`) sets up Docker, Mosquitto, Home Assistant, and the Victron Bluetooth reader. Optional pieces (Sungold inverter, extra meters) turn on when you are ready.

## What it can do and what it’s for

**What it’s for:** see live battery, solar, and (optionally) inverter data at home without sitting in VictronConnect or a vendor cloud app. Useful if you already have Victron Bluetooth devices and want them next to lights, thermostats, and other Home Assistant stuff.

**What it can do**

| Gear | What this repo does |
|------|---------------------|
| Victron SmartShunt / MPPT (Bluetooth) | Reads BLE advertisements and creates Home Assistant sensors (voltage, current, SOC, solar power, charge state, …) |
| Sungold SPH302480A (USB cable) | Optional **read-only** Modbus sidecar — PV, battery, grid, load. Off until you plug USB and set `ENABLE_SUNGOLD=1` |
| BMS supervisor (VE.Direct USB) | Optional **read-only** shunt sidecar — voltage, current, SoC, alarm. Off until you plug USB and set `ENABLE_BMS_SUPERVISOR=1` |
| The Raspberry Pi itself | CPU, temperature, Wi‑Fi, uptime — so you can see if the box is healthy |
| House BLE (second Pi) | Optional **Pi 5** (`HOST_ROLE=monitor`) forwards decoded BLE to this Mosquitto |
| Refoss / Govee / other Wi‑Fi devices | **Not** installed here. Add those inside Home Assistant → Settings → Devices & services |
| Phone / laptop away from home | Optional VPN — same Home Assistant, no router port-forward. |

**What it does *not* do**

- It does **not** change inverter or charger settings (Sungold is sensors only; use the front panel).
- It does **not** replace VictronConnect for pairing or advertisement keys.
- It does **not** require a GPU cluster or any other repo to get a basic dashboard. An optional VPN is only for viewing that dashboard when you are not on home Wi‑Fi.

**Add or remove gear:** [docs/DEVICES.md](docs/DEVICES.md) — one page of on/off switches.

---

## What you need

1. A **Raspberry Pi** (Pi 4 is what we use) with Raspberry Pi OS and internet.
2. The Pi on your **home Wi‑Fi or Ethernet**.
3. **Bluetooth on** (for Victron). Close the VictronConnect app on your phone while testing — it can hide the Bluetooth ads.
4. About 20–40 minutes the first time (Home Assistant image is large).

Optional later: Sungold USB cable, extra Victron devices, and an optional VPN for away-from-home access.

---

## Easy install (recommended)

On the Pi, open a terminal and paste **one block at a time**.

### 1. Download the project

`git clone` means “download this folder from the internet.”

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/example/victron-ble2mqtt-integration.git
cd victron-ble2mqtt-integration
```

### 2. Create your secrets file

`.env` is a private settings file. It is **not** uploaded to GitHub if you follow these steps.

```bash
cp dotenv.sample .env
chmod 600 .env
nano .env
```

Change these three lines (use your Pi’s LAN IP from `hostname -I`, not `solar-broker0.XX`):

```text
MQTT_HOST=solar-broker
MQTT_USER=victron
MQTT_PASSWORD=change-me
```

Save: `Ctrl+O`, Enter, then `Ctrl+X`.

Leave Sungold **off** (`ENABLE_SUNGOLD=0`) until the USB cable is plugged in. See [docs/DEVICES.md](docs/DEVICES.md).

### 3. Add Victron Bluetooth keys (if you have Victron)

Each Victron device has a 32-character **advertisement key** (from VictronConnect). Put them in a second private file:

```bash
cp swarm/victron-secrets.env.example victron-secrets.env
chmod 600 victron-secrets.env
nano victron-secrets.env
```

Example:

```text
ADVKEY_BATTERY_1=your32hexcharactershere00000000
ADVKEY_victron-mppt-1=your32hexcharactershere00000000
ADVKEY_BATTERY_2=your32hexcharactershere00000000
```

You also need the device **MAC addresses** in `override/victron_ble2mqtt/user_settings_data.py` (this repo ships the author’s MACs as examples — **replace them with yours**). Step-by-step: [docs/DEVICES.md](docs/DEVICES.md#victron-bluetooth).

The Victron bridge checks its secrets at startup. If `MQTT_USER` is set but `MQTT_PASSWORD` is empty, or **no** device has an `ADVKEY_*` key, the `victron_ble2mqtt` container stops with an error that names the missing variable (`docker logs victron_ble2mqtt`). It doesn't fall back to running without them.

### 4. Run the installer

This installs Docker, Mosquitto (MQTT), Home Assistant, and the Victron reader. Safe to run more than once.

```bash
sudo bash scripts/deploy.sh
```

First run can take a while. When it finishes:

```bash
docker ps
```

You should see `victron_ble2mqtt` and `homeassistant` listed as **Up**.

If `docker` says **permission denied**, log out and back in (or reboot), then try `docker ps` again.

### 5. Open Home Assistant

On a phone or PC on the same Wi‑Fi:

```text
http://YOUR-PI-IP:8123
```

Example: `http://solar-broker`

Create your Home Assistant account on first visit. MQTT is wired automatically by the installer (Home Assistant 2026+).

**Dockge** (optional container UI): `http://YOUR-PI-IP:5006`

### 6. Away from home (optional)

To review the same numbers on cellular or another network, use an optional VPN on the Pi and on your phone. Do not open Home Assistant to the public internet.

---

## After install — turn devices on or off

| Want | Do this | Details |
|------|---------|---------|
| Victron batteries / MPPT | Keys in `victron-secrets.env` + MACs in `user_settings_data.py`, then `sudo bash scripts/deploy.sh` | [DEVICES.md](docs/DEVICES.md#victron-bluetooth) |
| Sungold inverter | Plug USB, set `ENABLE_SUNGOLD=1` in `.env`, run deploy | [DEVICES.md](docs/DEVICES.md#sungold-inverter) |
| Skip Home Assistant | `ENABLE_HOME_ASSISTANT=0` before deploy | You still get MQTT |
| Skip Sungold | Leave `ENABLE_SUNGOLD=0` (default) | Victron is unchanged |
| House BLE + LAN DNS | On the **Pi 5**: same clone, `HOST_ROLE=monitor`, `sudo bash scripts/deploy.sh` | [monitor_HOUSE_EDGE.md](docs/monitor_HOUSE_EDGE.md) |

You do **not** need to delete the whole project to drop a device. Flip a flag or remove one key, then re-run deploy.

---

## Did it work?

| Check | Command or place |
|-------|------------------|
| Containers running | `docker ps` |
| Victron / Pi numbers | Home Assistant → **Settings → Devices & services → MQTT** |
| Sungold (if enabled) | Same MQTT page, device **Sungold SPH302480A** |
| Live Victron logs | `docker logs -f victron_ble2mqtt` |
| Live Sungold logs | `docker logs -f sungold_modbus_ro` |

Close the Victron phone app if sensors stay empty.

---

## If something goes wrong

| Problem | Try this |
|---------|----------|
| Cannot open `:8123` | `hostname -I` — use that IP. Wait a few minutes after first install. |
| No Victron entities | Close VictronConnect. Check ADVKEY and MAC. `sudo bluetoothctl show` should say Powered: yes. |
| `victron_ble2mqtt` keeps restarting | `docker logs victron_ble2mqtt`. A line like `missing required configuration: ...` names the variable to set (`MQTT_PASSWORD` or `ADVKEY_*`). |
| “Connection refused” on MQTT | Set `MQTT_HOST` to the Pi LAN IP, then `sudo bash scripts/deploy.sh` |
| Sungold skipped | USB plugged? `ls -l /dev/sungold`? `ENABLE_SUNGOLD=1` in `.env`? |
| Need the long version | [DEPLOY.md](DEPLOY.md) |

---

## Words you will see

| Word | Plain meaning |
|------|----------------|
| **Git / clone** | Download this project folder |
| **`.env`** | Your private passwords and on/off flags |
| **Docker** | Runs each program in its own box (`victron_ble2mqtt`, `homeassistant`, …) |
| **MQTT / Mosquitto** | Local mailbox the boxes use to talk |
| **Home Assistant** | The website/app dashboard (`:8123`) |
| **BLE** | Bluetooth Low Energy (Victron ads) |
| **Modbus** | Wired USB talk to the Sungold inverter (read-only here) |
| **ADVKEY** | Secret that unlocks a Victron Bluetooth advertisement |
| **VPN** | Optional private network so you can open Home Assistant away from home |

---

## More docs (when you need them)

| Doc | Who it is for |
|-----|----------------|
| [docs/DEVICES.md](docs/DEVICES.md) | Add / remove Victron, Sungold, HA-only devices |
| [docs/monitor_HOUSE_EDGE.md](docs/monitor_HOUSE_EDGE.md) | House Pi 5: AdGuard DNS + BLE → Pi 4 MQTT |
| | Optional: view Home Assistant away from home |
| [docs/sungold-inverter-1.md](docs/sungold-inverter-1.md) | Sungold USB, udev, smoke test (optional; this site not connected) |
| [docs/SOLAR_POWER_BALANCE.md](docs/SOLAR_POWER_BALANCE.md) | 24 V watt in vs watt out (3 MPPTs, shunts, meter-1 A3/B2) |
| [Home Assistant Energy](https://www.home-assistant.io/docs/energy/) | Energy dashboard for grid, solar, and battery. This repo feeds that built-in page. See also [docs/SOLAR_HA_DASHBOARD.md](docs/SOLAR_HA_DASHBOARD.md). |
| [docs/solar-broker_BMS_SOFTWARE.md](docs/solar-broker_BMS_SOFTWARE.md) | Pi battery **supervisor** (VE.Direct shunt / MQTT). Not a pack BMS. Default off. |
| [docs/SOLAR_ARRAY_SOLARK.md](docs/SOLAR_ARRAY_SOLARK.md) | Planned **separate** 48 V island (not T2/KU) |
| [DEPLOY.md](DEPLOY.md) | Installer flags, Dockge, troubleshooting |
| [docs/ALFA_CLUSTER_INTEGRATION.md](docs/ALFA_CLUSTER_INTEGRATION.md) | Optional notes if another hub shares the LAN |

Do not commit `.env` or `victron-secrets.env`. They hold passwords and device keys.

License: MIT (see the project license file).
