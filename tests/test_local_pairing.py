"""Local provisioning protocol, credential recovery and config flow tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import hashlib
import struct

from Crypto.Cipher import AES
import pytest

from custom_components.tuya_ble import local_pairing as lp
from custom_components.tuya_ble.config_flow import TuyaBLEConfigFlow
from custom_components.tuya_ble.diagnostics import TO_REDACT
from custom_components.tuya_ble.tuya_ble.security import TuyaBLESecurityMaterial
from custom_components.tuya_ble.local_manager import LocalTuyaBLEDeviceManager

IDENTITY = {
    "uuid": "testidentity0001",
    "bound": False,
    "protocol_major": 3,
    "product_id": "gvygg3m8",
}
ADDRESS = "AA:BB:CC:DD:EE:FF"


def test_identity_without_product_allowlist():
    product = b"newmodel"
    key = hashlib.md5(product).digest()
    manufacturer = {
        2000: b"\0\x03\0\0\0\0"
        + AES.new(key, AES.MODE_CBC, key).encrypt(IDENTITY["uuid"].encode())
    }
    identity = lp.decode_identity(
        manufacturer, {"0000a201-0000-1000-8000-00805f9b34fb": b"\0" + product}
    )
    assert identity["product_id"] == "newmodel"
    assert identity["bound"] is False
    assert lp.decode_identity({}, {}) is None


def test_protocol_and_binary_runtime_key():
    assert lp.crc16(b"123456789") == 0x4B37
    material = TuyaBLESecurityMaterial("", local_key_hex="00ff80123456")
    assert material.pairing_login_key == bytes.fromhex("00ff80123456")
    assert material.login_key == hashlib.md5(material.pairing_login_key).digest()
    assert "00ff80123456" not in repr(material)
    assert "local_key_hex" in TO_REDACT
    receiver = lp.Receiver()
    data = b"testidentity0001" + material.pairing_login_key + b"v" * 22
    for packet in lp.packets(2, 1, data):
        assert len(packet) <= 20
        receiver.feed(None, packet)
    raw = receiver.frames[0][1:]
    assert struct.unpack(">IIHH", raw[:12]) == (2, 0, 1, 44)
    assert raw[12:56] == data
    encrypted = lp.Receiver()
    for packet in lp.packets(1, 0, key=material.login_key):
        encrypted.feed(None, packet)
    assert lp.decode_frame(encrypted.frames[0], material.login_key)["command"] == 0
    assert lp.decode_frame(encrypted.frames[0], bytes(16)) is None
    broken = bytearray(encrypted.frames[0])
    broken[-1] ^= 1
    assert lp.decode_frame(bytes(broken), material.login_key) is None
    for malformed in (b"", b"\x80", b"\0\x80", b"\0\x01"):
        receiver.feed(None, malformed)


@pytest.mark.asyncio
async def test_credentials_saved_before_bind_and_reused():
    store = SimpleNamespace(
        async_load=AsyncMock(return_value=None), async_save=AsyncMock()
    )
    saved = await lp.prepare_credentials(store, ADDRESS, IDENTITY)
    store.async_save.assert_awaited_once_with(saved)
    assert (
        saved["attempted"] is False and len(bytes.fromhex(saved["local_key_hex"])) == 6
    )
    store.async_load.return_value = saved
    assert (
        await lp.prepare_credentials(store, ADDRESS, {**IDENTITY, "bound": True})
        == saved
    )
    store.async_load.return_value = None
    with pytest.raises(lp.LocalPairingError, match="already_bound"):
        await lp.prepare_credentials(store, ADDRESS, {**IDENTITY, "bound": True})


@pytest.mark.asyncio
async def test_prompt_does_not_pair_or_require_pairing_mode():
    flow = TuyaBLEConfigFlow()
    flow.hass = Mock()
    flow._discovery_info = SimpleNamespace(address=ADDRESS)
    flow.async_show_form = Mock(return_value={"type": "form"})
    with patch(
        "custom_components.tuya_ble.config_flow.pair_local", new_callable=AsyncMock
    ) as pairing:
        await flow.async_step_local_device()
        pairing.assert_not_awaited()
    assert flow.async_show_form.call_args.kwargs["step_id"] == "local_pair"


@pytest.mark.asyncio
async def test_success_creates_existing_runtime_credentials_without_cloud():
    flow = TuyaBLEConfigFlow()
    flow.hass = Mock()
    flow._pending_address = ADDRESS
    flow.async_create_entry = Mock(return_value={"type": "create_entry"})
    saved = {**IDENTITY, "device_id": "v" * 22, "local_key_hex": "00ff80123456"}
    with patch(
        "custom_components.tuya_ble.config_flow.pair_local",
        AsyncMock(return_value=saved),
    ):
        await flow.async_step_local_pair({})
    options = flow.async_create_entry.call_args.kwargs["options"]
    assert options["category"] and options["local_key_hex"] == saved["local_key_hex"]
    manager = LocalTuyaBLEDeviceManager(Mock(), options)
    manager.login = AsyncMock(side_effect=AssertionError("cloud access"))
    credentials = await manager.get_device_credentials(ADDRESS)
    assert credentials.local_key_hex == saved["local_key_hex"]
    manager.login.assert_not_awaited()


@pytest.mark.asyncio
async def test_pairing_error_offers_retry_without_creating_entry():
    flow = TuyaBLEConfigFlow()
    flow.hass = Mock()
    flow._pending_address = ADDRESS
    flow.async_show_form = Mock()
    flow.async_show_menu = Mock()
    flow.async_create_entry = Mock()
    with patch(
        "custom_components.tuya_ble.config_flow.pair_local",
        AsyncMock(side_effect=lp.LocalPairingError("local_verification_failed")),
    ):
        await flow.async_step_local_pair({})
    flow.async_create_entry.assert_not_called()
    assert flow.async_show_menu.call_args.kwargs["menu_options"] == [
        "retry_pair",
        "cancel",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("attempted", [False, True])
async def test_pair_local_verifies_reconnect_and_never_repeats_uncertain_bind(
    attempted,
):
    saved = {
        **IDENTITY,
        "address": ADDRESS,
        "local_key_hex": "00ff80123456",
        "device_id": "v" * 22,
        "attempted": attempted,
    }
    store = SimpleNamespace(
        async_load=AsyncMock(return_value=saved), async_save=AsyncMock()
    )
    commands = []
    opened = []
    closed = []

    class Client:
        def __init__(self, *args, **kwargs):
            self.receiver = lp.Receiver()

        async def __aenter__(self):
            opened.append(self)
            return self

        async def __aexit__(self, *args):
            closed.append(self)

        async def start_notify(self, uuid, callback):
            self.callback = callback

        async def write_gatt_char(self, uuid, data, response):
            self.receiver.feed(None, data)
            if not self.receiver.frames:
                return
            envelope = self.receiver.frames.pop()
            if envelope[0] == 0:
                raw = envelope[1:]
                command = int.from_bytes(raw[8:10], "big")
                if command == 1:
                    assert saved["attempted"] and store.async_save.await_count > 0
                commands.append(command)
            else:
                commands.append("verify")
                key = TuyaBLESecurityMaterial(
                    "", local_key_hex=saved["local_key_hex"]
                ).login_key
                # Construct an independent device reply, including bound=1.
                payload = bytes([9, 3, 3, 1, 0, 1]) + b"random" + b"\x01\x00"
                raw = struct.pack(">IIHH", 10, 1, 0, len(payload)) + payload
                raw += struct.pack(">H", lp.crc16(raw))
                raw += b"\0" * (-len(raw) % 16)
                iv = bytes(range(16))
                envelope = b"\x04" + iv + AES.new(key, AES.MODE_CBC, iv).encrypt(raw)
                self.callback(None, b"\0" + bytes([len(envelope), 0x30]) + envelope)

    async def no_wait(*args):
        pass

    with (
        patch.object(lp, "Store", return_value=store),
        patch.object(lp, "discover_identity", AsyncMock(return_value=IDENTITY)),
        patch.object(
            lp.bluetooth, "async_ble_device_from_address", return_value=object()
        ),
        patch.object(lp, "BleakClient", Client),
        patch.object(lp.asyncio, "sleep", no_wait),
    ):
        result = await lp.pair_local(SimpleNamespace(data={}), ADDRESS)
    assert result["verified"] is True
    assert commands == (["verify"] if attempted else [0, 1, "verify"])
    assert opened == closed


async def test_identity_waits_for_delayed_scan_response():
    import asyncio

    callbacks = []
    remove = Mock()
    product = b"gvygg3m8"
    key = hashlib.md5(product).digest()
    info = SimpleNamespace(
        address=ADDRESS,
        service_data={"0000a201-0000-1000-8000-00805f9b34fb": b"\0" + product},
        manufacturer_data={},
    )

    def register(*args):
        callbacks.append(args[1])
        return remove

    async def sweep(*args):
        callbacks[0](info, None)

        # Deliver the scan response after the sweep itself has returned.
        def response():
            info.manufacturer_data = {
                2000: b"\0\x03\0\0\0\0"
                + AES.new(key, AES.MODE_CBC, key).encrypt(IDENTITY["uuid"].encode())
            }
            callbacks[0](info, None)

        asyncio.get_running_loop().call_later(0.01, response)

    with (
        patch.object(lp.bluetooth, "async_register_callback", side_effect=register),
        patch.object(lp.bluetooth, "async_request_active_scan", side_effect=sweep),
    ):
        assert await lp.discover_identity(Mock(), ADDRESS) == IDENTITY
    remove.assert_called_once()


async def test_retry_screen_requires_explicit_retry_before_pairing():
    flow = TuyaBLEConfigFlow()
    flow.async_show_menu = Mock()
    with patch.object(flow, "async_step_local_pair", new_callable=AsyncMock) as pair:
        await flow.async_step_local_retry()
        pair.assert_not_awaited()
        await flow.async_step_retry_pair()
        pair.assert_awaited_once_with({})
