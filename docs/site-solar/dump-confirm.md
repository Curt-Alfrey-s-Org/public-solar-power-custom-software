# Site solar help: Dump confirm (wait / load rise)

**Where:** Site solar > Now view > **Dump confirm (wait / load rise)**.
**Logic:** `config/packages/dump_control.yaml`, automation `dump_turn_on`
(`Dump ON: add dump sockets while the charger is in float`), template sensors
`dump_bus_load_t2` / `_ku` / `_sph`.

## What this box is for

The H5082 plugs report on/off but no watts. The watt response is the bus meter.
HA turns dump sockets on until that meter rises by **Confirm min load rise**.
A socket that comes on but does not move the meter stays on (nothing is drawing)
and the next socket is tried. A socket that never reports on takes the 10 minute
cooldown so HA does not sit on it, and the next socket is tried.

## The entities

| Row | Entity | Unit / range | What it does | Raise it | Lower it |
|---|---|---|---|---|---|
| Confirm wait | `input_number.dump_site_confirm_s` | s, 5-30, step 1 | Seconds HA waits, after the plug reports on, before reading the meter again | Slower staging, but slow meters (Sungold Modbus polls every ~5 s) have time to update | Faster staging; too short and the meter has not caught up, so good loads fail |
| Confirm min load rise | `input_number.dump_site_delta_min_w` | W, 5-500, step 5 | The bus load must rise by at least this many watts | Small loads (lamp, fan) get rejected | Meter noise may "confirm" a socket that is not drawing anything |

**Safe starting values:** 5 s and 25 W. A good rule: min load rise = about half the
watts of your smallest dump load (a 60 W lamp: 25-30 W; a 1500 W heater: 25-500 W).

## How it works in the package

For each socket `sensor.dump_next_plug` offers, `dump_turn_on`:

1. Reads all three bus loads **before**. A = `sensor.dump_bus_load_t2`
   (= minus `sensor.battery_1_power`), B = `sensor.dump_bus_load_ku`
   (= minus `sensor.battery_2_power`), Sungold =
   `sensor.sungold-inverter-1_load_power`. The Inverter label does not pick the meter.
2. Logs `turning ON from measured bus headroom` and calls `switch.turn_on`.
3. Waits up to 2 minutes for the H5082 to **report** on (the Pi bridge only reports
   on after the plug acknowledges over Bluetooth).
4. Waits **Confirm wait** seconds, then reads the load **after**.
5. If the A charger left float or solar went away meanwhile: socket off, 10 minute
   cooldown, staging stops.
6. **Watt response** = the plug reported on and a **healthy** bus rose by at least
   **Confirm min load rise** (that bus still above stop, inside its discharge limit,
   and at start volts; Sungold also needs the voltage guard off). The log says
   `kept ON` and adding stops. A rise only on a bus at or under stop, or past its
   discharge limit, turns that socket off.
7. **On, no watt rise:** the socket stays on. The log says `on but no watt rise`
   and HA tries the next socket (at most 16 per run).
8. **Did not report on:** 10 minute cooldown, log says `did not report on within
   2 minutes`, and HA tries the next socket. The same plug is not commanded again
   until that cooldown ends.

Note for A and B: the meter is the battery shunt. In float the MPPT can cover part
of a new load from PV, so the shunt may show less than the appliance's full watts.
If a known-good A/B heater keeps failing confirm, lower min load rise first.

Before 2026-09-28 both numbers went back to 5 s / 25 W at every HA restart. They now
keep your value.

## Example

Sungold socket with a 700 W heater. Load before 310 W; the plug reports on after
3 s; 5 s later Sungold AC-out reads 1015 W. Rise 705 W >= 25 W: kept on, and HA
stops adding. A socket whose heater thermostat is satisfied reads a rise of 4 W:
left on, log `on but no watt rise`, and the next socket is tried. A socket that
never reports on takes the 10 minute cooldown and the next socket is tried.

## Recommended first test

1. Lamp on a dump socket (see [Socket Use](socket-use.md)); set min load rise to half
   the lamp's watts.
2. When HA adds it, the activity log should show `turning ON` then `kept ON: ... load
   rose N W`.
3. Unplug the lamp. The next attempt that finds it on with no watt rise leaves it
   on and tries another socket. A socket that does not report on logs
   `did not report on` and waits out its 10 minute cooldown.
