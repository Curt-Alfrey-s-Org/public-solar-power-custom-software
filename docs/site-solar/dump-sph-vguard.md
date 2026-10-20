# Site solar help: Sungold voltage guard

**Where:** Site solar > Now view > **Sungold voltage guard**.
The guard sensor does not use binary-sensor device class `problem`. That class is defined as problem detected (https://www.home-assistant.io/integrations/binary_sensor/#device-class). This row is a dump hold, not a fault in the cart.

**Logic:** `config/packages/dump_control.yaml`: `input_boolean.dump_inverter-1-vguard_enabled`,
`input_number.dump_inverter-1-vguard_floor_v`, `input_number.dump_inverter-1-vguard_margin_v`,
`input_number.dump_inverter-1-vguard_hysteresis_v`, `input_number.dump_inverter-1-vguard_dwell_s`,
`binary_sensor.dump_inverter-1-vguard`, `sensor.dump_inverter-1-vguard_gap`, automations
`dump_inverter-1-vguard_shed`, `dump_inverter-1-vguard_inlet_off`, and `dump_inverter-1-vguard_inlet_off_clear`.
Voltages: `sensor.sungold-inverter-1_battery_voltage`,
`sensor.battery_1_voltage` (A, SmartShunt HQ2239CQYT2), `sensor.battery_2_voltage`
(B, SmartShunt HQ2239JTRKU).

## What this box is for

While you are balancing the packs, stop dump sockets that are assigned to the Sungold
inverter from pulling the Sungold battery further below the A and B voltages, or
below a floor you set. The guard sheds those dump sockets and
blocks turning them on. It does not change the inverter, and it does not
send a status notification when the guard is on.

## The gap

The Sungold sidecar in this repo publishes sensors only. It does not write Modbus, and
there is no other switch here for the inverter's charge current, AC charge or output
mode. Those stay on the inverter's front panel.

What this repo can do:

- Turn **off** dump sockets whose **Inverter** helper is Sungold (Use = dump, not House),
  and refuse to turn those sockets **on**, while the guard is active.
- Post one notification only when the guard is on and the Sungold charge inlet
  stayed off (automation `dump_inverter-1-vguard_inlet_off`). A guard that is on while
  that inlet is already on is not a notification. Phone text uses
  [Dump alerts](dump-alerts.md) when a service is set.

What it cannot do: raise or hold Sungold voltage by itself, and it does not turn on
an inlet. Shedding only removes the AC load of the dump sockets you assigned to
Sungold. If the sag is the inverter's own load, a socket whose Use is normal, or
charge settings on the panel, the voltage can keep
falling. That state is not a notification. Home Assistant already charges the
Sungold inlet from A or B through the Sungold charge rule. The only alert is
when the guard is on and that inlet stayed off: turn the inlet on. To feed the
Sungold from A or B through a socket, use
[Sungold charge](sph-charge.md). That rule is separate. A guard trip does not turn
the charge socket on. The guard shed still only targets Use = dump and Inverter = Sungold.

Which sockets are on the Sungold inverter is only the **Inverter** helper
(`input_select.plug_<id>_<side>_inverter` = Sungold). Nothing in the repo names a load
or a place.

## The entities

| Row | Entity | Range / states | What it does |
|---|---|---|---|
| Guard active | `binary_sensor.dump_inverter-1-vguard` | On / Off | Shows **On** or **Off**, not Problem. **On** when the guard is enabled and Sungold volts are under the floor, or under the lower of the live A and B volts by the margin. Stays on until both tests have recovered by the hysteresis. **off** when the guard is disabled, Sungold volts are missing, or the voltage has recovered. Attributes: `sungold_v`, `battery-2-v`, `battery-1-v`, `ref_v` (the lower shunt, or `none`), `reason`. |
| Sungold minus lower of A and B | `sensor.dump_inverter-1-vguard_gap` | volts, may be negative | `sensor.sungold-inverter-1_battery_voltage` minus the lower of `sensor.battery_1_voltage` and `sensor.battery_2_voltage`. Negative means Sungold is below that shunt. `none` if Sungold or both shunts are missing. One missing shunt: the other shunt is the reference. |
| Sungold battery voltage | `sensor.sungold-inverter-1_battery_voltage` | V | Sungold pack voltage from the read-only sidecar. |
| A battery voltage | `sensor.battery_1_voltage` | V | A SmartShunt voltage. |
| B battery voltage | `sensor.battery_2_voltage` | V | B SmartShunt voltage. |
| Enable Sungold voltage guard | `input_boolean.dump_inverter-1-vguard_enabled` | on / off | Master for this guard only. **Off:** the sensor stays off and nothing is shed for this rule. A brand-new helper starts **off**. |
| Floor (Sungold volts) | `input_number.dump_inverter-1-vguard_floor_v` | 24.0–29.5 V, step 0.05 | Sungold at or above this is not a floor trip. Suggested start **25.6 V**. A brand-new helper starts at **24.0**. |
| Margin below the lower of A and B | `input_number.dump_inverter-1-vguard_margin_v` | 0–2 V, step 0.05 | Trip when Sungold is below (lower of A and B) minus this. Suggested start **0.30 V**. A brand-new helper starts at **0** (any drop below the lower shunt). |
| Hysteresis | `input_number.dump_inverter-1-vguard_hysteresis_v` | 0.05–1 V, step 0.05 | Once tripped, Sungold must rise by this much above the floor and above (lower shunt minus margin) before the guard clears. Suggested start **0.10 V**. A brand-new helper starts at **0.05**. |
| Minimum time under the limit | `input_number.dump_inverter-1-vguard_dwell_s` | 15–600 s, step 15 | The guard must stay on this long before the shed. The inlet-off alert waits longer, until the charge rule has had time to turn the inlet on. Suggested start **60 s**. A brand-new helper starts at **15**. |

No helper here has `initial:`. Home Assistant keeps what you set across a restart. The
numbers above are suggested starts, written by hand or by **Dump master switch > Load
recommended starting values** (that button also replaces every other dump number, and
it does **not** turn the guard on).

The reference is the **lower** of the two live shunt voltages, so a difference between
A and B does not force Sungold to chase the higher pack. If one shunt is unavailable,
the other is used. If both are unavailable, only the floor applies.

## How it works in the package

- `binary_sensor.dump_inverter-1-vguard` is the trip, with hysteresis taken from its own
  previous state. The automation does not hard-code the volts or the seconds: it waits
  until the sensor has been on for `input_number.dump_inverter-1-vguard_dwell_s`.
- It does not notify because the guard is on, because the pack is under the floor,
  or because Sungold is below the A/B margin. Shedding dump sockets is the
  automation. Status is not notified.
- After that same dwell, `dump_inverter-1-vguard_inlet_off` waits until a Sungold charge
  socket is on, the guard clears, or the charge rule has had its dwell plus the
  3 minute plug wait and 30 seconds
  ([wait for a template](https://www.home-assistant.io/docs/scripts/#wait-for-a-template)).
  If the guard is still on and no socket whose Use is Sungold charge and whose
  Inverter is A or B is on, it sends `notify.persistent_notification`
  ([Notifications](https://www.home-assistant.io/integrations/notify/))
  with notification id `sungold_vguard_inlet_off`
  ([Persistent Notification](https://www.home-assistant.io/integrations/persistent_notification/)).
  The title is "Sungold charge inlet stayed off" and the message says to turn
  that inlet on. The phone service is sent when [Dump alerts](dump-alerts.md)
  has one. Reusing the notification id updates the same popup.
- When the guard turns off, or that inlet turns on, `dump_inverter-1-vguard_inlet_off_clear`
  dismisses `sungold_vguard_inlet_off`.
- If the master switch is on, it turns off every dump socket whose Inverter is Sungold
  and that is not already off, starts that socket's 10 minute cooldown, and logs the
  reason. The same [hold](dump-hold.md) rule as the other turn-offs applies: a held
  socket is skipped only while **Hold also blocks turn-offs** is on.
- While the sensor is on, `sensor.dump_next_plug` and Turn next dump ON will not choose
  a Sungold socket. A and B sockets are unchanged.
- Turning the master switch on while the guard has already been on for the dwell sheds
  at that moment.
- If a hold ends while the guard is still on and the socket is still on, `Dump HOLD end`
  turns a Sungold dump socket off (`Sungold voltage guard`).
- Missing Sungold voltage: the sensor stays **off**. It will not shed on an empty
  reading.

## Example

A `sensor.battery_1_voltage` = 27.20 V, B `sensor.battery_2_voltage` = 27.00 V, so the
lower shunt is 27.00 V. Floor 25.6 V, margin 0.30 V, hysteresis 0.10 V, dwell 60 s,
guard enabled, master switch on, Hold also blocks turn-offs off.

Sungold falls to 26.65 V (below 27.00 − 0.30 = 26.70, still above the floor). The gap
sensor reads about −0.35 V. After 60 s the guard turns off dump sockets whose Inverter is Sungold and does not notify.
A dump socket on A or B stays on. If the Sungold charge inlet is already
on, there is still no notification. If that inlet is still off after the
charge dwell plus the 3 minute plug wait, one notification says to turn it
on. Sungold must climb to
26.80 V (26.70 + 0.10) before the guard clears. Under the floor (25.6 V) trips the same
way even if the shunts are lower, and it notifies only when the inlet stayed off.

## Recommended first test

1. Read **Sungold battery voltage**, **A battery voltage** and **B battery voltage**.
   Set floor, margin, hysteresis and dwell **before** enabling. Suggested start: 25.6 V,
   0.30 V, 0.10 V, 60 s. Leave the guard off until those four match what you typed.
2. Set one test socket's Use to dump and its Inverter to Sungold, and leave a second
   dump socket on A or B. Master switch on. Hold also blocks turn-offs off.
3. Temporarily set the floor **above** the live Sungold voltage (put it back after).
   Within the dwell, Guard active turns on and the Sungold dump socket
   turns off (Dump activity log names the voltage guard). The A/B socket stays.
   **Next socket HA would add** is not the Sungold socket. No notification appears
   while the Sungold charge inlet is on. If that inlet stays off, one notification
   appears after the charge wait and tells you to turn it on.
4. Set the floor back to 25.6 V. When Sungold is above the floor and within the margin
   of the lower shunt, Guard active clears after the hysteresis.
