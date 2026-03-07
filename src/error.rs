use std::fmt;

/// Errors that can occur during schema processing.
#[derive(Debug, Clone)]
pub enum SchemaError {
    /// Base schema error
    Schema(String),
    /// Invalid or unsupported type
    Type(String),
    /// Error in schema combiners (allOf/anyOf/oneOf)
    Combiner(String),
    /// Error in schema references ($ref)
    Reference(String),
}

impl fmt::Display for SchemaError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SchemaError::Schema(msg) => write!(f, "SchemaError: {msg}"),
            SchemaError::Type(msg) => write!(f, "TypeError: {msg}"),
            SchemaError::Combiner(msg) => write!(f, "CombinerError: {msg}"),
            SchemaError::Reference(msg) => write!(f, "ReferenceError: {msg}"),
        }
    }
}

impl std::error::Error for SchemaError {}
