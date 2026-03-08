"""Benchmark: json-schema-to-pydantic (pure Python) vs json-schema-to-pydantic-rs (Rust core)."""

import time
import statistics

# ── Schemas ──────────────────────────────────────────────────────────────────

SIMPLE_OBJECT = {
    "title": "User",
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 100},
        "age": {"type": "integer", "minimum": 0, "maximum": 150},
        "email": {"type": "string", "format": "email"},
        "active": {"type": "boolean"},
    },
    "required": ["name", "age"],
}

NESTED_OBJECTS = {
    "title": "Company",
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "address": {
            "type": "object",
            "properties": {
                "street": {"type": "string"},
                "city": {"type": "string"},
                "country": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "code": {"type": "string", "pattern": "^[A-Z]{2}$"},
                    },
                    "required": ["name", "code"],
                },
            },
        },
        "ceo": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "title": {"type": "string"},
            },
        },
    },
}

WITH_REFS = {
    "title": "Order",
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "customer": {"$ref": "#/definitions/Customer"},
        "items": {
            "type": "array",
            "items": {"$ref": "#/definitions/Product"},
        },
        "shipping": {"$ref": "#/definitions/Address"},
    },
    "required": ["id", "customer", "items"],
    "definitions": {
        "Customer": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string", "format": "email"},
            },
            "required": ["name"],
        },
        "Product": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "price": {"type": "number", "minimum": 0},
                "quantity": {"type": "integer", "minimum": 1},
            },
            "required": ["name", "price"],
        },
        "Address": {
            "type": "object",
            "properties": {
                "street": {"type": "string"},
                "city": {"type": "string"},
                "zip": {"type": "string"},
            },
        },
    },
}

COMBINERS = {
    "title": "Shape",
    "type": "object",
    "properties": {
        "shape": {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "type": {"const": "circle"},
                        "radius": {"type": "number", "exclusiveMinimum": 0},
                    },
                    "required": ["type", "radius"],
                },
                {
                    "type": "object",
                    "properties": {
                        "type": {"const": "rectangle"},
                        "width": {"type": "number", "exclusiveMinimum": 0},
                        "height": {"type": "number", "exclusiveMinimum": 0},
                    },
                    "required": ["type", "width", "height"],
                },
                {
                    "type": "object",
                    "properties": {
                        "type": {"const": "triangle"},
                        "base": {"type": "number"},
                        "height": {"type": "number"},
                    },
                    "required": ["type", "base", "height"],
                },
            ]
        },
        "color": {
            "anyOf": [
                {"type": "string"},
                {
                    "type": "object",
                    "properties": {
                        "r": {"type": "integer", "minimum": 0, "maximum": 255},
                        "g": {"type": "integer", "minimum": 0, "maximum": 255},
                        "b": {"type": "integer", "minimum": 0, "maximum": 255},
                    },
                },
            ]
        },
        "metadata": {
            "allOf": [
                {
                    "type": "object",
                    "properties": {"created_by": {"type": "string"}},
                    "required": ["created_by"],
                },
                {
                    "type": "object",
                    "properties": {"version": {"type": "integer", "minimum": 1}},
                },
            ]
        },
    },
}

WIDE_OBJECT = {
    "title": "BigForm",
    "type": "object",
    "properties": {
        f"field_{i}": {
            "type": ["string", "integer", "null"][i % 3],
            **({"minLength": 1} if i % 3 == 0 else {}),
            **({"minimum": 0} if i % 3 == 1 else {}),
        }
        for i in range(50)
    },
    "required": [f"field_{i}" for i in range(0, 50, 2)],
}

MANY_ENUMS = {
    "title": "Config",
    "type": "object",
    "properties": {
        "log_level": {"enum": ["debug", "info", "warn", "error", "fatal"]},
        "env": {"enum": ["dev", "staging", "prod"]},
        "region": {"enum": [f"region-{i}" for i in range(20)]},
        "status": {"const": "active"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
            "minItems": 1,
            "maxItems": 10,
        },
    },
    "required": ["log_level", "env", "region"],
}


# ── Benchmark runner ─────────────────────────────────────────────────────────

SCHEMAS = {
    "simple_object": SIMPLE_OBJECT,
    "nested_3_levels": NESTED_OBJECTS,
    "with_refs": WITH_REFS,
    "combiners": COMBINERS,
    "wide_50_fields": WIDE_OBJECT,
    "enums_and_arrays": MANY_ENUMS,
}

ITERATIONS = 200
WARMUP = 10


def bench(create_fn, schema, iterations):
    """Run create_fn(schema) `iterations` times, return list of durations in µs."""
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        create_fn(schema)
        elapsed = (time.perf_counter() - start) * 1_000_000
        times.append(elapsed)
    return times


def fmt(us):
    if us >= 1000:
        return f"{us / 1000:.2f} ms"
    return f"{us:.1f} µs"


def main():
    from json_schema_to_pydantic import create_model as create_original
    from json_schema_to_pydantic_rs import create_model as create_rs
    from json_schema_to_pydantic_rs._core import process_json_schema

    # ── End-to-end comparison ────────────────────────────────────────────
    print(f"Benchmarking {ITERATIONS} iterations per schema (+ {WARMUP} warmup)\n")
    print("End-to-end (schema → Pydantic model):")
    print(f"{'Schema':<22} {'Original (median)':>18} {'Rust (median)':>18} {'Speedup':>10}")
    print("─" * 72)

    for name, schema in SCHEMAS.items():
        for _ in range(WARMUP):
            create_original(schema)
            create_rs(schema)

        t_orig = bench(create_original, schema, ITERATIONS)
        t_rs = bench(create_rs, schema, ITERATIONS)

        med_orig = statistics.median(t_orig)
        med_rs = statistics.median(t_rs)
        speedup = med_orig / med_rs if med_rs > 0 else float("inf")

        print(f"{name:<22} {fmt(med_orig):>18} {fmt(med_rs):>18} {speedup:>9.2f}x")

    # ── Rust core only (schema processing, no Pydantic model building) ──
    print()
    print("Rust core only (schema parsing + ref resolution + constraint extraction):")
    print(f"{'Schema':<22} {'Rust core (median)':>18}")
    print("─" * 44)

    for name, schema in SCHEMAS.items():
        for _ in range(WARMUP):
            process_json_schema(schema)

        t_core = bench(process_json_schema, schema, ITERATIONS)
        med_core = statistics.median(t_core)

        print(f"{name:<22} {fmt(med_core):>18}")

    print()


if __name__ == "__main__":
    main()
