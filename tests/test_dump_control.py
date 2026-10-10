"""Dump-load control on the real H5082 sockets (config/packages/dump_control.yaml).

Structure checks always run. Template behaviour is rendered with jinja2 and a fake
HA state table when jinja2 is installed (HA's own template engine is Jinja2).
"""

from __future__ import annotations

import ast
import datetime as dt
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from govee_h5082.mqtt_bridge import PLUGS, SIDES

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "config" / "packages" / "dump_control.yaml"
DOCS = ROOT / "docs" / "DUMP_LOAD_HA_CONTROL.md"
DASHBOARD = ROOT / "config" / "dashboards" / "solar-plant.yaml"
INSTALL = ROOT / "scripts" / "install_dump_control_ha.sh"

# Stage order = plug id order (same as the Site solar cards and the label script).
# Every bridge plug is a dump candidate (plug-7 paired 2026-09-28): 8 plugs, 16 sockets.
# (Nothing here says what is plugged into a socket: that is the HA Load text.)
SOCKS = [
    f"{plug}_{side}"
    for plug in sorted(name[-4:].lower() for _address, name in PLUGS)
    for side, _port, _label in SIDES
]
ALL_plug_SWITCHES = {
    f"switch.{name.lower()}_{label.lower()}" for _a, name in PLUGS for _s, _p, label in SIDES
}


def _load() -> dict:
    data = yaml.safe_load(PACKAGE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _templates() -> dict[str, dict]:
    out = {}
    for block in _load()["template"]:
        for row in block.get("sensor", []) + block.get("binary_sensor", []):
            out[row["unique_id"]] = row
    return out


def _automations() -> dict[str, dict]:
    return {a["id"]: a for a in _load()["automation dump_load"]}


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_no_simulated_plugs_left() -> None:
    text = PACKAGE.read_text(encoding="utf-8")
    assert "sim_" not in text
    assert not (ROOT / "config" / "packages" / "sim_dump_control.yaml").exists()
    assert not (ROOT / "config" / "packages" / "sim_dump_plugs.yaml").exists()


def test_socket_list_matches_bridge_discovery() -> None:
    text = PACKAGE.read_text(encoding="utf-8")
    lists = re.findall(r"\[\s*('[0-9a-f]{4}_(?:left|right)'(?:,\s*'[0-9a-f]{4}_(?:left|right)')*)\s*\]", text)
    assert lists, "no socket list found"
    for raw in lists:
        assert re.findall(r"'([^']+)'", raw) == SOCKS
    # The switch ids the templates build are the ids HA gives the bridge's discovery.
    for s in SOCKS:
        assert f"switch.ihoment_plug_{s}" in ALL_plug_SWITCHES
    assert len(SOCKS) == 16
    assert "'plug-7_left', 'plug-7_right'" in text.split("# Victron float hold")[1]


def test_helpers_per_socket() -> None:
    data = _load()
    for s in SOCKS:
        sel = data["input_select"][f"plug_{s}_inverter"]
        # Sungold stays first (first-install default); House = grid-powered house plug.
        assert sel["options"] == ["Sungold", "T2", "KU", "House"]
        assert "initial" not in sel  # bus choice must survive HA restarts
        assert data["timer"][f"plug_{s}_min_on"]["duration"] == "00:15:00"
        assert data["timer"][f"plug_{s}_cooldown"]["duration"] == "00:10:00"
        assert data["timer"][f"plug_{s}_cooldown"]["restore"] is True
    # The per-socket use select is the UI helper from create_plug_socket_labels.py;
    # defining it here too would collide with it.
    assert not any(k.endswith("_use") for k in data["input_select"])
    assert "dump_control_enabled" in data["input_boolean"]
    assert "initial" not in data["input_boolean"]["dump_control_enabled"]
    # plug-09-28: no `initial:` anywhere, so tuned values survive HA restarts
    # (tests/test_site_solar_persist_and_help.py covers every helper).
    assert "initial" not in data["input_number"]["dump_site_confirm_s"]
    assert data["input_number"]["dump_site_confirm_s"]["min"] == 5


USE_DUMP = re.compile(r"is_state\('input_select\.plug_' ~ (\w+) ~ '_use', 'dump'\)")


def test_every_dump_pick_has_the_house_guard() -> None:
    """One guard everywhere: Use is dump, Inverter is not House, and the plug is online."""
    text = PACKAGE.read_text(encoding="utf-8")
    hits = list(USE_DUMP.finditer(text))
    # dump_sockets (count + list), next, shed, turn_on recheck, solar gone, 3 re-bulk,
    # 3 batt, the two manual-hold rules (hold start, hold end), on-demand on, on-demand
    # off (count + list), the off script, and the Sungold voltage guard.
    assert len(hits) == 22
    for m in hits:
        var = m.group(1)
        guard = (
            " and not is_state('input_select.plug_' ~ "
            + var
            + " ~ '_inverter', 'House') and is_state('input_boolean.plug_' ~ "
            + var
            + ".split('_')[0] ~ '_online', 'on'))"
        )
        assert text[m.start() - 1] == "(", text[m.start() - 40 : m.end()]
        assert text[m.end() : m.end() + len(guard)] == guard, text[m.start() : m.end() + 80]


def test_problem_device_class_is_not_used_for_dump_rules() -> None:
    """Problem is only a real fault, not a dump or charge gate."""
    text = PACKAGE.read_text(encoding="utf-8")
    assert text.count("device_class: problem") == 1
    assert "unique_id: plug_plugs_unseen" in text


def test_switch_actions_are_never_hardcoded() -> None:
    for auto in _automations().values():
        for node in _walk(auto["actions"]):
            if node.get("action") in ("switch.turn_on", "switch.turn_off"):
                target = node["target"]["entity_id"]
                assert "{{" in target, f"{auto['id']} hardcodes {target}"
                assert target in (
                    "{{ target }}",
                    "switch.ihoment_plug_{{ repeat.item }}",
                ), target


def test_timings_kept() -> None:
    autos = _automations()
    assert set(autos) == {
        "dump_turn_on",
        "dump_turn_off_solar_gone",
        "dump_turn_off_bulk",
        "dump_shed_load_exceeds_solar",
        "dump_notify_load_exceeds_solar",
        "dump_turn_off_rebulk_t2",
        "dump_turn_off_rebulk_ku",
        "dump_turn_off_rebulk_sph",
        "dump_turn_off_batt_t2",
        "dump_turn_off_batt_ku",
        "dump_turn_off_batt_sph",
        "dump_inverter-1-vguard_shed",
        "dump_inverter-1-charge_on",
        "dump_inverter-1-charge_off",
        "dump_inverter-1-charge_surplus_on",
        "dump_inverter-1-charge_surplus_off",
        "dump_inverter-1-charge_source_stop",
        "dump_inverter-1-charge_inlet_dark",
        "dump_inverter-1-charge_inlet_clear",
        "dump_remember_solar_before_float",
        "plug_plugs_unseen_notify",
        "dump_hold_start",
        "dump_hold_end",
    }
    for aid, auto in autos.items():
        if aid.startswith("dump_hold_") or aid in ("plug_plugs_unseen_notify", "dump_remember_solar_before_float") or aid in {
            "dump_inverter-1-vguard_shed",
            "dump_inverter-1-charge_on",
            "dump_inverter-1-charge_off",
            "dump_inverter-1-charge_surplus_on",
            "dump_inverter-1-charge_surplus_off",
            "dump_inverter-1-charge_source_stop",
            "dump_inverter-1-charge_inlet_dark",
            "dump_inverter-1-charge_inlet_clear",
        }:
            continue  # hold: switch/timer triggers. Guard and charge: dwell comes from a helper.
        for trig in auto["triggers"]:
            if trig.get("entity_id") != "sensor.dump_next_plug":
                want = "00:10:00" if aid == "dump_notify_load_exceeds_solar" else "00:01:00"
                assert trig["for"] == want, aid
        if aid != "dump_notify_load_exceeds_solar":
            assert auto["conditions"][0] == {
                "condition": "state",
                "entity_id": "input_boolean.dump_control_enabled",
                "state": "on",
            }
    seq = autos["dump_turn_on"]["actions"][0]["repeat"]["sequence"]
    delays = [n["delay"] for n in seq if "delay" in n]
    assert "{{ states('input_number.dump_site_confirm_s') | int(5) }}" in delays
    for shed in ("dump_turn_off_bulk", "dump_shed_load_exceeds_solar"):
        seq = autos[shed]["actions"][0]["repeat"]["sequence"]
        assert seq[-1] == {"delay": "00:01:00"}


def test_turn_on_waits_for_the_plug_and_respects_kill_switch() -> None:
    auto = _automations()["dump_turn_on"]
    seq = auto["actions"][0]["repeat"]["sequence"]
    waits = [n for n in seq if "wait_template" in n]
    assert waits and waits[0]["wait_template"] == "{{ is_state(target, 'on') }}"
    whiles = auto["actions"][0]["repeat"]["while"]
    assert {"condition": "state", "entity_id": "input_boolean.dump_control_enabled", "state": "on"} in whiles
    blob = str(auto["conditions"]) + str(whiles)
    assert "binary_sensor.dump_load_exceeds_solar" in blob


def test_docs_and_install() -> None:
    docs = DOCS.read_text(encoding="utf-8")
    assert "dump_control.yaml" in docs
    assert "input_select.plug_<id>_<side>_use" in docs
    assert "sim_ac_plug" not in docs
    text = INSTALL.read_text(encoding="utf-8")
    assert "dump_control.yaml" in text
    assert "sim_dump_control.yaml" in text  # removes the old copy on 


def test_dashboard_references_real_dump_helpers() -> None:
    blob = DASHBOARD.read_text(encoding="utf-8")
    assert "sim_ac_plug" not in blob
    assert "dump_plug_" not in blob
    assert "timer.plug_" in blob
    for s in SOCKS:
        assert f"input_select.plug_{s}_inverter" in blob


# ---------------------------------------------------------------- template behaviour

jinja2 = pytest.importorskip("jinja2")
jinja2_sandbox = pytest.importorskip("jinja2.sandbox")


def _is_number(value) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True



def _regex_findall(value, pattern, ignorecase=False):
    flags = re.IGNORECASE if ignorecase else 0
    return re.findall(pattern, "" if value is None else str(value), flags)


def _ha_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "on", "1")


