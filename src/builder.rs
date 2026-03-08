use serde_json::Value;
use std::collections::{HashMap, HashSet};

use crate::constraints::{build_constraints, merge_schema_constraints};
use crate::error::SchemaError;
use crate::resolver::ReferenceResolver;
use crate::schema::*;

/// Configuration options for schema processing.
#[derive(Debug, Clone)]
#[allow(dead_code)]
#[derive(Default)]
pub struct ProcessOptions {
    pub allow_undefined_array_items: bool,
    pub allow_undefined_type: bool,
    pub populate_by_name: bool,
}


/// Main entry point: processes a raw JSON schema and returns a FieldType
/// representing the full resolved structure.
pub fn process_schema(
    schema: &Value,
    root_schema: Option<&Value>,
    opts: &ProcessOptions,
) -> Result<FieldType, SchemaError> {
    let root = root_schema.unwrap_or(schema);
    let mut resolver = ReferenceResolver::new();
    let mut model_cache: HashSet<String> = HashSet::new();

    process_schema_inner(schema, root, opts, &mut resolver, &mut model_cache, None)
}

fn process_schema_inner(
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
    schema_ref: Option<&str>,
) -> Result<FieldType, SchemaError> {
    let mut schema = schema;
    let mut owned_ref: Option<String> = schema_ref.map(|s| s.to_string());

    // Handle $ref
    if let Some(ref_str) = schema.get("$ref").and_then(|v| v.as_str()) {
        if owned_ref.is_none() {
            owned_ref = Some(ref_str.to_string());
        }

        let ref_key = owned_ref.as_deref().unwrap_or(ref_str);

        // Check if already being built (recursive reference)
        if model_cache.contains(ref_key) {
            let name = if ref_key == "#" {
                root_schema
                    .get("title")
                    .and_then(|v| v.as_str())
                    .unwrap_or("DynamicModel")
                    .to_string()
            } else {
                ref_key.split('/').next_back().unwrap_or("DynamicModel").to_string()
            };
            return Ok(FieldType::ForwardRef(name));
        }

        model_cache.insert(ref_key.to_string());
        schema = resolver.resolve_ref(ref_str, root_schema)?;
    }

    // Handle combiners
    if let Some(all_of) = schema.get("allOf").and_then(|v| v.as_array()) {
        let result = process_all_of(all_of, root_schema, opts, resolver, model_cache);
        if let Some(ref ref_key) = owned_ref { model_cache.remove(ref_key.as_str()); }
        return result;
    }
    if let Some(any_of) = schema.get("anyOf").and_then(|v| v.as_array()) {
        let result = process_any_of(any_of, root_schema, opts, resolver, model_cache);
        if let Some(ref ref_key) = owned_ref { model_cache.remove(ref_key.as_str()); }
        return result;
    }
    if let Some(one_of) = schema.get("oneOf").and_then(|v| v.as_array()) {
        let result = process_one_of(one_of, root_schema, opts, resolver, model_cache);
        if let Some(ref ref_key) = owned_ref { model_cache.remove(ref_key.as_str()); }
        return result;
    }

    // Handle top-level arrays
    if schema.get("type").and_then(|v| v.as_str()) == Some("array") {
        let result = process_root_array(schema, root_schema, opts, resolver, model_cache, &owned_ref);
        if let Some(ref ref_key) = owned_ref { model_cache.remove(ref_key.as_str()); }
        return result;
    }

    // Handle top-level scalars
    let schema_type = schema.get("type");
    let is_scalar = is_scalar_schema(schema_type, schema);
    if is_scalar {
        let result = process_root_scalar(schema, root_schema, opts, resolver, model_cache, &owned_ref);
        if let Some(ref ref_key) = owned_ref { model_cache.remove(ref_key.as_str()); }
        return result;
    }

    // Handle object schemas -> ModelDef
    let result = process_object_schema(schema, root_schema, opts, resolver, model_cache, &owned_ref);
    if let Some(ref ref_key) = owned_ref { model_cache.remove(ref_key.as_str()); }
    result
}

