#!/usr/bin/env python3
"""Read the LiTime pack with aiobmsble and publish Home Assistant MQTT discovery.

Library: aiobmsble 0.29.0 Redodo BMS (LiTime local name L-24*, service FFE0).
https://github.com/patman15/aiobmsble/blob/0.29.0/aiobmsble/bms/redodo_bms.py
Password: none. BMS_BLE README says turn a 6-digit Bluetooth password off in the
LiTime app and disconnect the phone.
https://github.com/patman15/BMS_BLE-HA#litime-batteries

Radio is hci1 only. hci0 is the Victron adapter and is never opened here.
Each poll uses BMSConfig(keep_alive=False), which disconnects after the read
so Theengs and the H5082 bridge keep scanning on hci1.
https://github.com/patman15/aiobmsble/blob/0.29.0/aiobmsble/basebms.py

Discovery: https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
Scanner adapter: https://bleak.readthedocs.io/en/latest/api/scanner.html
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from typing import Any

import paho.mqtt.client as mqtt
from bleak import BleakScanner
from bleak.exc import BleakError

from aiobmsble import BMSConfig
from aiobmsble.bms.redodo_bms import BMS

ADAPTER = "hci1"
ADDRESS = "AA:BB:CC:DD:EE:FF"
DEVICE_NAME = "L-24100BNN160-C03961"
# BMS_BLE default poll, custom_components/bms_ble/const.py UPDATE_INTERVAL.
INTERVAL_SEC = 30
DISCOVERY_PREFIX = "homeassistant"
NODE = "litime_c84780722a2f"
STATE_TOPIC = "litime/c84780722a2f/state"
AVAIL_TOPIC = "litime/c84780722a2f/availability"
CLIENT_ID = "litime-bms-solar-broker-hci1"
# Exit 3 is RestartPreventExitStatus in the systemd unit (do not retry a PIN).
EXIT_AUTH = 3

LOG = logging.getLogger("litime_bms_mqtt")

# Keys aiobmsble already returns. This script does not decode registers.
SCALAR_KEYS = (
    "voltage",
    "current",
    "battery_level",
    "power",
    "temperature",
    "cycles",
    "cycle_charge",
    "design_capacity",
)


def _num(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    # TempSensor implements __float__.
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def flatten_sample(sample: dict[str, Any]) -> dict[str, Any]:
    """Copy library fields into a JSON object. Skip anything we cannot encode."""
    out: dict[str, Any] = {}
    for key in SCALAR_KEYS:
        num = _num(sample.get(key))
        if num is None:
            continue
        if isinstance(num, float):
            out[key] = round(num, 3)
        else:
            out[key] = num
    if "problem" in sample:
        out["problem"] = bool(sample["problem"])
    cells = sample.get("cell_voltages")
    if isinstance(cells, list) and cells:
        encoded: list[float] = []
        for cell in cells:
            num = _num(cell)
            if num is None:
                continue
            encoded.append(round(float(num), 3))
        if encoded:
            out["cell_voltages"] = encoded
    return out


def device_block() -> dict[str, Any]:
    return {
        "identifiers": [NODE],
        "name": DEVICE_NAME,
        "manufacturer": "LiTime",
        "model": DEVICE_NAME,
        "via_device": "solar-broker-hci1",
    }


def origin_block() -> dict[str, str]:
    return {
        "name": "litime-bms-mqtt",
        "sw": "aiobmsble 0.29.0",
        "url": "https://github.com/patman15/aiobmsble/blob/0.29.0/aiobmsble/bms/redodo_bms.py",
    }


def sensor_configs() -> list[tuple[str, str, dict[str, Any]]]:
    """Return (component, object_id, payload) discovery messages."""
    common = {
        "state_topic": STATE_TOPIC,
        "availability_topic": AVAIL_TOPIC,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": device_block(),
        "origin": origin_block(),
    }
    rows: list[tuple[str, str, dict[str, Any]]] = [
        (
            "sensor",
            "voltage",
            {
                **common,
                "name": "Voltage",
                "default_entity_id": "sensor.litime-battery-1_voltage",
                "unique_id": f"{NODE}_voltage",
                "device_class": "voltage",
                "state_class": "measurement",
                "unit_of_measurement": "V",
                "suggested_display_precision": 2,
                "value_template": "{{ value_json.voltage }}",
                "expire_after": 120,
            },
        ),
        (
            "sensor",
            "soc",
            {
                **common,
                "name": "State of charge",
                "default_entity_id": "sensor.litime-battery-1_soc",
                "unique_id": f"{NODE}_soc",
                "device_class": "battery",
                "state_class": "measurement",
                "unit_of_measurement": "%",
                "suggested_display_precision": 0,
                "value_template": "{{ value_json.battery_level }}",
                "expire_after": 120,
            },
        ),
        (
            "sensor",
            "current",
            {
                **common,
                "name": "Current",
                "default_entity_id": "sensor.litime-battery-1_current",
                "unique_id": f"{NODE}_current",
                "device_class": "current",
                "state_class": "measurement",
                "unit_of_measurement": "A",
                "suggested_display_precision": 2,
                "value_template": "{{ value_json.current }}",
                "expire_after": 120,
            },
        ),
        (
            "sensor",
            "power",
            {
                **common,
                "name": "Power",
                "default_entity_id": "sensor.litime-battery-1_power",
                "unique_id": f"{NODE}_power",
                "device_class": "power",
                "state_class": "measurement",
                "unit_of_measurement": "W",
                "suggested_display_precision": 0,
                "value_template": "{{ value_json.power }}",
                "expire_after": 120,
            },
        ),
        (
            "sensor",
            "temperature",
            {
                **common,
                "name": "Temperature",
                "default_entity_id": "sensor.litime-battery-1_temperature",
                "unique_id": f"{NODE}_temperature",
                "device_class": "temperature",
                "state_class": "measurement",
                "unit_of_measurement": "°C",
                "suggested_display_precision": 1,
                "value_template": "{{ value_json.temperature }}",
                "expire_after": 120,
            },
        ),
        (
            "sensor",
            "cycles",
            {
                **common,
                "name": "Charge cycles",
                "default_entity_id": "sensor.litime-battery-1_cycles",
                "unique_id": f"{NODE}_cycles",
                "state_class": "total_increasing",
                "value_template": "{{ value_json.cycles }}",
                "expire_after": 120,
            },
        ),
        (
            "binary_sensor",
            "problem",
            {
                **common,
                "name": "Problem",
                "default_entity_id": "binary_sensor.litime-battery-1_problem",
                "unique_id": f"{NODE}_problem",
                "device_class": "problem",
                "payload_on": "ON",
                "payload_off": "OFF",
                "value_template": "{{ 'ON' if value_json.problem else 'OFF' }}",
            },
        ),
    ]
    return rows


def auth_rejection(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}"
    markers = (
        "authenticationfailed",
        "authenticationcanceled",
        "authenticationrejected",
        "org.bluez.error.rejected",
        "insufficientencryption",
        "encryptionfailed",
    )
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def mqtt_client() -> mqtt.Client:
    host = os.environ.get("MQTT_HOST", "").strip()
    port_s = os.environ.get("MQTT_PORT", "1883").strip()
    user = os.environ.get("MQTT_USERNAME", "").strip()
    password = os.environ.get("MQTT_PASSWORD", "")
    if not host or not user or not password:
        LOG.error("MQTT_HOST, MQTT_USERNAME, and MQTT_PASSWORD must be set")
        raise SystemExit(4)
    try:
        port = int(port_s)
    except ValueError:
        LOG.error("MQTT_PORT is not an integer")
        raise SystemExit(4) from None
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(user, password)
    client.will_set(AVAIL_TOPIC, payload="offline", qos=1, retain=True)
    try:
        client.connect(host, port, keepalive=60)
    except OSError as exc:
        LOG.error("MQTT connect failed (%s)", type(exc).__name__)
        raise SystemExit(4) from None
    client.loop_start()
    return client


def publish(client: mqtt.Client, topic: str, payload: str, retain: bool = True) -> None:
    info = client.publish(topic, payload, qos=1, retain=retain)
    info.wait_for_publish(timeout=10)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        LOG.error("MQTT publish failed rc=%s topic=%s", info.rc, topic)
        raise SystemExit(4)


def publish_discovery(client: mqtt.Client) -> None:
    for component, object_id, payload in sensor_configs():
        topic = f"{DISCOVERY_PREFIX}/{component}/{NODE}/{object_id}/config"
        publish(client, topic, json.dumps(payload, separators=(",", ":")))


def publish_reading(client: mqtt.Client, reading: dict[str, Any]) -> None:
    body = dict(reading)
    # Binary sensor template reads problem as a boolean in JSON.
    publish(client, STATE_TOPIC, json.dumps(body, separators=(",", ":")))
    publish(client, AVAIL_TOPIC, "online")


async def read_once() -> dict[str, Any]:
    device = await BleakScanner.find_device_by_address(
        ADDRESS,
        timeout=20.0,
        bluez={"adapter": ADAPTER},
    )
    if device is None:
        raise LookupError(f"{ADDRESS} not found on {ADAPTER}")
    path = ""
    details = getattr(device, "details", None)
    if isinstance(details, dict):
        path = str(details.get("path", ""))
    LOG.info("found %s name=%s path=%s", device.address, device.name, path)
    if "/hci0/" in path or path.endswith("/hci0"):
        raise RuntimeError(f"refusing device path on hci0: {path}")
    if "/hci1/" not in path:
        raise RuntimeError(f"device path is not hci1: {path or 'missing'}")
    bms = BMS(ble_device=device, config=BMSConfig(keep_alive=False))
    try:
        sample = await bms.async_update()
    finally:
        if bms.is_connected:
            await bms.disconnect()
    if not isinstance(sample, dict):
        raise RuntimeError("aiobmsble returned no sample")
    reading = flatten_sample(sample)
    voltage = reading.get("voltage")
    if not isinstance(voltage, (int, float)) or voltage <= 0:
        raise RuntimeError("sample has no positive voltage")
    return reading


async def run(once: bool) -> int:
    client = mqtt_client()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    failures = 0
    try:
        while not stop.is_set():
            started = time.monotonic()
            try:
                reading = await read_once()
            except LookupError as exc:
                failures += 1
                LOG.error("%s", exc)
                if once or failures >= 3:
                    publish(client, AVAIL_TOPIC, "offline")
                    return 2
            except (BleakError, TimeoutError, EOFError, ConnectionError, OSError) as exc:
                LOG.error("read failed (%s): %s", type(exc).__name__, exc)
                if auth_rejection(exc):
                    publish(client, AVAIL_TOPIC, "offline")
                    LOG.error(
                        "connection rejected; turn the 6-digit Bluetooth password off "
                        "in the LiTime app and disconnect the phone"
                    )
                    return EXIT_AUTH
                failures += 1
                if once or failures >= 3:
                    publish(client, AVAIL_TOPIC, "offline")
                    return 1
            except RuntimeError as exc:
                LOG.error("%s", exc)
                publish(client, AVAIL_TOPIC, "offline")
                return 1
            else:
                failures = 0
                publish_discovery(client)
                publish_reading(client, reading)
                LOG.info(
                    "voltage=%s soc=%s current=%s",
                    reading.get("voltage"),
                    reading.get("battery_level"),
                    reading.get("current"),
                )
                if once:
                    return 0
            elapsed = time.monotonic() - started
            try:
                await asyncio.wait_for(stop.wait(), timeout=max(1.0, INTERVAL_SEC - elapsed))
            except TimeoutError:
                continue
        publish(client, AVAIL_TOPIC, "offline")
        return 0
    finally:
        client.loop_stop()
        client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="LiTime BMS to MQTT via aiobmsble on hci1")
    parser.add_argument(
        "--once",
        action="store_true",
        help="one connect/read/disconnect, then exit",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if ADAPTER != "hci1":
        LOG.error("adapter must be hci1")
        raise SystemExit(1)
    code = asyncio.run(run(once=args.once))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