def _render(template: str, states: dict[str, str]):
    env = jinja2.Environment()
    env.filters["bool"] = _ha_bool
    env.filters["regex_findall"] = _regex_findall
    env.globals.update(
        states=lambda eid: states.get(eid, "unknown"),
        is_state=lambda eid, value: states.get(eid, "unknown") == value,
        is_number=_is_number,
    )
    return env.from_string(template).render(feed_load=False).strip()


def _ok_states(**over) -> dict[str, str]:
    st = {
        "binary_sensor.dump_solar_present": "on",
        "binary_sensor.dump_charge_float": "on",
        "binary_sensor.dump_soc_ok": "on",
        "binary_sensor.dump_batt_inverter-1-ok": "on",
        "binary_sensor.dump_batt_battery-2-ok": "on",
        "binary_sensor.dump_batt_battery-1-ok": "on",
        "binary_sensor.dump_v_float_sph": "on",
        "binary_sensor.dump_v_float_t2": "on",
        "binary_sensor.dump_v_float_ku": "on",
        "binary_sensor.dump_v_rebulk_sph": "off",
        "binary_sensor.dump_v_rebulk_t2": "off",
        "binary_sensor.dump_v_rebulk_ku": "off",
        "sensor.sungold-inverter-1_load_power": "300",
        "sensor.battery_1_power": "50",
        "sensor.battery_2_power": "40",
        "input_boolean.dump_soc_unsynced": "on",
        "sensor.victron-mppt-1_solar_power": "200",
        "sensor.victron-mppt-1_solar": "80",
        "sensor.victron-mppt-1_battery_state": "float",
        "sensor.victron-mppt-1_charge_state": "float",
        "weather.hygrometer-1": "sunny",
        "input_number.dump_solar_before_float_w": "908",
        "input_number.dump_min_solar_w": "50",
        "input_number.dump_site_delta_min_w": "25",
        "input_number.dump_ac_limit_inverter-1-w": "2000",
        "input_number.dump_ac_limit_battery-2-w": "2000",
        "input_number.dump_ac_limit_battery-1-w": "2000",
    }
    for s in SOCKS:
        st[f"switch.ihoment_plug_{s}"] = "off"
        st[f"input_select.plug_{s}_use"] = "normal"
        st[f"input_select.plug_{s}_inverter"] = "Sungold"
        st[f"timer.plug_{s}_cooldown"] = "idle"
        st[f"input_boolean.plug_{s.split('_')[0]}_online"] = "on"
    st.update(over)
    return st


def _next(states):
    return _render(_templates()["dump_next_plug"]["state"], states)


def _shed(states):
    return _render(_templates()["dump_shed_plug"]["state"], states)



def test_on_socket_with_no_measured_watts_does_not_block_the_next_dump() -> None:
    """A dump switch that is on is not a consuming load by itself."""
    st = _ok_states(**{
        "input_select.plug-1_left_use": "dump",
        "input_select.plug-1_left_inverter": "KU",
        "switch.plug-1_left": "on",
        "input_select.plug-1_right_use": "dump",
        "input_select.plug-1_right_inverter": "KU",
        "switch.plug-1_right": "off",
    })
    assert _next(st) == "switch.plug-1_right"




def test_offline_plug_is_not_a_dump_target_or_unseen() -> None:
    """A plug checkbox that is off is not offered, not shed, and not an unseen alarm."""
    st = _ok_states(**{
        "input_select.plug-1_left_use": "dump",
        "input_select.plug-2_left_use": "dump",
        "input_boolean.plug-1_online": "off",
        "switch.plug-1_left": "unavailable",
        "switch.plug-1_right": "unknown",
    })
    assert _next(st) == "switch.plug-2_left"
    shed = _ok_states(**{
        "input_select.plug-1_left_use": "dump",
        "switch.plug-1_left": "on",
        "input_boolean.plug-1_online": "off",
    })
    assert _shed(shed) == "none"
    unseen = _render(_templates()["plug_plugs_unseen"]["state"], st)
    assert unseen == "False"
    st["input_boolean.plug-2_online"] = "on"
    st["switch.plug-2_left"] = "unavailable"
    assert _render(_templates()["plug_plugs_unseen"]["state"], st) == "True"


def test_next_plug_ignores_normal_sockets() -> None:
    assert _next(_ok_states()) == "none"


def test_next_plug_picks_first_eligible_dump_socket() -> None:
    st = _ok_states(**{
        "input_select.plug-2_right_use": "dump",
        "input_select.plug-6_left_use": "dump",
    })
    assert _next(st) == "switch.plug-2_right"
    st["timer.plug-2_right_cooldown"] = "active"
    assert _next(st) == "switch.plug-6_left"
    st["switch.plug-6_left"] = "unavailable"  # bridge offline: never pick
    assert _next(st) == "none"


def test_next_plug_blocks_on_bus_and_site_conditions() -> None:
    base = {"input_select.plug-1_left_use": "dump", "input_select.plug-1_left_inverter": "Sungold"}
    assert _next(_ok_states(**base)) == "switch.plug-1_left"
    for key, value in (
        ("binary_sensor.dump_solar_present", "off"),
        ("binary_sensor.dump_soc_ok", "unavailable"),
    ):
        assert _next(_ok_states(**base, **{key: value})) == "none", key
    # One measured bus in trouble does not block while another bus is healthy.
    # The Sungold label is not the decider.
    assert _next(_ok_states(**base, **{"binary_sensor.dump_v_rebulk_sph": "on"})) != "none"
    assert _next(_ok_states(**base, **{"sensor.battery_1_power": "-2500"})) != "none"
    blocked = {
        "binary_sensor.dump_v_rebulk_t2": "on",
        "binary_sensor.dump_v_rebulk_ku": "on",
        "binary_sensor.dump_v_rebulk_sph": "on",
    }
    assert _next(_ok_states(**base, **blocked)) == "none"


def test_shed_plug_only_sheds_dump_sockets_last_first() -> None:
    st = _ok_states(**{
        "switch.plug-8_right": "on",  # normal load, must stay
        "switch.plug-1_left": "on",
        "input_select.plug-1_left_use": "dump",
        "switch.plug-5_left": "on",
        "input_select.plug-5_left_use": "dump",
    })
    assert _shed(st) == "switch.plug-5_left"
    st["switch.plug-5_left"] = "off"
    assert _shed(st) == "switch.plug-1_left"
    st["switch.plug-1_left"] = "off"
    assert _shed(st) == "none"


def _targets(aid: str, states) -> list[str]:
    auto = _automations()[aid]
    tpl = None
    for step in auto["actions"]:
        variables = step.get("variables") if isinstance(step, dict) else None
        if isinstance(variables, dict) and "targets" in variables:
            tpl = variables["targets"]
            break
    if tpl is None:
        raise KeyError("targets")
    return yaml.safe_load(_render(tpl, states).replace("'", '"'))


