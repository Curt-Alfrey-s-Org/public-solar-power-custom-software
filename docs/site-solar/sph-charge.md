# Site solar help: Sungold charge

**Where:** Site solar > Now view > **Sungold charge**.
**Logic:** `config/packages/dump_control.yaml` and the Use option `Sungold charge` from
`scripts/create_plug_socket_labels.py`. Dashboard seed: `config/dashboards/solar-plant.yaml`.

## What this box is for

Charge the Sungold pack from a T2 or KU outlet when that feeding charger has spare
solar. There is no second Use and no second enable switch.

The inlet turns on only when the feeding charger is in Absorption or Float and
that bank is above its re-bulk stop (`binary_sensor.dump_battery-2-charger_float` and
not `binary_sensor.dump_v_rebulk_t2` for a T2 inlet; the KU stage and re-bulk
sensors for a KU inlet). A low Sungold pack does not turn the inlet on.
`binary_sensor.inverter-1-charge_need` stays off. Charge watts into the battery are not
a test, and both banks sitting at the float voltage during Bulk is not a test.

The inlet turns off when that feeding bank's re-bulk sensor is on (26.8 V when
float is 27.0 V). Reaching full Sungold volts does not turn it off while the
feeding charger is still in Absorption or Float.
`binary_sensor.inverter-1-charge_banks_feed` is the T2 stage check that holds it.

You choose which socket is the grid inlet by setting that socket's **Use** to
**Sungold charge** and its **Inverter** to the bank that feeds it (T2 or KU).
Nothing in the repo names a plug, a load or a place.

This is not a dump. Dump add, shed, off, on-demand and the Sungold voltage-guard
shed only look at Use = dump. A Sungold charge socket is left out of all of those,
including while rescue is on. Solar-gone, re-bulk and the dump sheds do not turn
it off.

The Sungold sidecar only reads the inverter. These rules switch the socket. They
do not write the inverter's charge settings. When the panel's own settings are
not calling for a charge, the socket can stay on with grid voltage present and
charging power about 0 W. That wait is not an inlet failure, and the inlet alert
stays off. The alert fires only when grid voltage is at or below 0 V.

## The entities

