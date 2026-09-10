"""Discovery remains broad and local, preceding the pairing-mode prompt."""

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
        device=SimpleNamespace(name=name),
        service_data=service_data,
        service_uuids=list(SERVICE_UUIDS),
        manufacturer_data={},
    )


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {SERVICE_UUIDS[0]: b""},
        {SERVICE_UUIDS[0]: b"\0"},
        {"unrelated": b"data"},
    ],
)
async def test_invalid_advertisement_rejected_before_flow_identity(data):
    flow = TuyaBLEConfigFlow()
    flow.async_set_unique_id = AsyncMock()
    flow.async_abort = Mock(return_value={"reason": "not_supported"})
    assert (await flow.async_step_bluetooth(advertisement(data)))[
        "reason"
    ] == "not_supported"
    flow.async_set_unique_id.assert_not_awaited()


@pytest.mark.parametrize("uuid", SERVICE_UUIDS)
@pytest.mark.parametrize("payload", [b"\0newmodel", b"\1opaque-model-data"])
async def test_unknown_models_discover_before_pairing_mode(uuid, payload):
    flow = TuyaBLEConfigFlow()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = Mock()
    flow.context = {}
    flow.async_show_form = Mock(return_value={"type": "form"})
    with patch(
        "custom_components.tuya_ble.config_flow.pair_local", new_callable=AsyncMock
    ) as pair:
        assert (await flow.async_step_bluetooth(advertisement({uuid: payload})))[
            "type"
        ] == "form"
        pair.assert_not_awaited()
    assert flow.async_show_form.call_args.kwargs["step_id"] == "local_pair"


def test_dryer_and_uuid_only_are_rejected():
    dryer = advertisement({}, "Dryer")
    dryer.manufacturer_data = {0x75: bytes.fromhex("421f3001010f00f0f10100")}
    assert not _has_tuya_service_data(dryer)
    assert not _has_tuya_service_data(advertisement())
    assert _has_tuya_service_data(
        advertisement({SERVICE_UUIDS[0]: b"", SERVICE_UUIDS[1]: b"\1data"})
    )


def test_manual_discovery_filters_and_keeps_existing_entries():
    good = advertisement({SERVICE_UUIDS[0]: b"\0future"})
    bad = advertisement({}, "Dryer")
    bad.address = "other"
    flow = TuyaBLEConfigFlow()
    flow.hass = Mock()
    flow._async_current_ids = Mock(return_value=set())
    with patch(
        "custom_components.tuya_ble.config_flow.async_discovered_service_info",
        return_value=[bad, good, good],
    ):
        flow._collect_discovered_devices()
    assert list(flow._discovered_devices) == [good.address]
    flow._discovered_devices.clear()
    flow._async_current_ids.return_value = {good.address}
    with patch(
        "custom_components.tuya_ble.config_flow.async_discovered_service_info",
        return_value=[good],
    ):
        flow._collect_discovered_devices()
    assert not flow._discovered_devices