def test_bus_turn_off_follows_measured_trouble_not_the_inverter_label() -> None:
    st = _ok_states(**{
        "input_select.plug_1_left_use": "dump",
        "input_select.plug_1_left_inverter": "T2",
        "switch.plug_1_left": "on",
        "input_select.plug_2_left_use": "dump",
        "input_select.plug_2_left_inverter": "Sungold",
        "switch.plug_2_left": "unavailable",  # still sent off
        "input_select.plug_3_left_use": "dump",
        "input_select.plug_3_left_inverter": "KU",
        "switch.plug_3_left": "on",
        "input_select.plug_8_left_inverter": "T2",  # normal, on: untouched
        "switch.plug_8_left": "on",
        "input_select.plug_4_left_use": "dump",
        "input_select.plug_4_left_inverter": "House",
        "switch.plug_4_left": "on",
    })
    eligible = ["plug_1_left", "plug_2_left", "plug_3_left"]
    for aid in (
        "dump_turn_off_rebulk_t2",
        "dump_turn_off_batt_t2",
        "dump_turn_off_rebulk_ku",
        "dump_turn_off_batt_ku",
        "dump_turn_off_rebulk_sph",
        "dump_turn_off_batt_sph",
    ):
        assert _targets(aid, st) == eligible, aid
    assert _targets("dump_turn_off_solar_gone", st) == eligible
    ku = _automations()["dump_turn_off_rebulk_ku"]
    assert any(t.get("entity_id") == "binary_sensor.dump_soc_hold_trips" for t in ku["triggers"])
    assert any(
        c.get("entity_id") == "binary_sensor.dump_v_rebulk_ku" and c.get("for") == "00:01:00"
        for c in ku["conditions"]
    )


def test_house_sockets_are_never_picked_or_switched() -> None:
    """Inverter = House (grid-powered house plug): dump control never switches it."""
    house = {
        "input_select.plug_1_left_use": "dump",
        "input_select.plug_1_left_inverter": "House",
    }
    tpl = _templates()
    # Off: never offered to turn on.
    st = _ok_states(**house)
    assert _next(st) == "none"
    assert _render(tpl["dump_sockets"]["state"], st) == "0"
    assert yaml.safe_load(_render(tpl["dump_sockets"]["attributes"]["entities"], st)) == []
    # The next real dump socket is still picked.
    st["input_select.plug_2_left_use"] = "dump"
    assert _next(st) == "switch.plug_2_left"
    # On: never shed and never in any turn-off list (solar gone, re-bulk, battery).
    st = _ok_states(**house, **{"switch.plug_1_left": "on"})
    assert _shed(st) == "none"
    offs = [a for a in _automations() if a.startswith("dump_turn_off_") and a != "dump_turn_off_bulk"]
    assert len(offs) == 7
    for aid in offs:
        assert "plug_1_left" not in _targets(aid, st), aid
    # dump_turn_on rechecks the socket right before switch.turn_on.
    seq = _automations()["dump_turn_on"]["actions"][0]["repeat"]["sequence"]
    recheck = [n for n in seq if n.get("condition") == "template"]
    assert len(recheck) == 1
    env_st = dict(st)
    tmpl = recheck[0]["value_template"].replace("sock", "'plug-1_left'")
    assert _render(tmpl, env_st) == "False"
    env_st["input_select.plug_1_left_inverter"] = "KU"
    assert _render(tmpl, env_st) == "True"
    # Dashboard "Dump sockets by name" says so instead of naming a bus.
    assert "House (grid power): never switched by dump control" in DASHBOARD.read_text(encoding="utf-8")


# ---------------------------------------------------------------- manual hold

HOLD_ON = " and states('timer.plug_' ~ {v} ~ '_hold') not in ['active', 'paused']"
HOLD_OFF = (
    " and (states('timer.plug_' ~ {v} ~ '_hold') not in ['active', 'paused']"
    " or not is_state('input_boolean.dump_hold_blocks_turn_off', 'on'))"
)
TURN_OFF_LISTS = (
    "dump_turn_off_solar_gone",
    "dump_turn_off_rebulk_t2",
    "dump_turn_off_rebulk_ku",
    "dump_turn_off_rebulk_sph",
    "dump_turn_off_batt_t2",
    "dump_turn_off_batt_ku",
    "dump_turn_off_batt_sph",
)


def _strings(node) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        return "\n".join(_strings(v) for v in node.values())
    if isinstance(node, list):
        return "\n".join(_strings(v) for v in node)
    return ""


def _lists(node):
    if isinstance(node, list):
        yield node
        for v in node:
            yield from _lists(v)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _lists(v)


def test_manual_hold_helpers() -> None:
    data = _load()
    hold_ids = []
    for s in SOCKS:
        tm = data["timer"][f"plug_{s}_hold"]
        assert tm["restore"] is True
        assert tm["name"] == f"{s[:4].upper()} {s[5:]} dump manual hold"
        hold_ids.append(f"timer.plug_{s}_hold")
    num = data["input_number"]["dump_manual_hold_min"]
    assert (num["min"], num["max"], num["unit_of_measurement"]) == (0, 720, "min")
    assert "initial" not in num  # a new helper starts at 0 = hold off
    assert "initial" not in data["input_boolean"]["dump_hold_blocks_turn_off"]
    clear = data["script"]["dump_clear_holds"]["sequence"][0]
    assert clear["action"] == "timer.cancel"
    assert clear["target"]["entity_id"] == hold_ids
    defaults = _strings(data["script"]["dump_load_recommended_defaults"])
    assert "input_number.dump_manual_hold_min" in defaults
    assert "input_boolean.dump_hold_blocks_turn_off" in defaults
    autos = _automations()
    start = autos["dump_hold_start"]["triggers"][0]
    assert start["entity_id"] == [f"switch.ihoment_plug_{s}" for s in SOCKS]
    assert (start["from"], start["to"]) == (["on", "off"], ["on", "off"])
    end = autos["dump_hold_end"]["triggers"][0]
    assert end["entity_id"] == hold_ids
    assert (end["from"], end["to"]) == ("active", "idle")


def test_every_dump_path_has_the_hold_guard() -> None:
    """Turn-on always skips a held socket; turn-offs skip it only when the toggle is on."""
    text = PACKAGE.read_text(encoding="utf-8")
    tpl = _templates()
    autos = _automations()
    assert HOLD_ON.format(v="s") in tpl["dump_next_plug"]["state"]
    assert HOLD_ON.format(v="sock") in _strings(autos["dump_turn_on"]["actions"])
    assert HOLD_OFF.format(v="s") in tpl["dump_shed_plug"]["state"]
    for aid in TURN_OFF_LISTS:
        assert HOLD_OFF.format(v="s") in autos[aid]["actions"][0]["variables"]["targets"], aid
    # Turn-on skips holds in next_plug, the turn-on recheck, on-demand on, on-demand
    # off (count + list) and the off script, plus rescue on, surplus ready and surplus on.
    # Turn-offs: shed + 7 lists + the guard, plus charge recovery, source stop,
    # surplus stop and surplus off.
    # Rescue on skips a hold unless a Sungold AC load is being fed (feed_load).
    assert "or feed_load | bool" in text
    assert text.count(HOLD_ON.format(v="s")) + text.count(HOLD_ON.format(v="sock")) == 8
    assert text.count(HOLD_OFF.format(v="s")) == 13
    # "Sockets set to dump" still counts held sockets and lists them in `held`.
    assert "_hold'" not in tpl["dump_sockets"]["state"]
    assert "_hold')" in tpl["dump_sockets"]["attributes"]["held"]


def test_held_socket_is_never_turned_on() -> None:
    st = _ok_states(**{
        "input_select.plug_1_left_use": "dump",
        "input_select.plug_2_left_use": "dump",
        "timer.plug_1_left_hold": "active",
    })
    assert _next(st) == "switch.plug_2_left"
    st["timer.plug_2_left_hold"] = "paused"
    assert _next(st) == "none"
    st["timer.plug_1_left_hold"] = "idle"
    assert _next(st) == "switch.plug_1_left"
    # dump_turn_on rechecks right before switch.turn_on, whatever the toggle says.
    seq = _automations()["dump_turn_on"]["actions"][0]["repeat"]["sequence"]
    recheck = next(n for n in seq if n.get("condition") == "template")["value_template"]
    tmpl = recheck.replace("sock", "'plug-1_left'")
    assert _render(tmpl, st) == "True"
    st["timer.plug_1_left_hold"] = "active"
    assert _render(tmpl, st) == "False"
    st["input_boolean.dump_hold_blocks_turn_off"] = "off"
    assert _render(tmpl, st) == "False"


