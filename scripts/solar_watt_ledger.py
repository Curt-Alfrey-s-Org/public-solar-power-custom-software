"""End-to-end watt hops from panel current/power through conversion losses.

Keep a copy in victron-ble2mqtt-integration/scripts/solar_watt_ledger.py.

Battery charge is storage, not loss. sensor.victron-mppt-1_* is the paired
B BlueSolar 75/15, not the A SmartSolar 100/50 (no HA entity until its
Instant Readout key exists). The second B 75/15 and the A 100/50 are
unmetered, so the combined loss total stays incomplete.

Formula source: victron docs/SOLAR_POWER_BALANCE.md. SmartShunt sign:
https://www.victronenergy.com/media/pg/SmartShunt/en/operation.html
Sungold energy split: reprint §4.1 AC INPUT + PV vs battery input + INV OUTPUT LOAD.
"""

from __future__ import annotations

from typing import Any

_SOLAR_IDS = (
    "sensor.victron-mppt-1_solar_power",
    "sensor.victron-mppt-1_solar",
)
_battery_2_PV_IDS = ("sensor.victron-mppt-1_solar_power",)
_battery_2_BATT_W_IDS = ("sensor.victron-mppt-1_battery_power",)
_battery_2_BATT_A_IDS = ("sensor.victron-mppt-1_battery_current",)
_CHARGE_IDS = ("sensor.victron-mppt-1_charging_power",)
_MPPT_LOAD_IDS = ("sensor.victron-mppt-1_load_power",)
_MPPT_V_IDS = ("sensor.victron-mppt-1_battery",)
_MPPT_A_IDS = ("sensor.victron-mppt-1_battery_charging",)
_BATT1_W_IDS = ("sensor.battery_1_power",)
_BATT1_V_IDS = ("sensor.battery_1_voltage", "sensor.battery_1_battery_voltage")
_BATT1_A_IDS = ("sensor.battery_1_current", "sensor.battery_1_battery_current")
_BATT2_W_IDS = ("sensor.battery_2_power",)
_BATT2_V_IDS = ("sensor.battery_2_voltage", "sensor.battery_2_battery_voltage")
_BATT2_A_IDS = ("sensor.battery_2_current", "sensor.battery_2_battery_current")
_A3_IDS = ("sensor.meter-1_a3_power",)
_A3_V_IDS = ("sensor.meter-1_a3_voltage",)
_A3_A_IDS = ("sensor.meter-1_a3_current",)
_B3_IDS = ("sensor.meter-1_b3_power",)
_SG_PV_IDS = ("sensor.sungold-inverter-1_pv_power",)
_SG_PV_V_IDS = ("sensor.sungold-inverter-1_pv_voltage",)
_SG_PV_A_IDS = ("sensor.sungold-inverter-1_pv_current",)
_SG_BATT_IDS = ("sensor.sungold-inverter-1_charging_power",)
_SG_LOAD_IDS = (
    "sensor.sungold-inverter-1_load_active_power",
    "sensor.sungold-inverter-1_load_power",
)
_SG_GRID_V_IDS = ("sensor.sungold-inverter-1_grid_voltage",)
_SG_GRID_A_IDS = ("sensor.sungold-inverter-1_grid_current",)


def _parse_float_state(state_row: dict[str, Any] | None) -> float | None:
    if not state_row:
        return None
    raw = str(state_row.get("state") or "").strip().lower()
    if raw in ("unavailable", "unknown", "", "none", "nan"):
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _first_w(states: dict[str, dict[str, Any]], entity_ids: tuple[str, ...]) -> float | None:
    for eid in entity_ids:
        val = _parse_float_state(states.get(eid))
        if val is not None:
            return val
    return None


def _va_w(v: float | None, a: float | None) -> float | None:
    if v is None or a is None:
        return None
    return abs(v * a)


