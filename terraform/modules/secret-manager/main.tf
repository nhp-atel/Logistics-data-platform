/**
 * Secret Manager Module
 * Creates secrets for storing sensitive credentials.
 */

variable "project_id" {
  description = "GCP project ID"
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
}

# ============================================================================
# API Keys Secret
# ============================================================================

resource "google_secret_manager_secret" "api_keys" {
  secret_id = "${local.name_prefix}-api-keys"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "api-authentication"
  }
}

resource "google_secret_manager_secret_version" "api_keys" {
  secret = google_secret_manager_secret.api_keys.id

  secret_data = jsonencode({
    internal_api_key = "PLACEHOLDER_INTERNAL_API_KEY"
    partner_api_keys = {
      partner_a = "PLACEHOLDER_PARTNER_A_KEY"
      partner_b = "PLACEHOLDER_PARTNER_B_KEY"
    }
  })

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# ============================================================================
# Database Credentials Secret
# ============================================================================

resource "google_secret_manager_secret" "database_credentials" {
  secret_id = "${local.name_prefix}-database-credentials"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "database-auth"
  }
}

resource "google_secret_manager_secret_version" "database_credentials" {
  secret = google_secret_manager_secret.database_credentials.id

  secret_data = jsonencode({
    host     = "PLACEHOLDER_HOST"
    port     = 5432
    database = "logistics_${var.environment}"
    username = "PLACEHOLDER_USERNAME"
    password = "PLACEHOLDER_PASSWORD"
  })

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# ============================================================================
# PII Tokenization Keys
# ============================================================================

resource "google_secret_manager_secret" "pii_keys" {
  secret_id = "${local.name_prefix}-pii-tokenization-keys"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "pii-tokenization"
  }
}

resource "google_secret_manager_secret_version" "pii_keys" {
  secret = google_secret_manager_secret.pii_keys.id

  secret_data = jsonencode({
    encryption_key = "PLACEHOLDER_32_BYTE_KEY_BASE64"
    hmac_key       = "PLACEHOLDER_HMAC_KEY_BASE64"
    salt           = "PLACEHOLDER_SALT"
  })

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# ============================================================================
# External Service Credentials
# ============================================================================

resource "google_secret_manager_secret" "external_services" {
  secret_id = "${local.name_prefix}-external-service-credentials"
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    purpose     = "external-integrations"
  }
}

resource "google_secret_manager_secret_version" "external_services" {
  secret = google_secret_manager_secret.external_services.id

  secret_data = jsonencode({
    sentry_dsn         = "PLACEHOLDER_SENTRY_DSN"
    slack_webhook_url  = "PLACEHOLDER_SLACK_WEBHOOK"
    pagerduty_api_key  = "PLACEHOLDER_PAGERDUTY_KEY"
  })

  lifecycle {
    ignore_changes = [secret_data]
  }
}

# ============================================================================
# IAM Bindings
# ============================================================================

# Dataflow worker access
resource "google_secret_manager_secret_iam_member" "dataflow_pii_accessor" {
  secret_id = google_secret_manager_secret.pii_keys.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.dataflow_worker_email}"
  project   = var.project_id
}

resource "google_secret_manager_secret_iam_member" "dataflow_external_accessor" {
  secret_id = google_secret_manager_secret.external_services.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.dataflow_worker_email}"
  project   = var.project_id
}

# Composer worker access
resource "google_secret_manager_secret_iam_member" "composer_db_accessor" {
  secret_id = google_secret_manager_secret.database_credentials.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.composer_worker_email}"
  project   = var.project_id
}

resource "google_secret_manager_secret_iam_member" "composer_external_accessor" {
  secret_id = google_secret_manager_secret.external_services.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.composer_worker_email}"
  project   = var.project_id
}

# Analytics API access
resource "google_secret_manager_secret_iam_member" "api_keys_accessor" {
  secret_id = google_secret_manager_secret.api_keys.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.analytics_api_email}"
  project   = var.project_id
}

resource "google_secret_manager_secret_iam_member" "api_external_accessor" {
  secret_id = google_secret_manager_secret.external_services.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.analytics_api_email}"
  project   = var.project_id
}

# ============================================================================
# Outputs
# ============================================================================

output "api_keys_secret_id" {
  description = "API keys secret ID"
  value       = google_secret_manager_secret.api_keys.secret_id
}

output "database_credentials_secret_id" {
  description = "Database credentials secret ID"
  value       = google_secret_manager_secret.database_credentials.secret_id
}

output "pii_keys_secret_id" {
  description = "PII tokenization keys secret ID"
  value       = google_secret_manager_secret.pii_keys.secret_id
}

output "external_services_secret_id" {
  description = "External services credentials secret ID"
  value       = google_secret_manager_secret.external_services.secret_id
}

output "secret_ids" {
  description = "All secret IDs"
  value = {
    api_keys          = google_secret_manager_secret.api_keys.secret_id
    database          = google_secret_manager_secret.database_credentials.secret_id
    pii_keys          = google_secret_manager_secret.pii_keys.secret_id
    external_services = google_secret_manager_secret.external_services.secret_id
  }
}