def test_hold_blocks_turn_offs_only_when_the_toggle_is_on() -> None:
    st = _ok_states(**{
        "input_select.plug_1_left_use": "dump",
        "input_select.plug_1_left_inverter": "T2",
        "switch.plug_1_left": "on",
        "timer.plug_1_left_hold": "active",
        "input_select.plug_2_left_use": "dump",
        "input_select.plug_2_left_inverter": "T2",
        "switch.plug_2_left": "on",
    })
    # Toggle off (or a brand-new helper): the turn-off rules still act on a held socket.
    for aid in ("dump_turn_off_solar_gone", "dump_turn_off_rebulk_t2", "dump_turn_off_batt_t2"):
        assert _targets(aid, st) == ["plug_1_left", "plug_2_left"], aid
    st["switch.plug_2_left"] = "off"
    assert _shed(st) == "switch.plug_1_left"
    # Toggle on: the held socket is left alone by every turn-off rule and the sheds.
    st["input_boolean.dump_hold_blocks_turn_off"] = "on"
    st["switch.plug_2_left"] = "on"
    for aid in TURN_OFF_LISTS:
        assert "plug_1_left" not in _targets(aid, st), aid
    assert _targets("dump_turn_off_rebulk_t2", st) == ["plug_2_left"]
    assert _shed(st) == "switch.plug_2_left"
    st["switch.plug_2_left"] = "off"
    assert _shed(st) == "none"
    st["timer.plug_1_left_hold"] = "idle"  # hold over: back to normal
    assert _shed(st) == "switch.plug_1_left"


def test_every_dump_switch_action_is_announced_first() -> None:
    found = 0
    for auto in _automations().values():
        for seq in _lists(auto["actions"]):
            for i, node in enumerate(seq):
                if not isinstance(node, dict) or node.get("action") not in ("switch.turn_on", "switch.turn_off"):
                    continue
                found += 1
                prev = seq[i - 1]
                assert i > 0 and prev.get("event") == "dump_control_switching", auto["id"]
                assert prev["event_data"]["state"] == node["action"].split("_")[-1], auto["id"]
                want = "{{ repeat.item }}" if "repeat.item" in node["target"]["entity_id"] else "{{ sock }}"
                assert prev["event_data"]["sock"] == want, auto["id"]
    assert found == 20  # trouble-bus confirm turns that socket off; a plug with no watt rise stays on


def _render_ha(template: str, states: dict[str, str] | None = None, **extra) -> str:
    """Closer to HA: sandboxed, with now / as_timestamp / state_attr / timedelta."""
    states = states or {}

    def as_timestamp(value, default=None):
        if isinstance(value, dt.datetime):
            return value.timestamp()
        try:
            return dt.datetime.fromisoformat(str(value)).timestamp()
        except (TypeError, ValueError):
            return default

    env = jinja2_sandbox.ImmutableSandboxedEnvironment()
    env.filters["bool"] = _ha_bool
    env.filters["regex_findall"] = _regex_findall
    env.globals.update(
        states=lambda eid: states.get(eid, "unknown"),
        is_state=lambda eid, value: states.get(eid, "unknown") == value,
        is_number=_is_number,
        now=extra.pop("now", lambda: dt.datetime.now(dt.timezone.utc)),
        as_timestamp=as_timestamp,
        timedelta=dt.timedelta,
        state_attr=extra.pop("state_attr", lambda eid, attr: None),
    )
    extra.setdefault("feed_load", False)
    return env.from_string(template).render(**extra).strip()


def test_intent_sensor_keeps_one_request_per_socket() -> None:
    block = next(b for b in _load()["template"] if "triggers" in b)
    assert block["triggers"] == [{"trigger": "event", "event_type": "dump_control_switching"}]
    tpl = block["sensor"][0]["attributes"]["intents"]

    def fire(this, sock, state):
        trig = {"event": {"data": {"sock": sock, "state": state}}}
        extra = {"trigger": trig}
        if this is not None:
            extra["this"] = SimpleNamespace(attributes=this)
        return ast.literal_eval(_render_ha(tpl, **extra))

    one = fire(None, "plug_1_left", "on")
    assert list(one) == ["plug_1_left"] and one["plug_1_left"][0] == "on"
    two = fire({"intents": one}, "plug_2_left", "off")
    assert set(two) == {"plug_1_left", "plug_2_left"}
    three = fire({"intents": two}, "plug_1_left", "done")
    assert three["plug_1_left"][0] == "done" and three["plug_2_left"][0] == "off"
    fresh = fire({}, "plug_7_right", "off")  # restored without intents: starts clean
    assert list(fresh) == ["plug_7_right"] and fresh["plug_7_right"][0] == "off"
    assert isinstance(fresh["plug_7_right"][1], float)


def test_hold_start_tells_dump_control_from_a_hand_switch() -> None:
    auto = _automations()["dump_hold_start"]
    tpl = auto["variables"]["by_dump"]
    now = dt.datetime.now(dt.timezone.utc)

    def by_dump(intents, to_state):
        return _render_ha(
            tpl,
            now=lambda: now,
            state_attr=lambda e, a: intents if (e, a) == ("sensor.dump_control_switching", "intents") else None,
            sock="plug_1_left",
            trigger={"to_state": {"state": to_state}},
        )

    ts = now.timestamp()
    assert by_dump({"plug_1_left": ["on", ts - 20]}, "on") == "True"  # dump control asked
    assert by_dump({"plug_1_left": ["on", ts - 20]}, "off") == "False"  # opposite: by hand
    assert by_dump({"plug_1_left": ["on", ts - 200]}, "on") == "False"  # stale request
    assert by_dump({"plug_1_left": ["done", ts - 5]}, "on") == "False"  # already used up
    assert by_dump({"plug_2_left": ["on", ts - 5]}, "on") == "False"  # other socket
    assert by_dump(None, "on") == "False"  # registry empty / unknown
    # A hand switch starts the hold only on a dump socket (not House) with minutes > 0.
    cond = next(a for a in auto["actions"] if a.get("condition") == "template")["value_template"]
    assert "'_inverter', 'House'" in cond and "hold_min > 0" in cond
    start = next(a for a in auto["actions"] if a.get("action") == "timer.start")
    assert start["target"]["entity_id"] == "timer.plug_{{ sock }}_hold"
    for minutes, want in ((5, "00:05:00"), (60, "01:00:00"), (720, "12:00:00")):
        assert _render_ha(start["data"]["duration"], hold_min=minutes) == want
    # Runs even with the master switch off: no master-switch condition.
    assert "dump_control_enabled" not in _strings(auto)


def test_hold_end_turns_off_only_what_dump_control_would_want_off() -> None:
    auto = _automations()["dump_hold_end"]
    why = auto["variables"]["why_off"]
    ok = _ok_states(**{"binary_sensor.dump_charge_ok": "on", "binary_sensor.dump_load_exceeds_solar": "off"})
    assert _render_ha(why, ok, bus="T2") == ""
    assert _render_ha(why, {**ok, "binary_sensor.dump_solar_present": "off"}, bus="T2") == "solar gone"
    assert _render_ha(why, {**ok, "binary_sensor.dump_v_rebulk_t2": "on"}, bus="T2") == "T2 bus at stop volts"
    assert _render_ha(why, {**ok, "binary_sensor.dump_v_rebulk_t2": "on"}, bus="KU") == "T2 bus at stop volts"
    assert _render_ha(why, {**ok, "binary_sensor.dump_batt_inverter_1_ok": "off"}, bus="Sungold") == (
        "Sungold battery past its discharge limit"
    )
    assert _render_ha(why, {**ok, "binary_sensor.dump_charge_ok": "off"}, bus="KU") == (
        "T2 charger left absorption/float"
    )
    blob = _strings(auto["actions"])
    assert "input_boolean.dump_control_enabled" in blob
    assert "'_inverter', 'House'" in blob
    assert _render_ha(why, {**ok, "binary_sensor.dump_inverter_1_vguard": "on"}, bus="Sungold") == (
        "Sungold voltage guard"
    )
    assert _render_ha(why, {**ok, "binary_sensor.dump_inverter_1_vguard": "on"}, bus="T2") == (
        "Sungold voltage guard"
    )


# ------------------------------------------------------- on demand + skip cooldown


def _ondemand_on(states):
    return _render(_templates()["dump_ondemand_on"]["state"], states)


