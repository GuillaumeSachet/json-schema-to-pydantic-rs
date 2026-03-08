//! Builds pydantic-core CoreSchema dicts directly from our intermediate FieldType representation.
//!
//! Instead of returning custom dicts that Python must interpret, we produce
//! the exact dict format that `pydantic_core.SchemaValidator` expects.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde_json::Value;

use crate::schema::*;

/// Convert a serde_json::Value to a Python object.
fn value_to_py(py: Python<'_>, value: &Value) -> PyObject {
    match value {
        Value::Null => py.None(),
        Value::Bool(b) => b.into_pyobject(py).unwrap().to_owned().into_any().unbind(),
        Value::Number(n) => {
            if let Some(i) = n.as_i64() {
                i.into_pyobject(py).unwrap().into_any().unbind()
            } else if let Some(f) = n.as_f64() {
                f.into_pyobject(py).unwrap().into_any().unbind()
            } else {
                py.None()
            }
        }
        Value::String(s) => s.into_pyobject(py).unwrap().into_any().unbind(),
        Value::Array(arr) => {
            let list = PyList::empty(py);
            for v in arr {
                list.append(value_to_py(py, v)).unwrap();
            }
            list.into_any().unbind()
        }
        Value::Object(obj) => {
            let dict = PyDict::new(py);
            for (k, v) in obj {
                dict.set_item(k, value_to_py(py, v)).unwrap();
            }
            dict.into_any().unbind()
        }
    }
}

/// Build a pydantic-core schema dict for a FieldType.
pub fn field_type_to_core_schema<'py>(
    py: Python<'py>,
    ft: &FieldType,
) -> PyObject {
    match ft {
        FieldType::Scalar(name) => scalar_schema(py, name),
        FieldType::Dict { key_type, value_type } => {
            let d = PyDict::new(py);
            d.set_item("type", "dict").unwrap();
            d.set_item("keys_schema", field_type_to_core_schema(py, key_type)).unwrap();
            d.set_item("values_schema", field_type_to_core_schema(py, value_type)).unwrap();
            d.into_any().unbind()
        }
        FieldType::Format(name) => format_schema(py, name),
        FieldType::Literal(values) => literal_schema(py, values),
        FieldType::List(inner) => {
            let d = PyDict::new(py);
            d.set_item("type", "list").unwrap();
            d.set_item("items_schema", field_type_to_core_schema(py, inner)).unwrap();
            d.into_any().unbind()
        }
        FieldType::Set(inner) => {
            let d = PyDict::new(py);
            d.set_item("type", "set").unwrap();
            d.set_item("items_schema", field_type_to_core_schema(py, inner)).unwrap();
            d.into_any().unbind()
        }
        FieldType::Optional(inner) => {
            let d = PyDict::new(py);
            d.set_item("type", "nullable").unwrap();
            d.set_item("schema", field_type_to_core_schema(py, inner)).unwrap();
            d.into_any().unbind()
        }
        FieldType::Union(types) => union_schema(py, types),
        FieldType::ForwardRef(name) => {
            // Return a string type as placeholder for forward refs
            let d = PyDict::new(py);
            d.set_item("type", "str").unwrap();
            // Store the ref name as metadata for the Python layer to handle
            let meta = PyDict::new(py);
            meta.set_item("forward_ref", name.as_str()).unwrap();
            d.set_item("metadata", meta).unwrap();
            d.into_any().unbind()
        }
        FieldType::NestedModel(model_def) => {
            model_def_to_core_schema(py, model_def)
        }
        FieldType::AllOfModel(model_def) => {
            model_def_to_core_schema(py, model_def)
        }
        FieldType::AnyOf(types) | FieldType::OneOfUnion(types) => union_schema(py, types),
        FieldType::OneOfLiteral(values) => literal_schema(py, values),
        FieldType::OneOfDiscriminated { discriminator_field, variants } => {
            discriminated_union_schema(py, discriminator_field, variants)
        }
        FieldType::RootArray { item_type, unique_items, constraints, name, description, json_schema_extra } => {
            root_array_schema(py, item_type, *unique_items, constraints, name, description.as_deref(), json_schema_extra)
        }
        FieldType::RootScalar { scalar_type, constraints, name, description, json_schema_extra } => {
            root_scalar_schema(py, scalar_type, constraints, name, description.as_deref(), json_schema_extra)
        }
    }
}

