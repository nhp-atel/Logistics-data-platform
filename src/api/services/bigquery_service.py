"""
BigQuery service for executing queries.
"""

from typing import Any

from google.cloud import bigquery

from src.common.logging_utils import get_logger

logger = get_logger(__name__)


class BigQueryService:
    """Service for interacting with BigQuery."""

    def __init__(self, client: bigquery.Client, project_id: str, dataset: str):
        self.client = client
        self.project_id = project_id
        self.dataset = dataset

    def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Execute a query and return results as list of dicts.

        Args:
            query: SQL query to execute
            parameters: Query parameters

        Returns:
            List of result rows as dictionaries
        """
        job_config = bigquery.QueryJobConfig()

        if parameters:
            query_params = []
            for name, value in parameters.items():
                param_type = self._infer_param_type(value)
                query_params.append(
                    bigquery.ScalarQueryParameter(name, param_type, value)
                )
            job_config.query_parameters = query_params

        try:
            result = self.client.query(query, job_config=job_config).result()
            return [dict(row) for row in result]
        except Exception as e:
            logger.error(f"Query execution failed: {e}", query=query[:100])
            raise

    def _infer_param_type(self, value: Any) -> str:
        """Infer BigQuery parameter type from Python value."""
        from datetime import date, datetime

        if isinstance(value, bool):
            return "BOOL"
        if isinstance(value, int):
            return "INT64"
        if isinstance(value, float):
            return "FLOAT64"
        if isinstance(value, datetime):
            return "TIMESTAMP"
        if isinstance(value, date):
            return "DATE"
        return "STRING"

    def get_table_ref(self, table_name: str) -> str:
        """Get fully qualified table reference."""
        return f"`{self.project_id}.{self.dataset}.{table_name}`"
