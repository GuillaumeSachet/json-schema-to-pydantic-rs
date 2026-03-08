"""Fast model builder using pydantic-core directly, bypassing pydantic.create_model()."""

from __future__ import annotations

from typing import Any, Dict, Optional, Type, Union

from pydantic import BaseModel
from pydantic._internal._fields import PydanticMetadata
from pydantic.fields import FieldInfo
from pydantic_core import SchemaSerializer, SchemaValidator, core_schema as cs


def _make_model(
    name: str,
    fields_schema: dict,
    fields_info: dict[str, FieldInfo],
    base_model_type: type[BaseModel] = BaseModel,
    description: str | None = None,
    json_schema_extra: dict | None = None,
    populate_by_name: bool = False,
    extra: str | None = None,
) -> type[BaseModel]:
    """Build a BaseModel subclass using pydantic-core directly."""
    # Create class without triggering ModelMetaclass processing
    namespace: dict[str, Any] = {
        "__module__": "json_schema_to_pydantic_rs._dynamic",
        "__qualname__": name,
        "__annotations__": {},
    }
    cls = type.__new__(type(base_model_type), name, (base_model_type,), namespace)

    # Build core schema
    model_fields = cs.model_fields_schema(fields_schema)
    schema = cs.model_schema(cls=cls, schema=model_fields)

    # Config
    config_kwargs: dict[str, Any] = {}
    if populate_by_name:
        config_kwargs["populate_by_name"] = True
    if extra:
        config_kwargs["extra_behavior"] = extra
    if config_kwargs:
        schema["config"] = cs.CoreConfig(**config_kwargs)

    cls.__pydantic_validator__ = SchemaValidator(schema)
    cls.__pydantic_serializer__ = SchemaSerializer(schema)
    cls.__pydantic_core_schema__ = schema
    cls.__pydantic_complete__ = True
    cls.__pydantic_fields__ = fields_info
    cls.__pydantic_computed_fields__ = {}
    cls.__pydantic_extra__ = None
    cls.__pydantic_decorators__ = base_model_type.__pydantic_decorators__
    cls.__pydantic_private__ = None
    cls.__pydantic_post_init__ = None
    cls.__pydantic_custom_init__ = False
    cls.__pydantic_generic_metadata__ = {
        "origin": None,
        "args": (),
        "parameters": (),
    }

    if description:
        cls.__doc__ = description

    if json_schema_extra:
        cls.model_config = {
            **getattr(cls, "model_config", {}),
            "json_schema_extra": json_schema_extra,
        }

    return cls


def _build_field_info(fi_dict: dict) -> FieldInfo:
    """Build a FieldInfo from the Rust-provided field info dict."""
    kwargs: dict[str, Any] = {}

    if "default" in fi_dict:
        kwargs["default"] = fi_dict["default"]

    if "description" in fi_dict:
        kwargs["description"] = fi_dict["description"]

    if "alias" in fi_dict:
        kwargs["alias"] = fi_dict["alias"]

    if "constraints" in fi_dict:
        kwargs.update(fi_dict["constraints"])

    if "json_schema_extra" in fi_dict:
        kwargs["json_schema_extra"] = dict(fi_dict["json_schema_extra"])

    return FieldInfo(**kwargs)


def build_model_from_core(
    result: dict,
    models_ns: dict[str, type] | None = None,
    base_model_type: type[BaseModel] = BaseModel,
    populate_by_name: bool = False,
    extra: str | None = None,
) -> type[BaseModel]:
    """Build a Pydantic model from the output of process_json_schema_core()."""
    if models_ns is None:
        models_ns = {}

    kind = result.get("_kind")

    if kind == "model":
        return _build_model_result(
            result, models_ns, base_model_type, populate_by_name, extra
        )

    if kind == "discriminated_union":
        return _build_discriminated_union_result(result, models_ns, populate_by_name)

    if kind == "root_array":
        return _build_root_array_result(result, models_ns)

    if kind == "root_scalar":
        return _build_root_scalar_result(result, models_ns)

    # For union/literal/scalar types that come back as plain core schema dicts,
    # fall back to the legacy builder
    from ._builder import resolve_python_type
    return resolve_python_type(result, models_ns)


