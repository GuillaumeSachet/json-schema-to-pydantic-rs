use serde_json::Value;
use std::collections::{HashMap, HashSet};

/// Intermediate representation of a resolved JSON schema field.
#[derive(Debug, Clone)]
pub struct FieldDef {
    pub name: String,
    pub python_type: FieldType,
    pub required: bool,
    pub default: Option<Value>,
    pub description: Option<String>,
    pub alias: Option<String>,
    pub constraints: HashMap<String, Value>,
    pub json_schema_extra: HashMap<String, Value>,
}

/// Intermediate representation of a resolved JSON schema model.
#[derive(Debug, Clone)]
pub struct ModelDef {
    pub name: String,
    pub description: Option<String>,
    pub fields: Vec<FieldDef>,
    pub json_schema_extra: HashMap<String, Value>,
}

/// Represents the Python type that a field should map to.
#[derive(Debug, Clone)]
pub enum FieldType {
    /// Simple scalar type: "str", "int", "float", "bool", "None", "Any"
    Scalar(String),
    /// Dict with optional key/value types: Dict[key_type, value_type]
    Dict {
        key_type: Box<FieldType>,
        value_type: Box<FieldType>,
    },
    /// Format-specific type: "datetime", "date", "time", "uuid", "AnyUrl"
    Format(String),
    /// Literal type with values
    Literal(Vec<Value>),
    /// List[inner]
    List(Box<FieldType>),
    /// Set[inner]
    Set(Box<FieldType>),
    /// Optional[inner]
    Optional(Box<FieldType>),
    /// Union[types...]
    Union(Vec<FieldType>),
    /// Forward reference (string name for recursive models)
    ForwardRef(String),
    /// A nested model definition that needs to be built
    NestedModel(Box<ModelDef>),
    /// allOf combiner result
    AllOfModel(Box<ModelDef>),
    /// anyOf combiner result - Union of resolved types
    AnyOf(Vec<FieldType>),
    /// oneOf with const literals
    OneOfLiteral(Vec<Value>),
    /// oneOf with discriminated union
    OneOfDiscriminated {
        discriminator_field: String,
        variants: Vec<OneOfVariant>,
    },
    /// oneOf as general union (fallback)
    OneOfUnion(Vec<FieldType>),
    /// RootModel for top-level arrays
    RootArray {
        item_type: Box<FieldType>,
        unique_items: bool,
        constraints: HashMap<String, Value>,
        name: String,
        description: Option<String>,
        json_schema_extra: HashMap<String, Value>,
    },
    /// RootModel for top-level scalars
    RootScalar {
        scalar_type: Box<FieldType>,
        constraints: HashMap<String, Value>,
        name: String,
        description: Option<String>,
        json_schema_extra: HashMap<String, Value>,
    },
}

#[derive(Debug, Clone)]
pub struct OneOfVariant {
    pub model_name: String,
    pub discriminator_value: Value,
    pub fields: Vec<FieldDef>,
}

/// Standard JSON Schema field-level properties (not json_schema_extra).
pub fn standard_field_properties() -> HashSet<&'static str> {
    [
        "type",
        "format",
        "description",
        "default",
        "title",
        "examples",
        "const",
        "enum",
        "multipleOf",
        "maximum",
        "exclusiveMaximum",
        "minimum",
        "exclusiveMinimum",
        "maxLength",
        "minLength",
        "pattern",
        "items",
        "additionalItems",
        "maxItems",
        "minItems",
        "uniqueItems",
        "properties",
        "additionalProperties",
        "required",
        "patternProperties",
        "dependencies",
        "propertyNames",
        "if",
        "then",
        "else",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "$ref",
        "$defs",
        "definitions",
    ]
    .into_iter()
    .collect()
}

/// Standard JSON Schema model-level properties (not json_schema_extra).
pub fn standard_model_properties() -> HashSet<&'static str> {
    [
        "type",
        "title",
        "description",
        "properties",
        "required",
        "additionalProperties",
        "patternProperties",
        "dependencies",
        "propertyNames",
        "if",
        "then",
        "else",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "$ref",
        "$defs",
        "definitions",
        "$schema",
        "$id",
        "$comment",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
    ]
    .into_iter()
    .collect()
}
