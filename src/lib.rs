mod builder;
mod constraints;
mod convert;
mod core_schema;
mod error;
mod pydict_to_value;
mod resolver;
mod schema;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use builder::{ProcessOptions, process_schema};
use convert::field_type_to_py;
use core_schema::field_type_to_core_schema;
use pydict_to_value::pydict_to_value;

/// Shared processing logic: parse schema + options, run process_schema.
fn do_process(
    schema_value: serde_json::Value,
    root_value: Option<serde_json::Value>,
    allow_undefined_array_items: bool,
    allow_undefined_type: bool,
    populate_by_name: bool,
) -> PyResult<schema::FieldType> {
    let opts = ProcessOptions {
        allow_undefined_array_items,
        allow_undefined_type,
        populate_by_name,
    };

    process_schema(&schema_value, root_value.as_ref(), &opts)
        .map_err(|e| PyValueError::new_err(e.to_string()))
}

/// Parse input: either a JSON string or a Python dict → serde_json::Value.
fn parse_input(input: &Bound<'_, pyo3::PyAny>) -> PyResult<serde_json::Value> {
    // Try string first (fast path)
    if let Ok(s) = input.extract::<String>() {
        return serde_json::from_str(&s)
            .map_err(|e| PyValueError::new_err(format!("Invalid JSON: {e}")));
    }
    // Fall back to dict (legacy path)
    let dict = input
        .downcast::<PyDict>()
        .map_err(|_| PyValueError::new_err("schema must be a JSON string or a dict"))?;
    pydict_to_value(dict).map_err(|e| PyValueError::new_err(e.to_string()))
}

/// Process a JSON schema (str or dict) and return a resolved type description (legacy format).
#[pyfunction]
#[pyo3(signature = (schema, root_schema=None, allow_undefined_array_items=false, allow_undefined_type=false, populate_by_name=false))]
fn process_json_schema(
    py: Python<'_>,
    schema: &Bound<'_, pyo3::PyAny>,
    root_schema: Option<&Bound<'_, pyo3::PyAny>>,
    allow_undefined_array_items: bool,
    allow_undefined_type: bool,
    populate_by_name: bool,
) -> PyResult<PyObject> {
    let schema_value = parse_input(schema)?;
    let root_value = root_schema.map(parse_input).transpose()?;

    let result = do_process(
        schema_value,
        root_value,
        allow_undefined_array_items,
        allow_undefined_type,
        populate_by_name,
    )?;

    Ok(field_type_to_py(py, &result))
}

/// Process a JSON schema (str or dict) and return pydantic-core compatible schema dicts.
#[pyfunction]
#[pyo3(signature = (schema, root_schema=None, allow_undefined_array_items=false, allow_undefined_type=false, populate_by_name=false))]
fn process_json_schema_core(
    py: Python<'_>,
    schema: &Bound<'_, pyo3::PyAny>,
    root_schema: Option<&Bound<'_, pyo3::PyAny>>,
    allow_undefined_array_items: bool,
    allow_undefined_type: bool,
    populate_by_name: bool,
) -> PyResult<PyObject> {
    let schema_value = parse_input(schema)?;
    let root_value = root_schema.map(parse_input).transpose()?;

    let result = do_process(
        schema_value,
        root_value,
        allow_undefined_array_items,
        allow_undefined_type,
        populate_by_name,
    )?;

    Ok(field_type_to_core_schema(py, &result))
}

/// The native Rust module for json-schema-to-pydantic-rs.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(process_json_schema, m)?)?;
    m.add_function(wrap_pyfunction!(process_json_schema_core, m)?)?;
    Ok(())
}
