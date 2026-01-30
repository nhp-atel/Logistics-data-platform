"""
Kafka source for reading events.
"""

import json
from typing import Any

import apache_beam as beam
from apache_beam.io.kafka import ReadFromKafka as BeamReadFromKafka

from src.common.logging_utils import get_logger

logger = get_logger(__name__)


class ReadFromKafka(beam.PTransform):
    """
    Read messages from Kafka topics.

    Wraps the Beam Kafka connector with configuration for
    the logistics platform.
    """

    def __init__(
        self,
        bootstrap_servers: str,
        topics: list[str],
        consumer_group: str,
        security_protocol: str = "SASL_SSL",
        sasl_mechanism: str = "PLAIN",
        sasl_username: str | None = None,
        sasl_password: str | None = None,
        auto_offset_reset: str = "earliest",
        max_read_time: int | None = None,
    ):
        """
        Initialize the Kafka reader.

        Args:
            bootstrap_servers: Kafka bootstrap servers
            topics: List of topics to read from
            consumer_group: Consumer group ID
            security_protocol: Security protocol (PLAINTEXT, SASL_SSL, etc.)
            sasl_mechanism: SASL mechanism (PLAIN, SCRAM-SHA-256, etc.)
            sasl_username: SASL username (API key)
            sasl_password: SASL password (API secret)
            auto_offset_reset: Offset reset policy (earliest, latest)
            max_read_time: Maximum read time in seconds (for batch mode)
        """
        super().__init__()
        self.bootstrap_servers = bootstrap_servers
        self.topics = topics
        self.consumer_group = consumer_group
        self.security_protocol = security_protocol
        self.sasl_mechanism = sasl_mechanism
        self.sasl_username = sasl_username
        self.sasl_password = sasl_password
        self.auto_offset_reset = auto_offset_reset
        self.max_read_time = max_read_time

    def expand(self, pcoll):
        """Read from Kafka topics."""
        consumer_config = self._build_consumer_config()

        return (
            pcoll
            | "ReadFromKafka" >> BeamReadFromKafka(
                consumer_config=consumer_config,
                topics=self.topics,
                max_read_time=self.max_read_time,
                with_metadata=True,
            )
            | "ExtractValue" >> beam.Map(self._extract_message)
        )

    def _build_consumer_config(self) -> dict[str, Any]:
        """Build Kafka consumer configuration."""
        config = {
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": self.consumer_group,
            "auto.offset.reset": self.auto_offset_reset,
            "enable.auto.commit": "false",  # Beam manages offsets
        }

        # Add security configuration
        if self.security_protocol != "PLAINTEXT":
            config["security.protocol"] = self.security_protocol

            if self.sasl_mechanism:
                config["sasl.mechanism"] = self.sasl_mechanism

            if self.sasl_username and self.sasl_password:
                config["sasl.username"] = self.sasl_username
                config["sasl.password"] = self.sasl_password

                # For PLAIN mechanism, also need jaas config
                if self.sasl_mechanism == "PLAIN":
                    config["sasl.jaas.config"] = (
                        f"org.apache.kafka.common.security.plain.PlainLoginModule required "
                        f'username="{self.sasl_username}" password="{self.sasl_password}";'
                    )

        return config

    def _extract_message(self, kafka_record) -> dict[str, Any]:
        """
        Extract message from Kafka record.

        Args:
            kafka_record: Kafka record with key, value, metadata

        Returns:
            Parsed message with metadata
        """
        key, value = kafka_record

        # Parse value as JSON
        try:
            if isinstance(value, bytes):
                message = json.loads(value.decode("utf-8"))
            else:
                message = json.loads(value)
        except json.JSONDecodeError:
            message = {"raw_value": value}

        # Add Kafka metadata
        if hasattr(kafka_record, "topic"):
            message["_kafka_topic"] = kafka_record.topic
        if hasattr(kafka_record, "partition"):
            message["_kafka_partition"] = kafka_record.partition
        if hasattr(kafka_record, "offset"):
            message["_kafka_offset"] = kafka_record.offset
        if hasattr(kafka_record, "timestamp"):
            message["_kafka_timestamp"] = kafka_record.timestamp

        # Add key if present
        if key:
            try:
                if isinstance(key, bytes):
                    message["_kafka_key"] = key.decode("utf-8")
                else:
                    message["_kafka_key"] = str(key)
            except Exception:
                pass

        return message


class ReadFromKafkaWithSecrets(ReadFromKafka):
    """
    Read from Kafka with credentials from Secret Manager.
    """

    def __init__(
        self,
        project_id: str,
        secret_id: str,
        topics: list[str],
        consumer_group: str,
        **kwargs,
    ):
        """
        Initialize with Secret Manager credentials.

        Args:
            project_id: GCP project ID
            secret_id: Secret Manager secret ID containing Kafka credentials
            topics: List of topics to read from
            consumer_group: Consumer group ID
            **kwargs: Additional arguments passed to ReadFromKafka
        """
        # Load credentials from Secret Manager
        from google.cloud import secretmanager

        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        credentials = json.loads(response.payload.data.decode("utf-8"))

        super().__init__(
            bootstrap_servers=credentials.get("bootstrap_servers", ""),
            topics=topics,
            consumer_group=consumer_group,
            security_protocol=credentials.get("security_protocol", "SASL_SSL"),
            sasl_mechanism=credentials.get("sasl_mechanism", "PLAIN"),
            sasl_username=credentials.get("api_key"),
            sasl_password=credentials.get("api_secret"),
            **kwargs,
        )
