# Public snapshot

This tree is a **scrubbed snapshot** of the private Victron BLE / MQTT / Home Assistant solar
integration. It is not a continuation of private git history. The source commit SHA is recorded
only on the operator build host under `public-exports/_tools/solar-source-sha.txt`.

## Configure before you run

1. Install and run **your own MQTT broker** on your LAN (for example Mosquitto).
2. Copy `config/hosts.example.env` to `config/hosts.env` and set `SOLAR_BROKER_HOST` (do not commit `hosts.env`).
3. Copy `swarm/example/.env.example` (or another `*.env.example` in this repo) to a local `.env` and set broker credentials.
4. Rename Home Assistant entity ids using **`config/entities.example.yaml`** — one map for your site.

Home Assistant MQTT entity naming: [MQTT integration](https://www.home-assistant.io/integrations/mqtt/).

## Example addresses (RFC 5737)

| Role | Variable | Address |
|------|----------|---------|
| MQTT / solar broker | `SOLAR_BROKER_HOST` | see `config/hosts.example.env` |
| Loopback | local services | `127.0.0.1` |
| All interfaces | bind when documented | `0.0.0.0` |

## VPN

Use your own private network path to reach Home Assistant when away from home. This snapshot does
not include vendor VPN install steps.

## Secrets

Long-lived Home Assistant tokens and MQTT passwords stay on the operator machine. See
`deploy/secrets/home-assistant/README.md`.
