# json-schema-to-pydantic-rs

Fast JSON Schema to Pydantic v2 model generation, powered by Rust.

A high-performance drop-in replacement for [json-schema-to-pydantic](https://github.com/richard-gyiko/json-schema-to-pydantic) using a Rust core via [PyO3](https://pyo3.rs).

## Performance

**5-10x faster** than the pure-Python original:

| Schema | Original | Rust | Speedup |
|---|---|---|---|
| Simple object (4 fields) | 993 us | 172 us | **5.8x** |
| Nested 3 levels | 2.49 ms | 306 us | **8.1x** |
| With `$ref` definitions | 1.59 ms | 164 us | **9.7x** |
| oneOf / anyOf / allOf combiners | 2.88 ms | 656 us | **4.4x** |
| Wide object (50 fields) | 2.37 ms | 354 us | **6.7x** |
| Enums and arrays | 452 us | 69 us | **6.6x** |

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
