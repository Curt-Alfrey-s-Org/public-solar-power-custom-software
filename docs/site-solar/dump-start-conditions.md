# Site solar help: Dump start conditions

**Where:** Site solar > Now view > **Dump start conditions**.
**Logic:** `config/packages/dump_control.yaml` (`binary_sensor.dump_solar_present`,
`binary_sensor.dump_soc_ok`, `binary_sensor.dump_load_exceeds_solar`, automations
`dump_turn_on` and `dump_turn_off_solar_gone`).

## What this box is for

Site-wide gates that apply to every dump socket, whatever bus it is on:

- **Sun** (`binary_sensor.dump_solar_present`) is on when either of these is true.
  A full charger holds panel watts near zero, so watts alone are not the sun signal
  ([MPPT features](https://www.victronenergy.com/media/pg/Manual_SmartSolar_MPPT_100-30__100-50/en/features.html)).
  1. The B SmartSolar 100/50 is in Absorption or Float
     (`binary_sensor.dump_battery-1-charger_float` reads `sensor.victron-mppt-1_battery_state`).
     `binary_sensor.dump_battery-2-charger_float` is off: A has no charger.
  2. Live panel watts are at or above min solar: only
     `sensor.victron-mppt-1_solar_power`. The three BlueSolar 75/15 are unused.
     A adds 0 W. In Bulk, watts below that minimum mean the sun is weak.
  Daylight, the clock, weather, and `input_number.dump_solar_before_float_w` are not
  the signal. The remember-watts automation may still store a number. It does not decide sun.
  Below that sun signal for 1 minute, every dump socket turns off.
- **Min SoC (A or B)** is still a helper. It does not block adding dump sockets.
- **Ignore SoC** switches the SoC check off (for when the SmartShunt has not synced
  to 100 % yet and its SoC number cannot be trusted).



## SoC holds the dumps through a cloud

The lower of A and B state of charge decides whether a full pack may ride
through a cloud. SmartShunt state of charge is remaining capacity
(https://www.victronenergy.com/media/pg/SmartShunt/en/operation.html).
Voltage moves on the first cloud. SoC moves slowly. These banks are LiFePO4.

| Row | Entity | What it does |
|---|---|---|
| No trip above | `input_number.dump_soc_no_trip_percent` | Lower SoC above this (91) turns `binary_sensor.dump_soc_hold_trips` on |
| Trip again at | `input_number.dump_soc_trip_floor_percent` | Lower SoC at or below this (90) turns that sensor off |
| SoC holding dumps | `binary_sensor.dump_soc_hold_trips` | On: the cloud trips below do not run, so they do not start the 10 minute cooldown |

While the sensor is on, these offs do not run:

- A or B bus at stop volts
- A or B battery discharging past the watt limit
- Charger left absorption or float (one dump per minute)
- Sungold load above solar (one dump per minute)

Between the floor and the no-trip number, the sensor keeps its previous state.
Home Assistant exposes that previous state as `this.state`
(https://www.home-assistant.io/integrations/template/).
If the floor is not below the no-trip number, the sensor stays off.
If either SoC is missing, the lower value is the one that is present.
If both are missing, the sensor stays off.

**Ignore SoC** on: the sensor stays off. Watt and voltage rules run, because the
SmartShunt number is not trusted yet.

These offs are not held by SoC: solar gone, the Sungold voltage guard, and the
Sungold bus stop-volts and discharge rules. Min SoC still only blocks adding
a socket. It does not turn sockets off.

## Battery chemistry

These banks are LiFePO4. The SmartSolar operation chapter states the default
LiFePO4 absorption voltage is 14.2 V (28.4 V) and the float voltage is 13.5 V
(27 V), and 24 V systems use twice the 12 V figures.
https://www.victronenergy.com/media/pg/Manual_SmartSolar_MPPT_100-30__100-50/en/operation.html

The dump start and stop helpers are not those charger setpoints. This plant
does not change the charger's own settings.

## The entities

| Row | Entity | Unit / range | What it does | Raise it | Lower it |
|---|---|---|---|---|---|
| Min solar (below = solar gone) | `input_number.dump_min_solar_w` | W, 0-500, step 10 | Live SmartSolar plus paired 75/15 watts at or above this count as sun while the chargers are not in Absorption or Float. Those stages count as sun even when live watts are near 0 | A higher number treats a weak Bulk sun as gone sooner | **never 0** (0 W >= 0 is always true while the sensors are numbers) |
| Min SoC (A or B) to add sockets | `input_number.dump_min_soc_percent` | %, 80-100, step 1 | `binary_sensor.dump_soc_ok` is on while A or B state of charge is at least this (only when Ignore SoC is off) | Fewer dump starts (battery must be fuller) | More dump starts at a lower SoC |
| Ignore SoC (shunt not synced) | `input_boolean.dump_soc_unsynced` | on / off | On: `dump_soc_ok` is always on (SoC not checked). Off: SoC must be >= Min SoC (A or B) | - | - |

**Safe starting values:** min solar 50 W, min SoC 90 %, Ignore SoC **on** until the
A SmartShunt has done a full charge and synced to 100 %, then **off**. The
**Load recommended starting values** button leaves Ignore SoC as it is, so it
cannot switch off the SoC hold.

## How it works in the package

- `Dump ON: add dump sockets while the charger is in float` (`dump_turn_on`) needs
  `dump_charge_float` on for 1 minute (A or B in Absorption or Float) and
  `dump_solar_present` on for 1 minute. It does not require `dump_soc_ok`.
  `sensor.dump_next_plug` returns `none` while solar present is off. It does not
  return `none` because SoC is under the minimum. Sungold voltage does not set
  `dump_charge_float`.
- `Dump OFF all: solar gone for 1 minute` (`dump_turn_off_solar_gone`) fires when
  `dump_solar_present` has been off for 1 minute: every dump socket that is not
  already off is turned off, its min-on cancelled, its cooldown started.
- Min solar is also part of `binary_sensor.dump_load_exceeds_solar`: that alarm is
  only on while A PV + Sungold PV is at least min solar (so it stays quiet at night).
- Only the **A** SoC (`sensor.battery_1_state_of_charge`) is checked, for every
  socket, including B and Sungold ones.
- SoC below the minimum only stops **adding**. It does not turn sockets off; the
  voltage and battery rules do that.
- Before 2026-09-28 `Ignore SoC` was forced **on** at every restart and both numbers
  went back to 50 / 95. They now keep your setting. On a brand-new install Ignore SoC
  starts **off** (SoC checked) until you press **Load recommended starting values**.

## Example

Min solar 50 W. In Bulk with live panel watts under 50 W, solar present is off.
When a charger enters Absorption or Float, solar present stays on even if live
watts fall toward 0. Bulk with live watts at or above 50 W is sun. When both
chargers leave Absorption and Float and live watts stay under 50 W for a minute,
every dump socket turns off.

## Recommended first test

1. Keep the lamp test socket from [Socket Use](socket-use.md) on while dumping.
2. Late afternoon, set **Min solar** a little above the present A PV (see
   **Dump status > A PV now**). After about a minute the lamp turns off with the
   "solar gone" line in the activity log.
3. Put **Min solar** back to 50 W.
4. With Ignore SoC **off**, raising Min SoC turns **SoC ok** off. That does not stop a new socket. The add waits for Absorption or Float.

While that bus's Victron is in Absorption or Float, folded panel watts are not "no sun":

- The next dump socket is still offered when the shunt is only a few watts negative against a 0 W discharge limit.
- A plug that reports on is kept on even if the bus load has not risen by the confirm watts. The charger does not produce those watts until the load is there. Bulk still needs the rise.
- "Load above solar" and "battery discharging past limit" do not shed that bus while it stays in Absorption or Float. They resume when the charger leaves those stages.
The add stops after that one socket while the charger is still in Absorption or Float, so a folded afternoon does not open every dump at once.

## Adding while the charger is in float

Live charger watts can fall to a few tens of watts in float because no dump is
pulling. That is not "no sun". While the dump master is on and that bus charger
is in Absorption or Float, above its re-bulk stop, HA adds one dump at a time.
Voltage at the start helper during Bulk does not add a dump. The shunt does not
have to be charging before the first dump.

A dump is shed when that bus voltage falls to its re-bulk stop (float minus 0.2 V,
26.8 V when float is 27.0 V), and the stop check runs again every minute while
that sensor stays on
([time pattern](https://www.home-assistant.io/docs/automation/trigger/#time-pattern-trigger)).
Sun gone is both chargers out of Absorption and Float with live panel watts under
min solar. A socket with held-by-you on is skipped. Live PV near 0 does not shed
a dump while the charger is still in Absorption or Float.
The first plug that reports on is kept on without waiting for a 25 W shunt rise, so the folded charger can produce watts again. The add then stops until that charger leaves float.

## A switch on is not a load

No H5082 socket has its own watt sensor. A dump counts as taking solar only when
a measured watt change follows the turn-on.

A uses `sensor.battery_1_power` (bus load is that shunt with the sign flipped).
B uses `sensor.battery_2_power` the same way. A Sungold-inverter dump uses
`sensor.sungold-inverter-1_load_power` or
`sensor.sungold-inverter-1_charging_power`. A real load makes the A or B shunt
more negative, or solar watts rise while the shunt holds. There is no watt floor.

If the switch is on and those numbers do not move, the socket is empty. HA leaves
it on and may add the next dump while sun is present and the bus is still at or
above the start helper. One socket is tried at a time. The add stops when a
measured load appears. Held-by-you, the Sungold voltage guard, cooldown, and the
manual hold timer still skip a socket. A low live PV reading does not shed while
the sun signal is on.
