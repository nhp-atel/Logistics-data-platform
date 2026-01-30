"""
Stateful deduplication transform for events.
"""

from datetime import timedelta
from typing import Iterator, Tuple

import apache_beam as beam
from apache_beam.coders import StrUtf8Coder
from apache_beam.transforms.userstate import (
    BagStateSpec,
    TimerSpec,
    on_timer,
)
from apache_beam.utils.timestamp import Duration

from src.common.schemas import EventEnvelope
from src.common.logging_utils import get_logger
from src.common.metrics import beam_metrics

logger = get_logger(__name__)


class StatefulDedupeDoFn(beam.DoFn):
    """
    Stateful deduplication using event_id with TTL.

    Uses Beam state to track seen event IDs within a configurable
    time window. Duplicate events are dropped.
    """

    # State spec for tracking seen event IDs
    SEEN_STATE = BagStateSpec("seen", StrUtf8Coder())

    # Timer spec for garbage collection
    GC_TIMER = TimerSpec("gc_timer", beam.TimeDomain.PROCESSING_TIME)

    def __init__(self, dedup_window_hours: int = 24):
        """
        Initialize the deduplication transform.

        Args:
            dedup_window_hours: How long to remember event IDs (default 24 hours)
        """
        super().__init__()
        self.dedup_window_hours = dedup_window_hours
        self._counter_unique = None
        self._counter_duplicate = None

    def setup(self):
        """Initialize counters."""
        self._counter_unique = beam_metrics.get_counter("dedupe_unique")
        self._counter_duplicate = beam_metrics.get_counter("dedupe_duplicate")

    def process(
        self,
        element: Tuple[str, EventEnvelope],
        seen=beam.DoFn.StateParam(SEEN_STATE),
        gc_timer=beam.DoFn.TimerParam(GC_TIMER),
    ) -> Iterator[EventEnvelope]:
        """
        Process an event and yield if not a duplicate.

        Args:
            element: Tuple of (dedupe_key, event)
            seen: State parameter for tracking seen IDs
            gc_timer: Timer for garbage collection

        Yields:
            Event if not a duplicate
        """
        dedupe_key, event = element

        # Check if we've seen this event
        seen_ids = list(seen.read())

        if event.event_id in seen_ids:
            self._counter_duplicate.inc()
            logger.debug(
                "Dropping duplicate event",
                event_id=event.event_id,
                event_type=event.event_type,
            )
            return

        # Not a duplicate - add to state and emit
        seen.add(event.event_id)
        self._counter_unique.inc()

        # Set/reset the GC timer
        gc_timer.set(
            beam.DoFn.TimestampParam + Duration(seconds=self.dedup_window_hours * 3600)
        )

        yield event

    @on_timer(GC_TIMER)
    def gc_callback(self, seen=beam.DoFn.StateParam(SEEN_STATE)):
        """
        Garbage collect the state when the timer fires.

        This clears the seen IDs to prevent unbounded state growth.
        """
        seen.clear()
        logger.debug("Cleared deduplication state")


class WindowedDedupeDoFn(beam.DoFn):
    """
    Simpler deduplication within a window using in-memory set.

    This is more efficient for smaller windows but doesn't persist
    across windows like StatefulDedupeDoFn.
    """

    def __init__(self):
        super().__init__()
        self._seen_in_window: set = set()
        self._counter_unique = None
        self._counter_duplicate = None

    def setup(self):
        """Initialize counters."""
        self._counter_unique = beam_metrics.get_counter("windowed_dedupe_unique")
        self._counter_duplicate = beam_metrics.get_counter("windowed_dedupe_duplicate")

    def start_bundle(self):
        """Reset the seen set for each bundle."""
        self._seen_in_window = set()

    def process(self, event: EventEnvelope) -> Iterator[EventEnvelope]:
        """Process an event and yield if not seen in this bundle."""
        if event.event_id in self._seen_in_window:
            self._counter_duplicate.inc()
            return

        self._seen_in_window.add(event.event_id)
        self._counter_unique.inc()
        yield event


class GroupAndDedupeDoFn(beam.DoFn):
    """
    Deduplicate by grouping on key and taking first event.

    Use this after GroupByKey for more robust deduplication.
    """

    def process(
        self,
        element: Tuple[str, Iterator[EventEnvelope]],
    ) -> Iterator[EventEnvelope]:
        """
        Take the first event from each group.

        Args:
            element: Tuple of (key, events iterator)

        Yields:
            First event in the group
        """
        key, events = element

        # Sort by ingest_time and take the first
        events_list = list(events)
        if events_list:
            events_list.sort(key=lambda e: e.ingest_time)
            yield events_list[0]

            if len(events_list) > 1:
                logger.debug(
                    "Deduplicated %d events with key %s",
                    len(events_list) - 1,
                    key,
                )
