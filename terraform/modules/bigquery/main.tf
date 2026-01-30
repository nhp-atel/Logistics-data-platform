/**
 * BigQuery Module
 * Creates datasets, tables, and views for medallion architecture.
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

variable "composer_worker_email" {
  description = "Composer worker service account email"
  type        = string
}

variable "analytics_api_email" {
  description = "Analytics API service account email"
  type        = string
}

locals {
  name_prefix = var.environment

  # Table expiration based on environment
  table_expiration_ms = var.environment == "dev" ? 7776000000 : null # 90 days for dev, never for prod

  # Default partition expiration
  partition_expiration_days = var.environment == "dev" ? 90 : 730
}

# ============================================================================
# Bronze/Raw Dataset
# ============================================================================

resource "google_bigquery_dataset" "raw" {
  dataset_id    = "${local.name_prefix}_raw"
  project       = var.project_id
  location      = var.region
  friendly_name = "Raw Data (${var.environment})"
  description   = "Bronze layer - raw ingested events with minimal transformation"

  default_table_expiration_ms     = local.table_expiration_ms
  default_partition_expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000

  labels = {
    environment = var.environment
    layer       = "bronze"
  }
}

# ============================================================================
# Silver/Clean Dataset
# ============================================================================

resource "google_bigquery_dataset" "clean" {
  dataset_id    = "${local.name_prefix}_clean"
  project       = var.project_id
  location      = var.region
  friendly_name = "Clean Data (${var.environment})"
  description   = "Silver layer - validated, deduplicated, enriched events"

  default_table_expiration_ms     = local.table_expiration_ms
  default_partition_expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000

  labels = {
    environment = var.environment
    layer       = "silver"
  }
}

# ============================================================================
# Gold/Curated Dataset
# ============================================================================

resource "google_bigquery_dataset" "curated" {
  dataset_id    = "${local.name_prefix}_curated"
  project       = var.project_id
  location      = var.region
  friendly_name = "Curated Data (${var.environment})"
  description   = "Gold layer - dimension tables, fact tables, aggregated marts"

  default_table_expiration_ms     = local.table_expiration_ms
  default_partition_expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000

  labels = {
    environment = var.environment
    layer       = "gold"
  }
}

# ============================================================================
# ML Features Dataset
# ============================================================================

resource "google_bigquery_dataset" "features" {
  dataset_id    = "${local.name_prefix}_features"
  project       = var.project_id
  location      = var.region
  friendly_name = "ML Features (${var.environment})"
  description   = "ML feature tables with point-in-time correctness"

  default_table_expiration_ms     = local.table_expiration_ms
  default_partition_expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000

  labels = {
    environment = var.environment
    layer       = "features"
  }
}

# ============================================================================
# Staging Dataset (for intermediate transformations)
# ============================================================================

resource "google_bigquery_dataset" "staging" {
  dataset_id    = "${local.name_prefix}_staging"
  project       = var.project_id
  location      = var.region
  friendly_name = "Staging Data (${var.environment})"
  description   = "Staging area for intermediate transformations"

  default_table_expiration_ms = 86400000 # 24 hours

  labels = {
    environment = var.environment
    layer       = "staging"
  }
}

# ============================================================================
# IAM Bindings - Raw Dataset
# ============================================================================

resource "google_bigquery_dataset_iam_member" "raw_dataflow_editor" {
  dataset_id = google_bigquery_dataset.raw.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.dataflow_worker_email}"
}

# ============================================================================
# IAM Bindings - Clean Dataset
# ============================================================================

resource "google_bigquery_dataset_iam_member" "clean_dataflow_editor" {
  dataset_id = google_bigquery_dataset.clean.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.dataflow_worker_email}"
}

resource "google_bigquery_dataset_iam_member" "clean_composer_viewer" {
  dataset_id = google_bigquery_dataset.clean.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.composer_worker_email}"
}

# ============================================================================
# IAM Bindings - Curated Dataset
# ============================================================================

resource "google_bigquery_dataset_iam_member" "curated_composer_editor" {
  dataset_id = google_bigquery_dataset.curated.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.composer_worker_email}"
}

resource "google_bigquery_dataset_iam_member" "curated_analytics_viewer" {
  dataset_id = google_bigquery_dataset.curated.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.analytics_api_email}"
}

# ============================================================================
# IAM Bindings - Features Dataset
# ============================================================================

resource "google_bigquery_dataset_iam_member" "features_composer_editor" {
  dataset_id = google_bigquery_dataset.features.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.composer_worker_email}"
}

resource "google_bigquery_dataset_iam_member" "features_analytics_viewer" {
  dataset_id = google_bigquery_dataset.features.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${var.analytics_api_email}"
}

# ============================================================================
# IAM Bindings - Staging Dataset
# ============================================================================

resource "google_bigquery_dataset_iam_member" "staging_dataflow_editor" {
  dataset_id = google_bigquery_dataset.staging.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.dataflow_worker_email}"
}

resource "google_bigquery_dataset_iam_member" "staging_composer_editor" {
  dataset_id = google_bigquery_dataset.staging.dataset_id
  project    = var.project_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${var.composer_worker_email}"
}

# ============================================================================
# Silver Layer Tables
# ============================================================================

resource "google_bigquery_table" "shipment_events" {
  dataset_id          = google_bigquery_dataset.clean.dataset_id
  table_id            = "shipment_events"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  time_partitioning {
    type          = "DAY"
    field         = "event_time"
    expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000
  }

  clustering = ["shipment_id", "event_type"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED", description = "Unique event identifier (UUID)" },
    { name = "event_type", type = "STRING", mode = "REQUIRED", description = "Event type (e.g., shipment.created)" },
    { name = "event_version", type = "STRING", mode = "REQUIRED", description = "Schema version (e.g., v1, v2)" },
    { name = "event_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Business event time" },
    { name = "ingest_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Pipeline ingestion time" },
    { name = "trace_id", type = "STRING", mode = "NULLABLE", description = "Distributed tracing ID" },
    { name = "source_system", type = "STRING", mode = "NULLABLE", description = "Origin system identifier" },
    { name = "shipment_id", type = "STRING", mode = "NULLABLE", description = "Shipment identifier" },
    { name = "facility_id", type = "STRING", mode = "NULLABLE", description = "Facility identifier" },
    { name = "carrier_id", type = "STRING", mode = "NULLABLE", description = "Carrier identifier" },
    { name = "payload", type = "JSON", mode = "NULLABLE", description = "Event-specific payload" },
    { name = "dedupe_key", type = "STRING", mode = "NULLABLE", description = "Deduplication key" },
  ])

  labels = {
    environment = var.environment
    layer       = "silver"
    domain      = "shipment"
  }
}

resource "google_bigquery_table" "facility_events" {
  dataset_id          = google_bigquery_dataset.clean.dataset_id
  table_id            = "facility_events"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  time_partitioning {
    type          = "DAY"
    field         = "event_time"
    expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000
  }

  clustering = ["facility_id", "event_type"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED", description = "Unique event identifier" },
    { name = "event_type", type = "STRING", mode = "REQUIRED", description = "Event type" },
    { name = "event_version", type = "STRING", mode = "REQUIRED", description = "Schema version" },
    { name = "event_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Business event time" },
    { name = "ingest_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Pipeline ingestion time" },
    { name = "trace_id", type = "STRING", mode = "NULLABLE", description = "Distributed tracing ID" },
    { name = "source_system", type = "STRING", mode = "NULLABLE", description = "Origin system" },
    { name = "facility_id", type = "STRING", mode = "NULLABLE", description = "Facility identifier" },
    { name = "payload", type = "JSON", mode = "NULLABLE", description = "Event payload" },
  ])

  labels = {
    environment = var.environment
    layer       = "silver"
    domain      = "facility"
  }
}

resource "google_bigquery_table" "driver_events" {
  dataset_id          = google_bigquery_dataset.clean.dataset_id
  table_id            = "driver_events"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  time_partitioning {
    type          = "DAY"
    field         = "event_time"
    expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000
  }

  clustering = ["driver_id", "event_type"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED", description = "Unique event identifier" },
    { name = "event_type", type = "STRING", mode = "REQUIRED", description = "Event type" },
    { name = "event_version", type = "STRING", mode = "REQUIRED", description = "Schema version" },
    { name = "event_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Business event time" },
    { name = "ingest_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Pipeline ingestion time" },
    { name = "trace_id", type = "STRING", mode = "NULLABLE", description = "Distributed tracing ID" },
    { name = "source_system", type = "STRING", mode = "NULLABLE", description = "Origin system" },
    { name = "driver_id", type = "STRING", mode = "NULLABLE", description = "Driver identifier" },
    { name = "facility_id", type = "STRING", mode = "NULLABLE", description = "Current facility" },
    { name = "payload", type = "JSON", mode = "NULLABLE", description = "Event payload" },
  ])

  labels = {
    environment = var.environment
    layer       = "silver"
    domain      = "driver"
  }
}

resource "google_bigquery_table" "delivery_events" {
  dataset_id          = google_bigquery_dataset.clean.dataset_id
  table_id            = "delivery_events"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  time_partitioning {
    type          = "DAY"
    field         = "event_time"
    expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000
  }

  clustering = ["delivery_id", "shipment_id", "event_type"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED", description = "Unique event identifier" },
    { name = "event_type", type = "STRING", mode = "REQUIRED", description = "Event type" },
    { name = "event_version", type = "STRING", mode = "REQUIRED", description = "Schema version" },
    { name = "event_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Business event time" },
    { name = "ingest_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Pipeline ingestion time" },
    { name = "trace_id", type = "STRING", mode = "NULLABLE", description = "Distributed tracing ID" },
    { name = "source_system", type = "STRING", mode = "NULLABLE", description = "Origin system" },
    { name = "delivery_id", type = "STRING", mode = "NULLABLE", description = "Delivery identifier" },
    { name = "shipment_id", type = "STRING", mode = "NULLABLE", description = "Shipment identifier" },
    { name = "driver_id", type = "STRING", mode = "NULLABLE", description = "Driver identifier" },
    { name = "facility_id", type = "STRING", mode = "NULLABLE", description = "Facility identifier" },
    { name = "payload", type = "JSON", mode = "NULLABLE", description = "Event payload" },
  ])

  labels = {
    environment = var.environment
    layer       = "silver"
    domain      = "delivery"
  }
}

# ============================================================================
# Gold Layer Tables
# ============================================================================

resource "google_bigquery_table" "dim_facility" {
  dataset_id          = google_bigquery_dataset.curated.dataset_id
  table_id            = "dim_facility"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  schema = jsonencode([
    { name = "facility_id", type = "STRING", mode = "REQUIRED", description = "Facility identifier" },
    { name = "facility_name", type = "STRING", mode = "NULLABLE", description = "Facility name" },
    { name = "facility_type", type = "STRING", mode = "NULLABLE", description = "Type (warehouse, hub, last-mile)" },
    { name = "address", type = "STRING", mode = "NULLABLE", description = "Street address" },
    { name = "city", type = "STRING", mode = "NULLABLE", description = "City" },
    { name = "state", type = "STRING", mode = "NULLABLE", description = "State/Province" },
    { name = "country", type = "STRING", mode = "NULLABLE", description = "Country" },
    { name = "postal_code", type = "STRING", mode = "NULLABLE", description = "Postal code" },
    { name = "latitude", type = "FLOAT64", mode = "NULLABLE", description = "Latitude" },
    { name = "longitude", type = "FLOAT64", mode = "NULLABLE", description = "Longitude" },
    { name = "timezone", type = "STRING", mode = "NULLABLE", description = "Timezone" },
    { name = "capacity_units", type = "INT64", mode = "NULLABLE", description = "Capacity in units" },
    { name = "is_active", type = "BOOL", mode = "NULLABLE", description = "Is facility active" },
    { name = "effective_from", type = "TIMESTAMP", mode = "REQUIRED", description = "SCD2 effective from" },
    { name = "effective_to", type = "TIMESTAMP", mode = "NULLABLE", description = "SCD2 effective to" },
    { name = "is_current", type = "BOOL", mode = "REQUIRED", description = "Is current version" },
  ])

  labels = {
    environment = var.environment
    layer       = "gold"
    type        = "dimension"
  }
}

resource "google_bigquery_table" "dim_carrier" {
  dataset_id          = google_bigquery_dataset.curated.dataset_id
  table_id            = "dim_carrier"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  schema = jsonencode([
    { name = "carrier_id", type = "STRING", mode = "REQUIRED", description = "Carrier identifier" },
    { name = "carrier_name", type = "STRING", mode = "NULLABLE", description = "Carrier name" },
    { name = "carrier_type", type = "STRING", mode = "NULLABLE", description = "Type (parcel, freight, LTL)" },
    { name = "scac_code", type = "STRING", mode = "NULLABLE", description = "Standard Carrier Alpha Code" },
    { name = "is_active", type = "BOOL", mode = "NULLABLE", description = "Is carrier active" },
    { name = "effective_from", type = "TIMESTAMP", mode = "REQUIRED", description = "SCD2 effective from" },
    { name = "effective_to", type = "TIMESTAMP", mode = "NULLABLE", description = "SCD2 effective to" },
    { name = "is_current", type = "BOOL", mode = "REQUIRED", description = "Is current version" },
  ])

  labels = {
    environment = var.environment
    layer       = "gold"
    type        = "dimension"
  }
}

resource "google_bigquery_table" "dim_driver" {
  dataset_id          = google_bigquery_dataset.curated.dataset_id
  table_id            = "dim_driver"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  schema = jsonencode([
    { name = "driver_id", type = "STRING", mode = "REQUIRED", description = "Driver identifier" },
    { name = "driver_name_hash", type = "STRING", mode = "NULLABLE", description = "Hashed driver name (PII)" },
    { name = "carrier_id", type = "STRING", mode = "NULLABLE", description = "Associated carrier" },
    { name = "home_facility_id", type = "STRING", mode = "NULLABLE", description = "Home facility" },
    { name = "license_type", type = "STRING", mode = "NULLABLE", description = "License type" },
    { name = "is_active", type = "BOOL", mode = "NULLABLE", description = "Is driver active" },
    { name = "effective_from", type = "TIMESTAMP", mode = "REQUIRED", description = "SCD2 effective from" },
    { name = "effective_to", type = "TIMESTAMP", mode = "NULLABLE", description = "SCD2 effective to" },
    { name = "is_current", type = "BOOL", mode = "REQUIRED", description = "Is current version" },
  ])

  labels = {
    environment = var.environment
    layer       = "gold"
    type        = "dimension"
  }
}

resource "google_bigquery_table" "fact_deliveries" {
  dataset_id          = google_bigquery_dataset.curated.dataset_id
  table_id            = "fact_deliveries"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  time_partitioning {
    type          = "DAY"
    field         = "delivery_date"
    expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000
  }

  clustering = ["facility_id", "carrier_id"]

  schema = jsonencode([
    { name = "delivery_id", type = "STRING", mode = "REQUIRED", description = "Delivery identifier" },
    { name = "shipment_id", type = "STRING", mode = "REQUIRED", description = "Shipment identifier" },
    { name = "delivery_date", type = "DATE", mode = "REQUIRED", description = "Delivery date (partition key)" },
    { name = "facility_id", type = "STRING", mode = "NULLABLE", description = "Origin facility" },
    { name = "driver_id", type = "STRING", mode = "NULLABLE", description = "Driver identifier" },
    { name = "carrier_id", type = "STRING", mode = "NULLABLE", description = "Carrier identifier" },
    { name = "status", type = "STRING", mode = "NULLABLE", description = "Final delivery status" },
    { name = "scheduled_time", type = "TIMESTAMP", mode = "NULLABLE", description = "Scheduled delivery time" },
    { name = "delivery_time", type = "TIMESTAMP", mode = "NULLABLE", description = "Actual delivery time" },
    { name = "first_attempt_time", type = "TIMESTAMP", mode = "NULLABLE", description = "First attempt time" },
    { name = "attempt_count", type = "INT64", mode = "NULLABLE", description = "Number of attempts" },
    { name = "on_time_flag", type = "BOOL", mode = "NULLABLE", description = "Delivered on time" },
    { name = "delivery_duration_minutes", type = "INT64", mode = "NULLABLE", description = "Duration in minutes" },
  ])

  labels = {
    environment = var.environment
    layer       = "gold"
    type        = "fact"
  }
}

resource "google_bigquery_table" "fact_shipment_events" {
  dataset_id          = google_bigquery_dataset.curated.dataset_id
  table_id            = "fact_shipment_events"
  project             = var.project_id
  deletion_protection = var.environment == "prod"

  time_partitioning {
    type          = "DAY"
    field         = "event_date"
    expiration_ms = local.partition_expiration_days * 24 * 60 * 60 * 1000
  }

  clustering = ["shipment_id", "event_type"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED", description = "Event identifier" },
    { name = "shipment_id", type = "STRING", mode = "REQUIRED", description = "Shipment identifier" },
    { name = "event_date", type = "DATE", mode = "REQUIRED", description = "Event date (partition key)" },
    { name = "event_type", type = "STRING", mode = "REQUIRED", description = "Event type" },
    { name = "event_time", type = "TIMESTAMP", mode = "REQUIRED", description = "Event timestamp" },
    { name = "facility_id", type = "STRING", mode = "NULLABLE", description = "Facility where event occurred" },
    { name = "carrier_id", type = "STRING", mode = "NULLABLE", description = "Carrier identifier" },
    { name = "driver_id", type = "STRING", mode = "NULLABLE", description = "Driver identifier" },
    { name = "status", type = "STRING", mode = "NULLABLE", description = "Shipment status" },
    { name = "latitude", type = "FLOAT64", mode = "NULLABLE", description = "Event latitude" },
    { name = "longitude", type = "FLOAT64", mode = "NULLABLE", description = "Event longitude" },
  ])

  labels = {
    environment = var.environment
    layer       = "gold"
    type        = "fact"
  }
}

# ============================================================================
# Outputs
# ============================================================================

output "raw_dataset_id" {
  description = "Raw dataset ID"
  value       = google_bigquery_dataset.raw.dataset_id
}

output "clean_dataset_id" {
  description = "Clean dataset ID"
  value       = google_bigquery_dataset.clean.dataset_id
}

output "curated_dataset_id" {
  description = "Curated dataset ID"
  value       = google_bigquery_dataset.curated.dataset_id
}

output "features_dataset_id" {
  description = "Features dataset ID"
  value       = google_bigquery_dataset.features.dataset_id
}

output "staging_dataset_id" {
  description = "Staging dataset ID"
  value       = google_bigquery_dataset.staging.dataset_id
}
