"""Shared mode: every radio may drive every plug; one acts per command, the next fails over.

No BlueZ and no broker: the MQTT client is a Mock and BLE is a scripted fake.
"""

from __future__ import annotations

import asyncio
import json
import time
import types
from datetime import datetime
from unittest.mock import Mock

import pytest

govee_main = pytest.importorskip("govee_h5082.__main__")
from govee_h5082.mqtt_bridge import (  # noqa: E402
    LINK_STATES,
    LISTENERS,
    PLUGS,
    avail_topic,
    discovery_topic,
    link_discovery_topic,
    link_topic,
    owner_topic,
    result_topic,
    state_topic,
)

A = PLUGS[0][0]  # plug-1
MAC = A.replace(":", "").lower()
TOKEN = "change-me"


class FakeClient:
    def __init__(self, world, device, disconnected_callback=None, timeout=None, **_kw):
        self.world = world
        self.address = device.address
        self.cb = disconnected_callback
        self.is_connected = False
        self.notify = None

    async def connect(self):
        self.world.connects.append(self.address)
        await asyncio.sleep(0.005)
        fails = self.world.connect_fail
        if fails:
            raise fails.pop(0)
        self.is_connected = True

    async def disconnect(self):
        self.is_connected = False

    async def start_notify(self, _uuid, cb):
        self.notify = cb

    async def write_gatt_char(self, _uuid, data):
        if data[1] == 0xB2:
            self.notify(None, bytearray([0x33, 0xB2]))
            return
        fails = self.world.write_fail
        if fails:
            raise fails.pop(0)
        self.world.writes.append((self.address, bytes(data)))
        self.notify(None, bytearray([0x33, 0x01]))


@pytest.fixture
def world(monkeypatch):
    w = types.SimpleNamespace(connects=[], writes=[], connect_fail=[], write_fail=[], find_fail=[])

    class Scanner:
        @staticmethod
        async def find_device_by_address(address, timeout=10.0, **_kw):
            if w.find_fail:
                w.find_fail.pop(0)
                return None
            return types.SimpleNamespace(address=address)

    monkeypatch.setattr(govee_main, "_bleak_scanner_cls", lambda: Scanner)
    monkeypatch.setattr(govee_main, "_bleak_client_cls", lambda: lambda *a, **k: FakeClient(w, *a, **k))
    monkeypatch.setattr(govee_main, "RETRY_BACKOFF_S", (0.0, 0.0))
    monkeypatch.setattr(govee_main, "FAILOVER_POLL_S", 0.01)
    monkeypatch.setattr(govee_main, "IDLE_DISCONNECT_S", 0.05)
    return w


