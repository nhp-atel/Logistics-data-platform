"""
Main streaming pipeline for logistics events.

This pipeline reads from Pub/Sub, processes events through normalization,
validation, deduplication, enrichment, and PII masking, then writes to
both GCS (Bronze) and BigQuery (Silver).
"""

import argparse
import json
from datetime import datetime, timezone

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.io.gcp.pubsub import ReadFromPubSub
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition

from src.common.config_loader import get_config
from src.common.logging_utils import get_logger, setup_logging
from src.streaming.transforms.normalize import NormalizeToEnvelope
from src.streaming.transforms.validate import ValidateSchema
from src.streaming.transforms.dedupe import StatefulDedupeDoFn
from src.streaming.transforms.enrich import EnrichWithSideInputs
from src.streaming.transforms.pii import MaskPII
from src.streaming.transforms.route import RouteByEventType, RouteToDLQ
from src.streaming.sinks.gcs_sink import WriteToGCS
from src.streaming.sinks.bq_sink import get_table_schema
from src.streaming.windows.tumbling import ApplyTumblingWindow

logger = get_logger(__name__)


class LogisticsPipelineOptions(PipelineOptions):
    """Custom pipeline options for the logistics streaming pipeline."""

    @classmethod
    def _add_argparse_args(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--input_subscription",
            required=True,
            help="Pub/Sub subscription to read from",
        )
        parser.add_argument(
            "--output_table",
            required=True,
            help="BigQuery output table (project:dataset.table)",
        )
        parser.add_argument(
            "--raw_bucket",
            required=True,
            help="GCS bucket for raw event archive",
        )
        parser.add_argument(
            "--dlq_topic",
            required=True,
            help="Pub/Sub topic for dead letter queue",
        )
        parser.add_argument(
            "--environment",
            default="dev",
            help="Environment (dev/prod)",
        )
        parser.add_argument(
            "--window_duration_seconds",
            type=int,
            default=300,
            help="Tumbling window duration in seconds",
        )
        parser.add_argument(
            "--allowed_lateness_seconds",
            type=int,
            default=86400,
            help="Allowed lateness in seconds",
        )
        parser.add_argument(
            "--enable_pii_masking",
            type=bool,
            default=True,
            help="Enable PII masking",
        )


class LogisticsPipeline:
    """Main streaming pipeline for logistics events."""

    def __init__(self, options: LogisticsPipelineOptions):
        self.options = options
        self.config = get_config(options.environment)

    def build(self, pipeline: beam.Pipeline) -> None:
        """Build the pipeline graph."""

        # Read from Pub/Sub
        raw_messages = (
            pipeline
            | "ReadFromPubSub" >> ReadFromPubSub(
                subscription=self.options.input_subscription,
                with_attributes=True,
                timestamp_attribute="event_time",
            )
        )

        # Normalize to EventEnvelope
        normalized = (
            raw_messages
            | "NormalizeToEnvelope" >> beam.ParDo(NormalizeToEnvelope())
        )

        # Validate schema
        validated = (
            normalized
            | "ValidateSchema" >> beam.ParDo(ValidateSchema()).with_outputs(
                "valid", "invalid", main="valid"
            )
        )

        valid_events = validated.valid
        invalid_events = validated.invalid

        # Route invalid events to DLQ
        _ = (
            invalid_events
            | "RouteToDLQ" >> beam.ParDo(RouteToDLQ(self.options.dlq_topic))
        )

        # Stateful deduplication
        deduped = (
            valid_events
            | "KeyByDedupeKey" >> beam.Map(lambda e: (e.dedupe_key, e))
            | "StatefulDedupe" >> beam.ParDo(StatefulDedupeDoFn())
        )

        # Enrich with side inputs (dimension data)
        enriched = (
            deduped
            | "EnrichEvents" >> beam.ParDo(EnrichWithSideInputs())
        )

        # PII masking
        if self.options.enable_pii_masking:
            processed = (
                enriched
                | "MaskPII" >> beam.ParDo(MaskPII())
            )
        else:
            processed = enriched

        # Apply windowing
        windowed = (
            processed
            | "ApplyWindow" >> ApplyTumblingWindow(
                window_duration=self.options.window_duration_seconds,
                allowed_lateness=self.options.allowed_lateness_seconds,
            )
        )

        # Write to GCS (Bronze layer)
        _ = (
            windowed
            | "WriteToGCS" >> WriteToGCS(
                bucket=self.options.raw_bucket,
                prefix="events",
            )
        )

        # Route by event type for BigQuery writes
        routed = (
            windowed
            | "RouteByEventType" >> RouteByEventType()
        )

        # Write each event type to its BigQuery table
        for event_domain in ["shipment", "facility", "driver", "delivery"]:
            table = f"{self.options.output_table.rsplit('.', 1)[0]}.{event_domain}_events"
            _ = (
                getattr(routed, event_domain)
                | f"ToBQRow_{event_domain}" >> beam.Map(self._to_bq_row)
                | f"WriteToBQ_{event_domain}" >> WriteToBigQuery(
                    table=table,
                    schema=get_table_schema(event_domain),
                    write_disposition=BigQueryDisposition.WRITE_APPEND,
                    create_disposition=BigQueryDisposition.CREATE_IF_NEEDED,
                )
            )

    def _to_bq_row(self, event) -> dict:
        """Convert event envelope to BigQuery row."""
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "event_version": event.event_version,
            "event_time": event.event_time.isoformat(),
            "ingest_time": event.ingest_time.isoformat(),
            "trace_id": event.trace_id,
            "source_system": event.source_system,
            "payload": json.dumps(event.payload),
            "dedupe_key": event.dedupe_key,
            # Extract common fields from payload for clustering
            "shipment_id": event.payload.get("shipment_id"),
            "facility_id": event.payload.get("facility_id"),
            "driver_id": event.payload.get("driver_id"),
            "delivery_id": event.payload.get("delivery_id"),
            "carrier_id": event.payload.get("carrier_id"),
        }


def run(argv=None):
    """Run the streaming pipeline."""
    setup_logging(service_name="logistics-streaming-pipeline")

    # Parse options
    options = PipelineOptions(argv)
    custom_options = options.view_as(LogisticsPipelineOptions)
    options.view_as(StandardOptions).streaming = True

    logger.info(
        "Starting logistics streaming pipeline",
        environment=custom_options.environment,
        subscription=custom_options.input_subscription,
    )

    # Build and run pipeline
    pipeline = LogisticsPipeline(custom_options)

    with beam.Pipeline(options=options) as p:
        pipeline.build(p)


if __name__ == "__main__":
    run()
