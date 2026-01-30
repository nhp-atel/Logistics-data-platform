"""Delivery event type definitions."""

from datetime import datetime
from enum import Enum
from typing import ClassVar

from pydantic import Field

from src.models.events.base import BaseEvent, GeoLocation, Address


class DeliveryStatus(str, Enum):
    """Delivery status enumeration."""

    SCHEDULED = "scheduled"
    ASSIGNED = "assigned"
    EN_ROUTE = "en_route"
    ARRIVING = "arriving"
    ATTEMPTING = "attempting"
    COMPLETED = "completed"
    FAILED = "failed"
    RESCHEDULED = "rescheduled"
    CANCELLED = "cancelled"


class DeliveryFailureReason(str, Enum):
    """Reasons for delivery failure."""

    RECIPIENT_NOT_HOME = "recipient_not_home"
    WRONG_ADDRESS = "wrong_address"
    ACCESS_ISSUE = "access_issue"
    REFUSED = "refused"
    DAMAGED_PACKAGE = "damaged_package"
    WEATHER = "weather"
    VEHICLE_ISSUE = "vehicle_issue"
    DRIVER_ISSUE = "driver_issue"
    BUSINESS_CLOSED = "business_closed"
    OTHER = "other"


class DeliveryLocation(str, Enum):
    """Where package was left."""

    FRONT_DOOR = "front_door"
    BACK_DOOR = "back_door"
    SIDE_DOOR = "side_door"
    GARAGE = "garage"
    MAILROOM = "mailroom"
    RECEPTION = "reception"
    LOCKER = "locker"
    NEIGHBOR = "neighbor"
    SAFE_PLACE = "safe_place"
    IN_PERSON = "in_person"


class DeliveryScheduledEvent(BaseEvent):
    """Event emitted when a delivery is scheduled."""

    EVENT_TYPE: ClassVar[str] = "delivery.scheduled"
    EVENT_VERSION: ClassVar[str] = "v1"

    delivery_id: str = Field(..., description="Unique delivery identifier")
    shipment_id: str = Field(..., description="Associated shipment ID")
    tracking_number: str = Field(..., description="Tracking number")

    # Scheduling
    scheduled_date: datetime = Field(..., description="Scheduled delivery date")
    time_window_start: datetime | None = Field(default=None, description="Delivery window start")
    time_window_end: datetime | None = Field(default=None, description="Delivery window end")

    # Destination
    destination_address: Address = Field(..., description="Delivery address")
    delivery_instructions: str | None = Field(default=None, description="Special instructions")
    requires_signature: bool = Field(default=False, description="Signature required")
    is_residential: bool = Field(default=True, description="Residential vs commercial")

    # Origin
    origin_facility_id: str = Field(..., description="Origin facility")
    carrier_id: str = Field(..., description="Carrier handling delivery")

    # Priority
    priority: int = Field(default=5, ge=1, le=10, description="Priority level (1=highest)")
    is_expedited: bool = Field(default=False, description="Whether expedited delivery")


class DeliveryStartedEvent(BaseEvent):
    """Event emitted when driver starts delivery attempt."""

    EVENT_TYPE: ClassVar[str] = "delivery.started"
    EVENT_VERSION: ClassVar[str] = "v1"

    delivery_id: str = Field(..., description="Delivery identifier")
    shipment_id: str = Field(..., description="Shipment identifier")
    driver_id: str = Field(..., description="Driver making delivery")
    vehicle_id: str | None = Field(default=None, description="Vehicle identifier")

    # Start info
    started_at: datetime = Field(..., description="When delivery attempt started")
    departed_facility_id: str = Field(..., description="Facility departed from")
    departure_time: datetime = Field(..., description="Time departed facility")

    # Route info
    route_id: str | None = Field(default=None, description="Route identifier")
    stop_number: int = Field(..., ge=1, description="Stop number on route")
    total_stops: int = Field(..., ge=1, description="Total stops on route")

    # ETA
    estimated_arrival_time: datetime = Field(..., description="ETA at destination")
    distance_remaining_km: float = Field(..., ge=0, description="Distance to destination")


