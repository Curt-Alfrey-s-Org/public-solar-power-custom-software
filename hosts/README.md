# Host roles (one repo, two Raspberry Pis)

`scripts/deploy.sh` reads **`HOST_ROLE`** from `.env` (or guesses from the LAN IP).

| `HOST_ROLE` | Typical IP | What `deploy.sh` starts |
|-------------|------------|-------------------------|
| **solar-broker** (default) | `solar-broker` | Mosquitto, Victron BLE (exclusive onboard HCI), Home Assistant, optional Sungold; solar-broker Theengs off unless second adapter |
| **monitor** | `solar-broker` | AdGuard DNS, Theengs house BLE → Pi 4 MQTT, node_exporter |

Pi 5 details: [hosts/monitor/README.md](monitor/README.md) and [docs/monitor_HOUSE_EDGE.md](../docs/monitor_HOUSE_EDGE.md).
