"""
Reconciliation DAG for handling late-arriving data.

This DAG runs periodically to reconcile late data that arrived after
the initial processing window, rebuilding affected Gold layer partitions.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.providers.google.cloud.operators.bigquery import (
    BigQueryInsertJobOperator,
    BigQueryCheckOperator,
)
from airflow.utils.task_group import TaskGroup


# Configuration
PROJECT_ID = Variable.get("project_id", default_var="logistics-platform")
ENVIRONMENT = Variable.get("environment", default_var="dev")
CLEAN_DATASET = f"{ENVIRONMENT}_clean"
CURATED_DATASET = f"{ENVIRONMENT}_curated"
STAGING_DATASET = f"{ENVIRONMENT}_staging"

# Lookback window for late data detection
LOOKBACK_DAYS = 7
LATE_THRESHOLD_HOURS = 4  # Events arriving more than 4 hours late

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(hours=3),
}


def detect_late_data(**context):
    """
    Detect partitions that have received late-arriving data.

    Returns list of dates that need reconciliation.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT_ID)

    query = f"""
        WITH late_events AS (
            SELECT
                DATE(event_time) AS event_date,
                COUNT(*) AS late_count
            FROM `{PROJECT_ID}.{CLEAN_DATASET}.shipment_events`
            WHERE
                -- Events ingested recently
                ingest_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 4 HOUR)
                -- But event time is older
                AND event_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {LATE_THRESHOLD_HOURS} HOUR)
                -- Within lookback window
                AND DATE(event_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL {LOOKBACK_DAYS} DAY)
            GROUP BY 1
            HAVING late_count > 10  -- Minimum threshold to trigger reconciliation
        )
        SELECT event_date
        FROM late_events
        ORDER BY event_date
    """

    result = client.query(query).result()
    dates_to_reconcile = [row.event_date.isoformat() for row in result]

    context["ti"].xcom_push(key="dates_to_reconcile", value=dates_to_reconcile)

    return dates_to_reconcile


def check_reconciliation_needed(**context):
    """Branch based on whether reconciliation is needed."""
    dates = context["ti"].xcom_pull(
        task_ids="detect_late_data", key="dates_to_reconcile"
    )

    if dates and len(dates) > 0:
        return "reconcile_partitions"
    return "skip_reconciliation"


def reconcile_partition(date_str: str, **context):
    """
    Reconcile a single partition by rebuilding it.

    This performs a full rebuild of the affected Gold layer partition
    using all available Silver layer data.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT_ID)

    # Delete existing partition
    delete_query = f"""
        DELETE FROM `{PROJECT_ID}.{CURATED_DATASET}.fact_deliveries`
        WHERE delivery_date = '{date_str}'
    """
    client.query(delete_query).result()

    # Rebuild partition (same logic as marts_daily but for specific date)
    rebuild_query = f"""
        INSERT INTO `{PROJECT_ID}.{CURATED_DATASET}.fact_deliveries`
        (delivery_id, shipment_id, delivery_date, facility_id, driver_id,
         carrier_id, status, scheduled_time, delivery_time, first_attempt_time,
         attempt_count, on_time_flag, delivery_duration_minutes)
        WITH delivery_events_deduped AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY JSON_VALUE(payload, '$.delivery_id'), event_type
                    ORDER BY event_time DESC
                ) AS rn
            FROM `{PROJECT_ID}.{CLEAN_DATASET}.delivery_events`
            WHERE DATE(event_time) = '{date_str}'
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
            TIMESTAMP_DIFF(c.delivery_time, COALESCE(fa.first_attempt_time, c.delivery_time), MINUTE)
        FROM completed c
        LEFT JOIN scheduled s ON c.delivery_id = s.delivery_id
        LEFT JOIN first_attempt fa ON c.delivery_id = fa.delivery_id
    """
    client.query(rebuild_query).result()

    return f"Reconciled partition: {date_str}"


with DAG(
    dag_id="reconciliation",
    default_args=default_args,
    description="Reconcile late-arriving data in Gold layer",
    schedule_interval="0 */4 * * *",  # Every 4 hours
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["reconciliation", "late-data", "gold-layer"],
    doc_md="""
    # Reconciliation DAG

    Detects and reconciles late-arriving data that was missed by the daily marts build.

    ## Process
    1. Detect partitions with significant late data
    2. Rebuild affected Gold layer partitions
    3. Log reconciliation metrics

    ## Schedule
    Runs every 4 hours to catch late data promptly.
    """,
) as dag:

    start = EmptyOperator(task_id="start")

    detect = PythonOperator(
        task_id="detect_late_data",
        python_callable=detect_late_data,
    )

    check = BranchPythonOperator(
        task_id="check_reconciliation_needed",
        python_callable=check_reconciliation_needed,
    )

    skip = EmptyOperator(
        task_id="skip_reconciliation",
    )

    # Dynamic task generation for each date to reconcile
    reconcile = PythonOperator(
        task_id="reconcile_partitions",
        python_callable=lambda **ctx: [
            reconcile_partition(date, **ctx)
            for date in ctx["ti"].xcom_pull(
                task_ids="detect_late_data", key="dates_to_reconcile"
            )
        ],
    )

    log_metrics = PythonOperator(
        task_id="log_reconciliation_metrics",
        python_callable=lambda **ctx: print(
            f"Reconciled {len(ctx['ti'].xcom_pull(task_ids='detect_late_data', key='dates_to_reconcile') or [])} partitions"
        ),
        trigger_rule="none_failed_min_one_success",
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule="none_failed_min_one_success",
    )

    start >> detect >> check
    check >> skip >> log_metrics >> end
    check >> reconcile >> log_metrics >> end
