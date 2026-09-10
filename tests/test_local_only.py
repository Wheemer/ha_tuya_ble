"""No vendor clients, account steps, or account data in the local-only fork."""

import ast
import json
from pathlib import Path
from unittest.mock import Mock
from custom_components.tuya_ble.config_flow import TuyaBLEConfigFlow, TuyaBLEOptionsFlow
from custom_components.tuya_ble.config_flow import _validate_manual


def test_no_cloud_dependencies_or_imports():
    root = Path(__file__).parents[1] / "custom_components/tuya_ble"
    manifest = json.loads((root / "manifest.json").read_text())
    assert "tuya" not in manifest["dependencies"]
    assert not any(
        "tuya" in requirement or "pycountry" in requirement
        for requirement in manifest["requirements"]
    )
    assert not (root / "cloud.py").exists() and not (root / "mobile.py").exists()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in ("tuya_iot", "tuya_mobile", "pycountry")


async def test_no_account_steps():
    flow = TuyaBLEConfigFlow()
    flow.async_show_menu = Mock()
    await flow.async_step_user()
    assert flow.async_show_menu.call_args.kwargs["menu_options"] == [
        "local_device",
        "manual",
    ]
    for cls in (TuyaBLEConfigFlow, TuyaBLEOptionsFlow):
        assert not hasattr(cls, "async_step_login") and not hasattr(
            cls, "async_step_mobile_app"
        )


def test_import_binary_saved_key():
    data = {
        "uuid": "testidentity0001",
        "local_key_hex": "00ff80123456",
        "device_id": "v" * 22,
        "product_id": "gvygg3m8",
        "category": "zwjcy",
    }
    errors = {}
    assert _validate_manual(data, errors)["local_key_hex"] == "00ff80123456"
    assert not errors
    assert _validate_manual({**data, "local_key": "anotherkey"}, errors) is None
