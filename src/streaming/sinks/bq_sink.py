"""
BigQuery sink utilities and schema definitions.
"""

from typing import Any


def get_table_schema(domain: str) -> dict[str, Any]:
    """
    Get BigQuery table schema for a specific event domain.

    Args:
        domain: Event domain (shipment, facility, driver, delivery)

    Returns:
        BigQuery schema dictionary
    """
    # Common fields for all event tables
    common_fields = [
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED", "description": "Unique event identifier"},
        {"name": "event_type", "type": "STRING", "mode": "REQUIRED", "description": "Event type"},
        {"name": "event_version", "type": "STRING", "mode": "REQUIRED", "description": "Schema version"},
        {"name": "event_time", "type": "TIMESTAMP", "mode": "REQUIRED", "description": "Business event time"},
        {"name": "ingest_time", "type": "TIMESTAMP", "mode": "REQUIRED", "description": "Pipeline ingestion time"},
        {"name": "trace_id", "type": "STRING", "mode": "NULLABLE", "description": "Distributed tracing ID"},
        {"name": "source_system", "type": "STRING", "mode": "NULLABLE", "description": "Origin system"},
        {"name": "payload", "type": "JSON", "mode": "NULLABLE", "description": "Event payload"},
        {"name": "dedupe_key", "type": "STRING", "mode": "NULLABLE", "description": "Deduplication key"},
    ]

    # Domain-specific fields
    domain_fields = {
        "shipment": [
            {"name": "shipment_id", "type": "STRING", "mode": "NULLABLE", "description": "Shipment identifier"},
            {"name": "tracking_number", "type": "STRING", "mode": "NULLABLE", "description": "Tracking number"},
            {"name": "carrier_id", "type": "STRING", "mode": "NULLABLE", "description": "Carrier identifier"},
            {"name": "facility_id", "type": "STRING", "mode": "NULLABLE", "description": "Facility identifier"},
        ],
        "facility": [
            {"name": "facility_id", "type": "STRING", "mode": "NULLABLE", "description": "Facility identifier"},
            {"name": "facility_type", "type": "STRING", "mode": "NULLABLE", "description": "Facility type"},
            {"name": "region_id", "type": "STRING", "mode": "NULLABLE", "description": "Region identifier"},
        ],
        "driver": [
            {"name": "driver_id", "type": "STRING", "mode": "NULLABLE", "description": "Driver identifier"},
            {"name": "carrier_id", "type": "STRING", "mode": "NULLABLE", "description": "Carrier identifier"},
            {"name": "facility_id", "type": "STRING", "mode": "NULLABLE", "description": "Facility identifier"},
            {"name": "vehicle_id", "type": "STRING", "mode": "NULLABLE", "description": "Vehicle identifier"},
        ],
        "delivery": [
            {"name": "delivery_id", "type": "STRING", "mode": "NULLABLE", "description": "Delivery identifier"},
            {"name": "shipment_id", "type": "STRING", "mode": "NULLABLE", "description": "Shipment identifier"},
            {"name": "driver_id", "type": "STRING", "mode": "NULLABLE", "description": "Driver identifier"},
            {"name": "facility_id", "type": "STRING", "mode": "NULLABLE", "description": "Facility identifier"},
        ],
    }

    fields = common_fields + domain_fields.get(domain, [])

    return {"fields": fields}


def get_streaming_insert_schema(domain: str) -> str:
    """
    Get schema string for streaming inserts.

    Args:
        domain: Event domain

    Returns:
        Schema string for BigQuery streaming inserts
    """
    schema = get_table_schema(domain)
    return ",".join(
        f"{f['name']}:{f['type']}"
        for f in schema["fields"]
    )


# Curated layer (Gold) table schemas

FACT_DELIVERIES_SCHEMA = {
    "fields": [
        {"name": "delivery_id", "type": "STRING", "mode": "REQUIRED", "description": "Delivery identifier"},
        {"name": "shipment_id", "type": "STRING", "mode": "REQUIRED", "description": "Shipment identifier"},
        {"name": "delivery_date", "type": "DATE", "mode": "REQUIRED", "description": "Delivery date"},
        {"name": "facility_id", "type": "STRING", "mode": "NULLABLE", "description": "Origin facility"},
        {"name": "driver_id", "type": "STRING", "mode": "NULLABLE", "description": "Driver identifier"},
        {"name": "carrier_id", "type": "STRING", "mode": "NULLABLE", "description": "Carrier identifier"},
        {"name": "status", "type": "STRING", "mode": "NULLABLE", "description": "Final delivery status"},
        {"name": "scheduled_time", "type": "TIMESTAMP", "mode": "NULLABLE", "description": "Scheduled time"},
        {"name": "delivery_time", "type": "TIMESTAMP", "mode": "NULLABLE", "description": "Actual delivery time"},
        {"name": "first_attempt_time", "type": "TIMESTAMP", "mode": "NULLABLE", "description": "First attempt time"},
        {"name": "attempt_count", "type": "INT64", "mode": "NULLABLE", "description": "Number of attempts"},
        {"name": "on_time_flag", "type": "BOOL", "mode": "NULLABLE", "description": "Delivered on time"},
        {"name": "delivery_duration_minutes", "type": "INT64", "mode": "NULLABLE", "description": "Duration in minutes"},
    ]
}