fn is_scalar_schema(schema_type: Option<&Value>, schema: &Value) -> bool {
    if let Some(t) = schema_type {
        if let Some(s) = t.as_str() {
            return matches!(s, "string" | "integer" | "number" | "boolean" | "null");
        }
        if let Some(arr) = t.as_array() {
            return !arr.iter().any(|v| {
                let s = v.as_str().unwrap_or("");
                s == "object" || s == "array"
            });
        }
    }
    schema.get("enum").is_some() || schema.get("const").is_some()
}

fn process_object_schema(
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
    owned_ref: &Option<String>,
) -> Result<FieldType, SchemaError> {
    let title = if let Some(ref_str) = owned_ref {
        if schema.get("title").is_none() {
            ref_str.split('/').next_back().unwrap_or("DynamicModel").to_string()
        } else {
            schema
                .get("title")
                .and_then(|v| v.as_str())
                .unwrap_or("DynamicModel")
                .to_string()
        }
    } else {
        schema
            .get("title")
            .and_then(|v| v.as_str())
            .unwrap_or("DynamicModel")
            .to_string()
    };

    let description = schema
        .get("description")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    let properties = schema
        .get("properties")
        .and_then(|v| v.as_object())
        .cloned()
        .unwrap_or_default();

    let required: HashSet<String> = schema
        .get("required")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();

    let std_props = standard_model_properties();
    let json_schema_extra: HashMap<String, Value> = schema
        .as_object()
        .map(|obj| {
            obj.iter()
                .filter(|(k, _)| !std_props.contains(k.as_str()))
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect()
        })
        .unwrap_or_default();

    let property_names: HashSet<String> = properties.keys().cloned().collect();

    let mut fields = Vec::new();
    for (field_name, field_schema) in &properties {
        let field_type =
            resolve_field_type(field_schema, root_schema, opts, resolver, model_cache)?;

        let (sanitized_name, alias) = sanitize_field_name(field_name, &property_names)?;
        let is_required = required.contains(field_name);

        let default = if field_schema.get("default").is_some() {
            field_schema.get("default").cloned()
        } else if !is_required {
            Some(Value::Null)
        } else {
            None
        };

        let field_description = field_schema
            .get("description")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        let constraints = build_field_constraints(field_schema);

        let std_field_props = standard_field_properties();
        let field_extra: HashMap<String, Value> = field_schema
            .as_object()
            .map(|obj| {
                obj.iter()
                    .filter(|(k, _)| !std_field_props.contains(k.as_str()))
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect()
            })
            .unwrap_or_default();

        fields.push(FieldDef {
            name: sanitized_name,
            python_type: field_type,
            required: is_required,
            default,
            description: field_description,
            alias,
            constraints,
            json_schema_extra: field_extra,
        });
    }

    let model_def = ModelDef {
        name: title,
        description,
        fields,
        json_schema_extra,
    };

    Ok(FieldType::NestedModel(Box::new(model_def)))
}

