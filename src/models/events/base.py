"""Base event class and common event utilities."""

from datetime import datetime, timezone
from typing import Any, ClassVar
import uuid

from pydantic import BaseModel, Field, field_validator


class BaseEvent(BaseModel):
    """
    Base class for all event types in the logistics platform.

    Provides common fields and validation for event payloads.
    """

    # Class-level attributes to be overridden by subclasses
    EVENT_TYPE: ClassVar[str] = "unknown"
    EVENT_VERSION: ClassVar[str] = "v1"

    # Common fields present in all events
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique event identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the event occurred",
    )
    correlation_id: str | None = Field(default=None, description="Correlation ID for request tracing")
    causation_id: str | None = Field(default=None, description="ID of the event that caused this event")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, v: Any) -> datetime:
        """Parse timestamp from various formats."""
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, (int, float)):
            return datetime.fromtimestamp(v, tz=timezone.utc)
        return datetime.now(timezone.utc)

    def to_envelope_dict(self) -> dict[str, Any]:
        """Convert to a dictionary suitable for EventEnvelope payload."""
        data = self.model_dump(mode="json")
        # Remove fields that are in the envelope, not the payload
        for field_name in ["id", "timestamp"]:
            data.pop(field_name, None)
        return data

    @classmethod
    def get_event_type(cls) -> str:
        """Get the event type string."""
        return cls.EVENT_TYPE

    @classmethod
    def get_event_version(cls) -> str:
        """Get the event version string."""
        return cls.EVENT_VERSION

    class Config:
        """Pydantic model configuration."""

        populate_by_name = True
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class Address(BaseModel):
    """Address model used across multiple event types."""

    street: str = Field(..., description="Street address")
    city: str = Field(..., description="City")
    state: str = Field(..., description="State or province")
    postal_code: str = Field(..., description="Postal or ZIP code")
    country: str = Field(default="US", description="Country code")
    latitude: float | None = Field(default=None, description="Latitude coordinate")
    longitude: float | None = Field(default=None, description="Longitude coordinate")


class GeoLocation(BaseModel):
    """Geographic location model."""

    latitude: float = Field(..., ge=-90, le=90, description="Latitude")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude")
    accuracy_meters: float | None = Field(default=None, ge=0, description="Accuracy in meters")
    altitude_meters: float | None = Field(default=None, description="Altitude in meters")
    heading: float | None = Field(default=None, ge=0, lt=360, description="Heading in degrees")
    speed_mps: float | None = Field(default=None, ge=0, description="Speed in meters per second")


class ContactInfo(BaseModel):
    """Contact information model."""

    name: str = Field(..., description="Contact name")
    phone: str | None = Field(default=None, description="Phone number")
    email: str | None = Field(default=None, description="Email address")


class Dimensions(BaseModel):
    """Package dimensions model."""

    length_cm: float = Field(..., gt=0, description="Length in centimeters")
    width_cm: float = Field(..., gt=0, description="Width in centimeters")
    height_cm: float = Field(..., gt=0, description="Height in centimeters")
    weight_kg: float = Field(..., gt=0, description="Weight in kilograms")

    @property
    def volume_cubic_cm(self) -> float:
        """Calculate volume in cubic centimeters."""
        return self.length_cm * self.width_cm * self.height_cm

    @property
    def dimensional_weight_kg(self, divisor: float = 5000) -> float:
        """Calculate dimensional weight using standard divisor."""
        return self.volume_cubic_cm / divisor
