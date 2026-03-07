mod builder;
mod constraints;
mod convert;
mod error;
mod resolver;
mod schema;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use builder::{process_schema, ProcessOptions};
use convert::field_type_to_py;

/// Process a JSON schema dict and return a resolved type description.
///
/// Args:
///     schema: The JSON schema as a Python dict.
///     root_schema: Optional root schema for $ref resolution.
///     allow_undefined_array_items: Allow arrays without 'items'.
///     allow_undefined_type: Allow schemas without explicit type.
///     populate_by_name: Allow field access by name and alias.
///
/// Returns:
///     A dict describing the resolved type structure.
#[pyfunction]
#[pyo3(signature = (schema, root_schema=None, allow_undefined_array_items=false, allow_undefined_type=false, populate_by_name=false))]
fn process_json_schema(
    py: Python<'_>,
    schema: &Bound<'_, PyDict>,
    root_schema: Option<&Bound<'_, PyDict>>,
    allow_undefined_array_items: bool,
    allow_undefined_type: bool,
    populate_by_name: bool,
) -> PyResult<PyObject> {
    // Convert Python dict to serde_json::Value
    let schema_str = py
        .import("json")?
        .call_method1("dumps", (schema,))?
        .extract::<String>()?;
    let schema_value: serde_json::Value =
        serde_json::from_str(&schema_str).map_err(|e| PyValueError::new_err(e.to_string()))?;

    let root_value = if let Some(root) = root_schema {
        let root_str = py
            .import("json")?
            .call_method1("dumps", (root,))?
            .extract::<String>()?;
        Some(
            serde_json::from_str::<serde_json::Value>(&root_str)
                .map_err(|e| PyValueError::new_err(e.to_string()))?,
        )
    } else {
        None
    };

    let opts = ProcessOptions {
        allow_undefined_array_items,
        allow_undefined_type,
        populate_by_name,
    };

    let result = process_schema(&schema_value, root_value.as_ref(), &opts)
        .map_err(|e| PyValueError::new_err(e.to_string()))?;

    Ok(field_type_to_py(py, &result))
}

/// The native Rust module for json-schema-to-pydantic-rs.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_json_schema, m)?)?;
    Ok(())
}
