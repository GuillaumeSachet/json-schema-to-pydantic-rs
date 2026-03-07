import pytest
from pydantic import BaseModel, Field, ValidationError

from json_schema_to_pydantic_rs import (
    PydanticModelBuilder,
    SchemaError,
    create_model,
)


class CustomBaseModel(BaseModel):
    test_case: str = Field(default="test", description="A test case")


def test_basic_model_creation():
    builder = PydanticModelBuilder(base_model_type=CustomBaseModel)
    schema = {
        "title": "TestModel",
        "description": "A test model",
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"],
    }

    model = builder.create_pydantic_model(schema)

    assert model.__name__ == "TestModel"
    assert model.__doc__ == "A test model"
    assert issubclass(model, CustomBaseModel)

    instance = model(name="test", age=25)
    assert instance.name == "test"
    assert instance.age == 25

    with pytest.raises(ValueError):
        model(age=25)


def test_model_builder_constructor_with_undefined_arrays():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"data": {"type": "array"}},
    }

    model = builder.create_pydantic_model(schema, allow_undefined_array_items=True)
    instance = model(data=[1, 2, 3])
    assert instance.data == [1, 2, 3]


def test_nested_model_creation():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "address": {
                        "type": "object",
                        "properties": {"street": {"type": "string"}},
                    },
                },
            }
        },
    }

    model = builder.create_pydantic_model(schema)
    instance = model(user={"name": "John", "address": {"street": "Main St"}})

    assert isinstance(instance.user, BaseModel)
    assert isinstance(instance.user.address, BaseModel)
    assert instance.user.name == "John"
    assert instance.user.address.street == "Main St"


def test_model_with_references():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"current_pet": {"$ref": "#/definitions/Pet"}},
        "definitions": {
            "Pet": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "type": {"type": "string"}},
            }
        },
    }

    model = builder.create_pydantic_model(schema)
    instance = model(current_pet={"name": "Fluffy", "type": "cat"})

    assert isinstance(instance.current_pet, BaseModel)
    assert instance.current_pet.name == "Fluffy"


def test_predefined_models_builder_reuses_definition_model():
    class PetModel(BaseModel):
        name: str
        type: str

    builder = PydanticModelBuilder(predefined_models={"#/definitions/Pet": PetModel})
    schema = {
        "type": "object",
        "properties": {"current_pet": {"$ref": "#/definitions/Pet"}},
        "definitions": {
            "Pet": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "type": {"type": "string"}},
            }
        },
    }

    model = builder.create_pydantic_model(schema)
    instance = model(current_pet={"name": "Fluffy", "type": "cat"})
    assert type(instance.current_pet) is PetModel


def test_predefined_models_create_model_reuses_defs_model():
    class SharedType(BaseModel):
        value: str

    schema = {
        "type": "object",
        "properties": {"shared": {"$ref": "#/$defs/SharedType"}},
        "$defs": {
            "SharedType": {
                "type": "object",
                "properties": {"value": {"type": "string"}},
            }
        },
    }

    model = create_model(schema, predefined_models={"#/$defs/SharedType": SharedType})
    instance = model(shared={"value": "ok"})
    assert type(instance.shared) is SharedType


def test_predefined_models_validation_requires_local_ref_keys():
    with pytest.raises(ValueError, match="Keys must be local JSON Pointer refs"):
        PydanticModelBuilder(predefined_models={"http://example.com/Pet": BaseModel})


def test_predefined_models_validation_rejects_empty_pointer_segments():
    with pytest.raises(ValueError, match="without empty path segments"):
        PydanticModelBuilder(predefined_models={"#/": BaseModel})

    with pytest.raises(ValueError, match="without empty path segments"):
        PydanticModelBuilder(predefined_models={"#/definitions//Pet": BaseModel})


def test_predefined_models_validation_requires_basemodel_subclasses():
    with pytest.raises(ValueError, match="must be subclasses of pydantic.BaseModel"):
        PydanticModelBuilder(predefined_models={"#/definitions/Pet": str})


def test_predefined_models_validation_requires_subclass_of_configured_base():
    class CustomBase(BaseModel):
        base_field: str = "x"

    class DifferentBase(BaseModel):
        pass

    with pytest.raises(ValueError, match="must be subclasses of the configured base_model_type"):
        PydanticModelBuilder(
            base_model_type=CustomBase,
            predefined_models={"#/definitions/Pet": DifferentBase},
        )


def test_predefined_models_validation_requires_mapping():
    with pytest.raises(ValueError, match="predefined_models must be a dict"):
        PydanticModelBuilder(predefined_models=[])


def test_nested_undefined_array_items():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "tags": {"type": "array"},
                },
            }
        },
    }

    with pytest.raises(ValueError):
        builder.create_pydantic_model(schema)

    model = builder.create_pydantic_model(schema, allow_undefined_array_items=True)
    instance = model(user={"name": "John", "tags": ["admin", "user"]})
    assert instance.user.name == "John"
    assert instance.user.tags == ["admin", "user"]


def test_undefined_array_items():
    builder = PydanticModelBuilder()
    schema = {"type": "object", "properties": {"tags": {"type": "array"}}}

    with pytest.raises(ValueError, match="Array type must specify 'items' schema"):
        builder.create_pydantic_model(schema)

    model = builder.create_pydantic_model(schema, allow_undefined_array_items=True)
    instance = model(tags=["tag1", "tag2"])
    assert instance.tags == ["tag1", "tag2"]

    instance = model(tags=[1, "two", 3.0, True])
    assert instance.tags == [1, "two", 3.0, True]


