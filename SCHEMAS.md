# Local product schemas

Local Tuya BLE can interpret the native schema-array format used by Smart Life's `ProductBean.SchemaInfo`. Definitions are stored in the integration's configuration options. There is no vendor client, login, download or schema command sent to a device by this feature.

After adding a device, choose **Configure → Device definition**. Paste the array for that exact product. Invalid input leaves the previous configuration intact. Saving an options change follows the integration's normal reload behavior; it does not pair or reset the device.

This example illustrates the format only; it is not a verified product definition:

```json
[
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
      "unit": "°C"
    }
  }
]
```

The reading `234` becomes `23.4 °C`. Names come from the definition, with a readable version of the code as fallback. Generic entity identity uses the device ID and datapoint ID rather than the displayed name.

| Schema type | Read-only (`ro`) | Writable (`rw` or `wr`) |
| --- | --- | --- |
| `bool` | Binary sensor | Switch |
| `value` | Sensor | Number using the declared bounds and step |
| `enum` | Sensor displaying the declared enum label | Select encoding the label's index |
| `string` | Sensor | Text control |
| `raw`, `bitmap` | Sensor displaying bytes as hex | No generic opaque-payload control; a readable `rw` value can still be shown |

`rw` permits both reports and commands; `wr` permits commands only. Missing or unknown access modes are rejected. Datapoint IDs and codes must be unique. Integer scaling, ranges and steps are validated; enum choices must be unique. Unknown and compound types are rejected rather than assigned invented behavior. Long raw/string reports that exceed Home Assistant's state limit are not displayed as a truncated measurement.

The fallback runs only when the device has no applicable specialized mapping. Existing product and category mappings, including compound light, lock and vacuum controls, retain precedence. This avoids creating duplicate controls or changing existing entity IDs. Imported schemas can supply metadata consumed by those existing platforms, but the fallback does not fill gaps in their mappings yet.

Schema entities are declared without requiring a live datapoint report, so an offline device does not lose these entities at setup. Existing credentials and connection settings are retained when a schema is saved. Legacy read-only status definitions are also loaded independently of writable functions.

## What remains

- Automatic acquisition of product definitions has not been implemented. A valid definition must already be available locally.
- Smart Life's separate CommRod schema synchronization path has been identified, but it is not implemented here and has not been verified against ordinary Tuya BLE sensors.
- Schemas describe datapoints; they do not by themselves implement authentication, another BLE transport, proprietary raw commands, or compound device behavior.
- Tests cover schema validation, access permissions, command encoding, offline entities, Home Assistant state updates and preservation of existing mappings. They are not hardware verification for every product using this format.
