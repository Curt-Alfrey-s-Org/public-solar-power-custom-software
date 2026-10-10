"""Deprecated KU estimate package, and the paired meter on the Now view."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "config" / "packages" / "solar_battery-1-estimates.yaml"
DASH = ROOT / "config" / "dashboards" / "solar-plant.yaml"


def test_battery_1_est_package_exists() -> None:
    text = PKG.read_text(encoding="utf-8")
    assert "battery-1-pwm_mppt_combined_est_power" in text
    assert "battery-2-battery-1-jumper_power" in text


def test_now_view_shows_100_50_not_a_live_75_15_tile() -> None:
    """KU 24 V shows the SmartSolar 100/50. The 75/15 is an unused note, not a live tile."""
    blob = DASH.read_text(encoding="utf-8")
    ku = blob.split("heading: KU 24 V", 1)[1].split("heading: KU outlet", 1)[0]
    assert "sensor.victron-mppt-1_solar_power" in ku
    assert "sensor.victron-mppt-1_solar" not in ku
    assert "Unused: three BlueSolar 75/15" in ku
    assert "sensor.battery-1-pwm_mppt_combined_est_power" not in blob
    assert "PWM+MPPT est" not in blob
