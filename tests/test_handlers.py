"""Tests for allOf/anyOf/oneOf/if-then-else combiner handling."""

import pytest
from pydantic import ValidationError

from json_schema_to_pydantic_rs import PydanticModelBuilder, create_model


# ═══════════════════════════════════════════════════════════════════════════════
# allOf
# ═══════════════════════════════════════════════════════════════════════════════


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


def test_empty_combiner_error():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"value": {"allOf": []}},
    }
    with pytest.raises(ValueError, match="allOf must contain at least one schema"):
        builder.create_pydantic_model(schema)


# ═══════════════════════════════════════════════════════════════════════════════
# anyOf
# ═══════════════════════════════════════════════════════════════════════════════


def test_any_of_union():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"value": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
        "required": ["value"],
    }

    model = builder.create_pydantic_model(schema)
    instance = model(value="hello")
    assert instance.value == "hello"

    instance = model(value=42)
    assert instance.value == 42


def test_anyof_nullable():
    model = create_model(
        {
            "type": "object",
            "properties": {"v": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
            "required": ["v"],
        }
    )
    assert model(v="hello").v == "hello"
    assert model(v=None).v is None


def test_anyof_nullable_array():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "items": {
                    "anyOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "null"},
                    ]
                }
            },
        }
    )
    assert model(items=["a", "b"]).items == ["a", "b"]
    assert model(items=None).items is None


def test_anyof_with_ref():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "data": {
                    "anyOf": [
                        {"$ref": "#/$defs/Payload"},
                        {"type": "null"},
                    ]
                }
            },
            "$defs": {
                "Payload": {
                    "type": "object",
                    "properties": {"content": {"type": "string"}},
                    "required": ["content"],
                }
            },
        }
    )
    inst = model(data={"content": "hello"})
    assert inst.data.content == "hello"
    assert model(data=None).data is None


def test_anyof_multiple_objects():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "v": {
                    "anyOf": [
                        {
                            "type": "object",
                            "properties": {"name": {"type": "string"}},
                        },
                        {
                            "type": "object",
                            "properties": {"id": {"type": "integer"}},
                        },
                    ]
                }
            },
            "required": ["v"],
        }
    )
    inst = model(v={"name": "Alice"})
    assert inst.v.name == "Alice"


# ═══════════════════════════════════════════════════════════════════════════════
# oneOf
# ═══════════════════════════════════════════════════════════════════════════════


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

    instance = model(shape={"type": "circle", "radius": 5.0})
    assert instance.shape.root.type == "circle"
    assert instance.shape.root.radius == 5.0

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
        "properties": {"value": {"oneOf": [{"type": "string"}, {"type": "integer"}]}},
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
    instance = model(
        item={"type": "parent", "child": {"type": "child1", "value": "test"}}
    )
    assert instance.item.root.type == "parent"
    assert instance.item.root.child.root.type == "child1"
    assert instance.item.root.child.root.value == "test"


def test_oneof_discriminated_with_refs():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "payload": {
                    "oneOf": [
                        {"$ref": "#/$defs/MessagePayload"},
                        {"$ref": "#/$defs/PingPayload"},
                    ]
                }
            },
            "$defs": {
                "MessagePayload": {
                    "type": "object",
                    "properties": {
                        "type": {"const": "message"},
                        "text": {"type": "string"},
                    },
                    "required": ["type", "text"],
                },
                "PingPayload": {
                    "type": "object",
                    "properties": {
                        "type": {"const": "ping"},
                        "ts": {"type": "string"},
                    },
                    "required": ["type"],
                },
            },
        }
    )
    inst = model(payload={"type": "message", "text": "hello"})
    assert inst.payload.root.type == "message"
    assert inst.payload.root.text == "hello"

    inst = model(payload={"type": "ping", "ts": "2026-01-01"})
    assert inst.payload.root.type == "ping"


# ═══════════════════════════════════════════════════════════════════════════════
# if / then / else
# ═══════════════════════════════════════════════════════════════════════════════


