"""Tests for type resolution and reference handling via the Rust core."""

import pytest
from datetime import datetime, date, time
from typing import List, Optional, Set, Union
from uuid import UUID

from pydantic import AnyUrl, BaseModel

from json_schema_to_pydantic_rs import PydanticModelBuilder, create_model


def test_basic_type_mapping():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "s": {"type": "string"},
            "i": {"type": "integer"},
            "n": {"type": "number"},
            "b": {"type": "boolean"},
        },
    }
    model = builder.create_pydantic_model(schema)
    instance = model(s="hello", i=42, n=3.14, b=True)
    assert instance.s == "hello"
    assert instance.i == 42
    assert instance.n == 3.14
    assert instance.b is True


def test_format_datetime():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"ts": {"type": "string", "format": "date-time"}},
    }
    model = builder.create_pydantic_model(schema)
    instance = model(ts="2024-01-01T00:00:00")
    assert isinstance(instance.ts, datetime)


def test_format_date():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"d": {"type": "string", "format": "date"}},
    }
    model = builder.create_pydantic_model(schema)
    instance = model(d="2024-01-01")
    assert isinstance(instance.d, date)


def test_format_uuid():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"uid": {"type": "string", "format": "uuid"}},
    }
    model = builder.create_pydantic_model(schema)
    instance = model(uid="12345678-1234-5678-1234-567812345678")
    assert isinstance(instance.uid, UUID)


def test_enum_to_literal():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"color": {"enum": ["red", "green", "blue"]}},
        "required": ["color"],
    }
    model = builder.create_pydantic_model(schema)
    instance = model(color="red")
    assert instance.color == "red"

    with pytest.raises(ValueError):
        model(color="yellow")


def test_const_to_literal():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"status": {"const": "active"}},
        "required": ["status"],
    }
    model = builder.create_pydantic_model(schema)
    instance = model(status="active")
    assert instance.status == "active"

    with pytest.raises(ValueError):
        model(status="inactive")


def test_nullable_type():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"value": {"type": ["string", "null"]}},
    }
    model = builder.create_pydantic_model(schema)
    instance = model(value="hello")
    assert instance.value == "hello"

    instance = model(value=None)
    assert instance.value is None


def test_union_type():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"value": {"type": ["string", "integer"]}},
        "required": ["value"],
    }
    model = builder.create_pydantic_model(schema)
    instance = model(value="hello")
    assert instance.value == "hello"

    instance = model(value=42)
    assert instance.value == 42


def test_array_with_items():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "names": {"type": "array", "items": {"type": "string"}},
        },
    }
    model = builder.create_pydantic_model(schema)
    instance = model(names=["Alice", "Bob"])
    assert instance.names == ["Alice", "Bob"]


def test_array_unique_items():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "tags": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        },
    }
    model = builder.create_pydantic_model(schema)
    instance = model(tags={"a", "b", "c"})
    assert isinstance(instance.tags, set)


def test_nested_arrays():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "matrix": {
                "type": "array",
                "items": {"type": "array", "items": {"type": "integer"}},
            },
        },
    }
    model = builder.create_pydantic_model(schema)
    instance = model(matrix=[[1, 2], [3, 4]])
    assert instance.matrix == [[1, 2], [3, 4]]


def test_reference_resolution():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"pet": {"$ref": "#/definitions/Pet"}},
        "definitions": {
            "Pet": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            }
        },
    }
    model = builder.create_pydantic_model(schema)
    instance = model(pet={"name": "Fluffy"})
    assert instance.pet.name == "Fluffy"


def test_reference_resolution_defs():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"pet": {"$ref": "#/$defs/Pet"}},
        "$defs": {
            "Pet": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
            }
        },
    }
    model = builder.create_pydantic_model(schema)
    instance = model(pet={"name": "Rex"})
    assert instance.pet.name == "Rex"


def test_self_referencing_schema():
    """Self-referencing $ref: '#' produces a recursive model with forward ref."""
    builder = PydanticModelBuilder()
    schema = {
        "title": "TreeNode",
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "child": {"$ref": "#"},
        },
    }
    model = builder.create_pydantic_model(schema)
    # The model should be created with a forward reference for the recursive field
    assert model.__name__ == "TreeNode"
    instance = model(value="root")
    assert instance.value == "root"


def test_invalid_reference_path():
    """Invalid $ref path raises an error."""
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"bad": {"$ref": "#/nonexistent/path"}},
    }
    with pytest.raises(ValueError, match="Invalid reference path"):
        builder.create_pydantic_model(schema)
