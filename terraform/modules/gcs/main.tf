/**
 * GCS Module
 * Creates buckets with lifecycle policies for medallion architecture storage.
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

locals {
  name_prefix = "${var.project_id}-${var.environment}"

  # Lifecycle transition days based on environment
  lifecycle_config = {
    dev = {
      nearline_days  = 7
      coldline_days  = 30
      archive_days   = 90
      delete_days    = 180
    }
    prod = {
      nearline_days  = 30
      coldline_days  = 90
      archive_days   = 365
      delete_days    = 730
    }
  }

  lifecycle = local.lifecycle_config[var.environment]
}

# ============================================================================
# Raw Data Bucket (Bronze Layer)
# ============================================================================

resource "google_storage_bucket" "raw" {
  name          = "${local.name_prefix}-raw"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = local.lifecycle.nearline_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = local.lifecycle.coldline_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = local.lifecycle.archive_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }

  lifecycle_rule {
    condition {
      age = local.lifecycle.delete_days
    }
    action {
      type = "Delete"
    }
  }

  # Delete non-current versions after 30 days
  lifecycle_rule {
    condition {
      num_newer_versions = 3
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
    layer       = "bronze"
    purpose     = "raw-data"
  }
}

# ============================================================================
# Dataflow Temp Bucket
# ============================================================================

resource "google_storage_bucket" "dataflow_temp" {
  name          = "${local.name_prefix}-dataflow-temp"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  # Auto-delete temp files after 7 days
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
    purpose     = "dataflow-temp"
  }
}

# ============================================================================
# Dataflow Staging Bucket
# ============================================================================

resource "google_storage_bucket" "dataflow_staging" {
  name          = "${local.name_prefix}-dataflow-staging"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
    purpose     = "dataflow-staging"
  }
}

# ============================================================================
# Composer DAGs Bucket
# ============================================================================

resource "google_storage_bucket" "composer_dags" {
  name          = "${local.name_prefix}-composer-dags"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  labels = {
    environment = var.environment
    purpose     = "composer-dags"
  }
}

# ============================================================================
# ML Artifacts Bucket
# ============================================================================

resource "google_storage_bucket" "ml_artifacts" {
  name          = "${local.name_prefix}-ml-artifacts"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = local.lifecycle.coldline_days
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  labels = {
    environment = var.environment
    purpose     = "ml-artifacts"
  }
}

# ============================================================================
# Quarantine Bucket (for invalid/DLQ data)
# ============================================================================

resource "google_storage_bucket" "quarantine" {
  name          = "${local.name_prefix}-quarantine"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
    purpose     = "quarantine"
  }
}

# ============================================================================
# IAM Bindings
# ============================================================================

# Dataflow worker access to raw bucket
resource "google_storage_bucket_iam_member" "dataflow_raw_creator" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${var.dataflow_worker_email}"
}

# Dataflow worker access to temp bucket
resource "google_storage_bucket_iam_member" "dataflow_temp_admin" {
  bucket = google_storage_bucket.dataflow_temp.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.dataflow_worker_email}"
}

# Dataflow worker access to staging bucket
resource "google_storage_bucket_iam_member" "dataflow_staging_admin" {
  bucket = google_storage_bucket.dataflow_staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.dataflow_worker_email}"
}

# Dataflow worker access to quarantine bucket
resource "google_storage_bucket_iam_member" "dataflow_quarantine_creator" {
  bucket = google_storage_bucket.quarantine.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${var.dataflow_worker_email}"
}

# Composer worker access to DAGs bucket
resource "google_storage_bucket_iam_member" "composer_dags_admin" {
  bucket = google_storage_bucket.composer_dags.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.composer_worker_email}"
}

# Composer worker access to raw bucket (for reading)
resource "google_storage_bucket_iam_member" "composer_raw_viewer" {
  bucket = google_storage_bucket.raw.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${var.composer_worker_email}"
}

# ============================================================================
# Outputs
# ============================================================================

output "raw_bucket_name" {
  description = "Raw data bucket name"
  value       = google_storage_bucket.raw.name
}

output "raw_bucket_url" {
  description = "Raw data bucket URL"
  value       = google_storage_bucket.raw.url
}

output "dataflow_temp_bucket_name" {
  description = "Dataflow temp bucket name"
  value       = google_storage_bucket.dataflow_temp.name
}

output "dataflow_staging_bucket_name" {
  description = "Dataflow staging bucket name"
  value       = google_storage_bucket.dataflow_staging.name
}

output "composer_dags_bucket_name" {
  description = "Composer DAGs bucket name"
  value       = google_storage_bucket.composer_dags.name
}

output "ml_artifacts_bucket_name" {
  description = "ML artifacts bucket name"
  value       = google_storage_bucket.ml_artifacts.name
}

output "quarantine_bucket_name" {
  description = "Quarantine bucket name"
  value       = google_storage_bucket.quarantine.name
}