fn resolve_field_type(
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
) -> Result<FieldType, SchemaError> {
    let original_ref = schema.get("$ref").and_then(|v| v.as_str());

    // Handle $ref
    if let Some(ref_str) = original_ref {
        let resolved = resolver.resolve_ref(ref_str, root_schema)?;

        // Only use cycle detection for object schemas (models), not scalars/enums
        let is_object = resolved.get("type").and_then(|v| v.as_str()) == Some("object")
            && resolved.get("properties").is_some();

        if is_object {
            // Check for recursive reference (currently being built)
            if model_cache.contains(ref_str) {
                let name = if ref_str == "#" {
                    root_schema
                        .get("title")
                        .and_then(|v| v.as_str())
                        .unwrap_or("DynamicModel")
                        .to_string()
                } else {
                    ref_str.split('/').next_back().unwrap_or("DynamicModel").to_string()
                };
                return Ok(FieldType::ForwardRef(name));
            }

            // Mark as in-progress for cycle detection
            model_cache.insert(ref_str.to_string());

            let result = process_object_schema(
                resolved,
                root_schema,
                opts,
                resolver,
                model_cache,
                &Some(ref_str.to_string()),
            );

            // Remove from in-progress set so sibling refs can resolve normally
            model_cache.remove(ref_str);

            return result;
        }

        // Non-object ref (enum, scalar, etc.) - resolve without cycle tracking
        return resolve_field_type(resolved, root_schema, opts, resolver, model_cache);
    }

    // Handle combiners
    if let Some(all_of) = schema.get("allOf").and_then(|v| v.as_array()) {
        return process_all_of(all_of, root_schema, opts, resolver, model_cache);
    }
    if let Some(any_of) = schema.get("anyOf").and_then(|v| v.as_array()) {
        return process_any_of(any_of, root_schema, opts, resolver, model_cache);
    }
    if let Some(one_of) = schema.get("oneOf").and_then(|v| v.as_array()) {
        return process_one_of(one_of, root_schema, opts, resolver, model_cache);
    }

    // Handle arrays
    if schema.get("type").and_then(|v| v.as_str()) == Some("array") {
        return resolve_array_type(schema, root_schema, opts, resolver, model_cache);
    }

    // Handle nested objects
    if schema.get("type").and_then(|v| v.as_str()) == Some("object")
        && schema.get("properties").is_some()
    {
        return process_object_schema(schema, root_schema, opts, resolver, model_cache, &None);
    }

    // Handle typed dicts (object with additionalProperties schema)
    if schema.get("type").and_then(|v| v.as_str()) == Some("object") {
        return resolve_dict_type(schema, root_schema, opts, resolver, model_cache);
    }

    // Resolve scalar type
    resolve_scalar_type(schema, root_schema, opts)
}

fn resolve_array_type(
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
) -> Result<FieldType, SchemaError> {
    let items = schema.get("items");
    let item_type = match items {
        Some(items_schema) => {
            resolve_field_type(items_schema, root_schema, opts, resolver, model_cache)?
        }
        None => {
            if opts.allow_undefined_array_items {
                FieldType::Scalar("Any".into())
            } else {
                return Err(SchemaError::Type(
                    "Array type must specify 'items' schema".into(),
                ));
            }
        }
    };

    let unique = schema
        .get("uniqueItems")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    if unique {
        Ok(FieldType::Set(Box::new(item_type)))
    } else {
        Ok(FieldType::List(Box::new(item_type)))
    }
}

fn resolve_dict_type(
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
) -> Result<FieldType, SchemaError> {
    let additional = schema.get("additionalProperties");

    match additional {
        // additionalProperties: { "type": "..." } or other schema object
        Some(Value::Object(_)) => {
            let value_type = resolve_field_type(additional.unwrap(), root_schema, opts, resolver, model_cache)?;
            Ok(FieldType::Dict {
                key_type: Box::new(FieldType::Scalar("str".into())),
                value_type: Box::new(value_type),
            })
        }
        // additionalProperties: false means no extra keys (empty dict)
        Some(Value::Bool(false)) => Ok(FieldType::Scalar("dict".into())),
        // additionalProperties: true or absent => untyped dict
        _ => Ok(FieldType::Scalar("dict".into())),
    }
}

