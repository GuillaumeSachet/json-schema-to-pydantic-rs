"""Tests using schemas extracted from real OpenAPI specs.

Schemas are taken directly from:
- Stripe API (https://github.com/stripe/openapi)
- GitHub REST API (https://github.com/github/rest-api-description)

OpenAPI 3.0 `nullable: true` is pre-normalized to JSON Schema `anyOf` with null,
and `#/components/schemas/` refs are rewritten to `#/$defs/`.
"""

import pytest
from pydantic import ValidationError

from json_schema_to_pydantic_rs import create_model


# ═══════════════════════════════════════════════════════════════════════════════
# Stripe API — real schemas from spec3.json
# ═══════════════════════════════════════════════════════════════════════════════


def test_stripe_address():
    """Stripe Address schema — extracted from components.schemas.address."""
    schema = {
        "title": "Address",
        "type": "object",
        "properties": {
            "city": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
            "country": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
            "line1": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
            "line2": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
            "postal_code": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
            "state": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
        },
    }
    Model = create_model(schema)

    inst = Model(
        line1="123 Main St",
        line2="Suite 100",
        city="San Francisco",
        state="CA",
        postal_code="94105",
        country="US",
    )
    assert inst.city == "San Francisco"
    assert inst.state == "CA"
    assert inst.country == "US"

    # All fields nullable
    inst2 = Model(city=None, country=None, line1=None)
    assert inst2.city is None

    # maxLength constraint
    with pytest.raises(ValidationError):
        Model(city="x" * 5001)

    # Round-trip
    restored = Model.model_validate_json(inst.model_dump_json())
    assert restored.city == "San Francisco"


def test_stripe_coupon():
    """Stripe Coupon schema — extracted from components.schemas.coupon."""
    schema = {
        "title": "Coupon",
        "type": "object",
        "properties": {
            "id": {"type": "string", "maxLength": 5000},
            "object": {"enum": ["coupon"], "type": "string"},
            "amount_off": {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "null"},
                ]
            },
            "created": {"type": "integer"},
            "currency": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "null"},
                ]
            },
            "duration": {
                "enum": ["forever", "once", "repeating"],
                "type": "string",
            },
            "duration_in_months": {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "null"},
                ]
            },
            "livemode": {"type": "boolean"},
            "max_redemptions": {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "null"},
                ]
            },
            "metadata": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "name": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
            "percent_off": {
                "anyOf": [
                    {"type": "number"},
                    {"type": "null"},
                ]
            },
            "redeem_by": {
                "anyOf": [
                    {"type": "integer"},
                    {"type": "null"},
                ]
            },
            "times_redeemed": {"type": "integer"},
            "valid": {"type": "boolean"},
        },
        "required": [
            "created",
            "duration",
            "id",
            "livemode",
            "object",
            "times_redeemed",
            "valid",
        ],
    }
    Model = create_model(schema)

    inst = Model(
        id="SUMMER2025",
        object="coupon",
        created=1700000000,
        duration="repeating",
        duration_in_months=3,
        livemode=False,
        times_redeemed=42,
        valid=True,
        percent_off=25.5,
        name="Summer Sale",
        metadata={"campaign": "summer"},
    )
    assert inst.id == "SUMMER2025"
    assert inst.duration == "repeating"
    assert inst.duration_in_months == 3
    assert inst.percent_off == 25.5
    assert inst.metadata == {"campaign": "summer"}

    # Nullable fields
    inst2 = Model(
        id="FLAT10",
        object="coupon",
        created=1700000000,
        duration="once",
        livemode=True,
        times_redeemed=0,
        valid=True,
        amount_off=1000,
        currency="usd",
        percent_off=None,
        name=None,
    )
    assert inst2.amount_off == 1000
    assert inst2.percent_off is None
    assert inst2.name is None

    # Enum validation
    with pytest.raises(ValidationError):
        Model(
            id="BAD",
            object="coupon",
            created=0,
            duration="weekly",
            livemode=False,
            times_redeemed=0,
            valid=False,
        )

    # Round-trip
    restored = Model.model_validate_json(inst.model_dump_json())
    assert restored.percent_off == 25.5
    assert restored.metadata == {"campaign": "summer"}


