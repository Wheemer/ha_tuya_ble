"""Interpret locally supplied Smart Life product schemas without network access."""

from __future__ import annotations

import json


def parse_schema(value: str | list) -> tuple[list[dict], list[dict]]:
    """Convert native schema entries to writable functions and reported statuses.

    Smart Life ProductBean.SchemaInfo.buildSchema indexes this same list by ID.
    Access mode is explicit: an absent mode must never imply write permission.
    """
    if isinstance(value, str):
        if len(value) > 262144:
            raise ValueError("Schema is too large")
        value = json.loads(value)
    if not isinstance(value, list) or not value or len(value) > 255:
        raise ValueError("Expected a nonempty list of datapoint definitions")
    functions, statuses = [], []
    ids, codes = set(), set()
    types = {
        "bool": "Boolean",
        "value": "Integer",
        "enum": "Enum",
        "string": "String",
        "bitmap": "Bitmap",
        "raw": "Raw",
    }
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Invalid datapoint definition")
        dp_id = item.get("id")
        if isinstance(dp_id, str) and dp_id.isdecimal():
            dp_id = int(dp_id)
        code = item.get("code")
        mode = item.get("mode")
        if type(dp_id) is not int or not 1 <= dp_id <= 255 or dp_id in ids:
            raise ValueError("Invalid or duplicate datapoint ID")
        if not isinstance(code, str) or not code.strip() or code in codes:
            raise ValueError("Invalid or duplicate datapoint code")
        if mode not in ("ro", "rw", "wr"):
            raise ValueError("Datapoint mode must be ro, rw, or wr")
        prop = item.get("property", {})
        if isinstance(prop, str):
            prop = json.loads(prop)
        if not isinstance(prop, dict):
            raise ValueError("Invalid datapoint property")
        kind = prop.get("type", item.get("type"))
        if kind not in types:
            raise ValueError("Unsupported datapoint type")
        if kind == "value":
            for key in ("min", "max", "step", "scale"):
                if type(prop.get(key)) is not int:
                    raise ValueError("Integer datapoints require min, max, step, scale")
            if not (-(2**31) <= prop["min"] <= prop["max"] < 2**31):
                raise ValueError("Invalid integer range")
            if prop["step"] <= 0 or not 0 <= prop["scale"] <= 9:
                raise ValueError("Invalid integer step or scale")
        if kind == "string" and (
            type(prop.get("maxlen", 255)) is not int
            or not 1 <= prop.get("maxlen", 255) <= 65535
        ):
            raise ValueError("Invalid string length")
        if kind == "enum":
            choices = prop.get("range")
            if (
                not isinstance(choices, list)
                or not choices
                or len(choices) > 256
                or any(not isinstance(x, str) or not x for x in choices)
                or len(set(choices)) != len(choices)
            ):
                raise ValueError("Invalid enum range")
        name = item.get("name") or code.replace("_", " ").capitalize()
        if not isinstance(name, str) or not isinstance(prop.get("unit", ""), str):
            raise ValueError("Invalid name or unit")
        definition = {
            "code": code,
            "dp_id": dp_id,
            "type": types[kind],
            "values": dict(prop),
            "name": name,
        }
        if mode in ("rw", "wr"):
            functions.append(definition)
        if mode in ("rw", "ro"):
            statuses.append(definition)
        ids.add(dp_id)
        codes.add(code)
    return functions, statuses
