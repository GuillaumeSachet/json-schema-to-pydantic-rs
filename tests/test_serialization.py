"""Tests for Pydantic model serialization round-trips."""

import json

from json_schema_to_pydantic_rs import create_model


def test_model_dump():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer", "default": 0},
            },
            "required": ["name"],
        }
    )
    inst = model(name="test", count=5)
    d = inst.model_dump()
    assert d == {"name": "test", "count": 5}


def test_model_dump_json():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "value": {"type": "number"},
            },
            "required": ["name", "value"],
        }
    )
    inst = model(name="test", value=3.14)
    j = inst.model_dump_json()
    parsed = json.loads(j)
    assert parsed == {"name": "test", "value": 3.14}


def test_model_validate():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "string", "default": "hi"},
            },
            "required": ["x"],
        }
    )
    inst = model.model_validate({"x": 42})
    assert inst.x == 42
    assert inst.y == "hi"


def test_model_validate_json():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "string"},
            },
            "required": ["x", "y"],
        }
    )
    inst = model.model_validate_json('{"x": 42, "y": "hello"}')
    assert inst.x == 42
    assert inst.y == "hello"


def test_round_trip():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "score": {"type": "number"},
                "active": {"type": "boolean"},
            },
            "required": ["name", "score", "active"],
        }
    )
    original = model(name="test", score=9.5, active=True)
    json_str = original.model_dump_json()
    restored = model.model_validate_json(json_str)
    assert restored.name == original.name
    assert restored.score == original.score
    assert restored.active == original.active


def test_nested_round_trip():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["name"],
                }
            },
            "required": ["user"],
        }
    )
    original = model(user={"name": "Alice", "tags": ["admin"]})
    json_str = original.model_dump_json()
    restored = model.model_validate_json(json_str)
    assert restored.user.name == "Alice"
    assert restored.user.tags == ["admin"]


def test_optional_fields_round_trip():
    """Non-required fields with non-nullable types should round-trip through None."""
    model = create_model(
        {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "tags": {"type": "object", "additionalProperties": {"type": "string"}},
                "items": {"type": "array", "items": {"type": "string"}},
                "nested": {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                },
            },
            "required": ["name"],
        }
    )
    # With None defaults
    inst = model(name="test")
    assert inst.tags is None
    assert inst.items is None
    assert inst.nested is None
    restored = model.model_validate(inst.model_dump())
    assert restored.name == "test"
    assert restored.tags is None

    # With actual values
    inst2 = model(name="x", tags={"a": "b"}, items=["c"], nested={"x": 1})
    restored2 = model.model_validate(inst2.model_dump())
    assert restored2.tags == {"a": "b"}
    assert restored2.items == ["c"]
    assert restored2.nested.x == 1
