"""Python layer that takes Rust-processed schema output and builds Pydantic models."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Any, Dict, List, Literal, Optional, Set, Union
from uuid import UUID

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    RootModel,
    create_model,
)


# Type mapping for scalar types
_SCALAR_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "None": type(None),
    "dict": dict,
    "Any": Any,
}

# Type mapping for format types
_FORMAT_TYPE_MAP: dict[str, type] = {
    "datetime": datetime,
    "date": date,
    "time": time,
    "uuid": UUID,
    "AnyUrl": AnyUrl,
}


def _is_already_optional(tp: Any) -> bool:
    """Return True if *tp* is already Optional (i.e. Union[..., None])."""
    import typing

    origin = getattr(tp, "__origin__", None)
    if origin is Union:
        return type(None) in typing.get_args(tp)
    return False


def resolve_python_type(
    type_desc: dict, models_ns: dict[str, type] | None = None
) -> Any:
    """Convert a Rust type-description dict into a Python type annotation.

    Args:
        type_desc: Dictionary produced by the Rust ``process_json_schema()`` call,
            describing a type via its ``kind`` key.
        models_ns: Shared namespace of already-built models, used to resolve
            forward references and reuse named models.

    Returns:
        A Python type suitable for use as a Pydantic field annotation.
    """
    kind = type_desc["kind"]

    if kind == "scalar":
        return _SCALAR_TYPE_MAP.get(type_desc["name"], str)

    if kind == "format":
        return _FORMAT_TYPE_MAP.get(type_desc["name"], str)

    if kind == "literal":
        values = tuple(type_desc["values"])
        return Literal[values]

    if kind == "list":
        inner = resolve_python_type(type_desc["inner"], models_ns)
        return List[inner]

    if kind == "set":
        inner = resolve_python_type(type_desc["inner"], models_ns)
        return Set[inner]

    if kind == "optional":
        inner = resolve_python_type(type_desc["inner"], models_ns)
        return Optional[inner]

    if kind == "union":
        types = tuple(resolve_python_type(t, models_ns) for t in type_desc["types"])
        return Union[types]

    if kind == "model":
        name = type_desc["name"]
        if models_ns and name in models_ns:
            return models_ns[name]
        return name  # forward reference string

    if kind == "dict":
        key_t = resolve_python_type(type_desc["key_type"], models_ns)
        val_t = resolve_python_type(type_desc["value_type"], models_ns)
        return Dict[key_t, val_t]

    if kind == "forward_ref":
        return type_desc["name"]

    if kind == "nested_model":
        model_name = type_desc["model"]["name"]
        # Only reuse if this is a named model (not generic "DynamicModel")
        if models_ns and model_name != "DynamicModel" and model_name in models_ns:
            return models_ns[model_name]
        return build_model_from_def(type_desc["model"], models_ns)

    if kind == "all_of_model":
        return build_model_from_def(type_desc["model"], models_ns, extra="forbid")

    if kind in ("any_of", "one_of_union"):
        types = tuple(resolve_python_type(t, models_ns) for t in type_desc["types"])
        return Union[types]

    if kind == "one_of_literal":
        values = tuple(type_desc["values"])
        return Literal[values]

    if kind == "one_of_discriminated":
        return build_discriminated_union(type_desc, models_ns)

    if kind == "root_array":
        return build_root_array(type_desc, models_ns)

    if kind == "root_scalar":
        return build_root_scalar(type_desc, models_ns)

    return Any


def build_field_info(field_def: dict) -> Field:
    """Build a Pydantic ``Field`` from a Rust field-definition dict."""
    kwargs: dict[str, Any] = {}

    # Add constraints
    constraints = field_def.get("constraints", {})
    if constraints:
        kwargs.update(constraints)

    # Description
    if field_def.get("description") is not None:
        kwargs["description"] = field_def["description"]

    # Default
    default = field_def.get("default")
    if default is not None or not field_def.get("required", True):
        kwargs["default"] = default

    # Alias
    if field_def.get("alias") is not None:
        kwargs["alias"] = field_def["alias"]

    # json_schema_extra
    extra = field_def.get("json_schema_extra", {})
    if extra:
        kwargs["json_schema_extra"] = dict(extra)

    return Field(**kwargs)


def build_model_from_def(
    model_def: dict,
    models_ns: dict[str, type] | None = None,
    extra: str | None = None,
    populate_by_name: bool = False,
    base_model_type: type[BaseModel] = BaseModel,
    json_schema_extra_override: dict | None = None,
) -> type[BaseModel]:
    """Build a Pydantic model class from a Rust ``ModelDef`` dict.

    Args:
        model_def: Model definition dict with ``name``, ``fields``, etc.
        models_ns: Shared namespace for registering built models.
        extra: Pydantic ``extra`` config (e.g. ``"forbid"``).
        populate_by_name: Allow field access by both name and alias.
        base_model_type: Base class for the generated model.
        json_schema_extra_override: Override for ``json_schema_extra`` config.

    Returns:
        A new Pydantic model class.
    """
    if models_ns is None:
        models_ns = {}

    name = model_def["name"]
    description = model_def.get("description")
    model_extra = json_schema_extra_override or model_def.get("json_schema_extra", {})

    fields: dict[str, tuple] = {}
    for field_def in model_def.get("fields", []):
        field_type = resolve_python_type(field_def["python_type"], models_ns)
        # Wrap non-required fields that default to None in Optional so that
        # model_dump() -> model_validate() round-trips succeed.
        if (
            not field_def.get("required", True)
            and field_def.get("default") is None
            and field_type is not type(None)
            and not _is_already_optional(field_type)
        ):
            field_type = Optional[field_type]
        field_info = build_field_info(field_def)
        fields[field_def["name"]] = (field_type, field_info)

    config_kwargs: dict[str, Any] = {"populate_by_name": populate_by_name}
    if extra:
        config_kwargs["extra"] = extra

    if model_extra:

        class DynamicBase(base_model_type):
            model_config = ConfigDict(
                json_schema_extra=dict(model_extra),
                **config_kwargs,
            )

        model = create_model(name, __base__=DynamicBase, **fields)
    else:
        model = create_model(
            name,
            __base__=base_model_type,
            __config__=ConfigDict(**config_kwargs),
            **fields,
        )

    if description:
        model.__doc__ = description

    # Register in namespace for forward references
    models_ns[name] = model

    return model


def build_discriminated_union(
    type_desc: dict,
    models_ns: dict[str, type] | None = None,
    populate_by_name: bool = False,
) -> type[RootModel]:
    """Build a discriminated-union ``RootModel`` from a oneOf schema.

    Args:
        type_desc: Type description dict with ``discriminator_field`` and ``variants``.
        models_ns: Shared namespace for registering variant models.
        populate_by_name: Allow field access by both name and alias.

    Returns:
        A ``RootModel`` parameterized with the discriminated union type.
    """
    if models_ns is None:
        models_ns = {}

    disc_field = type_desc["discriminator_field"]
    variants = type_desc["variants"]
    variant_models = {}

    for variant in variants:
        model_name = variant["model_name"]
        disc_value = variant["discriminator_value"]

        fields: dict[str, tuple] = {}
        for field_def in variant["fields"]:
            field_type = resolve_python_type(field_def["python_type"], models_ns)
            field_info = build_field_info(field_def)
            fields[field_def["name"]] = (field_type, field_info)

        variant_model = create_model(
            model_name,
            __config__=ConfigDict(extra="forbid", populate_by_name=populate_by_name),
            **fields,
        )
        variant_models[disc_value] = variant_model
        models_ns[model_name] = variant_model

    if len(variant_models) == 1:
        return RootModel[list(variant_models.values())[0]]

    union_type = Annotated[
        Union[tuple(variant_models.values())],
        Discriminator(discriminator=disc_field),
    ]
    return RootModel[union_type]


def build_root_array(
    type_desc: dict,
    models_ns: dict[str, type] | None = None,
) -> type[RootModel]:
    """Build a ``RootModel`` for a top-level array schema."""
    item_type = resolve_python_type(type_desc["item_type"], models_ns)
    unique = type_desc.get("unique_items", False)
    constraints = type_desc.get("constraints", {})
    name = type_desc.get("name", "DynamicModel")
    description = type_desc.get("description")
    model_extra = type_desc.get("json_schema_extra", {})

    array_type = Set[item_type] if unique else List[item_type]

    namespace: dict[str, Any] = {}
    if description:
        namespace["__doc__"] = description
    if model_extra:
        namespace["model_config"] = ConfigDict(json_schema_extra=dict(model_extra))

    if constraints:
        root_type = Annotated[array_type, Field(**constraints)]
    else:
        root_type = array_type

    namespace["__annotations__"] = {"root": root_type}

    return type(name, (RootModel[array_type],), namespace)


def build_root_scalar(
    type_desc: dict,
    models_ns: dict[str, type] | None = None,
) -> type[RootModel]:
    """Build a ``RootModel`` for a top-level scalar schema."""
    scalar_type = resolve_python_type(type_desc["scalar_type"], models_ns)
    constraints = type_desc.get("constraints", {})
    name = type_desc.get("name", "DynamicModel")
    description = type_desc.get("description")
    model_extra = type_desc.get("json_schema_extra", {})

    namespace: dict[str, Any] = {}
    if description:
        namespace["__doc__"] = description
    if model_extra:
        namespace["model_config"] = ConfigDict(json_schema_extra=dict(model_extra))

    if constraints:
        root_type = Annotated[scalar_type, Field(**constraints)]
    else:
        root_type = scalar_type

    namespace["__annotations__"] = {"root": root_type}

    return type(name, (RootModel[scalar_type],), namespace)
