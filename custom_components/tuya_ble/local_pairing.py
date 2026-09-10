"""Local protocol-3 provisioning; no Tuya account or cloud requests."""

from __future__ import annotations
import asyncio
import hashlib
import os
import secrets
import struct
from Crypto.Cipher import AES
from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.helpers.storage import Store
from .tuya_ble.security import TuyaBLESecurityMaterial

NOTIFY = "00002b10-0000-1000-8000-00805f9b34fb"
WRITE = "00002b11-0000-1000-8000-00805f9b34fb"


def decode_identity(manufacturer, service):
    payload = manufacturer.get(2000)
    product = service.get("0000a201-0000-1000-8000-00805f9b34fb")
    if payload is None or product is None:
        return None
    if len(payload) != 22 or len(product) < 2 or product[0] != 0:
        return None
    key = hashlib.md5(product[1:]).digest()
    identity = AES.new(key, AES.MODE_CBC, key).decrypt(payload[6:])
    # SDK device IDs are 16 ASCII characters. Keep malformed data from a bind request.
    if len(identity) != 16 or not all(32 <= b < 127 for b in identity):
        return None
    if not all(32 <= b < 127 for b in product[1:]):
        return None
    return {
        "uuid": identity.decode("ascii"),
        "bound": bool(payload[0] & 0x80),
        "protocol_major": payload[1],
        "product_id": product[1:].decode("ascii"),
    }


def crc16(raw):
    crc = 0xFFFF
    for byte in raw:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def variable(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out + bytes([value]))


def packets(sequence, command, data=b"", key=None):
    raw = struct.pack(">IIHH", sequence, 0, command, len(data)) + data
    raw += struct.pack(">H", crc16(raw))
    raw += b"\0" * ((-len(raw)) % 16)
    if key is None:
        envelope = b"\0" + raw
    else:
        iv = os.urandom(16)
        envelope = b"\x04" + iv + AES.new(key, AES.MODE_CBC, iv).encrypt(raw)
    out = []
    pos = 0
    while pos < len(envelope):
        header = variable(len(out))
        if not out:
            header += variable(len(envelope)) + b"\x30"
        chunk = envelope[pos : pos + 20 - len(header)]
        out.append(header + chunk)
        pos += len(chunk)
    return out


class Receiver:
    def __init__(self):
        self.buffer = bytearray()
        self.length = 0
        self.expected = 0
        self.frames = []

    def feed(self, _characteristic, packet):
        if not packet or len(self.frames) >= 64:
            return

        def integer(pos):
            value = 0
            for shift in range(0, 28, 7):
                if pos >= len(packet):
                    raise ValueError("truncated transport header")
                byte = packet[pos]
                pos += 1
                value |= (byte & 127) << shift
                if byte < 128:
                    return value, pos
            raise ValueError("invalid transport header")

        try:
            number, pos = integer(0)
            if number == 0:
                self.length, pos = integer(pos)
                if pos >= len(packet):
                    return
                pos += 1
                self.buffer.clear()
                self.expected = 0
        except (ValueError, IndexError):
            self.length = 0
            return
        if number != self.expected or not 1 <= self.length <= 4096:
            return
        self.expected += 1
        self.buffer.extend(packet[pos:])
        if len(self.buffer) > self.length:
            self.buffer.clear()
            self.length = 0
            return
        if len(self.buffer) == self.length:
            self.frames.append(bytes(self.buffer))
            self.length = 0


def decode_frame(envelope, key):
    if len(envelope) < 33 or envelope[0] != 4 or (len(envelope) - 17) % 16:
        return None
    raw = AES.new(key, AES.MODE_CBC, envelope[1:17]).decrypt(envelope[17:])
    sequence, reply, command, length = struct.unpack(">IIHH", raw[:12])
    end = 12 + length
    if end + 2 > len(raw) or crc16(raw[:end]) != int.from_bytes(
        raw[end : end + 2], "big"
    ):
        return None
    return {"reply": reply, "command": command, "data": raw[12:end]}


class LocalPairingError(Exception):
    """A translated config-flow failure, without credentials in its message."""


