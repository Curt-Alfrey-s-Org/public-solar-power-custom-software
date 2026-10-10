# Site solar help: Socket inverter (bus)

**Where:** Site solar > Now view > **Socket inverter (bus)**.
**Logic:** YAML helpers `input_select.plug_<id>_<side>_inverter` in
`config/packages/dump_control.yaml`. Dump add and shed do **not** use this helper
to choose a socket. They use measured bus voltage, current, and watts
([template](https://www.home-assistant.io/integrations/template/),
[triggers](https://www.home-assistant.io/docs/automation/trigger/),
[state condition `for`](https://www.home-assistant.io/docs/scripts/conditions/#state-condition)).
Sungold charge still reads it as the feeding bank. **House** is still the grid skip.

## What this box is for

**House** marks a plug that is on house grid power (not on any solar bus): dump
control never switches it, even if its Use is dump. The other options (Sungold, T2,
KU) are a label for you and for the Sungold charge inlet. They are not the decider
for which dump socket turns on or off.

## The entities

| Row | Entity | Options | What it does |
|---|---|---|---|
| live name (16 rows) | `input_select.plug_<id>_<side>_inverter` | `Sungold`, `T2`, `KU`, `House` | `House` = grid-powered house plug: never switched by dump control (on or off), still switchable by you. Sungold / T2 / KU name the outlet for you and name the Sungold charge source bank. Dump add and shed follow the bus meters below, not this label. |

What each choice watches:

| Choice | Voltage | Battery | AC limit room | Confirm meter |
|---|---|---|---|---|
| T2 | `sensor.battery_1_voltage` | `sensor.battery_1_power` | T2 limit - T2 battery discharge | minus `sensor.battery_1_power` |
| KU | `sensor.battery_2_voltage` | `sensor.battery_2_power` | KU limit - KU battery discharge | minus `sensor.battery_2_power` |
| Sungold | `sensor.sungold-inverter-1_battery_voltage` | Sungold charging power (or current x voltage) | Sungold limit - Sungold AC-out | `sensor.sungold-inverter-1_load_power` |
| House | none | none | none | none: dump control skips the socket entirely |

Each row's name is live: the socket's **Load** and its plug's **Where** from
[Plug names](plug-names.md), with the plug id and side in brackets (`Heater (<ID> left)
at Bedroom`), or just `<ID> left` when Load is blank. No inverter or load is fixed in
the repo: a new select starts on the first option and you pick the real one.

No raise / lower: pick where the socket is really wired.

**Safe start:** set every dump socket to its real inverter before turning the master
switch on. A brand-new select starts on **Sungold** (the first option).

For a [Sungold charge](sph-charge.md) inlet, Inverter is the bank that **feeds**
the socket (T2 or KU), not the Sungold pack and not House. The charge rule reads
that choice for the source minimum and the source stop. Dump on/off does not.

## How it works in the package

- `sensor.dump_next_plug` offers an off dump socket when **some measured bus** is
  at/above start volts, not at/below stop volts, battery ok, and under its AC limit.
  The socket's Inverter label is not that test. Sungold is not a ready bus while
  `binary_sensor.dump_inverter-1-vguard` is on.
- `dump_turn_on` reads T2, KU, and Sungold load meters before and after. A rise on a
  bus that is still above its stop and inside its discharge limit confirms the socket.
  A rise only on a bus at or under stop, or past its discharge limit, turns that
  socket back off.
- `Dump OFF <bus> sockets: ...` rules turn off every dump socket (Use dump, not House,
  not held by you) when **that bus's** voltage or discharge says it is in trouble.
  They do not filter on the Inverter label. H5082 has no per-socket V/A/W, so HA
  cannot see which plug is on the healthy bus. A stale Sungold label must not keep
  a socket on while T2 or KU is at or under stop and carrying the watts.
- Stop-volts on T2 and KU also runs when `binary_sensor.dump_soc_hold_trips` goes
  off while that bus is still at or under stop
  ([several triggers](https://www.home-assistant.io/docs/automation/trigger/),
  [state condition `for`](https://www.home-assistant.io/docs/scripts/conditions/#state-condition)).
  A one-shot `to: on` that already fired during the SoC hold does not have to happen again.
- **House:** every socket pick in the package uses the same test, "Use is dump **and**
  Inverter is not House". So a House socket is not counted in `sensor.dump_sockets`,
  never offered by `sensor.dump_next_plug` or `sensor.dump_shed_plug`, and never in any
  turn-off list (solar gone, stop volts, battery, shed). It is never turned on **or**
  off by dump control; the Plugs buttons and the plug's own button still work.
  Changing a socket to House while dump control has it on leaves it on: turn it off
  yourself if needed. Setting its Use to normal as well keeps the rows clear.
- Use **normal** stays out of dump on/off. **Held by you** stays out.
- These selects never had `initial:`; they already kept your choice over restarts.

## Plugged in (online / offline)

One checkbox per physical plug (both sockets share it): `input_boolean.plug_<id>_online`
in `config/packages/dump_control.yaml`. On means the plug is online (plugged in).
Off means it is offline (unplugged). The name is that plug's Where label plus "online"
([input boolean](https://www.home-assistant.io/integrations/input_boolean/)).
There is no `initial:`; Home Assistant restores the last choice, and a brand-new
checkbox starts off until it is set. `input_boolean.reload` loads a new YAML
checkbox without restarting Home Assistant.

Each side still has its existing inverter select. That select is where the side
is plugged in. The options stay Sungold, T2, KU, and House. House is still the
grid skip. This does not add a second list.

A plug marked offline is out of dump on/off. The Use-is-dump and not-House guard
also requires `input_boolean.plug_<id>_online` on, so `sensor.dump_sockets`,
`sensor.dump_next_plug`, `sensor.dump_shed_plug`, and the dump turn-on and
turn-off rules skip both sockets. `binary_sensor.plug_plugs_unseen` skips them
too, so an unplugged plug is not a plug-not-seen alarm. The checkbox does not
turn the switch. After the package change, `template.reload` and
`automation.reload` load that exclusion
([template.reload](https://www.home-assistant.io/actions/template.reload/),
[automation.reload](https://www.home-assistant.io/actions/automation.reload/)).

Site solar shows the checkbox, then the left inverter select, then the right
inverter select, on one entities card titled **Plugs online and where each is plugged in**
([entities card](https://www.home-assistant.io/dashboards/entities/)).
The card sets `show_header_toggle: false` so the header button does not flip every row.


## Example

A dump socket labeled Sungold can stay on while Sungold is 26.6 V (above a 26.4 V
stop) and Sungold AC-out is about 1 W. If Battery 1 or Battery 2 is at or under its
stop and the shunt is discharging, that socket is eligible to turn off. The label
does not keep it on. Set **House** only when the plug is on grid power.

## Recommended first test

1. Use = dump on the lamp socket. The Inverter label can be wrong on purpose.
2. Sunny afternoon, a bus in float and above its stop, master switch on. The lamp
   may come on because some measured bus is ready, not because the label matches.
3. You do not type T2 or KU stop volts. When a measured bus stays at or under its
   re-bulk (Victron float minus 0.2 V) for about a minute, the lamp turns off even
   if the label names a different inverter. **Dump activity log** shows the
   stop-volts line for the bus that actually sagged.
