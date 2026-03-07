"""json-schema-to-pydantic-rs: Fast JSON Schema to Pydantic v2 model generation."""

from __future__ import annotations

import importlib.metadata
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from ._builder import build_model_from_def, resolve_python_type
from ._exceptions import CombinerError, ReferenceError, SchemaError, TypeError

try:
    __version__ = importlib.metadata.version("json-schema-to-pydantic-rs")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

T = TypeVar("T", bound=BaseModel)


class PydanticModelBuilder:
    """Creates Pydantic models from JSON Schema definitions.

    This is the main entry point for advanced usage. For simple cases,
    use the module-level ``create_model()`` function instead.
    """

    def __init__(
        self,
        base_model_type: Type[T] = BaseModel,
        predefined_models: Optional[Dict[str, Type[BaseModel]]] = None,
    ):
        self.base_model_type = base_model_type
        validated = self._validate_predefined_models(predefined_models, base_model_type)
        self._model_cache: Dict[str, Type[BaseModel]] = dict(validated)
        # Pre-populate models namespace with predefined models by their short name
        self._models_ns: Dict[str, type] = {}
        for ref_str, model_cls in validated.items():
            name = ref_str.split("/")[-1]
            self._models_ns[name] = model_cls

    @staticmethod
    def _validate_predefined_models(
        predefined_models: Optional[Dict[str, Type[BaseModel]]],
        base_model_type: type,
    ) -> Dict[str, Type[BaseModel]]:
        if predefined_models is None:
            return {}
        if not isinstance(predefined_models, dict):
            raise ValueError(
                "predefined_models must be a dict mapping local $ref strings to BaseModel subclasses"
            )

        validated: Dict[str, Type[BaseModel]] = {}
        for ref, model in predefined_models.items():
            if not isinstance(ref, str) or not ref.startswith("#/"):
                raise ValueError(
                    f"Invalid predefined model ref '{ref}'. Keys must be local JSON Pointer refs "
                    "like '#/definitions/Model'"
                )
            path = ref[2:]
            if not path or any(segment == "" for segment in path.split("/")):
                raise ValueError(
                    f"Invalid predefined model ref '{ref}'. Keys must be local JSON Pointer refs "
                    "without empty path segments, for example '#/definitions/Model'"
                )
            if not isinstance(model, type) or not issubclass(model, BaseModel):
                raise ValueError(
                    f"Invalid predefined model for ref '{ref}'. Values must be subclasses of "
                    "pydantic.BaseModel"
                )
            if not issubclass(model, base_model_type):
                raise ValueError(
                    f"Invalid predefined model for ref '{ref}'. Values must be subclasses of the "
                    f"configured base_model_type ({base_model_type.__name__})"
                )
            validated[ref] = model
        return validated

    def create_pydantic_model(
        self,
        schema: Dict[str, Any],
        root_schema: Optional[Dict[str, Any]] = None,
        allow_undefined_array_items: bool = False,
        allow_undefined_type: bool = False,
        populate_by_name: bool = False,
    ) -> Type[T]:
        """Create a Pydantic model from a JSON Schema definition.

        Args:
            schema: The JSON Schema to convert.
            root_schema: Root schema for $ref resolution. Defaults to ``schema``.
            allow_undefined_array_items: Allow arrays without ``items``.
            allow_undefined_type: Allow schemas without explicit ``type``.
            populate_by_name: Allow field access by both name and alias.

        Returns:
            A Pydantic model class.
        """
        from ._core import process_json_schema

        if root_schema is None:
            root_schema = schema

        # Check for $ref that maps to a predefined model
        ref_str = schema.get("$ref")
        if ref_str and ref_str in self._model_cache:
            return self._model_cache[ref_str]

        # Process through Rust core
        resolved = process_json_schema(
            schema,
            root_schema,
            allow_undefined_array_items,
            allow_undefined_type,
            populate_by_name,
        )

        # Build the Pydantic model from the resolved type description
        kind = resolved["kind"]

        if kind == "nested_model":
            model = build_model_from_def(
                resolved["model"],
                self._models_ns,
                populate_by_name=populate_by_name,
                base_model_type=self.base_model_type,
            )
        elif kind == "all_of_model":
            model = build_model_from_def(
                resolved["model"],
                self._models_ns,
                extra="forbid",
                populate_by_name=populate_by_name,
                base_model_type=self.base_model_type,
            )
        elif kind == "one_of_discriminated":
            from ._builder import build_discriminated_union

            model = build_discriminated_union(
                resolved, self._models_ns, populate_by_name=populate_by_name
            )
        elif kind in ("any_of", "one_of_union"):
            # Returns a Union type, not a model - wrap for consistency
            py_type = resolve_python_type(resolved, self._models_ns)
            return py_type
        elif kind == "one_of_literal":
            py_type = resolve_python_type(resolved, self._models_ns)
            return py_type
        elif kind in ("root_array", "root_scalar"):
            py_type = resolve_python_type(resolved, self._models_ns)
            return py_type
        else:
            py_type = resolve_python_type(resolved, self._models_ns)
            return py_type

        # Cache if this was a $ref
        if ref_str:
            self._model_cache[ref_str] = model

        # Rebuild models to resolve forward references
        if self._models_ns:
            for m in self._models_ns.values():
                if hasattr(m, "model_rebuild"):
                    try:
                        m.model_rebuild(_types_namespace=self._models_ns)
                    except Exception:
                        pass

        return model


def create_model(
    schema: Dict[str, Any],
    base_model_type: Type[T] = BaseModel,
    root_schema: Optional[Dict[str, Any]] = None,
    allow_undefined_array_items: bool = False,
    allow_undefined_type: bool = False,
    populate_by_name: bool = False,
    predefined_models: Optional[Dict[str, Type[BaseModel]]] = None,
) -> Type[T]:
    """Create a Pydantic model from a JSON Schema.

    This is the main convenience function. For advanced usage with model
    caching and predefined models, use :class:`PydanticModelBuilder` directly.

    Args:
        schema: The JSON Schema to convert.
        base_model_type: Base Pydantic model type. Defaults to ``BaseModel``.
        root_schema: Root schema for $ref resolution.
        allow_undefined_array_items: Allow arrays without ``items``.
        allow_undefined_type: Allow schemas without explicit ``type``.
        populate_by_name: Allow field access by both name and alias.
        predefined_models: Mapping of ``$ref`` strings to existing model classes.

    Returns:
        A Pydantic model class.

    Raises:
        SchemaError: If the schema is invalid.
        TypeError: If an unsupported type is encountered.
        CombinerError: If there's an error in schema combiners.
        ReferenceError: If there's an error resolving references.
    """
    builder = PydanticModelBuilder(
        base_model_type=base_model_type,
        predefined_models=predefined_models,
    )
    return builder.create_pydantic_model(
        schema,
        root_schema,
        allow_undefined_array_items,
        allow_undefined_type,
        populate_by_name,
    )


__all__ = [
    "create_model",
    "PydanticModelBuilder",
    "SchemaError",
    "TypeError",
    "CombinerError",
    "ReferenceError",
]
