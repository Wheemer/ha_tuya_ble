# Discovery validation

The Bluetooth config flow previously trusted its incoming discovery callback and
opened setup without checking for Tuya service data. The manual discovery list
checked only whether a supported service-data key existed, including empty data.

The flow now requires more than the format byte in the service data for either
supported UUID, matching the existing advertisement parser's minimum length.
Rejected advertisements abort before a unique ID is assigned or cloud credentials
are consulted. Both supported UUIDs and opaque/encrypted payloads remain eligible.
No manufacturer, name, product allowlist, or ownership restriction was added.

## Evidence and limits

A Home Assistant diagnostic capture on 2026-09-10 showed a device named Dryer
advertising manufacturer 0x0075 with no Tuya service data across multiple local
and ESPHome receivers. The same device had an ignored Tuya BLE config entry.
Its manufacturer payload is replayed in the regression test with an anonymized
address. A connected plant sensor and an unidentified TY advertiser supplied the
two positive payload shapes used in the tests.

This demonstrates a missing defensive check, but does not reconstruct the
historical callback that produced the ignored entry. It does not prove the cause
of all ignored discoveries. In particular, an unknown device carrying Tuya data
is not established to be a false detection and remains eligible.

Existing config entries, entity registries, manual credential setup, and the
connection/reconnection path are unchanged. This patch does not delete existing
ignored or pending discoveries.

## Smart Life reference check

Local inspection of Smart Life Android 7.11.3 (build 860) found its single-BLE
scanner forwards advertisements only after a protocol parser returns a device.
That parser requires manufacturer data and dispatches several manufacturer IDs;
the captured Dryer's ID 117 is not accepted. Its manufacturer-2000 A201 branch
handles service payload shapes matching the two observed Tuya advertisements,
including format bytes 0 and 1. This is static analysis, not a replay of the app.

The relevant recovered classes are `com.thingclips.sdk.ble.core.scan.BleSingleScanner`
and `com.thingclips.sdk.bluetooth.bqpdppq`. JADX reported errors in the
overall decompilation; the reference is not a complete recovered source tree.
No proprietary APK or decompiled source is included in this repository.

This supports validating advertisement contents before presenting setup. It does
not establish that a manufacturer-2000-only rule or the A201 parser's exact lengths
would preserve all devices supported through the integration's FD50 path. The
patch therefore retains its narrower service-data requirement.
