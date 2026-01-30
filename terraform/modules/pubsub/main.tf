/**
 * Pub/Sub Module
 * Creates topics, subscriptions, and DLQ configuration for event ingestion.
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

variable "message_retention_duration" {
  description = "Message retention duration"
  type        = string
  default     = "604800s" # 7 days
}

variable "ack_deadline_seconds" {
  description = "Acknowledgment deadline in seconds"
  type        = number
  default     = 600 # 10 minutes for Dataflow
}

locals {
  name_prefix = var.environment

  # Event topics to create
  event_topics = [
    "shipment-events",
    "facility-events",
    "driver-events",
    "delivery-events",
  ]
}

# ============================================================================
# Main Event Topics
# ============================================================================

resource "google_pubsub_topic" "events" {
  for_each = toset(local.event_topics)

  name    = "${local.name_prefix}-${each.key}"
  project = var.project_id

  message_retention_duration = var.message_retention_duration

  labels = {
    environment = var.environment
    purpose     = "event-ingestion"
  }

  schema_settings {
    encoding = "JSON"
  }
}

# ============================================================================
# Dead Letter Topics
# ============================================================================

resource "google_pubsub_topic" "dlq" {
  for_each = toset(local.event_topics)

  name    = "${local.name_prefix}-${each.key}-dlq"
  project = var.project_id

  message_retention_duration = "2592000s" # 30 days for DLQ

  labels = {
    environment = var.environment
    purpose     = "dead-letter-queue"
    source      = each.key
  }
}

# ============================================================================
# Main Subscriptions (for Dataflow)
# ============================================================================

resource "google_pubsub_subscription" "dataflow" {
  for_each = toset(local.event_topics)

  name    = "${local.name_prefix}-${each.key}-dataflow"
  topic   = google_pubsub_topic.events[each.key].name
  project = var.project_id

  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.message_retention_duration
  retain_acked_messages      = false
  enable_exactly_once_delivery = true

  expiration_policy {
    ttl = "" # Never expire
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq[each.key].id
    max_delivery_attempts = 5
  }

  labels = {
    environment = var.environment
    consumer    = "dataflow"
  }
}

# ============================================================================
# DLQ Subscriptions (for monitoring/replay)
# ============================================================================

resource "google_pubsub_subscription" "dlq_monitor" {
  for_each = toset(local.event_topics)

  name    = "${local.name_prefix}-${each.key}-dlq-monitor"
  topic   = google_pubsub_topic.dlq[each.key].name
  project = var.project_id

  ack_deadline_seconds       = 60
  message_retention_duration = "2592000s" # 30 days

  expiration_policy {
    ttl = "" # Never expire
  }

  labels = {
    environment = var.environment
    purpose     = "dlq-monitoring"
  }
}

# ============================================================================
# IAM Bindings
# ============================================================================

resource "google_pubsub_subscription_iam_member" "dataflow_subscriber" {
  for_each = toset(local.event_topics)

  subscription = google_pubsub_subscription.dataflow[each.key].name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${var.dataflow_worker_email}"
  project      = var.project_id
}

resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  for_each = toset(local.event_topics)

  topic   = google_pubsub_topic.dlq[each.key].name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${var.dataflow_worker_email}"
  project = var.project_id
}

# ============================================================================
# Unified Events Topic (for consolidated streaming)
# ============================================================================

resource "google_pubsub_topic" "unified_events" {
  name    = "${local.name_prefix}-unified-events"
  project = var.project_id

  message_retention_duration = var.message_retention_duration

  labels = {
    environment = var.environment
    purpose     = "unified-ingestion"
  }
}

resource "google_pubsub_subscription" "unified_dataflow" {
  name    = "${local.name_prefix}-unified-events-dataflow"
  topic   = google_pubsub_topic.unified_events.name
  project = var.project_id

  ack_deadline_seconds         = var.ack_deadline_seconds
  message_retention_duration   = var.message_retention_duration
  enable_exactly_once_delivery = true

  expiration_policy {
    ttl = ""
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  labels = {
    environment = var.environment
    consumer    = "dataflow"
  }
}

# ============================================================================
# Outputs
# ============================================================================

output "event_topic_ids" {
  description = "Map of event topic names to IDs"
  value       = { for k, v in google_pubsub_topic.events : k => v.id }
}

output "event_topic_names" {
  description = "Map of event topic names"
  value       = { for k, v in google_pubsub_topic.events : k => v.name }
}

output "dlq_topic_ids" {
  description = "Map of DLQ topic names to IDs"
  value       = { for k, v in google_pubsub_topic.dlq : k => v.id }
}

output "dataflow_subscription_ids" {
  description = "Map of Dataflow subscription IDs"
  value       = { for k, v in google_pubsub_subscription.dataflow : k => v.id }
}

output "dataflow_subscription_names" {
  description = "Map of Dataflow subscription names"
  value       = { for k, v in google_pubsub_subscription.dataflow : k => v.name }
}

output "unified_topic_id" {
  description = "Unified events topic ID"
  value       = google_pubsub_topic.unified_events.id
}

output "unified_subscription_id" {
  description = "Unified events subscription ID"
  value       = google_pubsub_subscription.unified_dataflow.id
}
