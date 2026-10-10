# Site solar help: Battery discharge limits

**Where:** Site solar > Now view > **Battery discharge limits**.
**Logic:** `config/packages/dump_control.yaml`, binary sensors `dump_batt_battery-2-ok` /
`dump_batt_battery-1-ok` / `dump_batt_inverter-1-ok`, automations `dump_turn_off_batt_t2` / `_ku`
/ `_sph`.

## What this box is for

Dump loads should only use **spare solar**, never the battery. This box says how
much battery discharge HA tolerates on each bus before it calls that battery
"not ok": then that bus is not a place to add a dump, and after 1 minute dump
sockets turn off. The Inverter label does not choose which sockets. H5082 has no
per-socket watts.

## The entities

| Row | Entity | Unit / range | Battery meter | Raise it | Lower it |
|---|---|---|---|---|---|
| T2 max battery discharge | `input_number.dump_max_discharge_battery-2-w` | W, 0-500, step 10 | `sensor.battery_1_power` (SmartShunt, + charge / - discharge) | Tolerate more drain before shutting T2 dumps off | Shut off at the first sign of discharge |
| KU max battery discharge | `input_number.dump_max_discharge_battery-1-w` | W, 0-500 | `sensor.battery_2_power` | as T2 | as T2 |
| Sungold max battery discharge | `input_number.dump_max_discharge_inverter-1-w` | W, 0-500 | `sensor.sungold-inverter-1_charging_power`, or battery current x voltage when that is missing | as T2 | as T2 |

"Battery ok" = battery power >= minus the limit. With 0 W, any discharge at all
counts. With 50 W, up to 50 W of discharge is tolerated.

**Safe starting values:** T2 0 W, KU 0 W, Sungold 50 W. If dump sockets keep turning
off on tiny readings (-5 W, -12 W) while the sun is strong, raise that bus to 20-50 W.

## How it works in the package

- `sensor.dump_next_plug` offers a dump socket when some measured bus battery is ok
  (and the other start gates pass). The socket's Inverter label is not that test.
- `Dump OFF <bus> sockets: <bus> battery discharging past limit` fires when
  `dump_batt_<bus>_ok` has been off for 1 minute and the master switch is on: every
  dump socket that is not already off is turned off (even during min-on), not only
  sockets labeled with that bus. Min-on is cancelled and the cooldown started.
  T2 and KU also run when SoC hold turns off while the battery is still not ok
  ([state condition](https://www.home-assistant.io/docs/scripts/conditions/#state-condition)).
- If the battery meter is unavailable (shunt out of range, Sungold offline) the
  battery counts as **not ok**, so the same turn-off happens after 1 minute. That is
  deliberate: no meter, no dumping.
- Before 2026-09-28 the limits went back to 0 / 0 / 50 at every HA restart. They now
  keep your value.

## Example

KU limit 0 W. Clouds come over; `sensor.battery_2_power` reads -140 W for a minute
(the KU inverter is now pulling from the pack). `KU battery within discharge limit`
goes off, and a minute later dump sockets turn off (including one labeled Sungold) with
`turned OFF by "Dump OFF KU sockets: KU battery discharging past limit": KU battery
power -140 W is past the -0 W limit for 1 min`.

## Recommended first test

1. With a lamp on a T2 dump socket that HA has turned on, look at **Batt 1 W** on the
   Now view.
2. If it is charging (positive), nothing happens. Turn on a normal load on the T2
   inverter big enough to make Batt 1 W negative for over a minute.
3. The lamp turns off with the battery line in **Dump activity log**.
4. Turn the extra load off. The lamp can come back after its 10 minute cooldown.

When a Victron on that bus is in absorption or float and Ecobee weather `weather.hygrometer-1` is sunny, partly cloudy, cloudy, or windy, a shunt that is only a few watts negative does not hide the next dump socket. The charger has folded its output because the battery is full. The discharge limit still turns a dump off if that bus stays past the limit after the socket is on.

While `binary_sensor.dump_soc_hold_trips` is on, the T2 and KU discharge offs
do not run. That sensor is on when the lower of T2 and KU state of charge is
above the no-trip helper (91) and Ignore SoC is off. It turns off again at the
trip floor (90). See [Dump start conditions](dump-start-conditions.md).