def _resolve_nested_fields(
    fields_dict: dict,
    fields_info_dict: dict,
    models_ns: dict[str, type],
    populate_by_name: bool = False,
) -> tuple[dict, dict[str, FieldInfo]]:
    """Process fields, recursively building nested models.

    Returns (core_fields_schema, pydantic_fields_info).
    """
    core_fields: dict = {}
    py_fields_info: dict[str, FieldInfo] = {}

    for field_name, field_schema in fields_dict.items():
        fi_data = fields_info_dict.get(field_name, {})

        # Check if the inner schema contains a nested model
        resolved_field = _resolve_field_schema(
            field_schema, models_ns, populate_by_name
        )
        core_fields[field_name] = resolved_field
        py_fields_info[field_name] = _build_field_info(fi_data)

    return core_fields, py_fields_info


def _resolve_field_schema(
    field_schema: dict,
    models_ns: dict[str, type],
    populate_by_name: bool = False,
) -> dict:
    """Resolve a field schema, building nested models as needed."""
    schema_type = field_schema.get("type")

    if schema_type == "model-field":
        inner = field_schema.get("schema", {})
        resolved_inner = _resolve_inner_schema(inner, models_ns, populate_by_name)
        result = dict(field_schema)
        result["schema"] = resolved_inner
        return result

    return field_schema


def _resolve_inner_schema(
    schema: dict,
    models_ns: dict[str, type],
    populate_by_name: bool = False,
) -> dict:
    """Resolve an inner schema that might contain nested models."""
    if not isinstance(schema, dict):
        return schema

    kind = schema.get("_kind")

    if kind == "model":
        # Nested model - build it
        model = _build_model_result(schema, models_ns, BaseModel, populate_by_name)
        # Return a model schema referencing the built class
        model_fields_schema = cs.model_fields_schema(
            {fname: fschema for fname, fschema in schema.get("_fields", {}).items()
             if not isinstance(fschema, dict) or fschema.get("_kind") is None}
        )
        return cs.model_schema(cls=model, schema=model_fields_schema)

    if kind == "discriminated_union":
        model = _build_discriminated_union_result(schema, models_ns, populate_by_name)
        # Return a simple model schema wrapping the union
        inner = cs.model_fields_schema({})
        return cs.model_schema(cls=model, schema=inner)

    schema_type = schema.get("type")

    # Handle default wrapper
    if schema_type == "default":
        inner = schema.get("schema", {})
        resolved = _resolve_inner_schema(inner, models_ns, populate_by_name)
        result = dict(schema)
        result["schema"] = resolved
        return result

    # Handle nullable wrapper
    if schema_type == "nullable":
        inner = schema.get("schema", {})
        resolved = _resolve_inner_schema(inner, models_ns, populate_by_name)
        result = dict(schema)
        result["schema"] = resolved
        return result

    # Handle list/set
    if schema_type in ("list", "set"):
        items = schema.get("items_schema", {})
        resolved = _resolve_inner_schema(items, models_ns, populate_by_name)
        result = dict(schema)
        result["items_schema"] = resolved
        return result

    # Handle union
    if schema_type == "union":
        choices = schema.get("choices", [])
        resolved_choices = [
            _resolve_inner_schema(c, models_ns, populate_by_name) for c in choices
        ]
        result = dict(schema)
        result["choices"] = resolved_choices
        return result

    return schema


