"""
Unit tests for the validate transform.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.common.schemas import EventEnvelope
from src.streaming.transforms.validate import ValidateSchema


class TestValidateSchema:
    """Tests for ValidateSchema DoFn."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = ValidateSchema()
        self.validator.setup()

    def create_envelope(
        self,
        event_type: str = "shipment.created",
        payload: dict | None = None,
        event_id: str = "test-123",
    ) -> EventEnvelope:
        """Helper to create test envelopes."""
        return EventEnvelope(
            event_id=event_id,
            event_type=event_type,
            event_version="v1",
            event_time=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            source_system="test",
            payload=payload or {"shipment_id": "SHIP-001"},
        )

    def test_validate_valid_shipment_event(self):
        """Test validating a valid shipment event."""
        envelope = self.create_envelope(
            event_type="shipment.created",
            payload={"shipment_id": "SHIP-001", "tracking_number": "1Z999"},
        )

        results = list(self.validator.process(envelope))

        # Should have one result tagged as valid
        assert len(results) == 1
        assert results[0].tag == ValidateSchema.VALID_TAG
        assert results[0].value.event_id == "test-123"

    def test_validate_missing_event_id(self):
        """Test that missing event_id is flagged."""
        envelope = EventEnvelope(
            event_id="",  # Empty event ID
            event_type="shipment.created",
            event_version="v1",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            source_system="test",
            payload={"shipment_id": "SHIP-001"},
        )

        results = list(self.validator.process(envelope))

        assert len(results) == 1
        assert results[0].tag == ValidateSchema.INVALID_TAG

    def test_validate_missing_event_type(self):
        """Test that missing event_type is flagged."""
        envelope = EventEnvelope(
            event_id="test-123",
            event_type="",  # Empty event type
            event_version="v1",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            source_system="test",
            payload={"shipment_id": "SHIP-001"},
        )

        results = list(self.validator.process(envelope))

        assert len(results) == 1
        assert results[0].tag == ValidateSchema.INVALID_TAG

    def test_validate_invalid_event_type_format(self):
        """Test that invalid event type format is flagged."""
        envelope = self.create_envelope(
            event_type="invalid_format",  # Missing dot separator
            payload={"shipment_id": "SHIP-001"},
        )

        results = list(self.validator.process(envelope))

        assert len(results) == 1
        assert results[0].tag == ValidateSchema.INVALID_TAG

    def test_validate_shipment_event_missing_shipment_id(self):
        """Test that shipment event without shipment_id is flagged."""
        envelope = self.create_envelope(
            event_type="shipment.created",
            payload={"tracking_number": "1Z999"},  # No shipment_id
        )

        results = list(self.validator.process(envelope))

        assert len(results) == 1
        result = results[0]
        assert result.tag == ValidateSchema.INVALID_TAG
        assert "_validation_errors" in result.value.payload

    def test_validate_delivery_event_missing_delivery_id(self):
        """Test that delivery event without delivery_id is flagged."""
        envelope = self.create_envelope(
            event_type="delivery.completed",
            payload={"shipment_id": "SHIP-001"},  # No delivery_id
        )

        results = list(self.validator.process(envelope))

        assert len(results) == 1
        assert results[0].tag == ValidateSchema.INVALID_TAG

    def test_validate_driver_event_missing_driver_id(self):
        """Test that driver event without driver_id is flagged."""
        envelope = self.create_envelope(
            event_type="driver.assigned",
            payload={"route_id": "ROUTE-001"},  # No driver_id
        )

        results = list(self.validator.process(envelope))

        assert len(results) == 1
        assert results[0].tag == ValidateSchema.INVALID_TAG

    def test_validate_facility_event_missing_facility_id(self):
        """Test that facility event without facility_id is flagged."""
        envelope = self.create_envelope(
            event_type="facility.updated",
            payload={"capacity": 1000},  # No facility_id
        )

        results = list(self.validator.process(envelope))

        assert len(results) == 1
        assert results[0].tag == ValidateSchema.INVALID_TAG

    def test_validate_unknown_domain_passes(self):
        """Test that unknown domain events pass basic validation."""
        envelope = self.create_envelope(
            event_type="custom.event",
            payload={"custom_field": "value"},
        )

        results = list(self.validator.process(envelope))

        # Unknown domains should pass (no domain-specific rules)
        assert len(results) == 1
        assert results[0].tag == ValidateSchema.VALID_TAG

    def test_validate_errors_attached_to_payload(self):
        """Test that validation errors are attached to the payload."""
        envelope = self.create_envelope(
            event_type="shipment.created",
            payload={},  # Missing required fields
        )

        results = list(self.validator.process(envelope))

        assert len(results) == 1
        result = results[0]
        assert result.tag == ValidateSchema.INVALID_TAG
        assert "_validation_errors" in result.value.payload
        errors = result.value.payload["_validation_errors"]
        assert len(errors) > 0
        assert all("field" in e and "message" in e for e in errors)


class TestValidateSchemaWithSchemaFiles:
    """Tests for ValidateSchema with actual JSON schema files."""

    @pytest.fixture
    def schema_validator(self, schema_dir):
        """Create validator with test schema directory."""
        validator = ValidateSchema(schema_dir=str(schema_dir))
        validator.setup()
        return validator

    def test_validate_against_json_schema(self, schema_validator):
        """Test validation against JSON schema file."""
        envelope = EventEnvelope(
            event_id="test-123",
            event_type="shipment",
            event_version="v1",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            source_system="test",
            payload={"shipment_id": "SHIP-001"},
        )

        results = list(schema_validator.process(envelope))

        assert len(results) == 1
        # Should pass since payload has shipment_id
        assert results[0].tag == ValidateSchema.VALID_TAG

    def test_validate_schema_violation(self, schema_validator):
        """Test that schema violations are detected."""
        envelope = EventEnvelope(
            event_id="test-123",
            event_type="shipment",
            event_version="v1",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            source_system="test",
            payload={"wrong_field": "value"},  # Missing required shipment_id
        )

        results = list(schema_validator.process(envelope))

        assert len(results) == 1
        assert results[0].tag == ValidateSchema.INVALID_TAG
