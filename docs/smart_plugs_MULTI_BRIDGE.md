# H5082 bridge on more than one Pi

The Govee H5082 bridge (`govee_h5082`, unit `h5082-mqtt`) can run on the Pi 4
(``) **and** the Pi 5 (``). Each plug is driven by the Pi that reaches
it, and only by that Pi. First case: plug `plug-4` (the fan) times out from the
Pi 4 (`GATT plug-4 ... TimeoutError`, `SET_FAIL`) but the Pi 5 hears it at about
−56 dBm (see [plug_COVERAGE_PLAN.md](plug_COVERAGE_PLAN.md)).

**Live since 2026-10-06 (afternoon): shared mode.** Every bridge (`solar-broker` on `hci1`,
`monitor` on `hci0`, `apps` on `hci0`) can drive every plug it has a key for. For each
command they pick one radio between them and fail over to the next one. Each radio
reports its own link to each plug. See "Shared mode" below. `apps` is the TP-Link
UB500 on `.229`, passed into VM 105 (see
[plug_USB_PASSTHROUGH.md](plug_USB_PASSTHROUGH.md)).

Before that (morning of 2026-10-06) each plug had exactly one owner (`plug_PLUGS`).
`plug-2` was listed on the Pi 4, which never hears it (`LookupError ... not seen on
hci1`), so every command for it failed. Per-host mode below still works, but shared
mode is the live setup. Step-by-step host list: `NEXT_STEPS.md`, section "Pi 5 H5082
bridge".

## Shared mode (any radio drives any plug)

Turn it on with `plug_SHARED=1` in the host file, with no `plug_PLUGS`. The bridge
then drives every plug whose line is in its key file. Give every bridge the full key
file (all 8 lines).

**Who acts on a command.** Every bridge receives the same HA command
(`govee/plugs/<mac>/<side>/set`). Each one ranks the radios for that plug from what
all of them see on the broker, so they agree on the order:

1. A radio that is linked to the plug now, or in the middle of a command on it
   (`connected` / `busy` in its link report). The plug accepts one link at a time
   and does not advertise while linked, so that radio is the only one that can
   reach it.
2. Radios whose last attempt on this plug did not fail within the last 10 min,
   ahead of radios whose last attempt failed. The age comes from `last_fail` in the
   radio's own link report, not from when the message arrived, so a bridge that
   just restarted reads the same age as the others.
3. Best signal. Each radio averages its RSSI for the plug over the last 2 min,
   rounds it down to a 4 dB step, and publishes the step retained on
   `govee/plugs/<mac>/signal/<radio>` when it changes (`-13` is -52 to -49 dBm).
   After 2 min without hearing the plug it publishes an empty value, and that
   radio goes after those that hear it.
4. Fixed order on a tie: `monitor`, `apps`, `solar-broker`.

Only retained topics feed the ranking, so every bridge, including one that just
started, ranks a plug the same way.

Radios that are offline (`govee/plugs/bridge/<radio>/status` is not `online`) or
have no key for the plug (`no_key`) are left out. The bridge logs the order as
`LINE <id> <side> ON|OFF solar-broker,apps,monitor`.

**Failover.** The first radio acts at once, with the normal 3 tries and the adapter
reset. When it finishes it publishes `govee/plugs/<mac>/<side>/result`
(`{"listener":"solar-broker","want":"ON","ok":false}`). The next radio starts as soon as every
radio ahead of it has reported a failure or gone offline (`FAILOVER <id> <side> ON
after solar-broker`). If a radio ahead says nothing for 4 min, the next one starts anyway
(`FAILOVER_TIMEOUT`). The 4 min restarts while a radio ahead shows `busy`, so a
radio working through a queue of commands is not overtaken, up to 8 min more than
the normal wait in case a report is stuck on `busy`. Once any radio reports
success, the others drop the command, and a radio still retrying stops
(`DONE_ELSEWHERE`).
A newer command for the same socket replaces an older one on every radio. Only
the last radio in line puts the HA switch back to the old state after a failure,
so the switch does not flip back and forth during a failover.

