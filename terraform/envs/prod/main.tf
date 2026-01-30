/**
 * Production Environment
 * Composes all modules for the prod environment with production-grade resources.
 */

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "terraform-state-logistics-prod"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ============================================================================
# Variables
# ============================================================================

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "billing_account_id" {
  description = "Billing account ID for budget alerts"
  type        = string
}

variable "enable_composer" {
  description = "Enable Cloud Composer (expensive resource)"
  type        = bool
  default     = true
}

locals {
  environment = "prod"
}

# ============================================================================
# Enable Required APIs
# ============================================================================

resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "iam.googleapis.com",
    "pubsub.googleapis.com",
    "storage.googleapis.com",
    "bigquery.googleapis.com",
    "dataflow.googleapis.com",
    "composer.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "servicenetworking.googleapis.com",
  ])

  project = var.project_id
  service = each.key

  disable_on_destroy = false
}

# ============================================================================
# Networking
# ============================================================================

module "networking" {
  source = "../../modules/networking"

  project_id  = var.project_id
  region      = var.region
  environment = local.environment
  vpc_cidr    = "10.1.0.0/16" # Different CIDR from dev

  depends_on = [google_project_service.apis]
}

# ============================================================================
# GCS Buckets (created before IAM to allow bucket-level IAM)
# ============================================================================

resource "google_storage_bucket" "raw_temp" {
  name          = "${var.project_id}-${local.environment}-raw"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket" "dataflow_temp_temp" {
  name          = "${var.project_id}-${local.environment}-dataflow-temp"
  project       = var.project_id
  location      = var.region
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  depends_on = [google_project_service.apis]
}

# ============================================================================
# IAM
# ============================================================================

module "iam" {
  source = "../../modules/iam"

  project_id                = var.project_id
  environment               = local.environment
  raw_bucket_name           = google_storage_bucket.raw_temp.name
  dataflow_temp_bucket_name = google_storage_bucket.dataflow_temp_temp.name

  depends_on = [
    google_project_service.apis,
    google_storage_bucket.raw_temp,
    google_storage_bucket.dataflow_temp_temp
  ]
}

# ============================================================================
# GCS Buckets (full module)
# ============================================================================

module "gcs" {
  source = "../../modules/gcs"

  project_id            = var.project_id
  region                = var.region
  environment           = local.environment
  dataflow_worker_email = module.iam.dataflow_worker_email
  composer_worker_email = module.iam.composer_worker_email

  depends_on = [module.iam]
}

# ============================================================================
# Pub/Sub
# ============================================================================

module "pubsub" {
  source = "../../modules/pubsub"

  project_id            = var.project_id
  environment           = local.environment
  dataflow_worker_email = module.iam.dataflow_worker_email

  # Prod-specific settings
  message_retention_duration = "604800s" # 7 days
  ack_deadline_seconds       = 600       # 10 minutes

  depends_on = [module.iam]
}

# ============================================================================
# BigQuery
# ============================================================================

module "bigquery" {
  source = "../../modules/bigquery"

  project_id            = var.project_id
  region                = var.region
  environment           = local.environment
  dataflow_worker_email = module.iam.dataflow_worker_email
  composer_worker_email = module.iam.composer_worker_email
  analytics_api_email   = module.iam.analytics_api_email

  depends_on = [module.iam]
}

# ============================================================================
# Dataflow
# ============================================================================

module "dataflow" {
  source = "../../modules/dataflow"

  project_id            = var.project_id
  region                = var.region
  environment           = local.environment
  network_self_link     = module.networking.network_self_link
  subnetwork_self_link  = "regions/${var.region}/subnetworks/${module.networking.dataflow_subnet_name}"
  dataflow_worker_email = module.iam.dataflow_worker_email
  temp_bucket_name      = module.gcs.dataflow_temp_bucket_name
  staging_bucket_name   = module.gcs.dataflow_staging_bucket_name

  # Prod-specific settings
  max_workers  = 20
  machine_type = "n1-standard-4"