def _make(monkeypatch, listener="solar-broker", adapter="hci1", keys=None, extra=None):
    monkeypatch.setenv("MQTT_HOST", "broker.invalid")
    monkeypatch.setenv("MQTT_USER", "u")
    monkeypatch.setenv("MQTT_PASSWORD", "p")
    monkeypatch.setenv("plug_LISTENER", listener)
    monkeypatch.setenv("plug_ADAPTER", adapter)
    monkeypatch.setenv("plug_SHARED", "1")
    for name in ("plug_PLUGS", "plug_RSSI_ONLY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in (extra or {}).items():
        monkeypatch.setenv(name, value)
    found = {address: TOKEN for address, _name in PLUGS} if keys is None else keys
    monkeypatch.setattr(govee_main, "load_keys", lambda: dict(found))
    client = Mock()
    client.is_connected.return_value = True
    monkeypatch.setattr(govee_main.mqtt, "Client", lambda *_a, **_k: client)
    return govee_main.Bridge()


def _msg(topic, payload):
    return types.SimpleNamespace(topic=topic, payload=payload.encode())


def _pubs(br):
    return [(c.args[0], c.args[1], c.kwargs) for c in br._client.publish.call_args_list]


def _payloads(br, topic):
    return [p for t, p, _k in _pubs(br) if t == topic]


def _feed(br, topic, payload):
    br._on_message(None, None, _msg(topic, payload))


def _online(br, *names):
    for name in names:
        _feed(br, f"govee/plugs/bridge/{name}/status", "online")


def _rssi(br, name, value, plug_mac=MAC):
    """Another radio's retained signal step for its 2-min average ``value`` dBm."""
    _feed(br, f"govee/plugs/{plug_mac}/signal/{name}", str(value // govee_main.RSSI_STEP_DB))


def _iso(offset_s=0.0):
    return datetime.fromtimestamp(time.time() + offset_s).astimezone().isoformat(timespec="seconds")


def _result(br, name, want, ok, side="left"):
    _feed(br, f"govee/plugs/{MAC}/{side}/result", json.dumps({"listener": name, "want": want, "ok": ok}))


async def _until(pred, timeout=3.0):
    end = time.monotonic() + timeout
    while not pred():
        if time.monotonic() > end:
            raise AssertionError("condition not reached")
        await asyncio.sleep(0.005)


# --- config --------------------------------------------------------------------------


def test_shared_config_is_the_same_for_every_radio(monkeypatch):
    br = _make(monkeypatch)
    br.publish_config()
    switches = {t: json.loads(p) for t, p, _k in _pubs(br) if t.startswith("homeassistant/switch/")}
    assert len(switches) == 16
    for payload in switches.values():
        assert "availability_topic" not in payload
        assert payload["availability"] == [{"topic": avail_topic(n)} for n in LISTENERS]
        assert payload["availability_mode"] == "any"
    other = _make(monkeypatch, listener="monitor", adapter="hci0", keys={A: TOKEN})
    other.publish_config()
    assert {t: json.loads(p) for t, p, _k in _pubs(other) if t.startswith("homeassistant/switch/")} == switches
    link = json.loads(_payloads(br, link_discovery_topic(A, "solar-broker"))[0])
    assert link["device_class"] == "enum" and link["options"] == list(LINK_STATES)
    assert link["state_topic"] == link["json_attributes_topic"] == link_topic(A, "solar-broker")
    assert link["availability_topic"] == avail_topic("solar-broker")
    subs = {c.args[0] for c in br._client.subscribe.call_args_list}
    assert {"govee/plugs/+/+/set", "govee/plugs/+/+/result", "govee/plugs/+/link/+"} <= subs
    assert not [t for t, p, _k in _pubs(br) if t.endswith("/owner") and p]
    assert br.describe().startswith("OWNS plug-1") and "mode=shared" in br.describe()


def test_plugs_without_a_key_report_no_key(monkeypatch, capsys):
    br = _make(monkeypatch, listener="monitor", adapter="hci0", keys={A: TOKEN})
    br.startup_report()
    br.publish_config()
    assert "NO_KEY plug-2" in capsys.readouterr().out
    other = PLUGS[1][0]
    assert json.loads(_payloads(br, link_topic(other, "monitor"))[-1])["state"] == "no_key"
    assert _payloads(br, link_topic(A, "monitor")) == []  # untried: no report yet


def test_shared_rejects_allowlist_and_unknown_radio(monkeypatch):
    with pytest.raises(SystemExit, match="remove plug_PLUGS"):
        _make(monkeypatch, extra={"plug_PLUGS": "plug-1"})
    with pytest.raises(SystemExit, match="not one of"):
        _make(monkeypatch, listener="pi9", adapter="hci0")


def test_shared_releases_own_old_claims(monkeypatch, capsys):
    br = _make(monkeypatch)
    _feed(br, f"govee/plugs/{MAC}/owner", "solar-broker")
    br._client.publish.assert_called_once_with(owner_topic(A), "", qos=1, retain=True)
    _feed(br, f"govee/plugs/{MAC}/owner", "monitor")
    out = capsys.readouterr().out
    assert "OWNER_RELEASE plug-1" in out and "OWNER_MIXED plug-1 claimed by monitor" in out


# --- ranking ---------------------------------------------------------------------------


def test_rank_prefers_link_then_health_then_signal_then_order(monkeypatch):
    br = _make(monkeypatch)
    assert br.rank_listeners(A) == ["solar-broker"]  # others not online yet
    _online(br, "monitor", "apps")
    assert br.rank_listeners(A) == ["monitor", "apps", "solar-broker"]  # nobody heard it: tie order
    _rssi(br, "solar-broker", -50)
    _rssi(br, "monitor", -80)
    assert br.rank_listeners(A) == ["solar-broker", "monitor", "apps"]
    _rssi(br, "apps", -51)  # same 4 dB step as solar-broker: tie order puts apps first
    assert br.rank_listeners(A)[:2] == ["apps", "solar-broker"]
    _feed(br, link_topic(A, "apps"), json.dumps({"state": "connect_timeout", "last_fail": _iso()}))
    assert br.rank_listeners(A) == ["solar-broker", "monitor", "apps"]
    _feed(br, link_topic(A, "monitor"), json.dumps({"state": "ok", "connected": True}))
    assert br.rank_listeners(A)[0] == "monitor"
    _feed(br, link_topic(A, "monitor"), json.dumps({"state": "no_key"}))
    _feed(br, "govee/plugs/bridge/apps/status", "offline")
    assert br.rank_listeners(A) == ["solar-broker"]


def test_failure_age_comes_from_the_report_not_arrival(monkeypatch):
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "monitor", -40)
    _feed(br, link_topic(A, "monitor"), json.dumps({"state": "no_ack", "last_fail": _iso(-60)}))
    assert br.rank_listeners(A) == ["solar-broker", "monitor"]
    # A bridge that restarts gets the same retained report much later: it is old news.
    old = _iso(-govee_main.FAIL_DEMOTE_S - 60)
    _feed(br, link_topic(A, "monitor"), json.dumps({"state": "no_ack", "last_fail": old}))
    assert br.rank_listeners(A) == ["monitor", "solar-broker"]
    _feed(br, f"govee/plugs/{MAC}/signal/monitor", "")  # monitor stopped hearing it: tie order
    assert br.rank_listeners(A) == ["monitor", "solar-broker"]
    _rssi(br, "solar-broker", -70)
    assert br.rank_listeners(A) == ["solar-broker", "monitor"]


def test_two_bridges_rank_the_same_from_retained_data(monkeypatch):
    retained = [
        ("govee/plugs/bridge/monitor/status", "online"),
        ("govee/plugs/bridge/apps/status", "online"),
        ("govee/plugs/bridge/solar-broker/status", "online"),
        (f"govee/plugs/{MAC}/signal/monitor", "-15"),
        (f"govee/plugs/{MAC}/signal/solar-broker", "-16"),
        (link_topic(A, "apps"), json.dumps({"state": "connect_timeout", "last_fail": _iso(-30)})),
    ]
    orders = []
    for listener, adapter in (("solar-broker", "hci1"), ("monitor", "hci0"), ("apps", "hci0")):
        br = _make(monkeypatch, listener=listener, adapter=adapter)
        for topic, payload in retained:
            _feed(br, topic, payload)
        orders.append(br.rank_listeners(A))
    assert orders[0] == orders[1] == orders[2] == ["monitor", "solar-broker", "apps"]


def test_own_signal_step_is_published_on_change_and_cleared(monkeypatch):
    br = _make(monkeypatch)
    topic = f"govee/plugs/{MAC}/signal/solar-broker"
    br.publish_rssi(A, -50)
    br.publish_rssi(A, -51)  # same 4 dB step: no new message
    assert _payloads(br, topic) == ["-13"]
    br.publish_rssi(A, -70)  # average -57 -> step -15
    assert _payloads(br, topic) == ["-13", "-15"]
    later = time.monotonic() + govee_main.RSSI_WINDOW_S + 1
    monkeypatch.setattr(govee_main.time, "monotonic", lambda: later)
    br.note_own_signal(A)
    assert _payloads(br, topic)[-1] == ""  # unheard for 2 min


# --- commands ---------------------------------------------------------------------------


def test_first_in_line_acts_and_reports(world, monkeypatch, capsys):
    br = _make(monkeypatch)
    _feed(br, link_topic(A, "solar-broker"), json.dumps({"state": "ok", "fails": 0}))  # earlier report

    async def run():
        br._state[(A, "left")] = False
        await br.shared_command(A, "left", True)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    out = capsys.readouterr().out
    assert "LINE plug-1 left ON solar-broker" in out and "SET plug-1 left ON" in out
    assert json.loads(_payloads(br, result_topic(A, "left"))[-1]) == {"listener": "solar-broker", "want": "ON", "ok": True}
    reports = [json.loads(p) for p in _payloads(br, link_topic(A, "solar-broker"))]
    assert reports[0]["busy"] is False
    assert any(r["busy"] for r in reports) and any(r["connected"] for r in reports)
    assert reports[-1]["state"] == "ok" and reports[-1]["fails"] == 0 and reports[-1]["last_ok"]
    assert TOKEN not in out


def test_second_in_line_takes_over_when_the_first_fails(world, monkeypatch, capsys):
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "monitor", -40)

    async def run():
        br._state[(A, "left")] = False
        await br.shared_command(A, "left", True)
        await asyncio.sleep(0.05)
        assert world.connects == []  # waiting for monitor
        _result(br, "monitor", "ON", False)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    out = capsys.readouterr().out
    assert "LINE plug-1 left ON monitor,solar-broker" in out
    assert "FAILOVER plug-1 left ON after monitor" in out and "SET plug-1 left ON" in out


def test_second_in_line_drops_the_command_after_a_success(world, monkeypatch):
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "monitor", -40)

    async def run():
        await br.shared_command(A, "left", True)
        _result(br, "monitor", "OFF", True)  # other command: does not count
        await asyncio.sleep(0.03)
        assert br._turns
        _result(br, "monitor", "ON", True)
        await _until(lambda: not br._turns)

    asyncio.run(run())
    assert world.connects == []


