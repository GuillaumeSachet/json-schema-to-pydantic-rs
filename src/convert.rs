//! Conversion from Rust types to Python-compatible dictionaries via PyO3.
//!
//! This module converts the internal `FieldType`, `ModelDef`, etc. into Python dicts
//! that the Python layer can read to build Pydantic models.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde_json::Value;

use crate::schema::*;

/// Convert a serde_json::Value to a Python object.
pub fn value_to_py(py: Python<'_>, value: &Value) -> PyObject {
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

/// Convert a HashMap<String, Value> to a Python dict.
pub fn hashmap_to_py<'a>(
    py: Python<'a>,
    map: &std::collections::HashMap<String, Value>,
) -> Bound<'a, PyDict> {
    let dict = PyDict::new(py);
    for (k, v) in map {
        dict.set_item(k, value_to_py(py, v)).unwrap();
    }
    dict
}

/// Convert a FieldType to a Python dict describing the type.
pub fn field_type_to_py(py: Python<'_>, ft: &FieldType) -> PyObject {
    let dict = PyDict::new(py);

    match ft {
        FieldType::Scalar(name) => {
            dict.set_item("kind", "scalar").unwrap();
            dict.set_item("name", name.as_str()).unwrap();
        }
        FieldType::Format(name) => {
            dict.set_item("kind", "format").unwrap();
            dict.set_item("name", name.as_str()).unwrap();
        }
        FieldType::Literal(values) => {
            dict.set_item("kind", "literal").unwrap();
            let list = PyList::empty(py);
            for v in values {
                list.append(value_to_py(py, v)).unwrap();
            }
            dict.set_item("values", list).unwrap();
        }
        FieldType::List(inner) => {
            dict.set_item("kind", "list").unwrap();
            dict.set_item("inner", field_type_to_py(py, inner)).unwrap();
        }
        FieldType::Set(inner) => {
            dict.set_item("kind", "set").unwrap();
            dict.set_item("inner", field_type_to_py(py, inner)).unwrap();
        }
        FieldType::Optional(inner) => {
            dict.set_item("kind", "optional").unwrap();
            dict.set_item("inner", field_type_to_py(py, inner)).unwrap();
        }
        FieldType::Union(types) => {
            dict.set_item("kind", "union").unwrap();
            let list = PyList::empty(py);
            for t in types {
                list.append(field_type_to_py(py, t)).unwrap();
            }
            dict.set_item("types", list).unwrap();
        }
        FieldType::ForwardRef(name) => {
            dict.set_item("kind", "forward_ref").unwrap();
            dict.set_item("name", name.as_str()).unwrap();
        }
        FieldType::NestedModel(model_def) => {
            dict.set_item("kind", "nested_model").unwrap();
            dict.set_item("model", model_def_to_py(py, model_def))
                .unwrap();
        }
        FieldType::AllOfModel(model_def) => {
            dict.set_item("kind", "all_of_model").unwrap();
            dict.set_item("model", model_def_to_py(py, model_def))
                .unwrap();
        }
        FieldType::AnyOf(types) => {
            dict.set_item("kind", "any_of").unwrap();
            let list = PyList::empty(py);
            for t in types {
                list.append(field_type_to_py(py, t)).unwrap();
            }
            dict.set_item("types", list).unwrap();
        }
        FieldType::OneOfLiteral(values) => {
            dict.set_item("kind", "one_of_literal").unwrap();
            let list = PyList::empty(py);
            for v in values {
                list.append(value_to_py(py, v)).unwrap();
            }
            dict.set_item("values", list).unwrap();
        }
        FieldType::OneOfDiscriminated {
            discriminator_field,
            variants,
        } => {
            dict.set_item("kind", "one_of_discriminated").unwrap();
            dict.set_item("discriminator_field", discriminator_field.as_str())
                .unwrap();
            let list = PyList::empty(py);
            for v in variants {
                let vdict = PyDict::new(py);
                vdict.set_item("model_name", v.model_name.as_str()).unwrap();
                vdict
                    .set_item("discriminator_value", value_to_py(py, &v.discriminator_value))
                    .unwrap();
                let fields_list = PyList::empty(py);
                for f in &v.fields {
                    fields_list.append(field_def_to_py(py, f)).unwrap();
                }
                vdict.set_item("fields", fields_list).unwrap();
                list.append(vdict).unwrap();
            }
            dict.set_item("variants", list).unwrap();
        }
        FieldType::OneOfUnion(types) => {
            dict.set_item("kind", "one_of_union").unwrap();
            let list = PyList::empty(py);
            for t in types {
                list.append(field_type_to_py(py, t)).unwrap();
            }
            dict.set_item("types", list).unwrap();
        }
        FieldType::RootArray {
            item_type,
            unique_items,
            constraints,
            name,
            description,
            json_schema_extra,
        } => {
            dict.set_item("kind", "root_array").unwrap();
            dict.set_item("item_type", field_type_to_py(py, item_type))
                .unwrap();
            dict.set_item("unique_items", *unique_items).unwrap();
            dict.set_item("constraints", hashmap_to_py(py, constraints))
                .unwrap();
            dict.set_item("name", name.as_str()).unwrap();
            dict.set_item(
                "description",
                description.as_deref().unwrap_or(""),
            )
            .unwrap();
            if description.is_none() {
                dict.set_item("description", py.None()).unwrap();
            }
            dict.set_item("json_schema_extra", hashmap_to_py(py, json_schema_extra))
                .unwrap();
        }
        FieldType::RootScalar {
            scalar_type,
            constraints,
            name,
            description,
            json_schema_extra,
        } => {
            dict.set_item("kind", "root_scalar").unwrap();
            dict.set_item("scalar_type", field_type_to_py(py, scalar_type))
                .unwrap();
            dict.set_item("constraints", hashmap_to_py(py, constraints))
                .unwrap();
            dict.set_item("name", name.as_str()).unwrap();
            if let Some(desc) = description {
                dict.set_item("description", desc.as_str()).unwrap();
            } else {
                dict.set_item("description", py.None()).unwrap();
            }
            dict.set_item("json_schema_extra", hashmap_to_py(py, json_schema_extra))
                .unwrap();
        }
    }

    dict.into_any().unbind()
}

