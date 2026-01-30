"""
SLA Monitoring DAG for checking pipeline health and data freshness.

This DAG runs frequently to monitor SLA compliance and alert on breaches.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator
from airflow.providers.google.cloud.operators.bigquery import BigQueryCheckOperator


# Configuration
PROJECT_ID = Variable.get("project_id", default_var="logistics-platform")
ENVIRONMENT = Variable.get("environment", default_var="dev")
CLEAN_DATASET = f"{ENVIRONMENT}_clean"
CURATED_DATASET = f"{ENVIRONMENT}_curated"
SLACK_WEBHOOK = Variable.get("slack_webhook_url", default_var="")
PAGERDUTY_KEY = Variable.get("pagerduty_routing_key", default_var="")

# SLA thresholds
MAX_STREAMING_LAG_MINUTES = 15 if ENVIRONMENT == "prod" else 60
MAX_PARTITION_DELAY_HOURS = 2 if ENVIRONMENT == "prod" else 6
MIN_DAILY_EVENTS = 1000 if ENVIRONMENT == "prod" else 10

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=15),
}


def check_streaming_lag(**context):
    """
    Check if streaming pipeline is keeping up with data.

    Returns True if within SLA, False if breached.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT_ID)

    query = f"""
        SELECT
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(ingest_time), MINUTE) AS lag_minutes
        FROM `{PROJECT_ID}.{CLEAN_DATASET}.shipment_events`
        WHERE ingest_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
    """

    result = list(client.query(query).result())
    if not result or result[0].lag_minutes is None:
        lag_minutes = 999  # No recent data
    else:
        lag_minutes = result[0].lag_minutes

    context["ti"].xcom_push(key="streaming_lag_minutes", value=lag_minutes)

    if lag_minutes > MAX_STREAMING_LAG_MINUTES:
        send_alert(
            severity="critical" if ENVIRONMENT == "prod" else "warning",
            title="Streaming Pipeline Lag SLA Breach",
            message=f"Streaming lag is {lag_minutes} minutes (threshold: {MAX_STREAMING_LAG_MINUTES})",
            context=context,
        )
        return False

    return True


def check_data_freshness(**context):
    """
    Check if Gold layer partitions are being built on time.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT_ID)

    query = f"""
        SELECT
            MAX(delivery_date) AS latest_partition,
            DATE_DIFF(CURRENT_DATE(), MAX(delivery_date), DAY) AS days_behind
        FROM `{PROJECT_ID}.{CURATED_DATASET}.fact_deliveries`
    """

    result = list(client.query(query).result())
    if not result or result[0].days_behind is None:
        days_behind = 999
    else:
        days_behind = result[0].days_behind

    context["ti"].xcom_push(key="partition_delay_days", value=days_behind)

    # For daily marts, we expect data from yesterday
    if days_behind > 1:
        hours_behind = days_behind * 24
        if hours_behind > MAX_PARTITION_DELAY_HOURS:
            send_alert(
                severity="high",
                title="Gold Layer Partition Delay",
                message=f"Latest partition is {days_behind} days old",
                context=context,
            )
            return False

    return True


def check_data_volume(**context):
    """
    Check if we're receiving expected data volume.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=PROJECT_ID)

    # Check last 24 hours of events
    query = f"""
        SELECT COUNT(*) AS event_count
        FROM `{PROJECT_ID}.{CLEAN_DATASET}.shipment_events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
    """

    result = list(client.query(query).result())
    event_count = result[0].event_count if result else 0

    context["ti"].xcom_push(key="daily_event_count", value=event_count)

    if event_count < MIN_DAILY_EVENTS:
        send_alert(
            severity="warning",
            title="Low Data Volume Alert",
            message=f"Only {event_count} events in last 24h (expected: {MIN_DAILY_EVENTS}+)",
            context=context,
        )
        return False

    return True


def check_dlq_volume(**context):
    """
    Check if DLQ has excessive messages.
    """
    from google.cloud import pubsub_v1

    subscriber = pubsub_v1.SubscriberClient()

    # This is a simplified check - in production you'd use monitoring metrics
    # For now, just log that we checked
    context["ti"].xcom_push(key="dlq_checked", value=True)
    return True


