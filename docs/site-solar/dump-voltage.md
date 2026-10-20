# Site solar help: Dump voltage (start / stop)

**Where:** Site solar (`/site-solar`) > Now view > **Dump voltage (start / stop)**.
**Logic:** `config/packages/dump_control.yaml` (binary sensors `dump_v_float_*`,
`dump_v_rebulk_*`, sensor `dump_next_plug`, automations `dump_turn_off_rebulk_*`).

## What this box is for

Each battery bus (A, B, Sungold cart) has two voltages:

- **Start volts (float):** a bus at or above this can accept another dump socket.
  It means "the battery is full and the charger is only holding it there".
  Which socket is offered does not come from the Inverter label.
- **Stop volts (re-bulk):** if the bus falls to or below this for 1 minute, HA turns
  off dump sockets (Use dump, not House, not held by you). It means "this measured
  bus is low". The Inverter label does not pick which sockets those are. H5082 has
  no per-socket voltage, so HA cannot leave a socket on just because its label names
  a bus that is still above stop.

Between the two (below start, above stop) that bus is not a reason to add, and it
is not a reason to turn sockets off. Another bus that is at or under its own stop
still is.

## The entities

| Row | Entity | Unit / range | What it does | Raise it | Lower it |
|---|---|---|---|---|---|
| A start volts (float) | `input_number.dump_float_battery-2-v` | V, 26.0-29.5, step 0.05 | HA writes this from the Victron float. `binary_sensor.dump_v_float_t2` is on while `sensor.battery_1_voltage` >= this. Not a box you fill. | Dumping on A starts later / less often (the bus must be higher) | Starts sooner; too low and it can start before the pack is really full |
| A stop volts (re-bulk) | `input_number.dump_rebulk_battery-2-v` | V, 25.5-29.0, step 0.05 | HA writes this as Victron float minus 0.2 V. `binary_sensor.dump_v_rebulk_t2` is on while `sensor.battery_1_voltage` <= this; on for 1 min turns dump sockets off (not only sockets labeled A). Not a box you fill. | Dumps shut off sooner, at a higher voltage (safer for the pack) | Dumps stay on longer while the voltage sags |
| B start volts (float) | `input_number.dump_float_battery-1-v` | V, 26.0-29.5 | HA writes this from the same Victron float, on `sensor.battery_2_voltage`. Not a box you fill. | as A | as A |
| B stop volts (re-bulk) | `input_number.dump_rebulk_battery-1-v` | V, 25.5-29.0 | HA writes this as Victron float minus 0.2 V, on `sensor.battery_2_voltage`. Not a box you fill. | as A | as A |
| Sungold start volts (float) | `input_number.dump_float_inverter-1-v` | V, 26.0-29.5 | You type this. It is not copied from the Sungold floating-charge box. `sensor.sungold-inverter-1_battery_voltage` | as A | as A |
| Sungold stop volts (re-bulk) | `input_number.dump_rebulk_inverter-1-v` | V, 25.5-29.0 | You type this. No Sungold stop formula is documented here, so HA does not apply the Victron 0.2 V offset. `sensor.sungold-inverter-1_battery_voltage` | as A | as A |
| Boost charge voltage (constant-voltage charge) | `input_number.inverter-1-boost_charge_v` | V, 20-32, step 0.1, box | You type the SPH302480A boost / constant-voltage charge setpoint (parameter 09, and the LF08 constant-voltage charge voltage). The inverter does not report it. Start 28.4 V is the manual LF08 column only. | Record only. Does not start or stop dumps. | Record only |
| Floating charge voltage | `input_number.inverter-1-floating_charge_v` | V, 20-32, step 0.1, box | You type the floating charge setpoint (section 4.3). Start 28.4 V is LF08 only. | Record only | Record only |
| Low voltage disconnection voltage | `input_number.inverter-1-low_voltage_disconnect_v` | V, 20-32, step 0.1, box | You type the low voltage disconnection voltage (04 fault). Start 24.4 V is LF08 only. | Record only | Record only |
| Low voltage disconnection voltage recovery point | `input_number.inverter-1-low_voltage_disconnect_recovery_v` | V, 20-32, step 0.1, box | You type setup item 35. Start 27.2 V is LF08 only. | Record only | Record only |
| Battery fully charged recovery point | `input_number.inverter-1-charge_full_v` | existing Sungold charge helper | Setup item 37. Same helper as Sungold charge full volts. No second full-volts helper. The LF08 column is 26.8 V. This change does not write that helper. | Record only on this card. The Sungold charge card still uses it as full volts. | same |



