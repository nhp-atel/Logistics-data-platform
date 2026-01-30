"""
PII tokenization and masking transform.
"""

import hashlib
import hmac
import re
from typing import Any, Iterator

import apache_beam as beam
from google.cloud import secretmanager

from src.common.schemas import EventEnvelope
from src.common.logging_utils import get_logger
from src.common.metrics import beam_metrics

logger = get_logger(__name__)


# Default PII field patterns
DEFAULT_PII_FIELDS = {
    # Exact field names
    "first_name",
    "last_name",
    "full_name",
    "name",
    "email",
    "phone",
    "phone_number",
    "address",
    "street",
    "ssn",
    "social_security_number",
    "license_number",
    "driver_license",
    "credit_card",
    "bank_account",
    "signed_by",
}

# Regex patterns for PII field names
PII_FIELD_PATTERNS = [
    re.compile(r".*_name$", re.IGNORECASE),
    re.compile(r".*email.*", re.IGNORECASE),
    re.compile(r".*phone.*", re.IGNORECASE),
    re.compile(r".*address.*", re.IGNORECASE),
    re.compile(r".*ssn.*", re.IGNORECASE),
    re.compile(r".*license.*", re.IGNORECASE),
]


class PIITokenizer:
    """
    Tokenizes PII values using HMAC for consistent, one-way hashing.
    """

    def __init__(self, hmac_key: bytes, salt: str = ""):
        """
        Initialize the tokenizer.

        Args:
            hmac_key: Secret key for HMAC
            salt: Additional salt for hashing
        """
        self.hmac_key = hmac_key
        self.salt = salt

    def tokenize(self, value: str) -> str:
        """
        Tokenize a PII value.

        Args:
            value: PII value to tokenize

        Returns:
            Tokenized value (hex string)
        """
        if not value:
            return ""

        # Combine value with salt
        salted_value = f"{self.salt}:{value}".encode("utf-8")

        # Create HMAC
        token = hmac.new(self.hmac_key, salted_value, hashlib.sha256).hexdigest()

        # Return truncated token (first 16 chars for readability)
        return f"tok_{token[:16]}"


class PIIMasker:
    """
    Masks PII values by replacing with asterisks while preserving structure.
    """

    def mask_email(self, email: str) -> str:
        """Mask email address."""
        if not email or "@" not in email:
            return "***@***.***"

        local, domain = email.rsplit("@", 1)
        masked_local = local[0] + "***" if local else "***"
        domain_parts = domain.split(".")
        masked_domain = ".".join(
            part[0] + "*" * (len(part) - 1) if len(part) > 1 else "*"
            for part in domain_parts
        )
        return f"{masked_local}@{masked_domain}"

    def mask_phone(self, phone: str) -> str:
        """Mask phone number, keeping last 4 digits."""
        if not phone:
            return "***-***-****"

        digits = re.sub(r"\D", "", phone)
        if len(digits) >= 4:
            return f"***-***-{digits[-4:]}"
        return "***-***-****"

    def mask_name(self, name: str) -> str:
        """Mask name, keeping first initial."""
        if not name:
            return "***"

        parts = name.split()
        return " ".join(
            part[0] + "*" * (len(part) - 1) if len(part) > 0 else "*"
            for part in parts
        )

    def mask_address(self, address: str) -> str:
        """Mask address, keeping rough structure."""
        if not address:
            return "*** **** ***"

        parts = address.split()
        return " ".join(
            part[0] + "*" * (len(part) - 1) if len(part) > 1 else "*"
            for part in parts[:3]
        ) + " ***"

    def mask_generic(self, value: str) -> str:
        """Generic masking for unknown PII types."""
        if not value:
            return "***"

        if len(value) <= 3:
            return "*" * len(value)

        return value[0] + "*" * (len(value) - 2) + value[-1]


class MaskPII(beam.DoFn):
    """
    DoFn that masks PII fields in event payloads.
    """

    def __init__(
        self,
        pii_fields: set[str] | None = None,
        use_tokenization: bool = False,
        secret_id: str | None = None,
        project_id: str | None = None,
    ):
        """
        Initialize the PII masking transform.

        Args:
            pii_fields: Set of field names to treat as PII
            use_tokenization: Use tokenization instead of masking
            secret_id: Secret Manager secret ID for HMAC key
            project_id: GCP project ID for Secret Manager
        """
        super().__init__()
        self.pii_fields = pii_fields or DEFAULT_PII_FIELDS
        self.use_tokenization = use_tokenization
        self.secret_id = secret_id
        self.project_id = project_id
        self._tokenizer: PIITokenizer | None = None
        self._masker: PIIMasker | None = None
        self._counter_fields_masked = None

    def setup(self):
        """Initialize the tokenizer/masker."""
        self._masker = PIIMasker()
        self._counter_fields_masked = beam_metrics.get_counter("pii_fields_masked")

        if self.use_tokenization and self.secret_id and self.project_id:
            try:
                client = secretmanager.SecretManagerServiceClient()
                name = f"projects/{self.project_id}/secrets/{self.secret_id}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                secret_data = response.payload.data.decode("utf-8")

                import json
                config = json.loads(secret_data)
                hmac_key = config.get("hmac_key", "").encode("utf-8")
                salt = config.get("salt", "")
                self._tokenizer = PIITokenizer(hmac_key, salt)
            except Exception as e:
                logger.warning(f"Failed to load tokenization key: {e}, falling back to masking")
                self._tokenizer = None

    def process(self, event: EventEnvelope) -> Iterator[EventEnvelope]:
        """
        Process an event and mask PII fields.

        Args:
            event: Event to process

        Yields:
            Event with PII fields masked
        """
        masked_payload = self._mask_dict(event.payload)

        masked_event = EventEnvelope(
            event_id=event.event_id,
            event_type=event.event_type,
            event_version=event.event_version,
            event_time=event.event_time,
            ingest_time=event.ingest_time,
            source_system=event.source_system,
            payload=masked_payload,
            trace_id=event.trace_id,
        )

        yield masked_event

    def _mask_dict(self, data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        """Recursively mask PII fields in a dictionary."""
        result = {}

        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                result[key] = self._mask_dict(value, full_key)
            elif isinstance(value, list):
                result[key] = [
                    self._mask_dict(item, full_key) if isinstance(item, dict) else item
                    for item in value
                ]
            elif self._is_pii_field(key):
                result[key] = self._mask_value(key, value)
                self._counter_fields_masked.inc()
            else:
                result[key] = value

        return result

    def _is_pii_field(self, field_name: str) -> bool:
        """Check if a field name indicates PII."""
        lower_name = field_name.lower()

        # Check exact matches
        if lower_name in self.pii_fields:
            return True

        # Check patterns
        for pattern in PII_FIELD_PATTERNS:
            if pattern.match(lower_name):
                return True

        return False

    def _mask_value(self, field_name: str, value: Any) -> Any:
        """Mask a PII value based on field name."""
        if value is None:
            return None

        str_value = str(value)

        # Use tokenization if available
        if self._tokenizer:
            return self._tokenizer.tokenize(str_value)

        # Otherwise use type-specific masking
        lower_name = field_name.lower()

        if "email" in lower_name:
            return self._masker.mask_email(str_value)
        elif "phone" in lower_name:
            return self._masker.mask_phone(str_value)
        elif "name" in lower_name:
            return self._masker.mask_name(str_value)
        elif "address" in lower_name or "street" in lower_name:
            return self._masker.mask_address(str_value)
        else:
            return self._masker.mask_generic(str_value)
