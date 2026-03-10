"""Fast model builder using pydantic-core directly, bypassing pydantic.create_model()."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Any, List, Literal, Optional, Set, Union
from uuid import UUID

import annotated_types
from pydantic import AnyUrl, BaseModel, Discriminator, RootModel
from pydantic._internal._fields import _general_metadata_cls
from pydantic.fields import FieldInfo
from pydantic_core import (
    PydanticUndefined,
    SchemaSerializer,
    SchemaValidator,
    core_schema as cs,
)

_PydanticGeneralMetadata = _general_metadata_cls()

_NoneType = type(None)

# Map core schema type strings to Python types
_CORE_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "none": _NoneType,
    "any": Any,
    "dict": dict,
    "datetime": datetime,
    "date": date,
    "time": time,
    "uuid": UUID,
    "url": AnyUrl,
}

# Map constraint names to annotated_types metadata constructors
_CONSTRAINT_BUILDERS: dict[str, Any] = {
    "gt": annotated_types.Gt,
    "ge": annotated_types.Ge,
    "lt": annotated_types.Lt,
    "le": annotated_types.Le,
    "multiple_of": annotated_types.MultipleOf,
    "min_length": annotated_types.MinLen,
    "max_length": annotated_types.MaxLen,
}

# FieldInfo slots that need defaults (pre-computed once)
_FI_DEFAULTS: dict[str, Any] = {
    "default": ...,  # PydanticUndefined equivalent — FieldInfo uses ... for required
    "default_factory": None,
    "alias": None,
    "alias_priority": None,
    "validation_alias": None,
    "serialization_alias": None,
    "title": None,
    "field_title_generator": None,
    "description": None,
    "examples": None,
    "exclude": None,
    "discriminator": None,
    "deprecated": None,
    "json_schema_extra": None,
    "frozen": None,
    "validate_default": None,
    "repr": True,
    "init": None,
    "init_var": None,
    "kw_only": None,
    "metadata": [],
    "_attributes_set": set(),
}

# Check for newer FieldInfo slots (added in later pydantic versions)
_FI_SLOTS = set(FieldInfo.__slots__) if hasattr(FieldInfo, "__slots__") else set()
_FI_EXTRA_SLOTS = {
    "exclude_if": None,
    "_qualifiers": set(),
    "_complete": True,
    "_original_assignment": None,
    "_original_annotation": None,
    "_final": False,
}


def _annotation_from_descriptor(desc: Any, models_ns: dict[str, type]) -> Any:
    """Resolve a Rust-emitted annotation descriptor to a Python type.

    Descriptors are either:
    - A string for simple types: "str", "int", "optional", etc.
    - A tuple for compound types: ("optional", inner), ("list", inner), etc.
    """
    # Fast path: simple scalar string
    if isinstance(desc, str):
        return _CORE_TYPE_MAP.get(desc, Any)

    # Compound type: tuple (tag, *args)
    if isinstance(desc, tuple) and len(desc) >= 1:
        tag = desc[0]

        if tag == "optional":
            inner = _annotation_from_descriptor(desc[1], models_ns)
            return Optional[inner]

        if tag == "list":
            inner = _annotation_from_descriptor(desc[1], models_ns)
            return List[inner]

        if tag == "set":
            inner = _annotation_from_descriptor(desc[1], models_ns)
            return Set[inner]

        if tag == "union":
            types = tuple(_annotation_from_descriptor(d, models_ns) for d in desc[1:])
            n = len(types)
            if n == 1:
                return types[0]
            non_none = [t for t in types if t is not _NoneType]
            if len(non_none) == n - 1 and len(non_none) == 1:
                return Optional[non_none[0]]
            return Union[types]

        if tag == "literal":
            values = desc[1:]
            return Literal[values] if values else Any

        if tag == "model":
            name = desc[1]
            return models_ns.get(name, Any)

        if tag == "dict_typed":
            from typing import Dict

            key_t = _annotation_from_descriptor(desc[1], models_ns)
            val_t = _annotation_from_descriptor(desc[2], models_ns)
            return Dict[key_t, val_t]

    return Any


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
    namespace: dict[str, Any] = {
        "__module__": "json_schema_to_pydantic_rs._dynamic",
        "__qualname__": name,
        "__annotations__": {},
    }
    cls = type.__new__(type(base_model_type), name, (base_model_type,), namespace)

    model_fields = cs.model_fields_schema(fields_schema)
    schema = cs.model_schema(cls=cls, schema=model_fields)

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


def _build_field_info(fi_dict: dict, annotation: Any = None) -> FieldInfo:
    """Build a FieldInfo bypassing __init__ for speed."""
    fi = FieldInfo.__new__(FieldInfo)

    # Set all defaults first
    fi.default = fi_dict.get("default", PydanticUndefined)
    fi.default_factory = None
    fi.alias = fi_dict.get("alias")
    fi.alias_priority = 2 if "alias" in fi_dict else None
    fi.validation_alias = None
    fi.serialization_alias = None
    fi.title = None
    fi.field_title_generator = None
    fi.description = fi_dict.get("description")
    fi.examples = None
    fi.exclude = None
    fi.discriminator = None
    fi.deprecated = None
    fi.frozen = None
    fi.validate_default = None
    fi.repr = True
    fi.init = None
    fi.init_var = None
    fi.kw_only = None
    fi.annotation = annotation

    # Build metadata from constraints (sorted for deterministic order)
    constraints = fi_dict.get("constraints")
    if constraints:
        metadata = []
        for key in sorted(constraints):
            val = constraints[key]
            builder = _CONSTRAINT_BUILDERS.get(key)
            if builder is not None:
                metadata.append(builder(val))
            elif key == "pattern":
                metadata.append(_PydanticGeneralMetadata({"pattern": val}))
        fi.metadata = metadata
    else:
        fi.metadata = []

    # json_schema_extra
    jse = fi_dict.get("json_schema_extra")
    fi.json_schema_extra = dict(jse) if jse else None

    # _attributes_set tracks which kwargs were explicitly passed
    attrs = set()
    if "default" in fi_dict:
        attrs.add("default")
    if "description" in fi_dict:
        attrs.add("description")
    if "alias" in fi_dict:
        attrs.add("alias")
    fi._attributes_set = attrs

    # Set extra slots that may exist in newer pydantic versions
    for slot, default in _FI_EXTRA_SLOTS.items():
        if slot in _FI_SLOTS:
            setattr(fi, slot, default)

    return fi


def build_model_from_core(
    result: dict,
    models_ns: dict[str, type] | None = None,
    base_model_type: type[BaseModel] = BaseModel,
    populate_by_name: bool = False,
    extra: str | None = None,
) -> type[BaseModel]:
    """Build a Pydantic model from ``process_json_schema_core()`` output.

    This is the fast path that constructs models using pydantic-core schemas
    directly, avoiding the overhead of ``pydantic.create_model()``.

    Args:
        result: Dict returned by Rust ``process_json_schema_core()``, keyed by
            ``_kind`` (one of ``model``, ``discriminated_union``, ``root_array``,
            ``root_scalar``).
        models_ns: Shared namespace for registering and resolving models.
        base_model_type: Base class for generated models.
        populate_by_name: Allow field access by both name and alias.
        extra: Pydantic ``extra`` config (e.g. ``"forbid"``).

    Returns:
        A new Pydantic model class.
    """
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

        resolved_field = _resolve_field_schema(
            field_schema, models_ns, populate_by_name
        )
        core_fields[field_name] = resolved_field

        # Use Rust-emitted annotation descriptor (fast path)
        ann_desc = fi_data.get("_annotation")
        if ann_desc is not None:
            annotation = _annotation_from_descriptor(ann_desc, models_ns)
        else:
            annotation = Any
        py_fields_info[field_name] = _build_field_info(fi_data, annotation)

    return core_fields, py_fields_info


def _resolve_field_schema(
    field_schema: dict,
    models_ns: dict[str, type],
    populate_by_name: bool = False,
) -> dict:
    """Resolve a field schema, building nested models as needed."""
    if field_schema.get("type") != "model-field":
        return field_schema

    inner = field_schema.get("schema", {})
    resolved_inner = _resolve_inner_schema(inner, models_ns, populate_by_name)
    if resolved_inner is inner:
        return field_schema
    # Mutate in place — these dicts are per-call from Rust and not reused
    field_schema["schema"] = resolved_inner
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
        model = _build_model_result(schema, models_ns, BaseModel, populate_by_name)
        model_fields_schema = cs.model_fields_schema(
            {
                fname: fschema
                for fname, fschema in schema.get("_fields", {}).items()
                if not isinstance(fschema, dict) or fschema.get("_kind") is None
            }
        )
        return cs.model_schema(cls=model, schema=model_fields_schema)

    if kind == "discriminated_union":
        model = _build_discriminated_union_result(schema, models_ns, populate_by_name)
        inner = cs.model_fields_schema({})
        return cs.model_schema(cls=model, schema=inner)

    schema_type = schema.get("type")

    # Handle default wrapper
    if schema_type == "default":
        inner = schema.get("schema", {})
        resolved = _resolve_inner_schema(inner, models_ns, populate_by_name)
        if resolved is not inner:
            schema["schema"] = resolved
        return schema

    # Handle nullable wrapper
    if schema_type == "nullable":
        inner = schema.get("schema", {})
        resolved = _resolve_inner_schema(inner, models_ns, populate_by_name)
        if resolved is not inner:
            schema["schema"] = resolved
        return schema

    # Handle list/set
    if schema_type == "list" or schema_type == "set":
        items = schema.get("items_schema", {})
        resolved = _resolve_inner_schema(items, models_ns, populate_by_name)
        if resolved is not items:
            schema["items_schema"] = resolved
        return schema

    # Handle union
    if schema_type == "union":
        choices = schema.get("choices", [])
        resolved_choices = [
            _resolve_inner_schema(c, models_ns, populate_by_name) for c in choices
        ]
        schema["choices"] = resolved_choices
        return schema

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
    name = result.get("_name", "DynamicModel")
    description = result.get("_description")
    inner_schema = result.get("_schema", {})
    json_extra = result.get("_json_schema_extra")

    inner_schema = _resolve_inner_schema(inner_schema, models_ns)

    namespace: dict[str, Any] = {}
    if description:
        namespace["__doc__"] = description
    if json_extra:
        namespace["model_config"] = {"json_schema_extra": dict(json_extra)}

    is_set = inner_schema.get("type") == "set"
    if is_set:
        namespace["__annotations__"] = {"root": Set}
    else:
        namespace["__annotations__"] = {"root": List}

    return type(name, (RootModel[list],), namespace)


_ROOT_SCALAR_TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "none": _NoneType,
    "dict": dict,
    "any": Any,
    "datetime": str,
    "date": str,
    "time": str,
    "url": str,
    "uuid": str,
}


def _build_root_scalar_result(
    result: dict,
    models_ns: dict[str, type],
) -> type:
    """Build a RootModel for root_scalar results."""
    name = result.get("_name", "DynamicModel")
    description = result.get("_description")
    inner_schema = result.get("_schema", {})
    json_extra = result.get("_json_schema_extra")

    namespace: dict[str, Any] = {}
    if description:
        namespace["__doc__"] = description
    if json_extra:
        namespace["model_config"] = {"json_schema_extra": dict(json_extra)}

    py_type = _ROOT_SCALAR_TYPE_MAP.get(inner_schema.get("type", "any"), Any)

    namespace["__annotations__"] = {"root": py_type}
    return type(name, (RootModel[py_type],), namespace)