def _ondemand_off(states):
    row = _templates()["dump_ondemand_off"]
    count = _render(row["state"], states)
    sockets = yaml.safe_load(_render(row["attributes"]["sockets"], states).replace("'", '"'))
    return count, sockets


def test_ondemand_on_ignores_float_and_respects_hold_cooldown_and_guard() -> None:
    base = {
        "input_select.plug-1_left_use": "dump",
        "input_select.plug-1_left_inverter": "Sungold",
        "input_select.plug-2_left_use": "dump",
        "input_select.plug-2_left_inverter": "T2",
    }
    # Charge-stage float can be off. Sun plus start volts still offers the first socket.
    st = _ok_states(**base, **{"binary_sensor.dump_charge_float": "off"})
    assert _next(st) == "switch.plug-1_left"
    assert _ondemand_on(st) == "switch.plug-1_left"
    # Cooldown blocks the button until skip cooldown is on.
    st["timer.plug-1_left_cooldown"] = "active"
    assert _ondemand_on(st) == "switch.plug-2_left"
    assert _next(_ok_states(**base, **{"timer.plug-1_left_cooldown": "active"})) == (
        "switch.plug-2_left"
    )
    st["input_boolean.dump_skip_cooldown"] = "on"
    assert _ondemand_on(st) == "switch.plug-1_left"
    assert _next(_ok_states(**base, **{
        "timer.plug-1_left_cooldown": "active",
        "input_boolean.dump_skip_cooldown": "on",
    })) == "switch.plug-1_left"
    # Hold is always respected. The voltage guard does not skip a socket by label.
    st["timer.plug-1_left_hold"] = "active"
    assert _ondemand_on(st) == "switch.plug-2_left"
    st["timer.plug-1_left_hold"] = "idle"
    st["binary_sensor.dump_inverter-1-vguard"] = "on"
    assert _ondemand_on(st) == "switch.plug-1_left"
    assert _next(_ok_states(**base, **{"binary_sensor.dump_inverter-1-vguard": "on"})) == (
        "switch.plug-1_left"
    )
    # House is never offered. A guard on does not block a KU/T2 socket's recheck.
    st["input_select.plug-1_left_inverter"] = "House"
    st["binary_sensor.dump_inverter-1-vguard"] = "off"
    assert _ondemand_on(st) == "switch.plug-2_left"


def test_ondemand_off_skips_held_house_and_normal() -> None:
    st = _ok_states(**{
        "switch.plug-1_left": "on",
        "input_select.plug-1_left_use": "dump",
        "input_select.plug-1_left_inverter": "Sungold",
        "switch.plug-2_left": "on",
        "input_select.plug-2_left_use": "dump",
        "input_select.plug-2_left_inverter": "T2",
        "timer.plug-2_left_hold": "active",
        "switch.plug-3_left": "on",
        "input_select.plug-3_left_use": "dump",
        "input_select.plug-3_left_inverter": "House",
        "switch.plug-8_left": "on",  # normal
    })
    count, sockets = _ondemand_off(st)
    assert count == "1"
    assert sockets == ["plug-1_left"]
    script_targets = _load()["script"]["dump_force_off"]["sequence"][0]["variables"]["targets"]
    assert yaml.safe_load(_render(script_targets, st).replace("'", '"')) == sockets


def test_force_scripts_let_the_hold_arm_and_revert_skip_cooldown() -> None:
    scripts = _load()["script"]
    on = _strings(scripts["dump_force_on"]["sequence"])
    off = _strings(scripts["dump_force_off"]["sequence"])
    assert "sensor.dump_ondemand_on" in on
    # No dump_control_switching event: Dump HOLD start treats the plug report as a hand switch.
    assert "dump_control_switching" not in on
    assert "dump_control_switching" not in off
    assert "input_boolean.dump_skip_cooldown" in on
    assert "input_boolean.turn_off" in on and "input_boolean.turn_off" in off
    assert "timer.plug_{{ sock }}_cooldown" in on  # cancelled after the plug reports on
    # Automatic add consumes the one-shot as it asks the socket to turn on.
    turn_on = _strings(_automations()["dump_turn_on"]["actions"])
    assert "input_boolean.dump_skip_cooldown" in turn_on
    assert "input_boolean.turn_off" in turn_on
    # Nothing in the on-demand path writes a threshold.
    for blob in (on, off):
        assert "input_number.set_value" not in blob


def test_skip_cooldown_and_guard_are_not_reset_by_the_defaults_button() -> None:
    script = _load()["script"]["dump_load_recommended_defaults"]
    blob = _strings(script)
    values = {}
    turned_on = []
    for step in script["sequence"]:
        action = step.get("action")
        eids = (step.get("target") or {}).get("entity_id")
        if isinstance(eids, str):
            eids = [eids]
        eids = eids or []
        if action == "input_number.set_value":
            for eid in eids:
                values[eid] = step["data"]["value"]
        elif action == "input_boolean.turn_on":
            turned_on.extend(eids)
    assert values["input_number.dump_inverter-1-vguard_floor_v"] == 25.6
    assert values["input_number.dump_inverter-1-vguard_margin_v"] == 0.3
    assert values["input_number.dump_inverter-1-vguard_hysteresis_v"] == 0.1
    assert values["input_number.dump_inverter-1-vguard_dwell_s"] == 60
    assert "input_boolean.dump_inverter-1-vguard_enabled" not in turned_on
    assert "input_boolean.dump_skip_cooldown" not in turned_on
    assert "input_boolean.dump_inverter-1-vguard_enabled" not in blob
    assert "input_boolean.dump_skip_cooldown" not in blob
    nums = _load()["input_number"]
    assert nums["dump_inverter-1-vguard_floor_v"]["min"] == 24.0
    assert nums["dump_inverter-1-vguard_margin_v"]["min"] == 0
    assert nums["dump_inverter-1-vguard_hysteresis_v"]["min"] == 0.05
    assert nums["dump_inverter-1-vguard_dwell_s"]["min"] == 15
    for key in (
        "dump_inverter-1-vguard_floor_v",
        "dump_inverter-1-vguard_margin_v",
        "dump_inverter-1-vguard_hysteresis_v",
        "dump_inverter-1-vguard_dwell_s",
    ):
        assert "initial" not in nums[key]


# --------------------------------------------------------- Sungold voltage guard


def _guard_states(**over) -> dict[str, str]:
    st = {
        "input_boolean.dump_inverter-1-vguard_enabled": "on",
        "sensor.sungold-inverter-1_battery_voltage": "26.65",
        "sensor.battery_1_voltage": "27.20",
        "sensor.battery_2_voltage": "27.00",
        "input_number.dump_inverter-1-vguard_floor_v": "25.6",
        "input_number.dump_inverter-1-vguard_margin_v": "0.30",
        "input_number.dump_inverter-1-vguard_hysteresis_v": "0.10",
    }
    st.update(over)
    return st


def _guard(states, was="off") -> str:
    tpl = _templates()["dump_inverter-1-vguard"]["state"]
    return _render_ha(tpl, states, this=SimpleNamespace(state=was))


def test_sungold_guard_trips_on_margin_or_floor_with_hysteresis() -> None:
    assert _guard(_guard_states()) == "on"  # 26.65 < 27.00 - 0.30
    assert _guard(_guard_states(**{"sensor.sungold-inverter-1_battery_voltage": "26.75"})) == "off"
    assert _guard(_guard_states(**{"sensor.sungold-inverter-1_battery_voltage": "26.75"}), was="on") == "on"
    assert _guard(_guard_states(**{"sensor.sungold-inverter-1_battery_voltage": "26.85"}), was="on") == "off"
    assert _guard(_guard_states(**{"sensor.sungold-inverter-1_battery_voltage": "25.50"})) == "on"
    assert _guard(_guard_states(**{"input_boolean.dump_inverter-1-vguard_enabled": "off"})) == "off"
    assert _guard(_guard_states(**{"sensor.sungold-inverter-1_battery_voltage": "unknown"})) == "off"
    # One shunt missing: the other is the reference. Both missing: floor only.
    assert _guard(_guard_states(**{
        "sensor.battery_2_voltage": "unknown",
        "sensor.sungold-inverter-1_battery_voltage": "26.85",
    })) == "on"  # 26.85 < 27.20 - 0.30
    assert _guard(_guard_states(**{
        "sensor.battery_1_voltage": "unavailable",
        "sensor.battery_2_voltage": "unavailable",
        "sensor.sungold-inverter-1_battery_voltage": "26.00",
    })) == "off"
    assert _guard(_guard_states(**{
        "sensor.battery_1_voltage": "unavailable",
        "sensor.battery_2_voltage": "unavailable",
        "sensor.sungold-inverter-1_battery_voltage": "25.00",
    })) == "on"
    reason = _render_ha(
        _templates()["dump_inverter-1-vguard"]["attributes"]["reason"],
        _guard_states(),
        this=SimpleNamespace(state="off"),
    )
    assert reason == "below T2/KU minus margin"
    gap = _render(_templates()["dump_inverter-1-vguard_gap"]["state"], _guard_states())
    assert float(gap) == -0.35


