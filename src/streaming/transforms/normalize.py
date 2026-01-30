"""
Normalize incoming messages to EventEnvelope format.
"""

import json
from datetime import datetime, timezone
from typing import Any, Iterator
import uuid

import apache_beam as beam
from apache_beam.io.gcp.pubsub import PubsubMessage

from src.common.schemas import EventEnvelope
from src.common.logging_utils import get_logger
from src.common.metrics import beam_metrics

logger = get_logger(__name__)


class NormalizeToEnvelope(beam.DoFn):
    """
    Normalize incoming Pub/Sub messages to EventEnvelope format.

    Handles various input formats and extracts event metadata from
    message attributes or payload fields.
    """

    def __init__(self):
        super().__init__()
        self._counter_success = None
        self._counter_error = None

    def setup(self):
        """Initialize counters."""
        self._counter_success = beam_metrics.get_counter("normalize_success")
        self._counter_error = beam_metrics.get_counter("normalize_error")

    def process(self, message: PubsubMessage) -> Iterator[EventEnvelope]:
        """
        Process a Pub/Sub message and yield an EventEnvelope.

        Args:
            message: Incoming Pub/Sub message

        Yields:
            Normalized EventEnvelope
        """
        try:
            # Parse message data
            data = self._parse_message_data(message.data)

            # Extract event metadata
            event_id = self._extract_event_id(data, message.attributes)
            event_type = self._extract_event_type(data, message.attributes)
            event_version = self._extract_event_version(data, message.attributes)
            event_time = self._extract_event_time(data, message.attributes)
            source_system = self._extract_source_system(data, message.attributes)
            trace_id = self._extract_trace_id(data, message.attributes)

            # Extract payload (remaining data after metadata extraction)
            payload = self._extract_payload(data)

            # Create envelope
            envelope = EventEnvelope(
                event_id=event_id,
                event_type=event_type,
                event_version=event_version,
                event_time=event_time,
                ingest_time=datetime.now(timezone.utc),
                source_system=source_system,
                payload=payload,
                trace_id=trace_id,
            )

            self._counter_success.inc()
            yield envelope

        except Exception as e:
            self._counter_error.inc()
            logger.error(
                "Failed to normalize message",
                error=str(e),
                message_id=message.attributes.get("message_id", "unknown"),
            )
            # Re-raise to trigger DLQ routing
            raise

    def _parse_message_data(self, data: bytes) -> dict[str, Any]:
        """Parse message data from bytes to dict."""
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            # Try to handle as raw string
            return {"raw_data": data.decode("utf-8", errors="replace")}
        except Exception as e:
            logger.warning(f"Failed to parse message data: {e}")
            return {"raw_data": str(data)}

    def _extract_event_id(self, data: dict, attributes: dict) -> str:
        """Extract or generate event ID."""
        # Check common field names
        for field in ["event_id", "eventId", "id", "message_id", "messageId"]:
            if field in data:
                return str(data[field])
            if field in attributes:
                return str(attributes[field])

        # Generate new UUID if not found
        return str(uuid.uuid4())

    def _extract_event_type(self, data: dict, attributes: dict) -> str:
        """Extract event type."""
        # Check common field names
        for field in ["event_type", "eventType", "type"]:
            if field in data:
                return str(data[field])
            if field in attributes:
                return str(attributes[field])

        # Try to infer from data structure
        if "shipment_id" in data or "shipmentId" in data:
            return "shipment.unknown"
        if "facility_id" in data or "facilityId" in data:
            return "facility.unknown"
        if "driver_id" in data or "driverId" in data:
            return "driver.unknown"
        if "delivery_id" in data or "deliveryId" in data:
            return "delivery.unknown"

        return "unknown"

    def _extract_event_version(self, data: dict, attributes: dict) -> str:
        """Extract event version."""
        for field in ["event_version", "eventVersion", "version", "schema_version"]:
            if field in data:
                return str(data[field])
            if field in attributes:
                return str(attributes[field])
        return "v1"

    def _extract_event_time(self, data: dict, attributes: dict) -> datetime:
        """Extract event time."""
        for field in ["event_time", "eventTime", "timestamp", "created_at", "occurred_at"]:
            value = data.get(field) or attributes.get(field)
            if value:
                return self._parse_timestamp(value)

        return datetime.now(timezone.utc)

    def _parse_timestamp(self, value: Any) -> datetime:
        """Parse timestamp from various formats."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            # Handle ISO format with optional Z suffix
            value = value.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        if isinstance(value, (int, float)):
            # Assume Unix timestamp
            return datetime.fromtimestamp(value, tz=timezone.utc)

        return datetime.now(timezone.utc)

    def _extract_source_system(self, data: dict, attributes: dict) -> str:
        """Extract source system identifier."""
        for field in ["source_system", "sourceSystem", "source", "origin"]:
            if field in data:
                return str(data[field])
            if field in attributes:
                return str(attributes[field])
        return "unknown"

    def _extract_trace_id(self, data: dict, attributes: dict) -> str | None:
        """Extract distributed trace ID."""
        for field in ["trace_id", "traceId", "x-trace-id", "X-Trace-Id", "correlation_id"]:
            if field in data:
                return str(data[field])
            if field in attributes:
                return str(attributes[field])
        return None

    def _extract_payload(self, data: dict) -> dict[str, Any]:
        """Extract payload, removing metadata fields."""
        metadata_fields = {
            "event_id", "eventId", "id", "message_id", "messageId",
            "event_type", "eventType", "type",
            "event_version", "eventVersion", "version", "schema_version",
            "event_time", "eventTime", "timestamp", "created_at", "occurred_at",
            "source_system", "sourceSystem", "source", "origin",
            "trace_id", "traceId", "x-trace-id", "correlation_id",
        }

        # If data has a 'payload' or 'data' field, use that
        if "payload" in data and isinstance(data["payload"], dict):
            return data["payload"]
        if "data" in data and isinstance(data["data"], dict):
            return data["data"]

        # Otherwise, return data without metadata fields
        return {k: v for k, v in data.items() if k not in metadata_fields}
