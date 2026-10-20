# Rack Theengs (``)

Listener for the TP-Link UB500 passed through from Proxmox `.229` into VM 105.
Adapter `hci0`, address `AA:BB:CC:DD:EE:FF`. Publishes to Mosquitto on this host.
Home Assistant reads MQTT. Do not add devices from the Bluetooth integration.

`mqtt.env` is local (gitignored `*.env`). It is copied from `ha-discovery.env`
keys `MQTT_USER` and `MQTT_PASSWORD`, with `MQTT_HOST=127.0.0.1`.

The hub file `theengs-gateway-v1.7.5.1.tar.gz` is the Pi **arm64** image.
`` needs `theengs-gateway-v1.7.5.1-amd64.tar.gz`. `pull_policy: never`
so Compose does not pull from Docker Hub.

Later: the other new dongle is on ``. Not this stack.