def test_sungold_guard_sheds_dump_sockets_not_by_inverter_label() -> None:
    auto = _automations()["dump_inverter-1-vguard_shed"]
    dwell = "{{ states('input_number.dump_inverter_1_vguard_dwell_s') | int(0) }}"
    assert auto["triggers"][0]["for"]["seconds"] == dwell
    assert auto["conditions"][0]["for"]["seconds"] == dwell
    blob = _strings(auto)
    for hardcoded in ("25.6", "0.30", "0.10", "00:01:00", "00:10:00"):
        assert hardcoded not in blob, hardcoded
    # The inlet-off notification is dump_inverter-1-vguard_inlet_off, not this shed.
    assert auto["conditions"][0]["entity_id"] == "binary_sensor.dump_inverter-1-vguard"
    st = _ok_states(**{
        "input_select.plug-1_left_use": "dump",
        "input_select.plug-1_left_inverter": "Sungold",
        "switch.plug-1_left": "on",
        "input_select.plug-2_left_use": "dump",
        "input_select.plug-2_left_inverter": "T2",
        "switch.plug-2_left": "on",
        "input_select.plug-3_left_use": "dump",
        "input_select.plug-3_left_inverter": "House",
        "switch.plug-3_left": "on",
        "input_boolean.dump_hold_blocks_turn_off": "off",
    })
    assert _targets("dump_inverter-1-vguard_shed", st) == ["plug-1_left", "plug-2_left"]
    st["timer.plug-1_left_hold"] = "active"
    st["input_boolean.dump_hold_blocks_turn_off"] = "on"
    assert _targets("dump_inverter-1-vguard_shed", st) == ["plug-2_left"]
    st["input_boolean.dump_hold_blocks_turn_off"] = "off"
    assert _targets("dump_inverter-1-vguard_shed", st) == ["plug-1_left", "plug-2_left"]


# -------------------------------------------------------------- Sungold charge inlet


def _charge_states(**over) -> dict[str, str]:
    st = {
        "input_boolean.inverter-1-charge_enabled": "on",
        "input_boolean.inverter-1-charge_soc_enabled": "off",
        "input_boolean.inverter-1-charge_source_soc_enabled": "off",
        "input_boolean.dump_hold_blocks_turn_off": "off",
        "input_boolean.dump_inverter-1-vguard_enabled": "off",
        "binary_sensor.dump_inverter-1-vguard": "off",
        "binary_sensor.inverter-1-charge_need": "on",
        "binary_sensor.inverter-1-charge_inlet_dark": "off",
        "sensor.sungold-inverter-1_battery_voltage": "22.0",
        "sensor.sungold-inverter-1_battery_soc": "21",
        "sensor.sungold-inverter-1_grid_voltage": "0.0",
        "sensor.sungold-inverter-1_charging_power": "0",
        "sensor.battery_1_voltage": "27.0",
        "sensor.battery_2_voltage": "27.0",
        "sensor.battery_1_state_of_charge": "99.3",
        "sensor.battery_2_state_of_charge": "99.4",
        "input_number.inverter-1-charge_floor_v": "25.0",
        "input_number.inverter-1-charge_margin_v": "0.50",
        "input_number.inverter-1-charge_full_v": "26.8",
        "input_number.inverter-1-charge_surplus_min_w": "1100",
        "input_number.inverter-1-charge_soc_below": "50",
        "input_number.inverter-1-charge_source_min_v": "26.6",
        "input_number.inverter-1-charge_source_stop_v": "26.2",
        "input_number.inverter-1-charge_source_min_soc": "90",
    }
    st.update(over)
    return st


def _need(states, was="off") -> str:
    return _render_ha(_templates()["inverter-1-charge_need"]["state"], states, this=SimpleNamespace(state=was))


def test_sungold_charge_socket_is_not_a_dump() -> None:
    """Use Sungold charge is skipped by add, shed, on-demand and the guard shed."""
    st = _ok_states(**{
        "input_select.plug-1_left_use": "Sungold charge",
        "input_select.plug-1_left_inverter": "T2",
        "switch.plug-1_left": "on",
        "input_select.plug-2_left_use": "dump",
        "input_select.plug-2_left_inverter": "T2",
        "switch.plug-2_left": "off",
    })
    assert _next(st) == "switch.plug-2_left"
    assert _shed(st) == "none"
    assert _ondemand_on(st) == "switch.plug-2_left"
    listed = _render(_templates()["dump_ondemand_off"]["attributes"]["sockets"], st)
    assert "plug-1_left" not in listed
    st["switch.plug-1_left"] = "on"
    st["switch.plug-2_left"] = "on"
    for aid in (
        "dump_turn_off_solar_gone",
        "dump_turn_off_rebulk_t2",
        "dump_turn_off_batt_t2",
        "dump_inverter-1-vguard_shed",
    ):
        assert "plug-1_left" not in _targets(aid, st), aid
    assert _targets("dump_turn_off_rebulk_t2", st) == ["plug-2_left"]
    guard = _ok_states(**{
        "input_select.plug-1_left_use": "Sungold charge",
        "input_select.plug-1_left_inverter": "Sungold",
        "switch.plug-1_left": "on",
        "input_boolean.dump_hold_blocks_turn_off": "off",
    })
    assert _targets("dump_inverter-1-vguard_shed", guard) == []


def test_sungold_charge_need_trips_and_clears_with_guard_and_soc() -> None:
    base = _charge_states()
    assert _need(base) == "on"  # 22 < 25 floor and < 27 - 0.50
    assert _need(_charge_states(**{"sensor.sungold-inverter-1_battery_voltage": "26.60"})) == "off"
    assert _need(_charge_states(**{"sensor.sungold-inverter-1_battery_voltage": "26.60"}), was="on") == "on"
    assert _need(_charge_states(**{"sensor.sungold-inverter-1_battery_voltage": "26.80"}), was="on") == "off"
    assert _need(_charge_states(**{"input_boolean.inverter-1-charge_enabled": "off"})) == "off"
    assert _need(_charge_states(**{"sensor.sungold-inverter-1_battery_voltage": "unknown"})) == "off"
    assert _need(_charge_states(**{"sensor.sungold-inverter-1_battery_voltage": "unknown"}), was="on") == "on"
    assert _need(_charge_states(**{
        "sensor.sungold-inverter-1_battery_voltage": "28.0",
        "binary_sensor.dump_inverter-1-vguard": "on",
    })) == "off"
    assert _need(_charge_states(**{
        "sensor.sungold-inverter-1_battery_voltage": "28.0",
        "binary_sensor.dump_inverter-1-vguard": "on",
    }), was="on") == "off"
    assert _need(_charge_states(**{
        "sensor.sungold-inverter-1_battery_voltage": "28.0",
        "input_boolean.inverter-1-charge_soc_enabled": "on",
    })) == "on"  # SoC 21 < 50 even though volts are high
    high = _charge_states(**{
        "sensor.sungold-inverter-1_battery_voltage": "28.0",
        "input_boolean.inverter-1-charge_soc_enabled": "on",
        "sensor.sungold-inverter-1_battery_soc": "55",
    })
    assert _need(high) == "off"
    nums = _load()["input_number"]
    for key in (
        "inverter-1-charge_floor_v",
        "inverter-1-charge_margin_v",
        "inverter-1-charge_full_v",
        "inverter-1-charge_surplus_min_w",
        "inverter-1-charge_source_min_v",
        "inverter-1-charge_source_stop_v",
        "inverter-1-charge_dwell_s",
        "inverter-1-charge_min_on_s",
    ):
        assert "initial" not in nums[key]
    assert nums["inverter-1-charge_surplus_min_w"]["min"] == 100
    assert "inverter-1-charge_target_v" not in nums
    assert "inverter-1-charge_confirm_s" not in nums
    assert "inverter-1-charge" not in _strings(_load()["script"]["dump_load_recommended_defaults"])