fn scalar_schema(py: Python<'_>, name: &str) -> PyObject {
    let d = PyDict::new(py);
    match name {
        "str" => d.set_item("type", "str").unwrap(),
        "int" => d.set_item("type", "int").unwrap(),
        "float" => d.set_item("type", "float").unwrap(),
        "bool" => d.set_item("type", "bool").unwrap(),
        "None" => d.set_item("type", "none").unwrap(),
        "dict" => d.set_item("type", "dict").unwrap(),
        "Any" => d.set_item("type", "any").unwrap(),
        _ => d.set_item("type", "str").unwrap(),
    };
    d.into_any().unbind()
}

fn format_schema(py: Python<'_>, name: &str) -> PyObject {
    let d = PyDict::new(py);
    match name {
        "datetime" => d.set_item("type", "datetime").unwrap(),
        "date" => d.set_item("type", "date").unwrap(),
        "time" => d.set_item("type", "time").unwrap(),
        "uuid" => d.set_item("type", "uuid").unwrap(),
        "AnyUrl" => d.set_item("type", "url").unwrap(),
        _ => d.set_item("type", "str").unwrap(),
    };
    d.into_any().unbind()
}

fn literal_schema(py: Python<'_>, values: &[Value]) -> PyObject {
    let d = PyDict::new(py);
    d.set_item("type", "literal").unwrap();
    let expected = PyList::empty(py);
    for v in values {
        expected.append(value_to_py(py, v)).unwrap();
    }
    d.set_item("expected", expected).unwrap();
    d.into_any().unbind()
}

fn union_schema(py: Python<'_>, types: &[FieldType]) -> PyObject {
    let d = PyDict::new(py);
    d.set_item("type", "union").unwrap();
    let choices = PyList::empty(py);
    for t in types {
        choices.append(field_type_to_core_schema(py, t)).unwrap();
    }
    d.set_item("choices", choices).unwrap();
    d.into_any().unbind()
}

/// Build a model-fields + model core schema from a ModelDef.
/// Returns a dict with keys: _model_schema, _fields_info, _model_name, _description, _json_schema_extra
/// The Python layer will use this to construct the class and validators.
pub fn model_def_to_core_schema(py: Python<'_>, model: &ModelDef) -> PyObject {
    let result = PyDict::new(py);
    result.set_item("_kind", "model").unwrap();
    result.set_item("_model_name", model.name.as_str()).unwrap();

    if let Some(ref desc) = model.description {
        result.set_item("_description", desc.as_str()).unwrap();
    }

    // Build the fields dict for model_fields_schema
    let fields = PyDict::new(py);
    let fields_info = PyDict::new(py);

    for field in &model.fields {
        let field_core = build_field_core_schema(py, field);
        let field_dict = PyDict::new(py);
        field_dict.set_item("type", "model-field").unwrap();
        field_dict.set_item("schema", field_core).unwrap();

        // Validation alias
        if let Some(ref alias) = field.alias {
            field_dict.set_item("validation_alias", alias.as_str()).unwrap();
        }

        fields.set_item(field.name.as_str(), field_dict).unwrap();

        // Build FieldInfo metadata for the Python layer
        let fi = PyDict::new(py);
        fi.set_item("required", field.required).unwrap();
        if let Some(ref default) = field.default {
            fi.set_item("default", value_to_py(py, default)).unwrap();
        }
        if let Some(ref desc) = field.description {
            fi.set_item("description", desc.as_str()).unwrap();
        }
        if let Some(ref alias) = field.alias {
            fi.set_item("alias", alias.as_str()).unwrap();
        }
        if !field.constraints.is_empty() {
            let c = PyDict::new(py);
            for (k, v) in &field.constraints {
                c.set_item(k.as_str(), value_to_py(py, v)).unwrap();
            }
            fi.set_item("constraints", c).unwrap();
        }
        if !field.json_schema_extra.is_empty() {
            let extra = PyDict::new(py);
            for (k, v) in &field.json_schema_extra {
                extra.set_item(k.as_str(), value_to_py(py, v)).unwrap();
            }
            fi.set_item("json_schema_extra", extra).unwrap();
        }
        fields_info.set_item(field.name.as_str(), fi).unwrap();
    }

    result.set_item("_fields", fields).unwrap();
    result.set_item("_fields_info", fields_info).unwrap();

    if !model.json_schema_extra.is_empty() {
        let extra = PyDict::new(py);
        for (k, v) in &model.json_schema_extra {
            extra.set_item(k.as_str(), value_to_py(py, v)).unwrap();
        }
        result.set_item("_json_schema_extra", extra).unwrap();
    }

    result.into_any().unbind()
}

