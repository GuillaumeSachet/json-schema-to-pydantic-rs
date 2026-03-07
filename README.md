# json-schema-to-pydantic-rs

Fast JSON Schema to Pydantic v2 model generation, powered by a Rust core.

A rewrite of [json-schema-to-pydantic](https://github.com/richard-gyiko/json-schema-to-pydantic) with a Rust core (via PyO3) for speed, published to PyPI.

## Installation

```bash
pip install json-schema-to-pydantic-rs
```

## Usage

```python
from json_schema_to_pydantic_rs import create_model

schema = {
    "title": "Person",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
    },
    "required": ["name"],
}

Person = create_model(schema)
person = Person(name="Alice", age=30)
```

## Features

- Same public API as the original: `create_model()` and `PydanticModelBuilder`
- `$ref` resolution with circular reference detection
- `allOf` / `anyOf` / `oneOf` combiner support
- Full constraint extraction (min/max/pattern/format/etc.)
- Predefined model reuse
- Custom base model types
- `populate_by_name` support
- `json_schema_extra` preservation

## License

MIT
