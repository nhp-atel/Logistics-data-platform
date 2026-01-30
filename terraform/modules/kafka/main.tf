/**
 * Kafka Module
 * Configuration for Confluent Cloud managed Kafka or self-managed on GKE.
 * This module provides the configuration structure - actual cluster creation
 * may use Confluent Terraform provider or GKE resources.
 */

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "dataflow_worker_email" {
  description = "Dataflow worker service account email"
  type        = string
}

variable "kafka_bootstrap_servers" {
  description = "Kafka bootstrap servers (if using external Kafka)"
  type        = string
  default     = ""
}

variable "use_confluent_cloud" {
  description = "Use Confluent Cloud instead of self-managed Kafka"
  type        = bool
  default     = true
}

locals {
  name_prefix = var.environment

  # Kafka topic configuration
  kafka_topics = {
    "shipment-events" = {
      partitions        = var.environment == "prod" ? 12 : 3
      replication_factor = var.environment == "prod" ? 3 : 1
      retention_ms      = 604800000 # 7 days
      cleanup_policy    = "delete"
    }
    "facility-events" = {
      partitions        = var.environment == "prod" ? 6 : 2
      replication_factor = var.environment == "prod" ? 3 : 1
      retention_ms      = 604800000
      cleanup_policy    = "delete"
    }
    "driver-events" = {
      partitions        = var.environment == "prod" ? 6 : 2
      replication_factor = var.environment == "prod" ? 3 : 1
      retention_ms      = 604800000
      cleanup_policy    = "delete"
    }
    "delivery-events" = {
      partitions        = var.environment == "prod" ? 12 : 3
      replication_factor = var.environment == "prod" ? 3 : 1
      retention_ms      = 604800000
      cleanup_policy    = "delete"
    }
    "dlq-events" = {
      partitions        = var.environment == "prod" ? 6 : 2
      replication_factor = var.environment == "prod" ? 3 : 1
      retention_ms      = 2592000000 # 30 days for DLQ
      cleanup_policy    = "delete"
    }
  }
}

# ============================================================================
# Secret Manager - Kafka Credentials
# ============================================================================

resource "google_secret_manager_secret" "kafka_credentials" {
  secret_id = "${local.name_prefix}-kafka-credentials"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "kafka-auth"
  }
}

# Placeholder secret version - should be updated with actual credentials
resource "google_secret_manager_secret_version" "kafka_credentials" {
  secret = google_secret_manager_secret.kafka_credentials.id

  secret_data = jsonencode({
    bootstrap_servers = var.kafka_bootstrap_servers
    api_key           = "PLACEHOLDER_API_KEY"
    api_secret        = "PLACEHOLDER_API_SECRET"
    security_protocol = "SASL_SSL"
    sasl_mechanism    = "PLAIN"
  })

  lifecycle {
    ignore_changes = [secret_data] # Don't overwrite if manually updated
  }
}

resource "google_secret_manager_secret_iam_member" "kafka_accessor" {
  secret_id = google_secret_manager_secret.kafka_credentials.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.dataflow_worker_email}"
  project   = var.project_id
}

# ============================================================================
# Kafka Configuration Storage
# ============================================================================

resource "google_storage_bucket" "kafka_config" {
  name          = "${var.project_id}-${local.name_prefix}-kafka-config"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  labels = {
    environment = var.environment
    purpose     = "kafka-config"
  }
}

# Store topic configurations
resource "google_storage_bucket_object" "topic_config" {
  name   = "topics/config.json"
  bucket = google_storage_bucket.kafka_config.name

  content = jsonencode({
    topics = local.kafka_topics
    consumer_groups = {
      "dataflow-${var.environment}" = {
        topics = keys(local.kafka_topics)
        reset_policy = "earliest"
      }
    }
  })

  content_type = "application/json"
}

# ============================================================================
# Schema Registry Configuration (if using Confluent)
# ============================================================================

resource "google_secret_manager_secret" "schema_registry_credentials" {
  count = var.use_confluent_cloud ? 1 : 0

  secret_id = "${local.name_prefix}-schema-registry-credentials"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "schema-registry"
  }
}

resource "google_secret_manager_secret_version" "schema_registry_credentials" {
  count = var.use_confluent_cloud ? 1 : 0

  secret = google_secret_manager_secret.schema_registry_credentials[0].id

  secret_data = jsonencode({
    url        = "PLACEHOLDER_SCHEMA_REGISTRY_URL"
    api_key    = "PLACEHOLDER_SR_API_KEY"
    api_secret = "PLACEHOLDER_SR_API_SECRET"
  })

  lifecycle {
    ignore_changes = [secret_data]
  }
}

resource "google_secret_manager_secret_iam_member" "schema_registry_accessor" {
  count = var.use_confluent_cloud ? 1 : 0

  secret_id = google_secret_manager_secret.schema_registry_credentials[0].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.dataflow_worker_email}"
  project   = var.project_id
}

# ============================================================================
# Outputs
# ============================================================================

output "kafka_credentials_secret_id" {
  description = "Secret Manager secret ID for Kafka credentials"
  value       = google_secret_manager_secret.kafka_credentials.secret_id
}

output "kafka_config_bucket" {
  description = "GCS bucket for Kafka configuration"
  value       = google_storage_bucket.kafka_config.name
}

output "kafka_topics" {
  description = "Kafka topic configurations"
  value       = local.kafka_topics
}

output "schema_registry_secret_id" {
  description = "Secret Manager secret ID for Schema Registry credentials"
  value       = var.use_confluent_cloud ? google_secret_manager_secret.schema_registry_credentials[0].secret_id : null
}