def test_radio_ahead_going_offline_hands_over(world, monkeypatch, capsys):
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "monitor", -40)

    async def run():
        await br.shared_command(A, "left", False)
        _feed(br, "govee/plugs/bridge/monitor/status", "offline")
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    assert "FAILOVER plug-1 left OFF after monitor" in capsys.readouterr().out


def test_silent_radio_ahead_times_out(world, monkeypatch, capsys):
    monkeypatch.setattr(govee_main, "FAILOVER_WAIT_S", 0.05)
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "monitor", -40)

    async def run():
        await br.shared_command(A, "left", True)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    assert "FAILOVER_TIMEOUT plug-1 left ON after monitor" in capsys.readouterr().out


def test_newer_command_replaces_a_waiting_one(world, monkeypatch):
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "monitor", -40)

    async def run():
        await br.shared_command(A, "left", True)
        first = br._turns[(A, "left")]
        await br.shared_command(A, "left", False)
        await asyncio.sleep(0.01)
        assert first.cancelled()
        _result(br, "monitor", "ON", False)  # failure for the old command: no takeover
        await asyncio.sleep(0.05)
        assert world.connects == []
        _result(br, "monitor", "OFF", False)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    assert json.loads(_payloads(br, result_topic(A, "left"))[-1])["want"] == "OFF"


