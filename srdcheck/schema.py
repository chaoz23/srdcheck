"""Small dependency-free validator for the JSON Schema subset adapters use.

Schemas are part of the agent contract, not documentation: validation happens
before handler dispatch on every transport. JSON Schema integral-number
semantics are preserved without leaking Python's ``float`` representation into
handlers: accepted integral floats are normalized to fresh integer values.
"""

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationIssue:
    """A machine-classifiable validation failure with legacy string rendering."""

    path: str
    code: str
    detail: str

    def __str__(self):
        return f"{self.path}: {self.detail}"


class ValidationError(ValueError):
    def __init__(self, errors):
        supplied = list(errors)
        self.issues = [error for error in supplied
                       if isinstance(error, ValidationIssue)]
        self.errors = [str(error) for error in supplied]
        super().__init__("; ".join(self.errors))


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


def issues(value, schema, path="$", limit=50):
    """Return typed, deterministic issues for the supported schema subset."""
    found = []

    def add(issue_path, code, detail):
        if len(found) < limit:
            found.append(ValidationIssue(issue_path, code, detail))

    def walk(current, spec, current_path):
        if len(found) >= limit:
            return
        if not isinstance(spec, dict):
            add(current_path, "invalid-schema", "invalid schema")
            return
        expected = spec.get("type")
        if expected is not None:
            choices = expected if isinstance(expected, list) else [expected]
            if not any(_matches_type(current, choice) for choice in choices):
                add(current_path, "type",
                    f"expected {' or '.join(map(str, choices))}")
                return
        if "enum" in spec and current not in spec["enum"]:
            add(current_path, "enum", f"expected one of {spec['enum']!r}")
        if isinstance(current, dict):
            properties = spec.get("properties", {})
            for name in spec.get("required", []):
                if name not in current:
                    add(_path(current_path, name), "required",
                        "required field is missing")
            additional = spec.get("additionalProperties", True)
            for name, item in current.items():
                if name in properties:
                    walk(item, properties[name], _path(current_path, name))
                elif additional is False:
                    add(_path(current_path, name), "additional-property",
                        "field is not allowed")
                elif isinstance(additional, dict):
                    walk(item, additional, _path(current_path, name))
        if isinstance(current, list):
            if "minItems" in spec and len(current) < spec["minItems"]:
                add(current_path, "min-items",
                    f"must contain at least {spec['minItems']} items")
            if "maxItems" in spec and len(current) > spec["maxItems"]:
                add(current_path, "max-items",
                    f"must contain at most {spec['maxItems']} items")
            item_schema = spec.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(current):
                    walk(item, item_schema, _path(current_path, index))
        if isinstance(current, str):
            if "minLength" in spec and len(current) < spec["minLength"]:
                add(current_path, "min-length",
                    f"length must be at least {spec['minLength']}")
            if "maxLength" in spec and len(current) > spec["maxLength"]:
                add(current_path, "max-length",
                    f"length must be at most {spec['maxLength']}")
            if "pattern" in spec:
                pattern = spec["pattern"]
                if not isinstance(pattern, str):
                    add(current_path, "invalid-schema",
                        "pattern must be a string")
                else:
                    try:
                        matches = re.search(pattern, current) is not None
                    except re.error:
                        add(current_path, "invalid-schema",
                            "pattern must be a valid regular expression")
                    else:
                        if not matches:
                            add(current_path, "pattern",
                                f"must match pattern {pattern!r}")
        if isinstance(current, (int, float)) and not isinstance(current, bool):
            if not _is_finite_number(current):
                add(current_path, "finite", "number must be finite")
            elif "minimum" in spec and current < spec["minimum"]:
                add(current_path, "minimum", f"must be >= {spec['minimum']}")
            elif "maximum" in spec and current > spec["maximum"]:
                add(current_path, "maximum", f"must be <= {spec['maximum']}")

    walk(value, schema or {}, path)
    return found


def errors(value, schema, path="$", limit=50):
    """Return the legacy deterministic string API for schema failures."""
    return [str(issue) for issue in issues(value, schema, path, limit)]


def normalize_integers(value, schema):
    """Return a fresh schema-shaped value with integral floats made integers.

    Callers validate first. This deliberately follows only the schema subset
    supported by :func:`issues`; unknown permitted values are copied unchanged.
    The input object is never mutated.
    """
    if not isinstance(schema, dict) or not schema:
        return value

    expected = schema.get("type")
    choices = expected if isinstance(expected, list) else [expected]
    if ("integer" in choices and isinstance(value, float)
            and math.isfinite(value) and value.is_integer()):
        return int(value)

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        additional = schema.get("additionalProperties", True)
        normalized = {}
        for name, item in value.items():
            child_schema = properties.get(name)
            if child_schema is None and isinstance(additional, dict):
                child_schema = additional
            normalized[name] = normalize_integers(item, child_schema or {})
        return normalized

    if isinstance(value, list):
        item_schema = schema.get("items", {})
        return [normalize_integers(item, item_schema) for item in value]

    return value


def validate(value, schema):
    found = issues(value, schema)
    if found:
        raise ValidationError(found)
    return normalize_integers(value, schema)
