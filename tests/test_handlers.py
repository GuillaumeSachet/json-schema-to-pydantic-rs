"""Tests for allOf/anyOf/oneOf combiner handling."""

from typing import Union

import pytest
from pydantic import BaseModel

from json_schema_to_pydantic_rs import PydanticModelBuilder
from json_schema_to_pydantic_rs._exceptions import CombinerError


def test_all_of_merging():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "combined": {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                    {
                        "type": "object",
                        "properties": {"age": {"type": "integer"}},
                        "required": ["age"],
                    },
                ]
            }
        },
    }

    model = builder.create_pydantic_model(schema)
    instance = model(combined={"name": "John", "age": 30})
    assert instance.combined.name == "John"
    assert instance.combined.age == 30


def test_all_of_conflicting_constraints():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {
                            "v": {"type": "integer", "minimum": 0, "maximum": 100}
                        },
                    },
                    {
                        "type": "object",
                        "properties": {
                            "v": {"type": "integer", "minimum": 50, "maximum": 75}
                        },
                    },
                ]
            }
        },
    }

    model = builder.create_pydantic_model(schema)
    instance = model(value={"v": 60})
    assert instance.value.v == 60

    with pytest.raises(ValueError):
        model(value={"v": 25})

    with pytest.raises(ValueError):
        model(value={"v": 80})


def test_any_of_union():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "anyOf": [{"type": "string"}, {"type": "integer"}]
            }
        },
        "required": ["value"],
    }

    model = builder.create_pydantic_model(schema)
    instance = model(value="hello")
    assert instance.value == "hello"

    instance = model(value=42)
    assert instance.value == 42


def test_one_of_discriminated():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "shape": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {
                            "type": {"const": "circle"},
                            "radius": {"type": "number"},
                        },
                        "required": ["type", "radius"],
                    },
                    {
                        "type": "object",
                        "properties": {
                            "type": {"const": "rectangle"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                        },
                        "required": ["type", "width", "height"],
                    },
                ]
            }
        },
    }

    model = builder.create_pydantic_model(schema)

    # Test circle
    instance = model(shape={"type": "circle", "radius": 5.0})
    assert instance.shape.root.type == "circle"
    assert instance.shape.root.radius == 5.0

    # Test rectangle
    instance = model(shape={"type": "rectangle", "width": 10.0, "height": 20.0})
    assert instance.shape.root.type == "rectangle"
    assert instance.shape.root.width == 10.0


def test_one_of_const_literals():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "status": {
                "oneOf": [
                    {"const": "active"},
                    {"const": "inactive"},
                    {"const": "pending"},
                ]
            }
        },
        "required": ["status"],
    }

    model = builder.create_pydantic_model(schema)
    instance = model(status="active")
    assert instance.status == "active"

    with pytest.raises(ValueError):
        model(status="unknown")


def test_one_of_simple_union():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "oneOf": [{"type": "string"}, {"type": "integer"}]
            }
        },
        "required": ["value"],
    }

    model = builder.create_pydantic_model(schema)
    instance = model(value="hello")
    assert instance.value == "hello"

    instance = model(value=42)
    assert instance.value == 42


def test_one_of_nested():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "item": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {
                            "type": {"const": "parent"},
                            "child": {
                                "oneOf": [
                                    {
                                        "type": "object",
                                        "properties": {
                                            "type": {"const": "child1"},
                                            "value": {"type": "string"},
                                        },
                                    },
                                    {
                                        "type": "object",
                                        "properties": {
                                            "type": {"const": "child2"},
                                            "value": {"type": "integer"},
                                        },
                                    },
                                ]
                            },
                        },
                    }
                ]
            }
        },
    }

    model = builder.create_pydantic_model(schema)
    instance = model(item={"type": "parent", "child": {"type": "child1", "value": "test"}})
    assert instance.item.root.type == "parent"
    assert instance.item.root.child.root.type == "child1"
    assert instance.item.root.child.root.value == "test"


def test_empty_combiner_error():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"value": {"allOf": []}},
    }
    with pytest.raises(ValueError, match="allOf must contain at least one schema"):
        builder.create_pydantic_model(schema)


def test_all_of_with_ref():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "combined": {
                "allOf": [
                    {"$ref": "#/definitions/Base"},
                    {
                        "type": "object",
                        "properties": {"extra": {"type": "string"}},
                    },
                ]
            }
        },
        "definitions": {
            "Base": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
        },
    }

    model = builder.create_pydantic_model(schema)
    instance = model(combined={"name": "John", "extra": "bonus"})
    assert instance.combined.name == "John"
    assert instance.combined.extra == "bonus"
