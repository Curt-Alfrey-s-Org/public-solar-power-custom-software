#!/usr/bin/env python3
"""Populate the solar-broker Lovelace dashboard with victron-ble2mqtt host metrics."""
import json
from pathlib import Path

STORAGE = Path("/opt/homeassistant/.storage/lovelace.dashboard_solar-broker")

SECTIONS = [
    ("System", [
        "sensor.solar-broker_hostname",
        "sensor.solar-broker_system_up_time",
        "sensor.solar-broker_total_cpu_usage",
        "sensor.solar-broker_process_cpu_usage",
        "sensor.solar-broker_system_load_1min",
        "sensor.solar-broker_temperature_cpu_thermal",
        "sensor.solar-broker_swap_usage",
        "sensor.solar-broker_cpu_frequency",
    ]),
    ("Wi-Fi", [
        "sensor.solar-broker_wifi_device_name",
        "sensor.solar-broker_essid",
        "sensor.solar-broker_signal_level",
        "sensor.solar-broker_link_quality",
        "sensor.solar-broker_frequency",
        "sensor.solar-broker_bit_rate",
    ]),
    ("Network", [
        "sensor.solar-broker_wlan0_received_rate",
        "sensor.solar-broker_wlan0_sent_rate",
        "sensor.solar-broker_eth0_received_rate",
        "sensor.solar-broker_eth0_sent_rate",
        "sensor.solar-broker_wan0_received_rate",
        "sensor.solar-broker_wan0_sent_rate",
    ]),
]


def tile(entity_id: str) -> dict:
    return {"type": "tile", "entity": entity_id}


def section(title: str, entities: list[str]) -> dict:
    cards = [{"type": "heading", "heading": title}]
    cards.extend(tile(e) for e in entities)
    return {"type": "grid", "cards": cards, "column_span": 3}


data = {
    "version": 1,
    "minor_version": 1,
    "key": "lovelace.dashboard_solar-broker",
    "data": {
        "config": {
            "views": [
                {
                    "title": "solar-broker",
                    "type": "sections",
                    "sections": [section(title, entities) for title, entities in SECTIONS],
                }
            ]
        }
    },
}

STORAGE.parent.mkdir(parents=True, exist_ok=True)
STORAGE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"wrote {STORAGE}")
