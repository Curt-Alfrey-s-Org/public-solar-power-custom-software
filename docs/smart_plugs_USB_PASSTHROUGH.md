# USB Bluetooth dongle: `.229` → HA VM 105

Official: [USB Devices in Virtual Machines](https://pve.proxmox.com/wiki/USB_Devices_in_Virtual_Machines), [HA Bluetooth](https://www.home-assistant.io/integrations/bluetooth/).

`` is Proxmox **VM 105** on `.229`. Pass the dongle into that VM. The listener stick on `.229` is a TP-Link UB500,
`2357:0604`, serial `3C789544E0FF`, USB bus 1 port 4 (12 Mb/s). The Pi 4 Victron
stick is the same model and the same id, and it stays on the Pi 4. `qm set` on
`.229` can only see the stick plugged into `.229`.

## When the stick is plugged into `.229`

```bash
ssh root@solar-broker
lsusb -d 2357:0604
qm config 105 | grep -i usb
qm set 105 -usb0 host=2357:0604
```

On ``:

```bash
ls /sys/class/bluetooth
hciconfig
sudo docker exec homeassistant ls /sys/class/bluetooth
```

If the VM sees `hci*` and the container does not, add that device to the HA compose and recreate the container. HA Bluetooth should then list the adapter. Heard-by already lists `ha-105` (`sensor.ihoment_plug_*_rssi_apps`).

Do not start a Govee GATT bridge on this radio in this checkpoint.

VM 105 stays running. `qm set` stores the assignment.
[Assign devices to an already running VM](https://pve.proxmox.com/wiki/USB_Devices_in_Virtual_Machines)
attaches it now, because this stick is USB full speed (12 Mb/s), not USB 3:

```bash
printf 'device_add usb-host,vendorid=0x2357,productid=0x0604,id=ub500listener\n' | qm monitor 105
```

On `` the bridge is `apps` (unit `h5082-mqtt-apps.service`). It publishes
RSSI for every plug it hears and owns `plug-2`, the plug only this radio reaches.
Ownership: [plug_MULTI_BRIDGE.md](plug_MULTI_BRIDGE.md).

