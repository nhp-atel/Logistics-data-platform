/**
 * IAM Module
 * Creates service accounts with least-privilege bindings for the logistics data platform.
 */

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "raw_bucket_name" {
  description = "Name of the raw data bucket"
  type        = string
}

variable "dataflow_temp_bucket_name" {
  description = "Name of the Dataflow temp bucket"
  type        = string
}

locals {
  name_prefix = var.environment
}

# Dataflow Worker Service Account
resource "google_service_account" "dataflow_worker" {
  account_id   = "${local.name_prefix}-dataflow-worker"
  display_name = "Dataflow Worker (${var.environment})"
  description  = "Service account for Dataflow streaming ETL pipelines"
  project      = var.project_id
}

# Composer Worker Service Account
resource "google_service_account" "composer_worker" {
  account_id   = "${local.name_prefix}-composer-worker"
  display_name = "Composer Worker (${var.environment})"
  description  = "Service account for Cloud Composer batch orchestration"
  project      = var.project_id
}

# Analytics API Service Account
resource "google_service_account" "analytics_api" {
  account_id   = "${local.name_prefix}-analytics-api"
  display_name = "Analytics API (${var.environment})"
  description  = "Service account for read-only Analytics API"
  project      = var.project_id
}

# ============================================================================
# Dataflow Worker IAM Bindings
# ============================================================================

# Allow Dataflow worker to subscribe to Pub/Sub
resource "google_project_iam_member" "dataflow_pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

resource "google_project_iam_member" "dataflow_pubsub_viewer" {
  project = var.project_id
  role    = "roles/pubsub.viewer"
  member  = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

# Allow Dataflow worker to write to GCS (raw bucket)
resource "google_storage_bucket_iam_member" "dataflow_raw_writer" {
  bucket = var.raw_bucket_name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

# Allow Dataflow worker to use temp bucket
resource "google_storage_bucket_iam_member" "dataflow_temp_admin" {
  bucket = var.dataflow_temp_bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

# Allow Dataflow worker to write to BigQuery (raw/clean datasets only)
resource "google_project_iam_member" "dataflow_bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

resource "google_project_iam_member" "dataflow_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

# Allow Dataflow worker to run as Dataflow worker
resource "google_project_iam_member" "dataflow_worker_role" {
  project = var.project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

# Allow Dataflow worker to read secrets (for Kafka credentials)
resource "google_project_iam_member" "dataflow_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

# Allow Dataflow worker to write metrics
resource "google_project_iam_member" "dataflow_monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.dataflow_worker.email}"
}

# ============================================================================
# Composer Worker IAM Bindings
# ============================================================================

# Allow Composer worker to run BigQuery jobs
resource "google_project_iam_member" "composer_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.composer_worker.email}"
}

# Allow Composer worker to edit BigQuery data (curated dataset)
resource "google_project_iam_member" "composer_bigquery_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.composer_worker.email}"
}

# Allow Composer worker to develop/manage Dataflow jobs
resource "google_project_iam_member" "composer_dataflow_developer" {
  project = var.project_id
  role    = "roles/dataflow.developer"
  member  = "serviceAccount:${google_service_account.composer_worker.email}"
}

# Allow Composer worker to read from GCS
resource "google_project_iam_member" "composer_storage_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.composer_worker.email}"
}

# Allow Composer worker to use Composer environment
resource "google_project_iam_member" "composer_worker_role" {
  project = var.project_id
  role    = "roles/composer.worker"
  member  = "serviceAccount:${google_service_account.composer_worker.email}"
}

# Allow Composer worker to write metrics
resource "google_project_iam_member" "composer_monitoring_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.composer_worker.email}"
}

# Allow Composer worker to write logs
resource "google_project_iam_member" "composer_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.composer_worker.email}"
}

# ============================================================================
# Analytics API IAM Bindings (Read-Only)
# ============================================================================

# Allow Analytics API to read BigQuery data (curated/features only)
resource "google_project_iam_member" "analytics_bigquery_data_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.analytics_api.email}"
}

resource "google_project_iam_member" "analytics_bigquery_job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.analytics_api.email}"
}

# Allow Analytics API to access secrets (for API keys, etc.)
resource "google_project_iam_member" "analytics_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.analytics_api.email}"
}

# Allow Analytics API to run on Cloud Run
resource "google_project_iam_member" "analytics_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.analytics_api.email}"
}

# ============================================================================
# Workload Identity Bindings (for GKE)
# ============================================================================

resource "google_service_account_iam_member" "dataflow_workload_identity" {
  service_account_id = google_service_account.dataflow_worker.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[dataflow/dataflow-worker]"
}

output "dataflow_worker_email" {
  description = "Dataflow worker service account email"
  value       = google_service_account.dataflow_worker.email
}

output "dataflow_worker_id" {
  description = "Dataflow worker service account ID"
  value       = google_service_account.dataflow_worker.id
}

output "composer_worker_email" {
  description = "Composer worker service account email"
  value       = google_service_account.composer_worker.email
}

output "composer_worker_id" {
  description = "Composer worker service account ID"
  value       = google_service_account.composer_worker.id
}

output "analytics_api_email" {
  description = "Analytics API service account email"
  value       = google_service_account.analytics_api.email
}

output "analytics_api_id" {
  description = "Analytics API service account ID"
  value       = google_service_account.analytics_api.id
}
