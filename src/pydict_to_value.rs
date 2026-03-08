//! Direct conversion from Python dict to serde_json::Value without json.dumps round-trip.

use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyNone, PyString};
use serde_json::{Map, Number, Value};

/// Convert a Python object to serde_json::Value by walking the PyObject tree directly.
pub fn pyany_to_value(obj: &Bound<'_, PyAny>) -> PyResult<Value> {
    // None
    if obj.is_instance_of::<PyNone>() {
        return Ok(Value::Null);
    }

    // Bool (must check before int, since bool is a subclass of int in Python)
    if obj.is_instance_of::<PyBool>() {
        return Ok(Value::Bool(obj.extract::<bool>()?));
    }

    // Int
    if obj.is_instance_of::<PyInt>() {
        let val: i64 = obj.extract()?;
        return Ok(Value::Number(Number::from(val)));
    }

    // Float
    if obj.is_instance_of::<PyFloat>() {
        let val: f64 = obj.extract()?;
        return Ok(match Number::from_f64(val) {
            Some(n) => Value::Number(n),
            None => Value::Null, // NaN/Inf
        });
    }

    // String
    if obj.is_instance_of::<PyString>() {
        return Ok(Value::String(obj.extract::<String>()?));
    }

    // List/tuple
    if obj.is_instance_of::<PyList>() {
        let list = obj.downcast::<PyList>()?;
        let mut arr = Vec::with_capacity(list.len());
        for item in list.iter() {
            arr.push(pyany_to_value(&item)?);
        }
        return Ok(Value::Array(arr));
    }

    // Dict
    if obj.is_instance_of::<PyDict>() {
        let dict = obj.downcast::<PyDict>()?;
        return pydict_to_value(dict);
    }

    // Fallback: convert via str()
    let s: String = obj.str()?.extract()?;
    Ok(Value::String(s))
}

/// Convert a Python dict to serde_json::Value::Object.
pub fn pydict_to_value(dict: &Bound<'_, PyDict>) -> PyResult<Value> {
    let mut map = Map::with_capacity(dict.len());
    for (key, value) in dict.iter() {
        let k: String = key.extract()?;
        let v = pyany_to_value(&value)?;
        map.insert(k, v);
    }
    Ok(Value::Object(map))
}
