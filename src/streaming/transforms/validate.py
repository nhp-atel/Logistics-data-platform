"""
Schema validation transform for events.
"""

import json
from pathlib import Path
from typing import Any, Iterator

import apache_beam as beam
from apache_beam.pvalue import TaggedOutput
import jsonschema
from jsonschema import Draft7Validator

from src.common.schemas import EventEnvelope, ValidationError
from src.common.logging_utils import get_logger
from src.common.metrics import beam_metrics

logger = get_logger(__name__)


class ValidateSchema(beam.DoFn):
    """
    Validate events against JSON schemas.

    Outputs valid events to the main output and invalid events
    to the 'invalid' tagged output.
    """

    # Output tags
    VALID_TAG = "valid"
    INVALID_TAG = "invalid"

    def __init__(self, schema_dir: str | None = None):
        """
        Initialize the validator.

        Args:
            schema_dir: Directory containing JSON schema files.
                       Defaults to config/event_schemas/
        """
        super().__init__()
        self.schema_dir = schema_dir
        self._schemas: dict[str, dict] = {}
        self._validators: dict[str, Draft7Validator] = {}
        self._counter_valid = None
        self._counter_invalid = None

    def setup(self):
        """Load schemas and initialize counters."""
        self._load_schemas()
        self._counter_valid = beam_metrics.get_counter("validation_valid")
        self._counter_invalid = beam_metrics.get_counter("validation_invalid")

    def _load_schemas(self):
        """Load JSON schemas from disk."""
        if self.schema_dir:
            schema_path = Path(self.schema_dir)
        else:
            # Default path relative to project root
            schema_path = Path(__file__).parent.parent.parent.parent / "config" / "event_schemas"

        if not schema_path.exists():
            logger.warning(f"Schema directory not found: {schema_path}")
            return

        for schema_file in schema_path.glob("*.json"):
            try:
                with open(schema_file) as f:
                    schema = json.load(f)
                    schema_name = schema_file.stem
                    self._schemas[schema_name] = schema
                    self._validators[schema_name] = Draft7Validator(schema)
                    logger.debug(f"Loaded schema: {schema_name}")
            except Exception as e:
                logger.error(f"Failed to load schema {schema_file}: {e}")

    def process(self, event: EventEnvelope) -> Iterator[EventEnvelope | TaggedOutput]:
        """
        Validate an event against its schema.

        Args:
            event: Event to validate

        Yields:
            Valid events to main output, invalid events to 'invalid' tag
        """
        errors = self._validate_event(event)

        if errors:
            self._counter_invalid.inc()
            logger.warning(
                "Event failed validation",
                event_id=event.event_id,
                event_type=event.event_type,
                error_count=len(errors),
            )
            # Attach errors to event for DLQ processing
            event.payload["_validation_errors"] = [e.to_dict() for e in errors]
            yield TaggedOutput(self.INVALID_TAG, event)
        else:
            self._counter_valid.inc()
            yield TaggedOutput(self.VALID_TAG, event)

    def _validate_event(self, event: EventEnvelope) -> list[ValidationError]:
        """
        Validate an event and return any errors.

        Args:
            event: Event to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Basic envelope validation
        if not event.event_id:
            errors.append(ValidationError(
                field="event_id",
                message="Event ID is required",
                error_code="REQUIRED_FIELD",
            ))

        if not event.event_type:
            errors.append(ValidationError(
                field="event_type",
                message="Event type is required",
                error_code="REQUIRED_FIELD",
            ))

        # Validate event type format
        if event.event_type and "." not in event.event_type:
            errors.append(ValidationError(
                field="event_type",
                message="Event type must be in format 'domain.action'",
                error_code="INVALID_FORMAT",
                value=event.event_type,
            ))

        # Schema validation
        schema_key = self._get_schema_key(event)
        if schema_key and schema_key in self._validators:
            validator = self._validators[schema_key]
            for error in validator.iter_errors(event.payload):
                errors.append(ValidationError(
                    field=".".join(str(p) for p in error.absolute_path) or "root",
                    message=error.message,
                    error_code="SCHEMA_VIOLATION",
                    value=error.instance if not isinstance(error.instance, dict) else None,
                ))

        # Domain-specific validation
        domain_errors = self._validate_domain_rules(event)
        errors.extend(domain_errors)

        return errors

    def _get_schema_key(self, event: EventEnvelope) -> str | None:
        """Get the schema key for an event."""
        # Try versioned schema first
        versioned_key = f"{event.event_type}_{event.event_version}"
        if versioned_key in self._schemas:
            return versioned_key

        # Try unversioned schema
        if event.event_type in self._schemas:
            return event.event_type

        # Try domain-level schema
        domain = event.get_domain()
        if domain in self._schemas:
            return domain

        return None

    def _validate_domain_rules(self, event: EventEnvelope) -> list[ValidationError]:
        """Apply domain-specific validation rules."""
        errors = []
        domain = event.get_domain()
        payload = event.payload

        if domain == "shipment":
            # Shipment events should have shipment_id
            if "shipment_id" not in payload and "shipmentId" not in payload:
                errors.append(ValidationError(
                    field="shipment_id",
                    message="Shipment events must have shipment_id",
                    error_code="MISSING_DOMAIN_FIELD",
                ))

        elif domain == "facility":
            # Facility events should have facility_id
            if "facility_id" not in payload and "facilityId" not in payload:
                errors.append(ValidationError(
                    field="facility_id",
                    message="Facility events must have facility_id",
                    error_code="MISSING_DOMAIN_FIELD",
                ))

        elif domain == "driver":
            # Driver events should have driver_id
            if "driver_id" not in payload and "driverId" not in payload:
                errors.append(ValidationError(
                    field="driver_id",
                    message="Driver events must have driver_id",
                    error_code="MISSING_DOMAIN_FIELD",
                ))

        elif domain == "delivery":
            # Delivery events should have delivery_id
            if "delivery_id" not in payload and "deliveryId" not in payload:
                errors.append(ValidationError(
                    field="delivery_id",
                    message="Delivery events must have delivery_id",
                    error_code="MISSING_DOMAIN_FIELD",
                ))

        return errors