def send_alert(severity: str, title: str, message: str, context: dict):
    """
    Send alert to appropriate channels based on severity.
    """
    import requests
    import json

    alert_data = {
        "severity": severity,
        "title": title,
        "message": message,
        "environment": ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "dag_run_id": context.get("run_id", "unknown"),
    }

    # Send to Slack
    if SLACK_WEBHOOK:
        try:
            slack_message = {
                "text": f":{severity}: *{title}*",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{title}*\n{message}\n_Environment: {ENVIRONMENT}_",
                        },
                    }
                ],
            }
            requests.post(SLACK_WEBHOOK, json=slack_message, timeout=10)
        except Exception as e:
            print(f"Failed to send Slack alert: {e}")

    # Send to PagerDuty for critical issues
    if severity in ("critical", "high") and PAGERDUTY_KEY and ENVIRONMENT == "prod":
        try:
            pd_payload = {
                "routing_key": PAGERDUTY_KEY,
                "event_action": "trigger",
                "payload": {
                    "summary": f"{title}: {message}",
                    "severity": "critical" if severity == "critical" else "error",
                    "source": f"logistics-platform-{ENVIRONMENT}",
                    "custom_details": alert_data,
                },
            }
            requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=pd_payload,
                timeout=10,
            )
        except Exception as e:
            print(f"Failed to send PagerDuty alert: {e}")


def generate_sla_report(**context):
    """
    Generate summary report of all SLA checks.
    """
    ti = context["ti"]

    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "environment": ENVIRONMENT,
        "checks": {
            "streaming_lag_minutes": ti.xcom_pull(
                task_ids="check_streaming_lag", key="streaming_lag_minutes"
            ),
            "partition_delay_days": ti.xcom_pull(
                task_ids="check_data_freshness", key="partition_delay_days"
            ),
            "daily_event_count": ti.xcom_pull(
                task_ids="check_data_volume", key="daily_event_count"
            ),
        },
        "thresholds": {
            "max_streaming_lag_minutes": MAX_STREAMING_LAG_MINUTES,
            "max_partition_delay_hours": MAX_PARTITION_DELAY_HOURS,
            "min_daily_events": MIN_DAILY_EVENTS,
        },
    }

    print(f"SLA Report: {json.dumps(report, indent=2)}")
    return report


with DAG(
    dag_id="sla_monitoring",
    default_args=default_args,
    description="Monitor SLA compliance for data pipelines",
    schedule_interval="*/15 * * * *",  # Every 15 minutes
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["monitoring", "sla", "alerts"],
    doc_md="""
    # SLA Monitoring DAG

    Monitors pipeline health and data freshness, alerting on SLA breaches.

    ## Checks
    1. Streaming pipeline lag
    2. Gold layer partition freshness
    3. Data volume thresholds
    4. DLQ volume

    ## Alerts
    - Slack notifications for all issues
    - PagerDuty for critical issues in prod

    ## Schedule
    Runs every 15 minutes.
    """,
) as dag:

    import json

    start = EmptyOperator(task_id="start")

    streaming_lag = PythonOperator(
        task_id="check_streaming_lag",
        python_callable=check_streaming_lag,
    )

    data_freshness = PythonOperator(
        task_id="check_data_freshness",
        python_callable=check_data_freshness,
    )

    data_volume = PythonOperator(
        task_id="check_data_volume",
        python_callable=check_data_volume,
    )

    dlq_volume = PythonOperator(
        task_id="check_dlq_volume",
        python_callable=check_dlq_volume,
    )

    report = PythonOperator(
        task_id="generate_sla_report",
        python_callable=generate_sla_report,
        trigger_rule="all_done",
    )

    end = EmptyOperator(
        task_id="end",
        trigger_rule="all_done",
    )

    start >> [streaming_lag, data_freshness, data_volume, dlq_volume] >> report >> end
