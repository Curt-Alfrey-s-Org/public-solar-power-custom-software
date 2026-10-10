# Site solar help: Dump status (why / why not)

**Where:** Site solar > Now view > **Dump status (why / why not)**.
**Logic:** `config/packages/dump_control.yaml`, `template:` and `binary_sensor:`
blocks, automation `dump_turn_on`.

## What this box is for

Read-only. Every condition the dump rules check, in one place, so "why isn't it
dumping?" has an answer. Nothing here is a setting; the settings are the other boxes.

## Do this (un-hold)

The top of **Now** is a [conditional card](https://www.home-assistant.io/dashboards/conditional/)
titled **Do this**. It is the first card in the first section, above the attention tiles and Power flow.
Inside it is a [Markdown card](https://www.home-assistant.io/dashboards/markdown/)
([sections view](https://www.home-assistant.io/dashboards/sections/)).

The card names a dump socket only when that socket is why `sensor.dump_next_plug`
is `none` and clearing **held by you** would make the socket eligible for
`dump_next_plug`. The row is the plug Where plus left or right, and the action
is **un-hold** (Automate, which turns off
`input_boolean.plug_<id>_<side>_held_by_you`).

`binary_sensor.dump_unhold_for_next` is on only then. Attribute `actions` is the
table. The conditional card is shown when that sensor is **on**, and hidden
when the list is empty. There is no "nothing to do" row.

It does not list gates Home Assistant already handles: PV falling, site SoC,
absorption / float. The Sungold voltage guard only removes Sungold from the
ready buses. Another ready bus can still make the socket eligible after un-hold. A House socket is never listed. The
master switch, site solar, site SoC, charger stage, PV falling, and Sungold
load must already allow `dump_turn_on`; otherwise un-hold would not let Home
Assistant turn the socket on.


## Attention tiles

A blocker that is **Yes** (that sensor is on) shows a tile at the top of
Site solar, on the **Now** view, under **Do this** and above Power flow
([sections](https://www.home-assistant.io/dashboards/sections/)).
Each blocker is its own
[tile card](https://www.home-assistant.io/dashboards/tile/) inside a
[conditional card](https://www.home-assistant.io/dashboards/conditional/),
so the tile is hidden when that sensor is off. A **No** row has no tile.

Core dashboard docs have no flash, pulse, or blink for a card. A search of
the dashboards index for those words does not turn up a card option.
The tile uses the official color `amber` from the tile card color list
(https://www.home-assistant.io/dashboards/tile/). Home Assistant 2026.7.3
pulses a tile icon only for an alarm panel that is pending, arming, or
triggered, and for a jammed lock. That behavior is built into those
domains. It is not a setting these dump sensors can use.

| Tile | Sensor | Shown while |
|---|---|---|
| Un-hold next socket | `binary_sensor.dump_unhold_for_next` | on (a held-by-you dump socket is why the next socket is none) |
| PV falling | `binary_sensor.dump_status_pv_falling` | on (Blocking dumps? **Yes**) |
| Sungold load | `binary_sensor.dump_load_exceeds_solar` | on (Blocking dumps? **Yes**) |
| Sungold guard | `binary_sensor.dump_inverter-1-vguard` | on (Blocking dumps? **Yes**) |

The **Blocking dumps?** Markdown card stays. These tiles do not use device
class `problem`.

Bulk on the Victron chargers is normal operation and is shown on the charger cards (100/50 charge and Paired 75/15 charge). It is not an alarm tile. Site solar does not show Victron stage shed as a warning, a Yes/No blocker, or an escalation.

**Plugs seen** says **Yes** when every plug marked online is being heard. **No** names any online plug whose switch is `unavailable` or `unknown`. Plugs marked offline (`input_boolean.plug_<id>_online` off) are not counted. `binary_sensor.plug_plugs_unseen` stays device class `problem`. There is no Plug not seen row.

## The entities

Each **binary** row shows **On** or **Off**. **On** means that row's condition is true.
The three blocker rows (PV falling, Sungold load, Sungold guard)
are in their own card, **Blocking dumps?**, and read **Yes** (holding back dump
sockets now) or **No**. The entities card cannot relabel a state
(https://www.home-assistant.io/dashboards/entities/), so that card is a Markdown card
with a template (https://www.home-assistant.io/dashboards/markdown/). Yes is the same
as that sensor being on; Unknown or Unavailable shows as is.
These rows do not use device class `problem`. That class means a fault was detected
(https://www.home-assistant.io/integrations/binary_sensor/#device-class) and is not
used for dump gates. Numeric rows (PV watts, jumper) are unchanged.

The card uses the same on/off sensors the automations use. **On** means that row's condition is true.

| Row (dashboard) | Entity | On means | Set by |
|---|---|---|---|
| Sockets set to dump | `sensor.dump_sockets` | (numeric) | [Socket Use](socket-use.md) |
| Next socket HA would add | `sensor.dump_next_plug` | (text) | all gates below |
| Next socket HA would shed | `sensor.dump_shed_plug` | (text) | Socket Use + plug state |
| Site charger stage | `binary_sensor.dump_charge_float` | A Victron is in absorption or float, or Sungold is at start volts | chargers + Sungold volts |
| Site solar | `binary_sensor.dump_solar_present` | Daylight, a daytime sky, and watts saved from before float are all at least the sun rule | [Dump start conditions](dump-start-conditions.md) |
| Site SoC | `binary_sensor.dump_soc_ok` | Ignore SoC is on, or T2 or KU SoC is at least the minimum | [Dump start conditions](dump-start-conditions.md) |
| T2 PV now | `sensor.battery-2-pv_now` | 0 W. No T2 MPPT tonight | template |
| KU PV now | `sensor.battery-1-pv_now` | SmartSolar 100/50 solar W plus the paired 75/15 | template |
| PV falling | `binary_sensor.dump_status_pv_falling` | Surplus is falling by more than 5 W/min, solar is present, and T2 and KU are not both already in absorption or float | template on `sensor.dump_surplus_derivative` |
| Sungold load | `binary_sensor.dump_load_exceeds_solar` | Load is above solar or the shunt reserve | loads + shunts |
| Sungold guard | `binary_sensor.dump_inverter-1-vguard` | Holding Sungold dump adds | [Sungold voltage guard](dump-sph-vguard.md) |
| Victron stage shed | `binary_sensor.dump_status_victron_stage_shed` | No Victron is in absorption or float | `dump_charge_ok` |
| T2 stage | `binary_sensor.dump_battery-2-charger_float` | The 100/50 charge state is absorption or float. That charger is on KU; this row was not retargeted | charger |
| T2 start volts | `binary_sensor.dump_v_float_t2` | T2 is at or above start volts | [Dump voltage](dump-voltage.md) |
| T2 stop volts | `binary_sensor.dump_v_rebulk_t2` | T2 is at or below stop volts | [Dump voltage](dump-voltage.md) |
| T2 battery | `binary_sensor.dump_batt_battery-2-ok` | T2 discharge is within its limit | [Battery discharge limits](dump-battery-limits.md) |
| KU stage | `binary_sensor.dump_battery-1-charger_float` | KU 75/15 is in absorption or float | charger |
| KU start volts | `binary_sensor.dump_v_float_ku` | KU is at or above start volts | [Dump voltage](dump-voltage.md) |
| KU stop volts | `binary_sensor.dump_v_rebulk_ku` | KU is at or below stop volts | [Dump voltage](dump-voltage.md) |
| KU battery | `binary_sensor.dump_batt_battery-1-ok` | KU discharge is within its limit | [Battery discharge limits](dump-battery-limits.md) |
| Sungold start volts | `binary_sensor.dump_v_float_sph` | Sungold is at or above start volts | [Dump voltage](dump-voltage.md) |
| Sungold stop volts | `binary_sensor.dump_v_rebulk_sph` | Sungold is at or below stop volts | [Dump voltage](dump-voltage.md) |
| Sungold battery | `binary_sensor.dump_batt_inverter-1-ok` | Sungold discharge is within its limit | [Battery discharge limits](dump-battery-limits.md) |

## PV falling

The **Blocking dumps?** row is **Yes** only when all three are true:

1. `sensor.dump_surplus_derivative` (derivative of `sensor.dump_surplus_w`, 15 minute window, W/min) is below **-5**. At or above -5, including a flat surplus near 0, the row is **No**. -5 is a noise band. The template does not remember the previous state.
2. `binary_sensor.dump_solar_present` is on. That sensor is already sun elevation (daylight) and a daytime sky (`sunny`, `partlycloudy`, `cloudy`, `windy`, `windy-variant`) plus watts saved from before float. See [Dump start conditions](dump-start-conditions.md). When the sun is down or the sky is not a daytime condition, solar-present fails and dumps shed. This row is not a second night check.
3. T2 and KU are not both already in absorption or float (`binary_sensor.dump_battery-2-charger_float` and `binary_sensor.dump_battery-1-charger_float`). When both are, the chargers are holding full banks. Surplus can fall or sit near 0 because there is nowhere for the watts to go. Adding load would change what solar looks like. That is not solar leaving, so the row stays **No**.

While both banks are in absorption or float, a negative derivative stays **No**: there is nowhere for the watts to go. While the banks are not both full, the row is **Yes** only for as long as the derivative stays below -5, then **No** as soon as it recovers. It does not keep the afternoon's earlier **Yes**. A missing derivative does not block.

`dump_turn_on` requires this sensor **off**. It does not also bypass the row when only one bank is in absorption or float.

This is a [template binary sensor](https://www.home-assistant.io/integrations/template/#binary-sensor). It is not the [threshold](https://www.home-assistant.io/integrations/threshold/) helper. With only a lower limit, that helper turns on when the source is below (lower - hysteresis) and turns off only when the source rises above (lower + hysteresis). Anything in between keeps the last state, so a full-bank surplus that never climbs above +5 W/min stays **on** all afternoon. The derivative itself is the [derivative](https://www.home-assistant.io/integrations/derivative/) integration. Daylight is the [sun](https://www.home-assistant.io/integrations/sun/) elevation; the sky list is the [weather](https://www.home-assistant.io/integrations/weather/) entity already used by solar-present.

## How it works in the package

HA **adds** a socket (`dump_turn_on`) only when all of these hold:

- master switch on; a Victron in **absorption or float** (not bulk) or Sungold at start volts for 1 min; solar present for 1 min; SoC ok;
- PV falling **off** (rule above); Sungold load above solar **off**;
- `sensor.dump_next_plug` names a socket. It picks, in the order plug-1 left, plug-1
  right, plug-2 left ... plug-8 right, the first socket that has Use = dump (and Inverter not House), is **off**, is not on manual hold,
  has an idle cooldown (or [Skip cooldown once](dump-on-demand.md) is on), is not a Sungold
  socket while `binary_sensor.dump_inverter-1-vguard` is on, and whose Inverter bus is at/above
  start volts, not at/below stop volts, battery ok, and under its AC limit.
  A T2 socket also needs the 100/50 in absorption or float, T2 PV >= min solar, and
  T2 shunt net charge W > (estimated plug W + Min solar). A KU socket needs the 75/15
  in absorption or float, KU PV >= min solar, and KU shunt net charge W > (estimated
  plug W + Min solar). A Sungold-inverter socket needs Sungold PV >= min solar, start/stop
  volts, and **T2** shunt headroom (shore loads on Inverter T2 draw from the T2 bank).
  Plug W is the larger of **Dump confirm min load rise** and any digits in the socket
  Load text. No add while the feeding shunt is discharging or not charging above that reserve.

HA **removes** sockets when: solar present off 1 min (all), T2 absorption/float off
1 min (one per minute), Sungold load above solar 1 min (one per minute), a bus at stop
volts 1 min or its battery not ok 1 min (all on that bus), or the Sungold voltage guard
has been on for its dwell (Sungold sockets only).

## Example

Nothing is dumping at noon. The **T2 stage** row is red (alert): the charger is
still in **bulk**, so dump waits (no early bulk add). Nothing is wrong; wait for absorption.
Another day **Next socket HA would add** is `none` while whole-site rows are green:
look at the bus rows; **KU start volts** is red, so the only dump socket (on
KU) is not offered.

## Recommended first test

Open this box next to **Plugs** on a sunny afternoon and walk down the list: each
off row names the box to look at. Confirm `Sockets set to dump` equals the number of
sockets you set to dump.

Silent KU 75/15 (no BLE dongle) is max(0, Battery 2 W - paired 75/15 charge W + jumper W). Signed jumper W is Battery 1 W - SmartSolar battery W + measured Sungold charging_power (+ into T2). An unmetered T2 dump plug is not given the 25 W minimum in this balance. `Silent 75/15 size check` is SmartSolar PV / 3 and is not the measurement. Dump sockets are added only while that bus charger is in **absorption or float** (not bulk), with start volts, solar, SoC, and shunt headroom so the pack keeps net charge. HA does not write the MPPT.

## Plugs seen

The **Plugs seen** card says **Yes** when every watched plug is `on` or `off`, and
**No** when one is not, naming each plug that is `unavailable` or `unknown`.
The entities card cannot relabel a state
(https://www.home-assistant.io/dashboards/entities/), so this card is Markdown
(https://www.home-assistant.io/dashboards/markdown/).
`binary_sensor.plug_plugs_unseen` still uses device class `problem` so the
notification below still fires. That sensor is not a row on the card.

A plug counts as not seen only when its state is `unavailable` or `unknown`
(https://www.home-assistant.io/docs/configuration/state_object/). The attribute
`entity_ids` lists those switches. The popup uses that list.

Automation `plug_plugs_unseen_notify` calls `persistent_notification.create`
with `notification_id: plug_plugs_unseen` when the sensor turns on, and
`persistent_notification.dismiss` with that same id when it turns off
(https://www.home-assistant.io/integrations/persistent_notification/). The same
id replaces the previous popup. There is no minute timer.

The Pi 4 bridge polls every 10 s (`govee_h5082/__main__.py`). Home Assistant
`last_updated` does not move while a switch stays `on` or `off`, so a frozen
on/off state is not marked Problem. Only `unavailable` and `unknown` are.

Sungold grid voltage at 0 V while the inlet switch reads on is not this fault.
Dump gates, charge need, inlet dark, the voltage guard, and re-bulk stay On/Off.
