# Docker build pattern — victron-ble2mqtt-integration

This image uses **`python:3.11-bookworm`** plus **`pip install -r requirements.lock`**. When the Pi has **`./wheels`** populated from the hub hub, builds use **`PIP_OFFLINE=1`** (`--no-index --find-links`) — same hub-wheel convention as **alfa-ai** ([`docs/HUB_ARTIFACTS.md`](https://github.com/example/alfa-ai/blob/main/docs/HUB_ARTIFACTS.md)).

| Situation | What to do |
|-----------|------------|
| Normal Pi / internet | `sudo bash scripts/deploy.sh` — **`PIP_OFFLINE=0`** if `./wheels` has no `.whl` files. |
| LAN + NFS **`/mnt/cluster`** mounted | **`deploy.sh`** auto-mounts when **`ENSURE_hub_NFS_MOUNT=1`** (default) if `` pings and **`wheels/victron`** was missing — or run **`sudo bash scripts/mount-hub-hub.sh`** once. Then **`deploy.sh`** syncs **`./wheels`** and builds with **`PIP_OFFLINE=1`** when `.whl` files exist. |
| Seed wheels on `` | `sudo bash alfa-ai/scripts/seed-victron-wheels-hub.sh` (arm64 + amd64). |
| Large base images | **`deploy.sh`** merges **`registry-mirrors: ["http://solar-broker"]`** into **`daemon.json`** so Docker Hub pulls use the LAN mirror. **Home Assistant** comes from **GHCR** (pinned tag in `docker-compose.homeassistant.yml`) — mirror via **`docker pull`** of that tag on `` then **`alfa-ai/scripts/publish-built-image-to-hub.sh`** → **`home-assistant-2026.7.3.tar.gz`** (legacy **`home-assistant-stable.tar.gz`** still accepted); **`deploy.sh`** **`docker load`**s from **`/mnt/cluster/docker-images/`** when present. |

Manual rebuild:

```bash
bash scripts/sync-victron-wheels-from-hub.sh   # when hub mounted
export PIP_OFFLINE=1    # if wheels present
docker compose -f docker-compose.victron.yml build --build-arg PIP_OFFLINE="${PIP_OFFLINE:-0}"
```

Shared vocabulary: **`/home/operator/docs/DOCKER_BUILD_PATTERNS.md`** on the dev server.