/// Build a core schema for a single field, applying constraints and wrapping with defaults.
fn build_field_core_schema(py: Python<'_>, field: &FieldDef) -> PyObject {
    let mut inner = field_type_to_core_schema(py, &field.python_type);

    // Apply constraints to the inner schema.
    // For union/anyOf types, apply constraints to each non-null choice
    // rather than the union wrapper (pydantic-core union doesn't support constraints).
    if !field.constraints.is_empty() {
        if is_union_type(&field.python_type) {
            inner = apply_constraints_to_union_choices(py, inner, &field.constraints);
        } else {
            inner = apply_constraints(py, inner, &field.constraints);
        }
    }

    // Wrap with default if needed
    if let Some(ref default) = field.default {
        // When the default is null and the type isn't already nullable,
        // wrap in nullable so that model_dump() -> model_validate() round-trips work.
        if default.is_null() && !is_already_nullable(&field.python_type) {
            let nullable = PyDict::new(py);
            nullable.set_item("type", "nullable").unwrap();
            nullable.set_item("schema", inner).unwrap();
            inner = nullable.into_any().unbind();
        }

        let wrapper = PyDict::new(py);
        wrapper.set_item("type", "default").unwrap();
        wrapper.set_item("schema", inner).unwrap();
        wrapper.set_item("default", value_to_py(py, default)).unwrap();
        return wrapper.into_any().unbind();
    }

    inner
}

/// Check if a FieldType is a union/anyOf/oneOf type.
fn is_union_type(ft: &FieldType) -> bool {
    matches!(
        ft,
        FieldType::Union(_)
            | FieldType::AnyOf(_)
            | FieldType::OneOfUnion(_)
            | FieldType::Optional(_)
    )
}

/// Apply constraints to non-null choices within a union schema dict.
fn apply_constraints_to_union_choices(
    py: Python<'_>,
    schema_obj: PyObject,
    constraints: &std::collections::HashMap<String, Value>,
) -> PyObject {
    let bound = schema_obj.bind(py);
    if let Ok(dict) = bound.downcast::<PyDict>() {
        let schema_type = dict
            .get_item("type")
            .ok()
            .flatten()
            .and_then(|v| v.extract::<String>().ok());

        if schema_type.as_deref() == Some("union") {
            if let Ok(Some(choices)) = dict.get_item("choices") {
                if let Ok(list) = choices.downcast::<PyList>() {
                    for item in list.iter() {
                        if let Ok(choice_dict) = item.downcast::<PyDict>() {
                            let choice_type = choice_dict
                                .get_item("type")
                                .ok()
                                .flatten()
                                .and_then(|v| v.extract::<String>().ok());
                            // Skip null choices
                            if choice_type.as_deref() != Some("none") {
                                for (k, v) in constraints {
                                    choice_dict
                                        .set_item(k.as_str(), value_to_py(py, v))
                                        .unwrap();
                                }
                            }
                        }
                    }
                }
            }
        } else if schema_type.as_deref() == Some("nullable") {
            // Optional wraps as nullable -> inner schema
            if let Ok(Some(inner)) = dict.get_item("schema") {
                let inner_obj = inner.unbind();
                apply_constraints(py, inner_obj, constraints);
            }
        } else {
            // Fallback: apply directly
            return apply_constraints(py, schema_obj, constraints);
        }
    }
    schema_obj
}

/// Check if a FieldType already accepts None.
fn is_already_nullable(ft: &FieldType) -> bool {
    match ft {
        FieldType::Optional(_) => true,
        FieldType::Scalar(name) if name == "None" || name == "Any" => true,
        FieldType::Union(types) | FieldType::AnyOf(types) | FieldType::OneOfUnion(types) => {
            types.iter().any(|t| matches!(t, FieldType::Scalar(n) if n == "None"))
        }
        _ => false,
    }
}

/// Apply constraints to an existing core schema dict by merging keys into it.
fn apply_constraints(
    py: Python<'_>,
    schema_obj: PyObject,
    constraints: &std::collections::HashMap<String, Value>,
) -> PyObject {
    // Try to merge constraints directly into the schema dict
    let bound = schema_obj.bind(py);
    if let Ok(dict) = bound.downcast::<PyDict>() {
        for (k, v) in constraints {
            dict.set_item(k.as_str(), value_to_py(py, v)).unwrap();
        }
        return schema_obj;
    }
    schema_obj
}