def test_failure_hands_off_without_flipping_the_switch(world, monkeypatch, capsys):
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "solar-broker", -40)
    world.connect_fail[:] = [OSError("br-connection-canceled")] * 3

    async def run():
        br._state[(A, "left")] = False
        await br.shared_command(A, "left", True)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    out = capsys.readouterr().out
    assert "SET_FAIL plug-1 left ON handing off" in out
    assert _payloads(br, state_topic(A, "left")) == []  # monitor still to try
    assert json.loads(_payloads(br, result_topic(A, "left"))[-1])["ok"] is False
    report = json.loads(_payloads(br, link_topic(A, "solar-broker"))[-1])
    assert report["state"] == "error" and report["fails"] == 1 and "br-connection-canceled" in report["error"]


def test_last_in_line_puts_the_switch_back(world, monkeypatch, capsys):
    br = _make(monkeypatch)
    world.connect_fail[:] = [OSError("x")] * 3

    async def run():
        br._state[(A, "left")] = False
        await br.shared_command(A, "left", True)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    assert "SET_FAIL plug-1 left ON\n" in capsys.readouterr().out
    assert _payloads(br, state_topic(A, "left"))[-1] == "OFF"


@pytest.mark.parametrize(
    ("setup", "state"),
    [
        (lambda w: w.connect_fail.extend([TimeoutError()] * 3), "connect_timeout"),
        (lambda w: w.find_fail.extend([1] * 3), "not_heard"),
        (lambda w: w.write_fail.extend([TimeoutError("no ack")] * 3), "no_ack"),
    ],
)
def test_link_report_names_the_failure(world, monkeypatch, setup, state):
    monkeypatch.setattr(govee_main, "ADAPTER_RESET_AFTER", 0)
    br = _make(monkeypatch)
    setup(world)

    async def run():
        await br.shared_command(A, "left", True)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    assert json.loads(_payloads(br, link_topic(A, "solar-broker"))[-1])["state"] == state


