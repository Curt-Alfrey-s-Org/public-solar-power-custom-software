# Solar HA: device sensors only (policy)

**Effective:** removed template **site total** sensors and **duplicate tiles** from
`config/dashboards/solar-plant.yaml`. **Now** view: one tile per device entity
(Victron BLE, Sungold Modbus, meter-1). Header badges on **Now** are
**A SoC**, **B SoC**, **Sungold SoC**, and **NWS** (see below).


## Header badges

The **Now** view header is [view badges](https://www.home-assistant.io/dashboards/views/)
(`views[].badges`, `header.badges_position: bottom`). The badge
[name](https://www.home-assistant.io/dashboards/badges/) is the short label.

| Badge | Entity |
|-------|--------|
| A SoC | `sensor.battery_1_state_of_charge` |
| B SoC | `sensor.battery_2_state_of_charge` |
| Sungold SoC | `sensor.sungold-inverter-1_battery_soc` |
| NWS | `sensor.nws_example_alerts` |

Sungold SoC is that header badge only on **Now**. It is not also a tile in the
Sungold section (that row used to say **Batt SoC (reset on the Sungold when full)**).
History still graphs the same entity. The Sungold charge box still lists it
next to the source-bank SoC numbers.

## Removed (do not re-add without operator approval)

- `sensor.site_solar_power`, `site_charge_power`, `site_source_power`,
  `site_total_load_power`, `site_load_*`, `*_today` site integrals
- Riemann `integration` / `utility_meter` rows in `solar_plant.yaml` (kWh tiles)
- Dashboard **Quick meters**, **Instant W** distribution, duplicate tiles (same entity twice)
- Template dump status tiles on the main view (`dump_surplus_w`, `dump_bus_load_*`, binary gates)
- Jumper math: `battery-2-battery-1-jumper_*`, `battery-1-unmetered_pv_est_*`, `battery-1-charger_equal_share_*`
- AC merge/loss estimates: `trailer_outlet_power`, `battery-1-renogy_ac_load_power`,
  `inverter-1-ac_in_unmatched_power`, `sungold_*_va_power`, `*_conversion_loss_*`,
  `solar_component_losses_power`, `sungold_cart_to_load_power`, charge/discharge splits

## Use instead

| Question | Read this entity (device) |
|----------|---------------------------|
| Paired B 75/15 solar W | `sensor.victron-mppt-1_solar` (not A 100/50) |
| A pack W | `sensor.battery_1_power` (sign = shunt) |
| B pack W | `sensor.battery_2_power` |
| Sungold PV | `sensor.sungold-inverter-1_pv_power` |
| Cart charge W | `sensor.sungold-inverter-1_charging_power` |
| Sungold AC out | `sensor.sungold-inverter-1_load_power` |
| Trailer / breaker clamp | `sensor.meter-1_a3_power`, `sensor.meter-1_b3_power` |
| Sungold AC-in (inverter) | `sensor.sungold-inverter-1_grid_voltage` / `grid_current` |

Dump automations still use **small templates inside** `dump_control.yaml`
(for staging confirm and A+PV compare). Those are not shown on the Site solar tiles.

## Deploy

From `` after `git pull`:

```bash
cd /home/operator/victron-ble2mqtt-integration
bash scripts/install_solar_plant_ha.sh
HA_TOKEN_FILE=... python3 scripts/save_solar_plant_storage_dashboard.py --dry-run
# add --force to replace UI edits (live config is backed up first)
```

Old computed entities may remain in **History** until purged; remove stale entities
in **Settings > Devices & services > Entities** if needed.

## Node-RED computed meters (not in HA)

Derived tiles (legacy B est / equal-share retired 2026-10-02; jumper, meter-1 A3 live; per-panel est waits on new BLE keys) live in **Node-RED** only:
`http://solar-broker/solar/computed` (see `docs/SOLAR_HA_NODERED_SPLIT.md`).

HA keeps `solar_meter-1_live.yaml` so Site solar meter-1 tiles go **Unavailable** when the AC path is dead (not frozen watts).