## What you type vs what HA sets

### Victron chargers (one preset for both)

You type two boxes on **Victron chargers**. You do not type A and B separately.

| Box | Entity | What HA does with it |
|---|---|---|
| Absorption (V) | `input_number.victron_absorption_v` | Stored so HA knows the absorption voltage. It does not change start or stop. The 24 V LiFePO4 configuration value is 28.4 V. https://www.victronenergy.com/media/pg/Manual_SmartSolar_MPPT_100-30__100-50/en/configuration-and-settings.html |
| Float (V) | `input_number.victron_float_v` | The float you set in VictronConnect. The 24 V LiFePO4 configuration value is 27.0 V. Start equals this float. Start does not equal absorption. Same manual page. |

When that float changes, and again when Home Assistant starts, automation `victron_float_writes_battery-2-battery-1-dump_volts` calls `input_number.set_value` ([input number](https://www.home-assistant.io/integrations/input_number/), [actions](https://www.home-assistant.io/docs/scripts/service-calls/), [start](https://www.home-assistant.io/triggers/homeassistant/), [modes](https://www.home-assistant.io/docs/automation/modes/)):

| HA writes | Formula |
|---|---|
| `input_number.dump_float_battery-2-v` | Victron float |
| `input_number.dump_float_battery-1-v` | Victron float |
| `input_number.dump_rebulk_battery-2-v` | Victron float minus 0.2 V |
| `input_number.dump_rebulk_battery-1-v` | Victron float minus 0.2 V |

Re-bulk is the operation-chapter restart of the charge cycle: "Vbat (Vfloat - 0.1 V) for LiFePO4 batteries, during 1 minute. These values are for 12 V batteries, multiply by two for 24V." For 24 V the offset is 0.2 V. https://www.victronenergy.com/media/pg/Manual_SmartSolar_MPPT_100-30__100-50/en/operation.html

The card shows that re-bulk as a read-only line. A and B start and stop are not boxes.

### Sungold

You still type the SPH302480A boxes on **Sungold settings you enter** (boost / constant-voltage, floating charge, low voltage disconnection, low voltage disconnection recovery, and the existing full-volts helper). The floating-charge row is record only and does not start or stop dumps, so HA does not copy it onto `input_number.dump_float_inverter-1-v`. That start box stays one you type.

`input_number.dump_rebulk_inverter-1-v` stays its own box. This page does not give a Sungold stop formula, and the Victron 0.2 V offset is not applied to Sungold. Manual: https://www.solaris-shop.com/content/3000W_SPH302480A_20231128.pdf

`input_number.inverter-1-charge_full_v` is already the battery fully charged recovery point (setup item 37) and the Sungold charge full-volts helper. There is no second helper. This automation does not write it.

Min solar, min SoC, guard margin, guard hysteresis, charge floor, charge margin, source minimum, and source stop stay boxes you type. They are not charger presets.

**Safe starting values:** 27.0 V start and 26.8 V stop on every bus. 27.0 V is the
Victron LiFePO4 24 V float default; 26.8 V is Victron's re-bulk offset (float minus
0.1 V per 12 V, doubled on 24 V). For A and B, type the Victron **Float (V)** box. HA sets start to that
float and stop 0.2 V lower. Do not type A and B separately. The **Load recommended
starting values** button in **Dump master switch** sets Absorption to 28.4 V and Float to 27.0 V, and writes 27.0 / 26.8 on the dump start and stop helpers, including Sungold. Pressing that button is what replaces a stored Sungold 26.6 / 26.4. The Victron float automation then keeps A and B on that float. It does not write Sungold start or stop, and it does not run by itself.

**Operator 2026-10-08:** both Victron chargers are set to absorption 28.4 V, float 27.0 V, and re-bulk 26.8 V. A is the SmartSolar 100/50. B is the BlueSolar 75/15. That is the configuration-chapter LiFePO4 preset (24 V absorption 28.4 V, float 27.0 V; re-bulk is float minus 0.2 V). Source: https://www.victronenergy.com/media/pg/Manual_SmartSolar_MPPT_100-30__100-50/en/configuration-and-settings.html

A and B dump start/stop helpers follow that float and re-bulk (27.0 V start, 26.8 V stop). Sungold dump start/stop (`input_number.dump_float_inverter-1-v` / `dump_rebulk_inverter-1-v`) are not those charger setpoints and stay at the stored values (26.6 V start and 26.4 V stop unless you change those boxes). Sungold dump start (`input_number.dump_float_inverter-1-v`) is not copied from the floating-charge box. Sungold dump stop (`input_number.dump_rebulk_inverter-1-v`) stays its own box: this page has no Sungold stop formula, and Victron's 0.2 V offset is not applied to Sungold.

Sungold charge setpoints are entered on this same Site solar area, card **Sungold settings you enter (the inverter does not report them)**, because Modbus does not expose them. Starting numbers are the SPH302480A manual LF08 column only: boost / constant-voltage charge 28.4 V, floating charge 28.4 V, low voltage disconnection 24.4 V, low voltage disconnection recovery (setup item 35) 27.2 V. Fully charged recovery (setup item 37) reuses `input_number.inverter-1-charge_full_v`. Manual: https://www.solaris-shop.com/content/3000W_SPH302480A_20231128.pdf

**Rule:** keep stop at least 0.2 V **below** start. If stop is at or above start, a
bus can be "at start" and "at stop" at the same time: `sensor.dump_next_plug` never
picks it and the stop rule turns it off again.

## How it works in the package

1. `sensor.dump_next_plug` offers a dump socket when that bus charger is in
   Absorption or Float, `dump_v_float_<bus>` is **on**, and `dump_v_rebulk_<bus>`
   is **off**. Voltage at the start helper during Bulk does not offer a socket.
   Sungold is not an add bus. The socket's Inverter label is not that test.
2. The site-wide start needs `binary_sensor.dump_charge_float` on for 1 minute.
   That sensor is A or B in Absorption or Float. Sungold voltage does not set it.
3. `Dump OFF <bus> sockets: <bus> bus at stop volts (re-bulk)` (ids
   `dump_turn_off_rebulk_t2` / `_ku` / `_sph`) requires `dump_v_rebulk_<bus>` on
   for 1 minute and the master switch on. A and B also run on Home Assistant
   start and every minute, so a stop that is already true is checked again
   ([time pattern](https://www.home-assistant.io/docs/automation/trigger/#time-pattern-trigger),
   [start](https://www.home-assistant.io/docs/automation/trigger/#home-assistant-trigger)).
   It turns off every dump socket that is not already off (even during min-on),
   not only sockets labeled with that bus, cancels min-on and starts the 10 minute
   cooldown. A and B also fire when SoC hold (`binary_sensor.dump_soc_hold_trips`)
   turns off while stop volts are still on
   ([state condition](https://www.home-assistant.io/docs/scripts/conditions/#state-condition)).
4. If a voltage sensor is unavailable, both binary sensors for that bus are off:
   that bus is not a start bus and its stop rule does not fire (the battery rule in
   [Battery discharge limits](dump-battery-limits.md) still can).

Before 2026-09-28 these six numbers had `initial:` in the package and went back to
27.0 / 26.8 at every HA restart. Sungold start and stop still keep the value you type.
A and B start and stop are written again from the Victron float box when Home
Assistant starts, so they match that box.

## Example

A charger float is set to 27.0 V. At 13:00 the A MPPT stage is Float and the shunt
reads 27.02 V, so `dump_v_float_t2` is on and HA may add a dump socket even if
its Inverter label says Sungold. The same voltage during Bulk does not add a socket. The heater draws more than the spare PV, the bus
sags, and at 26.78 V `dump_v_rebulk_t2` turns on. One minute later dump sockets turn
off and the activity log says `Dump control turned OFF by "Dump OFF A sockets: A
bus at stop volts (re-bulk)": A bus 26.78 V at or below stop volts 26.8 V for 1 min`.
A socket labeled Sungold is included. Sungold still being above its own stop does
not keep it on, because the plug has no voltage sensor of its own.

If that happens several times a day, change **Float (V)**. A and B stop follow
0.2 V below that float, and start moves with it. The 10 minute cooldown still
keeps it from flapping.

## Recommended first test

1. One socket with a lamp: **Use** = dump. Leave **Inverter** as whatever it already is.
2. Sunny afternoon, A charger in float, master switch on. Watch **Dump status**:
   `A at/above start volts` should be on and the lamp should come on.
3. With **Float (V)** at 27.0 the read-only re-bulk line shows 26.8 V. You do not
   type A or B start or stop. When the A bus stays at or under that re-bulk for
   1 minute the lamp turns off and **Dump activity log** shows the stop-volts line,
   including when the socket's Inverter label is not A.
4. Leave **Float (V)** at 27.0. The lamp stays off for its 10 minute
   cooldown (see [Dump timers](dump-timers.md)), then may come back on.