def test_sungold_charge_on_off_follow_source_hold_and_cooldown() -> None:
    st = _ok_states(**_charge_states(**{
        "input_select.plug-1_left_use": "Sungold charge",
        "input_select.plug-1_left_inverter": "T2",
        "switch.plug-1_left": "off",
        "input_select.plug-2_left_use": "dump",
        "input_select.plug-2_left_inverter": "T2",
        "switch.plug-2_left": "off",
    }))
    assert _targets("dump_inverter-1-charge_on", st) == ["plug-1_left"]
    st["sensor.battery_1_voltage"] = "26.0"  # under source min 26.6
    assert _targets("dump_inverter-1-charge_on", st) == []
    st["sensor.battery_1_voltage"] = "27.0"
    st["timer.plug-1_left_cooldown"] = "active"  # rescue ignores cooldown
    assert _targets("dump_inverter-1-charge_on", st) == ["plug-1_left"]
    st["timer.plug-1_left_cooldown"] = "idle"
    st["timer.plug-1_left_hold"] = "active"
    assert _targets("dump_inverter-1-charge_on", st) == []
    st["timer.plug-1_left_hold"] = "idle"
    st["input_boolean.inverter-1-charge_source_soc_enabled"] = "on"
    st["sensor.battery_1_state_of_charge"] = "80"  # under 90
    assert _targets("dump_inverter-1-charge_on", st) == []
    st["sensor.battery_1_state_of_charge"] = "99.3"
    assert _targets("dump_inverter-1-charge_on", st) == ["plug-1_left"]
    # Inverter Sungold is not a feeding bank, even if Use is Sungold charge.
    st["input_select.plug-1_left_inverter"] = "Sungold"
    assert _targets("dump_inverter-1-charge_on", st) == []
    on = _automations()["dump_inverter-1-charge_on"]
    dwell = "{{ states('input_number.inverter_1_charge_dwell_s') | int(0) }}"
    assert on["conditions"][1]["for"]["seconds"] == dwell
    blob = _strings(on)
    for hardcoded in ("25.0", "0.50", "26.6", "26.8"):
        assert hardcoded not in blob


def test_sungold_charge_off_source_stop_inlet_and_hold() -> None:
    st = _ok_states(**_charge_states(**{
        "input_select.plug_1_left_use": "Sungold charge",
        "input_select.plug_1_left_inverter": "T2",
        "switch.plug_1_left": "on",
        "sensor.battery_1_voltage": "26.0",
        "input_boolean.dump_hold_blocks_turn_off": "off",
    }))
    assert _render(_templates()["inverter_1_charge_source_stop"]["state"], st) == "on"
    assert _targets("dump_inverter_1_charge_source_stop", st) == ["plug_1_left"]
    st["timer.plug_1_left_hold"] = "active"
    st["input_boolean.dump_hold_blocks_turn_off"] = "on"
    assert _render(_templates()["inverter_1_charge_source_stop"]["state"], st) == "on"
    assert _targets("dump_inverter_1_charge_source_stop", st) == []
    st["input_boolean.dump_hold_blocks_turn_off"] = "off"
    assert _targets("dump_inverter_1_charge_source_stop", st) == ["plug_1_left"]
    st["timer.plug_1_left_hold"] = "idle"
    st["sensor.battery_1_voltage"] = "27.0"
    assert _targets("dump_inverter_1_charge_source_stop", st) == []
    assert _targets("dump_inverter_1_charge_off", st) == []  # 22.0 V is under full, so surplus owns it
    st["sensor.sungold_inverter_1_battery_voltage"] = "26.8"
    assert _targets("dump_inverter_1_charge_off", st) == ["plug_1_left"]
    st["timer.plug_1_left_hold"] = "active"
    st["input_boolean.dump_hold_blocks_turn_off"] = "on"
    assert _targets("dump_inverter_1_charge_off", st) == []

    dark = _charge_states(**{
        "input_select.plug_1_left_use": "Sungold charge",
        "switch.plug_1_left": "on",
    })
    assert _render(_templates()["inverter_1_charge_inlet_dark"]["state"], dark) == "on"
    dark["sensor.sungold_inverter_1_grid_voltage"] = "120"  # grid present: inverter waiting
    assert _render(_templates()["inverter_1_charge_inlet_dark"]["state"], dark) == "off"
    dark["sensor.sungold_inverter_1_charging_power"] = "400"
    assert _render(_templates()["inverter_1_charge_inlet_dark"]["state"], dark) == "off"
    dark["sensor.sungold_inverter_1_charging_power"] = "0"
    dark["sensor.sungold_inverter_1_grid_voltage"] = "unavailable"
    dark["sensor.sungold_inverter_1_charging_power"] = "unavailable"
    assert _render(_templates()["inverter_1_charge_inlet_dark"]["state"], dark) == "off"
    dark["sensor.sungold_inverter_1_grid_voltage"] = "120"
    dark["sensor.sungold_inverter_1_charging_power"] = "unknown"
    assert _render(_templates()["inverter_1_charge_inlet_dark"]["state"], dark) == "off"
    dark["sensor.sungold_inverter_1_grid_voltage"] = "0.0"
    dark["sensor.sungold_inverter_1_charging_power"] = "0"
    dark["switch.plug_1_left"] = "off"
    assert _render(_templates()["inverter_1_charge_inlet_dark"]["state"], dark) == "off"
    alert = _automations()["dump_inverter_1_charge_inlet_dark"]
    assert alert["triggers"][0]["for"] == "00:03:00"
    assert alert["conditions"][1]["for"] == "00:03:00"
    assert all(trig.get("trigger") != "time_pattern" for trig in alert["triggers"])
    assert "sungold_charge_inlet_dark" in _strings(alert)
    assert "inverter_1_charge_confirm_s" not in _strings(alert)
    assert _render(_templates()["inverter_1_charge_status"]["state"], _charge_states()) == "Needs charge"
    charging = _charge_states(**{
        "input_select.plug_1_left_use": "Sungold charge",
        "switch.plug_1_left": "on",
        "binary_sensor.inverter_1_charge_inlet_dark": "off",
        "sensor.sungold_inverter_1_grid_voltage": "120",
        "sensor.sungold_inverter_1_charging_power": "400",
    })
    assert _render(_templates()["inverter_1_charge_status"]["state"], charging) == "Charging"
    assert _render(
        _templates()["inverter_1_charge_status"]["state"],
        _charge_states(**{"input_boolean.inverter_1_charge_enabled": "off"}),
    ) == "Off"
    cond = next(
        a for a in _automations()["dump_hold_start"]["actions"] if a.get("condition") == "template"
    )["value_template"]
    assert "Sungold charge" in cond and "hold_min > 0" in cond


def _surplus_base(**over) -> dict[str, str]:
    return _ok_states(**_charge_states(**{
        "binary_sensor.inverter_1_charge_need": "off",
        "sensor.sungold_inverter_1_battery_voltage": "26.60",
        "input_number.inverter_1_charge_surplus_min_w": "1100",
        "sensor.battery_1_power": "1500",
        "input_select.plug_1_left_use": "Sungold charge",
        "input_select.plug_1_left_inverter": "T2",
        "switch.plug_1_left": "off",
        "input_boolean.dump_control_enabled": "off",
        **over,
    }))


def test_sungold_surplus_on_follows_bank_watts_and_stages_after_dumps() -> None:
    st = _surplus_base()
    assert _targets("dump_inverter_1_charge_surplus_on", st) == ["plug_1_left"]
    assert _render(_templates()["inverter_1_charge_surplus_ready"]["state"], st) == "on"
    st["sensor.battery_1_power"] = "500"
    assert _targets("dump_inverter_1_charge_surplus_on", st) == []
    st["sensor.battery_1_power"] = "1500"
    st["binary_sensor.inverter_1_charge_need"] = "on"
    assert _targets("dump_inverter_1_charge_surplus_on", st) == []
    st["binary_sensor.inverter_1_charge_need"] = "off"
    for key, block in (
        ("binary_sensor.dump_solar_present", "off"),
        ("binary_sensor.dump_v_float_t2", "off"),
        ("binary_sensor.dump_v_rebulk_t2", "on"),
        ("binary_sensor.dump_batt_battery_2_ok", "off"),
    ):
        st[key] = block
        assert _targets("dump_inverter_1_charge_surplus_on", st) == [], key
        st[key] = "on" if key != "binary_sensor.dump_v_rebulk_t2" else "off"
    st["sensor.sungold_inverter_1_battery_voltage"] = "26.80"
    assert _targets("dump_inverter_1_charge_surplus_on", st) == []
    st["sensor.sungold_inverter_1_battery_voltage"] = "26.60"
    st["timer.plug_1_left_cooldown"] = "active"
    assert _targets("dump_inverter_1_charge_surplus_on", st) == []
    st["timer.plug_1_left_cooldown"] = "idle"
    st["input_boolean.dump_control_enabled"] = "on"
    st["input_select.plug_2_left_use"] = "dump"
    st["input_select.plug_2_left_inverter"] = "T2"
    assert _next(st) == "switch.plug_2_left"
    st["sensor.dump_next_plug"] = "switch.plug_2_left"
    assert _targets("dump_inverter_1_charge_surplus_on", st) == []
    assert _render(_templates()["inverter_1_charge_surplus_ready"]["state"], st) == "off"
    st["input_boolean.dump_control_enabled"] = "off"
    assert _targets("dump_inverter_1_charge_surplus_on", st) == ["plug_1_left"]
    assert _render(
        _templates()["inverter_1_charge_status"]["state"],
        _surplus_base(**{"switch.plug_1_left": "on"}),
    ) == "On, under full volts"