fn discriminated_union_schema(
    py: Python<'_>,
    discriminator_field: &str,
    variants: &[OneOfVariant],
) -> PyObject {
    let result = PyDict::new(py);
    result.set_item("_kind", "discriminated_union").unwrap();
    result.set_item("_discriminator_field", discriminator_field).unwrap();

    let variants_list = PyList::empty(py);
    for v in variants {
        let vd = PyDict::new(py);
        vd.set_item("model_name", v.model_name.as_str()).unwrap();
        vd.set_item("discriminator_value", value_to_py(py, &v.discriminator_value)).unwrap();

        let fields = PyDict::new(py);
        let fields_info = PyDict::new(py);

        for field in &v.fields {
            let field_core = build_field_core_schema(py, field);
            let field_dict = PyDict::new(py);
            field_dict.set_item("type", "model-field").unwrap();
            field_dict.set_item("schema", field_core).unwrap();
            if let Some(ref alias) = field.alias {
                field_dict.set_item("validation_alias", alias.as_str()).unwrap();
            }
            fields.set_item(field.name.as_str(), field_dict).unwrap();

            let fi = PyDict::new(py);
            fi.set_item("required", field.required).unwrap();
            if let Some(ref default) = field.default {
                fi.set_item("default", value_to_py(py, default)).unwrap();
            }
            if let Some(ref desc) = field.description {
                fi.set_item("description", desc.as_str()).unwrap();
            }
            if let Some(ref alias) = field.alias {
                fi.set_item("alias", alias.as_str()).unwrap();
            }
            fields_info.set_item(field.name.as_str(), fi).unwrap();
        }

        vd.set_item("fields", fields).unwrap();
        vd.set_item("fields_info", fields_info).unwrap();
        variants_list.append(vd).unwrap();
    }

    result.set_item("_variants", variants_list).unwrap();
    result.into_any().unbind()
}

fn root_array_schema(
    py: Python<'_>,
    item_type: &FieldType,
    unique_items: bool,
    constraints: &std::collections::HashMap<String, Value>,
    name: &str,
    description: Option<&str>,
    json_schema_extra: &std::collections::HashMap<String, Value>,
) -> PyObject {
    let result = PyDict::new(py);
    result.set_item("_kind", "root_array").unwrap();
    result.set_item("_name", name).unwrap();
    if let Some(desc) = description {
        result.set_item("_description", desc).unwrap();
    }

    let inner = field_type_to_core_schema(py, item_type);
    let array_schema = PyDict::new(py);
    if unique_items {
        array_schema.set_item("type", "set").unwrap();
    } else {
        array_schema.set_item("type", "list").unwrap();
    }
    array_schema.set_item("items_schema", inner).unwrap();

    // Apply array constraints
    for (k, v) in constraints {
        array_schema.set_item(k.as_str(), value_to_py(py, v)).unwrap();
    }

    result.set_item("_schema", array_schema).unwrap();

    if !json_schema_extra.is_empty() {
        let extra = PyDict::new(py);
        for (k, v) in json_schema_extra {
            extra.set_item(k.as_str(), value_to_py(py, v)).unwrap();
        }
        result.set_item("_json_schema_extra", extra).unwrap();
    }

    result.into_any().unbind()
}

fn root_scalar_schema(
    py: Python<'_>,
    scalar_type: &FieldType,
    constraints: &std::collections::HashMap<String, Value>,
    name: &str,
    description: Option<&str>,
    json_schema_extra: &std::collections::HashMap<String, Value>,
) -> PyObject {
    let result = PyDict::new(py);
    result.set_item("_kind", "root_scalar").unwrap();
    result.set_item("_name", name).unwrap();
    if let Some(desc) = description {
        result.set_item("_description", desc).unwrap();
    }

    let inner = field_type_to_core_schema(py, scalar_type);
    // Apply constraints
    if !constraints.is_empty() {
        let bound = inner.bind(py);
        if let Ok(dict) = bound.downcast::<PyDict>() {
            for (k, v) in constraints {
                dict.set_item(k.as_str(), value_to_py(py, v)).unwrap();
            }
        }
    }
    result.set_item("_schema", inner).unwrap();

    if !json_schema_extra.is_empty() {
        let extra = PyDict::new(py);
        for (k, v) in json_schema_extra {
            extra.set_item(k.as_str(), value_to_py(py, v)).unwrap();
        }
        result.set_item("_json_schema_extra", extra).unwrap();
    }

    result.into_any().unbind()
}