def test_success_elsewhere_holds_advertisements(monkeypatch):
    br = _make(monkeypatch)
    br._state[(A, "left")] = False
    _result(br, "monitor", "ON", True)
    assert br._state[(A, "left")] is True
    br.note_advertisement(A, 0)  # stale ad (left off) sent just before the switch
    assert _payloads(br, state_topic(A, "left")) == []


def test_state_topic_keeps_radios_in_step(monkeypatch):
    br = _make(monkeypatch)
    _feed(br, state_topic(A, "left"), "ON")
    br.note_advertisement(A, 2)  # left on: already known, nothing to publish
    assert _payloads(br, state_topic(A, "left")) == []


def test_own_report_after_restart_drops_stale_flags(monkeypatch):
    br = _make(monkeypatch)
    old = {"state": "connect_timeout", "connected": True, "busy": True, "fails": 4,
           "last_ok": "2026-10-06T10:00:00-0400", "last_fail": "2026-10-06T11:00:00-0400", "error": "x"}
    _feed(br, link_topic(A, "solar-broker"), json.dumps(old))
    report = json.loads(_payloads(br, link_topic(A, "solar-broker"))[-1])
    assert report["connected"] is False and report["busy"] is False
    assert report["fails"] == 4 and report["state"] == "connect_timeout"


def test_reconnect_does_not_republish_cached_state(monkeypatch):
    br = _make(monkeypatch)
    br._state[(A, "left")] = False  # stale: another radio switched it on meanwhile
    br.publish_config()
    assert _payloads(br, state_topic(A, "left")) == []


def test_stops_retrying_once_another_radio_succeeds(world, monkeypatch, capsys):
    br = _make(monkeypatch)
    world.connect_fail[:] = [OSError("busy")] * 3

    async def run():
        await br.shared_command(A, "left", True)
        await _until(lambda: world.connects)
        _result(br, "monitor", "ON", True)
        await _until(lambda: "DONE_ELSEWHERE" in capsys.readouterr().out or len(world.connects) >= 3)

    asyncio.run(run())
    assert len(world.connects) < 3
    assert _payloads(br, result_topic(A, "left")) == []


def test_waiting_radio_keeps_waiting_while_the_one_ahead_is_busy(world, monkeypatch, capsys):
    monkeypatch.setattr(govee_main, "FAILOVER_WAIT_S", 0.1)
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "monitor", -40)
    _feed(br, link_topic(A, "monitor"), json.dumps({"state": "ok", "busy": True}))

    async def run():
        await br.shared_command(A, "left", True)
        await asyncio.sleep(0.2)  # past the 0.1 s wait, before the 0.3 s cap
        assert world.connects == []
        _feed(br, link_topic(A, "monitor"), json.dumps({"state": "ok", "busy": False}))
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    assert "FAILOVER_TIMEOUT plug-1 left ON after monitor" in capsys.readouterr().out


def _connected(br, monkeypatch, settle=0.0):
    monkeypatch.setattr(govee_main, "RETAINED_SETTLE_S", settle)
    br.publish_config()
    br._client.publish.reset_mock()


