# json-schema-to-pydantic-rs

[![PyPI](https://img.shields.io/pypi/v/json-schema-to-pydantic-rs)](https://pypi.org/project/json-schema-to-pydantic-rs/)
[![CI](https://github.com/GuillaumeSachet/json-schema-to-pydantic-rs/actions/workflows/test.yaml/badge.svg)](https://github.com/GuillaumeSachet/json-schema-to-pydantic-rs/actions/workflows/test.yaml)
[![Python](https://img.shields.io/pypi/pyversions/json-schema-to-pydantic-rs)](https://pypi.org/project/json-schema-to-pydantic-rs/)
[![License](https://img.shields.io/pypi/l/json-schema-to-pydantic-rs)](https://github.com/GuillaumeSachet/json-schema-to-pydantic-rs/blob/main/LICENSE)

Fast JSON Schema to Pydantic v2 model generation, powered by Rust.

A high-performance drop-in replacement for [json-schema-to-pydantic](https://github.com/richard-gyiko/json-schema-to-pydantic) using a Rust core via [PyO3](https://pyo3.rs).

## Performance

**3-8x faster** than the pure-Python original:

| Schema | Original | Rust | Speedup |
|---|---|---|---|
| Simple object (4 fields) | 1.00 ms | 178 us | **5.7x** |
| Nested 3 levels | 2.42 ms | 280 us | **7.8x** |
| With `$ref` definitions | 1.26 ms | 149 us | **8.4x** |
| oneOf / anyOf / allOf / if-then-else | 2.38 ms | 752 us | **3.2x** |
| Wide object (50 fields) | 2.40 ms | 365 us | **7.3x** |
| Enums and arrays | 462 us | 71 us | **6.6x** |

## Installation

```bash
pip install json-schema-to-pydantic-rs
```

Requires Python 3.10+ and Pydantic v2.10.4+.

## Quick start

```python
from json_schema_to_pydantic_rs import create_model

User = create_model({
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "age": {"type": "integer", "minimum": 0},
        "email": {"type": "string", "format": "email"},
    },
    "required": ["name", "age"],
})

user = User(name="Alice", age=30, email="alice@example.com")
print(user.model_dump_json())
# {"name":"Alice","age":30,"email":"alice@example.com"}

# Round-trip
restored = User.model_validate_json('{"name":"Alice","age":30}')
```

## API

### `create_model(schema, **options)`

Converts a JSON Schema into a Pydantic `BaseModel` subclass. Accepts a `dict` or a JSON `str`. Supports the full JSON Schema spec: types, formats (`uuid`, `date-time`, `email`, ...), `$ref`/`$defs`, `allOf`/`anyOf`/`oneOf`, `enum`, `const`, `additionalProperties`, constraints, and nullable types.

```python
from json_schema_to_pydantic_rs import create_model

# From a dict
Order = create_model({
    "type": "object",
    "properties": {
        "customer": {"$ref": "#/$defs/Customer"},
        "items": {"type": "array", "items": {"$ref": "#/$defs/Product"}, "minItems": 1},
    },
    "required": ["customer", "items"],
    "$defs": {
        "Customer": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "email": {"type": "string", "format": "email"},
            },
            "required": ["name"],
        },
        "Product": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "price": {"type": "number", "minimum": 0},
            },
            "required": ["name", "price"],
        },
    },
})

order = Order(
    customer={"name": "Alice", "email": "alice@example.com"},
    items=[{"name": "Widget", "price": 9.99}],
)
print(order.customer.name)   # "Alice"
print(order.items[0].price)  # 9.99

# Or from a JSON string
Order = create_model('{"type": "object", "properties": {"name": {"type": "string"}}}')
```

**Options:**

```python
create_model(
    schema,
    base_model_type=MyBase,             # Base class for generated models
    predefined_models={                  # Plug your own classes for $ref paths
        "#/$defs/Address": Address,
    },
    allow_undefined_array_items=True,    # Arrays without "items" -> List[Any]
    allow_undefined_type=True,           # Schemas without "type" -> Any
    populate_by_name=True,               # Access fields by both name and alias
)
```

### `PydanticModelBuilder`

For reusing config across multiple schemas:

```python
from pydantic import BaseModel
from json_schema_to_pydantic_rs import PydanticModelBuilder

class Address(BaseModel):
    street: str
    city: str

builder = PydanticModelBuilder(
    base_model_type=BaseModel,                         # custom base class
    predefined_models={"#/$defs/Address": Address},    # reuse existing models
)
Model = builder.create_pydantic_model(schema)
```

Non-standard schema properties are preserved via `json_schema_extra`:

```python
Model = create_model({
    "type": "object",
    "properties": {"bio": {"type": "string", "ui_widget": "textarea"}},
})
Model.model_fields["bio"].json_schema_extra  # {"ui_widget": "textarea"}
```

## Development

```bash
uv sync --dev
uv run maturin develop --release
uv run pytest
uv run python bench.py
```

## Compatibility

- Python 3.10 - 3.14
- Pydantic v2.10.4+
- Rust edition 2024

## License

MIT — see [LICENSE](LICENSE).

Based on [json-schema-to-pydantic](https://github.com/richard-gyiko/json-schema-to-pydantic) by Richard Gyiko.
