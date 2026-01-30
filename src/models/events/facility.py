"""Facility event type definitions."""

from datetime import datetime, time
from enum import Enum
from typing import ClassVar

from pydantic import Field

from src.models.events.base import BaseEvent, Address


class FacilityType(str, Enum):
    """Facility type enumeration."""

    WAREHOUSE = "warehouse"
    DISTRIBUTION_CENTER = "distribution_center"
    CROSS_DOCK = "cross_dock"
    LAST_MILE_HUB = "last_mile_hub"
    RETURNS_CENTER = "returns_center"
    LOCKER = "locker"
    PARTNER_LOCATION = "partner_location"


class FacilityStatus(str, Enum):
    """Facility operational status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    CLOSED = "closed"
    CAPACITY_LIMITED = "capacity_limited"


class OperatingHours(BaseEvent):
    """Operating hours for a facility."""

    day_of_week: int = Field(..., ge=0, le=6, description="Day of week (0=Monday)")
    open_time: time = Field(..., description="Opening time")
    close_time: time = Field(..., description="Closing time")
    is_closed: bool = Field(default=False, description="Whether facility is closed this day")


class FacilityCreatedEvent(BaseEvent):
    """Event emitted when a new facility is created."""

    EVENT_TYPE: ClassVar[str] = "facility.created"
    EVENT_VERSION: ClassVar[str] = "v1"

    facility_id: str = Field(..., description="Unique facility identifier")
    facility_name: str = Field(..., description="Facility name")
    facility_type: FacilityType = Field(..., description="Type of facility")
    facility_code: str = Field(..., description="Short code for the facility")

    # Location
    address: Address = Field(..., description="Facility address")
    timezone: str = Field(default="UTC", description="Facility timezone")

    # Capacity
    capacity_units: int = Field(default=0, ge=0, description="Storage capacity in units")
    capacity_volume_cubic_meters: float | None = Field(default=None, ge=0, description="Volume capacity")
    max_daily_throughput: int | None = Field(default=None, ge=0, description="Max daily package throughput")

    # Organization
    region_id: str | None = Field(default=None, description="Region identifier")
    manager_id: str | None = Field(default=None, description="Manager identifier")
    carrier_ids: list[str] = Field(default_factory=list, description="Associated carrier IDs")

    # Capabilities
    supports_hazmat: bool = Field(default=False, description="Can handle hazardous materials")
    supports_refrigeration: bool = Field(default=False, description="Has refrigeration capability")
    supports_oversized: bool = Field(default=False, description="Can handle oversized packages")
    has_sorting_equipment: bool = Field(default=False, description="Has automated sorting")

    # Status
    status: FacilityStatus = Field(default=FacilityStatus.ACTIVE, description="Operational status")
    opened_date: datetime | None = Field(default=None, description="When facility opened")


class FacilityUpdatedEvent(BaseEvent):
    """Event emitted when facility details are updated."""

    EVENT_TYPE: ClassVar[str] = "facility.updated"
    EVENT_VERSION: ClassVar[str] = "v1"

    facility_id: str = Field(..., description="Facility identifier")
    updated_fields: list[str] = Field(..., description="List of fields that were updated")

    # Optional updated values (only present if updated)
    facility_name: str | None = Field(default=None, description="Updated facility name")
    address: Address | None = Field(default=None, description="Updated address")
    status: FacilityStatus | None = Field(default=None, description="Updated status")
    capacity_units: int | None = Field(default=None, ge=0, description="Updated capacity")
    max_daily_throughput: int | None = Field(default=None, ge=0, description="Updated throughput")


class FacilityCapacityChangedEvent(BaseEvent):
    """Event emitted when facility capacity changes significantly."""

    EVENT_TYPE: ClassVar[str] = "facility.capacity_changed"
    EVENT_VERSION: ClassVar[str] = "v1"

    facility_id: str = Field(..., description="Facility identifier")

    # Current utilization
    current_units: int = Field(..., ge=0, description="Current units in facility")
    max_capacity_units: int = Field(..., ge=0, description="Maximum capacity")
    utilization_percentage: float = Field(..., ge=0, le=100, description="Current utilization %")

    # Change details
    previous_utilization_percentage: float = Field(..., ge=0, le=100, description="Previous utilization %")
    change_reason: str | None = Field(default=None, description="Reason for capacity change")

    # Thresholds
    is_at_capacity: bool = Field(default=False, description="Whether at or over capacity")
    is_critical: bool = Field(default=False, description="Whether utilization is critical (>90%)")


class FacilityStatusChangedEvent(BaseEvent):
    """Event emitted when facility operational status changes."""

    EVENT_TYPE: ClassVar[str] = "facility.status_changed"
    EVENT_VERSION: ClassVar[str] = "v1"

    facility_id: str = Field(..., description="Facility identifier")
    previous_status: FacilityStatus = Field(..., description="Previous status")
    new_status: FacilityStatus = Field(..., description="New status")
    status_reason: str = Field(..., description="Reason for status change")
    expected_resolution_time: datetime | None = Field(default=None, description="When normal ops expected")

    # Impact assessment
    affected_shipment_count: int = Field(default=0, ge=0, description="Number of affected shipments")
    requires_rerouting: bool = Field(default=False, description="Whether shipments need rerouting")
    alternative_facility_id: str | None = Field(default=None, description="Alternative facility to use")