def test_stale_cached_advertisement_is_ignored(monkeypatch):
    br = _make(monkeypatch)
    _connected(br, monkeypatch)
    _online(br, "apps")
    _feed(br, link_topic(A, "apps"), json.dumps({"state": "ok", "connected": True}))
    _feed(br, state_topic(A, "left"), "ON")
    _feed(br, state_topic(A, "right"), "ON")
    br.note_advertisement(A, 0)  # BlueZ cache from before apps switched it on
    br.note_advertisement(A, 0)
    assert _payloads(br, state_topic(A, "left")) == []
    br.note_advertisement(A, 2)  # a new advertisement (left on, right off): news
    assert _payloads(br, state_topic(A, "right")) == ["OFF"]


def test_first_advertisement_counts_when_nobody_holds_the_link(monkeypatch):
    br = _make(monkeypatch)
    _connected(br, monkeypatch)
    _feed(br, state_topic(A, "left"), "OFF")
    _feed(br, link_topic(A, "apps"), json.dumps({"state": "ok", "connected": True}))  # apps offline
    br.note_advertisement(A, 2)  # button pressed while the bridges were down
    assert _payloads(br, state_topic(A, "left")) == ["ON"]


def test_first_advertisement_waits_for_retained_data(monkeypatch):
    br = _make(monkeypatch)
    _connected(br, monkeypatch, settle=10.0)
    br.note_advertisement(A, 0)  # retained state and links may still be in flight
    assert _payloads(br, state_topic(A, "left")) == []
    _feed(br, state_topic(A, "left"), "ON")
    monkeypatch.setattr(govee_main, "RETAINED_SETTLE_S", 0.0)
    br.note_advertisement(A, 0)  # not taken as a baseline earlier: judged now
    assert _payloads(br, state_topic(A, "left")) == ["OFF"]


def test_busy_is_reported_before_the_first_result(world, monkeypatch):
    br = _make(monkeypatch)

    async def run():
        await br.shared_command(A, "left", True)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    reports = [json.loads(p) for p in _payloads(br, link_topic(A, "solar-broker"))]
    assert reports[0]["busy"] is True and reports[0]["state"] is None
    assert reports[-1]["state"] == "ok" and reports[-1]["busy"] is False


def test_a_report_stuck_on_busy_does_not_block_forever(world, monkeypatch, capsys):
    monkeypatch.setattr(govee_main, "FAILOVER_WAIT_S", 0.05)
    br = _make(monkeypatch)
    _online(br, "monitor")
    _rssi(br, "monitor", -40)
    _feed(br, link_topic(A, "monitor"), json.dumps({"state": "ok", "busy": True}))

    async def run():
        await br.shared_command(A, "left", True)
        await _until(lambda: _payloads(br, result_topic(A, "left")))

    asyncio.run(run())
    assert "FAILOVER_TIMEOUT plug-1 left ON after monitor" in capsys.readouterr().out


def test_per_host_mode_is_unchanged(monkeypatch):
    monkeypatch.delenv("plug_SHARED", raising=False)
    monkeypatch.setenv("MQTT_HOST", "broker.invalid")
    monkeypatch.setenv("MQTT_USER", "u")
    monkeypatch.setenv("MQTT_PASSWORD", "p")
    monkeypatch.setenv("plug_LISTENER", "monitor")
    monkeypatch.setenv("plug_ADAPTER", "hci0")
    monkeypatch.setenv("plug_PLUGS", "plug-1")
    monkeypatch.setattr(govee_main, "load_keys", lambda: {A: TOKEN})
    client = Mock()
    client.is_connected.return_value = True
    monkeypatch.setattr(govee_main.mqtt, "Client", lambda *_a, **_k: client)
    br = govee_main.Bridge()
    br.publish_config()
    payload = json.loads(_payloads(br, discovery_topic(A, "left"))[0])
    assert payload["availability_topic"] == avail_topic("monitor") and "availability" not in payload
    assert not [t for t, _p, _k in _pubs(br) if "/link/" in t or "_link_" in t]
