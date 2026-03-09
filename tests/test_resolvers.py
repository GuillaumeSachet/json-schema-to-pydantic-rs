"""Tests for type resolution and reference handling via the Rust core."""

import pytest
from datetime import datetime, date, time
from uuid import UUID

from pydantic import ValidationError

from json_schema_to_pydantic_rs import PydanticModelBuilder, create_model


# ═══════════════════════════════════════════════════════════════════════════════
# Basic type mapping
# ═══════════════════════════════════════════════════════════════════════════════


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


def test_null_type():
    model = create_model(
        {
            "type": "object",
            "properties": {"v": {"type": "null"}},
            "required": ["v"],
        }
    )
    inst = model(v=None)
    assert inst.v is None


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


def test_type_array_nullable_union():
    model = create_model(
        {
            "type": "object",
            "properties": {"v": {"type": ["string", "integer", "null"]}},
            "required": ["v"],
        }
    )
    assert model(v="a").v == "a"
    assert model(v=1).v == 1
    assert model(v=None).v is None


# ═══════════════════════════════════════════════════════════════════════════════
# Format types
# ═══════════════════════════════════════════════════════════════════════════════


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


def test_format_time():
    model = create_model(
        {
            "type": "object",
            "properties": {"t": {"type": "string", "format": "time"}},
            "required": ["t"],
        }
    )
    inst = model(t="12:30:00")
    assert isinstance(inst.t, time)


def test_format_uuid():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"uid": {"type": "string", "format": "uuid"}},
    }
    model = builder.create_pydantic_model(schema)
    instance = model(uid="12345678-1234-5678-1234-567812345678")
    assert isinstance(instance.uid, UUID)


def test_format_email():
    model = create_model(
        {
            "type": "object",
            "properties": {"email": {"type": "string", "format": "email"}},
            "required": ["email"],
        }
    )
    inst = model(email="user@example.com")
    assert inst.email == "user@example.com"

    with pytest.raises(ValidationError):
        model(email="not-an-email")


def test_format_uri():
    model = create_model(
        {
            "type": "object",
            "properties": {"url": {"type": "string", "format": "uri"}},
            "required": ["url"],
        }
    )
    inst = model(url="https://example.com")
    assert str(inst.url) == "https://example.com/"


# ═══════════════════════════════════════════════════════════════════════════════
# Enum and const
# ═══════════════════════════════════════════════════════════════════════════════


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


def test_integer_enum():
    model = create_model(
        {
            "type": "object",
            "properties": {"level": {"enum": [1, 2, 3]}},
            "required": ["level"],
        }
    )
    assert model(level=2).level == 2
    with pytest.raises(ValidationError):
        model(level=4)


def test_mixed_enum():
    model = create_model(
        {
            "type": "object",
            "properties": {"v": {"enum": ["a", 1, True, None]}},
            "required": ["v"],
        }
    )
    assert model(v="a").v == "a"
    assert model(v=1).v == 1


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


def test_const_null():
    model = create_model(
        {
            "type": "object",
            "properties": {"v": {"const": None}},
            "required": ["v"],
        }
    )
    assert model(v=None).v is None


# ═══════════════════════════════════════════════════════════════════════════════
# Arrays
# ═══════════════════════════════════════════════════════════════════════════════


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


def test_array_of_objects():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                        },
                        "required": ["id"],
                    },
                }
            },
            "required": ["items"],
        }
    )
    inst = model(items=[{"id": 1, "name": "a"}, {"id": 2}])
    assert inst.items[0].id == 1
    assert inst.items[0].name == "a"
    assert inst.items[1].id == 2


def test_array_min_max_items():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "v": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 3,
                }
            },
            "required": ["v"],
        }
    )
    assert model(v=["a"]).v == ["a"]
    assert model(v=["a", "b", "c"]).v == ["a", "b", "c"]

    with pytest.raises(ValidationError):
        model(v=[])

    with pytest.raises(ValidationError):
        model(v=["a", "b", "c", "d"])


# ═══════════════════════════════════════════════════════════════════════════════
# Dict / additionalProperties
# ═══════════════════════════════════════════════════════════════════════════════


