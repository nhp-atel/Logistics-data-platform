"""Shipment-related API endpoints."""

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


class ShipmentSummary(BaseModel):
    """Summary information for a shipment."""
    shipment_id: str
    tracking_number: str | None
    status: str
    carrier_id: str | None
    created_at: datetime | None
    delivered_at: datetime | None


class ShipmentListResponse(BaseModel):
    """Paginated list of shipments."""
    shipments: list[ShipmentSummary]
    total_count: int
    page: int
    page_size: int


@router.get("/", response_model=ShipmentListResponse)
async def list_shipments(
    status: str | None = Query(default=None, description="Filter by status"),
    carrier_id: str | None = Query(default=None, description="Filter by carrier"),
    date_from: date | None = Query(default=None, description="Start date"),
    date_to: date | None = Query(default=None, description="End date"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Page size"),
):
    """
    List shipments with optional filtering and pagination.
    """
    # Implementation would query BigQuery
    return ShipmentListResponse(
        shipments=[],
        total_count=0,
        page=page,
        page_size=page_size,
    )


@router.get("/{shipment_id}")
async def get_shipment(shipment_id: str):
    """Get details for a specific shipment."""
    # Implementation would query BigQuery
    raise HTTPException(status_code=404, detail="Shipment not found")


@router.get("/{shipment_id}/events")
async def get_shipment_events(
    shipment_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Get all events for a shipment."""
    return {"shipment_id": shipment_id, "events": []}