Pack needs charge and Inlet has no power show **On** or **Off**. They do not use device class `problem`, so the card does not say Problem. That class means a fault was detected (https://www.home-assistant.io/integrations/binary_sensor/#device-class).


| Row | Entity | Range / states | What it does |
|---|---|---|---|
| Status | `sensor.inverter-1-charge_status` | Off, Idle, Needs charge, Charging, On, solar feed, On under full volts, On at full volts, Held by hand, Inlet on no grid | Short state. Attribute `reason` is the Why row. **surplus** means a Sungold charge socket is on, rescue is off, and Sungold volts are under full. **min on** means the socket is on, rescue is off, and Sungold is at or above full (or volts are missing) while the minimum on timer runs out. |
| Why | `sensor.inverter-1-charge_status` | text | Same sensor, attribute `reason`. |
| Pack needs charge | `binary_sensor.inverter-1-charge_need` | Off | Stays off. A low Sungold pack does not turn the inlet on. |
| Inlet has no power | `binary_sensor.inverter-1-charge_inlet_dark` | On / Off | On when any Sungold charge socket is on, both Sungold grid voltage and charging power are numbers, grid voltage is at or below 0 V, and charging power is at or below 5 W. Grid voltage that is present means the inlet is energized and Sungold is waiting on its own charge settings, so this stays **off**. Missing, `unknown` or `unavailable` sidecar values stay **off**. They are not treated as 0. |
| Feeding bank under stop volts | `binary_sensor.inverter-1-charge_source_stop` | on / off | On when a Sungold charge socket is on and that bank's re-bulk sensor is on (`dump_v_rebulk_t2` or `dump_v_rebulk_ku`). |
| Feeding bank has surplus | `binary_sensor.inverter-1-charge_surplus_ready` | on / off | On when the dump master is not holding a dump socket as next, and a Sungold charge socket is off, not on hold and not in cooldown, and its feeding charger is in Absorption or Float above that bank's re-bulk stop. |
| Sungold voltage guard (sheds dump sockets only) | `binary_sensor.dump_inverter-1-vguard` | on / off | Shown here so you can see it. It does **not** start or hold a Sungold charge. It only sheds dump sockets whose Inverter is Sungold. See [dump-sph-vguard.md](dump-sph-vguard.md). |
| Enable Sungold charge | `input_boolean.inverter-1-charge_enabled` | on / off | Own switch for rescue and surplus. Does not follow the dump master switch. A brand-new helper starts **off**. Turning it off leaves sockets as they are. |
| Floor (Sungold volts) | `input_number.inverter-1-charge_floor_v` | 20–29.5 V, step 0.05 | Rescue trips when `sensor.sungold-inverter-1_battery_voltage` is under this. Suggested start **25.0 V**. A brand-new helper starts at **20**. |
| Margin below the lower of T2 and KU | `input_number.inverter-1-charge_margin_v` | 0–2 V, step 0.05 | Rescue trips when Sungold is below the lower of `sensor.battery_1_voltage` and `sensor.battery_2_voltage`, minus this. Suggested start **0.50 V**. A brand-new helper starts at **0**. |
| Full volts (off at or above) | `input_number.inverter-1-charge_full_v` | 24–29.5 V, step 0.05 | Pack recovered turns the socket off at full volts only when the feeding charger is not in Absorption or Float above re-bulk. Full volts do not turn the inlet off while that stage check is on. Suggested start **26.8 V**. A brand-new helper starts at **24**. |
| Surplus min charge W | `input_number.inverter-1-charge_surplus_min_w` | 100–4000 W, step 50 | Not used to turn the inlet on or off. A full charger holds charge watts near zero. |
| Also charge when SoC is low | `input_boolean.inverter-1-charge_soc_enabled` | off | Not on any HA tab. The SPH302480A percent is not a BMS value while program 32 is not BMS, so this switch stays **off** and the percent is not used. |
| SoC below | `input_number.inverter-1-charge_soc_below` | unused | Not on any HA tab. Ignored while the SoC switch stays off. |
| Source minimum volts | `input_number.inverter-1-charge_source_min_v` | 24–29.5 V, step 0.05 | Rescue only. The feeding bank must be at or above this before the socket turns on. Suggested start **26.6 V**. A brand-new helper starts at **24**. |
| Source stop volts | `input_number.inverter-1-charge_source_stop_v` | 24–29.5 V, step 0.05 | Not the inlet off. The off is that bank's re-bulk sensor (26.8 V when Victron float is 27.0 V). |
| Require source SoC | `input_boolean.inverter-1-charge_source_soc_enabled` | on / off | Rescue only. Off: source SoC is ignored. On: the feeding bank's SoC must also be at or above the helper below before rescue turn-on. It does not by itself turn the socket off. A brand-new helper starts **off**. |
| Source minimum SoC | `input_number.inverter-1-charge_source_min_soc` | 0–100 %, step 1 | Used only when Require source SoC is on. Suggested start **90**. A brand-new helper starts at **0**. |
| Dwell | `input_number.inverter-1-charge_dwell_s` | 15–600 s, step 15 | Rescue, surplus, pack-recovered and source-stop must hold this long before a switch. Suggested start **60 s**. A brand-new helper starts at **15**. |
| Minimum on time | `input_number.inverter-1-charge_min_on_s` | 60–1800 s, step 30 | After rescue turns a socket on, pack-recovered waits until this timer is idle. Surplus does not start this timer. Source-stop does not wait. Suggested start **300 s**. A brand-new helper starts at **60**. |
| Sungold battery voltage | `sensor.sungold-inverter-1_battery_voltage` | V | Pack voltage from the read-only sidecar. |
| Sungold SoC | `sensor.sungold-inverter-1_battery_soc` | % | The inverter's own count, for reading only. Reset it on the Sungold once the pack is full. |
| Sungold grid voltage | `sensor.sungold-inverter-1_grid_voltage` | V | Mains voltage the inverter reports. Used by the inlet alert only. |
| Sungold charging power | `sensor.sungold-inverter-1_charging_power` | W | Power into the Sungold battery. About 0 W with the socket on is the inlet alert. |
| T2 battery voltage | `sensor.battery_1_voltage` | V | T2 SmartShunt. Rescue reference and the source check when Inverter is T2. |
| KU battery voltage | `sensor.battery_2_voltage` | V | KU SmartShunt. Rescue reference and the source check when Inverter is KU. |
| T2 battery power | `sensor.battery_1_power` | W | Positive means the T2 pack is charging. Surplus on Inverter T2 compares this with Surplus min charge W. |
| KU battery power | `sensor.battery_2_power` | W | Positive means the KU pack is charging. Surplus on Inverter KU compares this with Surplus min charge W. |
| T2 battery SoC | `sensor.battery_1_state_of_charge` | % | Used only when Require source SoC is on and Inverter is T2. |
| KU battery SoC | `sensor.battery_2_state_of_charge` | % | Used only when Require source SoC is on and Inverter is KU. |

`binary_sensor.inverter-1-charge_surplus_stop` is not on the card. It is on while a
Sungold charge socket should turn off because its feeding charger is no longer
in Absorption or Float above that bank's re-bulk stop. Full Sungold volts do not
set it while that stage check is still on.

No helper here has `initial:`. Home Assistant keeps what you type across a restart.
**Load recommended starting values** does not write these numbers and does not turn
the enable switch on. Set them by hand, including Surplus min charge W at 1100.

The rescue reference is the **lower** of the two live shunt voltages. One shunt
missing: the other is the reference. Both missing: only the floor, the full helper
and the optional SoC apply.

Which socket is the inlet is only the **Use** helper
(`input_select.plug_<id>_<side>_use` = `Sungold charge`) and the **Inverter** helper
(`input_select.plug_<id>_<side>_inverter` = `T2` or `KU`). House and Sungold are
not feeding banks. A socket set to Sungold charge with Inverter Sungold is not
switched by this rule and is not shed by the voltage guard (the guard only sheds
Use = dump).

### Retired charge numbers

The target-gap and inlet-confirm numbers are not in `dump_control.yaml` and are
not in the live helper list. Full volts are the only rescue cap. The inlet alert
is a fixed 3 minutes (`00:03:00`).

## How it works in the package

- `binary_sensor.inverter-1-charge_need` is the rescue trip, with the off point taken from
  its previous state. The automations do not hard-code the volts.
- Rescue on (`dump_inverter-1-charge_on`) waits until need has been on for
  `input_number.inverter-1-charge_dwell_s`, then switches each eligible socket. It also
  runs when the feeding bank's volts or SoC change, on Home Assistant start, and
  every minute, so a need that is already on after a restart still acts.
- A rescue socket is eligible when Use is Sungold charge, Inverter is T2 or KU, the
  switch is off, manual hold is not active, that bank's volts are at or above
  `input_number.inverter-1-charge_source_min_v`, and (only if Require source SoC is on)
  that bank's SoC is at or above `input_number.inverter-1-charge_source_min_soc`.
  Rescue does **not** wait for the 10 minute cooldown.
- Rescue sends ON once per socket, then waits up to 3 minutes for the plug to report
  on. The Pi 4 bridge retries the Bluetooth link up to three times in that window.
  The rule runs in `mode: single`, so its minute poll and volts/SoC triggers are
  dropped while it waits and a new ON cannot cancel a bridge retry.
- Only a confirmed on starts that socket's min-on timer at
  `input_number.inverter-1-charge_min_on_s` and writes the `turned ON` activity line.
- No report within 3 minutes writes a `did not turn ON` line and the notification
  **Plug did not switch** (`notification_id` `plug_no_switch_<id>_<side>`). The next
  check tries again. The notification is dismissed when that socket turns on.
- A socket that is **held by you** is skipped: no command, no timer, no log line.
- Pack recovered (`dump_inverter-1-charge_off`) runs only when Sungold volts are at or
  above full. It waits until need has been off for the dwell, then until that
  socket's min-on timer is idle, then turns it off and starts the cooldown. It
  does not turn off a surplus charge that is still under full volts, and it does not
  turn the inlet off while `binary_sensor.inverter-1-charge_banks_feed` is on.
  A feeding bank under source stop volts still turns the inlet off.
- Surplus on (`dump_inverter-1-charge_surplus_on`) turns the inlet on when the feeding
  charger is in Absorption or Float and that bank's re-bulk sensor is off.
  It does not use charge watts, both-banks-at-float, or Sungold under full volts.
  The socket must be off, not on hold, not held by you, and its cooldown must be
  idle. It does not start the min-on timer. It sends ON once and waits up to 3
  minutes for the plug the same way as rescue, with the same notification.
- Surplus waits while `input_boolean.dump_control_enabled` is on and
  `sensor.dump_next_plug` still names a dump socket, so small dumps stage first.
  When the dump master is off, surplus does not wait on that sensor.
- Surplus off (`dump_inverter-1-charge_surplus_off`) turns the socket off when those bank
  checks fail, or when Sungold volts are not a number, after the dwell, once the
  min-on timer is idle. Reaching full volts is the pack-recovered rule. While
  rescue is on, this rule leaves the socket alone.
- Source stop (`dump_inverter-1-charge_source_stop`) does not wait for the minimum on
  time. It turns the socket off after that bank's re-bulk sensor has been on for
  the dwell, then starts the cooldown. That cooldown does not block a later
  Absorption or Float turn-on.
- Each automatic switch fires `dump_control_switching` first, so it does not arm
  manual hold. A hand tap (Plugs button or the plug's own button) does arm
  `timer.plug_<id>_<side>_hold` for **Dump manual hold** minutes, the same as a
  dump socket, when Inverter is T2 or KU and hold minutes are above 0.
  Turn-on always skips a hold. Turn-off skips a hold only while **Hold also blocks
  turn-offs** is on. When a hold ends, a surplus charge that still qualifies stays
  on. A hold that ends while rescue is off and the bank no longer qualifies turns
  the socket off.
- The inlet alert (`dump_inverter-1-charge_inlet_dark`) notifies once after a fixed 3
  minutes when `binary_sensor.inverter-1-charge_inlet_dark` stays on. Grid voltage that
  is present does not raise it: Sungold is waiting on its own charge settings.
  It uses `notify.persistent_notification` with notification id
  `sungold_charge_inlet_dark`, and `input_text.dump_notify_service` when that is
  a notify service name. It does not turn the socket off. When the inlet is no
  longer dark, `dump_inverter-1-charge_inlet_clear` dismisses that notification.
  Unknown sidecar values do not start it.
- Unavailable plugs are not commanded on (the switch state is not `off`). A bridge
  that is down leaves those sockets unavailable; that is a host issue, not this rule.
- The dump master switch is not required for rescue. It only delays surplus while
  a dump socket is still next.

## Voltage guard

The guard only sheds dump sockets whose Inverter is Sungold, and it still blocks
adding those dump sockets. It does not turn `binary_sensor.inverter-1-charge_need` on and
it does not turn a Sungold charge socket on. You can run the charge rule with the
guard off. You can run the guard with charge off (shed only, no inlet). A guard that is on
while the charge inlet is on is not a notification. The only guard notification
is when that inlet stayed off. See [dump-sph-vguard.md](dump-sph-vguard.md).

## Example

Set one socket's Use to **Sungold charge** and its Inverter to **T2** (the bank
that actually feeds that inlet). Leave every other socket as it is. Type the
suggested starts: floor 25.0 V, margin 0.50 V, full 26.8 V, surplus min charge
1100 W, source minimum 26.6 V, source stop 26.2 V, dwell 60 s, minimum on 300 s.
Leave both SoC switches off. Then turn **Enable Sungold charge** on.

A low Sungold pack does not turn the inlet on. With the T2 charger in Bulk at
27.0 V, the inlet stays off. When the T2 charger enters Absorption or Float and
T2 is above 26.8 V, after the dwell and after any waiting dump socket, the inlet
turns on. It stays on at full Sungold volts while that charger stays in
Absorption or Float. If T2 falls to 26.8 V, the inlet turns off without waiting
out a minimum on time. Charge watts near 0 while the charger is in Float do not
turn it off.

## Recommended first test

1. Do not enable yet. On the inlet socket only, set Use to **Sungold charge** and Inverter to the bank that feeds it (T2 or KU). Confirm **Sockets set to dump** does not count it.
2. Type the suggested starts above, including Surplus min charge W at 1100. Confirm the enable switch is still off and Status reads **disabled**.
3. On the Sungold panel, set charger source priority so mains / utility charging is allowed.
4. Turn **Enable Sungold charge** on. With the feeding charger in Bulk, the inlet stays off even if Sungold is under the floor.
5. If the socket turns on and charging power stays at or below 5 W for 3 minutes, with grid voltage at or below 0, the notification appears and the socket stays on. Unavailable sidecar values do not notify.
6. Full Sungold volts do not turn the inlet off while the feeding charger is still in Absorption or Float.
7. When that charger enters Absorption or Float and the bank is above re-bulk, after small dumps and the dwell, the socket turns on. When that bank reaches re-bulk, the socket turns off.
8. Tap the socket by hand with Dump manual hold above 0. The activity log shows a `by hand` line and the button shows a hold. With **Hold also blocks turn-offs** on, a recovery does not turn it off until the hold ends.

Sungold SoC (`sensor.sungold-inverter-1_battery_soc`) is on the Sungold tiles, this card
and the SoC graph for reading only. The SPH302480A percent is the inverter count and is
only a BMS value when program 32 is BMS, so it drifts. Reset it on the Sungold once the
pack is full. Full charge is still the voltage helpers. The only rule that reads the
percent is the optional **Sungold charge also when SoC is low**; keep that off until the
count has been reset.

A low Sungold pack, including while the Sungold AC load is on, does not turn the
inlet on. Use = normal is not a dump and is not switched. With no sun, the
existing shed still turns dump sockets off. It does not switch a Use = normal load.
