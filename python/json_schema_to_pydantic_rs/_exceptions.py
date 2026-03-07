class SchemaError(Exception):
    """Base class for schema-related errors."""


class TypeError(SchemaError):
    """Invalid or unsupported type."""


class CombinerError(SchemaError):
    """Error in schema combiners."""


class ReferenceError(SchemaError):
    """Error in schema references."""