class DeliveryAttemptedEvent(BaseEvent):
    """Event emitted when a delivery attempt is made (success or failure)."""

    EVENT_TYPE: ClassVar[str] = "delivery.attempted"
    EVENT_VERSION: ClassVar[str] = "v1"

    delivery_id: str = Field(..., description="Delivery identifier")
    shipment_id: str = Field(..., description="Shipment identifier")
    driver_id: str = Field(..., description="Driver who made attempt")
    attempt_number: int = Field(..., ge=1, description="Attempt number")

    # Attempt result
    was_successful: bool = Field(..., description="Whether attempt succeeded")
    attempt_time: datetime = Field(..., description="Time of attempt")
    location: GeoLocation = Field(..., description="Location of attempt")

    # Failure details (if applicable)
    failure_reason: DeliveryFailureReason | None = Field(default=None, description="Reason if failed")
    failure_notes: str | None = Field(default=None, description="Additional failure details")

    # Success details (if applicable)
    delivery_location: DeliveryLocation | None = Field(default=None, description="Where package left")
    signed_by: str | None = Field(default=None, description="Who signed (PII)")

    # Evidence
    photo_url: str | None = Field(default=None, description="Proof of delivery photo URL")


class DeliveryCompletedEvent(BaseEvent):
    """Event emitted when a delivery is successfully completed."""

    EVENT_TYPE: ClassVar[str] = "delivery.completed"
    EVENT_VERSION: ClassVar[str] = "v1"

    delivery_id: str = Field(..., description="Delivery identifier")
    shipment_id: str = Field(..., description="Shipment identifier")
    driver_id: str = Field(..., description="Driver who completed delivery")

    # Completion details
    completed_at: datetime = Field(..., description="Completion time")
    delivery_location: DeliveryLocation = Field(..., description="Where package was left")
    location: GeoLocation = Field(..., description="GPS location at completion")

    # Signature
    signature_obtained: bool = Field(default=False, description="Was signature obtained")
    signed_by: str | None = Field(default=None, description="Name of signer (PII)")

    # Proof
    photo_url: str | None = Field(default=None, description="Delivery photo URL")
    delivery_notes: str | None = Field(default=None, description="Driver notes")

    # Metrics
    attempt_count: int = Field(default=1, ge=1, description="Total attempts needed")
    scheduled_time: datetime = Field(..., description="Originally scheduled time")
    was_on_time: bool = Field(..., description="Whether delivered on time")
    time_variance_minutes: int = Field(default=0, description="Minutes early/late")


class DeliveryFailedEvent(BaseEvent):
    """Event emitted when all delivery attempts fail."""

    EVENT_TYPE: ClassVar[str] = "delivery.failed"
    EVENT_VERSION: ClassVar[str] = "v1"

    delivery_id: str = Field(..., description="Delivery identifier")
    shipment_id: str = Field(..., description="Shipment identifier")
    driver_id: str = Field(..., description="Last driver who attempted")

    # Failure info
    failed_at: datetime = Field(..., description="When final failure occurred")
    total_attempts: int = Field(..., ge=1, description="Total attempts made")
    failure_reason: DeliveryFailureReason = Field(..., description="Final failure reason")
    failure_notes: str | None = Field(default=None, description="Failure details")

    # Next steps
    next_action: str = Field(..., description="Planned next action")
    reschedule_date: datetime | None = Field(default=None, description="Rescheduled date if applicable")
    return_to_facility_id: str | None = Field(default=None, description="Facility for return")


class DeliveryRescheduledEvent(BaseEvent):
    """Event emitted when a delivery is rescheduled."""

    EVENT_TYPE: ClassVar[str] = "delivery.rescheduled"
    EVENT_VERSION: ClassVar[str] = "v1"

    delivery_id: str = Field(..., description="Delivery identifier")
    shipment_id: str = Field(..., description="Shipment identifier")

    # Previous schedule
    previous_scheduled_date: datetime = Field(..., description="Previous scheduled date")

    # New schedule
    new_scheduled_date: datetime = Field(..., description="New scheduled date")
    new_time_window_start: datetime | None = Field(default=None, description="New window start")
    new_time_window_end: datetime | None = Field(default=None, description="New window end")

    # Reason
    reschedule_reason: str = Field(..., description="Reason for rescheduling")
    requested_by: str = Field(..., description="Who requested (customer, carrier, system)")
    attempt_count: int = Field(default=0, ge=0, description="Attempts before reschedule")
