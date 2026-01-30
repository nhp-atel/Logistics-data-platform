"""
Enrichment transform using side inputs for dimension data.
"""

from typing import Any, Iterator

import apache_beam as beam
from apache_beam.pvalue import AsSingleton, AsDict

from src.common.schemas import EventEnvelope
from src.common.logging_utils import get_logger
from src.common.metrics import beam_metrics

logger = get_logger(__name__)


class EnrichWithSideInputs(beam.DoFn):
    """
    Enrich events with dimension data from side inputs.

    Looks up facility, carrier, and driver information from
    BigQuery dimension tables provided as side inputs.
    """

    def __init__(self):
        super().__init__()
        self._counter_enriched = None
        self._counter_not_found = None

    def setup(self):
        """Initialize counters."""
        self._counter_enriched = beam_metrics.get_counter("enrich_success")
        self._counter_not_found = beam_metrics.get_counter("enrich_not_found")

    def process(
        self,
        event: EventEnvelope,
        facilities: dict[str, dict] | None = None,
        carriers: dict[str, dict] | None = None,
        drivers: dict[str, dict] | None = None,
    ) -> Iterator[EventEnvelope]:
        """
        Enrich an event with dimension data.

        Args:
            event: Event to enrich
            facilities: Side input of facility dimension data
            carriers: Side input of carrier dimension data
            drivers: Side input of driver dimension data

        Yields:
            Enriched event
        """
        payload = event.payload.copy()
        enriched = False

        # Enrich with facility data
        facility_id = payload.get("facility_id") or payload.get("facilityId")
        if facility_id and facilities:
            facility_data = facilities.get(facility_id)
            if facility_data:
                payload["_facility"] = {
                    "name": facility_data.get("facility_name"),
                    "type": facility_data.get("facility_type"),
                    "region_id": facility_data.get("region_id"),
                    "timezone": facility_data.get("timezone"),
                }
                enriched = True
            else:
                self._counter_not_found.inc()
                logger.debug(f"Facility not found: {facility_id}")

        # Enrich with carrier data
        carrier_id = payload.get("carrier_id") or payload.get("carrierId")
        if carrier_id and carriers:
            carrier_data = carriers.get(carrier_id)
            if carrier_data:
                payload["_carrier"] = {
                    "name": carrier_data.get("carrier_name"),
                    "type": carrier_data.get("carrier_type"),
                    "scac_code": carrier_data.get("scac_code"),
                }
                enriched = True
            else:
                self._counter_not_found.inc()
                logger.debug(f"Carrier not found: {carrier_id}")

        # Enrich with driver data (excluding PII)
        driver_id = payload.get("driver_id") or payload.get("driverId")
        if driver_id and drivers:
            driver_data = drivers.get(driver_id)
            if driver_data:
                payload["_driver"] = {
                    "carrier_id": driver_data.get("carrier_id"),
                    "home_facility_id": driver_data.get("home_facility_id"),
                    "vehicle_type": driver_data.get("vehicle_type"),
                }
                enriched = True
            else:
                self._counter_not_found.inc()
                logger.debug(f"Driver not found: {driver_id}")

        if enriched:
            self._counter_enriched.inc()

        # Create new event with enriched payload
        enriched_event = EventEnvelope(
            event_id=event.event_id,
            event_type=event.event_type,
            event_version=event.event_version,
            event_time=event.event_time,
            ingest_time=event.ingest_time,
            source_system=event.source_system,
            payload=payload,
            trace_id=event.trace_id,
        )

        yield enriched_event


class LoadDimensionTable(beam.PTransform):
    """
    Load dimension table from BigQuery for use as side input.
    """

    def __init__(self, table: str, key_field: str, project: str | None = None):
        """
        Initialize the dimension loader.

        Args:
            table: BigQuery table reference (project:dataset.table)
            key_field: Field to use as dictionary key
            project: GCP project ID (optional, will use table's project)
        """
        super().__init__()
        self.table = table
        self.key_field = key_field
        self.project = project

    def expand(self, pcoll):
        """Load dimension data from BigQuery."""
        from apache_beam.io.gcp.bigquery import ReadFromBigQuery

        return (
            pcoll
            | f"Read_{self.table}" >> ReadFromBigQuery(
                table=self.table,
                project=self.project,
                gcs_location=f"gs://temp-{self.project}/bq-temp",
            )
            | f"ToDict_{self.table}" >> beam.Map(
                lambda row: (row[self.key_field], dict(row))
            )
        )


def create_enrichment_side_inputs(
    pipeline: beam.Pipeline,
    project_id: str,
    dataset: str,
) -> dict[str, beam.pvalue.PValue]:
    """
    Create side inputs for all dimension tables.

    Args:
        pipeline: Beam pipeline
        project_id: GCP project ID
        dataset: BigQuery dataset containing dimension tables

    Returns:
        Dictionary of side input PValues
    """
    facilities = (
        pipeline
        | "LoadFacilities" >> LoadDimensionTable(
            table=f"{project_id}:{dataset}.dim_facility",
            key_field="facility_id",
            project=project_id,
        )
    )

    carriers = (
        pipeline
        | "LoadCarriers" >> LoadDimensionTable(
            table=f"{project_id}:{dataset}.dim_carrier",
            key_field="carrier_id",
            project=project_id,
        )
    )

    drivers = (
        pipeline
        | "LoadDrivers" >> LoadDimensionTable(
            table=f"{project_id}:{dataset}.dim_driver",
            key_field="driver_id",
            project=project_id,
        )
    )

    return {
        "facilities": AsDict(facilities),
        "carriers": AsDict(carriers),
        "drivers": AsDict(drivers),
    }
