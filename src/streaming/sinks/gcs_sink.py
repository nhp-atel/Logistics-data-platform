"""
GCS sink for writing events to cloud storage (Bronze layer).
"""

import json
from datetime import datetime
from typing import Any, Iterator

import apache_beam as beam
from apache_beam.io import fileio

from src.common.schemas import EventEnvelope
from src.common.logging_utils import get_logger
from src.common.metrics import beam_metrics

logger = get_logger(__name__)


class WriteToGCS(beam.PTransform):
    """
    Write events to GCS in partitioned Avro/JSON format.

    Events are partitioned by event_date and hour for efficient querying.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "events",
        file_format: str = "jsonl",
        max_records_per_shard: int = 10000,
    ):
        """
        Initialize the GCS sink.

        Args:
            bucket: GCS bucket name (without gs:// prefix)
            prefix: Path prefix within the bucket
            file_format: Output format (jsonl, avro)
            max_records_per_shard: Maximum records per output file
        """
        super().__init__()
        self.bucket = bucket
        self.prefix = prefix
        self.file_format = file_format
        self.max_records_per_shard = max_records_per_shard

    def expand(self, pcoll):
        """Write events to GCS."""
        return (
            pcoll
            | "ToJSON" >> beam.Map(self._event_to_json)
            | "WriteToGCS" >> fileio.WriteToFiles(
                path=f"gs://{self.bucket}/{self.prefix}",
                destination=self._get_destination,
                sink=lambda dest: JsonLinesSink(),
                file_naming=fileio.destination_prefix_naming(suffix=".jsonl"),
                max_writers_per_bundle=10,
            )
        )

    def _event_to_json(self, event: EventEnvelope) -> tuple[str, str]:
        """Convert event to JSON string with destination key."""
        json_str = json.dumps(event.to_dict(), default=str)
        destination = self._get_destination(event)
        return (destination, json_str)

    def _get_destination(self, element: Any) -> str:
        """
        Generate destination path based on event time.

        Creates partitioned paths like:
        events/event_type=shipment.created/event_date=2024-01-15/hour=14/
        """
        if isinstance(element, tuple):
            return element[0]

        if isinstance(element, EventEnvelope):
            event = element
        else:
            return "unknown"

        event_date = event.event_time.strftime("%Y-%m-%d")
        hour = event.event_time.strftime("%H")
        domain = event.get_domain()

        return f"{domain}/event_date={event_date}/hour={hour}"


class JsonLinesSink(fileio.TextSink):
    """Sink that writes JSON lines format."""

    def write(self, record: tuple[str, str]) -> None:
        """Write a record to the file."""
        _, json_str = record
        self._fh.write(json_str.encode("utf-8"))
        self._fh.write(b"\n")


class WriteToGCSAvro(beam.PTransform):
    """
    Write events to GCS in Avro format with schema.

    Avro provides better compression and schema evolution support.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "events",
        schema: dict | None = None,
    ):
        """
        Initialize the Avro GCS sink.

        Args:
            bucket: GCS bucket name
            prefix: Path prefix within the bucket
            schema: Avro schema dictionary
        """
        super().__init__()
        self.bucket = bucket
        self.prefix = prefix
        self.schema = schema or self._default_schema()

    def _default_schema(self) -> dict:
        """Get default Avro schema for events."""
        return {
            "type": "record",
            "name": "EventEnvelope",
            "namespace": "com.logistics.events",
            "fields": [
                {"name": "event_id", "type": "string"},
                {"name": "event_type", "type": "string"},
                {"name": "event_version", "type": "string"},
                {"name": "event_time", "type": "string"},
                {"name": "ingest_time", "type": "string"},
                {"name": "source_system", "type": "string"},
                {"name": "trace_id", "type": ["null", "string"], "default": None},
                {"name": "payload", "type": "string"},  # JSON string
            ],
        }

    def expand(self, pcoll):
        """Write events to GCS in Avro format."""
        from apache_beam.io.avroio import WriteToAvro

        return (
            pcoll
            | "ToAvroRecord" >> beam.Map(self._to_avro_record)
            | "WriteAvro" >> WriteToAvro(
                file_path_prefix=f"gs://{self.bucket}/{self.prefix}/events",
                schema=self.schema,
                file_name_suffix=".avro",
            )
        )

    def _to_avro_record(self, event: EventEnvelope) -> dict:
        """Convert event to Avro record format."""
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "event_version": event.event_version,
            "event_time": event.event_time.isoformat(),
            "ingest_time": event.ingest_time.isoformat(),
            "source_system": event.source_system,
            "trace_id": event.trace_id,
            "payload": json.dumps(event.payload, default=str),
        }


class WriteToGCSParquet(beam.PTransform):
    """
    Write events to GCS in Parquet format.

    Parquet provides excellent compression and columnar access patterns.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "events",
    ):
        """
        Initialize the Parquet GCS sink.

        Args:
            bucket: GCS bucket name
            prefix: Path prefix within the bucket
        """
        super().__init__()
        self.bucket = bucket
        self.prefix = prefix

    def expand(self, pcoll):
        """Write events to GCS in Parquet format."""
        from apache_beam.io.parquetio import WriteToParquet
        import pyarrow as pa

        schema = pa.schema([
            ("event_id", pa.string()),
            ("event_type", pa.string()),
            ("event_version", pa.string()),
            ("event_time", pa.timestamp("us")),
            ("ingest_time", pa.timestamp("us")),
            ("source_system", pa.string()),
            ("trace_id", pa.string()),
            ("payload", pa.string()),
            ("event_date", pa.date32()),
        ])

        return (
            pcoll
            | "ToParquetRecord" >> beam.Map(self._to_parquet_record)
            | "WriteParquet" >> WriteToParquet(
                file_path_prefix=f"gs://{self.bucket}/{self.prefix}/events",
                schema=schema,
                file_name_suffix=".parquet",
            )
        )

    def _to_parquet_record(self, event: EventEnvelope) -> dict:
        """Convert event to Parquet record format."""
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "event_version": event.event_version,
            "event_time": event.event_time,
            "ingest_time": event.ingest_time,
            "source_system": event.source_system,
            "trace_id": event.trace_id,
            "payload": json.dumps(event.payload, default=str),
            "event_date": event.event_time.date(),
        }
