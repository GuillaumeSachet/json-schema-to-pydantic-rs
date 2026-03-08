"""Tests with real-world complex schemas."""

import pytest
from pydantic import ValidationError

from json_schema_to_pydantic_rs import create_model


def test_job_config():
    """Schema for a batch job configuration with constraints and defaults."""
    schema = {
        "title": "JobConfig",
        "properties": {
            "steps": {
                "items": {
                    "properties": {
                        "options": {
                            "additionalProperties": {"type": "boolean"},
                            "type": "object",
                        },
                        "stepId": {"type": "string"},
                    },
                    "type": "object",
                    "required": ["stepId", "options"],
                },
                "minItems": 1,
                "type": "array",
                "maxItems": 1,
            },
            "max_retries": {
                "multipleOf": 1000,
                "default": 16000,
                "maximum": 128000,
                "type": "integer",
                "minimum": 1000,
            },
            "priority": {
                "default": "medium",
                "enum": ["low", "medium", "high"],
                "type": "string",
            },
            "threshold": {
                "multipleOf": 0.01,
                "default": 0.7,
                "maximum": 1,
                "type": "number",
                "minimum": 0,
            },
            "parent_id": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
            },
        },
        "type": "object",
    }
    Model = create_model(schema)

    # Defaults
    inst = Model()
    assert inst.max_retries == 16000
    assert inst.priority == "medium"
    assert inst.threshold == 0.7

    # Constraints
    with pytest.raises(ValidationError):
        Model(max_retries=500)
    with pytest.raises(ValidationError):
        Model(max_retries=1500)
    with pytest.raises(ValidationError):
        Model(threshold=1.5)
    with pytest.raises(ValidationError):
        Model(priority="invalid")

    # Nested array of objects with typed dict
    inst = Model(
        steps=[{"stepId": "abc", "options": {"verbose": True}}]
    )
    assert inst.steps[0].stepId == "abc"
    assert inst.steps[0].options == {"verbose": True}

    # Nullable field
    assert Model(parent_id=None).parent_id is None
    assert Model(parent_id="abc").parent_id == "abc"


def test_request_with_discriminated_unions_and_refs():
    """Complex schema with $defs, $ref, discriminated unions, enum refs, anyOf nullable."""
    schema = {
        "title": "Request",
        "$defs": {
            "Category": {
                "enum": ["billing", "support", "sales"],
                "type": "string",
            },
            "PriceRule": {
                "title": "PriceRule",
                "properties": {
                    "max_value": {"type": "number"},
                    "name": {"type": "string"},
                    "rule_type": {
                        "default": "price",
                        "const": "price",
                        "type": "string",
                    },
                    "category": {"$ref": "#/$defs/Category"},
                },
                "type": "object",
                "required": ["name", "category", "max_value"],
            },
            "CountRule": {
                "title": "CountRule",
                "properties": {
                    "max_value": {"type": "number"},
                    "name": {"type": "string"},
                    "rule_type": {
                        "default": "count",
                        "const": "count",
                        "type": "string",
                    },
                    "category": {"$ref": "#/$defs/Category"},
                },
                "type": "object",
                "required": ["name", "category", "max_value"],
            },
            "TextPayload": {
                "title": "TextPayload",
                "properties": {
                    "kind": {
                        "default": "text",
                        "const": "text",
                        "type": "string",
                    },
                    "body": {"type": "string"},
                },
                "type": "object",
                "required": ["body"],
            },
            "PingPayload": {
                "title": "PingPayload",
                "properties": {
                    "kind": {
                        "default": "ping",
                        "const": "ping",
                        "type": "string",
                    },
                },
                "type": "object",
            },
        },
        "properties": {
            "tags": {
                "additionalProperties": {"type": "string"},
                "default": {},
                "type": "object",
            },
            "payload": {
                "oneOf": [
                    {"$ref": "#/$defs/TextPayload"},
                    {"$ref": "#/$defs/PingPayload"},
                ],
            },
            "rules": {
                "anyOf": [
                    {
                        "items": {
                            "oneOf": [
                                {"$ref": "#/$defs/CountRule"},
                                {"$ref": "#/$defs/PriceRule"},
                            ],
                        },
                        "type": "array",
                    },
                    {"type": "null"},
                ]
            },
        },
        "type": "object",
        "required": ["payload"],
    }
    Model = create_model(schema)

    # Text payload
    inst = Model(payload={"kind": "text", "body": "Hello"})
    root = inst.payload.root if hasattr(inst.payload, "root") else inst.payload
    assert root.kind == "text"
    assert root.body == "Hello"

    # Ping payload
    inst = Model(payload={"kind": "ping"})
    root = inst.payload.root if hasattr(inst.payload, "root") else inst.payload
    assert root.kind == "ping"

    # Tags typed dict
    inst = Model(
        payload={"kind": "text", "body": "test"},
        tags={"env": "prod"},
    )
    assert inst.tags == {"env": "prod"}

    # Rules with enum ref validation
    inst = Model(
        payload={"kind": "text", "body": "test"},
        rules=[
            {
                "rule_type": "price",
                "name": "max_price",
                "category": "billing",
                "max_value": 1.0,
            },
            {
                "rule_type": "count",
                "name": "max_items",
                "category": "support",
                "max_value": 10000,
            },
        ],
    )
    assert len(inst.rules) == 2

    # Invalid category enum
    with pytest.raises(ValidationError):
        Model(
            payload={"kind": "text", "body": "test"},
            rules=[
                {
                    "rule_type": "price",
                    "name": "x",
                    "category": "INVALID",
                    "max_value": 1.0,
                }
            ],
        )

    # Null rules
    inst = Model(
        payload={"kind": "text", "body": "test"}, rules=None
    )
    assert inst.rules is None


