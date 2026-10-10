"""Run the H5082 MQTT bridge. See mqtt_bridge.py for the protocol."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import os
import re
import time
from datetime import datetime

import paho.mqtt.client as mqtt
from dbus_fast import BusType, Variant
from dbus_fast.aio import MessageBus

from govee_h5082.mqtt_bridge import (
    AVAIL_LEGACY,
    LISTENERS,
    PLUGS,
    RECV_UUID,
    SEND_UUID,
    auth_packet,
    avail_topic,
    command_bytes,
    discovery_payload,
    discovery_topic,
    dumps,
    iter_switches,
    key_file_problem,
    key_path,
    link_discovery_payload,
    link_discovery_topic,
    link_topic,
    load_keys,
    owner_topic,
    parse_owned,
    payload_for,
    result_topic,
    rssi_discovery_payload,
    signal_topic,
    rssi_discovery_topic,
    rssi_topic,
    socket_on,
    state_topic,
)

MAC_HEX_LEN = 12
BLEAK_BLUEZ_ADAPTER_MAJOR = 3  # first bleak with bluez={"adapter": ...}
OWNER_TOPIC_PARTS = 4  # govee/plugs/<mac>/owner
AVAIL = AVAIL_LEGACY  # kept for callers; a per-host bridge uses Bridge._avail
HOLD_S = 20
# Poll every 10 s; re-read the BlueZ object tree every RESCAN_EVERY polls (~60 s).
RESCAN_EVERY = 6

# GATT timing (unchanged from the one-shot client): connect 20 s, auth reply 8 s,
# command reply 8 s. FIND_TIMEOUT_S is the address lookup the old
# BleakClient(address) did inside its 20 s connect when BlueZ had no device object.
CONNECT_TIMEOUT_S = 20
ACK_TIMEOUT_S = 8
FIND_TIMEOUT_S = 20
# A failed command is tried RETRIES times in total, sleeping RETRY_BACKOFF_S between.
RETRIES = 3
RETRY_BACKOFF_S = (1.0, 2.0)
# Keep a plug's GATT link open this long after its last command so bursts (dump
# staging, retries, left+right) reuse one login. 0 keeps links open until they drop.
# The plug does not advertise while connected, so a link held forever would hide
# button presses and RSSI ("heard by") for that plug.
IDLE_DISCONNECT_S = float(os.environ.get("plug_IDLE_DISCONNECT_S", "120"))

DBus_TIMEOUT_S = float(os.environ.get("plug_DBUS_TIMEOUT_S", "15.0"))
# A stuck controller completes the LE link but never the feature exchange, so every
# connect times out until the adapter is powered off and on (docs/plug_MULTI_BRIDGE.md).
ADAPTER_RESET_AFTER = int(os.environ.get("plug_ADAPTER_RESET_AFTER", "3"))
ADAPTER_RESET_GAP_S = float(os.environ.get("plug_ADAPTER_RESET_GAP_S", "600"))
ADAPTER_POWER_OFF_S = 2.0
ADAPTER_POWER_ON_S = 3.0

# Shared mode (plug_SHARED=1): every radio may drive every plug; one acts per command
# and the next takes over on failure (docs/plug_MULTI_BRIDGE.md "Shared mode").
FAILOVER_WAIT_S = 240.0  # per radio ahead in line that never reports
FAILOVER_POLL_S = 0.25
FAIL_DEMOTE_S = 600.0
RSSI_WINDOW_S = 120.0
RSSI_STEP_DB = 4
UNHEARD = 999
# After connecting to the broker, wait this long for retained link reports and state
# before judging a plug's first advertisement.
RETAINED_SETTLE_S = 10.0


def _bleak_client_cls():
    from bleak import BleakClient

    return BleakClient


def _bleak_scanner_cls():
    from bleak import BleakScanner

    return BleakScanner


def bleak_version() -> str:
    try:
        return importlib.metadata.version("bleak")
    except importlib.metadata.PackageNotFoundError:
        return "missing"


def adapter_kwargs(adapter: str, version: str | None = None) -> dict:
    """Pin BleakScanner / BleakClient to one adapter on any bleak version.

    bleak >= 3.0 takes ``bluez={"adapter": ...}``; older bleak ignores that key and
    silently falls back to the default adapter (hci0 = Victron on the Pi 4), so it
    gets the old ``adapter=`` keyword instead.
    """
    version = bleak_version() if version is None else version
    try:
        major = int(version.split(".")[0])
    except ValueError:
        major = 3
    return {"bluez": {"adapter": adapter}} if major >= BLEAK_BLUEZ_ADAPTER_MAJOR else {"adapter": adapter}




async def _dbus_call_get(props, interface: str, prop: str):
    try:
        return await asyncio.wait_for(
            props.call_get(interface, prop),
            timeout=DBus_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        print(f"DBUS_TIMEOUT {interface}.{prop}", flush=True)
        raise

def _short(address: str) -> str:
    return address[-5:].replace(":", "")


def _json_dict(text: str) -> dict:
    try:
        value = json.loads(text)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _failed_recently(info: dict, now_wall: float) -> bool:
    """Link report says the last try failed, within FAIL_DEMOTE_S by its own last_fail time."""
    if info.get("state") in (None, "", "ok", "no_key"):
        return False
    try:
        failed_at = datetime.fromisoformat(str(info.get("last_fail"))).timestamp()
    except (TypeError, ValueError):
        return True
    return now_wall - failed_at < FAIL_DEMOTE_S


def _new_report() -> dict:
    return {"state": None, "connected": False, "busy": False, "fails": 0,
            "last_ok": None, "last_fail": None, "error": ""}


def _link_state(exc: BaseException, connect_timed_out: bool) -> str:
    """Link report state for a failed try (docs/plug_MULTI_BRIDGE.md table)."""
    if connect_timed_out:
        return "connect_timeout"
    if isinstance(exc, LookupError):
        return "not_heard"
    if isinstance(exc, TimeoutError):
        return "no_ack"
    return "error"


def _log_task_error(what: str):
    """Done-callback for futures/tasks: log exceptions instead of dropping them."""

    def _done(fut) -> None:
        if fut.cancelled():
            return
        exc = fut.exception()
        if exc is not None:
            print(f"TASK_ERROR {what} {type(exc).__name__}: {exc}", flush=True)

    return _done


def unwrap(value):
    if isinstance(value, Variant):
        return unwrap(value.value)
    return value


def mfr_last(mfr) -> int | None:
    mfr = unwrap(mfr)
    if not isinstance(mfr, dict):
        return None
    for raw in mfr.values():
        data = unwrap(raw)
        if isinstance(data, (bytes, bytearray)) and data:
            return data[-1]
        if isinstance(data, list) and data:
            return int(data[-1])
    return None


class PlugLink:
    """One persistent GATT link per plug: resolve once, connect, log in once, reuse.

    Connection attempts on the shared adapter are serialized by ``adapter_lock``;
    writes on an established link are not, so plugs do not wait on each other.
    """

    def __init__(self, address: str, adapter: str, token: str, adapter_lock: asyncio.Lock) -> None:
        self.address = address
        self.adapter = adapter
        self._token = token
        self._adapter_lock = adapter_lock
        self.device = None  # cached BLEDevice from BleakScanner.find_device_by_address
        self.client = None
        self.authed = False
        self.connects = 0
        self.connect_timed_out = False
        self.on_change = None  # called with no args when the link goes up or down
        self._ready_auth = asyncio.Event()
        self._ready_set = asyncio.Event()

    @property
    def connected(self) -> bool:
        client = self.client
        return client is not None and bool(client.is_connected) and self.authed

    def _changed(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def _on_disconnect(self, client) -> None:
        if client is self.client:
            self.client = None
            self.authed = False
            print(f"LINK_DROP {_short(self.address)}", flush=True)
            self._changed()

    def _on_notify(self, _char, data: bytearray) -> None:
        if len(data) < 2 or data[0] != 0x33:
            return
        if data[1] == 0xB2:
            self._ready_auth.set()
        elif data[1] == 0x01:
            self._ready_set.set()

    async def _resolve(self):
        if self.device is None:
            device = await _bleak_scanner_cls().find_device_by_address(
                self.address, timeout=FIND_TIMEOUT_S, **adapter_kwargs(self.adapter)
            )
            if device is None:
                raise LookupError(f"{self.address} not seen on {self.adapter} in {FIND_TIMEOUT_S}s")
            self.device = device
        return self.device

    async def ensure(self) -> None:
        """Connect and log in unless the link is already up."""
        if self.connected:
            return
        await self.close()
        self.connect_timed_out = False
        async with self._adapter_lock:
            device = await self._resolve()
            client = _bleak_client_cls()(
                device,
                disconnected_callback=self._on_disconnect,
                timeout=CONNECT_TIMEOUT_S,
                **adapter_kwargs(self.adapter),
            )
            try:
                await client.connect()
            except BaseException as exc:
                # Stale BlueZ object or plug moved: look it up again next attempt.
                self.connect_timed_out = isinstance(exc, (TimeoutError, asyncio.TimeoutError))
                self.device = None
                await _quiet_disconnect(client)
                raise
        self.connects += 1
        try:
            self._ready_auth.clear()
            await client.start_notify(RECV_UUID, self._on_notify)
            await client.write_gatt_char(SEND_UUID, auth_packet(self._token))
            await asyncio.wait_for(self._ready_auth.wait(), timeout=ACK_TIMEOUT_S)
        except BaseException:
            await _quiet_disconnect(client)
            raise
        self.client = client
        self.authed = True
        print(f"LINK_UP {_short(self.address)}", flush=True)
        self._changed()

    async def send(self, side: str, turn_on: bool) -> None:
        await self.ensure()
        client = self.client
        if client is None:  # dropped between login and write
            raise ConnectionError(f"{self.address} link dropped before write")
        self._ready_set.clear()
        await client.write_gatt_char(SEND_UUID, command_bytes(side, turn_on))
        await asyncio.wait_for(self._ready_set.wait(), timeout=ACK_TIMEOUT_S)

    async def close(self) -> None:
        client, self.client, self.authed = self.client, None, False
        if client is not None:
            await _quiet_disconnect(client)
            self._changed()


async def _quiet_disconnect(client) -> None:
    try:
        if client.is_connected:
            await client.disconnect()
    except Exception as exc:
        print(f"DISCONNECT_ERR {type(exc).__name__}: {exc}", flush=True)


class Bridge:
    def __init__(self) -> None:
        self._adapter = os.environ.get("plug_ADAPTER", "hci1")
        self._listener = os.environ.get("plug_LISTENER", "solar-broker")
        self._rssi_only = os.environ.get("plug_RSSI_ONLY", "") == "1"
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", self._listener):
            raise SystemExit(f"plug_LISTENER {self._listener!r}: use a short host id such as solar-broker or monitor")
        if self._listener == "solar-broker" and self._adapter != "hci1":
            raise SystemExit("solar-broker listener uses hci1 only (hci0 is Victron)")
        if not re.fullmatch(r"hci[0-9]+", self._adapter):
            raise SystemExit(f"plug_ADAPTER {self._adapter!r}: expected hciN")
        # Plug ownership. Unset = legacy single bridge (every plug, legacy availability
        # topic), allowed only on the Pi 4 so a second Pi can never grab every plug.
        try:
            owned = parse_owned(os.environ.get("plug_PLUGS"))
        except ValueError as exc:
            raise SystemExit(f"plug_PLUGS: {exc}") from None
        # Shared: drive every plug we have a key for; radios agree per command who acts.
        self._shared = os.environ.get("plug_SHARED", "") == "1" and not self._rssi_only
        if self._shared and owned is not None:
            raise SystemExit("plug_SHARED=1 drives every plug with a key; remove plug_PLUGS")
        if self._shared and self._listener not in LISTENERS:
            raise SystemExit(f"plug_SHARED=1: listener {self._listener!r} is not one of {', '.join(LISTENERS)}")
        self._per_host = owned is not None or self._shared
        if not self._per_host and not self._rssi_only and self._listener != "solar-broker":
            raise SystemExit(
                f"plug_PLUGS is required on {self._listener} (for example plug_PLUGS=plug-4 "
                "in /home/operator/.config/plug-bridge.env); see docs/plug_MULTI_BRIDGE.md"
            )
        host = os.environ.get("MQTT_HOST", "")
        user = os.environ.get("MQTT_USER") or os.environ.get("MQTT_USERNAME", "")
        password = os.environ.get("MQTT_PASSWORD", "")
        port = int(os.environ.get("MQTT_PORT", "1883"))
        if not host or not user or not password:
            raise SystemExit("MQTT_HOST, MQTT_USER, and MQTT_PASSWORD are required")
        self._keys = load_keys()
        if self._shared:
            owned = {address for address, _name in PLUGS if address in self._keys}
        self._owned: set[str] = {address for address, _name in PLUGS} if owned is None else owned
        self._avail = avail_topic(self._listener if self._per_host else None)
        # Shared-mode view of the other radios, fed from the broker (paho thread).
        self._online: dict[str, bool] = {self._listener: True}
        self._signal_seen: dict[tuple[str, str], int] = {}
        self._own_rssi: dict[str, list[tuple[float, int]]] = {}
        self._own_step: dict[str, int | None] = {}
        self._ad_seen: dict[str, int] = {}
        self._links_seen: dict[tuple[str, str], dict] = {}
        self._report_sent: set[str] = set()
        self._mqtt_ready_at: float | None = None
        self._results: dict[tuple[str, str], list[tuple[float, str, bool, bool]]] = {}
        self._turns: dict[tuple[str, str], asyncio.Task] = {}
        self._last_in_line: dict[tuple[str, str], bool] = {}
        self._report: dict[str, dict] = {}
        self._busy: set[str] = set()
        self._key_problem = key_file_problem(key_path()) if not self._rssi_only else None
        self._state: dict[tuple[str, str], bool] = {}
        self._hold: dict[tuple[str, str], float] = {}
        self._paths: dict[str, str] = {}
        # Latest requested state per socket; a newer command replaces an older one.
        self._desired: dict[tuple[str, str], bool] = {}
        self._workers: dict[str, asyncio.Task] = {}
        self._wake: dict[str, asyncio.Event] = {}
        self._links: dict[str, PlugLink] = {}
        self._adapter_lock = asyncio.Lock()
        self._connect_timeouts = 0
        self._last_reset = float("-inf")
        self._watch_bus = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.username_pw_set(user, password)
        if not self._rssi_only:
            self._client.will_set(self._avail, "offline", qos=1, retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._host = host
        self._port = port

    def publish_state(self, address: str, side: str, on: bool) -> None:
        self._state[(address, side)] = on
        if not self._client.is_connected():
            return
        self._client.publish(state_topic(address, side), payload_for(on), qos=1, retain=True)

    def publish_rssi(self, address: str, rssi: int) -> None:
        if self._shared:
            self.note_own_signal(address, rssi)
        if not self._client.is_connected():
            return
        self._client.publish(rssi_topic(address, self._listener), str(rssi), retain=False)

    def note_own_signal(self, address: str, rssi: int | None = None) -> None:
        """Shared: publish our retained RSSI step for a plug when it changes (ranking input)."""
        now = time.monotonic()
        samples = self._own_rssi.setdefault(address, [])
        if rssi is not None:
            samples.append((now, rssi))
        while samples and samples[0][0] < now - RSSI_WINDOW_S:
            samples.pop(0)
        step = int((sum(r for _t, r in samples) / len(samples)) // RSSI_STEP_DB) if samples else None
        if address in self._own_step and self._own_step[address] == step:
            return
        if not self._client.is_connected():
            return
        self._own_step[address] = step
        payload = "" if step is None else str(step)
        self._client.publish(signal_topic(address, self._listener), payload, qos=1, retain=True)

    def owns(self, address: str) -> bool:
        # Legacy (no allowlist): everything, exactly as before (unknown -> NO_KEY).
        return not self._per_host or address.upper() in self._owned

    def owned_plugs(self) -> list[tuple[str, str]]:
        return [(address, name) for address, name in PLUGS if address in self._owned]

    def describe(self) -> str:
        ids = " ".join(_short(address) for address, _name in self.owned_plugs()) or "none"
        if self._shared:
            mode = "shared"
        else:
            mode = "per-host" if self._per_host else "all (no plug_PLUGS)"
        return f"OWNS {ids} listener={self._listener} adapter={self._adapter} mode={mode}"

    def publish_config(self) -> None:
        if not self._rssi_only:
            self._client.publish(self._avail, "online", qos=1, retain=True)
        count = 0
        for address, name in PLUGS:
            self._client.publish(
                rssi_discovery_topic(address, self._listener),
                dumps(rssi_discovery_payload(address, name, self._listener)),
                retain=True,
            )
            count += 1
        if self._shared:
            self._publish_shared_config()
        elif not self._rssi_only:
            # Only the owner publishes a plug's switch config, so each socket keeps one
            # HA entity whose availability follows the Pi that actually drives it.
            for address, name, side, side_name in iter_switches(self.owned_plugs()):
                payload = discovery_payload(address, name, side, side_name, self._avail)
                self._client.publish(discovery_topic(address, side), dumps(payload), qos=1, retain=True)
                cached = self._state.get((address, side))
                if cached is not None:
                    self.publish_state(address, side, cached)
            self._client.subscribe("govee/plugs/+/+/set", qos=1)
            if self._per_host:
                for address, _name in self.owned_plugs():
                    self._client.publish(owner_topic(address), self._listener, qos=1, retain=True)
                self._client.subscribe("govee/plugs/+/owner", qos=1)
        print(f"DISCOVERY {count} listener={self._listener}", flush=True)

    def _publish_shared_config(self) -> None:
        """Same switch config from every shared radio; own link sensors; subscriptions."""
        avail = [avail_topic(name) for name in LISTENERS]
        # No cached state here: after a reconnect ours may be older than the retained one.
        for address, name, side, side_name in iter_switches(PLUGS):
            payload = discovery_payload(address, name, side, side_name, availability_topics=avail)
            self._client.publish(discovery_topic(address, side), dumps(payload), qos=1, retain=True)
        self._own_step.clear()
        self._mqtt_ready_at = time.monotonic()
        for address, name in PLUGS:
            self._client.publish(
                link_discovery_topic(address, self._listener),
                dumps(link_discovery_payload(address, name, self._listener)),
                qos=1,
                retain=True,
            )
            if address not in self._owned:
                self.report_link(address, state="no_key")
            elif address in self._report:
                self.report_link(address)
        for topic in (
            "govee/plugs/+/+/set",
            "govee/plugs/+/owner",
            "govee/plugs/bridge/+/status",
            "govee/plugs/+/signal/+",
            "govee/plugs/+/link/+",
            "govee/plugs/+/+/result",
            "govee/plugs/+/+/state",
        ):
            self._client.subscribe(topic, qos=1)

    def report_link(self, address: str, state: str | None = None, error: str = "") -> None:
        """Publish this radio's retained link report for one plug (HA enum sensor)."""
        report = self._report.setdefault(address, _new_report())
        link = self._links.get(address)
        report["connected"] = bool(link is not None and link.connected)
        report["busy"] = address in self._busy
        if state is not None:
            stamp = datetime.now().astimezone().isoformat(timespec="seconds")
            report["state"] = state
            if state == "ok":
                report["fails"] = 0
                report["last_ok"] = stamp
                report["error"] = ""
            elif state != "no_key":
                report["fails"] += 1
                report["last_fail"] = stamp
                report["error"] = error[:120]
        if not self._client.is_connected():
            return
        # Before the first result the state is null, which HA shows as unknown
        # (https://www.home-assistant.io/integrations/sensor.mqtt/ state_topic); busy and
        # connected must still reach the other radios.
        flagged = report["busy"] or report["connected"] or address in self._report_sent
        if report["state"] is None and not flagged:
            return
        self._report_sent.add(address)
        self._client.publish(link_topic(address, self._listener), dumps(report), qos=1, retain=True)

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties) -> None:
        if getattr(reason_code, "is_failure", False):
            print(f"MQTT_FAIL {reason_code}", flush=True)
            return
        print("MQTT_OK", flush=True)
        self.publish_config()

    def note_owner_claim(self, mac: str, host: str) -> None:
        """Another bridge's retained claim: warn on a clash, drop our own stale claim."""
        if len(mac) != MAC_HEX_LEN or not host:
            return
        address = ":".join(mac[i : i + 2] for i in range(0, MAC_HEX_LEN, 2)).upper()
        if self._shared:
            if host == self._listener:
                self._client.publish(owner_topic(address), "", qos=1, retain=True)
                print(f"OWNER_RELEASE {_short(address)}", flush=True)
            else:
                print(f"OWNER_MIXED {_short(address)} claimed by {host} (still per-host)", flush=True)
            return
        if self.owns(address) and host != self._listener:
            print(
                f"OWNER_CONFLICT {_short(address)} also claimed by {host}; remove it from "
                f"plug_PLUGS on one Pi",
                flush=True,
            )
        elif not self.owns(address) and host == self._listener:
            # We owned it before a restart with a new allowlist: release the claim.
            self._client.publish(owner_topic(address), "", qos=1, retain=True)
            print(f"OWNER_RELEASE {_short(address)}", flush=True)

    def _on_message(self, _client, _userdata, message) -> None:
        parts = message.topic.split("/")
        if len(parts) == OWNER_TOPIC_PARTS and parts[3] == "owner":
            self.note_owner_claim(parts[2], message.payload.decode("utf-8", "replace").strip())
            return
        if len(parts) != 5:
            return
        if self._shared and self._note_shared(parts, message.payload):
            return
        if parts[4] != "set":
            return
        mac = parts[2]
        side = parts[3]
        if side not in ("left", "right") or len(mac) != MAC_HEX_LEN:
            return
        address = ":".join(mac[i : i + 2] for i in range(0, 12, 2)).upper()
        if not self._shared and not self.owns(address):
            # Another Pi's bridge owns this plug; never touch it from here.
            print(f"NOT_OWNER {_short(address)} {side}", flush=True)
            return
        text = message.payload.decode("utf-8", "replace").strip().upper()
        if text not in ("ON", "OFF"):
            print(f"BAD_PAYLOAD {_short(address)} {side} {text[:16]!r}", flush=True)
            return
        loop = self._loop
        if loop is None:
            print(f"NOT_READY {_short(address)} {side}", flush=True)
            return
        if self._shared:
            coro = self.shared_command(address, side, text == "ON", time.monotonic())
        else:
            coro = self.command(address, side, text == "ON")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        future.add_done_callback(_log_task_error(f"command {_short(address)} {side}"))

    def _note_shared(self, parts: list[str], raw: bytes) -> bool:
        """Record another radio's status / RSSI / link / result / state. True = handled."""
        text = raw.decode("utf-8", "replace").strip()
        now = time.monotonic()
        if parts[2] == "bridge":
            if parts[4] == "status":
                self._online[parts[3]] = text == "online" or parts[3] == self._listener
            return True
        mac = parts[2]
        if len(mac) != MAC_HEX_LEN:
            return True
        address = ":".join(mac[i : i + 2] for i in range(0, MAC_HEX_LEN, 2)).upper()
        if parts[3] == "signal":
            try:
                self._signal_seen[(address, parts[4])] = int(text)
            except ValueError:
                self._signal_seen.pop((address, parts[4]), None)
            return True
        if parts[3] == "link":
            info = _json_dict(text)
            self._links_seen[(address, parts[4])] = info
            seeded = info.get("state") not in (None, "", "no_key")
            if parts[4] == self._listener and info.get("state") == "no_key" and address in self._owned:
                # We have its key now: clear the old retained no_key report.
                self._client.publish(link_topic(address, self._listener), "", qos=1, retain=True)
            elif parts[4] == self._listener and address not in self._report and (
                seeded or info.get("busy") or info.get("connected")
            ):
                # Our own report from before a restart: keep its history, drop stale flags.
                self._report_sent.add(address)
                report = _new_report()
                for name in ("state", "last_ok", "last_fail", "error"):
                    if info.get(name) is not None:
                        report[name] = str(info[name])
                try:
                    report["fails"] = int(info.get("fails") or 0)
                except (TypeError, ValueError):
                    report["fails"] = 0
                self._report[address] = report
                self.report_link(address)
            return True
        side = parts[3]
        if side not in ("left", "right"):
            return False
        if parts[4] == "result":
            info = _json_dict(text)
            want = str(info.get("want", "")).upper()
            if want not in ("ON", "OFF") or not info.get("listener"):
                return True
            ok = bool(info.get("ok"))
            entries = self._results.setdefault((address, side), [])
            entries.append((now, str(info["listener"]), want == "ON", ok))
            del entries[:-20]
            if ok:
                self._hold[(address, side)] = now + HOLD_S
                self._state[(address, side)] = want == "ON"
            return True
        if parts[4] == "state":
            if text in ("ON", "OFF"):
                self._state[(address, side)] = text == "ON"
            return True
        return False

    def rank_listeners(self, address: str) -> list[str]:
        """Shared mode: radios in the order they should try this plug (see docs).

        Only retained broker data is used (link reports, signal steps, wall-clock
        last_fail), so a bridge that just restarted ranks the same as the others.
        """
        now_wall = time.time()
        ranked = []
        for order, name in enumerate(LISTENERS):
            if name == self._listener:
                if address not in self._owned:
                    continue
            elif not self._online.get(name):
                continue
            info = self._links_seen.get((address, name), {})
            if info.get("state") == "no_key" and name != self._listener:
                continue
            holding = 0 if info.get("connected") or info.get("busy") else 1
            failing = 1 if _failed_recently(info, now_wall) else 0
            step = self._signal_seen.get((address, name))
            signal = UNHEARD if step is None else -step
            ranked.append(((holding, failing, signal, order), name))
        return [name for _key, name in sorted(ranked)]

    def _done_elsewhere(self, address: str, side: str, turn_on: bool, since: float) -> bool:
        return any(
            ok and want == turn_on and name != self._listener and t >= since
            for t, name, want, ok in self._results.get((address, side), [])
        )

    async def shared_command(
        self, address: str, side: str, turn_on: bool, received: float | None = None
    ) -> None:
        """Act now if this radio is first in line, else wait for the ones ahead."""
        key = (address, side)
        tag = f"{_short(address)} {side} {payload_for(turn_on)}"
        start = time.monotonic() if received is None else received
        old = self._turns.pop(key, None)
        if old is not None and not old.done():
            old.cancel()
        order = self.rank_listeners(address)
        if self._listener not in order:
            print(f"NOT_IN_LINE {tag} line={','.join(order) or 'none'}", flush=True)
            return
        place = order.index(self._listener)
        self._last_in_line[key] = place == len(order) - 1
        print(f"LINE {tag} {','.join(order)}", flush=True)
        if place == 0:
            await self.command(address, side, turn_on)
            return
        task = asyncio.create_task(self._wait_turn(address, side, turn_on, order[:place], start))
        task.add_done_callback(_log_task_error(f"turn {_short(address)} {side}"))
        self._turns[key] = task

    async def _wait_turn(
        self, address: str, side: str, turn_on: bool, ahead: list[str], start: float
    ) -> None:
        key = (address, side)
        tag = f"{_short(address)} {side} {payload_for(turn_on)}"
        deadline = start + FAILOVER_WAIT_S * len(ahead)
        cap = start + FAILOVER_WAIT_S * (len(ahead) + 2)  # a report stuck on busy
        try:
            while True:
                recent = [r for r in self._results.get(key, []) if r[0] >= start and r[2] == turn_on]
                if any(ok for _t, _name, _want, ok in recent):
                    return
                done = {name for _t, name, _want, ok in recent if not ok}
                done |= {name for name in ahead if not self._online.get(name)}
                if set(ahead) <= done:
                    print(f"FAILOVER {tag} after {','.join(ahead)}", flush=True)
                    break
                now = time.monotonic()
                if any(self._links_seen.get((address, name), {}).get("busy") for name in ahead):
                    deadline = min(max(deadline, now + FAILOVER_WAIT_S), cap)  # still working
                if now >= deadline:
                    print(f"FAILOVER_TIMEOUT {tag} after {','.join(ahead)}", flush=True)
                    break
                await asyncio.sleep(FAILOVER_POLL_S)
        finally:
            if self._turns.get(key) is asyncio.current_task():
                self._turns.pop(key, None)
        await self.command(address, side, turn_on)

    async def command(self, address: str, side: str, turn_on: bool) -> None:
        if not self.owns(address):
            print(f"NOT_OWNER {_short(address)} {side}", flush=True)
            return
        token = self._keys.get(address)
        if not token:
            print(f"NO_KEY {_short(address)} {side}", flush=True)
            current = self._state.get((address, side))
            if current is not None:
                self.publish_state(address, side, current)
            return
        self._desired[(address, side)] = turn_on
        self._wake.setdefault(address, asyncio.Event()).set()
        worker = self._workers.get(address)
        if worker is None or worker.done():
            task = asyncio.create_task(self._plug_worker(address, token))
            task.add_done_callback(_log_task_error(f"worker {_short(address)}"))
            self._workers[address] = task

    def _link(self, address: str, token: str) -> PlugLink:
        link = self._links.get(address)
        if link is None:
            link = PlugLink(address, self._adapter, token, self._adapter_lock)
            if self._shared:
                link.on_change = lambda: self.report_link(address)
            self._links[address] = link
        return link

    async def _plug_worker(self, address: str, token: str) -> None:
        """Apply the latest desired state for each socket of one plug, then linger."""
        link = self._link(address, token)
        wake = self._wake.setdefault(address, asyncio.Event())
        try:
            while True:
                wake.clear()
                pending = [
                    (side, self._desired.pop((address, side)))
                    for side in ("left", "right")
                    if (address, side) in self._desired
                ]
                if pending:
                    for side, want in pending:
                        await self._apply(link, address, side, want)
                    continue
                if not link.connected:
                    return
                if IDLE_DISCONNECT_S <= 0:
                    await wake.wait()
                    continue
                try:
                    await asyncio.wait_for(wake.wait(), timeout=IDLE_DISCONNECT_S)
                except asyncio.TimeoutError:
                    if any(key[0] == address for key in self._desired):
                        continue
                    await link.close()
                    print(f"LINK_IDLE {_short(address)}", flush=True)
                    if any(key[0] == address for key in self._desired):
                        continue  # a command arrived while closing
                    return
        finally:
            if self._workers.get(address) is asyncio.current_task():
                self._workers.pop(address, None)

    async def reset_adapter(self) -> bool:
        """Power the adapter off and on through BlueZ (Adapter1.Powered).

        https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst
        """
        path = f"/org/bluez/{self._adapter}"
        async with self._adapter_lock:
            for link in self._links.values():
                await link.close()
                link.device = None
            bus = None
            try:
                bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
                intro = await bus.introspect("org.bluez", path)
                props = bus.get_proxy_object("org.bluez", path, intro).get_interface(
                    "org.freedesktop.DBus.Properties"
                )
                await props.call_set("org.bluez.Adapter1", "Powered", Variant("b", False))
                await asyncio.sleep(ADAPTER_POWER_OFF_S)
                await props.call_set("org.bluez.Adapter1", "Powered", Variant("b", True))
                await asyncio.sleep(ADAPTER_POWER_ON_S)
            except Exception as exc:
                print(f"ADAPTER_RESET_FAIL {self._adapter} {type(exc).__name__}: {exc}", flush=True)
                return False
            finally:
                if bus is not None:
                    bus.disconnect()
        if self._watch_bus is not None:
            await self.start_discovery(self._watch_bus)
        return True

    async def _note_connect_timeout(self) -> bool:
        """Count a connect timeout; reset the adapter when they keep coming."""
        self._connect_timeouts += 1
        if ADAPTER_RESET_AFTER <= 0 or self._connect_timeouts < ADAPTER_RESET_AFTER:
            return False
        now = time.monotonic()
        if now - self._last_reset < ADAPTER_RESET_GAP_S:
            return False
        count = self._connect_timeouts
        self._last_reset = now
        self._connect_timeouts = 0
        if not await self.reset_adapter():
            return False
        print(f"ADAPTER_RESET {self._adapter} after {count} connect timeouts", flush=True)
        return True

    async def _apply(self, link: PlugLink, address: str, side: str, turn_on: bool) -> bool:
        if not self._shared:
            ok, _state, _error = await self._attempt(link, address, side, turn_on)
            return ok
        self._busy.add(address)
        self.report_link(address)
        try:
            ok, state, error = await self._attempt(link, address, side, turn_on)
        finally:
            self._busy.discard(address)
        if state is not None:
            self.report_link(address, state=state, error=error)
            if self._client.is_connected():
                result = {"listener": self._listener, "want": payload_for(turn_on), "ok": ok}
                self._client.publish(result_topic(address, side), dumps(result), qos=1)
        else:
            self.report_link(address)
        return ok

    async def _attempt(
        self, link: PlugLink, address: str, side: str, turn_on: bool
    ) -> tuple[bool, str | None, str]:
        """Send one command with retries. Returns (ok, link state or None if superseded, error)."""
        tag = f"{_short(address)} {side}"
        attempts = RETRIES
        attempt = 0
        state, error = "error", ""
        started = time.monotonic()
        while attempt < attempts:
            attempt += 1
            if attempt > 1 and (address, side) in self._desired:
                print(f"SUPERSEDED {tag} {payload_for(turn_on)}", flush=True)
                return False, None, ""
            if attempt > 1 and self._shared and self._done_elsewhere(address, side, turn_on, started):
                print(f"DONE_ELSEWHERE {tag} {payload_for(turn_on)}", flush=True)
                return False, None, ""
            try:
                await link.send(side, turn_on)
            except Exception as exc:
                print(
                    f"GATT {tag} {payload_for(turn_on)} try {attempt}/{attempts} "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                timed_out = link.connect_timed_out
                state, error = _link_state(exc, timed_out), f"{type(exc).__name__}: {exc}"
                await link.close()
                if timed_out and await self._note_connect_timeout():
                    if attempts == RETRIES:
                        attempts += 1  # one more try on the freshly reset adapter
                    continue
                if attempt < attempts:
                    await asyncio.sleep(RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S)) - 1])
                continue
            self._connect_timeouts = 0
            self._hold[(address, side)] = time.monotonic() + HOLD_S
            self.publish_state(address, side, turn_on)
            extra = f" try {attempt}" if attempt > 1 else ""
            print(f"SET {tag} {payload_for(turn_on)}{extra}", flush=True)
            return True, "ok", ""
        if (address, side) in self._desired:
            print(f"SUPERSEDED {tag} {payload_for(turn_on)}", flush=True)
            return False, None, ""
        if self._shared and self._done_elsewhere(address, side, turn_on, started):
            print(f"DONE_ELSEWHERE {tag} {payload_for(turn_on)}", flush=True)
            return False, None, ""
        if self._shared and not self._last_in_line.get((address, side), True):
            # The next radio in line takes over; it puts HA back if it also fails.
            print(f"SET_FAIL {tag} {payload_for(turn_on)} handing off", flush=True)
            return False, state, error
        current = self._state.get((address, side))
        if current is not None:
            self.publish_state(address, side, current)
        print(f"SET_FAIL {tag} {payload_for(turn_on)}", flush=True)
        return False, state, error

    def note_advertisement(self, address: str, last: int) -> None:
        address = address.upper()
        if not self.owns(address):
            return  # the owning Pi publishes this plug's state
        if self._shared:
            # BlueZ keeps the last advertisement while another radio holds the link, so
            # only a changed value is news. A first sighting is that stale cache too
            # when some radio holds the link now. Judge it only once the retained
            # link reports and state have arrived after connecting to the broker.
            previous = self._ad_seen.get(address)
            if previous == last:
                return
            if previous is None:
                ready = self._mqtt_ready_at
                if ready is None or time.monotonic() - ready < RETAINED_SETTLE_S:
                    return
                held = any(
                    info.get("connected") or info.get("busy")
                    for (plug, name), info in list(self._links_seen.items())
                    if plug == address and (name == self._listener or self._online.get(name))
                )
                if held:
                    self._ad_seen[address] = last
                    return
            self._ad_seen[address] = last
        now = time.monotonic()
        for side, on in socket_on(last).items():
            if self._hold.get((address, side), 0) > now:
                continue
            if self._state.get((address, side)) is on and (address, side) in self._state:
                continue
            self.publish_state(address, side, on)
            print(f"STATE {address[-5:].replace(':', '')} {side} {payload_for(on)}", flush=True)

    async def discover(self, bus) -> None:
        """(Re)map plug addresses to their BlueZ object paths on ADAPTER.

        Run at start and every RESCAN_EVERY polls: a plug that was out of range
        (not yet in BlueZ) at start, or whose object BlueZ removed and re-created
        (bluetoothd restart, cache expiry), was otherwise never watched again.
        """
        intro = await bus.introspect("org.bluez", "/")
        root = bus.get_proxy_object("org.bluez", "/", intro)
        objects = await root.get_interface("org.freedesktop.DBus.ObjectManager").call_get_managed_objects()
        wanted = {item[0] for item in PLUGS}
        paths: dict[str, str] = {}
        for path, ifaces in objects.items():
            if not str(path).startswith(f"/org/bluez/{self._adapter}/dev_"):
                continue
            dev = ifaces.get("org.bluez.Device1")
            if not dev:
                continue
            address = str(unwrap(dev.get("Address") or "")).upper()
            if address not in wanted:
                continue
            paths[address] = str(path)
            rssi = unwrap(dev.get("RSSI"))
            if isinstance(rssi, int):
                self.publish_rssi(address, rssi)
            last = mfr_last(dev.get("ManufacturerData"))
            if last is not None and not self._rssi_only:
                self.note_advertisement(address, last)
        self._paths = paths

    async def start_discovery(self, bus) -> None:
        """BlueZ Adapter1.StartDiscovery so RSSI exists without another scanner.

        https://github.com/bluez/bluez/blob/master/doc/org.bluez.Adapter.rst
        """
        path = f"/org/bluez/{self._adapter}"
        intro = await bus.introspect("org.bluez", path)
        adapter = bus.get_proxy_object("org.bluez", path, intro)
        try:
            await adapter.get_interface("org.bluez.Adapter1").call_start_discovery()
            print(f"SCAN {self._adapter}", flush=True)
        except Exception as exc:
            print(f"SCAN {self._adapter} {type(exc).__name__}", flush=True)

    async def watch(self) -> None:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self._watch_bus = bus
        await self.start_discovery(bus)
        await self.discover(bus)
        polls = 0
        while True:
            polls += 1
            if polls % RESCAN_EVERY == 0:
                try:
                    await self.discover(bus)
                except Exception as exc:
                    print(f"DISCOVER {type(exc).__name__}", flush=True)
            for address, path in list(self._paths.items()):
                try:
                    node = await bus.introspect("org.bluez", path)
                    proxy = bus.get_proxy_object("org.bluez", path, node)
                    props = proxy.get_interface("org.freedesktop.DBus.Properties")
                    try:
                        rssi = unwrap(await _dbus_call_get(props, "org.bluez.Device1", "RSSI"))
                    except Exception:
                        rssi = None
                    if isinstance(rssi, int):
                        self.publish_rssi(address, rssi)
                    if self._rssi_only:
                        continue
                    raw = await _dbus_call_get(props, "org.bluez.Device1", "ManufacturerData")
                except asyncio.TimeoutError:
                    print(f"DBUS_SKIP {_short(address)} poll", flush=True)
                    continue
                except Exception:
                    continue
                last = mfr_last(raw)
                if last is not None:
                    self.note_advertisement(address, last)
            if self._shared:
                for address, _name in PLUGS:
                    self.note_own_signal(address)
            await asyncio.sleep(10)

    def startup_report(self) -> None:
        print(f"{self.describe()} bleak={bleak_version()}", flush=True)
        if self._rssi_only:
            return
        if self._key_problem:
            print(f"KEY_FILE {key_path()} {self._key_problem}", flush=True)
        if self._shared:
            missing = [_short(address) for address, _name in PLUGS if address not in self._owned]
            if missing:
                print(f"NO_KEY {' '.join(missing)} (other radios drive these)", flush=True)
            return
        for address, _name in self.owned_plugs():
            if address not in self._keys:
                print(f"NO_KEY_OWNED {_short(address)} (copy its line into {key_path()})", flush=True)

    async def run(self) -> None:
        self.startup_report()
        self._loop = asyncio.get_running_loop()
        self._client.connect(self._host, self._port)
        self._client.loop_start()
        try:
            await self.watch()
        finally:
            for task in list(self._workers.values()) + list(self._turns.values()):
                task.cancel()
            for link in list(self._links.values()):
                await link.close()
            if not self._rssi_only:
                self._client.publish(self._avail, "offline", qos=1, retain=True)
            self._client.loop_stop()
            self._client.disconnect()


def main() -> None:
    asyncio.run(Bridge().run())


if __name__ == "__main__":
    main()
