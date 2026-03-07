use serde_json::Value;
use std::collections::HashMap;

/// Extract Pydantic field constraints from a JSON Schema fragment.
///
/// Returns a map of constraint name -> value, matching Pydantic `Field` kwargs:
/// - `min_length`, `max_length`, `pattern` (string)
/// - `ge`, `le`, `gt`, `lt`, `multiple_of` (numeric)
/// - `min_length`, `max_length` (array via minItems/maxItems)
pub fn build_constraints(schema: &Value) -> HashMap<String, Value> {
    let obj = match schema.as_object() {
        Some(o) => o,
        None => return HashMap::new(),
    };

    let mut constraints = HashMap::new();

    // String constraints
    if let Some(v) = obj.get("minLength") {
        constraints.insert("min_length".into(), v.clone());
    }
    if let Some(v) = obj.get("maxLength") {
        constraints.insert("max_length".into(), v.clone());
    }
    if let Some(v) = obj.get("pattern") {
        constraints.insert("pattern".into(), v.clone());
    }

    // Numeric constraints
    if let Some(v) = obj.get("minimum") {
        constraints.insert("ge".into(), v.clone());
    }
    if let Some(v) = obj.get("maximum") {
        constraints.insert("le".into(), v.clone());
    }
    if let Some(v) = obj.get("exclusiveMinimum") {
        constraints.insert("gt".into(), v.clone());
    }
    if let Some(v) = obj.get("exclusiveMaximum") {
        constraints.insert("lt".into(), v.clone());
    }
    if let Some(v) = obj.get("multipleOf") {
        constraints.insert("multiple_of".into(), v.clone());
    }

    // Array constraints (mapped to same Pydantic kwargs)
    if let Some(v) = obj.get("minItems") {
        constraints.insert("min_length".into(), v.clone());
    }
    if let Some(v) = obj.get("maxItems") {
        constraints.insert("max_length".into(), v.clone());
    }

    constraints
}

/// Merge constraints from two schemas for the same property (allOf merging).
///
/// For min-like constraints: takes the maximum (most restrictive).
/// For max-like constraints: takes the minimum (most restrictive).
/// For patterns: combines with lookahead AND logic.
pub fn merge_schema_constraints(schema1: &Value, schema2: &Value) -> Value {
    let mut merged = match schema1.as_object() {
        Some(o) => o.clone(),
        None => return schema2.clone(),
    };

    let obj2 = match schema2.as_object() {
        Some(o) => o,
        None => return Value::Object(merged),
    };

    // Numeric constraints
    for key in &[
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    ] {
        if let Some(v2) = obj2.get(*key) {
            if let Some(v1) = merged.get(*key) {
                let is_min = *key == "minimum" || *key == "exclusiveMinimum";
                let pick = if is_min {
                    // Take the larger (more restrictive) minimum
                    if v2.as_f64().unwrap_or(0.0) > v1.as_f64().unwrap_or(0.0) {
                        v2
                    } else {
                        v1
                    }
                } else {
                    // Take the smaller (more restrictive) maximum
                    if v2.as_f64().unwrap_or(0.0) < v1.as_f64().unwrap_or(0.0) {
                        v2
                    } else {
                        v1
                    }
                };
                merged.insert(key.to_string(), pick.clone());
            } else {
                merged.insert(key.to_string(), v2.clone());
            }
        }
    }

    // String constraints
    for key in &["minLength", "maxLength", "pattern"] {
        if let Some(v2) = obj2.get(*key) {
            if let Some(v1) = merged.get(*key) {
                if *key == "minLength" {
                    let pick = if v2.as_u64().unwrap_or(0) > v1.as_u64().unwrap_or(0) {
                        v2
                    } else {
                        v1
                    };
                    merged.insert(key.to_string(), pick.clone());
                } else if *key == "maxLength" {
                    let pick = if v2.as_u64().unwrap_or(u64::MAX) < v1.as_u64().unwrap_or(u64::MAX)
                    {
                        v2
                    } else {
                        v1
                    };
                    merged.insert(key.to_string(), pick.clone());
                } else if *key == "pattern" {
                    // Combine patterns with AND logic using lookahead
                    let p1 = v1.as_str().unwrap_or("");
                    let p2 = v2.as_str().unwrap_or("");
                    let combined = format!("(?={p1})(?={p2})");
                    merged.insert(key.to_string(), Value::String(combined));
                }
            } else {
                merged.insert(key.to_string(), v2.clone());
            }
        }
    }

    Value::Object(merged)
}
