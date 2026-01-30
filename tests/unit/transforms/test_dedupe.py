"""
Unit tests for the deduplication transform.
"""

from datetime import datetime, timezone

import pytest

from src.common.schemas import EventEnvelope
from src.streaming.transforms.dedupe import WindowedDedupeDoFn, GroupAndDedupeDoFn


class TestWindowedDedupeDoFn:
    """Tests for WindowedDedupeDoFn."""

    def setup_method(self):
        """Set up test fixtures."""
        self.dedupe = WindowedDedupeDoFn()
        self.dedupe.setup()

    def create_envelope(self, event_id: str, shipment_id: str = "SHIP-001") -> EventEnvelope:
        """Helper to create test envelopes."""
        return EventEnvelope(
            event_id=event_id,
            event_type="shipment.created",
            event_version="v1",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            source_system="test",
            payload={"shipment_id": shipment_id},
        )

    def test_dedupe_removes_duplicates(self):
        """Test that duplicate events are removed."""
        self.dedupe.start_bundle()

        event1 = self.create_envelope("event-001")
        event2 = self.create_envelope("event-001")  # Same ID = duplicate
        event3 = self.create_envelope("event-002")  # Different ID

        results = []
        results.extend(self.dedupe.process(event1))
        results.extend(self.dedupe.process(event2))
        results.extend(self.dedupe.process(event3))

        assert len(results) == 2
        event_ids = [e.event_id for e in results]
        assert "event-001" in event_ids
        assert "event-002" in event_ids

    def test_dedupe_preserves_order(self):
        """Test that first occurrence is kept."""
        self.dedupe.start_bundle()

        events = [
            self.create_envelope("event-001"),
            self.create_envelope("event-002"),
            self.create_envelope("event-001"),  # Duplicate
            self.create_envelope("event-003"),
        ]

        results = []
        for event in events:
            results.extend(self.dedupe.process(event))

        assert len(results) == 3
        assert [e.event_id for e in results] == ["event-001", "event-002", "event-003"]

    def test_dedupe_resets_on_bundle(self):
        """Test that state resets between bundles."""
        # First bundle
        self.dedupe.start_bundle()
        event1 = self.create_envelope("event-001")
        results1 = list(self.dedupe.process(event1))
        assert len(results1) == 1

        # Second bundle - same event_id should be processed again
        self.dedupe.start_bundle()
        event2 = self.create_envelope("event-001")
        results2 = list(self.dedupe.process(event2))
        assert len(results2) == 1

    def test_dedupe_handles_many_events(self):
        """Test deduplication with many events."""
        self.dedupe.start_bundle()

        # Create 100 unique events and 50 duplicates
        results = []
        for i in range(100):
            event = self.create_envelope(f"event-{i:03d}")
            results.extend(self.dedupe.process(event))

        # Add duplicates
        for i in range(50):
            event = self.create_envelope(f"event-{i:03d}")
            results.extend(self.dedupe.process(event))

        assert len(results) == 100


class TestGroupAndDedupeDoFn:
    """Tests for GroupAndDedupeDoFn."""

    def setup_method(self):
        """Set up test fixtures."""
        self.dedupe = GroupAndDedupeDoFn()

    def create_envelope(
        self,
        event_id: str,
        ingest_time: datetime | None = None,
    ) -> EventEnvelope:
        """Helper to create test envelopes."""
        return EventEnvelope(
            event_id=event_id,
            event_type="shipment.created",
            event_version="v1",
            event_time=datetime.now(timezone.utc),
            ingest_time=ingest_time or datetime.now(timezone.utc),
            source_system="test",
            payload={"shipment_id": "SHIP-001"},
        )

    def test_takes_first_event_from_group(self):
        """Test that first event (by ingest_time) is kept."""
        early_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        late_time = datetime(2024, 1, 15, 10, 1, 0, tzinfo=timezone.utc)

        events = [
            self.create_envelope("event-001", ingest_time=late_time),
            self.create_envelope("event-001", ingest_time=early_time),
        ]

        results = list(self.dedupe.process(("key-1", iter(events))))

        assert len(results) == 1
        assert results[0].ingest_time == early_time

    def test_handles_single_event_group(self):
        """Test handling of groups with single event."""
        event = self.create_envelope("event-001")

        results = list(self.dedupe.process(("key-1", iter([event]))))

        assert len(results) == 1
        assert results[0].event_id == "event-001"

    def test_handles_empty_group(self):
        """Test handling of empty groups."""
        results = list(self.dedupe.process(("key-1", iter([]))))

        assert len(results) == 0

    def test_deduplicates_multiple_groups(self):
        """Test deduplication across multiple groups."""
        events_group1 = [
            self.create_envelope("event-001"),
            self.create_envelope("event-001"),
        ]
        events_group2 = [
            self.create_envelope("event-002"),
        ]

        results = []
        results.extend(self.dedupe.process(("key-1", iter(events_group1))))
        results.extend(self.dedupe.process(("key-2", iter(events_group2))))

        assert len(results) == 2