def test_undefined_type():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {"metadata": {"description": "Any metadata"}},
    }

    with pytest.raises(ValueError, match="Schema must specify a type"):
        builder.create_pydantic_model(schema)

    model = builder.create_pydantic_model(schema, allow_undefined_type=True)
    instance = model(metadata={"key": "value"})
    assert instance.metadata == {"key": "value"}

    instance = model(metadata=[1, "two", 3.0, True])
    assert instance.metadata == [1, "two", 3.0, True]


def test_create_model_function():
    schema = {"type": "object", "properties": {"tools": {"type": "array"}}}

    with pytest.raises(ValueError):
        create_model(schema)

    model = create_model(schema, allow_undefined_array_items=True)
    instance = model(tools=["hammer", "screwdriver"])
    assert instance.tools == ["hammer", "screwdriver"]


def test_json_schema_extra_field_level():
    builder = PydanticModelBuilder()
    schema = {
        "title": "FieldTestModel",
        "type": "object",
        "properties": {
            "field_with_extra": {
                "type": "string",
                "description": "A field with extra properties",
                "is_core_field": True,
                "custom_validation": "email",
                "ui_hint": "large_text",
            },
            "normal_field": {"type": "integer", "description": "A normal field"},
        },
        "required": ["field_with_extra"],
    }

    model = builder.create_pydantic_model(schema)

    field_info = model.model_fields["field_with_extra"]
    assert field_info.json_schema_extra == {
        "is_core_field": True,
        "custom_validation": "email",
        "ui_hint": "large_text",
    }
    assert field_info.description == "A field with extra properties"

    normal_field_info = model.model_fields["normal_field"]
    assert normal_field_info.json_schema_extra is None
    assert normal_field_info.description == "A normal field"


def test_json_schema_extra_model_level():
    builder = PydanticModelBuilder()
    schema = {
        "title": "ModelTestModel",
        "type": "object",
        "description": "A model with extra properties",
        "properties": {"field": {"type": "string"}},
        "examples": [{"field": "example_value"}],
        "ui_config": {"theme": "dark"},
        "version": "1.0.0",
    }

    model = builder.create_pydantic_model(schema)
    generated_schema = model.model_json_schema()

    assert "examples" in generated_schema
    assert generated_schema["examples"] == [{"field": "example_value"}]
    assert "ui_config" in generated_schema
    assert generated_schema["ui_config"] == {"theme": "dark"}
    assert "version" in generated_schema
    assert generated_schema["version"] == "1.0.0"
    assert generated_schema["title"] == "ModelTestModel"


@pytest.mark.parametrize("populate_by_name", [True, False])
def test_model_with_underscore_property(populate_by_name):
    builder = PydanticModelBuilder(base_model_type=CustomBaseModel)
    schema = {
        "title": "TestModel",
        "description": "A test model",
        "type": "object",
        "properties": {"_name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["_name"],
    }

    model = builder.create_pydantic_model(schema, populate_by_name=populate_by_name)

    assert model.__name__ == "TestModel"
    assert issubclass(model, CustomBaseModel)

    instance = model(_name="test", age=25)
    assert instance.name == "test"
    assert instance.age == 25
    assert instance.model_dump(by_alias=True) == {
        "_name": "test",
        "age": 25,
        "test_case": "test",
    }

    if populate_by_name:
        instance = model(name="test2", age=30)
        assert instance.name == "test2"
    else:
        with pytest.raises(ValidationError, match="1 validation error for TestModel\n_name"):
            model(name="test", age=25)


def test_model_with_underscore_collision():
    builder = PydanticModelBuilder()
    schema = {
        "title": "CollisionModel",
        "type": "object",
        "properties": {"_name": {"type": "string"}, "name": {"type": "string"}},
        "required": ["_name", "name"],
    }

    with pytest.raises(ValueError, match="Duplicate field name after sanitization"):
        builder.create_pydantic_model(schema)


def test_root_level_features():
    builder = PydanticModelBuilder()
    schema = {
        "title": "CustomModel",
        "description": "A model with root level features",
        "type": "object",
        "properties": {"field": {"type": "string"}},
        "$defs": {
            "SubType": {
                "type": "object",
                "properties": {"subfield": {"type": "string"}},
            }
        },
    }

    model = builder.create_pydantic_model(schema)
    assert model.__name__ == "CustomModel"
    assert model.__doc__ == "A model with root level features"

    schema_with_ref = {
        "type": "object",
        "properties": {"sub": {"$ref": "#/$defs/SubType"}},
    }
    model_with_ref = builder.create_pydantic_model(schema_with_ref, schema)
    instance = model_with_ref(sub={"subfield": "test"})
    assert instance.sub.subfield == "test"


def test_complex_schema_with_undefined_arrays():
    builder = PydanticModelBuilder()
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "tags": {"type": "array"},
            "metadata": {
                "type": "object",
                "properties": {
                    "categories": {"type": "array"},
                    "flags": {"type": "array"},
                },
            },
            "history": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "timestamp": {"type": "string"},
                        "actions": {"type": "array"},
                    },
                },
            },
        },
    }

    model = builder.create_pydantic_model(schema, allow_undefined_array_items=True)

    instance = model(
        name="Test",
        tags=["important", "urgent"],
        metadata={"categories": ["A", "B", "C"], "flags": [True, False, True]},
        history=[
            {"timestamp": "2023-01-01", "actions": ["created", "modified"]},
            {"timestamp": "2023-01-02", "actions": ["reviewed", 123]},
        ],
    )

    assert instance.name == "Test"
    assert instance.tags == ["important", "urgent"]
    assert instance.metadata.categories == ["A", "B", "C"]
    assert instance.history[0].timestamp == "2023-01-01"
    assert instance.history[0].actions == ["created", "modified"]
