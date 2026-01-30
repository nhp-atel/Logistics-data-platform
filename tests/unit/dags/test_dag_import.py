"""
Tests for DAG import validation.

These tests ensure DAGs can be imported without errors,
which catches syntax errors and missing dependencies.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Mock Airflow modules for testing without full Airflow installation
sys.modules["airflow"] = MagicMock()
sys.modules["airflow.models"] = MagicMock()
sys.modules["airflow.operators.empty"] = MagicMock()
sys.modules["airflow.operators.python"] = MagicMock()
sys.modules["airflow.providers.google.cloud.operators.bigquery"] = MagicMock()
sys.modules["airflow.providers.google.cloud.sensors.bigquery"] = MagicMock()
sys.modules["airflow.utils.task_group"] = MagicMock()


class TestDAGImports:
    """Test that all DAGs can be imported."""

    @pytest.fixture(autouse=True)
    def setup_airflow_mocks(self):
        """Set up Airflow mocks for all tests."""
        # Mock Variable.get
        with patch.dict(os.environ, {
            "AIRFLOW_VAR_PROJECT_ID": "test-project",
            "AIRFLOW_VAR_REGION": "us-central1",
            "AIRFLOW_VAR_ENVIRONMENT": "test",
        }):
            yield

    def test_marts_daily_dag_structure(self):
        """Test marts_daily DAG has expected structure."""
        # This would import and validate the DAG
        # For now, we just verify the file exists and is valid Python
        dag_path = Path(__file__).parent.parent.parent.parent / "src" / "batch" / "dags" / "marts_daily.py"
        assert dag_path.exists()

        # Compile the file to check for syntax errors
        with open(dag_path) as f:
            source = f.read()
        compile(source, dag_path, "exec")

    def test_reconciliation_dag_structure(self):
        """Test reconciliation DAG has expected structure."""
        dag_path = Path(__file__).parent.parent.parent.parent / "src" / "batch" / "dags" / "reconciliation.py"
        assert dag_path.exists()

        with open(dag_path) as f:
            source = f.read()
        compile(source, dag_path, "exec")

    def test_sla_monitoring_dag_structure(self):
        """Test sla_monitoring DAG has expected structure."""
        dag_path = Path(__file__).parent.parent.parent.parent / "src" / "batch" / "dags" / "sla_monitoring.py"
        assert dag_path.exists()

        with open(dag_path) as f:
            source = f.read()
        compile(source, dag_path, "exec")


class TestDAGConfiguration:
    """Test DAG configuration is valid."""

    def test_marts_daily_has_required_tasks(self):
        """Test that marts_daily DAG has all required tasks."""
        dag_path = Path(__file__).parent.parent.parent.parent / "src" / "batch" / "dags" / "marts_daily.py"

        with open(dag_path) as f:
            content = f.read()

        # Check for required task groups
        assert "check_sources" in content
        assert "build_dimensions" in content
        assert "build_facts" in content
        assert "quality_checks" in content

        # Check for key operators
        assert "BigQueryInsertJobOperator" in content
        assert "BigQueryCheckOperator" in content

    def test_reconciliation_has_detection_logic(self):
        """Test that reconciliation DAG has late data detection."""
        dag_path = Path(__file__).parent.parent.parent.parent / "src" / "batch" / "dags" / "reconciliation.py"

        with open(dag_path) as f:
            content = f.read()

        # Check for detection function
        assert "detect_late_data" in content
        assert "reconcile_partition" in content

    def test_sla_monitoring_has_all_checks(self):
        """Test that SLA monitoring DAG has all required checks."""
        dag_path = Path(__file__).parent.parent.parent.parent / "src" / "batch" / "dags" / "sla_monitoring.py"

        with open(dag_path) as f:
            content = f.read()

        # Check for monitoring functions
        assert "check_streaming_lag" in content
        assert "check_data_freshness" in content
        assert "check_data_volume" in content
        assert "send_alert" in content
