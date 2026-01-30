/**
 * Cloud Run Module
 * Creates Cloud Run service for the Analytics API.
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

variable "analytics_api_email" {
  description = "Analytics API service account email"
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

variable "image_url" {
  description = "Container image URL"
  type        = string
  default     = "" # Will be set during deployment
}

locals {
  name_prefix = var.environment

  # Environment-specific configurations
  config = {
    dev = {
      min_instances        = 0
      max_instances        = 3
      cpu                  = "1"
      memory               = "512Mi"
      timeout_seconds      = 60
      concurrency          = 80
      allow_unauthenticated = true
    }
    prod = {
      min_instances        = 2
      max_instances        = 10
      cpu                  = "2"
      memory               = "1Gi"
      timeout_seconds      = 30
      concurrency          = 100
      allow_unauthenticated = false
    }
  }

  env_config = local.config[var.environment]
}

# ============================================================================
# Artifact Registry for API Images
# ============================================================================

resource "google_artifact_registry_repository" "api" {
  location      = var.region
  repository_id = "${local.name_prefix}-analytics-api"
  description   = "Container images for Analytics API"
  format        = "DOCKER"
  project       = var.project_id

  labels = {
    environment = var.environment
  }
}

# ============================================================================
# Cloud Run Service
# ============================================================================

resource "google_cloud_run_v2_service" "analytics_api" {
  name     = "${local.name_prefix}-analytics-api"
  location = var.region
  project  = var.project_id

  template {
    service_account = var.analytics_api_email

    scaling {
      min_instance_count = local.env_config.min_instances
      max_instance_count = local.env_config.max_instances
    }

    timeout = "${local.env_config.timeout_seconds}s"

    containers {
      # Use placeholder image initially; will be updated by CD pipeline
      image = var.image_url != "" ? var.image_url : "gcr.io/cloudrun/hello"

      resources {
        limits = {
          cpu    = local.env_config.cpu
          memory = local.env_config.memory
        }
        cpu_idle = var.environment == "dev"
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }

      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }

      env {
        name  = "GCP_REGION"
        value = var.region
      }

      env {
        name  = "CURATED_DATASET"
        value = "${var.environment}_curated"
      }

      env {
        name  = "FEATURES_DATASET"
        value = "${var.environment}_features"
      }

      env {
        name  = "LOG_LEVEL"
        value = var.environment == "prod" ? "INFO" : "DEBUG"
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
        }
        timeout_seconds   = 5
        period_seconds    = 30
        failure_threshold = 3
      }
    }

    vpc_access {
      network_interfaces {
        network    = var.network_id
        subnetwork = var.subnetwork_id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    max_instance_request_concurrency = local.env_config.concurrency
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  labels = {
    environment = var.environment
    service     = "analytics-api"
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image, # Image updated by CI/CD
    ]
  }
}

# ============================================================================
# IAM - Allow Unauthenticated (dev only) or Authenticated Access
# ============================================================================

resource "google_cloud_run_v2_service_iam_member" "public_access" {
  count = local.env_config.allow_unauthenticated ? 1 : 0

  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.analytics_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ============================================================================
# Custom Domain Mapping (optional)
# ============================================================================

# Uncomment and configure if using custom domain
# resource "google_cloud_run_domain_mapping" "api" {
#   location = var.region
#   name     = var.environment == "prod" ? "api.logistics.example.com" : "api-dev.logistics.example.com"
#
#   metadata {
#     namespace = var.project_id
#   }
#
#   spec {
#     route_name = google_cloud_run_v2_service.analytics_api.name
#   }
# }

# ============================================================================
# Outputs
# ============================================================================

output "service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.analytics_api.name
}

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.analytics_api.uri
}

output "artifact_registry_url" {
  description = "Artifact Registry URL for API images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.api.name}"
}