  depends_on = [module.networking, module.iam, module.gcs]
}

# ============================================================================
# Cloud Composer
# ============================================================================

module "composer" {
  count  = var.enable_composer ? 1 : 0
  source = "../../modules/composer"

  project_id            = var.project_id
  region                = var.region
  environment           = local.environment
  network_id            = module.networking.network_id
  subnetwork_id         = module.networking.dataflow_subnet_id
  composer_worker_email = module.iam.composer_worker_email

  depends_on = [module.networking, module.iam]
}

# ============================================================================
# Secret Manager
# ============================================================================

module "secrets" {
  source = "../../modules/secret-manager"

  project_id            = var.project_id
  environment           = local.environment
  dataflow_worker_email = module.iam.dataflow_worker_email
  composer_worker_email = module.iam.composer_worker_email
  analytics_api_email   = module.iam.analytics_api_email

  depends_on = [module.iam]
}

# ============================================================================
# Kafka Configuration
# ============================================================================

module "kafka" {
  source = "../../modules/kafka"

  project_id            = var.project_id
  region                = var.region
  environment           = local.environment
  dataflow_worker_email = module.iam.dataflow_worker_email
  use_confluent_cloud   = true

  depends_on = [module.iam]
}

# ============================================================================
# Monitoring
# ============================================================================

module "monitoring" {
  source = "../../modules/monitoring"

  project_id         = var.project_id
  region             = var.region
  environment        = local.environment
  billing_account_id = var.billing_account_id

  depends_on = [google_project_service.apis]
}

# ============================================================================
# Cloud Run (API)
# ============================================================================

module "cloud_run" {
  source = "../../modules/cloud-run"

  project_id          = var.project_id
  region              = var.region
  environment         = local.environment
  analytics_api_email = module.iam.analytics_api_email
  network_id          = module.networking.network_name
  subnetwork_id       = module.networking.dataflow_subnet_name

  depends_on = [module.networking, module.iam]
}

# ============================================================================
# Outputs
# ============================================================================

output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "environment" {
  description = "Environment name"
  value       = local.environment
}

output "vpc_network" {
  description = "VPC network name"
  value       = module.networking.network_name
}

output "service_accounts" {
  description = "Service account emails"
  value = {
    dataflow = module.iam.dataflow_worker_email
    composer = module.iam.composer_worker_email
    api      = module.iam.analytics_api_email
  }
}

output "pubsub_subscriptions" {
  description = "Pub/Sub subscription names for Dataflow"
  value       = module.pubsub.dataflow_subscription_names
}

output "bigquery_datasets" {
  description = "BigQuery dataset IDs"
  value = {
    raw      = module.bigquery.raw_dataset_id
    clean    = module.bigquery.clean_dataset_id
    curated  = module.bigquery.curated_dataset_id
    features = module.bigquery.features_dataset_id
  }
}

output "gcs_buckets" {
  description = "GCS bucket names"
  value = {
    raw            = module.gcs.raw_bucket_name
    dataflow_temp  = module.gcs.dataflow_temp_bucket_name
    dataflow_stage = module.gcs.dataflow_staging_bucket_name
    quarantine     = module.gcs.quarantine_bucket_name
  }
}

output "dataflow_config" {
  description = "Dataflow configuration"
  value = {
    flex_templates_bucket = module.dataflow.flex_templates_bucket
    artifact_registry_url = module.dataflow.artifact_registry_url
  }
}

output "composer_config" {
  description = "Cloud Composer configuration"
  value = var.enable_composer ? {
    environment_name = module.composer[0].composer_environment_name
    dag_gcs_prefix   = module.composer[0].dag_gcs_prefix
    airflow_uri      = module.composer[0].airflow_uri
  } : null
}

output "api_url" {
  description = "Analytics API URL"
  value       = module.cloud_run.service_url
}

output "monitoring_dashboard" {
  description = "Monitoring dashboard ID"
  value       = module.monitoring.dashboard_id
}
