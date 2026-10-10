# Solar HA / Node-RED split (operator 2026-09-24)

## Home Assistant (`/site-solar`, packages)

- **Device clamps only** on Site solar: Victron BLE, Sungold Modbus, meter-1 (via `meter-1_*` live wrappers when stale/off-path).
- **No** template site totals, jumper tiles, or equal-share sensors in HA packages or Site solar storage. `sensor.battery-1-pv_now` and `sensor.battery-2-pv_now` (2026-10-08) are bus PV meters: KU is the 100/50 plus the paired 75/15, T2 is 0. Legacy 8-panel / PWM / `/3` math in Node-RED stays retired. Strings tonight: KU 100/50 2s5p, KU 2p, KU 2s. T2 has no MPPT.
- Dump automations stay in `dump_control.yaml` (H5082 dump sockets; small templates for staging only).

## Node-RED (`http://solar-broker/`)

- **Solar plant diagram** tab: editable topology, live device status from HA REST.
- **Solar computed meters** tab + page **`/solar/computed`**: derived watts (jumper, meter-1 A3 live; KU per-string est pending BLE keys). Logic: `scripts/nodered_solar_computed.js` (mirrors `solar_watt_ledger.py` helpers). PWM and equal-share `/3` retired 2026-10-02.

HA remains the **sensor bus**; Node-RED is the **derived display** (and diagram editor).

## Retired in HA (do not re-add to Site solar)

See `SOLAR_DEVICE_SENSORS_ONLY.md` removed list. Use Node-RED computed page or extend `nodered_solar_computed.js`.