def test_stripe_customer_with_address_ref():
    """Stripe Customer (simplified) with $ref to Address."""
    schema = {
        "title": "Customer",
        "type": "object",
        "$defs": {
            "address": {
                "title": "Address",
                "type": "object",
                "properties": {
                    "city": {
                        "anyOf": [
                            {"type": "string", "maxLength": 5000},
                            {"type": "null"},
                        ]
                    },
                    "country": {
                        "anyOf": [
                            {"type": "string", "maxLength": 5000},
                            {"type": "null"},
                        ]
                    },
                    "line1": {
                        "anyOf": [
                            {"type": "string", "maxLength": 5000},
                            {"type": "null"},
                        ]
                    },
                    "postal_code": {
                        "anyOf": [
                            {"type": "string", "maxLength": 5000},
                            {"type": "null"},
                        ]
                    },
                },
            },
        },
        "properties": {
            "id": {"type": "string", "maxLength": 5000},
            "object": {"enum": ["customer"], "type": "string"},
            "address": {
                "anyOf": [
                    {"$ref": "#/$defs/address"},
                    {"type": "null"},
                ],
            },
            "balance": {"type": "integer"},
            "created": {"type": "integer"},
            "email": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
            "livemode": {"type": "boolean"},
            "metadata": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "name": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
            "phone": {
                "anyOf": [
                    {"type": "string", "maxLength": 5000},
                    {"type": "null"},
                ]
            },
        },
        "required": ["balance", "created", "id", "livemode", "object"],
    }
    Model = create_model(schema)

    inst = Model(
        id="cus_abc123",
        object="customer",
        balance=0,
        created=1700000000,
        livemode=False,
        email="alice@example.com",
        name="Alice Smith",
        phone="+1234567890",
        address={
            "line1": "123 Main St",
            "city": "San Francisco",
            "country": "US",
            "postal_code": "94105",
        },
        metadata={"source": "web"},
    )
    assert inst.id == "cus_abc123"
    assert inst.email == "alice@example.com"
    assert inst.address.city == "San Francisco"
    assert inst.metadata == {"source": "web"}

    # Null address
    inst2 = Model(
        id="cus_no_addr",
        object="customer",
        balance=100,
        created=1700000000,
        livemode=True,
        address=None,
    )
    assert inst2.address is None

    # Round-trip
    restored = Model.model_validate_json(inst.model_dump_json())
    assert restored.address.city == "San Francisco"


# ═══════════════════════════════════════════════════════════════════════════════
# GitHub REST API — real schemas from api.github.com.json
# ═══════════════════════════════════════════════════════════════════════════════


def test_github_simple_user():
    """GitHub Simple User schema — extracted from components.schemas.simple-user."""
    schema = {
        "title": "Simple User",
        "description": "A GitHub user.",
        "type": "object",
        "properties": {
            "name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "email": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "login": {"type": "string"},
            "id": {"type": "integer"},
            "node_id": {"type": "string"},
            "avatar_url": {"type": "string", "format": "uri"},
            "gravatar_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "url": {"type": "string", "format": "uri"},
            "html_url": {"type": "string", "format": "uri"},
            "followers_url": {"type": "string", "format": "uri"},
            "repos_url": {"type": "string", "format": "uri"},
            "type": {"type": "string"},
            "site_admin": {"type": "boolean"},
            "starred_at": {"type": "string"},
            "user_view_type": {"type": "string"},
        },
        "required": [
            "avatar_url",
            "html_url",
            "id",
            "login",
            "node_id",
            "repos_url",
            "type",
            "url",
            "followers_url",
            "gravatar_id",
            "site_admin",
        ],
    }
    Model = create_model(schema)

    inst = Model(
        login="octocat",
        id=1,
        node_id="MDQ6VXNlcjE=",
        avatar_url="https://github.com/images/error/octocat_happy.gif",
        gravatar_id="",
        url="https://api.github.com/users/octocat",
        html_url="https://github.com/octocat",
        followers_url="https://api.github.com/users/octocat/followers",
        repos_url="https://api.github.com/users/octocat/repos",
        type="User",
        site_admin=False,
        name="The Octocat",
        email="octocat@github.com",
    )
    assert inst.login == "octocat"
    assert inst.id == 1
    assert inst.type == "User"
    assert inst.name == "The Octocat"

    # Nullable fields
    inst2 = Model(
        login="ghost",
        id=2,
        node_id="xxx",
        avatar_url="https://github.com/ghost.png",
        gravatar_id=None,
        url="https://api.github.com/users/ghost",
        html_url="https://github.com/ghost",
        followers_url="https://api.github.com/users/ghost/followers",
        repos_url="https://api.github.com/users/ghost/repos",
        type="User",
        site_admin=False,
        name=None,
        email=None,
    )
    assert inst2.name is None
    assert inst2.email is None
    assert inst2.gravatar_id is None

    # Round-trip
    restored = Model.model_validate_json(inst.model_dump_json())
    assert restored.login == "octocat"


def test_github_license_simple():
    """GitHub License Simple schema — extracted from components.schemas.license-simple."""
    schema = {
        "title": "License Simple",
        "description": "License Simple",
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "name": {"type": "string"},
            "url": {
                "anyOf": [
                    {"type": "string", "format": "uri"},
                    {"type": "null"},
                ]
            },
            "spdx_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "node_id": {"type": "string"},
            "html_url": {"type": "string", "format": "uri"},
        },
        "required": ["key", "name", "url", "spdx_id", "node_id"],
    }
    Model = create_model(schema)

    inst = Model(
        key="mit",
        name="MIT License",
        url="https://api.github.com/licenses/mit",
        spdx_id="MIT",
        node_id="MDc6TGljZW5zZW1pdA==",
    )
    assert inst.key == "mit"
    assert inst.name == "MIT License"
    assert inst.spdx_id == "MIT"

    # Nullable url and spdx_id
    inst2 = Model(
        key="other",
        name="Other",
        url=None,
        spdx_id=None,
        node_id="xxx",
    )
    assert inst2.url is None
    assert inst2.spdx_id is None

    # Round-trip
    restored = Model.model_validate_json(inst.model_dump_json())
    assert restored.key == "mit"


