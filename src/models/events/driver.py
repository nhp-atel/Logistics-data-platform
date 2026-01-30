"""Driver event type definitions."""

from datetime import datetime
from enum import Enum
from typing import ClassVar

from pydantic import Field

from src.models.events.base import BaseEvent, GeoLocation


class DriverStatus(str, Enum):
    """Driver status enumeration."""

    AVAILABLE = "available"
    ON_ROUTE = "on_route"
    DELIVERING = "delivering"
    ON_BREAK = "on_break"
    OFF_DUTY = "off_duty"
    UNAVAILABLE = "unavailable"


class VehicleType(str, Enum):
    """Vehicle type enumeration."""

    VAN = "van"
    TRUCK = "truck"
    SEMI = "semi"
    CARGO_BIKE = "cargo_bike"
    MOTORCYCLE = "motorcycle"
    CAR = "car"


class DriverCreatedEvent(BaseEvent):
    """Event emitted when a new driver is registered."""

    EVENT_TYPE: ClassVar[str] = "driver.created"
    EVENT_VERSION: ClassVar[str] = "v1"

    driver_id: str = Field(..., description="Unique driver identifier")
    carrier_id: str = Field(..., description="Associated carrier ID")
    home_facility_id: str = Field(..., description="Home facility ID")

    # Driver info (PII fields to be masked)
    first_name: str = Field(..., description="Driver first name (PII)")
    last_name: str = Field(..., description="Driver last name (PII)")
    email: str | None = Field(default=None, description="Driver email (PII)")
    phone: str | None = Field(default=None, description="Driver phone (PII)")

    # License info
    license_number: str = Field(..., description="Driver license number (PII)")
    license_state: str = Field(..., description="License issuing state")
    license_type: str = Field(..., description="License type (CDL-A, CDL-B, etc.)")
    license_expiry: datetime = Field(..., description="License expiration date")

    # Vehicle
    vehicle_type: VehicleType = Field(..., description="Type of vehicle assigned")
    vehicle_id: str | None = Field(default=None, description="Assigned vehicle ID")

    # Status
    status: DriverStatus = Field(default=DriverStatus.OFF_DUTY, description="Initial status")
    hire_date: datetime = Field(..., description="Date driver was hired")


class DriverUpdatedEvent(BaseEvent):
    """Event emitted when driver details are updated."""

    EVENT_TYPE: ClassVar[str] = "driver.updated"
    EVENT_VERSION: ClassVar[str] = "v1"

    driver_id: str = Field(..., description="Driver identifier")
    updated_fields: list[str] = Field(..., description="List of fields that were updated")

    # Optional updated values
    home_facility_id: str | None = Field(default=None, description="Updated home facility")
    vehicle_type: VehicleType | None = Field(default=None, description="Updated vehicle type")
    vehicle_id: str | None = Field(default=None, description="Updated vehicle ID")
    license_expiry: datetime | None = Field(default=None, description="Updated license expiry")


class DriverAssignedEvent(BaseEvent):
    """Event emitted when a driver is assigned to a route or delivery."""

    EVENT_TYPE: ClassVar[str] = "driver.assigned"
    EVENT_VERSION: ClassVar[str] = "v1"

    driver_id: str = Field(..., description="Driver identifier")
    assignment_id: str = Field(..., description="Assignment identifier")
    assignment_type: str = Field(..., description="Type of assignment (route, delivery)")

    # Assignment details
    facility_id: str = Field(..., description="Starting facility")
    route_id: str | None = Field(default=None, description="Route identifier")
    delivery_ids: list[str] = Field(default_factory=list, description="List of delivery IDs")
    shipment_count: int = Field(default=0, ge=0, description="Number of shipments")

    # Timing
    assigned_at: datetime = Field(..., description="When assignment was made")
    expected_start_time: datetime = Field(..., description="Expected start time")
    expected_end_time: datetime = Field(..., description="Expected completion time")
    expected_distance_km: float | None = Field(default=None, ge=0, description="Expected distance")


class DriverLocationUpdatedEvent(BaseEvent):
    """Event emitted when driver location is updated (high frequency)."""

    EVENT_TYPE: ClassVar[str] = "driver.location_updated"
    EVENT_VERSION: ClassVar[str] = "v1"

    driver_id: str = Field(..., description="Driver identifier")
    vehicle_id: str | None = Field(default=None, description="Vehicle identifier")

    # Location
    location: GeoLocation = Field(..., description="Current location")

    # Context
    current_status: DriverStatus = Field(..., description="Current driver status")
    current_delivery_id: str | None = Field(default=None, description="Current delivery being made")
    route_id: str | None = Field(default=None, description="Current route ID")

    # Metrics
    distance_traveled_km: float = Field(default=0, ge=0, description="Distance since shift start")
    deliveries_completed: int = Field(default=0, ge=0, description="Deliveries completed today")
    deliveries_remaining: int = Field(default=0, ge=0, description="Deliveries remaining")


class DriverStatusChangedEvent(BaseEvent):
    """Event emitted when driver status changes."""

    EVENT_TYPE: ClassVar[str] = "driver.status_changed"
    EVENT_VERSION: ClassVar[str] = "v1"

    driver_id: str = Field(..., description="Driver identifier")
    previous_status: DriverStatus = Field(..., description="Previous status")
    new_status: DriverStatus = Field(..., description="New status")
    status_reason: str | None = Field(default=None, description="Reason for status change")

    # Location at status change
    location: GeoLocation | None = Field(default=None, description="Location at status change")
    facility_id: str | None = Field(default=None, description="Facility if at one")

    # Shift info
    shift_start_time: datetime | None = Field(default=None, description="Shift start time")
    break_start_time: datetime | None = Field(default=None, description="Break start if on break")
