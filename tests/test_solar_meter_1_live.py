"""Site meter-1 live wrappers for A3/B3."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "config" / "packages" / "solar_meter-1_live.yaml"
DASH = ROOT / "config" / "dashboards" / "solar-plant.yaml"


def test_meter_1_live_package() -> None:
    text = PKG.read_text(encoding="utf-8")
    assert "meter-1_a3_power" in text
    assert "sungold-inverter-1_grid_voltage" in text


def test_dashboard_uses_meter_1() -> None:
    blob = DASH.read_text(encoding="utf-8")
    assert "sensor.meter-1_a3_power" in blob
    assert "sensor.meter-1_a3_power" not in blob.split("History")[0]