def test_if_then_else_basic():
    """Both branches are accepted; branch-only fields are optional."""
    model = create_model(
        {
            "type": "object",
            "properties": {
                "type": {"enum": ["residential", "business"]},
                "address": {"type": "string"},
            },
            "required": ["type", "address"],
            "if": {
                "properties": {"type": {"const": "business"}},
            },
            "then": {
                "properties": {"tax_id": {"type": "string"}},
                "required": ["tax_id"],
            },
            "else": {
                "properties": {"nickname": {"type": "string"}},
            },
        }
    )

    # Business branch — tax_id accepted
    inst = model(type="business", address="123 Main St", tax_id="TX-123")
    assert inst.tax_id == "TX-123"

    # Residential branch — nickname accepted, tax_id optional
    inst = model(type="residential", address="456 Oak Ave", nickname="home")
    assert inst.nickname == "home"

    # Both branch fields are optional (only required in one branch)
    inst = model(type="residential", address="789 Elm St")
    assert inst.tax_id is None
    assert inst.nickname is None


def test_if_then_only():
    """if/then without else — then fields become optional."""
    model = create_model(
        {
            "type": "object",
            "properties": {
                "role": {"type": "string"},
            },
            "required": ["role"],
            "if": {
                "properties": {"role": {"const": "admin"}},
            },
            "then": {
                "properties": {
                    "permissions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        }
    )

    inst = model(role="admin", permissions=["read", "write"])
    assert inst.permissions == ["read", "write"]

    # permissions is optional
    inst = model(role="viewer")
    assert inst.permissions is None


def test_if_then_else_with_constraints():
    """Constraints from branches are merged."""
    model = create_model(
        {
            "type": "object",
            "properties": {
                "category": {"enum": ["individual", "company"]},
                "name": {"type": "string", "minLength": 1},
            },
            "required": ["category", "name"],
            "if": {
                "properties": {"category": {"const": "company"}},
            },
            "then": {
                "properties": {
                    "employee_count": {"type": "integer", "minimum": 1},
                },
                "required": ["employee_count"],
            },
            "else": {
                "properties": {
                    "age": {"type": "integer", "minimum": 0, "maximum": 150},
                },
            },
        }
    )

    # Company
    inst = model(category="company", name="Acme", employee_count=50)
    assert inst.employee_count == 50

    # Individual
    inst = model(category="individual", name="Alice", age=30)
    assert inst.age == 30

    # Constraint validation still works
    with pytest.raises(ValidationError):
        model(category="individual", name="Bob", age=-1)


def test_if_then_else_nested_field():
    """if/then/else as a field-level sub-schema."""
    model = create_model(
        {
            "type": "object",
            "properties": {
                "contact": {
                    "type": "object",
                    "properties": {
                        "method": {"enum": ["email", "phone"]},
                    },
                    "required": ["method"],
                    "if": {
                        "properties": {"method": {"const": "email"}},
                    },
                    "then": {
                        "properties": {"email": {"type": "string"}},
                        "required": ["email"],
                    },
                    "else": {
                        "properties": {"phone": {"type": "string"}},
                        "required": ["phone"],
                    },
                },
            },
            "required": ["contact"],
        }
    )

    inst = model(contact={"method": "email", "email": "a@b.com"})
    assert inst.contact.email == "a@b.com"

    inst = model(contact={"method": "phone", "phone": "555-1234"})
    assert inst.contact.phone == "555-1234"


def test_if_then_else_required_in_both_branches():
    """A field required in both then and else becomes required."""
    model = create_model(
        {
            "type": "object",
            "properties": {
                "mode": {"type": "string"},
            },
            "required": ["mode"],
            "if": {
                "properties": {"mode": {"const": "a"}},
            },
            "then": {
                "properties": {"shared": {"type": "string"}},
                "required": ["shared"],
            },
            "else": {
                "properties": {"shared": {"type": "string"}},
                "required": ["shared"],
            },
        }
    )

    # shared is required (in both branches)
    with pytest.raises(ValidationError):
        model(mode="a")