fn resolve_scalar_type(
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
) -> Result<FieldType, SchemaError> {
    // Handle const
    if let Some(c) = schema.get("const") {
        if c.is_null() {
            return Ok(FieldType::Scalar("None".into()));
        }
        return Ok(FieldType::Literal(vec![c.clone()]));
    }

    // Handle null type
    if schema.get("type").and_then(|v| v.as_str()) == Some("null") {
        return Ok(FieldType::Scalar("None".into()));
    }

    // Handle array of types (e.g., ["string", "null"])
    if let Some(types) = schema.get("type").and_then(|v| v.as_array()) {
        return resolve_type_array(types, schema, root_schema, opts);
    }

    // Handle enum
    if let Some(enum_vals) = schema.get("enum").and_then(|v| v.as_array()) {
        if enum_vals.is_empty() {
            return Err(SchemaError::Type("Enum must have at least one value".into()));
        }
        return Ok(FieldType::Literal(enum_vals.clone()));
    }

    // Infer type if not specified
    let schema_type = schema.get("type").and_then(|v| v.as_str());
    let schema_type = match schema_type {
        Some(t) => t,
        None => {
            if schema.get("properties").is_some() {
                "object"
            } else if schema.get("items").is_some() {
                "array"
            } else if opts.allow_undefined_type {
                return Ok(FieldType::Scalar("Any".into()));
            } else {
                return Err(SchemaError::Type(
                    "Schema must specify a type. Set allow_undefined_type=True to infer Any type for schemas without explicit types.".into(),
                ));
            }
        }
    };

    // Handle string with format
    if schema_type == "string" {
        if let Some(fmt) = schema.get("format").and_then(|v| v.as_str()) {
            return Ok(match fmt {
                "date-time" => FieldType::Format("datetime".into()),
                "date" => FieldType::Format("date".into()),
                "time" => FieldType::Format("time".into()),
                "email" => FieldType::Scalar("str".into()),
                "uri" => FieldType::Format("AnyUrl".into()),
                "uuid" => FieldType::Format("uuid".into()),
                _ => FieldType::Scalar("str".into()),
            });
        }
    }

    // For object type, check additionalProperties for value typing
    if schema_type == "object" {
        if let Some(Value::Object(_)) = schema.get("additionalProperties") {
            // We can't call resolve_field_type here (no resolver/model_cache),
            // but we can handle simple type schemas inline
            let additional = schema.get("additionalProperties").unwrap();
            if let Some(t) = additional.get("type").and_then(|v| v.as_str()) {
                let value_type = match t {
                    "string" => FieldType::Scalar("str".into()),
                    "integer" => FieldType::Scalar("int".into()),
                    "number" => FieldType::Scalar("float".into()),
                    "boolean" => FieldType::Scalar("bool".into()),
                    "null" => FieldType::Scalar("None".into()),
                    _ => FieldType::Scalar("Any".into()),
                };
                return Ok(FieldType::Dict {
                    key_type: Box::new(FieldType::Scalar("str".into())),
                    value_type: Box::new(value_type),
                });
            }
        }
        return Ok(FieldType::Scalar("dict".into()));
    }

    Ok(match schema_type {
        "string" => FieldType::Scalar("str".into()),
        "integer" => FieldType::Scalar("int".into()),
        "number" => FieldType::Scalar("float".into()),
        "boolean" => FieldType::Scalar("bool".into()),
        "null" => FieldType::Scalar("None".into()),
        _ => FieldType::Scalar("str".into()),
    })
}

fn resolve_type_array(
    types: &[Value],
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
) -> Result<FieldType, SchemaError> {
    let type_strs: Vec<&str> = types.iter().filter_map(|v| v.as_str()).collect();
    let has_null = type_strs.contains(&"null");
    let other_types: Vec<&&str> = type_strs.iter().filter(|t| **t != "null").collect();

    if has_null && other_types.is_empty() {
        return Ok(FieldType::Scalar("None".into()));
    }

    let resolve_single = |type_str: &str| -> Result<FieldType, SchemaError> {
        let mut modified = schema.as_object().cloned().unwrap_or_default();
        modified.insert("type".into(), Value::String(type_str.to_string()));
        resolve_scalar_type(&Value::Object(modified), root_schema, opts)
    };

    if other_types.len() == 1 {
        let inner = resolve_single(other_types[0])?;
        if has_null {
            return Ok(FieldType::Optional(Box::new(inner)));
        }
        return Ok(inner);
    }

    let resolved: Result<Vec<FieldType>, SchemaError> =
        other_types.iter().map(|t| resolve_single(t)).collect();
    let resolved = resolved?;

    if has_null {
        Ok(FieldType::Optional(Box::new(FieldType::Union(resolved))))
    } else {
        Ok(FieldType::Union(resolved))
    }
}

