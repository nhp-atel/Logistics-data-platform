#!/bin/bash
# Deploy Dataflow Flex Template
set -euo pipefail

# Default values
PROJECT_ID=""
REGION="us-central1"
ENVIRONMENT="dev"
IMAGE=""
JOB_NAME="logistics-streaming-pipeline"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project)
            PROJECT_ID="$2"
            shift 2
            ;;
        --region)
            REGION="$2"
            shift 2
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --image)
            IMAGE="$2"
            shift 2
            ;;
        --job-name)
            JOB_NAME="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$PROJECT_ID" ]]; then
    echo "Error: --project is required"
    exit 1
fi

# Set image default if not provided
if [[ -z "$IMAGE" ]]; then
    IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ENVIRONMENT}-dataflow/logistics-pipeline:latest"
fi

echo "Deploying Dataflow pipeline..."
echo "  Project: $PROJECT_ID"
echo "  Region: $REGION"
echo "  Environment: $ENVIRONMENT"
echo "  Image: $IMAGE"
echo "  Job Name: $JOB_NAME"

# Get service account
SERVICE_ACCOUNT="${ENVIRONMENT}-dataflow-worker@${PROJECT_ID}.iam.gserviceaccount.com"

# Get bucket names
TEMP_BUCKET="${PROJECT_ID}-${ENVIRONMENT}-dataflow-temp"
STAGING_BUCKET="${PROJECT_ID}-${ENVIRONMENT}-dataflow-staging"

# Build Flex Template spec
TEMPLATE_SPEC_PATH="gs://${PROJECT_ID}-${ENVIRONMENT}-flex-templates/templates/logistics-streaming-pipeline/spec.json"

# Create template spec
cat > /tmp/flex_template_spec.json <<EOF
{
  "image": "${IMAGE}",
  "sdkInfo": {
    "language": "PYTHON"
  },
  "metadata": {
    "name": "logistics-streaming-pipeline",
    "description": "Streaming ETL pipeline for logistics events",
    "parameters": [
      {
        "name": "input_subscription",
        "label": "Input Subscription",
        "helpText": "Pub/Sub subscription to read from",
        "isOptional": false
      },
      {
        "name": "output_table",
        "label": "Output Table",
        "helpText": "BigQuery table for output",
        "isOptional": false
      },
      {
        "name": "raw_bucket",
        "label": "Raw Bucket",
        "helpText": "GCS bucket for raw data",
        "isOptional": false
      },
      {
        "name": "dlq_topic",
        "label": "DLQ Topic",
        "helpText": "Pub/Sub topic for DLQ",
        "isOptional": false
      }
    ]
  }
}
EOF

# Upload template spec
gsutil cp /tmp/flex_template_spec.json "$TEMPLATE_SPEC_PATH"

# Set environment-specific parameters
if [[ "$ENVIRONMENT" == "prod" ]]; then
    MAX_WORKERS=20
    NUM_WORKERS=3
    MACHINE_TYPE="n1-standard-4"
else
    MAX_WORKERS=3
    NUM_WORKERS=1
    MACHINE_TYPE="n1-standard-2"
fi

# Check if job already exists and is running
EXISTING_JOB=$(gcloud dataflow jobs list \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --filter="name:${ENVIRONMENT}-${JOB_NAME} AND state:Running" \
    --format="value(id)" 2>/dev/null || echo "")

if [[ -n "$EXISTING_JOB" ]]; then
    echo "Found existing running job: $EXISTING_JOB"
    echo "Updating job with new pipeline..."

    # For streaming jobs, we need to drain and replace
    gcloud dataflow jobs drain "$EXISTING_JOB" \
        --project="$PROJECT_ID" \
        --region="$REGION"

    echo "Waiting for job to drain..."
    sleep 60
fi

# Run the Flex Template job
gcloud dataflow flex-template run "${ENVIRONMENT}-${JOB_NAME}" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --template-file-gcs-location="$TEMPLATE_SPEC_PATH" \
    --service-account-email="$SERVICE_ACCOUNT" \
    --temp-location="gs://${TEMP_BUCKET}/temp" \
    --staging-location="gs://${STAGING_BUCKET}/staging" \
    --max-workers="$MAX_WORKERS" \
    --num-workers="$NUM_WORKERS" \
    --worker-machine-type="$MACHINE_TYPE" \
    --enable-streaming-engine \
    --parameters="input_subscription=projects/${PROJECT_ID}/subscriptions/${ENVIRONMENT}-unified-events-dataflow" \
    --parameters="output_table=${PROJECT_ID}:${ENVIRONMENT}_clean.shipment_events" \
    --parameters="raw_bucket=${PROJECT_ID}-${ENVIRONMENT}-raw" \
    --parameters="dlq_topic=projects/${PROJECT_ID}/topics/${ENVIRONMENT}-unified-events-dlq" \
    --parameters="environment=${ENVIRONMENT}"

echo "Dataflow job submitted successfully!"
echo "View job at: https://console.cloud.google.com/dataflow/jobs/${REGION}?project=${PROJECT_ID}"
