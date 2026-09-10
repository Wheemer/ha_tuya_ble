"""Read saved BLE credentials. This manager has no network client."""

from __future__ import annotations
from .tuya_ble import AbstaractTuyaBLEDeviceManager, TuyaBLEDeviceCredentials
from .schema import parse_schema
from .const import (
    CONF_UUID,
    CONF_LOCAL_KEY,
    CONF_LOCAL_KEY_HEX,
    CONF_SEC_KEY,
    CONF_CATEGORY,
    CONF_PRODUCT_ID,
    CONF_DEVICE_NAME,
    CONF_PRODUCT_NAME,
    CONF_PRODUCT_MODEL,
    CONF_FUNCTIONS,
    CONF_STATUS_RANGE,
)
from homeassistant.const import CONF_DEVICE_ID

# Remove only account configuration; BLE credentials and settings are retained.
CLOUD_ACCOUNT_KEYS = frozenset(
    {
        "username",
        "password",
        "country_code",
        "access_id",
        "access_secret",
        "endpoint",
        "auth_type",
        "tuya_project_type",
        "tuya_app_type",
        "mobile_app",
        "token",
        "access_token",
        "refresh_token",
    }
)


def local_options(options):
    """Copy settings without obsolete account credentials."""
    return {
        key: value for key, value in options.items() if key not in CLOUD_ACCOUNT_KEYS
    }


class LocalTuyaBLEDeviceManager(AbstaractTuyaBLEDeviceManager):
    """Supply existing or locally generated credentials, without lookup."""

    def __init__(self, hass, data):
        self._data = local_options(data)

    @property
    def data(self):
        return self._data

    async def get_device_credentials(
        self, address, force_update=False, save_data=False
    ):
        data = self._data
        if not data.get(CONF_LOCAL_KEY) and not data.get(CONF_LOCAL_KEY_HEX):
            return None
        if not all(
            data.get(key) for key in (CONF_UUID, CONF_DEVICE_ID, CONF_PRODUCT_ID)
        ):
            return None
        functions = data.get(CONF_FUNCTIONS)
        statuses = data.get(CONF_STATUS_RANGE)
        if data.get("schema"):
            functions, statuses = parse_schema(data["schema"])
        return TuyaBLEDeviceCredentials(
            uuid=data[CONF_UUID],
            local_key=data.get(CONF_LOCAL_KEY, ""),
            device_id=data[CONF_DEVICE_ID],
            category=data.get(CONF_CATEGORY, ""),
            product_id=data[CONF_PRODUCT_ID],
            device_name=data.get(CONF_DEVICE_NAME),
            product_model=data.get(CONF_PRODUCT_MODEL),
            product_name=data.get(CONF_PRODUCT_NAME),
            functions=functions,
            status_range=statuses,
            sec_key=data.get(CONF_SEC_KEY),
            local_key_hex=data.get(CONF_LOCAL_KEY_HEX),
        )