async def discover_identity(hass, address):
    """Wait for a complete identity, including delayed proxy scan responses."""
    received = asyncio.get_running_loop().create_future()

    def discovered(info, _change):
        if info.address.upper() != address.upper() or received.done():
            return
        candidate = decode_identity(info.manufacturer_data, info.service_data)
        if candidate:
            received.set_result(candidate)

    unsubscribe = bluetooth.async_register_callback(
        hass, discovered, {"address": address}, bluetooth.BluetoothScanningMode.ACTIVE
    )
    scan_task = None
    try:
        if sweep := getattr(bluetooth, "async_request_active_scan", None):
            scan_task = asyncio.create_task(sweep(hass, 15))
            identity = await asyncio.wait_for(received, 20)
        else:
            info = await bluetooth.async_process_advertisements(
                hass,
                lambda info: decode_identity(info.manufacturer_data, info.service_data)
                is not None,
                {"address": address},
                bluetooth.BluetoothScanningMode.ACTIVE,
                20,
            )
            identity = decode_identity(info.manufacturer_data, info.service_data)
    except TimeoutError as err:
        raise LocalPairingError("local_identity_missing") from err
    finally:
        unsubscribe()
        if scan_task is not None:
            scan_task.cancel()
            await asyncio.gather(scan_task, return_exceptions=True)
    if identity is None:
        raise LocalPairingError("local_identity_missing")
    if identity["protocol_major"] != 3:
        raise LocalPairingError("local_protocol_unsupported")
    return identity


async def prepare_credentials(store, address, identity):
    """Keep the same credential across cancellation, retries and HA restarts."""
    saved = await store.async_load()
    if saved:
        if saved.get("uuid") != identity["uuid"] or saved.get("address") != address:
            raise LocalPairingError("local_identity_mismatch")
        TuyaBLESecurityMaterial("", local_key_hex=saved["local_key_hex"])
        return saved
    if identity["bound"]:
        raise LocalPairingError("local_already_bound")
    saved = {
        "address": address,
        "uuid": identity["uuid"],
        "product_id": identity["product_id"],
        "local_key_hex": secrets.token_hex(6),
        "device_id": secrets.token_hex(11),
        "attempted": False,
    }
    await store.async_save(saved)
    return saved


async def send(client, chunks):
    for chunk in chunks:
        await client.write_gatt_char(WRITE, chunk, response=False)
        await asyncio.sleep(0.05)


async def pair_local(hass, address):
    """Bind only an unbound protocol-3 device; verify on a fresh connection."""
    locks = hass.data.setdefault("tuya_ble_local_pairing_locks", {})
    lock = locks.setdefault(address, asyncio.Lock())
    async with lock, asyncio.timeout(65):
        identity = await discover_identity(hass, address)
        store = Store(
            hass,
            1,
            f"tuya_ble.local_pairing.{address.replace(':', '').lower()}",
            private=True,
        )
        saved = await prepare_credentials(store, address, identity)
        device = bluetooth.async_ble_device_from_address(
            hass, address, connectable=True
        )
        if device is None:
            raise LocalPairingError("local_cannot_connect")
        material = TuyaBLESecurityMaterial("", local_key_hex=saved["local_key_hex"])
        if not identity["bound"] and not saved["attempted"]:
            async with BleakClient(device, timeout=15) as client:
                receiver = Receiver()
                await client.start_notify(NOTIFY, receiver.feed)
                await send(client, packets(1, 0))
                await asyncio.sleep(1)
                data = (
                    saved["uuid"].encode("ascii")
                    + material.pairing_login_key
                    + saved["device_id"].encode("ascii")
                )
                # Save this marker before any binding bytes. An interrupted write
                # must lead to verification, never an automatic replacement key.
                saved["attempted"] = True
                await store.async_save(saved)
                await send(client, packets(2, 1, data))
                await asyncio.sleep(2)
            await asyncio.sleep(1)
        async with BleakClient(device, timeout=15) as client:
            receiver = Receiver()
            await client.start_notify(NOTIFY, receiver.feed)
            await send(client, packets(1, 0, key=material.login_key))
            for _ in range(40):
                for envelope in receiver.frames:
                    response = decode_frame(envelope, material.login_key)
                    if (
                        response
                        and response["command"] == 0
                        and response["reply"] == 1
                        and len(response["data"]) >= 14
                        and response["data"][5] == 1
                    ):
                        saved["verified"] = True
                        await store.async_save(saved)
                        return saved
                await asyncio.sleep(0.1)
        raise LocalPairingError("local_verification_failed")