def _build_model_result(
    result: dict,
    models_ns: dict[str, type],
    base_model_type: type[BaseModel] = BaseModel,
    populate_by_name: bool = False,
    extra: str | None = None,
) -> type[BaseModel]:
    """Build a model from a _kind=model result dict."""
    name = result["_model_name"]

    # Check if already built (avoid rebuilding for reused models)
    if name != "DynamicModel" and name in models_ns:
        existing = models_ns[name]
        if isinstance(existing, type) and issubclass(existing, BaseModel):
            return existing

    fields_dict = result.get("_fields", {})
    fields_info_dict = result.get("_fields_info", {})
    description = result.get("_description")
    json_extra = result.get("_json_schema_extra")

    # Recursively resolve nested models in fields
    core_fields, py_fields_info = _resolve_nested_fields(
        fields_dict, fields_info_dict, models_ns, populate_by_name
    )

    model = _make_model(
        name=name,
        fields_schema=core_fields,
        fields_info=py_fields_info,
        base_model_type=base_model_type,
        description=description,
        json_schema_extra=dict(json_extra) if json_extra else None,
        populate_by_name=populate_by_name,
        extra=extra,
    )

    models_ns[name] = model
    return model


def _build_discriminated_union_result(
    result: dict,
    models_ns: dict[str, type],
    populate_by_name: bool = False,
) -> type:
    """Build a discriminated union from _kind=discriminated_union result."""
    from typing import Annotated

    from pydantic import Discriminator, RootModel

    disc_field = result["_discriminator_field"]
    variants = result.get("_variants", [])

    variant_models = {}
    for v in variants:
        model_name = v["model_name"]
        disc_value = v["discriminator_value"]
        fields = v.get("fields", {})
        fields_info = v.get("fields_info", {})

        core_fields, py_fi = _resolve_nested_fields(
            fields, fields_info, models_ns, populate_by_name
        )

        model = _make_model(
            name=model_name,
            fields_schema=core_fields,
            fields_info=py_fi,
            populate_by_name=populate_by_name,
            extra="forbid",
        )
        models_ns[model_name] = model
        variant_models[disc_value] = model

    if len(variant_models) == 1:
        return RootModel[list(variant_models.values())[0]]

    union_type = Annotated[
        Union[tuple(variant_models.values())],
        Discriminator(discriminator=disc_field),
    ]
    return RootModel[union_type]


def _build_root_array_result(
    result: dict,
    models_ns: dict[str, type],
) -> type:
    """Build a RootModel for root_array results."""
    from typing import List, Set

    from pydantic import RootModel

    name = result.get("_name", "DynamicModel")
    description = result.get("_description")
    inner_schema = result.get("_schema", {})
    json_extra = result.get("_json_schema_extra")

    # Resolve any nested models inside the array items
    resolved = _resolve_inner_schema(inner_schema, models_ns)

    namespace: dict[str, Any] = {}
    if description:
        namespace["__doc__"] = description
    if json_extra:
        namespace["model_config"] = {"json_schema_extra": dict(json_extra)}

    # Use the schema type to determine list vs set
    is_set = inner_schema.get("type") == "set"
    # We still need a Python type for RootModel
    # Use Any as placeholder - the core schema handles validation
    if is_set:
        namespace["__annotations__"] = {"root": Set}
    else:
        namespace["__annotations__"] = {"root": List}

    return type(name, (RootModel[list],), namespace)


def _build_root_scalar_result(
    result: dict,
    models_ns: dict[str, type],
) -> type:
    """Build a RootModel for root_scalar results."""
    from pydantic import RootModel

    name = result.get("_name", "DynamicModel")
    description = result.get("_description")
    inner_schema = result.get("_schema", {})
    json_extra = result.get("_json_schema_extra")

    namespace: dict[str, Any] = {}
    if description:
        namespace["__doc__"] = description
    if json_extra:
        namespace["model_config"] = {"json_schema_extra": dict(json_extra)}

    # Map core schema type to Python type for RootModel
    _type_map = {
        "str": str, "int": int, "float": float, "bool": bool,
        "none": type(None), "dict": dict, "any": Any,
        "datetime": str, "date": str, "time": str, "url": str, "uuid": str,
    }
    py_type = _type_map.get(inner_schema.get("type", "any"), Any)

    namespace["__annotations__"] = {"root": py_type}
    return type(name, (RootModel[py_type],), namespace)
