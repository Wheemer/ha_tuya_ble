"""Basic entities for schema-described products without a specialized mapping."""

from __future__ import annotations

from decimal import Decimal

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import Platform

from .devices import TuyaBLEEntity
from .tuya_ble import TuyaBLEDataPointType as WireType

WIRE_TYPES = {
    "Boolean": WireType.DT_BOOL,
    "Integer": WireType.DT_VALUE,
    "Enum": WireType.DT_ENUM,
    "String": WireType.DT_STRING,
    "Raw": WireType.DT_RAW,
    "Bitmap": WireType.DT_BITMAP,
}


class SchemaEntity(TuyaBLEEntity):
    """Use schema metadata for identity, access and wire representation."""

    def __init__(self, hass, data, definition, writable):
        self.definition = definition
        self.writable = writable
        self.values = definition.values or {}
        self.factor = 10 ** self.values.get("scale", 0)
        super().__init__(
            hass,
            data.coordinator,
            data.device,
            data.product,
            {
                Platform.SENSOR: SensorEntityDescription,
                Platform.BINARY_SENSOR: BinarySensorEntityDescription,
                Platform.SWITCH: SwitchEntityDescription,
                Platform.NUMBER: NumberEntityDescription,
                Platform.SELECT: SelectEntityDescription,
                Platform.TEXT: TextEntityDescription,
            }[self.platform](key=f"schema_dp_{definition.dp_id}"),
        )
        self._attr_translation_key = None
        self._attr_name = (
            definition.name or definition.code.replace("_", " ").capitalize()
        )

    @property
    def raw_value(self):
        point = self.device.datapoints[self.definition.dp_id]
        if point is None or point.type != WIRE_TYPES[self.definition.type]:
            return None
        return point.value

    async def write(self, value):
        if not self.writable:
            raise ValueError("Datapoint is read-only")
        point = self.device.datapoints.get_or_create(
            self.definition.dp_id, WIRE_TYPES[self.definition.type], value
        )
        await point.set_value(value)


class SchemaSensor(SchemaEntity, SensorEntity):
    platform = Platform.SENSOR

    def __init__(self, *args):
        super().__init__(*args)
        if self.definition.type == "Integer":
            self._attr_native_unit_of_measurement = self.values.get("unit") or None

    @property
    def native_value(self):
        value = self.raw_value
        if value is None:
            return None
        if self.definition.type == "Integer":
            return value / self.factor
        if self.definition.type == "Enum":
            choices = self.values.get("range", [])
            return (
                choices[value]
                if type(value) is int and 0 <= value < len(choices)
                else None
            )
        if isinstance(value, bytes):
            return value.hex() if len(value) <= 127 else None
        return value if not isinstance(value, str) or len(value) <= 255 else None


class SchemaBinarySensor(SchemaEntity, BinarySensorEntity):
    platform = Platform.BINARY_SENSOR

    @property
    def is_on(self):
        return self.raw_value


class SchemaSwitch(SchemaEntity, SwitchEntity):
    platform = Platform.SWITCH

    @property
    def is_on(self):
        return self.raw_value

    async def async_turn_on(self, **kwargs):
        await self.write(True)

    async def async_turn_off(self, **kwargs):
        await self.write(False)


class SchemaNumber(SchemaEntity, NumberEntity):
    platform = Platform.NUMBER

    def __init__(self, *args):
        super().__init__(*args)
        self._attr_native_min_value = self.values["min"] / self.factor
        self._attr_native_max_value = self.values["max"] / self.factor
        self._attr_native_step = self.values["step"] / self.factor
        self._attr_native_unit_of_measurement = self.values.get("unit") or None

    @property
    def native_value(self):
        value = self.raw_value
        return None if value is None else value / self.factor

    async def async_set_native_value(self, value):
        raw = Decimal(str(value)) * self.factor
        if (
            not raw.is_finite()
            or raw != raw.to_integral_value()
            or not self.values["min"] <= raw <= self.values["max"]
            or (raw - self.values["min"]) % self.values["step"]
        ):
            raise ValueError("Value is outside the schema range or step")
        await self.write(int(raw))


class SchemaSelect(SchemaEntity, SelectEntity):
    platform = Platform.SELECT

    def __init__(self, *args):
        super().__init__(*args)
        self._attr_options = self.values["range"]

    @property
    def current_option(self):
        value = self.raw_value
        return (
            self.options[value]
            if type(value) is int and 0 <= value < len(self.options)
            else None
        )

    async def async_select_option(self, option):
        await self.write(self.options.index(option))


class SchemaText(SchemaEntity, TextEntity):
    platform = Platform.TEXT

    def __init__(self, *args):
        super().__init__(*args)
        self._attr_native_max = min(self.values.get("maxlen", 255), 255)

    @property
    def native_value(self):
        value = self.raw_value
        return value if isinstance(value, str) and len(value) <= 255 else None

    async def async_set_value(self, value):
        if not isinstance(value, str) or len(value.encode("utf-8")) > self.native_max:
            raise ValueError("Text exceeds the schema length")
        await self.write(value)


def schema_entities(hass, data, platform):
    """Create declared entities even before the first datapoint report."""
    if not getattr(data, "use_schema_entities", False):
        return []
    definitions = {**data.device.status_range, **data.device.function}
    result = []
    for code, definition in definitions.items():
        writable = code in data.device.function
        cls = {
            "Boolean": SchemaSwitch if writable else SchemaBinarySensor,
            "Integer": SchemaNumber if writable else SchemaSensor,
            "Enum": SchemaSelect if writable else SchemaSensor,
            "String": SchemaText if writable else SchemaSensor,
            "Raw": SchemaSensor,
            "Bitmap": SchemaSensor,
        }.get(definition.type)
        # Opaque writable payloads need a product-specific command encoder.
        if (
            definition.type in ("Raw", "Bitmap")
            and code not in data.device.status_range
        ):
            continue
        if cls is not None and cls.platform == platform:
            result.append(cls(hass, data, definition, writable))
    return result


def has_specialized_mapping(device, product):
    """Keep established product entities and their unique IDs unchanged."""
    from importlib import import_module

    if product and product.lock:
        return True
    for platform in (
        "binary_sensor",
        "button",
        "climate",
        "cover",
        "event",
        "lawn_mower",
        "light",
        "number",
        "select",
        "sensor",
        "switch",
        "text",
        "vacuum",
    ):
        module = import_module(f".{platform}", __package__)
        getter = getattr(module, "get_mapping_by_device", None)
        if getter is None:
            getter = module._get_mapping
        if getter(device):
            return True
    return False
