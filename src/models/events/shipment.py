"""Shipment event type definitions."""

from datetime import datetime
from enum import Enum
from typing import ClassVar

from pydantic import Field

from src.models.events.base import BaseEvent, Address, ContactInfo, Dimensions


class ShipmentStatus(str, Enum):
    """Shipment status enumeration."""

    CREATED = "created"
    LABEL_PRINTED = "label_printed"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERY_ATTEMPTED = "delivery_attempted"
    RETURNED = "returned"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"
    EXCEPTION = "exception"


class ServiceLevel(str, Enum):
    """Shipping service level enumeration."""

    GROUND = "ground"
    EXPRESS = "express"
    OVERNIGHT = "overnight"
    SAME_DAY = "same_day"
    ECONOMY = "economy"
    FREIGHT = "freight"


class ShipmentCreatedEvent(BaseEvent):
    """Event emitted when a new shipment is created."""

    EVENT_TYPE: ClassVar[str] = "shipment.created"
    EVENT_VERSION: ClassVar[str] = "v1"

    shipment_id: str = Field(..., description="Unique shipment identifier")
    tracking_number: str = Field(..., description="Tracking number for the shipment")
    carrier_id: str = Field(..., description="Carrier identifier")
    service_level: ServiceLevel = Field(..., description="Service level for delivery")

    # Addresses
    origin_address: Address = Field(..., description="Origin/sender address")
    destination_address: Address = Field(..., description="Destination/recipient address")

    # Contacts
    sender: ContactInfo = Field(..., description="Sender contact information")
    recipient: ContactInfo = Field(..., description="Recipient contact information")

    # Package details
    dimensions: Dimensions | None = Field(default=None, description="Package dimensions")
    declared_value_cents: int | None = Field(default=None, ge=0, description="Declared value in cents")
    contents_description: str | None = Field(default=None, description="Description of contents")
    is_fragile: bool = Field(default=False, description="Whether the package is fragile")
    requires_signature: bool = Field(default=False, description="Whether delivery requires signature")

    # Scheduling
    estimated_delivery_date: datetime | None = Field(default=None, description="Estimated delivery date")
    scheduled_pickup_time: datetime | None = Field(default=None, description="Scheduled pickup time")

    # Business context
    order_id: str | None = Field(default=None, description="Associated order ID")
    customer_id: str | None = Field(default=None, description="Customer identifier")
    facility_id: str | None = Field(default=None, description="Origin facility ID")


class ShipmentUpdatedEvent(BaseEvent):
    """Event emitted when shipment details are updated."""

    EVENT_TYPE: ClassVar[str] = "shipment.updated"
    EVENT_VERSION: ClassVar[str] = "v1"

    shipment_id: str = Field(..., description="Shipment identifier")
    tracking_number: str = Field(..., description="Tracking number")
    previous_status: ShipmentStatus | None = Field(default=None, description="Previous status")
    current_status: ShipmentStatus = Field(..., description="Current status")
    status_reason: str | None = Field(default=None, description="Reason for status change")

    # Location information
    facility_id: str | None = Field(default=None, description="Current facility ID")
    location_description: str | None = Field(default=None, description="Human-readable location")

    # Updated estimates
    estimated_delivery_date: datetime | None = Field(default=None, description="Updated delivery estimate")

    # Exception details
    exception_code: str | None = Field(default=None, description="Exception code if applicable")
    exception_message: str | None = Field(default=None, description="Exception details")


class ShipmentDeliveredEvent(BaseEvent):
    """Event emitted when a shipment is delivered."""

    EVENT_TYPE: ClassVar[str] = "shipment.delivered"
    EVENT_VERSION: ClassVar[str] = "v1"

    shipment_id: str = Field(..., description="Shipment identifier")
    tracking_number: str = Field(..., description="Tracking number")
    delivery_id: str = Field(..., description="Delivery identifier")
    driver_id: str | None = Field(default=None, description="Driver who made delivery")
    facility_id: str | None = Field(default=None, description="Origin facility")

    # Delivery details
    delivery_time: datetime = Field(..., description="Actual delivery time")
    delivery_location: str | None = Field(default=None, description="Where package was left")
    signed_by: str | None = Field(default=None, description="Name of person who signed")
    signature_required: bool = Field(default=False, description="Was signature required")
    signature_obtained: bool = Field(default=False, description="Was signature obtained")

    # Proof of delivery
    photo_url: str | None = Field(default=None, description="URL to delivery photo")
    delivery_notes: str | None = Field(default=None, description="Driver notes")

    # Metrics
    delivery_attempt_count: int = Field(default=1, ge=1, description="Number of delivery attempts")
    was_on_time: bool = Field(default=True, description="Whether delivery was on time")


class ShipmentInTransitEvent(BaseEvent):
    """Event emitted when shipment status changes to in-transit."""

    EVENT_TYPE: ClassVar[str] = "shipment.in_transit"
    EVENT_VERSION: ClassVar[str] = "v1"

    shipment_id: str = Field(..., description="Shipment identifier")
    tracking_number: str = Field(..., description="Tracking number")
    carrier_id: str = Field(..., description="Carrier identifier")

    # Current location
    current_facility_id: str | None = Field(default=None, description="Current facility")
    next_facility_id: str | None = Field(default=None, description="Next facility in route")
    current_location: str | None = Field(default=None, description="Current location description")

    # Vehicle/transport info
    vehicle_id: str | None = Field(default=None, description="Vehicle identifier")
    driver_id: str | None = Field(default=None, description="Driver identifier")
    transport_mode: str | None = Field(default=None, description="Mode of transport (truck, air, etc.)")

    # Timing
    departed_at: datetime | None = Field(default=None, description="Departure time from last facility")
    estimated_arrival: datetime | None = Field(default=None, description="ETA at next facility")


class ShipmentCancelledEvent(BaseEvent):
    """Event emitted when a shipment is cancelled."""

    EVENT_TYPE: ClassVar[str] = "shipment.cancelled"
    EVENT_VERSION: ClassVar[str] = "v1"

    shipment_id: str = Field(..., description="Shipment identifier")
    tracking_number: str = Field(..., description="Tracking number")
    cancellation_reason: str = Field(..., description="Reason for cancellation")
    cancelled_by: str = Field(..., description="Who cancelled (customer, carrier, system)")
    refund_eligible: bool = Field(default=False, description="Whether refund is eligible")
    previous_status: ShipmentStatus = Field(..., description="Status before cancellation")
