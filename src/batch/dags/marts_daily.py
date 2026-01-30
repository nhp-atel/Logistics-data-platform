"""
Daily marts DAG for building Gold layer aggregations.

This DAG runs daily to build fact and dimension tables from the Silver layer,
performing deduplication, SCD2 updates, and aggregations.
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.providers.google.cloud.operators.bigquery import (
    BigQueryInsertJobOperator,
    BigQueryCheckOperator,
)
from airflow.providers.google.cloud.sensors.bigquery import BigQueryTableExistenceSensor
from airflow.utils.task_group import TaskGroup


# Configuration
PROJECT_ID = Variable.get("project_id", default_var="logistics-platform")
REGION = Variable.get("region", default_var="us-central1")
ENVIRONMENT = Variable.get("environment", default_var="dev")
CLEAN_DATASET = f"{ENVIRONMENT}_clean"
CURATED_DATASET = f"{ENVIRONMENT}_curated"
NOTIFICATION_EMAIL = Variable.get(
    "notification_email", default_var="data-alerts@example.com"
)

# SQL templates directory
SQL_DIR = Path(__file__).parent.parent / "sql"

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "email": [NOTIFICATION_EMAIL],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


with DAG(
    dag_id="marts_daily",
    default_args=default_args,
    description="Build daily Gold layer marts from Silver layer data",
    schedule_interval="0 6 * * *",  # Run at 6 AM UTC daily
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["gold-layer", "daily", "marts"],
    doc_md="""
    # Daily Marts DAG

    Builds Gold layer fact and dimension tables from Silver layer data.

    ## Tasks
    1. Check Silver layer partitions are available
    2. Build dimension tables (SCD2)
    3. Build fact tables
    4. Run data quality checks

    ## Schedule
    Runs daily at 6 AM UTC, processing the previous day's data.
    """,
) as dag:

    start = EmptyOperator(task_id="start")
    end = EmptyOperator(task_id="end")

    # =========================================================================
    # Check Source Data Availability
    # =========================================================================

    with TaskGroup(group_id="check_sources") as check_sources:
        check_shipment_events = BigQueryCheckOperator(
            task_id="check_shipment_events",
            sql=f"""
                SELECT COUNT(*) > 0
                FROM `{PROJECT_ID}.{CLEAN_DATASET}.shipment_events`
                WHERE DATE(event_time) = '{{{{ ds }}}}'
            """,
            use_legacy_sql=False,
        )

        check_delivery_events = BigQueryCheckOperator(
            task_id="check_delivery_events",
            sql=f"""
                SELECT COUNT(*) > 0
                FROM `{PROJECT_ID}.{CLEAN_DATASET}.delivery_events`
                WHERE DATE(event_time) = '{{{{ ds }}}}'
            """,
            use_legacy_sql=False,
        )

        check_facility_events = BigQueryCheckOperator(
            task_id="check_facility_events",
            sql=f"""
                SELECT COUNT(*) >= 0  -- Facility events may not occur daily
                FROM `{PROJECT_ID}.{CLEAN_DATASET}.facility_events`
                WHERE DATE(event_time) = '{{{{ ds }}}}'
            """,
            use_legacy_sql=False,
        )

    # =========================================================================
    # Build Dimension Tables (SCD2)
    # =========================================================================

    with TaskGroup(group_id="build_dimensions") as build_dimensions:
        build_dim_facility = BigQueryInsertJobOperator(
            task_id="build_dim_facility",
            configuration={
                "query": {
                    "query": f"""
                        MERGE `{PROJECT_ID}.{CURATED_DATASET}.dim_facility` T
                        USING (
                            SELECT DISTINCT
                                facility_id,
                                JSON_VALUE(payload, '$.facility_name') AS facility_name,
                                JSON_VALUE(payload, '$.facility_type') AS facility_type,
                                JSON_VALUE(payload, '$.address.street') AS address,
                                JSON_VALUE(payload, '$.address.city') AS city,
                                JSON_VALUE(payload, '$.address.state') AS state,
                                JSON_VALUE(payload, '$.address.country') AS country,
                                JSON_VALUE(payload, '$.address.postal_code') AS postal_code,
                                CAST(JSON_VALUE(payload, '$.address.latitude') AS FLOAT64) AS latitude,
                                CAST(JSON_VALUE(payload, '$.address.longitude') AS FLOAT64) AS longitude,
                                JSON_VALUE(payload, '$.timezone') AS timezone,
                                CAST(JSON_VALUE(payload, '$.capacity_units') AS INT64) AS capacity_units,
                                COALESCE(JSON_VALUE(payload, '$.status'), 'active') = 'active' AS is_active,
                                MAX(event_time) AS last_updated
                            FROM `{PROJECT_ID}.{CLEAN_DATASET}.facility_events`
                            WHERE DATE(event_time) = '{{{{ ds }}}}'
                            GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13
                        ) S
                        ON T.facility_id = S.facility_id AND T.is_current = TRUE
                        WHEN MATCHED AND (
                            T.facility_name != S.facility_name OR
                            T.facility_type != S.facility_type OR
                            T.is_active != S.is_active
                        ) THEN UPDATE SET
                            is_current = FALSE,
                            effective_to = S.last_updated
                        WHEN NOT MATCHED THEN INSERT (
                            facility_id, facility_name, facility_type, address, city, state,
                            country, postal_code, latitude, longitude, timezone,
                            capacity_units, is_active, effective_from, effective_to, is_current
                        ) VALUES (
                            S.facility_id, S.facility_name, S.facility_type, S.address, S.city, S.state,
                            S.country, S.postal_code, S.latitude, S.longitude, S.timezone,
                            S.capacity_units, S.is_active, S.last_updated, NULL, TRUE
                        )
                    """,
                    "useLegacySql": False,
                }
            },
        )

        build_dim_carrier = BigQueryInsertJobOperator(
            task_id="build_dim_carrier",
            configuration={
                "query": {
                    "query": f"""
                        MERGE `{PROJECT_ID}.{CURATED_DATASET}.dim_carrier` T
                        USING (
                            SELECT DISTINCT
                                carrier_id,
                                JSON_VALUE(payload, '$.carrier_name') AS carrier_name,
                                JSON_VALUE(payload, '$.carrier_type') AS carrier_type,
                                JSON_VALUE(payload, '$.scac_code') AS scac_code,
                                TRUE AS is_active,
                                MAX(event_time) AS last_updated
                            FROM `{PROJECT_ID}.{CLEAN_DATASET}.shipment_events`
                            WHERE DATE(event_time) = '{{{{ ds }}}}'
                              AND carrier_id IS NOT NULL
                            GROUP BY 1,2,3,4,5
                        ) S
                        ON T.carrier_id = S.carrier_id AND T.is_current = TRUE
                        WHEN NOT MATCHED THEN INSERT (
                            carrier_id, carrier_name, carrier_type, scac_code,
                            is_active, effective_from, effective_to, is_current
                        ) VALUES (
                            S.carrier_id, S.carrier_name, S.carrier_type, S.scac_code,
                            S.is_active, S.last_updated, NULL, TRUE
                        )
                    """,
                    "useLegacySql": False,
                }
            },
        )

    # =========================================================================
    # Build Fact Tables
    # =========================================================================

    with TaskGroup(group_id="build_facts") as build_facts:
        build_fact_deliveries = BigQueryInsertJobOperator(
            task_id="build_fact_deliveries",
            configuration={
                "query": {
                    "query": f"""
                        INSERT INTO `{PROJECT_ID}.{CURATED_DATASET}.fact_deliveries`
                        (delivery_id, shipment_id, delivery_date, facility_id, driver_id,
                         carrier_id, status, scheduled_time, delivery_time, first_attempt_time,
                         attempt_count, on_time_flag, delivery_duration_minutes)
                        WITH delivery_events_deduped AS (
                            SELECT *,
                                ROW_NUMBER() OVER (
                                    PARTITION BY delivery_id, event_type
                                    ORDER BY event_time DESC
                                ) AS rn
                            FROM `{PROJECT_ID}.{CLEAN_DATASET}.delivery_events`
                            WHERE DATE(event_time) = '{{{{ ds }}}}'
                        ),
                        completed AS (
                            SELECT
                                JSON_VALUE(payload, '$.delivery_id') AS delivery_id,
                                JSON_VALUE(payload, '$.shipment_id') AS shipment_id,
                                facility_id,
                                JSON_VALUE(payload, '$.driver_id') AS driver_id,
                                TIMESTAMP(JSON_VALUE(payload, '$.completed_at')) AS delivery_time,
                                CAST(JSON_VALUE(payload, '$.attempt_count') AS INT64) AS attempt_count,
                                JSON_VALUE(payload, '$.was_on_time') = 'true' AS on_time_flag
                            FROM delivery_events_deduped
                            WHERE event_type = 'delivery.completed' AND rn = 1
                        ),
                        scheduled AS (
                            SELECT
                                JSON_VALUE(payload, '$.delivery_id') AS delivery_id,
                                JSON_VALUE(payload, '$.carrier_id') AS carrier_id,
                                TIMESTAMP(JSON_VALUE(payload, '$.scheduled_date')) AS scheduled_time
                            FROM delivery_events_deduped
                            WHERE event_type = 'delivery.scheduled' AND rn = 1
                        ),
                        first_attempt AS (
                            SELECT
                                JSON_VALUE(payload, '$.delivery_id') AS delivery_id,
                                MIN(event_time) AS first_attempt_time
                            FROM delivery_events_deduped
                            WHERE event_type = 'delivery.attempted'
                            GROUP BY 1
                        )
                        SELECT
                            c.delivery_id,
                            c.shipment_id,
                            DATE(c.delivery_time) AS delivery_date,
                            c.facility_id,
                            c.driver_id,
                            s.carrier_id,
                            'completed' AS status,
                            s.scheduled_time,
                            c.delivery_time,
                            fa.first_attempt_time,
                            c.attempt_count,
                            c.on_time_flag,
                            TIMESTAMP_DIFF(c.delivery_time, COALESCE(fa.first_attempt_time, c.delivery_time), MINUTE) AS delivery_duration_minutes
                        FROM completed c
                        LEFT JOIN scheduled s ON c.delivery_id = s.delivery_id
                        LEFT JOIN first_attempt fa ON c.delivery_id = fa.delivery_id
                    """,
                    "useLegacySql": False,
                    "writeDisposition": "WRITE_APPEND",
                }
            },
        )

        build_fact_shipment_events = BigQueryInsertJobOperator(
            task_id="build_fact_shipment_events",
            configuration={
                "query": {
                    "query": f"""
                        INSERT INTO `{PROJECT_ID}.{CURATED_DATASET}.fact_shipment_events`
                        (event_id, shipment_id, event_date, event_type, event_time,
                         facility_id, carrier_id, driver_id, status, latitude, longitude)
                        SELECT
                            event_id,
                            shipment_id,
                            DATE(event_time) AS event_date,
                            event_type,
                            event_time,
                            facility_id,
                            carrier_id,
                            JSON_VALUE(payload, '$.driver_id') AS driver_id,
                            JSON_VALUE(payload, '$.status') AS status,
                            CAST(JSON_VALUE(payload, '$.location.latitude') AS FLOAT64) AS latitude,
                            CAST(JSON_VALUE(payload, '$.location.longitude') AS FLOAT64) AS longitude
                        FROM `{PROJECT_ID}.{CLEAN_DATASET}.shipment_events`
                        WHERE DATE(event_time) = '{{{{ ds }}}}'
                    """,
                    "useLegacySql": False,
                    "writeDisposition": "WRITE_APPEND",
                }
            },
        )

    # =========================================================================
    # Data Quality Checks
    # =========================================================================

    with TaskGroup(group_id="quality_checks") as quality_checks:
        check_fact_deliveries = BigQueryCheckOperator(
            task_id="check_fact_deliveries",
            sql=f"""
                SELECT
                    COUNT(*) > 0 AS has_data,
                    COUNT(DISTINCT delivery_id) = COUNT(delivery_id) AS no_duplicates,
                    COUNT(*) FILTER(WHERE delivery_date = '{{{{ ds }}}}') > 0 AS correct_partition
                FROM `{PROJECT_ID}.{CURATED_DATASET}.fact_deliveries`
                WHERE delivery_date = '{{{{ ds }}}}'
            """,
            use_legacy_sql=False,
        )

        check_fact_shipments = BigQueryCheckOperator(
            task_id="check_fact_shipments",
            sql=f"""
                SELECT COUNT(*) > 0
                FROM `{PROJECT_ID}.{CURATED_DATASET}.fact_shipment_events`
                WHERE event_date = '{{{{ ds }}}}'
            """,
            use_legacy_sql=False,
        )

    # =========================================================================
    # Task Dependencies
    # =========================================================================

    start >> check_sources >> build_dimensions >> build_facts >> quality_checks >> end
