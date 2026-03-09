"""Tests for constraint extraction and validation."""

import pytest

from json_schema_to_pydantic_rs import PydanticModelBuilder


def test_string_constraints():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "minLength": 3,
                "maxLength": 50,
            }
        },
        "required": ["name"],
    }

    model = builder.create_pydantic_model(schema)

    instance = model(name="Alice")
    assert instance.name == "Alice"

    with pytest.raises(ValueError):
        model(name="Al")

    with pytest.raises(ValueError):
        model(name="A" * 51)


def test_numeric_constraints():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "age": {
                "type": "integer",
                "minimum": 0,
                "maximum": 150,
            }
        },
        "required": ["age"],
    }

    model = builder.create_pydantic_model(schema)
    instance = model(age=25)
    assert instance.age == 25

    with pytest.raises(ValueError):
        model(age=-1)

    with pytest.raises(ValueError):
        model(age=200)


def test_exclusive_bounds():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "exclusiveMinimum": 0,
                "exclusiveMaximum": 100,
            }
        },
        "required": ["score"],
    }

    model = builder.create_pydantic_model(schema)
    instance = model(score=50.0)
    assert instance.score == 50.0

    with pytest.raises(ValueError):
        model(score=0)

    with pytest.raises(ValueError):
        model(score=100)


def test_pattern_constraint():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "pattern": "^[A-Z]{3}$",
            }
        },
        "required": ["code"],
    }

    model = builder.create_pydantic_model(schema)
    instance = model(code="ABC")
    assert instance.code == "ABC"

    with pytest.raises(ValueError):
        model(code="abc")


def test_multiple_of():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "type": "integer",
                "multipleOf": 5,
            }
        },
        "required": ["value"],
    }

    model = builder.create_pydantic_model(schema)
    instance = model(value=15)
    assert instance.value == 15

    with pytest.raises(ValueError):
        model(value=13)
