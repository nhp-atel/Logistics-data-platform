"""
Routing transforms for directing events to appropriate outputs.
"""

import json
from typing import Iterator

import apache_beam as beam
from apache_beam.pvalue import TaggedOutput
from apache_beam.io.gcp.pubsub import PubsubMessage

from src.common.schemas import EventEnvelope
from src.common.logging_utils import get_logger
from src.common.metrics import beam_metrics

logger = get_logger(__name__)


class RouteByEventType(beam.PTransform):
    """
    Route events to different outputs based on event type domain.
    """

    # Output tags for each domain
    SHIPMENT_TAG = "shipment"
    FACILITY_TAG = "facility"
    DRIVER_TAG = "driver"
    DELIVERY_TAG = "delivery"
    OTHER_TAG = "other"

    def expand(self, pcoll):
        """Route events by domain."""
        return (
            pcoll
            | "RouteByDomain" >> beam.ParDo(
                _RouteByDomainDoFn()
            ).with_outputs(
                self.SHIPMENT_TAG,
                self.FACILITY_TAG,
                self.DRIVER_TAG,
                self.DELIVERY_TAG,
                self.OTHER_TAG,
                main=self.OTHER_TAG,
            )
        )


class _RouteByDomainDoFn(beam.DoFn):
    """DoFn that routes events based on their domain."""

    def __init__(self):
        super().__init__()
        self._counters = {}

    def setup(self):
        """Initialize counters for each domain."""
        for domain in ["shipment", "facility", "driver", "delivery", "other"]:
            self._counters[domain] = beam_metrics.get_counter(f"route_{domain}")

    def process(self, event: EventEnvelope) -> Iterator[TaggedOutput]:
        """Route event to appropriate output based on domain."""
        domain = event.get_domain()

        if domain == "shipment":
            self._counters["shipment"].inc()
            yield TaggedOutput(RouteByEventType.SHIPMENT_TAG, event)
        elif domain == "facility":
            self._counters["facility"].inc()
            yield TaggedOutput(RouteByEventType.FACILITY_TAG, event)
        elif domain == "driver":
            self._counters["driver"].inc()
            yield TaggedOutput(RouteByEventType.DRIVER_TAG, event)
        elif domain == "delivery":
            self._counters["delivery"].inc()
            yield TaggedOutput(RouteByEventType.DELIVERY_TAG, event)
        else:
            self._counters["other"].inc()
            yield TaggedOutput(RouteByEventType.OTHER_TAG, event)


class RouteToDLQ(beam.DoFn):
    """
    Route failed events to a dead letter queue (Pub/Sub topic).
    """

    def __init__(self, dlq_topic: str):
        """
        Initialize the DLQ router.

        Args:
            dlq_topic: Pub/Sub topic for dead letter messages
        """
        super().__init__()
        self.dlq_topic = dlq_topic
        self._publisher = None
        self._counter_dlq = None

    def setup(self):
        """Initialize the Pub/Sub publisher."""
        from google.cloud import pubsub_v1

        self._publisher = pubsub_v1.PublisherClient()
        self._counter_dlq = beam_metrics.get_counter("dlq_messages")

    def process(self, event: EventEnvelope) -> None:
        """
        Publish a failed event to the DLQ.

        Args:
            event: Failed event to send to DLQ
        """
        try:
            # Serialize event
            message_data = json.dumps(event.to_dict()).encode("utf-8")

            # Add attributes for debugging
            attributes = {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "source_system": event.source_system,
                "failure_time": event.ingest_time.isoformat(),
            }

            # Add validation errors if present
            if "_validation_errors" in event.payload:
                attributes["validation_error_count"] = str(
                    len(event.payload["_validation_errors"])
                )

            # Publish to DLQ
            future = self._publisher.publish(
                self.dlq_topic,
                message_data,
                **attributes,
            )
            future.result()  # Wait for publish to complete

            self._counter_dlq.inc()
            logger.warning(
                "Event sent to DLQ",
                event_id=event.event_id,
                event_type=event.event_type,
            )

        except Exception as e:
            logger.error(
                "Failed to publish to DLQ",
                event_id=event.event_id,
                error=str(e),
            )
            raise


class RouteByPriority(beam.PTransform):
    """
    Route events based on priority for different processing paths.
    """

    HIGH_PRIORITY_TAG = "high"
    NORMAL_PRIORITY_TAG = "normal"
    LOW_PRIORITY_TAG = "low"

    def __init__(self, high_priority_types: set[str] | None = None):
        """
        Initialize priority router.

        Args:
            high_priority_types: Event types to treat as high priority
        """
        super().__init__()
        self.high_priority_types = high_priority_types or {
            "shipment.created",
            "shipment.delivered",
            "delivery.completed",
            "delivery.failed",
        }

    def expand(self, pcoll):
        """Route events by priority."""
        return (
            pcoll
            | "RouteByPriority" >> beam.ParDo(
                _RouteByPriorityDoFn(self.high_priority_types)
            ).with_outputs(
                self.HIGH_PRIORITY_TAG,
                self.NORMAL_PRIORITY_TAG,
                self.LOW_PRIORITY_TAG,
                main=self.NORMAL_PRIORITY_TAG,
            )
        )


class _RouteByPriorityDoFn(beam.DoFn):
    """DoFn that routes events based on priority."""

    def __init__(self, high_priority_types: set[str]):
        super().__init__()
        self.high_priority_types = high_priority_types
        self.low_priority_types = {
            "driver.location_updated",  # High frequency, can be delayed
        }

    def process(self, event: EventEnvelope) -> Iterator[TaggedOutput]:
        """Route event based on priority."""
        if event.event_type in self.high_priority_types:
            yield TaggedOutput(RouteByPriority.HIGH_PRIORITY_TAG, event)
        elif event.event_type in self.low_priority_types:
            yield TaggedOutput(RouteByPriority.LOW_PRIORITY_TAG, event)
        else:
            yield TaggedOutput(RouteByPriority.NORMAL_PRIORITY_TAG, event)


class FilterByEventType(beam.PTransform):
    """
    Filter events to only include specific event types.
    """

    def __init__(self, allowed_types: set[str]):
        """
        Initialize the filter.

        Args:
            allowed_types: Set of event types to allow through
        """
        super().__init__()
        self.allowed_types = allowed_types

    def expand(self, pcoll):
        """Filter events by type."""
        return (
            pcoll
            | "FilterByType" >> beam.Filter(
                lambda event: event.event_type in self.allowed_types
            )
        )
