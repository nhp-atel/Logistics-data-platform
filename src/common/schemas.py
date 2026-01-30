"""
Event envelope and schema definitions for the logistics platform.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


@dataclass
class EventEnvelope:
    """
    Standard envelope for all events in the logistics platform.

    This envelope provides a consistent structure for event metadata,
    enabling uniform processing across different event types.
    """

    event_id: str
    event_type: str
    event_version: str
    event_time: datetime
    ingest_time: datetime
    source_system: str
    payload: dict[str, Any]
    trace_id: str | None = None

    @classmethod
    def create(
        cls,
        event_type: str,
        payload: dict[str, Any],
        event_version: str = "v1",
        source_system: str = "unknown",
        event_time: datetime | None = None,
        trace_id: str | None = None,
    ) -> "EventEnvelope":
        """
        Create a new event envelope.

        Args:
            event_type: Type of the event (e.g., "shipment.created")
            payload: Event-specific data
            event_version: Schema version of the event
            source_system: System that generated the event
            event_time: When the event occurred (defaults to now)
            trace_id: Optional distributed tracing ID

        Returns:
            A new EventEnvelope instance
        """
        now = datetime.now(timezone.utc)
        return cls(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            event_version=event_version,
            event_time=event_time or now,
            ingest_time=now,
            source_system=source_system,
            payload=payload,
            trace_id=trace_id,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert the envelope to a dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_version": self.event_version,
            "event_time": self.event_time.isoformat(),
            "ingest_time": self.ingest_time.isoformat(),
            "source_system": self.source_system,
            "payload": self.payload,
            "trace_id": self.trace_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EventEnvelope":
        """Create an EventEnvelope from a dictionary."""
        event_time = data.get("event_time")
        if isinstance(event_time, str):
            event_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        elif event_time is None:
            event_time = datetime.now(timezone.utc)

        ingest_time = data.get("ingest_time")
        if isinstance(ingest_time, str):
            ingest_time = datetime.fromisoformat(ingest_time.replace("Z", "+00:00"))
        elif ingest_time is None:
            ingest_time = datetime.now(timezone.utc)

        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=data.get("event_type", "unknown"),
            event_version=data.get("event_version", "v1"),
            event_time=event_time,
            ingest_time=ingest_time,
            source_system=data.get("source_system", "unknown"),
            payload=data.get("payload", {}),
            trace_id=data.get("trace_id"),
        )

    @property
    def dedupe_key(self) -> str:
        """Get the deduplication key for this event."""
        return f"{self.event_type}:{self.event_id}"

    def get_domain(self) -> str:
        """Extract the domain from the event type (e.g., 'shipment' from 'shipment.created')."""
        parts = self.event_type.split(".")
        return parts[0] if parts else "unknown"

    def get_action(self) -> str:
        """Extract the action from the event type (e.g., 'created' from 'shipment.created')."""
        parts = self.event_type.split(".")
        return parts[1] if len(parts) > 1 else "unknown"


@dataclass
class ProcessingResult:
    """Result of processing an event through the pipeline."""

    event: EventEnvelope
    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0

    @property
    def is_valid(self) -> bool:
        """Check if the event passed validation."""
        return self.success and not self.errors


@dataclass
class ValidationError:
    """Details of a validation error."""

    field: str
    message: str
    error_code: str
    value: Any = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "field": self.field,
            "message": self.message,
            "error_code": self.error_code,
            "value": str(self.value) if self.value is not None else None,
        }


# Event type constants
class EventTypes:
    """Constants for event types."""

    # Shipment events
    SHIPMENT_CREATED = "shipment.created"
    SHIPMENT_UPDATED = "shipment.updated"
    SHIPMENT_CANCELLED = "shipment.cancelled"
    SHIPMENT_IN_TRANSIT = "shipment.in_transit"
    SHIPMENT_DELIVERED = "shipment.delivered"
    SHIPMENT_RETURNED = "shipment.returned"

    # Facility events
    FACILITY_CREATED = "facility.created"
    FACILITY_UPDATED = "facility.updated"
    FACILITY_CAPACITY_CHANGED = "facility.capacity_changed"
    FACILITY_STATUS_CHANGED = "facility.status_changed"

    # Driver events
    DRIVER_CREATED = "driver.created"
    DRIVER_UPDATED = "driver.updated"
    DRIVER_ASSIGNED = "driver.assigned"
    DRIVER_LOCATION_UPDATED = "driver.location_updated"
    DRIVER_STATUS_CHANGED = "driver.status_changed"

    # Delivery events
    DELIVERY_SCHEDULED = "delivery.scheduled"
    DELIVERY_STARTED = "delivery.started"
    DELIVERY_ATTEMPTED = "delivery.attempted"
    DELIVERY_COMPLETED = "delivery.completed"
    DELIVERY_FAILED = "delivery.failed"
    DELIVERY_RESCHEDULED = "delivery.rescheduled"

    @classmethod
    def all_types(cls) -> list[str]:
        """Get all event types."""
        return [
            getattr(cls, attr)
            for attr in dir(cls)
            if not attr.startswith("_") and isinstance(getattr(cls, attr), str)
        ]

    @classmethod
    def get_domain_types(cls, domain: str) -> list[str]:
        """Get all event types for a domain."""
        prefix = f"{domain}."
        return [t for t in cls.all_types() if t.startswith(prefix)]
