"""Schema access, wire encoding, persistence and offline entity behavior."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.const import Platform
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
import logging

from custom_components.tuya_ble.schema import parse_schema
from custom_components.tuya_ble.schema_entities import (
    schema_entities,
    has_specialized_mapping,
)
from custom_components.tuya_ble.local_manager import LocalTuyaBLEDeviceManager
from custom_components.tuya_ble.tuya_ble.tuya_ble import (
    TuyaBLEDevice,
    TuyaBLEDeviceFunction,
)
from custom_components.tuya_ble.tuya_ble import TuyaBLEDataPointType as WireType


SCHEMA = [
    {
        "id": 1,
        "code": "temperature",
        "name": "Temperature",
        "mode": "ro",
        "type": "obj",
        "property": {
            "type": "value",
            "min": -400,
            "max": 1250,
            "step": 1,
            "scale": 1,
            "unit": "°C",
        },
    },
    {
        "id": 2,
        "code": "relay",
        "mode": "rw",
        "type": "obj",
        "property": {"type": "bool"},
    },
    {
        "id": 3,
        "code": "setpoint",
        "mode": "rw",
        "type": "obj",
        "property": {"type": "value", "min": 0, "max": 500, "step": 5, "scale": 1},
    },
    {
        "id": 4,
        "code": "mode",
        "mode": "rw",
        "type": "obj",
        "property": {"type": "enum", "range": ["off", "auto", "manual"]},
    },
    {
        "id": 5,
        "code": "label",
        "mode": "rw",
        "type": "obj",
        "property": {"type": "string", "maxlen": 12},
    },
    {
        "id": 6,
        "code": "open",
        "mode": "ro",
        "type": "obj",
        "property": {"type": "bool"},
    },
]


def test_native_schema_permissions_and_string_properties():
    functions, statuses = parse_schema(json.dumps(SCHEMA))
    assert [d["dp_id"] for d in functions] == [2, 3, 4, 5]
    assert [d["dp_id"] for d in statuses] == [1, 2, 3, 4, 5, 6]
    assert statuses[0]["name"] == "Temperature"
    definition = {**SCHEMA[0], "property": json.dumps(SCHEMA[0]["property"])}
    assert parse_schema([definition]) == ([], [statuses[0]])
    assert parse_schema([{**SCHEMA[1], "mode": "wr"}])[1] == []


@pytest.mark.parametrize(
    "change",
    [
        {"id": True},
        {"id": 256},
        {"mode": None},
        {"mode": "write"},
        {"property": {"type": "array"}},
        {"property": {"type": "enum", "range": ["a", "a"]}},
        {"property": {"type": "value", "min": 0, "max": 10, "step": 0, "scale": 0}},
        {"property": {"type": "string", "maxlen": "20"}},
    ],
)
def test_reject_invalid_schema(change):
    with pytest.raises(ValueError):
        parse_schema([{**SCHEMA[0], **change}])


def test_duplicates_rejected():
    with pytest.raises(ValueError):
        parse_schema([SCHEMA[0], SCHEMA[0]])


def test_read_only_definitions_are_loaded_without_functions():
    device = SimpleNamespace(function={}, status_range={})
    functions, statuses = parse_schema([SCHEMA[0]])
    TuyaBLEDevice.append_functions(device, functions, statuses)
    assert device.function == {}
    assert device.status_range["temperature"].dp_id == 1
    TuyaBLEDevice.append_functions(device, [parse_schema(SCHEMA)[0][0]], None)
    assert device.function["relay"].dp_id == 2


async def test_manager_preserves_credentials_and_reads_schema():
    saved = {
        "uuid": "testidentity0001",
        "device_id": "v" * 22,
        "product_id": "newproduct",
        "local_key_hex": "00ff80123456",
        "schema": SCHEMA,
        "password": "obsolete",
    }
    manager = LocalTuyaBLEDeviceManager(None, saved)
    credentials = await manager.get_device_credentials("AA:BB:CC:DD:EE:FF")
    assert credentials.local_key_hex == "00ff80123456"
    assert credentials.functions[0]["dp_id"] == 2
    assert credentials.status_range[0]["values"]["scale"] == 1
    assert "password" not in manager.data
    assert saved["password"] == "obsolete"


@pytest.fixture
def schema_data(hass):
    functions, statuses = parse_schema(SCHEMA)
    points = {}
    # A real dictionary lookup shape with missing datapoints returning None.
    from unittest.mock import MagicMock

    datapoints = MagicMock()
    datapoints.__getitem__.side_effect = points.get
    datapoints.get_or_create.return_value = SimpleNamespace(set_value=AsyncMock())
    device = SimpleNamespace(
        device_id="test-schema",
        address="AA:BB:CC:DD:EE:FF",
        product_id="newproduct",
        category="unknown_category",
        name="Schema test",
        device_name="Schema test",
        product_model=None,
        product_name=None,
        firmware_version="1.0",
        hardware_version="1.0",
        device_version="1.0",
        protocol_version="3.1",
        function={x["code"]: TuyaBLEDeviceFunction(**x) for x in functions},
        status_range={x["code"]: TuyaBLEDeviceFunction(**x) for x in statuses},
        datapoints=datapoints,
    )
    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name="test", config_entry=None
    )
    coordinator.connected = False
    return SimpleNamespace(
        device=device,
        product=None,
        coordinator=coordinator,
        use_schema_entities=True,
        points=points,
    )


async def test_offline_entities_and_scaled_values(hass, schema_data):
    entities = {
        p: schema_entities(hass, schema_data, p)
        for p in (
            Platform.SENSOR,
            Platform.BINARY_SENSOR,
            Platform.SWITCH,
            Platform.NUMBER,
            Platform.SELECT,
            Platform.TEXT,
        )
    }
    assert all(len(v) == 1 for v in entities.values())
    sensor = entities[Platform.SENSOR][0]
    assert sensor.native_value is None and not sensor.available
    schema_data.points[1] = SimpleNamespace(type=WireType.DT_VALUE, value=-123)
    assert sensor.native_value == -12.3
    assert sensor.name == "Temperature"
    assert sensor.unique_id == "test-schema-schema_dp_1"
    with pytest.raises(ValueError):
        await sensor.write(123)
    schema_data.use_schema_entities = False
    assert schema_entities(hass, schema_data, Platform.SENSOR) == []


async def test_schema_controls_encode_wire_values(hass, schema_data):
    assert not has_specialized_mapping(schema_data.device, None)
    number = schema_entities(hass, schema_data, Platform.NUMBER)[0]
    select = schema_entities(hass, schema_data, Platform.SELECT)[0]
    switch = schema_entities(hass, schema_data, Platform.SWITCH)[0]
    text = schema_entities(hass, schema_data, Platform.TEXT)[0]
    points = schema_data.device.datapoints
    await number.async_set_native_value(12.5)
    points.get_or_create.assert_called_with(3, WireType.DT_VALUE, 125)
    for invalid in (12.3, 50.5, float("nan")):
        with pytest.raises(ValueError):
            await number.async_set_native_value(invalid)
    await select.async_select_option("manual")
    points.get_or_create.assert_called_with(4, WireType.DT_ENUM, 2)
    with pytest.raises(ValueError):
        await select.async_select_option("invalid")
    await switch.async_turn_off()
    points.get_or_create.assert_called_with(2, WireType.DT_BOOL, False)
    schema_data.points[5] = SimpleNamespace(type=WireType.DT_STRING, value="x" * 256)
    assert text.native_value is None
    await text.async_set_value("Garage")
    points.get_or_create.assert_called_with(5, WireType.DT_STRING, "Garage")
    with pytest.raises(ValueError):
        await text.async_set_value("é" * 7)


def test_existing_plant_mappings_take_precedence():
    device = SimpleNamespace(category="zwjcy", product_id="gvygg3m8")
    assert has_specialized_mapping(device, None)


async def test_options_reject_invalid_then_save_valid_schema(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.tuya_ble.config_flow import TuyaBLEConfigFlow

    entry = MockConfigEntry(
        domain="tuya_ble",
        options={
            "local_key_hex": "00ff80123456",
            "schema": SCHEMA,
            "device_id": "unchanged",
            "keep_connection": False,
        },
    )
    entry.add_to_hass(hass)
    flow = TuyaBLEConfigFlow.async_get_options_flow(entry)
    flow.handler = entry.entry_id
    flow.hass = hass
    flow.async_show_form = Mock()
    flow.async_create_entry = Mock()
    await flow.async_step_schema({"schema": "[]"})
    assert flow.async_show_form.call_args.kwargs["errors"] == {
        "schema": "invalid_schema"
    }
    flow.async_create_entry.assert_not_called()
    assert entry.options["schema"] == SCHEMA
    await flow.async_step_schema({"schema": json.dumps([SCHEMA[0]])})
    saved = flow.async_create_entry.call_args.kwargs["data"]
    assert saved == {**entry.options, "schema": [SCHEMA[0]]}


@pytest.mark.parametrize(
    "platform",
    [
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.SWITCH,
        Platform.NUMBER,
        Platform.SELECT,
        Platform.TEXT,
    ],
)
async def test_platform_adds_offline_schema_entity(hass, schema_data, platform):
    from importlib import import_module
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain="tuya_ble")
    hass.data.setdefault("tuya_ble", {})[entry.entry_id] = schema_data
    added = Mock()
    module = import_module(f"custom_components.tuya_ble.{platform}")
    await module.async_setup_entry(hass, entry, added)
    entities = added.call_args.args[0]
    assert any(e.unique_id.startswith("test-schema-schema_dp_") for e in entities)
    assert all(not e.available for e in entities)


async def test_schema_entity_is_registered_in_home_assistant(hass, schema_data):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "sensor", {})
    entity = schema_entities(hass, schema_data, Platform.SENSOR)[0]
    await hass.data["sensor"].async_add_entities([entity])
    state = hass.states.get(entity.entity_id)
    assert state.state == "unavailable"
    schema_data.coordinator.connected = True
    schema_data.points[1] = SimpleNamespace(type=WireType.DT_VALUE, value=234)
    schema_data.coordinator.async_set_updated_data(None)
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state.state == "23.4"
    assert state.attributes["unit_of_measurement"] == "°C"
