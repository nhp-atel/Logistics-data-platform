"""Sink implementations for the streaming pipeline."""

from src.streaming.sinks.gcs_sink import WriteToGCS
from src.streaming.sinks.bq_sink import get_table_schema

__all__ = ["WriteToGCS", "get_table_schema"]
