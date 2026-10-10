# H5082 coverage, live heard-by, dump UI

**Resume here:** Checkpoint 2 wait. Heard-by is live (closest RSSI). USB passthrough notes are written. Do not `qm set` until the dongle is in `lsusb` on `.229`.

Do **not** take Pi 4 `hci0` (Victron). Do **not** start a second scanner on Pi 5 `hci0` (Theengs). Do **not** invent plug watts. One checkpoint per session.

## Facts

| Radio | Role | H5082 |
|---|---|---|
| Pi 4 `hci1` | Solar-site listener + MQTT switches | All 8 |
| Pi 5 `hci0` | House Theengs, 12 s scan / 20 s | Five live (below) |
| `.229` USB → VM 105 | Server-room listener `apps`, RSSI + owns `plug-2` | UB500 `2357:0604` serial `3C789544E0FF` |
| `` USB → WSL Ubuntu | House listener `219`, RSSI only | usbipd attached; WSL kernel cannot load `rtl8761bu_fw.bin` |
| `` `` `.229` onboard | No Bluetooth | — |

H5082 BLE ads carry **on/off only** (manufacturer last byte: bit 1 left, bit 0 right). No watts, volts, or energy. Site solar cards cannot show plug watts until a meter exists.

Cooldown / min-on timers gate **dump automations only**. The HA switch and the physical button still work.

## Checkpoint 1 — Pi 5 house coverage `[x]`

Checked 2026-09-26, Theengs still owns `hci0`. Live RSSI (more negative = farther):

| Plug | RSSI | Notes |
|---|---|---|
| `plug-4` | −56 | Strongest |
| `plug-3` | −82 | In range |
| `plug-6` | −88 | In range |
| `plug-1` | −89 | Weak, still live |
| `plug-8` | −90 | Weak, still live |
| `plug-2` `plug-5` `plug-7` | — | Not on Pi 5. Solar-site / Pi 4. |

Five plugs are updating live on Pi 5. Where each plug is kept is the HA **Where** text, not this table. Do not add a second Pi 5 scanner.

## Checkpoint 2 — `.229` dongle into HA ``

`[x]` Commands are in [plug_USB_PASSTHROUGH.md](plug_USB_PASSTHROUGH.md).

`[x]` Dongle plugged in (`2357:0604` serial `3C789544E0FF`), `qm set 105` done, `` sees `hci0`, listener `apps` publishes RSSI and owns `plug-2`.

`` is Proxmox **VM 105** on `.229`. Official path: USB pass the dongle into that VM, then the HA Container uses it over the existing `/run/dbus` mount ([Bluetooth](https://www.home-assistant.io/integrations/bluetooth/), [USB devices in a VM](https://pve.proxmox.com/wiki/USB_Devices_in_Virtual_Machines)).

When the dongle is plugged in on `.229`:

1. `lsusb` → record `VID:PID` (never move the Pi 4 Victron dongle `2357:0604`).
2. `qm set 105 -usb0 host=VID:PID` (or the next free `usbN`).
3. On ``, confirm a new `hci*` appears. Map it into the `homeassistant` container if the VM sees it and the container does not.
4. HA Bluetooth should list that adapter. Do not start a Govee GATT bridge on it until ads are visible.

Prepare the commands in `docs/plug_USB_PASSTHROUGH.md` **before** the dongle arrives. Do not `qm set` until `lsusb` shows the new device.

## Checkpoint 3 — live “heard by” `[x]`

Closest RSSI owns the plug (tie: monitor, then apps, then solar-broker). Site solar **Heard by** is live. **Where** is the typed room.

Live sample 2026-09-26 (24 s, no extra scan):

| Plug | Pi 4 | Pi 5 | Owner |
|---|---|---|---|
| `plug-1` | −52 | −91 | solar-broker |
| `plug-6` | −54 | −93 | solar-broker |
| `plug-4` | −88 | −59 | **monitor** (closer to Pi 5 than to Pi 4) |
| `plug-3` | −82 | −82 | monitor (tie) |
| `plug-8` | −86 | −89 | solar-broker |
| `plug-2` | −98 | — | solar-broker |
| `plug-7` | −100 | — | solar-broker |
| `plug-5` | — | — | none this window |

`plug-4` is the one Pi 5 hears better. Pi 4 is no longer closer to it.

2026-09-28: `plug-4` switching from the Pi 4 times out (`GATT plug-4 ... TimeoutError`,
`SET_FAIL`). The Pi 5 now runs the full bridge for the plugs listed in its
`plug_PLUGS` (first `plug-4`). It replaces the RSSI-only `h5082-rssi-monitor` and still
publishes monitor RSSI. The bridge's short `find` scan on Pi 5 `hci0` is a BlueZ discovery
next to Theengs, not a second scanner process. **Heard by** is only advice; the
allowlist decides which Pi drives a plug. See [plug_MULTI_BRIDGE.md](plug_MULTI_BRIDGE.md).

## Checkpoint 4 — dump UI `[ ]`

| Now | Change to |
|---|---|
| Dump dwell | **Auto waits** (min-on / cooldown). Manual switch and the plug button ignore these. |
| Dump voltages | Keep the name. Put a short markdown **at the top** of the card: float / re-bulk volts, min solar, min SoC, confirm delay. |
| Dump limits | Rename **Bus caps**. Markdown at the top: AC watt cap and max battery discharge per bus. |

Weblinks at the bottom of those cards move up into that markdown. Do not block the operator from changing helpers or toggling a socket while a timer is running.

## Checkpoint 5 — watts `[ ]`

No work. H5082 does not send watts. Leave the cards without a W reading.

## Where the next session starts

Checkpoint **2** wait: plug the dongle into `.229`, then `lsusb` and `qm set 105`. Checkpoint **4** is dump UI.