def test_untyped_dict():
    model = create_model(
        {
            "type": "object",
            "properties": {"meta": {"type": "object"}},
            "required": ["meta"],
        }
    )
    inst = model(meta={"a": 1, "b": "two"})
    assert inst.meta == {"a": 1, "b": "two"}


def test_typed_dict_string_values():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "annotations": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                }
            },
            "required": ["annotations"],
        }
    )
    inst = model(annotations={"env": "prod", "region": "eu"})
    assert inst.annotations == {"env": "prod", "region": "eu"}

    schema = model.model_json_schema()
    assert schema["properties"]["annotations"]["additionalProperties"] == {
        "type": "string"
    }


def test_typed_dict_boolean_values():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "flags": {
                    "type": "object",
                    "additionalProperties": {"type": "boolean"},
                }
            },
            "required": ["flags"],
        }
    )
    inst = model(flags={"active": True, "visible": False})
    assert inst.flags == {"active": True, "visible": False}

    with pytest.raises(ValidationError):
        model(flags={"active": [1, 2]})


def test_typed_dict_integer_values():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "counts": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                }
            },
            "required": ["counts"],
        }
    )
    inst = model(counts={"a": 1, "b": 2})
    assert inst.counts == {"a": 1, "b": 2}


def test_typed_dict_number_values():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                }
            },
            "required": ["scores"],
        }
    )
    inst = model(scores={"math": 95.5, "science": 88.0})
    assert inst.scores == {"math": 95.5, "science": 88.0}


# ═══════════════════════════════════════════════════════════════════════════════
# $ref and $defs / definitions
# ═══════════════════════════════════════════════════════════════════════════════


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


def test_ref_to_enum():
    model = create_model(
        {
            "type": "object",
            "properties": {"status": {"$ref": "#/$defs/StatusEnum"}},
            "$defs": {
                "StatusEnum": {
                    "enum": ["active", "inactive", "pending"],
                    "type": "string",
                }
            },
            "required": ["status"],
        }
    )
    assert model(status="active").status == "active"
    with pytest.raises(ValidationError):
        model(status="invalid")


def test_multiple_refs_to_same_enum():
    """Enum $ref should be resolved each time, not treated as forward ref."""
    model = create_model(
        {
            "type": "object",
            "properties": {
                "input_type": {"$ref": "#/$defs/CostType"},
                "output_type": {"$ref": "#/$defs/CostType"},
            },
            "$defs": {
                "CostType": {
                    "enum": ["token", "api_call", "storage"],
                    "type": "string",
                }
            },
            "required": ["input_type", "output_type"],
        }
    )
    inst = model(input_type="token", output_type="api_call")
    assert inst.input_type == "token"
    assert inst.output_type == "api_call"

    with pytest.raises(ValidationError):
        model(input_type="invalid", output_type="token")

    with pytest.raises(ValidationError):
        model(input_type="token", output_type="invalid")


def test_multiple_refs_to_same_model():
    model = create_model(
        {
            "type": "object",
            "properties": {
                "billing": {"$ref": "#/$defs/Address"},
                "shipping": {"$ref": "#/$defs/Address"},
            },
            "$defs": {
                "Address": {
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
    inst = model(
        billing={"street": "123 Main", "city": "NYC"},
        shipping={"street": "456 Oak"},
    )
    assert inst.billing.street == "123 Main"
    assert inst.shipping.street == "456 Oak"


def test_nested_refs():
    model = create_model(
        {
            "type": "object",
            "properties": {"order": {"$ref": "#/$defs/Order"}},
            "$defs": {
                "Order": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "customer": {"$ref": "#/$defs/Customer"},
                    },
                    "required": ["id", "customer"],
                },
                "Customer": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "email": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        }
    )
    inst = model(order={"id": 1, "customer": {"name": "Alice", "email": "a@b.com"}})
    assert inst.order.id == 1
    assert inst.order.customer.name == "Alice"


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


def test_ref_to_scalar():
    """$ref to a simple string type (not object, not enum)."""
    model = create_model(
        {
            "type": "object",
            "properties": {"name": {"$ref": "#/$defs/NameType"}},
            "$defs": {"NameType": {"type": "string", "minLength": 1}},
            "required": ["name"],
        }
    )
    inst = model(name="hello")
    assert inst.name == "hello"
