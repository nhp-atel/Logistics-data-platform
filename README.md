# GCP Logistics Data Platform

An enterprise-grade, event-driven logistics data platform on Google Cloud Platform featuring:

- **Dual Ingestion**: Kafka + Pub/Sub event sources
- **Real-time Streaming ETL**: Dataflow/Apache Beam pipelines
- **Medallion Architecture**: Bronze/Silver/Gold data layers in GCS + BigQuery
- **Batch Orchestration**: Airflow/Cloud Composer for daily aggregations
- **Infrastructure as Code**: Terraform with dev/prod separation
- **Production-grade Testing**: Unit → Contract → Integration → E2E

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐
│     Kafka       │     │    Pub/Sub      │
│   (External)    │     │   (Native)      │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
                     ▼
         ┌───────────────────────┐
         │      Dataflow         │
         │  (Streaming ETL)      │
         │  - Normalize          │
         │  - Validate           │
         │  - Dedupe             │
         │  - Enrich             │
         │  - PII Mask           │
         └───────────┬───────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   GCS (Bronze)  │     │ BigQuery(Silver)│
│   Raw Events    │     │  Clean Events   │
└─────────────────┘     └────────┬────────┘
                                 │
                        ┌────────┴────────┐
                        │  Cloud Composer │
                        │  (Batch ETL)    │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │ BigQuery (Gold) │
                        │ Facts & Dims    │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   Cloud Run     │
                        │  Analytics API  │
                        └─────────────────┘
```

## Project Structure

```
├── terraform/           # Infrastructure as Code
│   ├── modules/         # Reusable Terraform modules
│   └── envs/            # Environment configurations (dev/prod)
├── src/                 # Python source code
│   ├── common/          # Shared utilities
│   ├── models/          # Data models (Pydantic)
│   ├── streaming/       # Dataflow pipelines
│   ├── batch/           # Airflow DAGs
│   └── api/             # FastAPI application
├── config/              # Configuration files
├── schemas/             # BigQuery table schemas
├── tests/               # Test suite
├── scripts/             # Deployment scripts
└── docker/              # Docker configurations
```

## Quick Start

### Prerequisites

- Python 3.11+
- Terraform 1.5+
- Google Cloud SDK
- Docker (for local development)

### Installation

```bash
# Clone the repository
git clone https://github.com/example/logistics-data-platform.git
cd logistics-data-platform

# Install dependencies
make install

# Run linting
make lint

# Run tests
make test
```

### Local Development

```bash
# Run API locally
make run-api-local

# Run pipeline locally with DirectRunner
make run-pipeline-direct ENV=dev
```

### Deploy to GCP

```bash
# Initialize Terraform
make terraform-init ENV=dev

# Plan changes
make terraform-plan ENV=dev

# Apply infrastructure
make terraform-apply ENV=dev

# Deploy Dataflow pipeline
make deploy-dataflow ENV=dev

# Sync DAGs to Composer
make sync-dags ENV=dev

# Deploy API
make deploy-api ENV=dev
```

## Testing

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run contract tests
make test-contract

# Run integration tests (requires GCP)
make test-integration ENV=dev

# Run e2e tests
make test-e2e ENV=dev

# Generate coverage report
make coverage
```

## Configuration

Configuration is managed through YAML files in the `config/` directory:

- `base.yaml` - Shared configuration
- `dev.yaml` - Development overrides
- `prod.yaml` - Production overrides

Environment variables can override configuration values using the pattern:
`GCP__PROJECT_ID=my-project` for nested values.

## Event Types

The platform processes the following event domains:

| Domain | Events |
|--------|--------|
| Shipment | created, updated, cancelled, in_transit, delivered, returned |
| Facility | created, updated, capacity_changed, status_changed |
| Driver | created, updated, assigned, location_updated, status_changed |
| Delivery | scheduled, started, attempted, completed, failed, rescheduled |

## Data Layers

### Bronze (GCS)
- Raw, immutable event archive
- Avro/JSON format
- Partitioned by date/hour
- Lifecycle policies for cost optimization

### Silver (BigQuery)
- Validated, deduplicated events
- Common envelope schema
- Partitioned by event_time
- Clustered by key fields

### Gold (BigQuery)
- Dimension tables (SCD Type 2)
- Fact tables (aggregated)
- ML feature tables
- Optimized for analytics queries

## Monitoring

- Cloud Monitoring dashboards
- Alert policies for SLA breaches
- Custom metrics for pipeline health
- Budget alerts for cost control

## CI/CD

- **CI**: Runs on PRs - lint, test, terraform validate
- **CD**: Runs on merge to main - deploy to dev, then prod with approval

## Contributing

1. Create a feature branch
2. Make changes
3. Run `make lint` and `make test`
4. Submit a PR

## License

MIT License - see LICENSE file for details.