def test_order_with_multiple_ref_nesting():
    """Order schema with product refs, customer ref, address ref."""
    schema = {
        "title": "Order",
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "customer": {"$ref": "#/$defs/Customer"},
            "items": {
                "type": "array",
                "items": {"$ref": "#/$defs/Product"},
            },
            "shipping": {"$ref": "#/$defs/Address"},
            "billing": {"$ref": "#/$defs/Address"},
        },
        "required": ["id", "customer", "items"],
        "$defs": {
            "Customer": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                },
                "required": ["name"],
            },
            "Product": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "price": {"type": "number", "minimum": 0},
                    "quantity": {"type": "integer", "minimum": 1},
                },
                "required": ["name", "price"],
            },
            "Address": {
                "type": "object",
                "properties": {
                    "street": {"type": "string"},
                    "city": {"type": "string"},
                    "zip": {"type": "string"},
                },
            },
        },
    }
    Model = create_model(schema)

    inst = Model(
        id=1,
        customer={"name": "Alice", "email": "alice@example.com"},
        items=[
            {"name": "Widget", "price": 9.99, "quantity": 2},
            {"name": "Gadget", "price": 24.99},
        ],
        shipping={"street": "123 Main", "city": "NYC", "zip": "10001"},
        billing={"street": "456 Oak", "city": "LA"},
    )
    assert inst.id == 1
    assert inst.customer.name == "Alice"
    assert len(inst.items) == 2
    assert inst.items[0].price == 9.99
    assert inst.shipping.street == "123 Main"
    assert inst.billing.city == "LA"

    # Price constraint
    with pytest.raises(ValidationError):
        Model(
            id=2,
            customer={"name": "Bob"},
            items=[{"name": "Bad", "price": -1}],
        )


def test_wide_object_50_fields():
    """Object with many fields of varying types."""
    properties = {}
    required = []
    for i in range(50):
        t = ["string", "integer", "number"][i % 3]
        properties[f"field_{i}"] = {"type": t}
        if i % 2 == 0:
            required.append(f"field_{i}")

    schema = {
        "title": "WideObject",
        "type": "object",
        "properties": properties,
        "required": required,
    }
    Model = create_model(schema)
    assert len(Model.model_fields) == 50

    kwargs = {}
    for i in range(50):
        if i % 3 == 0:
            kwargs[f"field_{i}"] = f"value_{i}"
        elif i % 3 == 1:
            kwargs[f"field_{i}"] = i
        else:
            kwargs[f"field_{i}"] = float(i)

    inst = Model(**kwargs)
    assert inst.field_0 == "value_0"
    assert inst.field_1 == 1
    assert inst.field_2 == 2.0


def test_schema_with_description_and_title():
    model = create_model(
        {
            "title": "MyModel",
            "description": "A useful model",
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The name field",
                }
            },
        }
    )
    assert model.__name__ == "MyModel"
    field_info = model.model_fields["name"]
    assert field_info.description == "The name field"
