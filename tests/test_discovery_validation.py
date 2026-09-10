"""Validate advertisements before offering Tuya BLE discovery flows."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.tuya_ble.config_flow import (
    TuyaBLEConfigFlow,
    _has_tuya_service_data,
)
from custom_components.tuya_ble.tuya_ble import SERVICE_UUIDS


def advertisement(service_data=None, name="TY"):
    return SimpleNamespace(
        address="AA:BB:CC:DD:EE:01",
        name=name,
        service_data=service_data,
        service_uuids=list(SERVICE_UUIDS),
        manufacturer_data={},
    )


@pytest.mark.parametrize(
    "service_data",
    [
        None,
        {},
        {SERVICE_UUIDS[0]: b""},
        {SERVICE_UUIDS[0]: b"\x00"},
        {"unrelated": b"\x00payload"},
    ],
)
async def test_reject_before_cloud_or_unique_id(service_data):
    flow = TuyaBLEConfigFlow()
    flow.async_set_unique_id = AsyncMock()
    flow.async_abort = Mock(return_value={"type": "abort", "reason": "not_supported"})
    with patch(
        "custom_components.tuya_ble.config_flow.HASSTuyaBLEDeviceManager"
    ) as manager:
        result = await flow.async_step_bluetooth(advertisement(service_data))
    assert result["reason"] == "not_supported"
    flow.async_set_unique_id.assert_not_awaited()
    manager.assert_not_called()
    assert flow._discovery_info is None


async def test_captured_dryer_advertisement_is_rejected():
    # Captured on multiple receivers, 2026-09-10. Address anonymized.
    dryer = advertisement({}, "Dryer")
    dryer.service_uuids = []
    dryer.manufacturer_data = {0x0075: bytes.fromhex("421f3001010f00f0f10100")}
    flow = TuyaBLEConfigFlow()
    flow.async_abort = Mock(return_value={"type": "abort", "reason": "not_supported"})
    with patch(
        "custom_components.tuya_ble.config_flow.HASSTuyaBLEDeviceManager"
    ) as manager:
        assert (await flow.async_step_bluetooth(dryer))["reason"] == "not_supported"
    manager.assert_not_called()


@pytest.mark.parametrize("uuid", SERVICE_UUIDS)
@pytest.mark.parametrize(
    "payload",
    [
        bytes.fromhex("000102030405060708"),
        bytes.fromhex("010102030405060708090a0b0c0d0e0f10"),
    ],
)
async def test_supported_encrypted_advertisements_still_reach_setup(uuid, payload):
    # Synthetic payloads preserving the formats and lengths in the live capture.
    discovery = advertisement({uuid: payload}, name=None)
    flow = TuyaBLEConfigFlow()
    flow.context = {}
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()
    flow._manager = SimpleNamespace(build_cache=AsyncMock())
    flow.async_step_user = AsyncMock(return_value={"type": "menu"})
    with patch(
        "custom_components.tuya_ble.config_flow.get_device_readable_name",
        AsyncMock(return_value="Tuya device"),
    ):
        assert await flow.async_step_bluetooth(discovery) == {"type": "menu"}
    flow._manager.build_cache.assert_awaited_once()
    assert flow._discovery_info is discovery


def test_manual_discovery_uses_same_filter_and_keeps_duplicate_checks():
    valid = advertisement({SERVICE_UUIDS[1]: b"\x01encrypted"})
    invalid = advertisement({SERVICE_UUIDS[0]: b""}, "Dryer")
    invalid.address = "AA:BB:CC:DD:EE:02"
    flow = TuyaBLEConfigFlow()
    flow.hass = Mock()
    flow._async_current_ids = Mock(return_value=set())
    with patch(
        "custom_components.tuya_ble.config_flow.async_discovered_service_info",
        return_value=[invalid, valid, valid],
    ):
        flow._collect_discovered_devices()
    assert flow._discovered_devices == {valid.address: valid}
    flow._discovered_devices.clear()
    flow._async_current_ids.return_value = {valid.address}
    with patch(
        "custom_components.tuya_ble.config_flow.async_discovered_service_info",
        return_value=[valid],
    ):
        flow._collect_discovered_devices()
    assert flow._discovered_devices == {}


def test_invalid_first_uuid_does_not_mask_valid_second_uuid():
    assert _has_tuya_service_data(
        advertisement({SERVICE_UUIDS[0]: b"", SERVICE_UUIDS[1]: b"\x00payload"})
    )
