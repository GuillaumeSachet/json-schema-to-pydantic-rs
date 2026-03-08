"""Tests for required/optional fields and default values."""

import pytest
from pydantic import ValidationError

from json_schema_to_pydantic_rs import create_model


def test_required_field():
    model = create_model(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
    )
    assert model(name="test").name == "test"
    with pytest.raises(ValidationError):
        model()


def test_optional_field_defaults_to_none():
    model = create_model(
        {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
    )
    inst = model()
    assert inst.name is None


def test_explicit_default():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "default": 10},
                "name": {"type": "string", "default": "unknown"},
            },
        }
    )
    inst = model()
    assert inst.count == 10
    assert inst.name == "unknown"


def test_default_empty_string():
    model = create_model(
        {
            "type": "object",
            "properties": {"prompt": {"type": "string", "default": ""}},
        }
    )
    assert model().prompt == ""


def test_default_false():
    model = create_model(
        {
            "type": "object",
            "properties": {"active": {"type": "boolean", "default": False}},
        }
    )
    assert model().active is False


def test_default_zero():
    model = create_model(
        {
            "type": "object",
            "properties": {"count": {"type": "integer", "default": 0}},
        }
    )
    assert model().count == 0