fn process_all_of(
    schemas: &[Value],
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
) -> Result<FieldType, SchemaError> {
    if schemas.is_empty() {
        return Err(SchemaError::Combiner(
            "allOf must contain at least one schema".into(),
        ));
    }

    let mut merged_properties: serde_json::Map<String, Value> = serde_json::Map::new();
    let mut required_fields: HashSet<String> = HashSet::new();

    for schema in schemas {
        let schema = if let Some(ref_str) = schema.get("$ref").and_then(|v| v.as_str()) {
            resolver.resolve_ref(ref_str, root_schema)?.clone()
        } else {
            schema.clone()
        };

        if let Some(props) = schema.get("properties").and_then(|v| v.as_object()) {
            for (name, prop_schema) in props {
                if let Some(existing) = merged_properties.get(name) {
                    let merged = merge_schema_constraints(existing, prop_schema);
                    merged_properties.insert(name.clone(), merged);
                } else {
                    merged_properties.insert(name.clone(), prop_schema.clone());
                }
            }
        }

        if let Some(req) = schema.get("required").and_then(|v| v.as_array()) {
            for r in req {
                if let Some(s) = r.as_str() {
                    required_fields.insert(s.to_string());
                }
            }
        }
    }

    let property_names: HashSet<String> = merged_properties.keys().cloned().collect();

    let mut fields = Vec::new();
    for (name, prop_schema) in &merged_properties {
        let field_type =
            resolve_field_type(prop_schema, root_schema, opts, resolver, model_cache)?;
        let (sanitized_name, alias) = sanitize_field_name(name, &property_names)?;
        let is_required = required_fields.contains(name);

        let default = if prop_schema.get("default").is_some() {
            prop_schema.get("default").cloned()
        } else if !is_required {
            Some(Value::Null)
        } else {
            None
        };

        let description = prop_schema
            .get("description")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());

        let constraints = build_field_constraints(prop_schema);

        fields.push(FieldDef {
            name: sanitized_name,
            python_type: field_type,
            required: is_required,
            default,
            description,
            alias,
            constraints,
            json_schema_extra: HashMap::new(),
        });
    }

    Ok(FieldType::AllOfModel(Box::new(ModelDef {
        name: "AllOfModel".into(),
        description: None,
        fields,
        json_schema_extra: HashMap::new(),
    })))
}

fn process_any_of(
    schemas: &[Value],
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
) -> Result<FieldType, SchemaError> {
    if schemas.is_empty() {
        return Err(SchemaError::Combiner(
            "anyOf must contain at least one schema".into(),
        ));
    }

    let mut types = Vec::new();
    for schema in schemas {
        let resolved = if let Some(ref_str) = schema.get("$ref").and_then(|v| v.as_str()) {
            let r = resolver.resolve_ref(ref_str, root_schema)?;
            resolve_field_type(r, root_schema, opts, resolver, model_cache)?
        } else {
            resolve_field_type(schema, root_schema, opts, resolver, model_cache)?
        };
        types.push(resolved);
    }

    Ok(FieldType::AnyOf(types))
}

fn process_one_of(
    schemas: &[Value],
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
) -> Result<FieldType, SchemaError> {
    if schemas.is_empty() {
        return Err(SchemaError::Combiner(
            "oneOf must contain at least one schema".into(),
        ));
    }

    // Check for const/literal pattern
    if schemas
        .iter()
        .all(|s| s.as_object().is_some_and(|o| o.contains_key("const")))
    {
        let values: Vec<Value> = schemas
            .iter()
            .filter_map(|s| s.get("const").cloned())
            .collect();
        let all_literal = values.iter().all(|v| {
            v.is_string() || v.is_i64() || v.is_boolean() || v.is_null() || v.is_u64()
        });
        if all_literal {
            return Ok(FieldType::OneOfLiteral(values));
        }
    }

    // Check for discriminated union pattern
    if is_discriminated_union(schemas, root_schema, resolver)? {
        return process_discriminated_union(schemas, root_schema, opts, resolver, model_cache);
    }

    // Fallback: general union
    let mut types = Vec::new();
    for schema in schemas {
        let resolved = resolve_field_type(schema, root_schema, opts, resolver, model_cache)?;
        types.push(resolved);
    }

    Ok(FieldType::OneOfUnion(types))
}

