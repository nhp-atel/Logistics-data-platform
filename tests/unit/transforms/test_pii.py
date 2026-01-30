"""
Unit tests for the PII masking transform.
"""

from datetime import datetime, timezone

import pytest

from src.common.schemas import EventEnvelope
from src.streaming.transforms.pii import MaskPII, PIIMasker, PIITokenizer


class TestPIIMasker:
    """Tests for PIIMasker utility class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.masker = PIIMasker()

    def test_mask_email(self):
        """Test email masking."""
        test_cases = [
            ("john.doe@example.com", "j***@e******.c**"),
            ("a@b.co", "a***@b.c*"),
            ("test@test.org", "t***@t***.o**"),
        ]

        for email, expected_pattern in test_cases:
            result = self.masker.mask_email(email)
            # Should start with first char and contain @
            assert "@" in result
            assert result[0] == email[0]

    def test_mask_email_empty(self):
        """Test masking empty email."""
        result = self.masker.mask_email("")
        assert result == "***@***.***"

    def test_mask_email_invalid(self):
        """Test masking invalid email."""
        result = self.masker.mask_email("not-an-email")
        assert result == "***@***.***"

    def test_mask_phone(self):
        """Test phone number masking."""
        test_cases = [
            ("555-123-4567", "***-***-4567"),
            ("(555) 123-4567", "***-***-4567"),
            ("+1 555 123 4567", "***-***-4567"),
            ("5551234567", "***-***-4567"),
        ]

        for phone, expected in test_cases:
            result = self.masker.mask_phone(phone)
            assert result == expected

    def test_mask_phone_short(self):
        """Test masking short phone numbers."""
        result = self.masker.mask_phone("123")
        assert "123" in result or result == "***-***-****"

    def test_mask_name(self):
        """Test name masking."""
        test_cases = [
            ("John", "J***"),
            ("John Doe", "J*** D**"),
            ("Mary Jane Watson", "M*** J*** W*****"),
        ]

        for name, expected in test_cases:
            result = self.masker.mask_name(name)
            assert result == expected

    def test_mask_name_empty(self):
        """Test masking empty name."""
        result = self.masker.mask_name("")
        assert result == "***"

    def test_mask_address(self):
        """Test address masking."""
        result = self.masker.mask_address("123 Main Street, Apt 4")
        # Should mask but keep some structure
        assert "***" in result

    def test_mask_generic(self):
        """Test generic masking."""
        test_cases = [
            ("secret123", "s*******3"),
            ("ab", "**"),
            ("abc", "a*c"),
        ]

        for value, expected in test_cases:
            result = self.masker.mask_generic(value)
            assert result == expected


class TestPIITokenizer:
    """Tests for PIITokenizer utility class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tokenizer = PIITokenizer(
            hmac_key=b"test-secret-key-32-bytes-long!!",
            salt="test-salt",
        )

    def test_tokenize_consistent(self):
        """Test that tokenization is consistent."""
        value = "john.doe@example.com"
        token1 = self.tokenizer.tokenize(value)
        token2 = self.tokenizer.tokenize(value)

        assert token1 == token2

    def test_tokenize_different_values(self):
        """Test that different values produce different tokens."""
        token1 = self.tokenizer.tokenize("value1")
        token2 = self.tokenizer.tokenize("value2")

        assert token1 != token2

    def test_tokenize_format(self):
        """Test token format."""
        token = self.tokenizer.tokenize("test-value")

        assert token.startswith("tok_")
        assert len(token) == 4 + 16  # prefix + 16 char token

    def test_tokenize_empty(self):
        """Test tokenizing empty string."""
        token = self.tokenizer.tokenize("")
        assert token == ""


class TestMaskPII:
    """Tests for MaskPII DoFn."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mask_pii = MaskPII()
        self.mask_pii.setup()

    def create_envelope(self, payload: dict) -> EventEnvelope:
        """Helper to create test envelopes."""
        return EventEnvelope(
            event_id="test-123",
            event_type="shipment.created",
            event_version="v1",
            event_time=datetime.now(timezone.utc),
            ingest_time=datetime.now(timezone.utc),
            source_system="test",
            payload=payload,
        )

    def test_masks_email_field(self):
        """Test that email fields are masked."""
        envelope = self.create_envelope({
            "shipment_id": "SHIP-001",
            "recipient_email": "john.doe@example.com",
        })

        results = list(self.mask_pii.process(envelope))

        assert len(results) == 1
        payload = results[0].payload
        assert payload["shipment_id"] == "SHIP-001"  # Not masked
        assert "@" in payload["recipient_email"]
        assert payload["recipient_email"] != "john.doe@example.com"

    def test_masks_phone_field(self):
        """Test that phone fields are masked."""
        envelope = self.create_envelope({
            "shipment_id": "SHIP-001",
            "phone_number": "555-123-4567",
        })

        results = list(self.mask_pii.process(envelope))

        assert len(results) == 1
        payload = results[0].payload
        assert payload["phone_number"] == "***-***-4567"

    def test_masks_name_fields(self):
        """Test that name fields are masked."""
        envelope = self.create_envelope({
            "shipment_id": "SHIP-001",
            "first_name": "John",
            "last_name": "Doe",
        })

        results = list(self.mask_pii.process(envelope))

        assert len(results) == 1
        payload = results[0].payload
        assert payload["first_name"] == "J***"
        assert payload["last_name"] == "D**"

    def test_masks_nested_pii(self):
        """Test that nested PII fields are masked."""
        envelope = self.create_envelope({
            "shipment_id": "SHIP-001",
            "recipient": {
                "name": "John Doe",
                "email": "john@example.com",
                "address": {
                    "street": "123 Main St",
                },
            },
        })

        results = list(self.mask_pii.process(envelope))

        assert len(results) == 1
        payload = results[0].payload
        assert payload["shipment_id"] == "SHIP-001"
        assert "@" in payload["recipient"]["email"]
        assert payload["recipient"]["email"] != "john@example.com"

    def test_preserves_non_pii_fields(self):
        """Test that non-PII fields are preserved."""
        envelope = self.create_envelope({
            "shipment_id": "SHIP-001",
            "tracking_number": "1Z999AA10123456784",
            "service_level": "ground",
            "weight_kg": 2.5,
        })

        results = list(self.mask_pii.process(envelope))

        assert len(results) == 1
        payload = results[0].payload
        assert payload["shipment_id"] == "SHIP-001"
        assert payload["tracking_number"] == "1Z999AA10123456784"
        assert payload["service_level"] == "ground"
        assert payload["weight_kg"] == 2.5

    def test_masks_signed_by_field(self):
        """Test that signed_by field is masked."""
        envelope = self.create_envelope({
            "delivery_id": "DEL-001",
            "signed_by": "Jane Smith",
        })

        results = list(self.mask_pii.process(envelope))

        assert len(results) == 1
        payload = results[0].payload
        assert payload["signed_by"] != "Jane Smith"

    def test_handles_list_in_payload(self):
        """Test handling lists containing PII."""
        envelope = self.create_envelope({
            "shipment_id": "SHIP-001",
            "contacts": [
                {"name": "John", "email": "john@example.com"},
                {"name": "Jane", "email": "jane@example.com"},
            ],
        })

        results = list(self.mask_pii.process(envelope))

        assert len(results) == 1
        payload = results[0].payload
        assert len(payload["contacts"]) == 2
        for contact in payload["contacts"]:
            assert contact["name"] != "John" and contact["name"] != "Jane"
