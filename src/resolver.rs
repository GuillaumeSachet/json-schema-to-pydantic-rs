use serde_json::Value;
use std::collections::HashSet;

use crate::error::SchemaError;

/// Resolves JSON Schema `$ref` references within a schema document.
pub struct ReferenceResolver {
    processing_refs: HashSet<String>,
}

impl ReferenceResolver {
    pub fn new() -> Self {
        Self {
            processing_refs: HashSet::new(),
        }
    }

    /// Resolve a `$ref` string to the referenced schema fragment.
    ///
    /// Only local references (`#/...`) are supported.
    /// Detects circular references and returns an error.
    pub fn resolve_ref<'a>(
        &mut self,
        ref_str: &str,
        root_schema: &'a Value,
    ) -> Result<&'a Value, SchemaError> {
        if !ref_str.starts_with('#') {
            return Err(SchemaError::Reference(
                "Only local references (#/...) are supported".into(),
            ));
        }

        if self.processing_refs.contains(ref_str) {
            return Err(SchemaError::Reference(format!(
                "Circular reference detected: {ref_str}"
            )));
        }

        self.processing_refs.insert(ref_str.to_string());

        let result = self.navigate_ref(ref_str, root_schema);

        self.processing_refs.remove(ref_str);

        let resolved = result?;

        // If we find another $ref, resolve it recursively
        if let Some(inner_ref) = resolved.get("$ref").and_then(|v| v.as_str()) {
            return self.resolve_ref(inner_ref, root_schema);
        }

        Ok(resolved)
    }

    fn navigate_ref<'a>(
        &self,
        ref_str: &str,
        root_schema: &'a Value,
    ) -> Result<&'a Value, SchemaError> {
        // Split "#/definitions/Foo" into ["definitions", "Foo"]
        let path: Vec<&str> = ref_str
            .trim_start_matches('#')
            .trim_start_matches('/')
            .split('/')
            .filter(|s| !s.is_empty())
            .collect();

        let mut current = root_schema;
        for part in &path {
            // Handle JSON Pointer escaping: ~1 -> /, ~0 -> ~
            let decoded = part.replace("~1", "/").replace("~0", "~");
            current = current.get(&decoded).ok_or_else(|| {
                SchemaError::Reference(format!("Invalid reference path: {ref_str}"))
            })?;
        }

        Ok(current)
    }
}
