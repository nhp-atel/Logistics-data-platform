"""
Unit tests for the Analytics API.
"""

import os
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

# Set environment before imports
os.environ["ENVIRONMENT"] = "test"
os.environ["GCP_PROJECT"] = "test-project"


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_healthy(self):
        """Test health endpoint returns healthy status."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        # Mock the BigQuery client
        with patch("src.api.main.bq_client", MagicMock()):
            client = TestClient(app)
            response = client.get("/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["environment"] == "test"
            assert "timestamp" in data


class TestRootEndpoint:
    """Tests for root endpoint."""

    def test_root_returns_api_info(self):
        """Test root endpoint returns API info."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with patch("src.api.main.bq_client", MagicMock()):
            client = TestClient(app)
            response = client.get("/")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Logistics Analytics API"
            assert data["version"] == "1.0.0"


class TestShipmentEndpoints:
    """Tests for shipment endpoints."""

    def test_list_shipments_returns_empty(self):
        """Test listing shipments returns empty list."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with patch("src.api.main.bq_client", MagicMock()):
            client = TestClient(app)
            response = client.get("/api/v1/shipments/")

            assert response.status_code == 200
            data = response.json()
            assert "shipments" in data
            assert "total_count" in data
            assert "page" in data

    def test_get_shipment_not_found(self):
        """Test getting non-existent shipment returns 404."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with patch("src.api.main.bq_client", MagicMock()):
            client = TestClient(app)
            response = client.get("/api/v1/shipments/non-existent")

            assert response.status_code == 404


class TestFacilityEndpoints:
    """Tests for facility endpoints."""

    def test_list_facilities_returns_empty(self):
        """Test listing facilities returns empty list."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with patch("src.api.main.bq_client", MagicMock()):
            client = TestClient(app)
            response = client.get("/api/v1/facilities/")

            assert response.status_code == 200
            data = response.json()
            assert "facilities" in data
            assert "total_count" in data


class TestMetricsEndpoints:
    """Tests for metrics endpoints."""

    def test_platform_daily_metrics_requires_dates(self):
        """Test platform metrics endpoint requires date parameters."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        with patch("src.api.main.bq_client", MagicMock()):
            client = TestClient(app)

            # Without required parameters should fail
            response = client.get("/api/v1/metrics/platform/daily")
            assert response.status_code == 422  # Validation error

            # With parameters should succeed
            response = client.get(
                "/api/v1/metrics/platform/daily",
                params={"date_from": "2024-01-01", "date_to": "2024-01-15"},
            )
            assert response.status_code == 200


class TestBigQueryService:
    """Tests for BigQuery service."""

    def test_execute_query(self):
        """Test query execution."""
        from src.api.services.bigquery_service import BigQueryService

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([
            {"id": "1", "value": "test"},
        ])
        mock_client.query.return_value.result.return_value = mock_result

        service = BigQueryService(mock_client, "test-project", "test_dataset")
        results = service.execute_query("SELECT * FROM table")

        assert len(results) == 1
        mock_client.query.assert_called_once()

    def test_execute_query_with_parameters(self):
        """Test query execution with parameters."""
        from src.api.services.bigquery_service import BigQueryService

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_client.query.return_value.result.return_value = mock_result

        service = BigQueryService(mock_client, "test-project", "test_dataset")
        results = service.execute_query(
            "SELECT * FROM table WHERE id = @id",
            parameters={"id": "123"},
        )

        mock_client.query.assert_called_once()
        call_args = mock_client.query.call_args
        assert call_args[1]["job_config"] is not None

    def test_infer_param_types(self):
        """Test parameter type inference."""
        from src.api.services.bigquery_service import BigQueryService

        service = BigQueryService(MagicMock(), "project", "dataset")

        assert service._infer_param_type("string") == "STRING"
        assert service._infer_param_type(123) == "INT64"
        assert service._infer_param_type(1.5) == "FLOAT64"
        assert service._infer_param_type(True) == "BOOL"
        assert service._infer_param_type(date.today()) == "DATE"
        assert service._infer_param_type(datetime.now()) == "TIMESTAMP"
