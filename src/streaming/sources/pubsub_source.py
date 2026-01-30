"""
Pub/Sub source with enhanced message handling.
"""

from typing import Any

import apache_beam as beam
from apache_beam.io.gcp.pubsub import ReadFromPubSub, PubsubMessage

from src.common.logging_utils import get_logger

logger = get_logger(__name__)


class ReadFromPubSubWithAttributes(beam.PTransform):
    """
    Read from Pub/Sub with message attributes and timestamp extraction.
    """

    def __init__(
        self,
        subscription: str | None = None,
        topic: str | None = None,
        timestamp_attribute: str = "event_time",
        id_attribute: str | None = "event_id",
    ):
        """
        Initialize the Pub/Sub reader.

        Args:
            subscription: Pub/Sub subscription to read from
            topic: Pub/Sub topic to read from (creates temp subscription)
            timestamp_attribute: Attribute containing event timestamp
            id_attribute: Attribute for deduplication (enables exactly-once)
        """
        super().__init__()
        self.subscription = subscription
        self.topic = topic
        self.timestamp_attribute = timestamp_attribute
        self.id_attribute = id_attribute

        if not subscription and not topic:
            raise ValueError("Either subscription or topic must be provided")

    def expand(self, pcoll):
        """Read from Pub/Sub with attributes."""
        reader_args = {
            "with_attributes": True,
        }

        if self.subscription:
            reader_args["subscription"] = self.subscription
        else:
            reader_args["topic"] = self.topic

        if self.timestamp_attribute:
            reader_args["timestamp_attribute"] = self.timestamp_attribute

        if self.id_attribute:
            reader_args["id_label"] = self.id_attribute

        return (
            pcoll
            | "ReadFromPubSub" >> ReadFromPubSub(**reader_args)
        )


class ReadFromMultiplePubSubTopics(beam.PTransform):
    """
    Read from multiple Pub/Sub topics and merge into single stream.
    """

    def __init__(
        self,
        subscriptions: dict[str, str],
        timestamp_attribute: str = "event_time",
    ):
        """
        Initialize multi-topic reader.

        Args:
            subscriptions: Dict mapping topic name to subscription path
            timestamp_attribute: Attribute containing event timestamp
        """
        super().__init__()
        self.subscriptions = subscriptions
        self.timestamp_attribute = timestamp_attribute

    def expand(self, pcoll):
        """Read from multiple subscriptions and merge."""
        streams = []

        for topic_name, subscription in self.subscriptions.items():
            stream = (
                pcoll
                | f"Read_{topic_name}" >> ReadFromPubSub(
                    subscription=subscription,
                    with_attributes=True,
                    timestamp_attribute=self.timestamp_attribute,
                )
                | f"Tag_{topic_name}" >> beam.Map(
                    lambda msg, topic=topic_name: self._tag_with_topic(msg, topic)
                )
            )
            streams.append(stream)

        if len(streams) == 1:
            return streams[0]

        return (
            tuple(streams)
            | "Flatten" >> beam.Flatten()
        )

    def _tag_with_topic(self, message: PubsubMessage, topic: str) -> PubsubMessage:
        """Add topic tag to message attributes."""
        new_attributes = dict(message.attributes)
        new_attributes["_source_topic"] = topic
        return PubsubMessage(data=message.data, attributes=new_attributes)


class BatchReadFromPubSub(beam.PTransform):
    """
    Read a batch of messages from Pub/Sub for testing/backfill.
    """

    def __init__(
        self,
        subscription: str,
        max_messages: int = 1000,
        timeout_seconds: int = 30,
    ):
        """
        Initialize batch reader.

        Args:
            subscription: Pub/Sub subscription to read from
            max_messages: Maximum messages to read
            timeout_seconds: Timeout for reading
        """
        super().__init__()
        self.subscription = subscription
        self.max_messages = max_messages
        self.timeout_seconds = timeout_seconds

    def expand(self, pcoll):
        """Read batch of messages from Pub/Sub."""
        from google.cloud import pubsub_v1

        # Use a DoFn that reads messages in batch
        return (
            pcoll
            | "CreateSeed" >> beam.Create([1])
            | "PullMessages" >> beam.ParDo(
                _PullMessagesDoFn(
                    self.subscription,
                    self.max_messages,
                    self.timeout_seconds,
                )
            )
        )


class _PullMessagesDoFn(beam.DoFn):
    """DoFn that pulls messages from Pub/Sub in batch mode."""

    def __init__(self, subscription: str, max_messages: int, timeout: int):
        super().__init__()
        self.subscription = subscription
        self.max_messages = max_messages
        self.timeout = timeout

    def process(self, _):
        """Pull messages from the subscription."""
        from google.cloud import pubsub_v1
        from concurrent.futures import TimeoutError

        subscriber = pubsub_v1.SubscriberClient()

        # Pull messages
        response = subscriber.pull(
            request={
                "subscription": self.subscription,
                "max_messages": self.max_messages,
            },
            timeout=self.timeout,
        )

        ack_ids = []
        for received_message in response.received_messages:
            message = received_message.message

            pubsub_msg = PubsubMessage(
                data=message.data,
                attributes=dict(message.attributes),
            )
            yield pubsub_msg

            ack_ids.append(received_message.ack_id)

        # Acknowledge messages
        if ack_ids:
            subscriber.acknowledge(
                request={
                    "subscription": self.subscription,
                    "ack_ids": ack_ids,
                }
            )

        subscriber.close()