fn is_discriminated_union(
    schemas: &[Value],
    root_schema: &Value,
    resolver: &mut ReferenceResolver,
) -> Result<bool, SchemaError> {
    for schema in schemas {
        let resolved = if let Some(ref_str) = schema.get("$ref").and_then(|v| v.as_str()) {
            resolver.resolve_ref(ref_str, root_schema)?
        } else {
            schema
        };

        let props = match resolved.get("properties").and_then(|v| v.as_object()) {
            Some(p) => p,
            None => return Ok(false),
        };

        let type_prop = match props.get("type").and_then(|v| v.as_object()) {
            Some(t) => t,
            None => return Ok(false),
        };

        if !type_prop.contains_key("const") {
            return Ok(false);
        }
    }
    Ok(true)
}

fn process_discriminated_union(
    schemas: &[Value],
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
) -> Result<FieldType, SchemaError> {
    let mut variants = Vec::new();

    for schema in schemas {
        let ref_path = schema.get("$ref").and_then(|v| v.as_str());
        let resolved = if let Some(ref_str) = ref_path {
            resolver.resolve_ref(ref_str, root_schema)?.clone()
        } else {
            schema.clone()
        };

        let properties = resolved
            .get("properties")
            .and_then(|v| v.as_object())
            .cloned()
            .unwrap_or_default();

        let type_const = properties
            .get("type")
            .and_then(|v| v.get("const"))
            .cloned()
            .unwrap_or(Value::Null);

        let required: HashSet<String> = resolved
            .get("required")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();

        let property_names: HashSet<String> = properties.keys().cloned().collect();

        let mut fields = Vec::new();
        for (name, prop_schema) in &properties {
            if name == "type" {
                // type field gets Literal type
                let description = prop_schema
                    .get("description")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string());
                fields.push(FieldDef {
                    name: "type".into(),
                    python_type: FieldType::Literal(vec![type_const.clone()]),
                    required: true,
                    default: Some(type_const.clone()),
                    description,
                    alias: None,
                    constraints: HashMap::new(),
                    json_schema_extra: HashMap::new(),
                });
            } else {
                let field_type =
                    resolve_field_type(prop_schema, root_schema, opts, resolver, model_cache)?;
                let (sanitized_name, alias) = sanitize_field_name(name, &property_names)?;
                let is_required = required.contains(name);

                let default = if prop_schema.get("default").is_some() {
                    prop_schema.get("default").cloned()
                } else if !is_required {
                    Some(Value::Null)
                } else {
                    None
                };

                let description = prop_schema
                    .get("description")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string());

                let constraints = build_field_constraints(prop_schema);

                fields.push(FieldDef {
                    name: sanitized_name,
                    python_type: field_type,
                    required: is_required,
                    default,
                    description,
                    alias,
                    constraints,
                    json_schema_extra: HashMap::new(),
                });
            }
        }

        let model_name = if let Some(rp) = ref_path {
            rp.split('/').next_back().unwrap_or("Variant").to_string()
        } else {
            format!(
                "Variant_{}",
                type_const.as_str().unwrap_or(
                    &type_const
                        .as_i64()
                        .map(|i| i.to_string())
                        .unwrap_or_else(|| "unknown".into())
                )
            )
        };

        variants.push(OneOfVariant {
            model_name,
            discriminator_value: type_const,
            fields,
        });
    }

    Ok(FieldType::OneOfDiscriminated {
        discriminator_field: "type".into(),
        variants,
    })
}

