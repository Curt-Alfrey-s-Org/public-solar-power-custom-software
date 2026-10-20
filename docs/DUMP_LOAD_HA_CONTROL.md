# Dump-load control in Home Assistant

Home Assistant owns dump-load **on/off**. The program follows Victron's charge
cycle, not a PV-minus-load watt band. In **float**, the MPPT already throttles to
match load; a 20 W "surplus" is normal. Dump then **claims leftover PV** by adding
plugs until bus voltage approaches **re-bulk**, then sheds so the packs stay full
when the sun stops (weather or end of day). Target: **95%+ SoC remaining** after
PV is gone -- dumps must not run as night loads.

alfa-ai does **not** toggle these switches from its ticker. The brain **observes**
HA states, keeps the watt-ledger for Ask ALFa, and may write dump **helpers**
(float/re-bulk volts, AC caps, inverter assign) immediately.

This site: LiTime 24 V 230 Ah on A and B ([product](https://www.litime.com/products/24v-230ah-truck-lithium-battery)
charge **28.8 V +/- 0.4 V**). Sungold cart is a separate LiTime 24 V pair.

Official manuals (RULE #1):

- Packages: [configuration packages](https://www.home-assistant.io/docs/configuration/packages/)
- Automations YAML (labeled `automation` block): [Automations in YAML](https://www.home-assistant.io/docs/automation/yaml/)
- Switch actions: [switch.turn_on](https://www.home-assistant.io/integrations/switch/) /
  [switch.turn_off](https://www.home-assistant.io/integrations/switch/)
- Threshold helper (numeric hysteresis): [Threshold](https://www.home-assistant.io/integrations/threshold/)
- State trigger `for:` (dwell): [State trigger](https://www.home-assistant.io/docs/automation/trigger/)
- Timer helper (per-plug min-on and cooldown): [Timer](https://www.home-assistant.io/integrations/timer/)
- Delay (`delay` seconds, templates): [Wait for time to pass](https://www.home-assistant.io/docs/scripts/#wait-for-time-to-pass-delay)
- Derivative helper (PV rising/falling): [Derivative](https://www.home-assistant.io/integrations/derivative/)
- Template sensors: [Template](https://www.home-assistant.io/integrations/template/)
- Number helper (AC watt cap and max battery discharge): [Input number](https://www.home-assistant.io/integrations/input_number/)
- Dropdown helpers (which sockets are dump, which inverter feeds each): [Input select](https://www.home-assistant.io/integrations/input_select/)
- Wait for the plug to report on: [Wait for a template](https://www.home-assistant.io/docs/scripts/#wait-for-a-template)
- Staged ON (`repeat` / `while` / `delay` / `if` / `stop`): [Script syntax](https://www.home-assistant.io/docs/scripts/)
- Notifications: [Notify](https://www.home-assistant.io/integrations/notify/) and [Companion](https://companion.home-assistant.io/docs/notifications/notifications-basic/)
- State `for:` 10 min / 1 min: [State trigger](https://www.home-assistant.io/docs/automation/trigger/)
- MQTT discovery (same HA path Victron BLE already uses): [MQTT](https://www.home-assistant.io/integrations/mqtt/)
- Govee BLE sensors only (**not** H5082 plugs): [Govee Bluetooth](https://www.home-assistant.io/integrations/govee_ble/)
- Victron charge stages and 1-minute re-bulk: [BlueSolar operation](https://www.victronenergy.com/media/pg/Manual_BlueSolar_MPPT_75-10_up_to_100-20/en/operation.html)
- SmartShunt current sign (+charge / -discharge): [SmartShunt operation](https://www.victronenergy.com/media/pg/SmartShunt/en/operation.html)

Morningstar diversion role (excess after the battery is served):
[Diversion Manual §6.0](https://www.morningstarcorp.com/wp-content/uploads/technical-doc-diversion-manual-en.pdf).

Do **not** invent PV watts from Ecobee `weather.*`. Optional later: HA
[Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/) sensors.

---

## What HA owns vs what Ask ALFa / the brain owns

Victron [BlueSolar operation](https://www.victronenergy.com/media/pg/Manual_BlueSolar_MPPT_75-10_up_to_100-20/en/operation.html):
bulk fills, absorption holds CV (~**28.4 V** on Victron lithium / LiTime 28.4-29.2 V),
float **holds** Vfloat (Victron LiFePO4 default **27.0 V** on 24 V). Re-bulk when
`Vbat < (Vfloat - 0.1 V)` for **12 V**, **multiply by two on 24 V** (offset **0.2 V**
-> **26.8 V** if float is 27.0 V) for **one minute**. Morningstar
[Diversion §6.0](https://www.morningstarcorp.com/wp-content/uploads/technical-doc-diversion-manual-en.pdf):
divert excess **after** the battery is served. Confirm float on the A MPPT in
VictronConnect; recommended 27.0 / 26.8 (Recommended defaults button); the values
survive restarts and Ask ALFa may tune them.

| Job | Owner |
|-----|--------|
| Kill switch | HA `input_boolean.dump_control_enabled` |
| `switch.turn_on` / `turn_off` | HA automations only |
| **When** dump may start | HA: some measured bus is in **absorption or float** (not bulk) for 1 min, that bus voltage **>= start-volt helper**, that bus PV >= min solar, that bus SoC >= min (or SoC ignored), and that bus's meter has room. A uses `sensor.battery_1_power` / `_voltage` / `_current` (+ power = charge). B uses `sensor.battery_2_power` / `_voltage` / `_current`. Sungold uses `sensor.sungold-inverter-1_load_power` and `sensor.sungold-inverter-1_battery_voltage`. The socket Inverter label is not the decider. Plug W estimate = max(`dump_site_delta_min_w`, digits in Load text). HA does not write the MPPT. |
| **Which** sockets | A socket on [manual hold](site-solar/dump-hold.md) (switched by hand) is never turned on by these automations and is turned off only if **Hold also blocks turn-offs** is off. Only sockets whose `input_select.plug_<id>_<side>_use` is **dump** (Site solar **Use**; default **normal**). A normal socket is never switched by these automations. A socket whose `input_select.plug_<id>_<side>_inverter` is **House** (plug on house grid power) is never switched either, even if its Use is dump. All 16 sockets (8 plugs) are in the list. What is plugged into a socket is only its HA **Load** text, never hard-coded. |
| **How many** plugs (claim leftover PV) | HA staged ON: one socket, **site load delta** on the bus meters after `dump_site_confirm_s` (default 5 s), then another while a measured bus stays above re-bulk, batt ok, under its AC limit, and that plug's cooldown is idle. A watt rise only on a bus at or under stop, or past its discharge limit, turns that socket back off. |
| **When** dump must stop (keep 95%+ after PV) | HA: solar gone 1 min (cancels min-on); bus voltage **<= re-bulk helper** 1 min; pack discharging `dump_batt_battery-2-ok` / `_battery-1-ok` / `_inverter-1-ok` off 1 min; **`dump_load_exceeds_solar`** on 1 min (Sungold AC-out above site PV **or** A/B shunt charge at/below `dump_min_solar_w` while a dump on that bus is on) sheds **one** plug per minute (`sensor.dump_shed_plug`); Victron left absorption/float 1 min sheds **one** plug per minute (not all at once) |
| **Loads > solar 10 min** | HA `binary_sensor.dump_load_exceeds_solar` (Sungold AC-out vs A MPPT PV + Sungold PV) `for: 00:10:00` then [notify](https://www.home-assistant.io/integrations/notify/). Helper `input_text.dump_notify_service` (recommended `persistent_notification`; empty = persistent notification only; set to Companion `mobile_app_<device>` for phone text). alfa-ai does **not** send this SMS. |
| Float / re-bulk volt helpers | HA `input_number.dump_float_*_v` / `dump_rebulk_*_v` (recommended 27.0 / 26.8; kept across restarts). Ask ALFa may `ha_set_number` immediately to match VictronConnect. |
| Min solar W (day vs night) | HA `input_number.dump_min_solar_w` (recommended 50). Below that for 1 min = PV stopped. |
| SoC 95% floor | HA `input_number.dump_min_soc_percent` (95) **only when** `input_boolean.dump_soc_unsynced` is **off**. While unsynced, float voltage **is** the full-enough gate (do not invent a voltage-to-% map). |
| Site confirm / delta | HA `input_number.dump_site_confirm_s` (5-30 s, recommended 5) and `input_number.dump_site_delta_min_w` (5-500 W, recommended 25) |
| Per-socket min-on / cooldown | HA `timer.plug_<id>_<side>_min_on` (15 min, `restore: true`) and `timer.plug_<id>_<side>_cooldown` (10 min, `restore: true`) |
| Inverter caps, socket label | HA `dump_ac_limit_battery-2-w` / `_battery-1-w` / `_inverter-1-w` apply to the measured bus, not to sockets grouped by label. `input_select.plug_<id>_<side>_inverter` (Sungold / A / B / House) is still the House skip and the Sungold charge source bank. It is not the dump add/shed decider. House = grid-powered house plug, never dump-switched. No `initial`, so the choice survives restarts. H5082 sends on/off only (no per-socket V/A/W). |
| Watt-ledger, AI Actions, `ha_dump_tick` | alfa-ai **observe / audit** |
| Tune helpers, inspect meters | Ask ALFa `ha_set_number` / `ha_select_option` / `ha_get_states` (no Approve). **Never** dump-actuate standing night loads. |
| Surplus W (`sensor.dump_surplus_w`) | Briefing only. **Not** the ON/OFF trigger. |

Do **not** add a second dump ticker in alfa-ai that calls `switch.turn_on` /
`turn_off` while this package is loaded.

---

## Package

Tracked source: `config/packages/dump_control.yaml` (replaced the retired
`sim_dump_control.yaml` + `sim_dump_plugs.yaml` on 2026-09-28).

Depends on:

- The H5082 MQTT switches `switch.ihoment_plug_<id>_<side>` from `govee_h5082`
  (`h5082-mqtt.service` on the Pi 4, `hci1`, and on the Pi 5 for the plugs it owns) -- see
  [plug_INSTALL_PLAN.md](plug_INSTALL_PLAN.md) and [plug_MULTI_BRIDGE.md](plug_MULTI_BRIDGE.md).
- The per-socket helpers `input_select.plug_<id>_<side>_use` (normal / dump) from
  `scripts/create_plug_socket_labels.py`. Missing or unknown = normal.

Dump sockets: the 16 sockets of plug-1, plug-2, plug-3, plug-4, plug-5, plug-6, plug-7, plug-8 whose
**Use** is dump and whose **Inverter** is not House. Stage order is that list (left
before right); shed order is the reverse.

**House guard.** Every socket pick in `dump_control.yaml` (the `sensor.dump_sockets`
count and list, `sensor.dump_next_plug`, `sensor.dump_shed_plug`, the recheck in
`dump_turn_on`, and every turn-off list: solar gone, per-bus stop volts, per-bus battery)
uses the same test: Use is `dump` **and** Inverter is not `House`. A House socket is
therefore never turned on or off by dump control; the Plugs buttons and the plug's own
button still switch it. Switching a socket to House while dump control has it on leaves
it on (turn it off yourself if needed). A House socket needs no bus: its volts, battery
and AC limits are never read. plug-7 was paired on the bridge 2026-09-28 and has the same Use / Inverter
selects and min-on / cooldown timers as every other socket.

**What is plugged in is not in the repo.** Loads move and plugs move, so the repo never
says what a socket feeds or where a plug is. Set **Where** (per plug) and **Load** (per
side) in HA under Site solar > **Plug names**; the Plugs buttons, the Socket Use /
Socket inverter rows, **Dump status > Dump sockets by name** and every **Dump control**
logbook line read them live (`Heater (<ID> left) at Bedroom`, or `<ID> left` when Load
is blank). Per-box help: [site-solar/plug-names.md](site-solar/plug-names.md).
`sensor.dump_sockets` shows how many sockets are dump (attribute `entities`).

PV watts: live MQTT id `sensor.victron-mppt-1_solar`, with fallback
`sensor.victron-mppt-1_solar_power`. Charge stage: live
`sensor.victron-mppt-1_charge_state`, with fallback
`sensor.victron-mppt-1_battery_state`. Bus volts: `sensor.battery_1_voltage` /
`sensor.battery_2_voltage` / `sensor.sungold-inverter-1_battery_voltage`.

`sensor.dump_surplus_w` remains for the watt-ledger. It is **not** the dump ON
trigger (float throttles PV watts to the load).

### Victron absorption/float then staged ON

**Bulk:** dump stays **off** until the MPPT enters absorption (no early morning bulk add).

**Absorption / float:** HA may add dumps while the charger serves the pack and shunt headroom remains:

1. `binary_sensor.dump_charge_float` on for 1 min (A or B in **absorption or float**, or Sungold at start volts).
2. `binary_sensor.dump_solar_present` on (PV >= `dump_min_solar_w`).
3. That plug's bus `dump_v_float_*` on for 1 min (shunt/cart V >= float helper).
4. `dump_soc_unsynced` off **and** SoC < `dump_min_soc_percent` (95) blocks A/B add.
   While unsynced, skip SoC (float voltage is the full-enough gate)
   ([SmartShunt 5.7](https://www.victronenergy.com/media/pg/SmartShunt/en/operation.html)).
5. `sensor.dump_next_plug` picks an **off** dump socket (Inverter not House) whose **cooldown timer is idle**,
   when some measured bus is in absorption/float (Victron buses), batt ok, under its AC limit, and that
   bus's meter has room above estimated plug W + `dump_min_solar_w`. A room is `sensor.battery_1_power`.
   B room is `sensor.battery_2_power`. Sungold room is the AC limit minus
   `sensor.sungold-inverter-1_load_power`. The Inverter label does not pick the bus. An unavailable
   socket (bridge offline) is never picked. H5082 has no telemetry watts; estimate from Load text and
   `dump_site_delta_min_w`.
   Staging also waits while `dump_load_exceeds_solar` is on (that rule would shed
   the socket a minute later), and stops if `dump_control_enabled` goes off.
6. One `switch.turn_on`, then wait (up to 2 min) until the H5082 **reports on** (the
   bridge publishes on only after the plug acks over BLE; a cold link is connect +
   login + retries), then [delay](https://www.home-assistant.io/docs/scripts/#wait-for-time-to-pass-delay)
   `input_number.dump_site_confirm_s` seconds (default **5**; Sungold Modbus poll
   default is also 5 s). A socket that never reports on counts as not confirmed.
7. **Site confirm** (solar-system load, not indoor Govee energy monitoring). All three
   meters are read. A rise on a bus that is still above its stop and inside its
   discharge limit keeps the socket:
   - **Sungold:** `sensor.sungold-inverter-1_load_power` rises by >=
     `dump_site_delta_min_w` (default 25 W).
   - **A:** `sensor.dump_bus_load_t2` (signed `-sensor.battery_1_power`; more AC load
     => more negative pack power / less charge).
   - **B:** `sensor.dump_bus_load_ku` (signed `-sensor.battery_2_power`).
   A rise only on a bus at or under stop, or past its discharge limit, turns the
   socket off. The Inverter label does not choose which meter to watch.
8. If solar-present or charge-float is already off after the delay: turn that plug
   off, start its 10 min cooldown, cancel its min-on, stop staging.
9. If **not** confirmed: turn off, start 10 min cooldown, try the next plug (do
   not stop the whole automation).
10. If **confirmed**: start that plug's 15 min min-on timer, delay 1 s, stage
    another. Confirmed plugs are **not** fail-closed for missing per-plug watts;
    they stay on until solar-gone / re-bulk / batt-not-ok / Sungold load > site solar
    (1 min shed-one) as below. PV falling does **not** immediately turn off a
    confirmed plug.

That is how leftover PV is claimed: add until voltage sags toward re-bulk or the
inverter is full -- not until a 200 W surplus helper trips. Clouds: if **Load now**
(Sungold AC-out, includes dump) stays **above Solar now**, HA sheds dump plugs one
per minute so dump tracks solar. It never switches a socket whose Use is normal. End of day
or dark storm (`dump_solar_present` off 1 min) still turns every dump socket off. After the
first float of the day, leaving absorb/float sheds **one** plug per minute instead
of all of them, so the MPPT is not forced back into a same-day float-idle cycle.

**Govee H5082 (this site's dump hardware):** same *shape* as Victron BLE, not
the same product. Victron Instant Readout is a documented advertisement;
`victron_ble2mqtt` on Pi 4 decodes it and publishes [MQTT discovery](https://www.home-assistant.io/integrations/mqtt/).
HA never speaks Victron BLE. H5082 also has no official HA plug integration
([govee_ble](https://www.home-assistant.io/integrations/govee_ble/) is sensors
only). Forums/GitHub drive it with extra software (HACS or a BLE/cloud MQTT
bridge). This repo's `govee_h5082` bridge on the Pi 4 publishes one MQTT switch
per socket (16), so HA stays on official MQTT. Confirm stays **Sungold AC-out**
(and A/B pack sign), not Govee energy monitoring. HACS Govee plugins are not
used for the plugs.

Default AC caps are **2000 W** per inverter (operator / Renogy 2 kW class).
Sungold nameplate is **3000 W**; raise **Sungold AC limit** only if dumps are on that
inverter and you want the higher cap. Do not set a helper above the inverter
that feeds those plugs.

SoC is **not** a dump-on gate while `dump_soc_unsynced` is on. Float voltage is
the battery-served check. After PV stops, dumps go off so overnight use is the
house/inverter, not dump plugs (95%+ leftover if the day reached float).

Turn-**off** (Victron 1 minute; per-plug 10 min cooldown after any off):

- **All dump sockets:** `dump_solar_present` off 1 min (weather / end of day) --
  every dump socket that is not already off is turned off, its min-on cancelled
  and its cooldown started. This is the 95%+ after solar stops rule.
- **One plug per minute:** `dump_load_exceeds_solar` on 1 min (Load now > Solar now)
  -- last dump socket in the stage order first (`sensor.dump_shed_plug`), cancel min-on,
  start cooldown, wait 1 min, repeat while still over.
- **One plug per minute:** A MPPT not absorption/float 1 min -- same shed-one
  until float returns or no dump is on.
- **Measured bus in trouble:** bus voltage <= re-bulk helper 1 min, or `dump_batt_*_ok`
  off 1 min (pack supplying that bus) -- turn off dump sockets that are not already
  off (unavailable ones are sent off too), cancel each one's min-on, start each one's
  cooldown. The Inverter label does not choose them. A and B stop-volts also run
  when `binary_sensor.dump_soc_hold_trips` turns off while voltage is still at or
  under stop
  ([triggers](https://www.home-assistant.io/docs/automation/trigger/),
  [state condition `for`](https://www.home-assistant.io/docs/scripts/conditions/#state-condition)).
  There is no per-socket voltage, so a socket whose label names a bus still above
  its stop is not left on while another bus is at or under stop and carrying the watts.
- **Failed site confirm:** turn off that plug only, start its 10 min cooldown
  (no min-on started).

**Text alert (10 min):** `dump_load_exceeds_solar` on for `00:10:00` sends
`notify.persistent_notification` and, if `input_text.dump_notify_service` is a
Companion action such as `mobile_app_<device>`, that notify too
([Companion notifications](https://companion.home-assistant.io/docs/notifications/notifications-basic/)).
Find the action under **Settings > Tools > Actions**. This is independent of the
dump kill switch. Trailer A/C on B is **not** in Load now; B overdraw still
uses `dump_batt_battery-1-ok` / re-bulk.

### Any load on any inverter (live meters)

You do **not** type the wattage of a heater/fan/PC you plug into A, B, or Sungold.
HA already has the live meters:

| Inverter | How HA sees a new AC load |
|----------|---------------------------|
| A Renogy | Battery 1 SmartShunt `sensor.battery_1_power` / `_current` (negative = pack supplying the load) |
| B Renogy | Battery 2 SmartShunt `sensor.battery_2_power` / `_current` (same sign) |
| Sungold cart | `sensor.sungold-inverter-1_load_power` (AC out) and cart battery V×A |

If that bus's pack starts discharging, `dump_batt_*_ok` goes off: that bus is not
a place to add a dump, and dump sockets turn off after 1 minute. Which socket is
not taken from the Inverter label. Sungold AC-out watts shrink Sungold headroom
immediately (`sensor.sungold-inverter-1_load_power`).

H5082 advertisements carry on/off only (no watts). There is no typed rating
helper and no per-socket power sensor; confirm is the rise on these bus meters.
Do not invent a plug watt sensor. If a per-socket power sensor appears later,
prefer the socket that is actually drawing on the bus that is in trouble.

Ask ALFa may **observe** shunt/Sungold/plug power and voltage (`ha_get_states` /
`ha_dump_tick`) and write float/re-bulk/AC-cap/inverter helpers immediately.
It does not invent plug watts and does not own dump on/off.

---

### Manual hold (2026-09-28)

When a dump socket is switched by hand (Plugs button, the plug's own button, any change
dump control did not ask for), dump control leaves it alone for a while, then resumes.
Full page: [Site solar help: Dump manual hold](site-solar/dump-hold.md).

- Settings: `input_number.dump_manual_hold_min` (0-720 min, **0 = hold off**, recommended
  60) and `input_boolean.dump_hold_blocks_turn_off` (recommended on). No `initial:`; a
  brand-new install starts at 0 min / off, so nothing changes until you set them (or
  press Recommended defaults, which replaces **all** tuned dump numbers).
- One hold timer per socket: `timer.plug_<id>_<side>_hold` (16, `restore: true`).
- **Detection.** The H5082 switches are MQTT switches with a state topic, so every state
  change (tap, plug button, dump rule) arrives with a fresh context and no user: context
  cannot tell them apart. Every dump rule therefore fires `dump_control_switching`
  (`sock`, `on`/`off`) right before each `switch.turn_on` / `turn_off`; the trigger-based
  `sensor.dump_control_switching` keeps the last request per socket. `Dump HOLD start`
  (`dump_hold_start`) runs on every on/off change of the 16 switches: a change that
  matches a request from the last 3 minutes is dump control; anything else on a dump
  socket (Use dump, Inverter not House) with hold minutes > 0 starts that socket's hold.
- **Hold guard.** Next to the House guard, the socket picks check the hold timer:
  - turn-on (`sensor.dump_next_plug`, the recheck in `dump_turn_on`): a held socket is
    **always** skipped;
  - turn-off (`sensor.dump_shed_plug`, used by both shed rules, and the seven turn-off
    lists: solar gone, stop volts A/b/Sungold, battery A/b/Sungold): a held socket
    is skipped only while **Hold also blocks turn-offs** is on. With it off, those
    rules still turn a held socket off (battery first).
  - `sensor.dump_sockets` still counts held sockets (they are still set to dump) and
    lists them in its `held` attribute.
- **Hold end.** `Dump HOLD end` (`dump_hold_end`) logs the end (time up / cleared). The
  turn-off rules only fire when their condition starts, so if the master switch is on
  and the socket is still on while dump control would want it off now (solar gone, A
  charger left absorption/float, Sungold load above solar, its bus at stop volts, its
  battery past the limit), it turns it off with a cooldown. Turn-on resumes through
  `sensor.dump_next_plug`.
- `script.dump_clear_holds` (Clear all holds button) cancels every hold; a single hold
  ends from its timer row (Cancel).
- Every hold start / end writes a `Dump control` line to the Dump activity log.

### On demand and skip cooldown

Full page: [Site solar help: Dump on demand](site-solar/dump-on-demand.md).

- **Turn next dump ON** (`script.dump_force_on`) switches the one socket in
  `sensor.dump_ondemand_on`. It does not wait for float, solar, SoC, start volts,
  battery ok or AC headroom. It still skips House, normal, held sockets, cooldown
  (unless skip cooldown is on), and Sungold sockets while the voltage guard is on.
- **Turn dumps OFF** (`script.dump_force_off`) switches off every on dump socket that
  is not on hold (`sensor.dump_ondemand_off`).
- Neither script fires `dump_control_switching`. When the plug reports the new state,
  `Dump HOLD start` arms the manual hold, so automation does not immediately undo the
  press. Hold minutes **0** arms nothing.
- `input_boolean.dump_skip_cooldown` (no `initial:`, starts off) lets the next
  automatic add and the ON button ignore cooldown, and makes the OFF button skip
  starting a cooldown. It turns off after that next success.

### Sungold voltage guard

Full page: [Site solar help: Sungold voltage guard](site-solar/dump-sph-vguard.md).

The Sungold sidecar is read-only. This guard cannot write charge settings. It sheds
and blocks dump sockets whose **Inverter** helper is Sungold. It does not send a
status notification. The only alert is `dump_inverter-1-vguard_inlet_off`, when the
Sungold charge inlet stayed off.

- Helpers (no `initial:`): `input_boolean.dump_inverter-1-vguard_enabled` (starts off),
  `input_number.dump_inverter-1-vguard_floor_v` (suggested 25.6 V, new helper starts at 24.0),
  `input_number.dump_inverter-1-vguard_margin_v` (suggested 0.30 V, starts at 0),
  `input_number.dump_inverter-1-vguard_hysteresis_v` (suggested 0.10 V, starts at 0.05),
  `input_number.dump_inverter-1-vguard_dwell_s` (suggested 60 s, starts at 15).
- Trip: enabled, and Sungold volts under the floor **or** under the lower of
  `sensor.battery_1_voltage` (A) and `sensor.battery_2_voltage` (B) by the margin.
  Hysteresis uses the sensor's previous state. Dwell is the helper, not a fixed minute.
- `binary_sensor.dump_inverter-1-vguard` and `sensor.dump_inverter-1-vguard_gap` (Sungold minus that
  lower shunt) are on Site solar. While the guard is on, `sensor.dump_next_plug` skips
  Sungold sockets. A and B sockets are not blocked by this rule.
- Shedding needs the master switch. There is no status notification either way.
  `dump_inverter-1-vguard_inlet_off` notifies only when no Sungold charge inlet is on
  after the charge rule's wait. A held socket is
  skipped only when **Hold also blocks turn-offs** is on, same as the other turn-offs.

### Sungold charge (grid inlet)

Full page: [Site solar help: Sungold charge](site-solar/sph-charge.md).

A socket whose Use is **Sungold charge** is not a dump. Dump add, shed, off,
on-demand and the voltage-guard shed never select it. Its Inverter helper names the
bank that feeds the inlet (A or B).

- Own enable switch `input_boolean.inverter-1-charge_enabled` (starts off). Does not follow
  the dump master switch.
- Rescue turns the socket on when the Sungold pack is under a floor helper, under
  the lower of A and B by a margin helper, or under an optional SoC, for a dwell,
  and the feeding bank is at or above a source-minimum volts helper (optional source
  SoC). The voltage guard does not start this charge. Rescue ignores the per-socket
  cooldown. It turns the socket off when the pack reaches the full helper, after a
  minimum on time, or immediately when the feeding bank falls under a source-stop helper.
- Surplus uses the same Use and the same enable switch. While rescue is off and
  Sungold is under full volts, the socket turns on when that bank is in float, solar
  is present, the bank is not at stop volts, the battery is within its discharge
  limit, and battery charge watts are at or above `input_number.inverter-1-charge_surplus_min_w`
  (suggested 1100 W, a new helper starts at 100). It waits while a dump socket is
  still next and the dump master is on. It turns off when those checks fail. Full
  volts are still the pack-recovered off.
- A hand tap arms the same manual hold. Automatic charge switches announce themselves
  first. Home Assistant start and a one minute poll re-check rescue and surplus.
- If the socket is on and charging power stays about 0 W for 3 minutes, with grid
  voltage at or below 0 or at or above 50, a notification fires. Missing sidecar
  values do not alert. The Sungold panel must allow mains charging or the inlet will
  not charge the pack. No helper has `initial:`. Suggested starts are only in the
  help page. The defaults button does not write them.

### Review 2026-09-28 (ported from the sim package)

- Dump actions only ever target sockets whose **Use** is dump. The sim package used
  a hardcoded list of six switches (the solar-gone all-off hit all six); pointed at
  the 16 real sockets that would have switched normal loads.
- Turn-off rules send off only to dump sockets that are not already off (fewer BLE
  commands); they no longer start cooldowns on sockets that were already off.
- Staging waits for the plug to report on before the site confirm delay; with a
  cold BLE link the 5 s confirm used to run before the plug switched.
- Staging stops when the kill switch goes off and does not start while Sungold
  load is above solar (it used to add a socket the shed rule removed a minute later).
- `input_select.plug_<id>_<side>_inverter` has no `initial`: the old
  `dump_plug_N_inverter` reset to Sungold on every HA restart, so re-bulk and
  battery rules could watch the wrong bus.
- `sensor.dump_surplus_w` is PV watts (no plug watts to subtract); the derivative
  behind `binary_sensor.dump_status_pv_falling` no longer drops when a dump
  turns on. That blocker is the template in [Dump status](site-solar/dump-status.md), not a threshold latch.
- No dump helper has `initial:` any more (16 `input_number`, `dump_soc_unsynced`,
  `dump_notify_service`). Before, tuned volts / caps / confirm / min solar / SoC floor,
  the alert service and Ignore SoC all snapped back to the package values at **every**
  HA restart (watchdog, autoheal, installs). Now HA restores the last value. The old
  values are the **recommended starting values**: Site solar > **Dump master switch** >
  **Recommended defaults** (`script.dump_load_recommended_defaults`, manual only, asks
  for confirmation) sets them once. A brand-new helper starts at its `min` (numbers),
  off (Ignore SoC) or unknown (alert service: persistent notification only) until you
  set it or press the button.
- `scripts/create_plug_socket_labels.py` used to create the Where / Load / Use storage
  helpers with `initial` "" / "normal". For storage `input_text` / `input_select`, HA
  skips restore when `initial` is set, so labels blanked and every socket fell back to
  **normal** (no dump) at each restart. The script now creates them without `initial`
  and strips it from existing ones (`--dry-run` to preview). See
  [Site solar help: Plug names](site-solar/plug-names.md).
- Every automation switch action writes a plain reason to the logbook ("Dump control:
  ..."), shown on Site solar > **Dump activity log**; helper changes (who / what) show on
  **Dump settings change log**. Automations were renamed ("Dump ON: ...", "Dump OFF ...",
  "Dump SHED ...", "Dump ALERT ...") with the same ids. `logbook:` is enabled by the
  package (no `default_config` on ).

---

## Site solar help (one page per dashboard box)

Each dump box on Site solar > Now has a short help card and a **Help** link:

| Box | Help page |
| --- | --- |
| Dump master switch | [dump-master-switch.md](site-solar/dump-master-switch.md) |
| Dump status (why / why not) | [dump-status.md](site-solar/dump-status.md) |
| Dump voltage (start / stop) | [dump-voltage.md](site-solar/dump-voltage.md) |
| Dump start conditions | [dump-start-conditions.md](site-solar/dump-start-conditions.md) |
| Dump confirm (wait / load rise) | [dump-confirm.md](site-solar/dump-confirm.md) |
| Inverter AC limits | [dump-inverter-limits.md](site-solar/dump-inverter-limits.md) |
| Battery discharge limits | [dump-battery-limits.md](site-solar/dump-battery-limits.md) |
| Dump alerts | [dump-alerts.md](site-solar/dump-alerts.md) |
| Dump timers (min-on / cooldown) | [dump-timers.md](site-solar/dump-timers.md) |
| Dump manual hold | [dump-hold.md](site-solar/dump-hold.md) |
| Dump on demand | [dump-on-demand.md](site-solar/dump-on-demand.md) |
| Sungold voltage guard | [dump-sph-vguard.md](site-solar/dump-sph-vguard.md) |
| Sungold charge | [sph-charge.md](site-solar/sph-charge.md) |
| Plugs | [plug-buttons.md](site-solar/plug-buttons.md) |
| Plug names (Where / Load) | [plug-names.md](site-solar/plug-names.md) |
| Socket Use (normal / dump) | [socket-use.md](site-solar/socket-use.md) |
| Socket inverter (bus) | [socket-inverter.md](site-solar/socket-inverter.md) |
| Dump activity log | [dump-activity-log.md](site-solar/dump-activity-log.md) |
| Dump settings change log | [dump-settings-log.md](site-solar/dump-settings-log.md) |
| History > Dump sockets timeline | [dump-history.md](site-solar/dump-history.md) |

Back up / restore every Site solar setting (helpers + dashboard):
`python3 scripts/site_solar_settings.py export` / `restore --from LATEST --helpers`.

---

## Enable on `` (one path)

Prerequisites: the 16 H5082 switches are in HA and the per-socket helpers exist
(`python3 scripts/create_plug_socket_labels.py`, skips helpers that exist).

```bash
cd /home/operator/victron-ble2mqtt-integration
git pull --ff-only origin main
bash scripts/install_dump_control_ha.sh
```

The script removes any retired `sim_dump_control.yaml` / `sim_dump_plugs.yaml`,
copies `dump_control.yaml` into `/opt/homeassistant/packages/`, runs
`check_config`, and restarts the `homeassistant` container
([HA Container](https://www.home-assistant.io/installation/linux#install-home-assistant-container)).
After a later dump-package change, `git pull` then rerun this script (or
`install_solar_plant_ha.sh`, which refreshes the dump file when it already
exists). A stale copy leaves helpers such as
`input_boolean.dump_soc_unsynced` / `input_number.dump_float_battery-2-v` missing from
`/api/states` while Energy / Helpers still expect them.

Operator dump UI is **Site solar** (`/site-solar`: **Plugs** cards with Use and
Inverter per socket, site confirm/delta helpers, **Dump dwell** per-socket 15 min
min-on / 10 min cooldown), plus **Settings > Devices & services > Helpers**.
Disable: `input_boolean.dump_control_enabled` (Dump Automations helper), or delete
the package file and restart HA. YAML Lovelace is not the daily dump control.

Default: this package is **not** on `/opt/homeassistant` until the operator runs
the install script.

---

## Related

- [plug_INSTALL_PLAN.md](plug_INSTALL_PLAN.md)
- [SOLAR_HA_DASHBOARD.md](SOLAR_HA_DASHBOARD.md)
- alfa-ai observe/audit only: sibling `docs/HOME_ASSISTANT_BRAIN_INTEGRATION.md`
