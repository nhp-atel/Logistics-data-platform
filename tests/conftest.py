"""
Pytest configuration and fixtures for the test suite.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Set environment for testing
os.environ["ENVIRONMENT"] = "test"
os.environ["GCP_PROJECT_ID"] = "test-project"


@pytest.fixture
def sample_event_dict() -> dict[str, Any]:
    """Return a sample event dictionary."""
    return {
        "event_id": "test-event-123",
        "event_type": "shipment.created",
        "event_version": "v1",
        "event_time": "2024-01-15T10:30:00Z",
        "source_system": "order-service",
        "trace_id": "trace-abc-123",
        "payload": {
            "shipment_id": "SHIP-001",
            "tracking_number": "1Z999AA10123456784",
            "carrier_id": "carrier-ups",
            "service_level": "ground",
            "origin_address": {
                "street": "123 Main St",
                "city": "San Francisco",
                "state": "CA",
                "postal_code": "94102",
                "country": "US",
            },
            "destination_address": {
                "street": "456 Oak Ave",
                "city": "Los Angeles",
                "state": "CA",
                "postal_code": "90001",
                "country": "US",
            },
        },
    }


@pytest.fixture
def sample_delivery_event_dict() -> dict[str, Any]:
    """Return a sample delivery completed event."""
    return {
        "event_id": "test-delivery-456",
        "event_type": "delivery.completed",
        "event_version": "v1",
        "event_time": "2024-01-16T14:45:00Z",
        "source_system": "delivery-app",
        "payload": {
            "delivery_id": "DEL-001",
            "shipment_id": "SHIP-001",
            "driver_id": "driver-123",
            "completed_at": "2024-01-16T14:45:00Z",
            "delivery_location": "front_door",
            "location": {
                "latitude": 34.0522,
                "longitude": -118.2437,
            },
            "attempt_count": 1,
            "was_on_time": True,
        },
    }


@pytest.fixture
def sample_event_envelope():
    """Return a sample EventEnvelope instance."""
    from src.common.schemas import EventEnvelope

    return EventEnvelope(
        event_id="test-event-123",
        event_type="shipment.created",
        event_version="v1",
        event_time=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        ingest_time=datetime(2024, 1, 15, 10, 30, 1, tzinfo=timezone.utc),
        source_system="order-service",
        payload={
            "shipment_id": "SHIP-001",
            "tracking_number": "1Z999AA10123456784",
            "carrier_id": "carrier-ups",
        },
        trace_id="trace-abc-123",
    )


@pytest.fixture
def sample_pubsub_message():
    """Return a sample Pub/Sub message mock."""
    from apache_beam.io.gcp.pubsub import PubsubMessage

    message_data = json.dumps({
        "event_id": "test-event-123",
        "event_type": "shipment.created",
        "payload": {
            "shipment_id": "SHIP-001",
        },
    }).encode("utf-8")

    return PubsubMessage(
        data=message_data,
        attributes={
            "event_time": "2024-01-15T10:30:00Z",
            "source_system": "order-service",
        },
    )


@pytest.fixture
def mock_bigquery_client():
    """Return a mock BigQuery client."""
    client = MagicMock()
    client.project = "test-project"
    return client


@pytest.fixture
def test_config_dir(tmp_path) -> Path:
    """Create a temporary config directory with test configs."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create base config
    base_config = {
        "environment": "test",
        "log_level": "DEBUG",
        "gcp": {
            "project_id": "test-project",
            "region": "us-central1",
        },
        "streaming": {
            "window_duration_seconds": 60,
            "dedupe_window_hours": 1,
        },
    }

    with open(config_dir / "base.yaml", "w") as f:
        import yaml
        yaml.dump(base_config, f)

    return config_dir


@pytest.fixture
def schema_dir(tmp_path) -> Path:
    """Create a temporary schema directory with test schemas."""
    schema_dir = tmp_path / "event_schemas"
    schema_dir.mkdir()

    # Create a simple schema
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "required": ["shipment_id"],
        "properties": {
            "shipment_id": {"type": "string"},
            "tracking_number": {"type": "string"},
        },
    }

    with open(schema_dir / "shipment.json", "w") as f:
        json.dump(schema, f)

    return schema_dir


@pytest.fixture
def multiple_events():
    """Return a list of sample events for batch testing."""
    from src.common.schemas import EventEnvelope

    base_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

    events = []
    for i in range(10):
        events.append(EventEnvelope(
            event_id=f"event-{i:03d}",
            event_type="shipment.created" if i % 2 == 0 else "shipment.updated",
            event_version="v1",
            event_time=base_time.replace(minute=i),
            ingest_time=base_time.replace(minute=i, second=1),
            source_system="test-system",
            payload={"shipment_id": f"SHIP-{i:03d}"},
        ))

    return events


@pytest.fixture
def duplicate_events(sample_event_envelope):
    """Return a list of events with duplicates."""
    from src.common.schemas import EventEnvelope

    events = [
        sample_event_envelope,
        EventEnvelope(
            event_id=sample_event_envelope.event_id,  # Same ID = duplicate
            event_type=sample_event_envelope.event_type,
            event_version=sample_event_envelope.event_version,
            event_time=sample_event_envelope.event_time,
            ingest_time=sample_event_envelope.ingest_time,
            source_system=sample_event_envelope.source_system,
            payload=sample_event_envelope.payload,
        ),
        EventEnvelope(
            event_id="different-event-id",  # Different ID = not duplicate
            event_type=sample_event_envelope.event_type,
            event_version=sample_event_envelope.event_version,
            event_time=sample_event_envelope.event_time,
            ingest_time=sample_event_envelope.ingest_time,
            source_system=sample_event_envelope.source_system,
            payload=sample_event_envelope.payload,
        ),
    ]

    return events