def test_github_repository_with_refs():
    """GitHub Repository (simplified) with $ref to simple-user and license."""
    schema = {
        "title": "Repository",
        "description": "A repository on GitHub.",
        "type": "object",
        "$defs": {
            "simple-user": {
                "title": "Simple User",
                "type": "object",
                "properties": {
                    "login": {"type": "string"},
                    "id": {"type": "integer"},
                    "avatar_url": {"type": "string", "format": "uri"},
                    "html_url": {"type": "string", "format": "uri"},
                    "type": {"type": "string"},
                    "site_admin": {"type": "boolean"},
                },
                "required": ["login", "id", "type", "site_admin"],
            },
            "nullable-license-simple": {
                "title": "License Simple",
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "name": {"type": "string"},
                    "spdx_id": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "node_id": {"type": "string"},
                },
                "required": ["key", "name", "spdx_id", "node_id"],
            },
        },
        "properties": {
            "id": {"type": "integer"},
            "node_id": {"type": "string"},
            "name": {"type": "string"},
            "full_name": {"type": "string"},
            "license": {"$ref": "#/$defs/nullable-license-simple"},
            "forks": {"type": "integer"},
            "permissions": {
                "type": "object",
                "properties": {
                    "admin": {"type": "boolean"},
                    "pull": {"type": "boolean"},
                    "push": {"type": "boolean"},
                },
                "required": ["admin", "pull", "push"],
            },
            "owner": {"$ref": "#/$defs/simple-user"},
            "private": {"type": "boolean", "default": False},
            "html_url": {"type": "string", "format": "uri"},
            "description": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "fork": {"type": "boolean"},
            "url": {"type": "string", "format": "uri"},
            "created_at": {"type": "string", "format": "date-time"},
            "updated_at": {"type": "string", "format": "date-time"},
            "stargazers_count": {"type": "integer"},
            "language": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "topics": {"type": "array", "items": {"type": "string"}},
            "default_branch": {"type": "string"},
        },
        "required": [
            "id",
            "node_id",
            "name",
            "full_name",
            "owner",
            "private",
            "html_url",
            "fork",
            "url",
        ],
    }
    Model = create_model(schema)

    inst = Model(
        id=1296269,
        node_id="MDEwOlJlcG9zaXRvcnkxMjk2MjY5",
        name="Hello-World",
        full_name="octocat/Hello-World",
        owner={
            "login": "octocat",
            "id": 1,
            "type": "User",
            "site_admin": False,
        },
        private=False,
        html_url="https://github.com/octocat/Hello-World",
        description="This is your first repo!",
        fork=False,
        url="https://api.github.com/repos/octocat/Hello-World",
        created_at="2011-01-26T19:01:12Z",
        updated_at="2025-01-01T00:00:00Z",
        stargazers_count=80,
        language="Python",
        topics=["octocat", "api", "testing"],
        default_branch="main",
        license={
            "key": "mit",
            "name": "MIT License",
            "spdx_id": "MIT",
            "node_id": "MDc6TGljZW5zZW1pdA==",
        },
        permissions={"admin": True, "push": True, "pull": True},
        forks=9,
    )
    assert inst.id == 1296269
    assert inst.name == "Hello-World"
    assert inst.owner.login == "octocat"
    assert inst.owner.id == 1
    assert inst.license.key == "mit"
    assert inst.permissions.admin is True
    assert inst.topics == ["octocat", "api", "testing"]
    assert inst.language == "Python"
    assert inst.private is False

    # Nullable description and language
    inst2 = Model(
        id=2,
        node_id="x",
        name="empty",
        full_name="u/empty",
        owner={"login": "u", "id": 2, "type": "User", "site_admin": False},
        private=True,
        html_url="https://github.com/u/empty",
        fork=True,
        url="https://api.github.com/repos/u/empty",
        description=None,
        language=None,
    )
    assert inst2.description is None
    assert inst2.language is None

    # Round-trip
    restored = Model.model_validate_json(inst.model_dump_json())
    assert restored.owner.login == "octocat"
    assert restored.license.key == "mit"
    assert restored.topics == ["octocat", "api", "testing"]

    # Missing required field
    with pytest.raises(ValidationError):
        Model(
            id=3,
            node_id="x",
            name="bad",
            full_name="u/bad",
            private=False,
            html_url="https://github.com/u/bad",
            fork=False,
            url="https://api.github.com/repos/u/bad",
            # missing owner
        )
