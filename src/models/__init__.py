"""Data models for the logistics platform."""

from src.models.events.base import BaseEvent
from src.models.events.shipment import (
    ShipmentCreatedEvent,
    ShipmentUpdatedEvent,
    ShipmentDeliveredEvent,
)
from src.models.events.facility import (
    FacilityCreatedEvent,
    FacilityUpdatedEvent,
)
from src.models.events.driver import (
    DriverCreatedEvent,
    DriverLocationUpdatedEvent,
)
from src.models.events.delivery import (
    DeliveryScheduledEvent,
    DeliveryCompletedEvent,
)

__all__ = [
    "BaseEvent",
    "ShipmentCreatedEvent",
    "ShipmentUpdatedEvent",
    "ShipmentDeliveredEvent",
    "FacilityCreatedEvent",
    "FacilityUpdatedEvent",
    "DriverCreatedEvent",
    "DriverLocationUpdatedEvent",
    "DeliveryScheduledEvent",
    "DeliveryCompletedEvent",
]