FACT_SHIPMENT_EVENTS_SCHEMA = {
    "fields": [
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED", "description": "Event identifier"},
        {"name": "shipment_id", "type": "STRING", "mode": "REQUIRED", "description": "Shipment identifier"},
        {"name": "event_date", "type": "DATE", "mode": "REQUIRED", "description": "Event date"},
        {"name": "event_type", "type": "STRING", "mode": "REQUIRED", "description": "Event type"},
        {"name": "event_time", "type": "TIMESTAMP", "mode": "REQUIRED", "description": "Event timestamp"},
        {"name": "facility_id", "type": "STRING", "mode": "NULLABLE", "description": "Facility where event occurred"},
        {"name": "carrier_id", "type": "STRING", "mode": "NULLABLE", "description": "Carrier identifier"},
        {"name": "driver_id", "type": "STRING", "mode": "NULLABLE", "description": "Driver identifier"},
        {"name": "status", "type": "STRING", "mode": "NULLABLE", "description": "Shipment status"},
        {"name": "latitude", "type": "FLOAT64", "mode": "NULLABLE", "description": "Event latitude"},
        {"name": "longitude", "type": "FLOAT64", "mode": "NULLABLE", "description": "Event longitude"},
    ]
}

DIM_FACILITY_SCHEMA = {
    "fields": [
        {"name": "facility_id", "type": "STRING", "mode": "REQUIRED", "description": "Facility identifier"},
        {"name": "facility_name", "type": "STRING", "mode": "NULLABLE", "description": "Facility name"},
        {"name": "facility_type", "type": "STRING", "mode": "NULLABLE", "description": "Type of facility"},
        {"name": "address", "type": "STRING", "mode": "NULLABLE", "description": "Street address"},
        {"name": "city", "type": "STRING", "mode": "NULLABLE", "description": "City"},
        {"name": "state", "type": "STRING", "mode": "NULLABLE", "description": "State/Province"},
        {"name": "country", "type": "STRING", "mode": "NULLABLE", "description": "Country"},
        {"name": "postal_code", "type": "STRING", "mode": "NULLABLE", "description": "Postal code"},
        {"name": "latitude", "type": "FLOAT64", "mode": "NULLABLE", "description": "Latitude"},
        {"name": "longitude", "type": "FLOAT64", "mode": "NULLABLE", "description": "Longitude"},
        {"name": "timezone", "type": "STRING", "mode": "NULLABLE", "description": "Timezone"},
        {"name": "capacity_units", "type": "INT64", "mode": "NULLABLE", "description": "Capacity in units"},
        {"name": "is_active", "type": "BOOL", "mode": "NULLABLE", "description": "Is facility active"},
        {"name": "effective_from", "type": "TIMESTAMP", "mode": "REQUIRED", "description": "SCD2 effective from"},
        {"name": "effective_to", "type": "TIMESTAMP", "mode": "NULLABLE", "description": "SCD2 effective to"},
        {"name": "is_current", "type": "BOOL", "mode": "REQUIRED", "description": "Is current version"},
    ]
}

DIM_CARRIER_SCHEMA = {
    "fields": [
        {"name": "carrier_id", "type": "STRING", "mode": "REQUIRED", "description": "Carrier identifier"},
        {"name": "carrier_name", "type": "STRING", "mode": "NULLABLE", "description": "Carrier name"},
        {"name": "carrier_type", "type": "STRING", "mode": "NULLABLE", "description": "Type of carrier"},
        {"name": "scac_code", "type": "STRING", "mode": "NULLABLE", "description": "Standard Carrier Alpha Code"},
        {"name": "is_active", "type": "BOOL", "mode": "NULLABLE", "description": "Is carrier active"},
        {"name": "effective_from", "type": "TIMESTAMP", "mode": "REQUIRED", "description": "SCD2 effective from"},
        {"name": "effective_to", "type": "TIMESTAMP", "mode": "NULLABLE", "description": "SCD2 effective to"},
        {"name": "is_current", "type": "BOOL", "mode": "REQUIRED", "description": "Is current version"},
    ]
}

DIM_DRIVER_SCHEMA = {
    "fields": [
        {"name": "driver_id", "type": "STRING", "mode": "REQUIRED", "description": "Driver identifier"},
        {"name": "driver_name_hash", "type": "STRING", "mode": "NULLABLE", "description": "Hashed driver name (PII)"},
        {"name": "carrier_id", "type": "STRING", "mode": "NULLABLE", "description": "Associated carrier"},
        {"name": "home_facility_id", "type": "STRING", "mode": "NULLABLE", "description": "Home facility"},
        {"name": "license_type", "type": "STRING", "mode": "NULLABLE", "description": "License type"},
        {"name": "is_active", "type": "BOOL", "mode": "NULLABLE", "description": "Is driver active"},
        {"name": "effective_from", "type": "TIMESTAMP", "mode": "REQUIRED", "description": "SCD2 effective from"},
        {"name": "effective_to", "type": "TIMESTAMP", "mode": "NULLABLE", "description": "SCD2 effective to"},
        {"name": "is_current", "type": "BOOL", "mode": "REQUIRED", "description": "Is current version"},
    ]
}