fn process_root_array(
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
    resolver: &mut ReferenceResolver,
    model_cache: &mut HashSet<String>,
    owned_ref: &Option<String>,
) -> Result<FieldType, SchemaError> {
    let name = get_model_name(schema, owned_ref);
    let description = schema
        .get("description")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    let items = schema.get("items");
    let item_type = match items {
        Some(items_schema) => {
            resolve_field_type(items_schema, root_schema, opts, resolver, model_cache)?
        }
        None => {
            if opts.allow_undefined_array_items {
                FieldType::Scalar("Any".into())
            } else {
                return Err(SchemaError::Type(
                    "Array type must specify 'items' schema".into(),
                ));
            }
        }
    };

    let unique = schema
        .get("uniqueItems")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    let constraints = build_constraints(schema);

    let std_props = standard_model_properties();
    let json_schema_extra: HashMap<String, Value> = schema
        .as_object()
        .map(|obj| {
            obj.iter()
                .filter(|(k, _)| !std_props.contains(k.as_str()))
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect()
        })
        .unwrap_or_default();

    Ok(FieldType::RootArray {
        item_type: Box::new(item_type),
        unique_items: unique,
        constraints,
        name,
        description,
        json_schema_extra,
    })
}

fn process_root_scalar(
    schema: &Value,
    root_schema: &Value,
    opts: &ProcessOptions,
    _resolver: &mut ReferenceResolver,
    _model_cache: &mut HashSet<String>,
    owned_ref: &Option<String>,
) -> Result<FieldType, SchemaError> {
    let name = get_model_name(schema, owned_ref);
    let description = schema
        .get("description")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    let scalar_type = resolve_scalar_type(schema, root_schema, opts)?;
    let constraints = build_constraints(schema);

    let std_props = standard_model_properties();
    let json_schema_extra: HashMap<String, Value> = schema
        .as_object()
        .map(|obj| {
            obj.iter()
                .filter(|(k, _)| !std_props.contains(k.as_str()))
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect()
        })
        .unwrap_or_default();

    Ok(FieldType::RootScalar {
        scalar_type: Box::new(scalar_type),
        constraints,
        name,
        description,
        json_schema_extra,
    })
}

fn get_model_name(schema: &Value, owned_ref: &Option<String>) -> String {
    if let Some(ref_str) = owned_ref {
        if schema.get("title").is_none() {
            return ref_str
                .split('/')
                .next_back()
                .unwrap_or("DynamicModel")
                .to_string();
        }
    }
    schema
        .get("title")
        .and_then(|v| v.as_str())
        .unwrap_or("DynamicModel")
        .to_string()
}

/// Build constraints dict for a field (excluding format-based type returns).
fn build_field_constraints(schema: &Value) -> HashMap<String, Value> {
    // If it has const or format that maps to a type, skip constraint extraction
    if schema.get("const").is_some() {
        return HashMap::new();
    }
    if let Some(fmt) = schema.get("format").and_then(|v| v.as_str()) {
        match fmt {
            "date-time" | "date" | "time" | "uri" | "uuid" => return HashMap::new(),
            "email" => {
                let mut m = HashMap::new();
                m.insert(
                    "pattern".into(),
                    Value::String(
                        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$".into(),
                    ),
                );
                return m;
            }
            _ => {}
        }
    }
    build_constraints(schema)
}

/// Sanitize a field name for Pydantic (strip leading underscores, return alias).
fn sanitize_field_name(
    field_name: &str,
    all_names: &HashSet<String>,
) -> Result<(String, Option<String>), SchemaError> {
    if field_name.starts_with('_') {
        let sanitized = field_name.trim_start_matches('_').to_string();
        if all_names.contains(&sanitized) {
            return Err(SchemaError::Schema(format!(
                "Duplicate field name after sanitization: '{sanitized}'\nPydantic does not support \
                 field names starting with underscores when another field would result in the same name."
            )));
        }
        Ok((sanitized, Some(field_name.to_string())))
    } else {
        Ok((field_name.to_string(), None))
    }
}
