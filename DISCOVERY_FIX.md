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
