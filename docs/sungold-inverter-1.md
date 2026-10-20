# Sungold SPH302480A — read-only Modbus → MQTT → Home Assistant

**Most people:** plug the USB cable, set `ENABLE_SUNGOLD=1` in `.env`, run `sudo bash scripts/deploy.sh`. On/off and how this fits next to Victron: **[DEVICES.md](DEVICES.md#sungold-inverter)**. First install: **[README](../README.md)**.

Sibling sidecar to **victron_ble2mqtt**. Publishes **sensors and binary_sensors only** — no HA controls, no Modbus writes. Change inverter settings on the **front panel** only.

**Voltage guard (Site solar):** dump control can shed dump sockets whose Inverter helper is Sungold, and can alert, when Sungold battery voltage is under helpers you set. It cannot command this inverter to charge. See [docs/site-solar/dump-sph-vguard.md](site-solar/dump-sph-vguard.md).

**Sungold charge (Site solar):** a socket whose Use helper is **Sungold charge** can be turned on so a A or B outlet feeds this inverter's AC inlet when the pack is low, and again for surplus while that bank is charging hard and Sungold is under full volts. The voltage guard does not start this charge. The sidecar still does not write Modbus. On the front panel, charger source priority must allow mains / utility charging; if it is solar-only, inlet power will not charge the pack. See [docs/site-solar/sph-charge.md](site-solar/sph-charge.md).

## Hardware

**This site:** the SPH302480A sits on a **dolly cart** with **2x LiTime 24 V 100 Ah** in parallel (emergency backup). It is **not** wired into the A/B trailer buses. Trailer layout: [SOLAR_POWER_BALANCE.md](SOLAR_POWER_BALANCE.md). Planned house install (2026-10-07, parts on the way, not installed): [Planned install](SOLAR_POWER_BALANCE.md#planned-install-operator-2026-10-07).

**15 Sep 15:53 ET:** cart on **AC charge**, PV **0 W**, Boost charge, remaining **68%**. Refoss **A3/B2** match LCD **AC INPUT** (10.40 A). Conversion loss:

`|A3| - INPUT BATT KW - INV OUTPUT LOAD KW - PV OUTPUT KW` = **1190 - 1042 - 10 - 0 = 138 W (~12% of AC-in)**.

Do not add B2. Do not use A3 as B trailer or cluster idle in that shot. Output mode **4** stays the raw integer (lookup is 0-3: Initialization / Standby / Mains output / Inverter output).

| Item | Value |
|------|--------|
| Model | Sungold **SPH302480A** (SRNE-class hybrid) |
| Link | USB-B → Pi (CH340 serial, vendor **1a86**) |
| Modbus | RTU **9600 8N1**, slave address **1** |
| Phase | Single-phase **120 V**, one MPPT |

## Architecture

```
SPH302480A (USB) → sungold_modbus_ro → Mosquitto (:1883) → Home Assistant
Victron BLE      → victron_ble2mqtt  → Mosquitto (:1883) → Home Assistant
```

- Victron stack is **unchanged**.
- Discovery prefix: `homeassistant/sensor/sungold-inverter-1-*` (and `binary_sensor`).
- MQTT topic root: `MQTT_TOPIC=sungold-inverter-1` (distinct from Victron).

## Operator setup (solar-broker)

Current USB host is this Pi 4. Planned USB host is the house Pi 5 (not installed): [Planned install](SOLAR_POWER_BALANCE.md#planned-install-operator-2026-10-07).

### 1. Plug USB

Connect the inverter **USB-B** cable to the Pi. Confirm CH340:

```bash
lsusb | grep -i '1a86\|ch340\|qinheng'
ls -l /dev/serial/by-id/
```

Typical by-id path (example — yours may differ):

```text
/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
```

### 2. Udev stable symlink

```bash
sudo cp udev/99-sungold-ch340.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
ls -l /dev/sungold
```

Or re-run **`sudo bash scripts/deploy.sh`** with `ENABLE_SUNGOLD=1` (installs the rule automatically).

### 3. Configure `.env`

Add to `.env` (see `dotenv.sample`):

```bash
ENABLE_SUNGOLD=1
SUNGOLD_SERIAL_DEVICE=/dev/sungold
# Or the full by-id path:
# SUNGOLD_SERIAL_DEVICE=/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
MQTT_TOPIC=sungold-inverter-1
DEVICE_NAME=Sungold SPH302480A
MODBUS_ADDRESS=1
POLL_INTERVAL_SEC=5
MODBUS_TIMEOUT=1.0
```

Uses the same **`MQTT_HOST` / `MQTT_USER` / `MQTT_PASSWORD`** as Victron and Home Assistant.

### 4. Deploy

```bash
sudo bash scripts/deploy.sh
# Or stack only:
docker compose -f docker-compose.sungold.yml up -d --build
```

Dockge: stack appears as **`sungold`** under `/opt/stacks/sungold` when `ENABLE_DOCKGE=1`.

### 5. Verify

```bash
bash scripts/sungold_smoke.sh
```

### Container health (heartbeat)

Compose [healthcheck](https://docs.docker.com/reference/compose-file/services/#healthcheck) (`CMD-SHELL`, `start_period` 90s) passes when `HEARTBEAT_FILE` mtime is within **`4 × POLL_INTERVAL_SEC + 60`** seconds (default poll 5s → max age 80s). The file is **not** touched on Modbus reads alone.

Each poll cycle touches the heartbeat only after at least one **curated** register was read **and** its retained state MQTT publish completed successfully. The sidecar uses Eclipse Paho [`Client.publish()`](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html#paho.mqtt.client.Client.publish) → [`MQTTMessageInfo`](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html#paho.mqtt.client.MQTTMessageInfo): `rc == MQTT_ERR_SUCCESS`, then [`wait_for_publish()`](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html#paho.mqtt.client.MQTTMessageInfo.wait_for_publish) / [`is_published()`](https://eclipse.dev/paho/files/paho.mqtt.python/html/client.html#paho.mqtt.client.MQTTMessageInfo.is_published) with `loop_start()` running. If the broker is down, `publish()` returns `MQTT_ERR_NO_CONN` or `is_connected()` is false — the heartbeat stays stale and Docker marks the container **unhealthy** even when USB Modbus still answers.

USB timeouts on **some** registers (`No communication with the instrument`) are expected when the cart is idle or a single Modbus read misses; the sidecar keeps polling. The container stays **healthy** while at least one curated register still publishes within the max-age window. If the inverter is powered off, every read fails, the heartbeat goes stale, and autoheal can restart the sidecar.

Manual checks:

```bash
docker logs -f sungold_modbus_ro
mosquitto_sub -h "$MQTT_HOST" -p 1883 -u "$MQTT_USER" -P "$MQTT_PASSWORD" \
  -t 'sungold-inverter-1/sensor/+/state' -v
mosquitto_sub -h "$MQTT_HOST" -p 1883 -u "$MQTT_USER" -P "$MQTT_PASSWORD" \
  -t 'homeassistant/sensor/sungold-inverter-1-+/config' -C 3 -W 5
```

In Home Assistant: **Settings → Devices & services → MQTT** — device **Sungold SPH302480A** with PV, battery, grid, load, and temperature entities.

**Solar dashboard:** HA [label](https://www.home-assistant.io/docs/organizing/labels/) **Sungold** (`sungold`) on that device and its MQTT entities, plus a **Sungold** [sections](https://www.home-assistant.io/dashboards/sections/) heading on sidebar **Solar** (one [tile](https://www.home-assistant.io/dashboards/tile/) per entity). Tiles bind **live** `entity_id`s from MQTT `unique_id` `sungold-inverter-1-*` and set `name: {type: entity}` so the card shows **PV input voltage**, not `Sungold S...` ([card naming](https://www.home-assistant.io/dashboards/naming/)). The cart stays off A/B.

Order: sidecar must already have republished discovery while HA is **running**, then stop HA and apply:

```bash
sudo python3 scripts/ha_label_sungold_solar.py
```

Then start the `homeassistant` container and wait for `:8123` ([container common tasks](https://www.home-assistant.io/common-tasks/container/), alfa-ai `wait-http.sh`).

## Published entities (curated)

HA MQTT `name` strings follow the SPH302480A **LCD real-time pages** and **fault table**, not SRNE nicknames. MQTT `unique_id` is `{mqtt_topic}-{key with / as -}` (for example `sungold-inverter-1-pv1-voltage`). Changing a **display name** keeps the same `unique_id`. Changing a **register key** (for example `pv/voltage` → `pv1/voltage`) is a new `unique_id`; Lovelace must be rewritten from the live registry.

Official: [SunGoldPower SPH302480A product page](https://sungoldpower.com/products/3000w-24v-solar-inverter-charger) (user manual download: LCD §4.1, fault codes §6.2). Same LCD wording in the 2023-11-28 reprint: [3000W_SPH302480A_20231128.pdf](https://www.solaris-shop.com/content/3000W_SPH302480A_20231128.pdf). Product page also states **high frequency transformer-less** and **PV Charging Current** as the 0–80 A rating (LCD field is `PV OUTPUT A`).

| HA name | Official source |
|---------|-----------------|
| PV input voltage | LCD `PV INPUT V` |
| PV output current | LCD `PV OUTPUT A` (PV output current) |
| PV output power | LCD `PV OUTPUT KW` |
| Remaining battery | LCD battery bars ("remaining battery") |
| Battery input voltage | LCD `INPUT BATT V` |
| Input battery current | LCD `INPUT BATT A` |
| Battery temperature | Not an LCD page; SRNE holding register (keep as diagnostic) |
| Charge state | CHARGE LED (charging / charging completed) plus setup boost / constant-voltage / floating; Modbus integers are SRNE-class, not printed in the Sungold manual |
| Battery input power | LCD `INPUT BATT KW` |
| Output mode | AC/INV LED: Mains output / Inverter output. LCD does not name Initialization / Standby; unknown codes publish as the raw integer |
| Inverter error flags | Not an LCD page; SRNE diagnostic |
| Fault code | LCD middle + §6.2 `【01】`… including BMS `【30】`–`【64】` |
| Fault state | FAULT LED "Fault state" |
| AC input voltage | LCD `AC INPUT V` (manual: Mains / AC input, not "grid") |
| AC input current | Not a numbered LCD page; named to match `AC INPUT V` / `Hz` |
| AC input frequency | LCD `AC INPUT Hz` |
| Output load voltage | LCD `OUTPUT LOAD V` |
| AC output frequency | LCD `AC OUTPUT LOAD Hz` |
| AC output load current | LCD `AC OUTPUT LOAD A` |
| Load active power | LCD `INV OUTPUT LOAD KW` |
| PV charger heatsink temperature | LCD `PV TEMP` |
| Inverter heat sink temperature | LCD `INV TEMP` / §6.2 "Inverter heat sink" |

Not published for this model (manual + this hardware):

- **PV total power** — one PV port / one MPPT (`PV+` / `PV-` only).
- **Grid power** — SPH302480A rejected holding register `0x023A` (illegal data address).
- **Transformer temperature** — product is **high frequency transformer-less**.
- LCD pages **OUTPUT BATT A / KW** and **OUTPUT LOAD KVA** — no verified Modbus address in the Sungold manual (manual does not publish a map).

Slave **illegal request** (unsupported address) still **skips** that register for `MODBUS_SKIP_RETRY_INTERVAL` ([IllegalRequestError](https://minimalmodbus.readthedocs.io/en/stable/apiminimalmodbus.html#minimalmodbus.IllegalRequestError)). USB timeouts (`NoResponseError` / "no communication with the instrument") do **not** skip: every curated register is polled again on the next cycle so a brief USB drop does not blank half the Solar tiles for an hour. Skip does **not** publish an empty MQTT discovery payload. Home Assistant [removes the entity](https://www.home-assistant.io/integrations/mqtt/#discovery-messages) when the discovery topic is an empty retained string; that is used only for `RETIRED_DISCOVERY`. Last Modbus values are published with MQTT **retain** so an HA restart keeps the last reading until the next poll.

Sidecar-only rebuild on solar-broker (do **not** run full `scripts/deploy.sh` for this; that compose file can rewrite Mosquitto):

```bash
sudo docker compose -f docker-compose.sungold.yml up -d --build
```

Do not pass `--remove-orphans`.

## Troubleshooting

| Symptom | Action |
|---------|--------|
| Deploy skips Sungold | Set `ENABLE_SUNGOLD=1`; confirm `/dev/sungold` or `SUNGOLD_SERIAL_DEVICE` exists |
| Container unhealthy | Heartbeat stale: no successful Modbus read **and** MQTT state publish in the last `4 × POLL_INTERVAL_SEC + 60` s. Check USB/Modbus **and** Mosquitto reachability (`MQTT_HOST`, credentials, broker up). `docker logs sungold_modbus_ro`. Solar tiles should stay **Unavailable**, not **Entity not found**. |
| Solar tiles **Entity not found** | Lovelace still points at retired `entity_id`s, or empty discovery deleted the MQTT entities. Recreate the sidecar, wait until HA has the `sungold-inverter-1-*` unique_ids, then re-run `ha_label_sungold_solar.py` with HA stopped. |
| No HA entities | Confirm HA MQTT integration uses same broker; check discovery topics with `mosquitto_sub` |
| Permission denied on serial | User in `dialout` group; udev rule sets `GROUP=dialout` |

## LiTime 24 V 100 Ah and the Sungold BMS port

Advertisements for MAC `AA:BB:CC:DD:EE:FF` (name `L-24100BNN160-C03961`) carry UUID `0xFFE0` and no voltage. That UUID is not a register map. Pack stats are read by **aiobmsble 0.29.0** `aiobmsble.bms.redodo_bms.BMS`, the library [BMS_BLE-HA](https://github.com/patman15/BMS_BLE-HA) uses. The matcher is local name `L-24*` and service `FFE0`; the library connects to FFE0, notifies FFE1, and writes FFE2. Source: [redodo_bms.py at 0.29.0](https://github.com/patman15/aiobmsble/blob/0.29.0/aiobmsble/bms/redodo_bms.py). No phone-app PIN is stored. If the LiTime app has a 6-digit Bluetooth password, turn it off and disconnect the phone ([BMS_BLE README, Litime batteries](https://github.com/patman15/BMS_BLE-HA#litime-batteries)).

The radio is Pi 4 `` adapter **`hci1` only**. `hci0` stays the Victron radio. `victron_ble2mqtt` is not stopped and this client never binds `hci0`. Theengs and the H5082 bridge stay up on `hci1`. [Theengs Gateway use](https://gateway.theengs.io/use/use.html) does not require one GATT client to own the adapter (its clock sync connects while scanning). Each poll uses `BMSConfig(keep_alive=False)`, so the link drops after the read ([BaseBMS.async_update](https://github.com/patman15/aiobmsble/blob/0.29.0/aiobmsble/basebms.py)). Poll interval is 30 s, the BMS_BLE default (`UPDATE_INTERVAL` in [const.py](https://github.com/patman15/BMS_BLE-HA/blob/main/custom_components/bms_ble/const.py)).

Home Assistant on `` has no Bluetooth adapter in the container. Theengs cannot decode LiTime ([device list](https://decoder.theengs.io/devices/devices.html)). The Pi publishes MQTT discovery to Mosquitto on `:1883`. Discovery prefix is `homeassistant` ([MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)). State topic is `litime/c84780722a2f/state`. The broker user is the existing Victron user in `hosts/solar-broker/mqtt.env`. Script: `scripts/litime_bms_mqtt.py`. Unit: `hosts/solar-broker/litime-bms-mqtt.service`. Sungold BMS wiring is unchanged. The [230 Ah shunt note](solar-broker_BMS_SOFTWARE.md) is a different pack. A live hci1 read published a positive pack voltage and state of charge before any card was saved. Site solar (`/site-solar`, Now view, after Sungold) card **LiTime L-24100** uses `sensor.litime-battery-1_voltage`, `sensor.litime-battery-1_soc`, `sensor.litime-battery-1_current`, `sensor.litime-battery-1_power`, and `sensor.litime-battery-1_temperature`. The card is the BLE reader. This pack is charging elsewhere and is not yet the third pack on the Sungold cart. The section stays in `config/dashboards/solar-plant.yaml` after Sungold on the Now view, so a later storage seed save does not drop it. No RSSI is stored. Service `litime-bms-mqtt.service` on Pi 4 polls every 30 s and disconnects after each read.

### Pack manual (FCC ID 2BDSV-24100)

- Product: [24V 100Ah Bluetooth](https://www.litime.com/products/litime-24v-100ah-lifepo4-rv-marine-battery-with-bluetooth)
- User manual PDF on that page (cover: Smart Bluetooth 5.0 x ComFlex Edition): [LiTime 25.6V 100Ah Bluetooth Lithium Battery-User Manual.pdf](https://cdn.shopify.com/s/files/1/0667/7220/5788/files/LiTime_25.6V_100Ah_Bluetooth_Lithium_Battery-User_Manual.pdf)
- FCC grant, model 24100, 2402-2480 MHz DTS: [fccid.io/2BDSV-24100](https://fccid.io/2BDSV-24100)

The store listing says app monitoring and a 4P2S maximum: "Smart Bluetooth 5.0: Monitor voltage, current, SOC, temperature, and more in real time via the free LiTime App" and "Max. Expansion (Parallel & Series) 4P2S". The manual PDF on the same page documents wired ports as well as Bluetooth.

Manual page 01, identification of parts:

> CAN-P | CAN-I Port: To communicate in parallel with the identical battery by provided battery parallel communication cable. To communicate with the external Victron GX series device by provided external communication cable.
>
> CAN-P | RS485 Port: To communicate in parallel with the identical battery by provided battery parallel communication cable. To communicate with the specified LiTime LCD screen. To communicate with the LiTime 24V solar inverter charger by provided RS485 communication extension cable and the external communication cable.
>
> It is necessary to use the specified LiTime screen and cable, other screens and cables are not supported. If the product is damaged by connecting other cables or screens, it will not be covered by the warranty.

Manual pages 10-14, series / parallel:

> Situation 1: When the battery is in communication. Support connecting up to 16 identical batteries in parallel for up to: 24V(25.6V) 1600Ah battery system.

Series is marked "DO NOT Support Series Connection" in that situation.

> Situation 2: When the battery is NOT in communication. Support connecting up to 8 identical batteries for up to: 4 in parallel as 24V(25.6V) 400Ah battery system or 2 in series as 48V(51.2V) 100Ah battery system.

> (Optional) Connect the screen or LiTime 24V solar inverter charger of the first battery to the CAN-P | RS485 port.
>
> (Optional) Connect the Victron GX device to the last battery of the CAN-P | CAN-I port by provided external communication cable.
>
> (Optional) Connect the first battery's CAN-P | CAN-I port to the second battery's CAN-P | RS485 port, then the second battery's CAN-P | CAN-I port to the third battery's CAN-P | RS485 port, and so on in sequence.

Power leads are still bus bars, positive to positive and negative to negative. "Turn on one of the batteries in the system and the whole system will be switched on." The battery on the monitoring screen "will complete the communication between the batteries within 5 seconds" and can then view each battery and the bank. Bluetooth in this manual is the LiTime app (OTA: "When a firmware upgrade notification appears in the LiTime APP"). It is not the inverter link.

Three identical packs in parallel fits both limits (16 with communication, 4 without). One pack does not host the other two over Bluetooth. The wired inverter port is the first battery's CAN-P | RS485, and the charger the manual names is a LiTime 24V solar inverter charger. Victron GX, if used, goes on the last battery's CAN-P | CAN-I. The manual does not name Sungold.

### Sungold BMS ports (SPH302480A)

Reprint: [3000W_SPH302480A_20231128.pdf](https://www.solaris-shop.com/content/3000W_SPH302480A_20231128.pdf). The inverter has external BMS ports. Parameter [32], RS485-2 communication:

> [32]SLA default -- RS485-2 port for PC or telecommunication control.
>
> [32]BMS -- RS485-2 port for BMS communication.

Parameter [33], Battery BMS communication protocol:

> When the parameter [32] setting item =BMS, you can choose to match the battery manufacturer's BMS protocol to communicate with BMS for the lithium battery protection. PAC=PACE, RDA=Ritar, AOG=ALLGRAND BATTERY, OLT=OLITER, HWD=SUNWODA, DAQ=DAKING, WOW=SRNE, PYL=PYLONTECH, UOL=WEILAN

Section 5.2, RS485 communication port: host-computer monitoring, and the optional RS485-to-WiFi/GPRS module. "Pin 1 is 5V power supply, Pin 2 is GND, Pin 5 is RS485-A2, Pin 6 is B2, Pin 7 is RS485-A1, and Pin 8 is RS485-B1."

Section 5.3, CAN communication function: "Function of connecting lithium battery communication." "Pin 1 is CAN-L, and Pin 2 is CAN-H."

Fault [58] BMS communication error: "Check whether the communication line is connected correctly and whether [33] is set to the corresponding lithium battery communication protocol."

LiTime is not in that list. The LiTime manual does not name the SPH302480A. There is no documented path that makes this pack the Sungold BMS comm point. Sungold battery volts already on Solar are the inverter LCD `INPUT BATT V` (Modbus), not this pack's BMS.

### Home Assistant and Theengs

[Theengs compatible devices](https://decoder.theengs.io/devices/devices.html) has no LiTime entry. [Gateway use](https://gateway.theengs.io/use/use.html) publishes Home Assistant discovery for decoded advertisements. Rack Theengs (`theengs/gateway:v1.7.5.1`) does not decode this MAC, and it does not give BMS_BLE a connection. The [Home Assistant Bluetooth integration](https://www.home-assistant.io/integrations/bluetooth/) is an adapter transport. The `` Home Assistant container has no adapter. Readings use the Pi 4 `hci1` aiobmsble path above, then MQTT discovery. `hci0` is untouched.

## Out of scope

- HA write controls (switch/number/select/button).
- SolarAssistant / Voltronic PI30 path.
- Changes to Victron BLE or ADVKEY configuration.

## Reference

Register map derived from [timbit123/srne-modbus](https://github.com/timbit123/srne-modbus) (Apache-2.0). This repo ships a **thin read-only** subset, not a full upstream clone.

## Battery current sign (HA / dump logic)

SRNE Modbus register **0x0102** (INPUT BATT A) uses the **opposite** sign from Victron-style
conventions in Home Assistant:

| Direction | Victron-style in HA | Raw SRNE before fix |
|-----------|---------------------|---------------------|
| Charging  | **+A**, **+W** (input power) | often **negative** A |
| Discharge | **-A**, negative `I*V` | often **positive** A |

The solar-broker sidecar applies **`invert=True`** on `battery/current`, then **`reconcile_battery_current`**
forces **positive** amps when **INPUT BATT KW** (`inverter/charging_power`, reg **0x010E**) is above ~15 W.
After publish, **`|A|*V` must agree with charging W** within normal meter tolerance.

Dump guard **`binary_sensor.dump_batt_inverter-1-ok`** uses `(battery_current * battery_voltage) >= -limit_w`;
it requires the corrected sign above.
