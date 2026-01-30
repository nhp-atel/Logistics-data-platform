/**
 * Cloud Composer Module
 * Creates Cloud Composer 2 environment for batch orchestration.
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

variable "network_id" {
  description = "VPC network ID"
  type        = string
}

variable "subnetwork_id" {
  description = "Subnetwork ID"
  type        = string
}

variable "composer_worker_email" {
  description = "Composer worker service account email"
  type        = string
}

locals {
  name_prefix = var.environment

  # Environment-specific configurations
  config = {
    dev = {
      environment_size = "ENVIRONMENT_SIZE_SMALL"
      scheduler_count  = 1
      scheduler_cpu    = 0.5
      scheduler_memory = 1.875
      scheduler_storage = 1
      web_server_cpu   = 0.5
      web_server_memory = 1.875
      web_server_storage = 1
      worker_cpu       = 0.5
      worker_memory    = 1.875
      worker_storage   = 1
      worker_min_count = 1
      worker_max_count = 3
    }
    prod = {
      environment_size = "ENVIRONMENT_SIZE_MEDIUM"
      scheduler_count  = 2
      scheduler_cpu    = 2
      scheduler_memory = 7.5
      scheduler_storage = 5
      web_server_cpu   = 2
      web_server_memory = 7.5
      web_server_storage = 5
      worker_cpu       = 2
      worker_memory    = 7.5
      worker_storage   = 5
      worker_min_count = 3
      worker_max_count = 10
    }
  }

  env_config = local.config[var.environment]
}

# ============================================================================
# Cloud Composer 2 Environment
# ============================================================================

resource "google_composer_environment" "main" {
  name    = "${local.name_prefix}-composer"
  project = var.project_id
  region  = var.region

  config {
    software_config {
      image_version = "composer-2.5.0-airflow-2.6.3"

      airflow_config_overrides = {
        core-dags_are_paused_at_creation = "True"
        core-max_active_runs_per_dag     = var.environment == "prod" ? "5" : "2"
        core-parallelism                 = var.environment == "prod" ? "32" : "8"
        scheduler-dag_dir_list_interval  = "60"
        webserver-expose_config          = "False"
        celery-worker_concurrency        = var.environment == "prod" ? "16" : "4"
      }

      pypi_packages = {
        "apache-beam[gcp]" = ">=2.50.0"
        "google-cloud-bigquery" = ">=3.0.0"
        "google-cloud-storage" = ">=2.0.0"
        "pydantic" = ">=2.0.0"
        "jsonschema" = ">=4.0.0"
        "sentry-sdk" = ">=1.0.0"
      }

      env_variables = {
        ENVIRONMENT      = var.environment
        GCP_PROJECT      = var.project_id
        GCP_REGION       = var.region
        AIRFLOW_VAR_ENV  = var.environment
      }
    }

    workloads_config {
      scheduler {
        cpu        = local.env_config.scheduler_cpu
        memory_gb  = local.env_config.scheduler_memory
        storage_gb = local.env_config.scheduler_storage
        count      = local.env_config.scheduler_count
      }

      web_server {
        cpu        = local.env_config.web_server_cpu
        memory_gb  = local.env_config.web_server_memory
        storage_gb = local.env_config.web_server_storage
      }

      worker {
        cpu        = local.env_config.worker_cpu
        memory_gb  = local.env_config.worker_memory
        storage_gb = local.env_config.worker_storage
        min_count  = local.env_config.worker_min_count
        max_count  = local.env_config.worker_max_count
      }
    }

    environment_size = local.env_config.environment_size

    node_config {
      network         = var.network_id
      subnetwork      = var.subnetwork_id
      service_account = var.composer_worker_email

      ip_allocation_policy {
        cluster_secondary_range_name  = "pods"
        services_secondary_range_name = "services"
      }
    }

    private_environment_config {
      enable_private_endpoint = var.environment == "prod"
      cloud_sql_ipv4_cidr_block = "10.0.0.0/12"
      master_ipv4_cidr_block    = var.environment == "prod" ? "172.16.0.0/28" : null
    }

    maintenance_window {
      start_time = "2024-01-01T02:00:00Z"
      end_time   = "2024-01-01T06:00:00Z"
      recurrence = "FREQ=WEEKLY;BYDAY=SU"
    }

    recovery_config {
      scheduled_snapshots_config {
        enabled                    = var.environment == "prod"
        snapshot_location          = var.region
        snapshot_creation_schedule = "0 4 * * *"
        time_zone                  = "UTC"
      }
    }
  }

  labels = {
    environment = var.environment
    purpose     = "batch-orchestration"
  }

  lifecycle {
    prevent_destroy = false # Set to true in prod
  }
}

# ============================================================================
# Airflow Variables (stored as secrets and synced)
# ============================================================================

resource "google_secret_manager_secret" "airflow_variables" {
  secret_id = "${local.name_prefix}-airflow-variables"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "airflow-config"
  }
}

resource "google_secret_manager_secret_version" "airflow_variables" {
  secret = google_secret_manager_secret.airflow_variables.id

  secret_data = jsonencode({
    project_id         = var.project_id
    region             = var.region
    environment        = var.environment
    raw_dataset        = "${var.environment}_raw"
    clean_dataset      = "${var.environment}_clean"
    curated_dataset    = "${var.environment}_curated"
    features_dataset   = "${var.environment}_features"
    notification_email = var.environment == "prod" ? "data-alerts@example.com" : "dev-alerts@example.com"
  })
}

resource "google_secret_manager_secret_iam_member" "composer_accessor" {
  secret_id = google_secret_manager_secret.airflow_variables.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.composer_worker_email}"
  project   = var.project_id
}

# ============================================================================
# Outputs
# ============================================================================

output "composer_environment_name" {
  description = "Composer environment name"
  value       = google_composer_environment.main.name
}

output "composer_environment_id" {
  description = "Composer environment ID"
  value       = google_composer_environment.main.id
}

output "dag_gcs_prefix" {
  description = "GCS prefix for DAGs"
  value       = google_composer_environment.main.config[0].dag_gcs_prefix
}

output "airflow_uri" {
  description = "Airflow web UI URI"
  value       = google_composer_environment.main.config[0].airflow_uri
}

output "gke_cluster" {
  description = "GKE cluster running Composer"
  value       = google_composer_environment.main.config[0].gke_cluster
}