def battery_2_bus_load_w(states: dict[str, dict[str, Any]]) -> float:
    """Measured A bus load: Sungold charging_power only.

    Dump plugs have no watt meter. The 25 W dump minimum stays in the dump
    headroom rules and is not added here, or the silent 75/15 is that many
    watts above the charger-to-shunt difference.
    """
    sg = _first_w(states, _SG_BATT_IDS)
    if sg is None or sg < 0:
        return 0.0
    return sg


def _clamp_charger_display(w: float | None) -> float | None:
    if w is None:
        return None
    return max(0.0, w)


_battery_1_UNMETERED_PV_REASON = (
    "Paired B BlueSolar 75/15 is sensor.victron-mppt-1_*. "
    "The second B 75/15 and the A SmartSolar 100/50 have no HA power. "
    "Do not scale the paired meter by 2 or 3. PWM is removed."
)


def battery_1_unmetered_pv_residual(
    batt2_w: float | None,
    jumper_w: float | None,
    battery_1_renogy_dc_w: float | None,
) -> float | None:
    """Combined unmetered B MPPT PV from shunt balance.

    batt2_W ≈ battery-1-PV + jumper_into_B - battery-1-Renogy_DC
    jumper_w is signed A to B positive (solar_W - battery-2-Renogy - batt1_W).
    That leftover is already in both SmartShunt nets (shunt-to-shunt on
    SYSTEM MINUS). Subtract it here so A-sourced watts in batt2 are not
    labeled B PV. Do not add jumper into site solar/charge/load.
    SmartShunt +charge / -discharge:
    https://www.victronenergy.com/media/pg/SmartShunt/en/operation.html

    Returns None when any term is missing. Live site has no B Renogy DC clamp;
    callers may pass trailer A/C (|A3|) as a **lower bound** for battery-1-Renogy_DC
    (inverter DC in >= AC out). Do not invent efficiency. Do not substitute 0
    when A/C is missing.
    """
    if batt2_w is None or jumper_w is None or battery_1_renogy_dc_w is None:
        return None
    return batt2_w - jumper_w + battery_1_renogy_dc_w


battery_1_EQUAL_SHARE_CHARGERS = 2


def battery_1_equal_share_w(combined_pv_w: float | None) -> float | None:
    """Equal 1/2 of combined B PV lower bound across two BlueSolar 75/15 MPPT.

    Not (batt2 + load) / 2 -- that drops the jumper. No site derate between strings.
    """
    if combined_pv_w is None:
        return None
    return combined_pv_w / float(battery_1_EQUAL_SHARE_CHARGERS)


def battery_1_est_amps(watts: float | None, volts: float | None) -> float | None:
    if watts is None or volts is None or volts == 0:
        return None
    return watts / volts


_CONVERSION_HOP_IDS = frozenset({"battery-1-victron_mppt", "sungold"})
_DC_VDROP_HOP_IDS = frozenset({"battery-2-mppt_vdrop", "battery-2-battery-1-jumper"})
_AC_VDROP_HOP_IDS = frozenset({"ac_a3_uti"})


def _vdrop_fields(
    v_up: float | None,
    v_down: float | None,
    current: float | None,
) -> tuple[float | None, float | None, bool]:
    """Metered ΔV and conductor loss. Incomplete when V or I is missing.

    Victron Wiring Unlimited §2.7: V = I×R; cable loss P = I²R.
    With both-end voltages, ΔV = V_up − V_down and P ≈ |ΔV × I|
    (same as I²R when ΔV = I×R). Never invent AWG or length.
    https://www.victronenergy.com/media/pg/The_Wiring_Unlimited_book/en/theory.html
    """
    if v_up is None or v_down is None:
        return None, None, True
    delta = v_up - v_down
    if delta < 0:
        return 0.0, 0.0 if current is not None else None, False
    abs_dv = abs(delta)
    if current is None:
        return abs_dv, None, True
    return abs_dv, abs(abs_dv * current), False


