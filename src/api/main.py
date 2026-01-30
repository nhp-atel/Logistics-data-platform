"""
FastAPI Analytics API for the logistics data platform.

Provides read-only access to curated data for dashboards and applications.
"""

import os
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import bigquery
from pydantic import BaseModel, Field

from src.api.routers import shipments, facilities, metrics
from src.api.services.bigquery_service import BigQueryService
from src.common.logging_utils import setup_logging, get_logger

logger = get_logger(__name__)

# Configuration
PROJECT_ID = os.environ.get("GCP_PROJECT", "logistics-platform")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
CURATED_DATASET = os.environ.get("CURATED_DATASET", f"{ENVIRONMENT}_curated")
FEATURES_DATASET = os.environ.get("FEATURES_DATASET", f"{ENVIRONMENT}_features")

# Global BigQuery client
bq_client: bigquery.Client | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    global bq_client

    # Startup
    setup_logging(
        service_name="analytics-api",
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        use_json=ENVIRONMENT != "dev",
    )
    logger.info(f"Starting Analytics API in {ENVIRONMENT} environment")

    bq_client = bigquery.Client(project=PROJECT_ID)
    logger.info("BigQuery client initialized")

    yield

    # Shutdown
    if bq_client:
        bq_client.close()
    logger.info("Analytics API shutdown complete")


app = FastAPI(
    title="Logistics Analytics API",
    description="Read-only API for logistics data analytics",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if ENVIRONMENT == "dev" else None,
    redoc_url="/redoc" if ENVIRONMENT == "dev" else None,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if ENVIRONMENT == "dev" else ["https://dashboard.logistics.example.com"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


# Dependency for BigQuery service
def get_bq_service() -> BigQueryService:
    """Get BigQuery service instance."""
    if bq_client is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return BigQueryService(bq_client, PROJECT_ID, CURATED_DATASET)


# Include routers
app.include_router(shipments.router, prefix="/api/v1/shipments", tags=["Shipments"])
app.include_router(facilities.router, prefix="/api/v1/facilities", tags=["Facilities"])
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["Metrics"])


# Health and info endpoints

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    environment: str
    timestamp: datetime


class InfoResponse(BaseModel):
    """API info response."""
    name: str
    version: str
    environment: str


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for load balancers."""
    return HealthResponse(
        status="healthy",
        environment=ENVIRONMENT,
        timestamp=datetime.utcnow(),
    )


@app.get("/", response_model=InfoResponse)
async def root():
    """API root endpoint."""
    return InfoResponse(
        name="Logistics Analytics API",
        version="1.0.0",
        environment=ENVIRONMENT,
    )


# Inline endpoint implementations for core functionality

class ShipmentTimelineEvent(BaseModel):
    """Single event in shipment timeline."""
    event_type: str
    event_time: datetime
    facility_id: str | None = None
    status: str | None = None
    location: dict[str, float] | None = None


class ShipmentTimelineResponse(BaseModel):
    """Shipment timeline response."""
    shipment_id: str
    events: list[ShipmentTimelineEvent]


@app.get("/api/v1/shipments/{shipment_id}/timeline", response_model=ShipmentTimelineResponse)
async def get_shipment_timeline(
    shipment_id: str,
    bq: BigQueryService = Depends(get_bq_service),
):
    """
    Get timeline of events for a shipment.

    Returns chronological list of all events for the specified shipment.
    """
    query = f"""
        SELECT
            event_type,
            event_time,
            facility_id,
            status,
            latitude,
            longitude
        FROM `{PROJECT_ID}.{CURATED_DATASET}.fact_shipment_events`
        WHERE shipment_id = @shipment_id
        ORDER BY event_time
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("shipment_id", "STRING", shipment_id)
        ]
    )

    try:
        results = bq.client.query(query, job_config=job_config).result()
        events = []
        for row in results:
            location = None
            if row.latitude and row.longitude:
                location = {"latitude": row.latitude, "longitude": row.longitude}
            events.append(ShipmentTimelineEvent(
                event_type=row.event_type,
                event_time=row.event_time,
                facility_id=row.facility_id,
                status=row.status,
                location=location,
            ))

        return ShipmentTimelineResponse(shipment_id=shipment_id, events=events)

    except Exception as e:
        logger.error(f"Failed to get shipment timeline: {e}", shipment_id=shipment_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve timeline")


class FacilityMetrics(BaseModel):
    """Facility performance metrics."""
    facility_id: str
    date: date
    total_deliveries: int
    on_time_deliveries: int
    on_time_rate: float
    avg_delivery_duration_minutes: float | None
    total_attempts: int


@app.get("/api/v1/facilities/{facility_id}/metrics", response_model=FacilityMetrics)
async def get_facility_metrics(
    facility_id: str,
    metrics_date: date = Query(default=None, description="Date for metrics (defaults to yesterday)"),
    bq: BigQueryService = Depends(get_bq_service),
):
    """
    Get performance metrics for a facility.

    Returns aggregated delivery metrics for the specified date.
    """
    if metrics_date is None:
        from datetime import timedelta
        metrics_date = date.today() - timedelta(days=1)

    query = f"""
        SELECT
            facility_id,
            delivery_date,
            COUNT(*) AS total_deliveries,
            COUNTIF(on_time_flag) AS on_time_deliveries,
            SAFE_DIVIDE(COUNTIF(on_time_flag), COUNT(*)) AS on_time_rate,
            AVG(delivery_duration_minutes) AS avg_delivery_duration_minutes,
            SUM(attempt_count) AS total_attempts
        FROM `{PROJECT_ID}.{CURATED_DATASET}.fact_deliveries`
        WHERE facility_id = @facility_id
          AND delivery_date = @date
        GROUP BY facility_id, delivery_date
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("facility_id", "STRING", facility_id),
            bigquery.ScalarQueryParameter("date", "DATE", metrics_date),
        ]
    )

    try:
        results = list(bq.client.query(query, job_config=job_config).result())

        if not results:
            raise HTTPException(status_code=404, detail="No metrics found for facility/date")

        row = results[0]
        return FacilityMetrics(
            facility_id=row.facility_id,
            date=row.delivery_date,
            total_deliveries=row.total_deliveries,
            on_time_deliveries=row.on_time_deliveries,
            on_time_rate=row.on_time_rate or 0.0,
            avg_delivery_duration_minutes=row.avg_delivery_duration_minutes,
            total_attempts=row.total_attempts,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get facility metrics: {e}", facility_id=facility_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=ENVIRONMENT == "dev",
    )
