"""
Contract tests for schema evolution and backward compatibility.

These tests ensure that schema changes are backward compatible
and that producers and consumers remain in sync.
"""

import json
from pathlib import Path

import pytest
import jsonschema
from jsonschema import validate, Draft7Validator


# Fixture data representing various event versions
V1_SHIPMENT_CREATED = {
    "shipment_id": "SHIP-001",
    "tracking_number": "1Z999AA10123456784",
    "carrier_id": "carrier-ups",
    "service_level": "ground",
    "origin_address": {
        "street": "123 Main St",
        "city": "San Francisco",
        "state": "CA",
        "postal_code": "94102",
    },
    "destination_address": {
        "street": "456 Oak Ave",
        "city": "Los Angeles",
        "state": "CA",
        "postal_code": "90001",
    },
}

V1_DELIVERY_COMPLETED = {
    "delivery_id": "DEL-001",
    "shipment_id": "SHIP-001",
    "driver_id": "driver-123",
    "completed_at": "2024-01-16T14:45:00Z",
    "delivery_location": "front_door",
    "location": {
        "latitude": 34.0522,
        "longitude": -118.2437,
    },
}


class TestSchemaValidation:
    """Test that fixtures validate against schemas."""

    @pytest.fixture
    def schema_dir(self) -> Path:
        """Get the schema directory."""
        return Path(__file__).parent.parent.parent / "config" / "event_schemas"

    def load_schema(self, schema_dir: Path, name: str) -> dict:
        """Load a JSON schema file."""
        schema_path = schema_dir / f"{name}.json"
        if not schema_path.exists():
            pytest.skip(f"Schema file not found: {schema_path}")
        with open(schema_path) as f:
            return json.load(f)

    def test_v1_shipment_created_validates(self, schema_dir):
        """Test that v1 shipment.created fixture validates."""
        schema = self.load_schema(schema_dir, "shipment.created")
        validate(instance=V1_SHIPMENT_CREATED, schema=schema)

    def test_v1_delivery_completed_validates(self, schema_dir):
        """Test that v1 delivery.completed fixture validates."""
        schema = self.load_schema(schema_dir, "delivery.completed")
        validate(instance=V1_DELIVERY_COMPLETED, schema=schema)

    def test_shipment_created_missing_required_fails(self, schema_dir):
        """Test that missing required field fails validation."""
        schema = self.load_schema(schema_dir, "shipment.created")

        incomplete = {
            "tracking_number": "1Z999",
            # Missing shipment_id, carrier_id, etc.
        }

        with pytest.raises(jsonschema.ValidationError):
            validate(instance=incomplete, schema=schema)

    def test_shipment_created_invalid_service_level_fails(self, schema_dir):
        """Test that invalid enum value fails validation."""
        schema = self.load_schema(schema_dir, "shipment.created")

        invalid = V1_SHIPMENT_CREATED.copy()
        invalid["service_level"] = "invalid_service"

        with pytest.raises(jsonschema.ValidationError):
            validate(instance=invalid, schema=schema)


class TestBackwardCompatibility:
    """Test backward compatibility of schema changes."""

    def test_adding_optional_field_is_backward_compatible(self):
        """Test that adding optional fields is backward compatible."""
        # v1 schema: required fields only
        v1_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["shipment_id"],
            "properties": {
                "shipment_id": {"type": "string"},
            },
        }

        # v2 schema: adds optional field
        v2_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["shipment_id"],
            "properties": {
                "shipment_id": {"type": "string"},
                "new_optional_field": {"type": "string"},  # New optional field
            },
        }

        # v1 data should validate against both schemas
        v1_data = {"shipment_id": "SHIP-001"}

        validate(instance=v1_data, schema=v1_schema)
        validate(instance=v1_data, schema=v2_schema)  # Should still work

    def test_adding_required_field_breaks_compatibility(self):
        """Test that adding required fields breaks backward compatibility."""
        v1_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["shipment_id"],
            "properties": {
                "shipment_id": {"type": "string"},
            },
        }

        # v2 schema with new required field (BAD!)
        v2_schema_breaking = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["shipment_id", "new_required_field"],  # Breaking change!
            "properties": {
                "shipment_id": {"type": "string"},
                "new_required_field": {"type": "string"},
            },
        }

        v1_data = {"shipment_id": "SHIP-001"}

        validate(instance=v1_data, schema=v1_schema)

        # v1 data fails against v2 schema
        with pytest.raises(jsonschema.ValidationError):
            validate(instance=v1_data, schema=v2_schema_breaking)

    def test_widening_type_is_backward_compatible(self):
        """Test that widening types is backward compatible."""
        # v1: only allows string
        v1_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
        }

        # v2: allows string or number (widened)
        v2_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "value": {"type": ["string", "number"]},
            },
        }

        v1_data = {"value": "test"}

        validate(instance=v1_data, schema=v1_schema)
        validate(instance=v1_data, schema=v2_schema)

    def test_narrowing_type_breaks_compatibility(self):
        """Test that narrowing types breaks forward compatibility."""
        # v1: allows string or number
        v1_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "value": {"type": ["string", "number"]},
            },
        }

        # v2: only allows string (narrowed - BAD for consumers!)
        v2_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "value": {"type": "string"},
            },
        }

        # Data valid in v1 but not v2
        v1_data_number = {"value": 123}

        validate(instance=v1_data_number, schema=v1_schema)

        with pytest.raises(jsonschema.ValidationError):
            validate(instance=v1_data_number, schema=v2_schema)


class TestProducerConsumerContract:
    """Test contracts between producers and consumers."""

    def test_producer_output_matches_consumer_input(self):
        """Test that producer output validates against consumer schema."""
        # Simulated producer output
        producer_event = {
            "shipment_id": "SHIP-001",
            "tracking_number": "1Z999AA10123456784",
            "carrier_id": "carrier-ups",
            "service_level": "ground",
            "origin_address": {
                "street": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94102",
            },
            "destination_address": {
                "street": "456 Oak Ave",
                "city": "Los Angeles",
                "state": "CA",
                "postal_code": "90001",
            },
        }

        # Consumer schema (what the pipeline expects)
        consumer_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["shipment_id"],
            "properties": {
                "shipment_id": {"type": "string"},
                "tracking_number": {"type": "string"},
                "carrier_id": {"type": "string"},
            },
        }

        validate(instance=producer_event, schema=consumer_schema)

    def test_all_producer_fixtures_validate(self):
        """Test that all producer fixtures validate against schemas."""
        fixtures = [
            ("shipment", V1_SHIPMENT_CREATED),
            ("delivery", V1_DELIVERY_COMPLETED),
        ]

        # Minimal consumer schema that accepts all event types
        consumer_schema = {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "shipment_id": {"type": "string"},
                "delivery_id": {"type": "string"},
            },
        }

        for name, fixture in fixtures:
            validate(instance=fixture, schema=consumer_schema)
