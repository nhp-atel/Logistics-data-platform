"""
Tumbling window implementation with late data handling.
"""

import apache_beam as beam
from apache_beam import window
from apache_beam.transforms.trigger import (
    AfterWatermark,
    AfterProcessingTime,
    AccumulationMode,
    Repeatedly,
    AfterCount,
)
from apache_beam.utils.timestamp import Duration

from src.common.logging_utils import get_logger

logger = get_logger(__name__)


class ApplyTumblingWindow(beam.PTransform):
    """
    Apply tumbling (fixed) windows with configurable triggers for late data.

    Implements early, on-time, and late firing triggers for comprehensive
    event-time processing with allowed lateness.
    """

    def __init__(
        self,
        window_duration: int = 300,  # 5 minutes
        allowed_lateness: int = 86400,  # 24 hours
        early_trigger_seconds: int = 60,
        accumulation_mode: AccumulationMode = AccumulationMode.DISCARDING,
    ):
        """
        Initialize the windowing transform.

        Args:
            window_duration: Window size in seconds
            allowed_lateness: How late data can arrive and still be processed
            early_trigger_seconds: Fire early results every N seconds
            accumulation_mode: How to handle multiple firings (DISCARDING or ACCUMULATING)
        """
        super().__init__()
        self.window_duration = window_duration
        self.allowed_lateness = allowed_lateness
        self.early_trigger_seconds = early_trigger_seconds
        self.accumulation_mode = accumulation_mode

    def expand(self, pcoll):
        """Apply windowing to the input PCollection."""

        # Create the trigger strategy
        trigger = AfterWatermark(
            # Early firings: every N seconds of processing time
            early=AfterProcessingTime(self.early_trigger_seconds),
            # Late firings: every late element
            late=AfterCount(1),
        )

        return (
            pcoll
            | "ApplyWindow" >> beam.WindowInto(
                window.FixedWindows(self.window_duration),
                trigger=trigger,
                accumulation_mode=self.accumulation_mode,
                allowed_lateness=Duration(seconds=self.allowed_lateness),
            )
        )


class ApplySlidingWindow(beam.PTransform):
    """
    Apply sliding windows for overlapping time periods.

    Useful for computing rolling aggregates.
    """

    def __init__(
        self,
        window_duration: int = 300,  # 5 minutes
        window_period: int = 60,  # 1 minute slide
        allowed_lateness: int = 86400,
    ):
        """
        Initialize the sliding window transform.

        Args:
            window_duration: Window size in seconds
            window_period: Slide period in seconds
            allowed_lateness: How late data can arrive
        """
        super().__init__()
        self.window_duration = window_duration
        self.window_period = window_period
        self.allowed_lateness = allowed_lateness

    def expand(self, pcoll):
        """Apply sliding windows."""
        return (
            pcoll
            | "ApplySlidingWindow" >> beam.WindowInto(
                window.SlidingWindows(self.window_duration, self.window_period),
                allowed_lateness=Duration(seconds=self.allowed_lateness),
            )
        )


class ApplySessionWindow(beam.PTransform):
    """
    Apply session windows that group events by activity gaps.

    Useful for grouping related events (e.g., all events for a delivery attempt).
    """

    def __init__(
        self,
        gap_duration: int = 300,  # 5 minute gap closes session
        allowed_lateness: int = 86400,
    ):
        """
        Initialize the session window transform.

        Args:
            gap_duration: Gap in seconds that closes a session
            allowed_lateness: How late data can arrive
        """
        super().__init__()
        self.gap_duration = gap_duration
        self.allowed_lateness = allowed_lateness

    def expand(self, pcoll):
        """Apply session windows."""
        return (
            pcoll
            | "ApplySessionWindow" >> beam.WindowInto(
                window.Sessions(self.gap_duration),
                allowed_lateness=Duration(seconds=self.allowed_lateness),
            )
        )


class ApplyGlobalWindowWithTrigger(beam.PTransform):
    """
    Apply global window with periodic triggers.

    Useful for aggregations that should span all time but fire periodically.
    """

    def __init__(
        self,
        trigger_interval: int = 60,  # Fire every minute
    ):
        """
        Initialize the global window transform.

        Args:
            trigger_interval: How often to fire results in seconds
        """
        super().__init__()
        self.trigger_interval = trigger_interval

    def expand(self, pcoll):
        """Apply global window with periodic trigger."""
        return (
            pcoll
            | "ApplyGlobalWindow" >> beam.WindowInto(
                window.GlobalWindows(),
                trigger=Repeatedly(AfterProcessingTime(self.trigger_interval)),
                accumulation_mode=AccumulationMode.DISCARDING,
            )
        )