def test_sungold_surplus_off_leaves_rescue_and_full_volts_alone() -> None:
    st = _surplus_base(**{
        "switch.plug_1_left": "on",
        "sensor.battery_1_power": "500",
    })
    assert _targets("dump_inverter_1_charge_surplus_off", st) == ["plug_1_left"]
    assert _render(_templates()["inverter_1_charge_surplus_stop"]["state"], st) == "on"
    st["sensor.battery_1_power"] = "1500"
    assert _targets("dump_inverter_1_charge_surplus_off", st) == []
    st["sensor.battery_1_power"] = "500"
    st["timer.plug_1_left_min_on"] = "active"
    assert _targets("dump_inverter_1_charge_surplus_off", st) == []
    st["timer.plug_1_left_min_on"] = "idle"
    st["sensor.sungold_inverter_1_battery_voltage"] = "26.80"
    assert _targets("dump_inverter_1_charge_surplus_off", st) == []
    assert _targets("dump_inverter_1_charge_off", st) == ["plug_1_left"]
    st["sensor.sungold_inverter_1_battery_voltage"] = "unknown"
    assert _targets("dump_inverter_1_charge_surplus_off", st) == ["plug_1_left"]
    assert _targets("dump_inverter_1_charge_off", st) == []
    st["sensor.sungold_inverter_1_battery_voltage"] = "26.60"
    st["binary_sensor.inverter_1_charge_need"] = "on"
    assert _targets("dump_inverter_1_charge_surplus_off", st) == []
    for aid in ("dump_turn_off_solar_gone", "dump_turn_off_rebulk_t2", "dump_turn_off_batt_t2"):
        assert "plug_1_left" not in _targets(aid, st), aid


def test_soc_hold_blocks_cloud_trips_until_the_floor() -> None:
    """Lower SoC above 91 holds dumps. At or below 90 the cloud trips run."""
    tpl = _templates()["dump_soc_hold_trips"]["state"]
    base = {
        "input_boolean.dump_soc_unsynced": "off",
        "input_number.dump_soc_no_trip_percent": "91",
        "input_number.dump_soc_trip_floor_percent": "90",
        "sensor.battery_1_state_of_charge": "98",
        "sensor.battery_2_state_of_charge": "97",
    }
    assert _render_ha(tpl, base, this=SimpleNamespace(state="off")) == "True"
    # Lower bank is T2 at 82 even when the average would still look high.
    low_bank = dict(base, **{"sensor.battery_1_state_of_charge": "82", "sensor.battery_2_state_of_charge": "100"})
    assert _render_ha(tpl, low_bank, this=SimpleNamespace(state="on")) == "False"
    at_floor = dict(base, **{"sensor.battery_1_state_of_charge": "90", "sensor.battery_2_state_of_charge": "99"})
    assert _render_ha(tpl, at_floor, this=SimpleNamespace(state="on")) == "False"
    # Between 90 and 91 the previous state is kept.
    band = dict(base, **{"sensor.battery_1_state_of_charge": "90.4", "sensor.battery_2_state_of_charge": "96"})
    assert _render_ha(tpl, band, this=SimpleNamespace(state="on")) == "True"
    assert _render_ha(tpl, band, this=SimpleNamespace(state="off")) == "False"
    unsynced = dict(base, **{"input_boolean.dump_soc_unsynced": "on"})
    assert _render_ha(tpl, unsynced, this=SimpleNamespace(state="on")) == "False"
    inverted = dict(base, **{"input_number.dump_soc_trip_floor_percent": "95"})
    assert _render_ha(tpl, inverted, this=SimpleNamespace(state="on")) == "False"

    gated = {
        "dump_turn_off_rebulk_t2",
        "dump_turn_off_rebulk_ku",
        "dump_turn_off_batt_t2",
        "dump_turn_off_batt_ku",
        "dump_turn_off_bulk",
        "dump_shed_load_exceeds_solar",
    }
    autos = _automations()
    for aid in gated:
        conds = autos[aid]["conditions"]
        assert any(
            isinstance(c, dict)
            and c.get("entity_id") == "binary_sensor.dump_soc_hold_trips"
            and c.get("state") == "off"
            for c in conds
        ), aid
    for aid in ("dump_turn_off_solar_gone", "dump_turn_off_rebulk_sph", "dump_turn_off_batt_sph", "dump_inverter_1_vguard_shed"):
        assert "dump_soc_hold_trips" not in _strings(autos[aid].get("conditions", "")), aid
    for aid in ("dump_turn_off_bulk", "dump_shed_load_exceeds_solar"):
        assert "dump_soc_hold_trips" in _strings(autos[aid]["actions"][0]["repeat"]["while"])
    defaults = _strings(_load()["script"]["dump_load_recommended_defaults"])
    assert "input_number.dump_soc_no_trip_percent" in defaults
    assert "input_number.dump_soc_trip_floor_percent" in defaults



def test_sungold_charge_on_waits_for_the_plug_and_alarms_once() -> None:
    """Send ON once, wait for the plug, then timer and log; no report raises one notification."""
    autos = _automations()
    for aid, timer in (("dump_inverter_1_charge_on", True), ("dump_inverter_1_charge_surplus_on", False)):
        auto = autos[aid]
        assert auto["mode"] == "single", aid
        step = auto["actions"][-1]["repeat"]["sequence"][0]
        assert "_held_by_you" in step["if"][0]["value_template"], aid
        then = step["then"]
        assert [s.get("action") for s in then[:2]] == [None, "switch.turn_on"], aid
        assert then[0]["event"] == "dump_control_switching", aid
        wait = then[2]
        assert wait["timeout"] == "00:03:00" and wait["continue_on_timeout"] is True, aid
        assert then[3]["variables"]["switched"] == "{{ wait.completed }}", aid
        gate = then[-1]
        ok = [s.get("action") for s in gate["then"]]
        bad = [s.get("action") for s in gate["else"]]
        assert ("timer.start" in ok) is timer, aid
        assert ok[-2:] == ["logbook.log", "persistent_notification.dismiss"], aid
        assert bad == ["logbook.log", "persistent_notification.create"], aid
        nid = "plug_no_switch_{{ sock }}"
        assert gate["then"][-1]["data"]["notification_id"] == nid, aid
        assert gate["else"][-1]["data"]["notification_id"] == nid, aid
        assert "switch.turn_on" not in _strings(gate), aid


def test_defaults_button_matches_the_soc_band_and_leaves_ignore_soc() -> None:
    script = _load()["script"]["dump_load_recommended_defaults"]
    values = {}
    turned_on = []
    for step in script["sequence"]:
        eids = (step.get("target") or {}).get("entity_id") or []
        if isinstance(eids, str):
            eids = [eids]
        if step.get("action") == "input_number.set_value":
            for eid in eids:
                values[eid] = step["data"]["value"]
        elif step.get("action") == "input_boolean.turn_on":
            turned_on.extend(eids)
    assert values["input_number.dump_min_soc_percent"] == 90
    assert values["input_number.dump_soc_no_trip_percent"] == 91
    assert values["input_number.dump_soc_trip_floor_percent"] == 90
    assert "input_boolean.dump_soc_unsynced" not in _strings(script)
    assert turned_on == ["input_boolean.dump_hold_blocks_turn_off"]


def test_dump_add_moves_on_until_a_watt_rise() -> None:
    """A plug that never reports on is cooled down. A watt rise stops adding."""
    auto = _automations()["dump_turn_on"]
    blob = _strings(auto)
    assert "did not report on within 2 minutes" in blob
    assert "on but no watt rise" in blob
    assert "measured load on this dump" in blob
    assert "input_number.dump_site_delta_min_w" in blob
    assert "timer.plug_{{ sock }}_cooldown" in blob