**State.** Every bridge with a key publishes socket state from the plug's
advertisements, and keeps in step with the retained state topic. BlueZ keeps a
plug's last advertisement while another radio holds the link, so a bridge only
treats an advertisement as news when its value changed. It judges the first one it
sees for a plug only 10 s after connecting to the broker, once the retained link
reports and state are in, and skips it when an online radio holds that plug's link. After any radio reports
success, every bridge ignores advertisements for that socket for 20 s, so an
advertisement sent just before the switch cannot flip it back. A bridge does not
republish its own cached state when it reconnects to the broker; the retained
state topic stays authoritative.

**HA entities.** Every shared bridge publishes the same switch config for all 8
plugs. The config lists every radio's status topic as `availability` with
`availability_mode: any`, so a socket stays usable while any bridge is up
([MQTT switch](https://www.home-assistant.io/integrations/switch.mqtt/)). The
entity ids do not change.

**Link health per radio.** Each bridge publishes a retained report per plug on
`govee/plugs/<mac>/link/<radio>` and an HA enum sensor
`sensor.ihoment_plug_<id>_link_<radio>`
([MQTT sensor](https://www.home-assistant.io/integrations/sensor.mqtt/): `device_class:
enum`, `options`, `json_attributes_topic`). The sensor goes unavailable when that
radio's bridge is offline.

| State | Meaning |
|---|---|
| `ok` | The last command this radio sent to the plug was acknowledged. |
| `connect_timeout` | The radio could not open a link (a stuck adapter looks like this). |
| `not_heard` | The radio could not find the plug (out of range, or another radio holds the link). |
| `no_ack` | The link opened but the plug did not confirm the login or the command. |
| `error` | Any other failure (`error` attribute has the text). |
| `no_key` | This radio has no key line for the plug and never tries it. |

Attributes: `connected`, `busy`, `fails` (failed commands in a row), `last_ok`,
`last_fail`, `error`. Until a radio has tried a plug, its sensor is `unknown`.
`config/packages/plug_link.yaml` sums them up per plug as `sensor.plug_<id>_link`:
`ok`, or the radios with a problem (`solar-broker connect timeout, monitor offline`). Site solar
shows it as **Link** in each plug card.

## Adapter reset (stuck controller)

On 2026-10-06 the Pi 4 `hci1` controller (Realtek RTL8761BU) stopped finishing
connections. `btmon` showed the link come up (`LE Enhanced Connection Complete`,
status Success), then `LE Read Remote Used Features` never completed, no ACL data
moved, and the link dropped about 20 s later with `Connection Timeout (0x08)`. The
bridge logged `GATT <id> ... TimeoutError` and `SET_FAIL` for every plug, while the
same plugs were advertising at −50 dBm. Restarting `h5082-mqtt` did not help.
Pausing Theengs did not help. Powering the adapter off and on did: the next
connect finished in 1.8 s.

The bridge now does that itself. When **3** connects in a row time out on its
adapter (any plug, `plug_ADAPTER_RESET_AFTER`, `0` turns it off), it closes its
links, sets BlueZ `org.bluez.Adapter1.Powered` to false and back to true
([BlueZ Adapter API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst)),
logs `ADAPTER_RESET hciN after N connect timeouts`, and tries the same command once
more. It resets at most once every 10 min (`plug_ADAPTER_RESET_GAP_S`, default
600). A plug that is not advertising (`LookupError ... not seen`) and a write with
no ack do not count. Only a connect that times out counts. Any good link sets the
count back to 0.

Powering the adapter off also stops every other program's scan on that adapter for
a few seconds (Theengs on the Pi 4 `hci1`). BlueZ starts them again when power
returns. It never touches another adapter.

## How it works

- **Allowlist per Pi.** `plug_PLUGS` lists the plugs that Pi owns, as the last
  4 hex digits of the MAC (`plug-4`, `plug-1`, ...), separated by commas or spaces.
  It lives in `/home/operator/.config/plug-bridge.env` on each Pi, **not in git**.
  An unknown id stops the bridge with an error, so a typo cannot quietly drop a
  plug. `all` owns every plug and `none` owns none.
- **A bridge ignores plugs it doesn't own.** It does not publish their switch
  config or their state, and does not act on their commands (it logs
  `NOT_OWNER <id> <side>`). It still publishes RSSI for every plug it hears, so
  **Heard by** keeps working.
- **HA stays the same.** Every Pi uses the same command, state and discovery
  topics (`govee/plugs/<mac>/<side>/set|state`,
  `homeassistant/switch/plug_<id>_<side>/config`), so each socket stays one
  entity (`switch.ihoment_plug_<id>_<side>`). Only the **availability** topic
  is per host: `govee/plugs/bridge/<host>/status`. If one Pi goes down, only
  its plugs show unavailable.
  No entity edits, but **reload the MQTT integration** after a bridge starts
  or a plug moves (see below). HA kept the old config until it was reloaded.
- **Claims.** Each owner publishes a retained `govee/plugs/<mac>/owner` =
  `<host>`. If two Pis list the same plug, both log
  `OWNER_CONFLICT <id> also claimed by <host>`. Fix it by removing the plug from
  one Pi's list. After you remove a plug from a Pi's list, that Pi clears its
  own old claim on the next start (`OWNER_RELEASE <id>`).
- **Without the file (or with `plug_PLUGS` unset)** the Pi 4 works exactly as
  before: it owns all 8 plugs and uses the old availability topic
  `govee/plugs/bridge/status`. Timings (connect 20 s, ack 8 s, 3 tries, 120 s
  idle, 20 s hold) are the same in both modes. Any bridge that is not the Pi 4
  refuses to start without `plug_PLUGS`, so a second Pi can never take every
  plug by accident.
- **Adapter.** The Pi 4 must stay on `hci1`, because `hci0` there is Victron.
  The Pi 5 unit uses `hci0` (onboard, shared with the Theengs container). You
  can change it with `plug_ADAPTER=hciN` in the host file, for example if you
  later add a USB dongle.
- **Keys.** Each Pi keeps its own `/home/operator/.govee-plug-keys` (mode 600),
  holding only the lines for the plugs it owns. You can point the bridge at
  another file with `plug_KEY_PATH`. At start the bridge logs
  `OWNS <ids> listener=<host> adapter=<hciN> mode=...`, then `NO_KEY_OWNED <id>`
  for any owned plug with no key line, and `KEY_FILE ... mode 644, want 600` if
  the file is readable by others. Keys are never logged.

## Python packages (venv)

Both units run `/home/operator/govee-ble-venv/bin/python -m govee_h5082`. That venv needs
**bleak**, **paho-mqtt** and **dbus-fast**. The Pi 5 venv (made for the RSSI-only
listener) had paho-mqtt 2.1.0 and dbus-fast but **no bleak**, so the bridge died with
`ModuleNotFoundError: No module named 'bleak'`. Fix it as `operator`, not root:

```bash
~/govee-ble-venv/bin/pip install bleak paho-mqtt      # plug-09-28: bleak 3.0.2
~/govee-ble-venv/bin/python -c 'import bleak, paho.mqtt, dbus_fast' && echo ok
```

`scripts/install_plug_bridge.sh` runs that import check before it touches systemd.
If the check fails, the script stops and prints the pip command.

The bridge works with bleak 3.x (live on the Pi 5, 3.0.2) and with older bleak (the
Pi 4 venv may be older). Adapter pinning differs between them: bleak >= 3.0 takes
`bluez={"adapter": "hciN"}`, while older bleak ignores that and needs `adapter="hciN"`,
or else it uses the default adapter (`hci0`, Victron on the Pi 4). The bridge picks
the right form from the installed version and logs it at start as
`OWNS ... bleak=<version>`.

## Files

| File | What |
|---|---|
| `systemd/h5082-mqtt.service` | Pi 4 unit (`solar-broker`, `hci1`). Reads the optional `~/.config/plug-bridge.env`. |
| `systemd/h5082-mqtt-apps.service` | `` unit (`apps`, `hci0` = the `.229` UB500), runs as `ansible`. Host file `/home/operator/.config/plug-bridge.env` (`plug_PLUGS=plug-2`, `plug_KEY_PATH=/home/operator/.govee-plug-keys`), MQTT from `/home/operator/.config/h5082-mqtt.env`. |
| `systemd/h5082-mqtt-monitor.service` | Pi 5 unit, installed as **`h5082-mqtt.service`** (`monitor`, `hci0`, MQTT from `hosts/monitor/mqtt.env`). The host file is required here. It replaces `h5082-rssi-monitor`, since it also publishes monitor RSSI. |
| `scripts/install_plug_bridge.sh --host solar-broker\|monitor [--dry-run]` | Checks that the venv can import bleak / paho.mqtt / dbus_fast, then copies the unit, runs daemon-reload, enables and restarts the bridge, and creates a template host file if it is missing. It checks that the key file exists with mode 600 but never reads it. On monitor it disables `h5082-rssi-monitor`. |
| `scripts/plug_rssi_scan.py --adapter hciN [--seconds 30]` | Read-only scan. For each plug it prints samples, best and average RSSI, and last seen, so you can see which Pi hears it best. It never connects and never reads keys, and it refuses `hci0` on the Pi 4. |

## Host file

`/home/operator/.config/plug-bridge.env` (mode 600, owner `operator`). It holds no
secrets, but it is per host and stays out of git. Shared mode (live):

```text
# Pi 4
plug_SHARED=1
```

```text
#  (apps), /home/operator/.config/plug-bridge.env
plug_SHARED=1
plug_KEY_PATH=/home/operator/.govee-plug-keys
```

```text
# Pi 5
plug_SHARED=1
plug_ADAPTER=hci0
```

Per-host mode instead lists the owned plugs, for example `plug_PLUGS=plug-4` on the
Pi 5. Do not mix the two modes on the same plugs.

## Which Pi should own a plug

Run the helper on each Pi for the same 30 s, then give the plug to the Pi with
the better **best** and **avg** values and more samples:

```bash
cd /home/operator/victron-ble2mqtt-integration
/home/operator/govee-ble-venv/bin/python scripts/plug_rssi_scan.py --adapter hci1 --seconds 30   # Pi 4
/home/operator/govee-ble-venv/bin/python scripts/plug_rssi_scan.py --adapter hci0 --seconds 30   # Pi 5
```

A plug that a bridge is connected to stops advertising until its link goes idle
(about 2 min). A plug you just switched may therefore show 0 samples. Wait
2 minutes and run it again. The **Heard by** sensors in HA give the same hint
over a longer time. They are advice only: `plug_PLUGS` decides which Pi drives
a plug.

## Move a plug to the other Pi later

Example: move `plug-6` from the Pi 4 to the Pi 5.

1. **Old Pi (Pi 4):** remove `plug-6` from `plug_PLUGS` in
   `~/.config/plug-bridge.env`, then `sudo systemctl restart h5082-mqtt`. Its
   log shows `OWNS` without `plug-6`. HA shows the `plug-6` sockets unavailable
   until the new Pi takes over.
2. **New Pi (Pi 5):** copy that plug's key line by hand (see "Copy a key line"
   below, with the plug's MAC) into `~/.govee-plug-keys` (keep mode 600). Add `plug-6` to
   `plug_PLUGS`, then run `sudo systemctl restart h5082-mqtt`. Its log shows
   `OWNS ... plug-6` and no `NO_KEY_OWNED plug-6`.
3. **HA:** reload MQTT (**Settings > Devices & services > MQTT > ⋮ > Reload**). HA can
   keep the old entity config (the old Pi's availability topic) until this is done.
4. Toggle a `plug-6` socket in HA, then run `journalctl -u h5082-mqtt -n 30` on the
   new Pi and look for `SET plug-6 <side> ON|OFF`. There must be no `OWNER_CONFLICT`
   on either Pi.
5. Optional: delete the moved line from the old Pi's key file. The bridge does
   not need it there any more.

Always remove the plug from the old Pi first, so that two Pis never drive one
plug.

## Copy a key line from one Pi to the other

The Pis have no SSH key between them (scp from the Pi 5 to the Pi 4 gave
`Permission denied (publickey)`), so copy the one line by hand. Use the plug's
full MAC (`plug-4` is `AA:BB:CC:DD:EE:FF`, see `PLUGS` in `govee_h5082/mqtt_bridge.py`).

**On the Pi that has the key (Pi 4):** print only that line. It shows the key on
your screen; copy it into the other Pi's file and nowhere else.

```bash
grep -i '^AA:BB:CC:DD:EE:FF ' ~/.govee-plug-keys
```

**On the Pi that needs it (Pi 5):**

```bash
[ -f ~/.govee-plug-keys ] || install -m 600 /dev/null ~/.govee-plug-keys   # only if missing
nano ~/.govee-plug-keys          # paste that one line, save
chmod 600 ~/.govee-plug-keys
wc -l ~/.govee-plug-keys         # one line per plug this Pi owns
```

Optional alternative, only if this Pi has an SSH key on the other Pi:

```bash
umask 077
scp operator@solar-broker:.govee-plug-keys ~/h5082-keys.solar-broker.tmp
grep -i '^AA:BB:CC:DD:EE:FF ' ~/h5082-keys.solar-broker.tmp >> ~/.govee-plug-keys
rm -f ~/h5082-keys.solar-broker.tmp
chmod 600 ~/.govee-plug-keys
```

## After starting or changing a bridge: reload MQTT in HA

After both bridges are up, and after any plug moves, reload the MQTT integration:
**Settings > Devices & services > MQTT > ⋮ > Reload**. On 2026-09-28 HA kept the old
`plug-4` entity config and sent no commands for it until this reload. No entity edits
are needed.

## Checking logs and the broker

- Use `journalctl -u h5082-mqtt -n 30` (or `-f` while you toggle), not
  `--since "-2 min"`. The Pi 5 clock/timezone was an hour off, so `--since` showed
  nothing. Optional fix: `sudo timedatectl set-timezone America/New_York`.
- To see the claims and availability on the broker from the Pi 5 (not installed
  there by default):

  ```bash
  sudo apt install -y mosquitto-clients
  cd /home/operator/victron-ble2mqtt-integration
  set -a; source hosts/monitor/mqtt.env; set +a     # MQTT_HOST MQTT_PORT MQTT_USERNAME MQTT_PASSWORD
  mosquitto_sub -h "$MQTT_HOST" -p "${MQTT_PORT:-1883}" -u "$MQTT_USERNAME" -P "$MQTT_PASSWORD" \
    -t 'govee/plugs/+/owner' -t 'govee/plugs/bridge/+/status' -v -W 5
  ```

## Known limits

- The Pi 5 `hci0` is also scanned by Theengs. BlueZ merges scans from several
  clients, but on the Pi 5 onboard (Broadcom) radio, scanning while connecting
  can abort a connect. The bridge retries 3 times. If `plug-4` still logs
  `SET_FAIL` from the Pi 5, use a USB dongle as `hci1` and set
  `plug_ADAPTER=hci1`.
- Per-host mode: never list the same plug on both Pis. The claim topic warns you
  when it happens, but it does not stop a Pi. A shared bridge clears its own old
  claims at start and logs `OWNER_MIXED <id> claimed by <radio>` if a per-host
  bridge still claims a plug.
- Shared mode: two radios can still try the same plug at once if they rank it
  differently, for example when a link or signal message is in flight at the
  moment the command arrives. The plug takes one link. The other radio logs a failed try,
  and the command still lands.
- Shared mode: if a bridge loses the broker in the middle of a command, the state
  that command set is not published when it reconnects. HA keeps the old state until
  the plug's next advertisement change or the next command.
- The old retained `govee/plugs/bridge/status` value (`offline`) stays on the
  broker once the Pi 4 has an allowlist. Nothing uses it any more.
