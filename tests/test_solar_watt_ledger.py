"""Watt hop ledger: B residual stays None without B Renogy DC."""

from __future__ import annotations

import sys
from math import isclose
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from solar_watt_ledger import (  # noqa: E402
    _CONVERSION_HOP_IDS,
    apply_ledger_to_meta,
    build_watt_ledger,
    battery_1_equal_share_w,
    battery_1_unmetered_pv_residual,
)


def _row(eid: str, state: str) -> dict:
    return {"entity_id": eid, "state": state}


def test_battery_1_unmetered_pv_residual_formula() -> None:
    assert isclose(battery_1_unmetered_pv_residual(80.3, 4.5, 400.0), 475.8, rel_tol=1e-6)
    assert battery_1_unmetered_pv_residual(80.3, 4.5, None) is None
    assert isclose(battery_1_unmetered_pv_residual(-803.4, 223.4, 0.0), -1026.8, rel_tol=1e-6)
    assert battery_1_unmetered_pv_residual(-803.4, 223.4, None) is None


def test_battery_1_unmetered_pv_est_stays_none_without_renogy_dc() -> None:
    states = {
        "sensor.victron-mppt-1_solar_power": _row(
            "sensor.victron-mppt-1_solar_power", "250"
        ),
        "sensor.battery_1_power": _row("sensor.battery_1_power", "26.6"),
        "sensor.battery_2_power": _row("sensor.battery_2_power", "-803.4"),
    }
    ledger = build_watt_ledger(states)
    assert ledger["jumper_w"] is None
    assert ledger["battery-1-unmetered_pv_est_w"] is None
    assert ledger["battery-1-unmetered_pv_est_kind"] is None
    hops = {h["id"]: h for h in ledger["watt_hops"]}
    assert "battery-1-victron_pwm" not in hops
    hop = hops["battery-1-victron_mppt"]
    assert hop["unmetered"] is False
    assert hop["watts_in"] == 250.0
    assert hop["loss_w"] is None
    meta: dict = {}
    apply_ledger_to_meta(meta, states, 250.0)
    assert meta["battery-1-unmetered_pv_est_w"] is None


def test_battery_1_renogy_ac_est_is_batt2_load_not_shunt() -> None:
    states = {
        "sensor.victron-mppt-1_solar_power": _row(
            "sensor.victron-mppt-1_solar_power", "150"
        ),
        "sensor.battery_1_power": _row("sensor.battery_1_power", "225"),
        "sensor.battery_2_power": _row("sensor.battery_2_power", "276"),
        "sensor.meter-1_a3_power": _row("sensor.meter-1_a3_power", "25"),
    }
    ledger = build_watt_ledger(states)
    # victron-mppt-1 is the paired B meter, so solar W minus Battery 1 is not the jumper.
    assert ledger["jumper_w"] is None
    assert isclose(ledger["battery-1-renogy_ac_est_w"], 25.0, rel_tol=1e-6)
    assert ledger["battery-1-unmetered_pv_est_w"] is None
    assert ledger["battery-1-unmetered_pv_est_kind"] == "ac_lower_bound"
    assert ledger["battery-1-charger_equal_share_w"] is None
    hops = {h["id"]: h for h in ledger["watt_hops"]}
    assert hops["battery-1-battery"]["stored_w"] == 276.0
    assert hops["battery-1-renogy_ac"]["watts_in"] == 25.0
    assert hops["battery-1-renogy_ac"]["watts_in"] != hops["battery-1-battery"]["stored_w"]
    assert hops["battery-1-victron_mppt"]["unmetered"] is False
    assert hops["battery-1-victron_mppt"]["watts_in"] == 150.0
    assert "battery-1-victron_pwm" not in hops
    assert isclose(battery_1_equal_share_w(376.0), 376.0 / 2.0, rel_tol=1e-6)
    assert not isclose(battery_1_equal_share_w(376.0), (276.0 + 25.0) / 2.0, rel_tol=1e-6)


def test_battery_1_renogy_ac_uses_max_trailer_ct_and_uti() -> None:
    states = {
        "sensor.meter-1_a3_power": _row("sensor.meter-1_a3_power", "25"),
        "sensor.sungold-inverter-1_grid_voltage": _row(
            "sensor.sungold-inverter-1_grid_voltage", "117"
        ),
        "sensor.sungold-inverter-1_grid_current": _row(
            "sensor.sungold-inverter-1_grid_current", "0"
        ),
        "sensor.sungold-inverter-1_load_active_power": _row(
            "sensor.sungold-inverter-1_load_active_power", "5"
        ),
    }
    ledger = build_watt_ledger(states)
    assert ledger["sungold_ac_in_w"] == 0.0
    assert ledger["uti_hop_w"] == 5.0
    assert ledger["vent_fan_w"] == 0.0
    assert ledger["battery-1-renogy_ac_est_w"] == 25.0
    hops = {h["id"]: h for h in ledger["watt_hops"]}
    assert hops["vent_fan"]["watts_in"] == 0.0
    assert hops["battery-1-renogy_ac"]["watts_in"] == 25.0


def test_sungold_ac_in_passthrough_from_load_when_grid_va_zero() -> None:
    states = {
        "sensor.meter-1_a3_power": _row("sensor.meter-1_a3_power", "25"),
        "sensor.sungold-inverter-1_grid_voltage": _row(
            "sensor.sungold-inverter-1_grid_voltage", "117"
        ),
        "sensor.sungold-inverter-1_grid_current": _row(
            "sensor.sungold-inverter-1_grid_current", "0"
        ),
        "sensor.sungold-inverter-1_load_active_power": _row(
            "sensor.sungold-inverter-1_load_active_power", "5"
        ),
    }
    ledger = build_watt_ledger(states)
    assert ledger["sungold_ac_in_w"] == 0.0
    assert ledger["uti_hop_w"] == 5.0
    hops = {h["id"]: h for h in ledger["watt_hops"]}
    assert hops["ac_a3_uti"]["watts_in"] == 5.0
    assert hops["sungold"]["watts_in"] == 0.0


def test_combined_path_losses_and_vent_fan_not_conversion() -> None:
    states = {
        "sensor.victron-mppt-1_solar_power": _row(
            "sensor.victron-mppt-1_solar_power", "150"
        ),
        "sensor.battery_1_power": _row("sensor.battery_1_power", "225"),
        "sensor.battery_2_power": _row("sensor.battery_2_power", "276"),
        "sensor.meter-1_a3_power": _row("sensor.meter-1_a3_power", "25"),
    }
    ledger = build_watt_ledger(states)
    conv = float(ledger["combined_losses_w"])
    vdrop = float(ledger["combined_vdrop_loss_w"])
    path = float(ledger["combined_path_losses_w"])
    assert isclose(path, conv + vdrop, rel_tol=1e-6)
    assert "vent_fan" not in _CONVERSION_HOP_IDS
    hops = {h["id"]: h for h in ledger["watt_hops"]}
    assert hops["vent_fan"]["id"] == "vent_fan"
    assert hops["vent_fan"].get("loss_w") in (None, 0.0)
