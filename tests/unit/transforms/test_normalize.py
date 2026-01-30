"""
Unit tests for the normalize transform.
"""

import json
from datetime import datetime, timezone

import pytest
from apache_beam.io.gcp.pubsub import PubsubMessage

from src.streaming.transforms.normalize import NormalizeToEnvelope


class TestNormalizeToEnvelope:
    """Tests for NormalizeToEnvelope DoFn."""

    def setup_method(self):
        """Set up test fixtures."""
        self.normalize = NormalizeToEnvelope()
        self.normalize.setup()

    def test_normalize_basic_message(self):
        """Test normalizing a basic message with all fields."""
        message_data = json.dumps({
            "event_id": "test-123",
            "event_type": "shipment.created",
            "event_version": "v1",
            "event_time": "2024-01-15T10:30:00Z",
            "source_system": "order-service",
            "payload": {
                "shipment_id": "SHIP-001",
            },
        }).encode("utf-8")

        message = PubsubMessage(data=message_data, attributes={})

        results = list(self.normalize.process(message))

        assert len(results) == 1
        envelope = results[0]
        assert envelope.event_id == "test-123"
        assert envelope.event_type == "shipment.created"
        assert envelope.event_version == "v1"
        assert envelope.source_system == "order-service"
        assert envelope.payload["shipment_id"] == "SHIP-001"

    def test_normalize_with_attributes(self):
        """Test extracting metadata from message attributes."""
        message_data = json.dumps({
            "shipment_id": "SHIP-001",
            "tracking_number": "1Z999",
        }).encode("utf-8")

        message = PubsubMessage(
            data=message_data,
            attributes={
                "event_id": "attr-event-123",
                "event_type": "shipment.created",
                "source_system": "external-api",
            },
        )

        results = list(self.normalize.process(message))

        assert len(results) == 1
        envelope = results[0]
        assert envelope.event_id == "attr-event-123"
        assert envelope.event_type == "shipment.created"
        assert envelope.source_system == "external-api"

    def test_normalize_generates_event_id_if_missing(self):
        """Test that event_id is generated if not provided."""
        message_data = json.dumps({
            "event_type": "shipment.created",
            "shipment_id": "SHIP-001",
        }).encode("utf-8")

        message = PubsubMessage(data=message_data, attributes={})

        results = list(self.normalize.process(message))

        assert len(results) == 1
        envelope = results[0]
        # Should have a UUID-format event_id
        assert len(envelope.event_id) == 36
        assert envelope.event_id.count("-") == 4

    def test_normalize_infers_event_type_from_payload(self):
        """Test inferring event type from payload contents."""
        message_data = json.dumps({
            "shipment_id": "SHIP-001",
            "tracking_number": "1Z999",
        }).encode("utf-8")

        message = PubsubMessage(data=message_data, attributes={})

        results = list(self.normalize.process(message))

        assert len(results) == 1
        envelope = results[0]
        assert envelope.event_type == "shipment.unknown"

    def test_normalize_handles_nested_payload(self):
        """Test that nested payload is extracted correctly."""
        message_data = json.dumps({
            "event_id": "test-123",
            "event_type": "shipment.created",
            "payload": {
                "shipment_id": "SHIP-001",
                "nested": {
                    "key": "value",
                },
            },
        }).encode("utf-8")

        message = PubsubMessage(data=message_data, attributes={})

        results = list(self.normalize.process(message))

        assert len(results) == 1
        envelope = results[0]
        assert envelope.payload["shipment_id"] == "SHIP-001"
        assert envelope.payload["nested"]["key"] == "value"

    def test_normalize_parses_timestamp_formats(self):
        """Test parsing various timestamp formats."""
        test_cases = [
            ("2024-01-15T10:30:00Z", datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)),
            ("2024-01-15T10:30:00+00:00", datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)),
        ]

        for timestamp_str, expected in test_cases:
            message_data = json.dumps({
                "event_id": "test-123",
                "event_type": "shipment.created",
                "event_time": timestamp_str,
                "payload": {},
            }).encode("utf-8")

            message = PubsubMessage(data=message_data, attributes={})
            results = list(self.normalize.process(message))

            assert len(results) == 1
            envelope = results[0]
            assert envelope.event_time == expected

    def test_normalize_handles_camelCase_fields(self):
        """Test handling camelCase field names."""
        message_data = json.dumps({
            "eventId": "test-123",
            "eventType": "shipment.created",
            "eventVersion": "v1",
            "eventTime": "2024-01-15T10:30:00Z",
            "sourceSystem": "order-service",
            "payload": {"shipmentId": "SHIP-001"},
        }).encode("utf-8")

        message = PubsubMessage(data=message_data, attributes={})

        results = list(self.normalize.process(message))

        assert len(results) == 1
        envelope = results[0]
        assert envelope.event_id == "test-123"
        assert envelope.event_type == "shipment.created"

    def test_normalize_extracts_trace_id(self):
        """Test extracting trace ID from various field names."""
        for trace_field in ["trace_id", "traceId", "correlation_id"]:
            message_data = json.dumps({
                "event_id": "test-123",
                "event_type": "shipment.created",
                trace_field: "trace-abc-123",
                "payload": {},
            }).encode("utf-8")

            message = PubsubMessage(data=message_data, attributes={})
            results = list(self.normalize.process(message))

            assert len(results) == 1
            assert results[0].trace_id == "trace-abc-123"

    def test_normalize_sets_ingest_time(self):
        """Test that ingest_time is set to current time."""
        message_data = json.dumps({
            "event_id": "test-123",
            "event_type": "shipment.created",
            "payload": {},
        }).encode("utf-8")

        message = PubsubMessage(data=message_data, attributes={})

        before = datetime.now(timezone.utc)
        results = list(self.normalize.process(message))
        after = datetime.now(timezone.utc)

        assert len(results) == 1
        envelope = results[0]
        assert before <= envelope.ingest_time <= after
