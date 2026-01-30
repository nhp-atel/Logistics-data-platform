/**
 * Monitoring Module
 * Creates budgets, alerts, and dashboards for the logistics data platform.
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

variable "notification_channels" {
  description = "List of notification channel IDs"
  type        = list(string)
  default     = []
}

variable "billing_account_id" {
  description = "Billing account ID for budget alerts"
  type        = string
  default     = ""
}

locals {
  name_prefix = var.environment

  # Budget thresholds based on environment
  budget_config = {
    dev = {
      monthly_budget = 500
      thresholds     = [0.5, 0.75, 0.9, 1.0]
    }
    prod = {
      monthly_budget = 5000
      thresholds     = [0.5, 0.75, 0.9, 1.0]
    }
  }

  budget = local.budget_config[var.environment]
}

# ============================================================================
# Notification Channels
# ============================================================================

resource "google_monitoring_notification_channel" "email" {
  display_name = "${local.name_prefix}-data-platform-alerts"
  type         = "email"
  project      = var.project_id

  labels = {
    email_address = var.environment == "prod" ? "data-platform-alerts@example.com" : "dev-alerts@example.com"
  }
}

resource "google_monitoring_notification_channel" "pagerduty" {
  count = var.environment == "prod" ? 1 : 0

  display_name = "${local.name_prefix}-data-platform-pagerduty"
  type         = "pagerduty"
  project      = var.project_id

  labels = {
    service_key = "PLACEHOLDER_PAGERDUTY_KEY"
  }

  sensitive_labels {
    service_key = "PLACEHOLDER_PAGERDUTY_KEY"
  }

  lifecycle {
    ignore_changes = [labels, sensitive_labels]
  }
}

# ============================================================================
# Alert Policies - Dataflow
# ============================================================================

resource "google_monitoring_alert_policy" "dataflow_lag" {
  display_name = "${local.name_prefix}-dataflow-data-lag"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Dataflow Data Watermark Lag"

    condition_threshold {
      filter          = "resource.type=\"dataflow_job\" AND metric.type=\"dataflow.googleapis.com/job/data_watermark_age\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.environment == "prod" ? 600 : 1800 # 10 min prod, 30 min dev

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = concat(
    [google_monitoring_notification_channel.email.name],
    var.environment == "prod" ? [google_monitoring_notification_channel.pagerduty[0].name] : []
  )

  alert_strategy {
    auto_close = "3600s"
  }

  documentation {
    content   = "Dataflow pipeline data watermark lag is high. This indicates the pipeline is falling behind in processing events."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "dataflow_errors" {
  display_name = "${local.name_prefix}-dataflow-errors"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Dataflow System Errors"

    condition_threshold {
      filter          = "resource.type=\"dataflow_job\" AND metric.type=\"dataflow.googleapis.com/job/element_count\" AND metric.labels.pcollection=\"errors\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.environment == "prod" ? 10 : 50

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Dataflow pipeline is experiencing elevated error rates. Check the DLQ and pipeline logs for details."
    mime_type = "text/markdown"
  }
}

# ============================================================================
# Alert Policies - Pub/Sub
# ============================================================================

resource "google_monitoring_alert_policy" "pubsub_unacked" {
  display_name = "${local.name_prefix}-pubsub-unacked-messages"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Pub/Sub Unacked Messages High"

    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      duration        = "600s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.environment == "prod" ? 10000 : 1000

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "3600s"
  }

  documentation {
    content   = "Pub/Sub subscription has accumulated unacked messages. The consumer may be down or unable to keep up with the message rate."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "dlq_messages" {
  display_name = "${local.name_prefix}-dlq-messages"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "DLQ Messages Detected"

    condition_threshold {
      filter          = "resource.type=\"pubsub_subscription\" AND resource.labels.subscription_id=monitoring.regex.full_match(\".*-dlq.*\") AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "3600s"
  }

  documentation {
    content   = "Messages have been sent to the Dead Letter Queue. Investigate the cause and consider replaying after fixing the issue."
    mime_type = "text/markdown"
  }
}

# ============================================================================
# Alert Policies - BigQuery
# ============================================================================

resource "google_monitoring_alert_policy" "bigquery_slot_utilization" {
  display_name = "${local.name_prefix}-bigquery-slot-utilization"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "BigQuery Slot Utilization High"

    condition_threshold {
      filter          = "resource.type=\"bigquery_project\" AND metric.type=\"bigquery.googleapis.com/slots/allocated_for_project\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.environment == "prod" ? 500 : 100

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "3600s"
  }

  documentation {
    content   = "BigQuery slot utilization is high. Consider optimizing queries or increasing slot capacity."
    mime_type = "text/markdown"
  }
}

# ============================================================================
# Alert Policies - Cloud Run (API)
# ============================================================================

resource "google_monitoring_alert_policy" "api_latency" {
  display_name = "${local.name_prefix}-api-latency"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "API P99 Latency High"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_latencies\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.environment == "prod" ? 1000 : 3000 # milliseconds

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_99"
        cross_series_reducer = "REDUCE_MAX"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Analytics API P99 latency is elevated. Check for slow queries or resource constraints."
    mime_type = "text/markdown"
  }
}

resource "google_monitoring_alert_policy" "api_errors" {
  display_name = "${local.name_prefix}-api-errors"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "API 5xx Error Rate High"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      duration        = "120s"
      comparison      = "COMPARISON_GT"
      threshold_value = var.environment == "prod" ? 5 : 20

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = concat(
    [google_monitoring_notification_channel.email.name],
    var.environment == "prod" ? [google_monitoring_notification_channel.pagerduty[0].name] : []
  )

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Analytics API is returning 5xx errors at an elevated rate. Check application logs for details."
    mime_type = "text/markdown"
  }
}

# ============================================================================
# Budget Alerts
# ============================================================================

resource "google_billing_budget" "data_platform" {
  count = var.billing_account_id != "" ? 1 : 0

  billing_account = var.billing_account_id
  display_name    = "${local.name_prefix}-data-platform-budget"

  budget_filter {
    projects = ["projects/${var.project_id}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(local.budget.monthly_budget)
    }
  }

  dynamic "threshold_rules" {
    for_each = local.budget.thresholds
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  all_updates_rule {
    monitoring_notification_channels = [
      google_monitoring_notification_channel.email.name
    ]
    disable_default_iam_recipients = false
  }
}

# ============================================================================
# Dashboard
# ============================================================================

resource "google_monitoring_dashboard" "data_platform" {
  dashboard_json = jsonencode({
    displayName = "${local.name_prefix}-data-platform-dashboard"
    mosaicLayout = {
      columns = 12
      tiles = [
        {
          width  = 6
          height = 4
          widget = {
            title = "Dataflow - Elements Processed"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"dataflow_job\" AND metric.type=\"dataflow.googleapis.com/job/element_count\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                    }
                  }
                }
              }]
            }
          }
        },
        {
          xPos   = 6
          width  = 6
          height = 4
          widget = {
            title = "Dataflow - Data Watermark Lag"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"dataflow_job\" AND metric.type=\"dataflow.googleapis.com/job/data_watermark_age\""
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_MAX"
                    }
                  }
                }
              }]
            }
          }
        },
        {
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "Pub/Sub - Unacked Messages"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"pubsub_subscription\" AND metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_MAX"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["resource.labels.subscription_id"]
                    }
                  }
                }
              }]
            }
          }
        },
        {
          xPos   = 6
          yPos   = 4
          width  = 6
          height = 4
          widget = {
            title = "BigQuery - Slot Utilization"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"bigquery_project\" AND metric.type=\"bigquery.googleapis.com/slots/allocated_for_project\""
                    aggregation = {
                      alignmentPeriod  = "60s"
                      perSeriesAligner = "ALIGN_MEAN"
                    }
                  }
                }
              }]
            }
          }
        },
        {
          yPos   = 8
          width  = 6
          height = 4
          widget = {
            title = "API - Request Latency (P50/P95/P99)"
            xyChart = {
              dataSets = [
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_latencies\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_PERCENTILE_50"
                      }
                    }
                  }
                  legendTemplate = "P50"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_latencies\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_PERCENTILE_95"
                      }
                    }
                  }
                  legendTemplate = "P95"
                },
                {
                  timeSeriesQuery = {
                    timeSeriesFilter = {
                      filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_latencies\""
                      aggregation = {
                        alignmentPeriod  = "60s"
                        perSeriesAligner = "ALIGN_PERCENTILE_99"
                      }
                    }
                  }
                  legendTemplate = "P99"
                }
              ]
            }
          }
        },
        {
          xPos   = 6
          yPos   = 8
          width  = 6
          height = 4
          widget = {
            title = "API - Request Rate by Status"
            xyChart = {
              dataSets = [{
                timeSeriesQuery = {
                  timeSeriesFilter = {
                    filter = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\""
                    aggregation = {
                      alignmentPeriod    = "60s"
                      perSeriesAligner   = "ALIGN_RATE"
                      crossSeriesReducer = "REDUCE_SUM"
                      groupByFields      = ["metric.labels.response_code_class"]
                    }
                  }
                }
              }]
            }
          }
        }
      ]
    }
  })
  project = var.project_id
}

# ============================================================================
# Outputs
# ============================================================================

output "email_notification_channel" {
  description = "Email notification channel ID"
  value       = google_monitoring_notification_channel.email.name
}

output "dashboard_id" {
  description = "Monitoring dashboard ID"
  value       = google_monitoring_dashboard.data_platform.id
}

output "alert_policy_ids" {
  description = "Alert policy IDs"
  value = {
    dataflow_lag      = google_monitoring_alert_policy.dataflow_lag.name
    dataflow_errors   = google_monitoring_alert_policy.dataflow_errors.name
    pubsub_unacked    = google_monitoring_alert_policy.pubsub_unacked.name
    dlq_messages      = google_monitoring_alert_policy.dlq_messages.name
    bq_slot_util      = google_monitoring_alert_policy.bigquery_slot_utilization.name
    api_latency       = google_monitoring_alert_policy.api_latency.name
    api_errors        = google_monitoring_alert_policy.api_errors.name
  }
}