def _hop(
    hop_id: str,
    label: str,
    watts_in: float | None,
    watts_out: float | None,
    *,
    stored_w: float | None = None,
    note: str = "",
    unmetered: bool = False,
    vdrop_v: float | None = None,
    vdrop_loss_w: float | None = None,
    vdrop_incomplete: bool = False,
    bus: str = "",
) -> dict[str, Any]:
    loss_w: float | None = None
    if not unmetered and watts_in is not None and watts_out is not None and stored_w is None:
        raw = watts_in - watts_out
        if raw < 0:
            note = note or "meter disagree"
            loss_w = 0.0
        else:
            loss_w = raw
    return {
        "id": hop_id,
        "label": label,
        "watts_in": watts_in,
        "watts_out": watts_out,
        "loss_w": loss_w,
        "stored_w": stored_w,
        "unmetered": unmetered,
        "note": note,
        "vdrop_v": vdrop_v,
        "vdrop_loss_w": vdrop_loss_w,
        "vdrop_incomplete": vdrop_incomplete,
        "bus": bus,
    }


def build_watt_ledger(states: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Panel current/power in, then per-hop in/out. Combined loss is metered conversion only."""
    battery_1_v = _first_w(states, _MPPT_V_IDS)
    battery_1_a = _first_w(states, _MPPT_A_IDS)
    battery_1_pv = _first_w(states, _SOLAR_IDS)
    if battery_1_pv is None:
        battery_1_pv = _va_w(battery_1_v, battery_1_a)

    mppt_charge = _first_w(states, _CHARGE_IDS)
    mppt_load = _first_w(states, _MPPT_LOAD_IDS)

    batt1 = _first_w(states, _BATT1_W_IDS)
    if batt1 is None:
        b1v = _first_w(states, _BATT1_V_IDS)
        b1a = _first_w(states, _BATT1_A_IDS)
        if b1v is not None and b1a is not None:
            batt1 = b1v * b1a

    batt2 = _first_w(states, _BATT2_W_IDS)
    if batt2 is None:
        b2v = _first_w(states, _BATT2_V_IDS)
        b2a = _first_w(states, _BATT2_A_IDS)
        if b2v is not None and b2a is not None:
            batt2 = b2v * b2a

    # SmartShunt power is +charge into that battery.
    # https://www.victronenergy.com/media/pg/SmartShunt/en/operation.html
    # A has one metered charger (SmartSolar 100/50). Extra battery watts are the jumper.
    # +jumper_w = watts into A from B. The silent B 75/15 is the B shunt
    # leftover after the paired 75/15 and the jumper leaving B.
    battery_2_pv = _first_w(states, _battery_2_PV_IDS)
    battery_2_batt_w = _first_w(states, _battery_2_BATT_W_IDS)
    battery_2_batt_a = _first_w(states, _battery_2_BATT_A_IDS)
    b1_a = _first_w(states, _BATT1_A_IDS)
    b2_a = _first_w(states, _BATT2_A_IDS)
    battery_2_load_w = battery_2_bus_load_w(states)
    jumper_w: float | None = None
    jumper_a: float | None = None
    if batt1 is not None and battery_2_batt_w is not None:
        jumper_w = batt1 - battery_2_batt_w + battery_2_load_w
    b1v = _first_w(states, _BATT1_V_IDS)
    if b1_a is not None and battery_2_batt_a is not None:
        battery_2_load_a = battery_2_load_w / b1v if b1v is not None and b1v > 0 else 0.0
        jumper_a = b1_a - battery_2_batt_a + battery_2_load_a
    silent_w: float | None = None
    silent_a: float | None = None
    if batt2 is not None and mppt_charge is not None and jumper_w is not None:
        silent_w = _clamp_charger_display(batt2 - mppt_charge + jumper_w)
    battery_1_charge_a = _first_w(states, _MPPT_A_IDS)
    if b2_a is not None and battery_1_charge_a is not None and jumper_a is not None:
        silent_a = _clamp_charger_display(b2_a - battery_1_charge_a + jumper_a)
    silent_third_w = None if battery_2_pv is None else battery_2_pv / 3.0

    jumper_flowing = jumper_w is not None and abs(jumper_w) >= 1.0
    mppt_out: float | None = None
    mppt_note = "solar in vs charge plus MPPT load out"
    if mppt_charge is not None and (mppt_charge > 0.5 or not jumper_flowing):
        mppt_out = mppt_charge + (mppt_load or 0.0)
    elif jumper_flowing:
        mppt_note = "MPPT charge 0/missing with jumper; skip conversion loss"

    a3 = _first_w(states, _A3_IDS)
    a3_v = _first_w(states, _A3_V_IDS)
    a3_a = _first_w(states, _A3_A_IDS)
    b3 = _first_w(states, _B3_IDS)
    trailer_ct_w: float | None = None
    if b3 is not None and abs(b3) >= 0.5:
        trailer_ct_w = abs(b3)
    elif a3 is not None:
        trailer_ct_w = abs(a3)

    sg_grid_v = _first_w(states, _SG_GRID_V_IDS)
    sg_grid_a = _first_w(states, _SG_GRID_A_IDS)
    sg_load = _first_w(states, _SG_LOAD_IDS)
    sg_ac_in = _va_w(sg_grid_v, sg_grid_a)
    uti_hop_w = sg_ac_in
    if uti_hop_w is None or uti_hop_w < 0.5:
        if sg_load is not None and abs(sg_load) >= 0.5:
            uti_hop_w = abs(sg_load)
    trailer_w: float | None = None
    if trailer_ct_w is not None or uti_hop_w is not None:
        trailer_w = max(trailer_ct_w or 0.0, uti_hop_w or 0.0)
    vent_fan_w: float | None = 0.0
    vent_unmetered = False

    sg_pv = _first_w(states, _SG_PV_IDS)
    if sg_pv is None:
        sg_pv = _va_w(_first_w(states, _SG_PV_V_IDS), _first_w(states, _SG_PV_A_IDS))
    sg_batt = _first_w(states, _SG_BATT_IDS)

    b2v = _first_w(states, _BATT2_V_IDS)
    mppt_dv, mppt_vdw, mppt_vd_inc = _vdrop_fields(battery_1_v, b2v, battery_1_a)
    jumper_dv, jumper_vdw, jumper_vd_inc = _vdrop_fields(b1v, b2v, None)
    ac_dv, ac_vdw, ac_vd_inc = _vdrop_fields(a3_v, sg_grid_v, a3_a if a3_a is not None else sg_grid_a)

    hops: list[dict[str, Any]] = []
    if battery_2_pv is not None or battery_2_batt_w is not None:
        hops.append(
            _hop(
                "battery-2-mppt",
                "A SmartSolar 100/50",
                battery_2_pv,
                battery_2_batt_w,
                note="metered Instant Readout; 2s3p on A",
                bus="dc",
            )
        )
    else:
        hops.append(
            _hop(
                "battery-2-mppt",
                "A SmartSolar 100/50 (unmetered)",
                None,
                None,
                unmetered=True,
                note="no victron-mppt-1 sample in this state set",
                vdrop_incomplete=True,
                bus="dc",
            )
        )

    hops.append(
        _hop(
            "battery-2-battery",
            "Battery 1 A",
            None,
            None,
            stored_w=batt1,
            note="SmartShunt net; +charge / -discharge (not conversion loss)",
        )
    )

    jumper_abs = abs(jumper_w) if jumper_w is not None else None
    if jumper_w is None:
        jumper_note = (
            "needs Battery 1 power and SmartSolar battery power; "
            "do not use the B 75/15 minus Battery 1"
        )
    elif jumper_w > 0:
        jumper_note = "+ into A from B (Battery 1 W minus SmartSolar battery W plus A bus load W)"
    elif jumper_w < 0:
        jumper_note = "+ into B from A (signed jumper; A bus load W included)"
    else:
        jumper_note = "jumper balance is about zero"
    hops.append(
        _hop(
            "battery-2-battery-1-jumper",
            "A-B jumper",
            jumper_abs,
            jumper_abs,
            note=jumper_note,
            vdrop_v=jumper_dv,
            vdrop_loss_w=jumper_vdw,
            vdrop_incomplete=jumper_vd_inc,
            bus="dc",
        )
    )

    hops.append(
        _hop(
            "battery-1-victron_mppt",
            "Paired B 75/15",
            battery_1_pv,
            mppt_out,
            unmetered=False,
            note=mppt_note + "; " + _battery_1_UNMETERED_PV_REASON,
            vdrop_v=mppt_dv,
            vdrop_loss_w=mppt_vdw,
            vdrop_incomplete=mppt_vd_inc,
            bus="dc",
        )
    )

    hops.append(
        _hop(
            "battery-1-battery",
            "Battery 2 B",
            None,
            None,
            stored_w=batt2,
            note="SmartShunt net; +charge / -discharge; load line is B Renogy A/C est",
        )
    )

    hops.append(
        _hop(
            "battery-1-renogy_ac",
            "B Renogy A/C",
            trailer_w,
            trailer_w,
            note="est. from A3/B3 trailer A/C (no DC clamp); DC in >= AC out; Battery 2 load uses this same W",
        )
    )

    hops.append(
        _hop(
            "trailer_outlet",
            "Trailer outlet",
            trailer_w,
            uti_hop_w,
            note="max(A3/B3 CT, Sungold UTI V*A); Sungold-only on B Renogy outlet",
        )
    )
    hops.append(
        _hop(
            "vent_fan",
            "Trailer vent fan (retired path)",
            vent_fan_w,
            vent_fan_w,
            unmetered=vent_unmetered,
            note="Vent fan and LEDs on Sungold AC out since 2026-09-21; not on A3 sibling",
        )
    )

    sg_in: float | None = None
    sg_out: float | None = None
    if sg_ac_in is not None:
        sg_in = sg_ac_in + (sg_pv or 0.0)
        if sg_batt is not None or sg_load is not None:
            sg_out = (sg_batt or 0.0) + (sg_load or 0.0)
    hops.append(
        _hop(
            "sungold",
            "Sungold",
            sg_in,
            sg_out,
            note="Sungold A/C INPUT (V*A) + PV minus (battery input + A/C out); not A3",
        )
    )
    hops.append(
        _hop(
            "ac_a3_uti",
            "A/C trailer to Sungold",
            uti_hop_w,
            uti_hop_w,
            note="UTI display hop (V*A, or AC-out when V*A ~0); conversion uses sungold_ac_in_w",
            vdrop_v=ac_dv,
            vdrop_loss_w=ac_vdw,
            vdrop_incomplete=ac_vd_inc,
            bus="ac",
        )
    )
    hops.append(
        _hop(
            "solar-broker",
            "solar-broker on Sungold A/C out",
            sg_load,
            sg_load,
            unmetered=True,
            note="always-on Victron BLE radio; no HA watt entity; not a sim dump plug",
        )
    )

    combined = 0.0
    for hop in hops:
        if hop.get("id") not in _CONVERSION_HOP_IDS:
            continue
        loss = hop.get("loss_w")
        if isinstance(loss, (int, float)):
            combined += float(loss)

    vdrop_dc = 0.0
    vdrop_ac = 0.0
    vdrop_w = 0.0
    vdrop_incomplete = False
    for hop in hops:
        dv = hop.get("vdrop_v")
        if hop.get("vdrop_incomplete"):
            vdrop_incomplete = True
        if isinstance(dv, (int, float)):
            if hop.get("bus") == "dc":
                vdrop_dc += float(dv)
            elif hop.get("bus") == "ac":
                vdrop_ac += float(dv)
        vl = hop.get("vdrop_loss_w")
        if isinstance(vl, (int, float)):
            vdrop_w += float(vl)
        elif hop.get("vdrop_v") is not None and hop.get("vdrop_loss_w") is None:
            vdrop_incomplete = True

    path_total = combined + vdrop_w
    panel_parts = [p for p in (battery_2_pv, battery_1_pv, sg_pv) if p is not None]
    panel_in = sum(panel_parts) if panel_parts else None
    if silent_w is not None:
        battery_1_unmetered = silent_w
        battery_1_kind = "shunt_balance"
    else:
        battery_1_unmetered = battery_1_unmetered_pv_residual(batt2, jumper_w, trailer_w)
        battery_1_kind = "ac_lower_bound" if trailer_w is not None and battery_1_unmetered is not None else None
    battery_1_share = battery_1_equal_share_w(battery_1_unmetered)

    return {
        "watt_hops": hops,
        "combined_losses_w": combined,
        "combined_vdrop_v": vdrop_dc,
        "combined_vdrop_ac_v": vdrop_ac,
        "combined_vdrop_loss_w": vdrop_w,
        "combined_path_losses_w": path_total,
        "combined_losses_incomplete": True,
        "combined_vdrop_incomplete": vdrop_incomplete,
        "panel_in_w": panel_in,
        "battery-2-bus_load_w": battery_2_load_w,
        "jumper_w": jumper_w,
        "jumper_a": jumper_a,
        "battery-1-silent_mppt_w": silent_w,
        "battery-1-silent_mppt_a": silent_a,
        "battery-1-silent_mppt_third_w": silent_third_w,
        "trailer_outlet_w": trailer_w,
        "sungold_ac_in_w": sg_ac_in,
        "uti_hop_w": uti_hop_w,
        "vent_fan_w": vent_fan_w,
        "battery-1-renogy_ac_est_w": trailer_w,
        "battery-1-unmetered_pv_est_w": battery_1_unmetered,
        "battery-1-unmetered_pv_est_kind": battery_1_kind,
        "battery-1-charger_equal_share_w": battery_1_share,
        "battery-1-charger_equal_share_a": battery_1_est_amps(battery_1_share, b2v),
    }


def apply_ledger_to_meta(
    meta: dict[str, Any],
    states: dict[str, dict[str, Any]],
    surplus: float | None,
) -> float | None:
    """Copy hop ledger onto dump-tick meta. Returns surplus minus combined conversion losses."""
    ledger = build_watt_ledger(states)
    meta["watt_hops"] = ledger["watt_hops"]
    meta["combined_losses_w"] = ledger["combined_losses_w"]
    meta["combined_vdrop_v"] = ledger["combined_vdrop_v"]
    meta["combined_vdrop_ac_v"] = ledger["combined_vdrop_ac_v"]
    meta["combined_vdrop_loss_w"] = ledger["combined_vdrop_loss_w"]
    meta["combined_path_losses_w"] = ledger["combined_path_losses_w"]
    meta["combined_losses_incomplete"] = ledger["combined_losses_incomplete"]
    meta["combined_vdrop_incomplete"] = ledger["combined_vdrop_incomplete"]
    meta["panel_in_w"] = ledger["panel_in_w"]
    meta["jumper_w"] = ledger["jumper_w"]
    meta["trailer_outlet_w"] = ledger["trailer_outlet_w"]
    meta["sungold_ac_in_w"] = ledger["sungold_ac_in_w"]
    meta["uti_hop_w"] = ledger["uti_hop_w"]
    meta["vent_fan_w"] = ledger["vent_fan_w"]
    meta["battery-1-renogy_ac_est_w"] = ledger["battery-1-renogy_ac_est_w"]
    meta["battery-1-unmetered_pv_est_w"] = ledger["battery-1-unmetered_pv_est_w"]
    meta["battery-1-unmetered_pv_est_kind"] = ledger["battery-1-unmetered_pv_est_kind"]
    meta["battery-1-charger_equal_share_w"] = ledger["battery-1-charger_equal_share_w"]
    meta["battery-1-charger_equal_share_a"] = ledger["battery-1-charger_equal_share_a"]
    path_losses = float(ledger.get("combined_path_losses_w") or 0.0)
    if surplus is None:
        meta["surplus_after_path_losses_w"] = None
        return None
    after = surplus - path_losses
    meta["surplus_after_path_losses_w"] = after
    return after
