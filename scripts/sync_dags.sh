#!/bin/bash
# Sync DAGs to Cloud Composer
set -euo pipefail

# Default values
PROJECT_ID=""
ENVIRONMENT="dev"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --project)
            PROJECT_ID="$2"
            shift 2
            ;;
        --environment)
            ENVIRONMENT="$2"
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

echo "Syncing DAGs to Cloud Composer..."
echo "  Project: $PROJECT_ID"
echo "  Environment: $ENVIRONMENT"

# Get Composer environment name
COMPOSER_ENV="${ENVIRONMENT}-composer"
REGION="us-central1"

# Get the DAGs bucket from Composer
DAG_BUCKET=$(gcloud composer environments describe "$COMPOSER_ENV" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --format="value(config.dagGcsPrefix)" 2>/dev/null || echo "")

if [[ -z "$DAG_BUCKET" ]]; then
    echo "Error: Could not find Composer environment: $COMPOSER_ENV"
    echo "Make sure Cloud Composer is deployed first."
    exit 1
fi

echo "DAG bucket: $DAG_BUCKET"

# Sync DAGs
echo "Uploading DAGs..."
gsutil -m rsync -d -r src/batch/dags/ "${DAG_BUCKET}/"

# Sync utility modules
echo "Uploading utility modules..."
gsutil -m cp -r src/batch/utils/ "${DAG_BUCKET}/utils/" 2>/dev/null || true
gsutil -m cp -r src/batch/operators/ "${DAG_BUCKET}/operators/" 2>/dev/null || true

# Sync common modules needed by DAGs
echo "Uploading common modules..."
gsutil -m cp -r src/common/ "${DAG_BUCKET}/common/" 2>/dev/null || true

# Upload requirements if exists
if [[ -f "requirements-airflow.txt" ]]; then
    echo "Uploading requirements..."
    gsutil cp requirements-airflow.txt "${DAG_BUCKET}/../requirements.txt"
fi

echo "DAG sync completed!"
echo "View DAGs at: https://console.cloud.google.com/composer/environments/detail/${REGION}/${COMPOSER_ENV}/dags?project=${PROJECT_ID}"

# List synced DAGs
echo ""
echo "Synced DAGs:"
gsutil ls "${DAG_BUCKET}/*.py" 2>/dev/null | xargs -I {} basename {} || echo "No DAGs found"
