"""Small dependency-free validator for the JSON Schema subset adapters use.

Schemas are part of the agent contract, not documentation: validation happens
before handler dispatch on every transport.
"""

import math


class ValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


def _path(parent, key):
    if isinstance(key, int):
        return f"{parent}[{key}]"
    return f"{parent}.{key}" if parent else str(key)


def _is_finite_number(value):
    # Integers are always finite; converting an attacker-sized integer to a
    # float can itself overflow. Booleans are deliberately not numbers here.
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _matches_type(value, expected):
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "boolean": lambda: isinstance(value, bool),
        # JSON Schema treats 1 and 1.0 as the same integral number.
        "integer": lambda: (
            (isinstance(value, int) and not isinstance(value, bool))
            or (isinstance(value, float) and math.isfinite(value)
                and value.is_integer())
        ),
        "number": lambda: _is_finite_number(value),
        "null": lambda: value is None,
    }.get(expected, lambda: False)()


def errors(value, schema, path="$", limit=50):
    """Return deterministic validation errors for the supported schema subset."""
    found = []

    def add(message):
        if len(found) < limit:
            found.append(message)

    def walk(current, spec, current_path):
        if len(found) >= limit:
            return
        if not isinstance(spec, dict):
            add(f"{current_path}: invalid schema")
            return
        expected = spec.get("type")
        if expected is not None:
            choices = expected if isinstance(expected, list) else [expected]
            if not any(_matches_type(current, choice) for choice in choices):
                add(f"{current_path}: expected {' or '.join(map(str, choices))}")
                return
        if "enum" in spec and current not in spec["enum"]:
            add(f"{current_path}: expected one of {spec['enum']!r}")
        if isinstance(current, dict):
            properties = spec.get("properties", {})
            for name in spec.get("required", []):
                if name not in current:
                    add(f"{_path(current_path, name)}: required field is missing")
            additional = spec.get("additionalProperties", True)
            for name, item in current.items():
                if name in properties:
                    walk(item, properties[name], _path(current_path, name))
                elif additional is False:
                    add(f"{_path(current_path, name)}: field is not allowed")
                elif isinstance(additional, dict):
                    walk(item, additional, _path(current_path, name))
        if isinstance(current, list):
            if "minItems" in spec and len(current) < spec["minItems"]:
                add(f"{current_path}: must contain at least {spec['minItems']} items")
            if "maxItems" in spec and len(current) > spec["maxItems"]:
                add(f"{current_path}: must contain at most {spec['maxItems']} items")
            item_schema = spec.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(current):
                    walk(item, item_schema, _path(current_path, index))
        if isinstance(current, str):
            if "minLength" in spec and len(current) < spec["minLength"]:
                add(f"{current_path}: length must be at least {spec['minLength']}")
            if "maxLength" in spec and len(current) > spec["maxLength"]:
                add(f"{current_path}: length must be at most {spec['maxLength']}")
        if isinstance(current, (int, float)) and not isinstance(current, bool):
            if not _is_finite_number(current):
                add(f"{current_path}: number must be finite")
            elif "minimum" in spec and current < spec["minimum"]:
                add(f"{current_path}: must be >= {spec['minimum']}")
            elif "maximum" in spec and current > spec["maximum"]:
                add(f"{current_path}: must be <= {spec['maximum']}")

    walk(value, schema or {}, path)
    return found


def validate(value, schema):
    found = errors(value, schema)
    if found:
        raise ValidationError(found)
    return value
