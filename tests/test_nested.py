"""Tests for nested model creation."""

import pytest
from pydantic import ValidationError

from json_schema_to_pydantic_rs import create_model


def test_simple_nested():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"type": "string"},
                    },
                    "required": ["street"],
                }
            },
        }
    )
    inst = model(address={"street": "123 Main", "city": "NYC"})
    assert inst.address.street == "123 Main"


def test_deeply_nested():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {
                                "level3": {
                                    "type": "object",
                                    "properties": {"value": {"type": "string"}},
                                }
                            },
                        }
                    },
                }
            },
        }
    )
    inst = model(level1={"level2": {"level3": {"value": "deep"}}})
    assert inst.level1.level2.level3.value == "deep"


def test_nested_with_constraints():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "person": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "age": {"type": "integer", "minimum": 0, "maximum": 150},
                    },
                    "required": ["name", "age"],
                }
            },
            "required": ["person"],
        }
    )
    assert model(person={"name": "Alice", "age": 30}).person.name == "Alice"
    with pytest.raises(ValidationError):
        model(person={"name": "", "age": 30})
    with pytest.raises(ValidationError):
        model(person={"name": "Alice", "age": -1})