/// Convert a FieldDef to a Python dict.
pub fn field_def_to_py(py: Python<'_>, field: &FieldDef) -> PyObject {
    let dict = PyDict::new(py);
    dict.set_item("name", field.name.as_str()).unwrap();
    dict.set_item("python_type", field_type_to_py(py, &field.python_type))
        .unwrap();
    dict.set_item("required", field.required).unwrap();

    if let Some(ref default) = field.default {
        dict.set_item("default", value_to_py(py, default)).unwrap();
    } else {
        dict.set_item("default", py.None()).unwrap();
    }

    if let Some(ref desc) = field.description {
        dict.set_item("description", desc.as_str()).unwrap();
    } else {
        dict.set_item("description", py.None()).unwrap();
    }

    if let Some(ref alias) = field.alias {
        dict.set_item("alias", alias.as_str()).unwrap();
    } else {
        dict.set_item("alias", py.None()).unwrap();
    }

    dict.set_item("constraints", hashmap_to_py(py, &field.constraints))
        .unwrap();
    dict.set_item(
        "json_schema_extra",
        hashmap_to_py(py, &field.json_schema_extra),
    )
    .unwrap();

    dict.into_any().unbind()
}

/// Convert a ModelDef to a Python dict.
pub fn model_def_to_py(py: Python<'_>, model: &ModelDef) -> PyObject {
    let dict = PyDict::new(py);
    dict.set_item("name", model.name.as_str()).unwrap();

    if let Some(ref desc) = model.description {
        dict.set_item("description", desc.as_str()).unwrap();
    } else {
        dict.set_item("description", py.None()).unwrap();
    }

    let fields_list = PyList::empty(py);
    for f in &model.fields {
        fields_list.append(field_def_to_py(py, f)).unwrap();
    }
    dict.set_item("fields", fields_list).unwrap();

    dict.set_item(
        "json_schema_extra",
        hashmap_to_py(py, &model.json_schema_extra),
    )
    .unwrap();

    dict.into_any().unbind()
}
