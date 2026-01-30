/**
 * Dataflow Module
 * Creates Flex Template configuration and related resources for streaming pipelines.
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

variable "network_self_link" {
  description = "VPC network self link"
  type        = string
}

variable "subnetwork_self_link" {
  description = "Subnetwork self link"
  type        = string
}

variable "dataflow_worker_email" {
  description = "Dataflow worker service account email"
  type        = string
}

variable "temp_bucket_name" {
  description = "Dataflow temp bucket name"
  type        = string
}

variable "staging_bucket_name" {
  description = "Dataflow staging bucket name"
  type        = string
}

variable "max_workers" {
  description = "Maximum number of workers"
  type        = number
  default     = 10
}

variable "machine_type" {
  description = "Worker machine type"
  type        = string
  default     = "n1-standard-4"
}

locals {
  name_prefix = var.environment

  # Environment-specific configurations
  config = {
    dev = {
      max_workers  = 3
      num_workers  = 1
      machine_type = "n1-standard-2"
      disk_size_gb = 30
    }
    prod = {
      max_workers  = var.max_workers
      num_workers  = 3
      machine_type = var.machine_type
      disk_size_gb = 100
    }
  }

  env_config = local.config[var.environment]
}

# ============================================================================
# Flex Template Storage
# ============================================================================

resource "google_storage_bucket" "flex_templates" {
  name          = "${var.project_id}-${local.name_prefix}-flex-templates"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  labels = {
    environment = var.environment
    purpose     = "flex-templates"
  }
}

resource "google_storage_bucket_iam_member" "flex_templates_viewer" {
  bucket = google_storage_bucket.flex_templates.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.dataflow_worker_email}"
}

# ============================================================================
# Dataflow Flex Template Metadata (stored as JSON in GCS)
# ============================================================================

resource "google_storage_bucket_object" "logistics_pipeline_metadata" {
  name   = "templates/logistics-streaming-pipeline/metadata.json"
  bucket = google_storage_bucket.flex_templates.name

  content = jsonencode({
    name        = "logistics-streaming-pipeline"
    description = "Streaming ETL pipeline for logistics events"
    parameters = [
      {
        name        = "input_subscription"
        label       = "Pub/Sub Subscription"
        helpText    = "The Pub/Sub subscription to read from"
        isOptional  = false
        regexes     = ["projects/[^/]+/subscriptions/[^/]+"]
      },
      {
        name        = "output_table"
        label       = "BigQuery Output Table"
        helpText    = "BigQuery table for clean events (project:dataset.table)"
        isOptional  = false
      },
      {
        name        = "raw_bucket"
        label       = "Raw Data Bucket"
        helpText    = "GCS bucket for raw event archive"
        isOptional  = false
      },
      {
        name        = "dlq_topic"
        label       = "Dead Letter Queue Topic"
        helpText    = "Pub/Sub topic for failed messages"
        isOptional  = false
      },
      {
        name        = "enable_streaming_engine"
        label       = "Enable Streaming Engine"
        helpText    = "Use Dataflow Streaming Engine"
        isOptional  = true
      },
      {
        name        = "window_duration"
        label       = "Window Duration (seconds)"
        helpText    = "Tumbling window duration in seconds"
        isOptional  = true
      }
    ]
  })

  content_type = "application/json"
}

# ============================================================================
# Dataflow Job Parameters (for reference/documentation)
# ============================================================================

locals {
  default_pipeline_options = {
    project                = var.project_id
    region                 = var.region
    temp_location          = "gs://${var.temp_bucket_name}/temp"
    staging_location       = "gs://${var.staging_bucket_name}/staging"
    service_account_email  = var.dataflow_worker_email
    network                = var.network_self_link
    subnetwork             = var.subnetwork_self_link
    use_public_ips         = false
    enable_streaming_engine = true
    max_num_workers        = local.env_config.max_workers
    num_workers            = local.env_config.num_workers
    machine_type           = local.env_config.machine_type
    disk_size_gb           = local.env_config.disk_size_gb
    worker_zone            = "${var.region}-b"
    experiments = [
      "enable_recommendations",
      "enable_google_cloud_profiler"
    ]
    labels = {
      environment = var.environment
      team        = "data-engineering"
      pipeline    = "logistics-streaming"
    }
  }
}

# Store default options as a reference file
resource "google_storage_bucket_object" "default_options" {
  name   = "config/default-pipeline-options-${var.environment}.json"
  bucket = google_storage_bucket.flex_templates.name

  content      = jsonencode(local.default_pipeline_options)
  content_type = "application/json"
}

# ============================================================================
# Artifact Registry for Container Images
# ============================================================================

resource "google_artifact_registry_repository" "dataflow" {
  location      = var.region
  repository_id = "${local.name_prefix}-dataflow"
  description   = "Container images for Dataflow Flex Templates"
  format        = "DOCKER"
  project       = var.project_id

  labels = {
    environment = var.environment
  }
}

resource "google_artifact_registry_repository_iam_member" "dataflow_reader" {
  location   = google_artifact_registry_repository.dataflow.location
  repository = google_artifact_registry_repository.dataflow.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${var.dataflow_worker_email}"
  project    = var.project_id
}

# ============================================================================
# Outputs
# ============================================================================

output "flex_templates_bucket" {
  description = "Flex templates bucket name"
  value       = google_storage_bucket.flex_templates.name
}

output "flex_templates_bucket_url" {
  description = "Flex templates bucket URL"
  value       = google_storage_bucket.flex_templates.url
}

output "artifact_registry_repository" {
  description = "Artifact Registry repository name"
  value       = google_artifact_registry_repository.dataflow.name
}

output "artifact_registry_url" {
  description = "Artifact Registry URL"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.dataflow.name}"
}

output "default_pipeline_options" {
  description = "Default pipeline options"
  value       = local.default_pipeline_options
}
