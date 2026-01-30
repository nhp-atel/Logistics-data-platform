"""
Custom metrics utilities for monitoring pipeline performance.
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator

from google.cloud import monitoring_v3

from src.common.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: dict[str, str] = field(default_factory=dict)


class MetricsClient:
    """Client for publishing custom metrics to Cloud Monitoring."""

    def __init__(self, project_id: str, environment: str = "dev"):
        self.project_id = project_id
        self.environment = environment
        self.project_name = f"projects/{project_id}"
        self._client: monitoring_v3.MetricServiceClient | None = None
        self._buffer: list[MetricPoint] = []
        self._buffer_size = 100

    @property
    def client(self) -> monitoring_v3.MetricServiceClient:
        """Lazy initialization of the monitoring client."""
        if self._client is None:
            self._client = monitoring_v3.MetricServiceClient()
        return self._client

    def _create_time_series(self, metric: MetricPoint) -> monitoring_v3.TimeSeries:
        """Create a TimeSeries object from a MetricPoint."""
        series = monitoring_v3.TimeSeries()

        # Set metric type
        series.metric.type = f"custom.googleapis.com/logistics/{metric.name}"

        # Set labels
        series.metric.labels["environment"] = self.environment
        for key, value in metric.labels.items():
            series.metric.labels[key] = str(value)

        # Set resource
        series.resource.type = "global"
        series.resource.labels["project_id"] = self.project_id

        # Set point
        point = monitoring_v3.Point()
        point.value.double_value = metric.value

        # Set interval
        now = metric.timestamp
        seconds = int(now.timestamp())
        nanos = int((now.timestamp() - seconds) * 10**9)
        point.interval.end_time.seconds = seconds
        point.interval.end_time.nanos = nanos

        series.points = [point]

        return series

    def record(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a metric value.

        Args:
            name: Metric name (will be prefixed with custom.googleapis.com/logistics/)
            value: Metric value
            labels: Optional labels for the metric
        """
        metric = MetricPoint(name=name, value=value, labels=labels or {})
        self._buffer.append(metric)

        if len(self._buffer) >= self._buffer_size:
            self.flush()

    def flush(self) -> None:
        """Flush buffered metrics to Cloud Monitoring."""
        if not self._buffer:
            return

        try:
            time_series = [self._create_time_series(m) for m in self._buffer]

            # Cloud Monitoring allows max 200 time series per request
            for i in range(0, len(time_series), 200):
                batch = time_series[i : i + 200]
                self.client.create_time_series(name=self.project_name, time_series=batch)

            logger.debug("Flushed %d metrics", len(self._buffer))
            self._buffer.clear()

        except Exception as e:
            logger.error("Failed to flush metrics: %s", e, exc_info=True)

    def increment(self, name: str, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric by 1."""
        self.record(name, 1.0, labels)

    def gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a gauge metric."""
        self.record(name, value, labels)

    @contextmanager
    def timer(self, name: str, labels: dict[str, str] | None = None) -> Generator[None, None, None]:
        """
        Context manager for timing operations.

        Usage:
            with metrics.timer("operation_duration", labels={"operation": "process"}):
                do_something()
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.record(f"{name}_ms", duration_ms, labels)

    def close(self) -> None:
        """Flush remaining metrics and close the client."""
        self.flush()
        if self._client:
            self._client = None


class BeamMetricsHelper:
    """Helper class for Beam-native metrics."""

    def __init__(self, namespace: str = "logistics_pipeline"):
        self.namespace = namespace
        self._counters: dict[str, Any] = {}
        self._distributions: dict[str, Any] = {}

    def get_counter(self, name: str) -> Any:
        """Get or create a Beam counter metric."""
        from apache_beam.metrics import Metrics

        if name not in self._counters:
            self._counters[name] = Metrics.counter(self.namespace, name)
        return self._counters[name]

    def get_distribution(self, name: str) -> Any:
        """Get or create a Beam distribution metric."""
        from apache_beam.metrics import Metrics

        if name not in self._distributions:
            self._distributions[name] = Metrics.distribution(self.namespace, name)
        return self._distributions[name]

    def inc_counter(self, name: str, value: int = 1) -> None:
        """Increment a counter."""
        self.get_counter(name).inc(value)

    def record_distribution(self, name: str, value: float) -> None:
        """Record a value in a distribution."""
        self.get_distribution(name).update(value)


# Global metrics helper for Beam pipelines
beam_metrics = BeamMetricsHelper()
