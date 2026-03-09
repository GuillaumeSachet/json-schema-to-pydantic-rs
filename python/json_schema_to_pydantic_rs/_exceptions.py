class SchemaError(Exception):
    """Raised when a JSON Schema is structurally invalid or cannot be processed."""


class TypeError(SchemaError):
    """Raised when a schema contains an invalid or unsupported type value."""


class CombinerError(SchemaError):
    """Raised when a schema combiner (allOf, anyOf, oneOf) cannot be resolved."""


class ReferenceError(SchemaError):
    """Raised when a ``$ref`` pointer cannot be resolved or contains a cycle."""
