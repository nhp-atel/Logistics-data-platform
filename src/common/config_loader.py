"""
Configuration loader supporting YAML files and environment variables.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class GCPConfig(BaseModel):
    """GCP-specific configuration."""

    project_id: str = Field(default="", description="GCP project ID")
    region: str = Field(default="us-central1", description="GCP region")
    zone: str = Field(default="us-central1-b", description="GCP zone")


class PubSubConfig(BaseModel):
    """Pub/Sub configuration."""

    shipment_events_subscription: str = Field(default="", description="Shipment events subscription")
    facility_events_subscription: str = Field(default="", description="Facility events subscription")
    driver_events_subscription: str = Field(default="", description="Driver events subscription")
    delivery_events_subscription: str = Field(default="", description="Delivery events subscription")
    unified_subscription: str = Field(default="", description="Unified events subscription")
    dlq_topic: str = Field(default="", description="Dead letter queue topic")


class KafkaConfig(BaseModel):
    """Kafka configuration."""

    bootstrap_servers: str = Field(default="", description="Kafka bootstrap servers")
    security_protocol: str = Field(default="SASL_SSL", description="Security protocol")
    sasl_mechanism: str = Field(default="PLAIN", description="SASL mechanism")
    consumer_group: str = Field(default="", description="Consumer group ID")
    auto_offset_reset: str = Field(default="earliest", description="Auto offset reset policy")


class BigQueryConfig(BaseModel):
    """BigQuery configuration."""

    raw_dataset: str = Field(default="", description="Raw/bronze dataset")
    clean_dataset: str = Field(default="", description="Clean/silver dataset")
    curated_dataset: str = Field(default="", description="Curated/gold dataset")
    features_dataset: str = Field(default="", description="ML features dataset")
    staging_dataset: str = Field(default="", description="Staging dataset")


class GCSConfig(BaseModel):
    """GCS configuration."""

    raw_bucket: str = Field(default="", description="Raw data bucket")
    temp_bucket: str = Field(default="", description="Dataflow temp bucket")
    staging_bucket: str = Field(default="", description="Dataflow staging bucket")
    quarantine_bucket: str = Field(default="", description="Quarantine bucket")


class DataflowConfig(BaseModel):
    """Dataflow configuration."""

    job_name: str = Field(default="logistics-streaming-pipeline", description="Dataflow job name")
    max_workers: int = Field(default=10, description="Maximum number of workers")
    num_workers: int = Field(default=1, description="Initial number of workers")
    machine_type: str = Field(default="n1-standard-4", description="Worker machine type")
    disk_size_gb: int = Field(default=50, description="Worker disk size in GB")
    enable_streaming_engine: bool = Field(default=True, description="Enable Streaming Engine")
    window_duration_seconds: int = Field(default=300, description="Tumbling window duration")
    allowed_lateness_seconds: int = Field(default=86400, description="Allowed lateness (24h)")


class StreamingConfig(BaseModel):
    """Streaming pipeline configuration."""

    window_duration_seconds: int = Field(default=300, description="Tumbling window duration")
    allowed_lateness_seconds: int = Field(default=86400, description="Allowed lateness")
    dedupe_window_hours: int = Field(default=24, description="Deduplication window in hours")
    early_trigger_seconds: int = Field(default=60, description="Early trigger interval")
    enable_pii_masking: bool = Field(default=True, description="Enable PII masking")


class Config(BaseSettings):
    """Main configuration class."""

    environment: str = Field(default="dev", description="Environment name")
    log_level: str = Field(default="INFO", description="Logging level")

    gcp: GCPConfig = Field(default_factory=GCPConfig)
    pubsub: PubSubConfig = Field(default_factory=PubSubConfig)
    kafka: KafkaConfig = Field(default_factory=KafkaConfig)
    bigquery: BigQueryConfig = Field(default_factory=BigQueryConfig)
    gcs: GCSConfig = Field(default_factory=GCSConfig)
    dataflow: DataflowConfig = Field(default_factory=DataflowConfig)
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)

    class Config:
        env_prefix = ""
        env_nested_delimiter = "__"


class ConfigLoader:
    """Loads configuration from YAML files with environment overrides."""

    def __init__(self, config_dir: str | Path | None = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_dir = Path(config_dir)
        self._config: Config | None = None

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Load a YAML file."""
        filepath = self.config_dir / filename
        if not filepath.exists():
            return {}
        with open(filepath) as f:
            return yaml.safe_load(f) or {}

    def _substitute_env_vars(self, config: dict) -> dict:
        """Substitute environment variables in config values."""
        result = {}
        for key, value in config.items():
            if isinstance(value, dict):
                result[key] = self._substitute_env_vars(value)
            elif isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                default = None
                if ":-" in env_var:
                    env_var, default = env_var.split(":-", 1)
                result[key] = os.environ.get(env_var, default)
            else:
                result[key] = value
        return result

    def load(self, environment: str | None = None) -> Config:
        """Load configuration for the specified environment."""
        if environment is None:
            environment = os.environ.get("ENVIRONMENT", "dev")

        # Load base config
        base_config = self._load_yaml("base.yaml")

        # Load environment-specific config
        env_config = self._load_yaml(f"{environment}.yaml")

        # Merge configs
        merged = self._deep_merge(base_config, env_config)

        # Substitute environment variables
        merged = self._substitute_env_vars(merged)

        # Add environment to config
        merged["environment"] = environment

        # Create Config instance
        self._config = Config(**merged)
        return self._config

    @property
    def config(self) -> Config:
        """Get the loaded configuration."""
        if self._config is None:
            return self.load()
        return self._config


# Global config loader instance
_config_loader: ConfigLoader | None = None


def get_config(environment: str | None = None, config_dir: str | Path | None = None) -> Config:
    """Get the global configuration instance."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_dir)
    return _config_loader.load(environment)
