<div align="center">

# Local Tuya BLE

### Local pairing and control of Tuya Bluetooth devices in Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-CUSTOM-FD7E14?style=for-the-badge&logo=home-assistant&logoColor=white&labelColor=555555)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/HOME%20ASSISTANT-2026.8%2B-41BDF5?style=for-the-badge&logo=home-assistant&logoColor=white&labelColor=555555)](https://www.home-assistant.io/)
[![Latest release](https://img.shields.io/github/v/release/Wheemer/local-tuya-ble?style=for-the-badge&logo=github&logoColor=white&label=RELEASE&labelColor=555555&color=22C55E)](https://github.com/Wheemer/local-tuya-ble/releases/latest)
[![License](https://img.shields.io/badge/LICENSE-MIT-64748B?style=for-the-badge&labelColor=555555)](LICENSE)

[Install](#install) | [Configure](#configure) | [Migration](#migration-from-tuya-ble) | [Devices](DEVICES.md) | [Troubleshooting](#troubleshooting) | [Contributing](#contributing)

</div>

Local Tuya BLE is a Home Assistant custom integration for Tuya Bluetooth Low Energy devices running their original firmware. It provides local discovery, experimental local pairing, and encrypted Bluetooth communication without a Tuya account or cloud connection.

This project builds on [ha-tuya-ble/ha_tuya_ble](https://github.com/ha-tuya-ble/ha_tuya_ble), preserving its device mappings while adding local setup, credential migration, and validated discovery.

## What It Does

- Validates Tuya Bluetooth advertisements to avoid treating unrelated Bluetooth devices as Tuya devices.
- Uses available product information for readable discovery names.
- Discovers advertising devices before pairing mode and keeps unknown Tuya models discoverable.
- Pairs supported protocol-3 BLE devices locally and verifies the generated key on a fresh connection.
- Imports existing saved credentials without an account login.
- Migrates existing Tuya BLE entries while preserving entity IDs, device settings, and unavailable sensors.
- Uses Home Assistant Bluetooth adapters and connectable Bluetooth proxies.

## Local-Only Boundary

Setup and device communication do not use Tuya cloud login, Smart Life login, account refresh, or the official Tuya integration. There is no cloud fallback for unsupported pairing protocols. No firmware flashing or DNS changes are required for the supported BLE pairing path.

This integration is for **Tuya BLE devices**. Wi-Fi switches that advertise over Bluetooth for Wi-Fi setup are not supported by the local pairing feature. Bluetooth Mesh devices require a different protocol. Downloading the integration and its dependencies still requires obtaining those files.

## Install

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Wheemer&repository=local-tuya-ble&category=integration)

If the button does not work:

1. Open HACS and choose **Custom repositories** from its menu.
2. Add `https://github.com/Wheemer/local-tuya-ble` as an **Integration** repository.
3. Install **Local Tuya BLE**.
4. Restart Home Assistant to load the integration.
5. Open **Settings > Devices & services** and select a discovered device, or choose **Add integration > Local Tuya BLE**.

For a manual install, copy `custom_components/tuya_ble` into Home Assistant's `/config/custom_components/` directory and restart Home Assistant. Restart after updating integration files as well.

## Configure

### Pair a device locally

1. Wait for the device to appear under **Discovered**. It must be advertising and within range of Home Assistant or a connectable Bluetooth proxy.
2. Click **Add**. Manual setup also offers **Pair locally**.
3. When prompted, put the device into pairing mode, close any app connected to it, and submit the form.
4. The integration obtains its identity, saves generated credentials, pairs it, and checks those credentials on a new connection.
5. Supported product mappings create its entities.

Discovery does not require pairing mode first. Some battery devices need to be woken before they advertise. If pairing mode expires, enable it again and use the retry option.

### Import existing credentials

Choose **Import existing credentials** when you already have the device identity and keys from a trusted backup. Some protocol variants require both `localKey` and `secKey`. Importing credentials does not contact an app or cloud service.

### Local Pairing Support

Local binding and encrypted reconnection have been verified on a stock **SGS01 soil sensor**, product ID `gvygg3m8`, protocol 3.1, after removal from Smart Life. The implementation supports the classic protocol-3 exchange without a model-specific allowlist, but this is not a claim that every protocol-3 device has been tested.

Other pairing protocols are rejected with an explanation. Unknown models remain discoverable and may need entity mappings even if pairing succeeds. Never-registered factory-new devices, power-cycle recovery, and sustained measurements across every supported mapping still need broader hardware validation.

See [Supported Devices](DEVICES.md) for inherited entity mappings and experimental models. Device mappings and local-pairing compatibility are separate.

## Migration From Tuya BLE

Back up Home Assistant before replacing the integration. This fork intentionally keeps the internal domain and folder name **`tuya_ble`** so existing configuration entries and entities can be migrated in place.

1. Keep your existing Tuya BLE entries in **Devices & services**; do not delete them.
2. Replace the previous HACS repository with this repository, or replace the integration files manually. Only one integration can occupy `custom_components/tuya_ble`.
3. Restart Home Assistant.
4. Check the existing devices and entities. Migration retains saved BLE credentials, identity, metadata, connection settings, and entity IDs while removing obsolete account-login fields.

Unavailable sensors are preserved. They do not need to be online for their configuration to remain intact. Migration does not reset devices. Removing a device from Smart Life is a separate vendor action that may reset its pairing; it is not part of migration.

## Troubleshooting

- **Nothing discovered:** wake the device and check Bluetooth range and proxy connectivity. A Wi-Fi-only or Bluetooth Mesh device is not a supported BLE device.
- **Pairing timed out:** put the device back into pairing mode, close connected apps, and retry. Check that the proxy has an available connection slot.
- **Unsupported pairing protocol:** use existing credentials if available. This release does not have a cloud fallback.
- **Device paired but entities are missing:** its product may need a mapping. Include the model and product ID in an issue.
- **Interrupted pairing:** retry using the saved pending credentials. Do not delete pending pairing storage or generate replacement keys manually.

Keep Home Assistant backups private: they contain the credentials needed to reconnect. Remove keys, account details, and Wi-Fi passwords from anything posted publicly.

## Contributing

Report discovery problems and request device support in [Issues](https://github.com/Wheemer/local-tuya-ble/issues). Include the model, product ID, Home Assistant version, integration version, and relevant sanitized logs. Please distinguish discovery, pairing, and entity-mapping problems.

New devices are welcome. Follow [AGENTS.md](AGENTS.md) for code conventions, translations, and relevant tests. Unsupported models should not be hidden just because a mapping has not been written yet.

## Credits

Based on the work of [ha-tuya-ble](https://github.com/ha-tuya-ble/ha_tuya_ble), [PlusPlus-ua](https://github.com/PlusPlus-ua/ha_tuya_ble), [markusg1234](https://github.com/markusg1234/ha_tuya_ble), [redphx](https://github.com/redphx/poc-tuya-ble-fingerbot), and the community contributors. Original copyright and the [MIT license](LICENSE) are retained.

You can also [support the original developer, PlusPlus-ua](https://www.buymeacoffee.com/3PaK6lXr4l).
