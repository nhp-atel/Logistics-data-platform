# GCP Logistics Data Platform

## Complete Technical Documentation

An enterprise-grade, event-driven logistics data platform on Google Cloud Platform that processes package tracking events from ingestion to analytics-ready data marts.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Data Flow: End-to-End Journey](#data-flow-end-to-end-journey)
4. [Project Structure](#project-structure)
5. [Detailed File Reference](#detailed-file-reference)
6. [Infrastructure (Terraform)](#infrastructure-terraform)
7. [Streaming Pipeline (Python/Apache Beam)](#streaming-pipeline-pythonapache-beam)
8. [Batch Processing (Airflow/SQL)](#batch-processing-airflowsql)
9. [Analytics API (FastAPI)](#analytics-api-fastapi)
10. [Containerization (Docker)](#containerization-docker)
11. [Data Layers Explained](#data-layers-explained)
12. [Deployment Flow](#deployment-flow)
13. [Quick Start](#quick-start)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              DATA SOURCES (External)                                 │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   ┌─────────────────────┐              ┌─────────────────────┐                      │
│   │   Kafka Cluster     │              │   Google Pub/Sub    │                      │
│   │   (External Apps)   │              │   (GCP Native)      │                      │
│   │                     │              │                     │                      │
│   │ • Shipment events   │              │ • Facility events   │                      │
│   │ • Driver updates    │              │ • Delivery events   │                      │
│   └──────────┬──────────┘              └──────────┬──────────┘                      │
│              │                                    │                                  │
└──────────────┼────────────────────────────────────┼──────────────────────────────────┘
               │                                    │
               └────────────────┬───────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         STREAMING ETL (Google Dataflow)                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                      │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                        Apache Beam Pipeline                                  │   │
│   │                        (src/streaming/pipeline.py)                           │   │
│   │                                                                              │   │
│   │   ┌─────────┐   ┌──────────┐   ┌────────┐   ┌────────┐   ┌───────┐          │   │
│   │   │ Sources │ → │Normalize │ → │Validate│ → │ Dedupe │ → │Enrich │          │   │
│   │   └─────────┘   └──────────┘   └────────┘   └────────┘   └───────┘          │   │
│   │        │                            │                          │             │   │
│   │        │                            ▼                          │             │   │
│   │   kafka_source.py           ┌──────────────┐                   │             │   │
│   │   pubsub_source.py          │  Dead Letter │                   │             │   │
│   │                             │    Queue     │                   │             │   │
│   │                             └──────────────┘                   │             │   │
│   │                                                                │             │   │
│   │                                         ┌──────────────────────┘             │   │
│   │                                         │                                    │   │
│   │                                         ▼                                    │   │
│   │                                   ┌───────────┐                              │   │
│   │                                   │ PII Mask  │                              │   │
│   │                                   └─────┬─────┘                              │   │
│   │                                         │                                    │   │
│   │                          ┌──────────────┴──────────────┐                     │   │
│   │                          │                             │                     │   │
│   │                          ▼                             ▼                     │   │
│   │                   ┌─────────────┐              ┌─────────────┐               │   │
│   │                   │  GCS Sink   │              │   BQ Sink   │               │   │
│   │                   │  (Bronze)   │              │  (Silver)   │               │   │
│   │                   └─────────────┘              └─────────────┘               │   │
│   │                                                                              │   │
│   └──────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└─────────────────────────────────────────────────────────────────────────────────────┘
               │                                    │
               ▼                                    ▼
┌──────────────────────────────┐    ┌──────────────────────────────────────────────────┐
│      BRONZE LAYER (GCS)      │    │              SILVER LAYER (BigQuery)             │
├──────────────────────────────┤    ├──────────────────────────────────────────────────┤
│                              │    │                                                  │
│  gs://project-raw-env/       │    │  Dataset: {env}_clean                            │
│  └── events/                 │    │  ├── shipment_events                             │
│      └── 2024/01/15/10/      │    │  ├── facility_events                             │
│          └── events.avro     │    │  ├── driver_events                               │
│                              │    │  └── delivery_events                             │
│  • Raw, immutable            │    │                                                  │
│  • Partitioned by date/hour  │    │  • Validated & deduplicated                      │
│  • Avro format               │    │  • Partitioned by event_time                     │
│  • Lifecycle: 90d → Coldline │    │  • Clustered by key fields                       │
│                              │    │                                                  │
└──────────────────────────────┘    └───────────────────────┬──────────────────────────┘
                                                            │
                                                            ▼
                               ┌────────────────────────────────────────────────────────┐
                               │            BATCH PROCESSING (Cloud Composer)          │
                               ├────────────────────────────────────────────────────────┤
                               │                                                        │
                               │   ┌─────────────────────────────────────────────────┐  │
                               │   │              Airflow DAGs                        │  │
                               │   │              (src/batch/dags/)                   │  │
                               │   │                                                  │  │
                               │   │   ┌─────────────────┐  Schedule: Daily 6 AM     │  │
                               │   │   │  marts_daily.py │ ─────────────────────────▶│  │
                               │   │   └─────────────────┘                           │  │
                               │   │           │                                      │  │
                               │   │           │ Executes SQL transformations        │  │
                               │   │           │ (schemas/curated/*.json)            │  │
                               │   │           ▼                                      │  │
                               │   │   ┌─────────────────┐  Schedule: Every 4 hours  │  │
                               │   │   │reconciliation.py│ ─────────────────────────▶│  │
                               │   │   └─────────────────┘                           │  │
                               │   │           │                                      │  │
                               │   │           │ Handles late-arriving data          │  │
                               │   │           ▼                                      │  │
                               │   │   ┌─────────────────┐  Schedule: Every 15 min   │  │
                               │   │   │sla_monitoring.py│ ─────────────────────────▶│  │
                               │   │   └─────────────────┘                           │  │
                               │   │                                                  │  │
                               │   └─────────────────────────────────────────────────┘  │
                               │                                                        │
                               └────────────────────────────┬───────────────────────────┘
                                                            │
                                                            ▼
                               ┌────────────────────────────────────────────────────────┐
                               │                GOLD LAYER (BigQuery)                   │
                               ├────────────────────────────────────────────────────────┤
                               │                                                        │
                               │   Dataset: {env}_curated                               │
                               │   ├── dim_facility      (SCD Type 2 dimension)        │
                               │   ├── dim_carrier       (SCD Type 2 dimension)        │
                               │   ├── dim_driver        (SCD Type 2 dimension)        │
                               │   ├── fact_deliveries   (Daily aggregated facts)      │
                               │   └── fact_shipments    (Daily aggregated facts)      │
                               │                                                        │
                               │   Dataset: {env}_features                              │
                               │   └── ml_delivery_features (ML feature store)         │
                               │                                                        │
                               └────────────────────────────┬───────────────────────────┘
                                                            │
                                                            ▼
                               ┌────────────────────────────────────────────────────────┐
                               │              ANALYTICS API (Cloud Run)                 │
                               ├────────────────────────────────────────────────────────┤
                               │                                                        │
                               │   ┌─────────────────────────────────────────────────┐  │
                               │   │              FastAPI Application                 │  │
                               │   │              (src/api/main.py)                   │  │
                               │   │                                                  │  │
                               │   │   Endpoints:                                     │  │
                               │   │   GET /api/v1/shipments/{id}/timeline           │  │
                               │   │   GET /api/v1/facilities/{id}/metrics           │  │
                               │   │   GET /api/v1/analytics/delivery-performance    │  │
                               │   │   GET /health                                    │  │
                               │   │                                                  │  │
                               │   │   Reads from: {env}_curated, {env}_features     │  │
                               │   │                                                  │  │
                               │   └─────────────────────────────────────────────────┘  │
                               │                                                        │
                               └────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Where Each Technology Fits

| Technology | Purpose | Files/Directories |
|------------|---------|-------------------|
| **Terraform** | Infrastructure provisioning (GCP resources) | `terraform/` |
| **Python** | Business logic, streaming ETL, batch jobs, API | `src/` |
| **Apache Beam** | Distributed stream processing framework | `src/streaming/` |
| **SQL** | Data transformations, aggregations, analytics | `schemas/`, DAG SQL templates |
| **Docker** | Containerization for Dataflow and Cloud Run | `docker/` |
| **Airflow** | Workflow orchestration for batch jobs | `src/batch/dags/` |
| **FastAPI** | REST API framework | `src/api/` |
| **JSON Schema** | Event contract validation | `config/event_schemas/` |
| **YAML** | Configuration management | `config/*.yaml` |

---

## Data Flow: End-to-End Journey

### Step-by-Step Data Journey

```
STEP 1: EVENT GENERATION
────────────────────────
External systems generate events:
• Warehouse management system → "shipment.created"
• GPS tracking system → "driver.location_updated"
• Delivery app → "delivery.completed"

                    │
                    ▼

STEP 2: EVENT INGESTION
────────────────────────
Events enter through two channels:

┌─────────────────────────────────────────────────────────────────┐
│ Kafka (External)                │ Pub/Sub (GCP Native)          │
│ ─────────────────               │ ────────────────────          │
│ • Legacy systems                │ • New GCP-native apps         │
│ • Third-party integrations      │ • Internal microservices      │
│ • High-volume producers         │ • Cloud Functions triggers    │
│                                 │                               │
│ File: src/streaming/sources/    │ File: src/streaming/sources/  │
│        kafka_source.py          │        pubsub_source.py       │
└─────────────────────────────────────────────────────────────────┘

                    │
                    ▼

STEP 3: STREAMING ETL (Dataflow)
─────────────────────────────────
Real-time processing with Apache Beam:

┌─────────────────────────────────────────────────────────────────┐
│ TRANSFORM              │ FILE                    │ PURPOSE      │
│ ─────────────────────  │ ─────────────────────── │ ──────────── │
│ 1. Normalize           │ transforms/normalize.py │ Convert to   │
│                        │                         │ common       │
│                        │                         │ envelope     │
│ ─────────────────────  │ ─────────────────────── │ ──────────── │
│ 2. Validate            │ transforms/validate.py  │ Check schema │
│                        │                         │ compliance   │
│ ─────────────────────  │ ─────────────────────── │ ──────────── │
│ 3. Deduplicate         │ transforms/dedupe.py    │ Remove       │
│                        │                         │ duplicates   │
│ ─────────────────────  │ ─────────────────────── │ ──────────── │
│ 4. Enrich              │ transforms/enrich.py    │ Add lookup   │
│                        │                         │ data         │
│ ─────────────────────  │ ─────────────────────── │ ──────────── │
│ 5. PII Mask            │ transforms/pii.py       │ Protect      │
│                        │                         │ sensitive    │
│                        │                         │ data         │
│ ─────────────────────  │ ─────────────────────── │ ──────────── │
│ 6. Route               │ transforms/route.py     │ Direct to    │
│                        │                         │ sinks/DLQ    │
└─────────────────────────────────────────────────────────────────┘

                    │
          ┌─────────┴─────────┐
          ▼                   ▼

STEP 4: DATA LANDING
────────────────────
Events land in two locations simultaneously:

┌───────────────────────────┐  ┌───────────────────────────────────┐
│ BRONZE (GCS)              │  │ SILVER (BigQuery)                 │
│ ───────────               │  │ ───────────────                   │
│ File: sinks/gcs_sink.py   │  │ File: sinks/bq_sink.py            │
│                           │  │                                   │
│ Purpose:                  │  │ Purpose:                          │
│ • Raw archive             │  │ • Query-ready events              │
│ • Disaster recovery       │  │ • Real-time dashboards            │
│ • Reprocessing source     │  │ • Ad-hoc analysis                 │
│                           │  │                                   │
│ Format: Avro              │  │ Format: Structured tables         │
│ Retention: 1 year         │  │ Retention: 90 days                │
└───────────────────────────┘  └───────────────────────────────────┘

                    │
                    ▼

STEP 5: BATCH AGGREGATION (Airflow)
────────────────────────────────────
Daily jobs transform Silver → Gold:

┌─────────────────────────────────────────────────────────────────┐
│ DAG                    │ SCHEDULE      │ PURPOSE                │
│ ─────────────────────  │ ───────────── │ ────────────────────── │
│ marts_daily.py         │ Daily 6 AM    │ Build fact tables      │
│                        │               │ Build dimensions       │
│                        │               │ Aggregate metrics      │
│ ─────────────────────  │ ───────────── │ ────────────────────── │
│ reconciliation.py      │ Every 4 hours │ Handle late arrivals   │
│                        │               │ Rebuild partitions     │
│ ─────────────────────  │ ───────────── │ ────────────────────── │
│ sla_monitoring.py      │ Every 15 min  │ Check pipeline health  │
│                        │               │ Alert on breaches      │
└─────────────────────────────────────────────────────────────────┘

                    │
                    ▼

STEP 6: ANALYTICS SERVING
─────────────────────────
Gold layer serves multiple consumers:

┌─────────────────────────────────────────────────────────────────┐
│ CONSUMER               │ ACCESS METHOD    │ DATA SOURCE         │
│ ─────────────────────  │ ──────────────── │ ─────────────────── │
│ BI Dashboards          │ Direct BigQuery  │ curated.fact_*      │
│ (Looker, Tableau)      │ connection       │ curated.dim_*       │
│ ─────────────────────  │ ──────────────── │ ─────────────────── │
│ Internal Apps          │ REST API         │ Analytics API       │
│                        │ (src/api/)       │ (Cloud Run)         │
│ ─────────────────────  │ ──────────────── │ ─────────────────── │
│ ML Models              │ BigQuery ML /    │ features.*          │
│                        │ Vertex AI        │                     │
│ ─────────────────────  │ ──────────────── │ ─────────────────── │
│ Data Science           │ Jupyter / Colab  │ All datasets        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
Data Engineering/
│
├── terraform/                          # INFRASTRUCTURE AS CODE
│   ├── modules/                        # Reusable Terraform modules
│   │   ├── networking/main.tf          # VPC, subnets, firewall rules
│   │   ├── iam/main.tf                 # Service accounts, IAM bindings
│   │   ├── pubsub/main.tf              # Topics, subscriptions, DLQs
│   │   ├── gcs/main.tf                 # Storage buckets, lifecycle policies
│   │   ├── bigquery/main.tf            # Datasets, tables, views
│   │   ├── dataflow/main.tf            # Flex template configuration
│   │   ├── composer/main.tf            # Cloud Composer (Airflow)
│   │   ├── cloud-run/main.tf           # API hosting
│   │   ├── kafka/main.tf               # Kafka connectivity
│   │   ├── monitoring/main.tf          # Alerts, dashboards, budgets
│   │   └── secret-manager/main.tf      # Secrets storage
│   │
│   └── envs/                           # Environment-specific configurations
│       ├── dev/main.tf                 # Development environment
│       └── prod/main.tf                # Production environment
│
├── src/                                # PYTHON SOURCE CODE
│   ├── common/                         # Shared utilities
│   │   ├── config_loader.py            # Loads YAML config + env vars
│   │   ├── logging_utils.py            # Structured JSON logging
│   │   ├── metrics.py                  # Cloud Monitoring metrics
│   │   └── schemas.py                  # Event envelope definition
│   │
│   ├── models/                         # Data models (Pydantic)
│   │   └── events/                     # Event type definitions
│   │       ├── base.py                 # BaseEvent, Address, GeoLocation
│   │       ├── shipment.py             # ShipmentCreated, ShipmentDelivered
│   │       ├── facility.py             # FacilityCreated, CapacityChanged
│   │       ├── driver.py               # DriverCreated, LocationUpdated
│   │       └── delivery.py             # DeliveryScheduled, DeliveryCompleted
│   │
│   ├── streaming/                      # DATAFLOW PIPELINE
│   │   ├── pipeline.py                 # Main pipeline orchestration
│   │   ├── sources/                    # Data ingestion
│   │   │   ├── kafka_source.py         # Read from Kafka
│   │   │   └── pubsub_source.py        # Read from Pub/Sub
│   │   ├── transforms/                 # Processing steps
│   │   │   ├── normalize.py            # Convert to common envelope
│   │   │   ├── validate.py             # Schema validation
│   │   │   ├── dedupe.py               # Stateful deduplication
│   │   │   ├── enrich.py               # Side input enrichment
│   │   │   ├── pii.py                  # PII masking/tokenization
│   │   │   └── route.py                # DLQ routing
│   │   ├── sinks/                      # Data output
│   │   │   ├── gcs_sink.py             # Write to GCS (Bronze)
│   │   │   └── bq_sink.py              # Write to BigQuery (Silver)
│   │   └── windows/                    # Windowing strategies
│   │       └── tumbling.py             # Tumbling window with late data
│   │
│   ├── batch/                          # AIRFLOW DAGS
│   │   └── dags/
│   │       ├── marts_daily.py          # Daily Gold layer builds
│   │       ├── reconciliation.py       # Late data handling
│   │       └── sla_monitoring.py       # Pipeline health checks
│   │
│   └── api/                            # ANALYTICS API
│       ├── main.py                     # FastAPI application
│       ├── routers/                    # API endpoints
│       │   ├── shipments.py            # Shipment endpoints
│       │   ├── facilities.py           # Facility endpoints
│       │   └── metrics.py              # Metrics endpoints
│       └── services/
│           └── bigquery_service.py     # BigQuery client wrapper
│
├── config/                             # CONFIGURATION
│   ├── base.yaml                       # Shared settings
│   ├── dev.yaml                        # Development overrides
│   ├── prod.yaml                       # Production settings
│   ├── pii_config.yaml                 # PII field definitions
│   └── event_schemas/                  # JSON Schema per event type
│       ├── shipment.created.json       # Shipment event schema
│       └── delivery.completed.json     # Delivery event schema
│
├── schemas/                            # BIGQUERY TABLE SCHEMAS
│   ├── clean/                          # Silver layer
│   │   └── shipment_events.json        # Clean events table
│   └── curated/                        # Gold layer
│       ├── fact_deliveries.json        # Delivery facts
│       └── dim_facility.json           # Facility dimension
│
├── tests/                              # TEST SUITE
│   ├── conftest.py                     # Shared fixtures
│   ├── unit/                           # Unit tests
│   │   ├── transforms/                 # Beam transform tests
│   │   ├── dags/                       # DAG import tests
│   │   └── api/                        # API tests
│   ├── contract/                       # Schema contract tests
│   ├── integration/                    # Integration tests
│   └── e2e/                            # End-to-end tests
│
├── scripts/                            # DEPLOYMENT SCRIPTS
│   ├── deploy_dataflow.sh              # Deploy streaming pipeline
│   ├── sync_dags.sh                    # Sync DAGs to Composer
│   └── run_tests.sh                    # Run test suite
│
├── docker/                             # CONTAINER DEFINITIONS
│   ├── Dockerfile.dataflow             # Dataflow Flex Template
│   ├── Dockerfile.api                  # Cloud Run API
│   └── entrypoint-dataflow.sh          # Pipeline entrypoint
│
├── .github/workflows/                  # CI/CD PIPELINES
│   ├── ci.yaml                         # PR validation
│   └── cd.yaml                         # Deployment automation
│
├── pyproject.toml                      # Python dependencies
├── Makefile                            # Build commands
└── README.md                           # This file
```

---

## Detailed File Reference

### Infrastructure (Terraform)

#### `terraform/modules/networking/main.tf`
**Purpose:** Creates the network foundation for all GCP resources.

**What it provisions:**
- VPC network with custom subnets
- Cloud NAT for outbound internet access
- Firewall rules for internal communication
- Private Google Access for GCP services

**Inputs:**
- Project ID, region, environment
- CIDR ranges for subnets

**Outputs:**
- VPC ID, subnet IDs
- Used by: Dataflow, Composer, Cloud Run

---

#### `terraform/modules/iam/main.tf`
**Purpose:** Creates service accounts with least-privilege permissions.

**Service accounts created:**

| Account | Used By | Permissions |
|---------|---------|-------------|
| `dataflow-worker` | Streaming pipeline | Pub/Sub subscriber, GCS writer, BQ data editor |
| `composer-worker` | Airflow DAGs | BQ job user, Dataflow developer |
| `analytics-api` | Cloud Run API | BQ data viewer (read-only) |

**Why it matters:** Follows principle of least privilege - each component can only access what it needs.

---

#### `terraform/modules/pubsub/main.tf`
**Purpose:** Creates event ingestion infrastructure.

**What it provisions:**
- Main topics: `shipment-events`, `facility-events`, `driver-events`, `delivery-events`
- Subscriptions with acknowledgment deadlines
- Dead letter topics for failed messages
- Retry policies

**Data flow:**
```
Producer → Topic → Subscription → Dataflow Pipeline
                        ↓ (on failure)
                   DLQ Topic → Alerting
```

---

#### `terraform/modules/gcs/main.tf`
**Purpose:** Creates storage buckets for the Bronze layer.

**Buckets:**
- `{project}-raw-{env}`: Bronze layer (raw events)
- `{project}-dataflow-temp-{env}`: Dataflow staging
- `{project}-composer-{env}`: Airflow DAGs

**Lifecycle policies:**
```
Standard → Nearline (30 days) → Coldline (90 days) → Archive (365 days)
```

---

#### `terraform/modules/bigquery/main.tf`
**Purpose:** Creates data warehouse structure.

**Datasets:**

| Dataset | Layer | Purpose |
|---------|-------|---------|
| `{env}_raw` | Bronze | Raw event backup |
| `{env}_clean` | Silver | Validated, deduplicated events |
| `{env}_curated` | Gold | Business-ready facts and dimensions |
| `{env}_features` | Gold | ML feature store |

**Tables created:** Uses schemas from `schemas/` directory.

---

#### `terraform/modules/dataflow/main.tf`
**Purpose:** Configures Dataflow Flex Template infrastructure.

**What it provisions:**
- Artifact Registry for Docker images
- Flex Template metadata in GCS
- Dataflow job configuration

---

#### `terraform/modules/composer/main.tf`
**Purpose:** Creates Cloud Composer (managed Airflow) environment.

**Configuration:**
- Composer 2 environment
- Auto-scaling workers
- PyPI packages for DAGs
- Environment variables

---

#### `terraform/modules/cloud-run/main.tf`
**Purpose:** Deploys the Analytics API.

**Configuration:**
- Container from Artifact Registry
- Auto-scaling (0-10 instances)
- VPC connector for BigQuery access
- IAM authentication

---

#### `terraform/modules/monitoring/main.tf`
**Purpose:** Creates observability infrastructure.

**What it provisions:**
- Budget alerts (cost control)
- Pipeline lag alerts
- Error rate alerts
- Custom dashboards

---

#### `terraform/envs/dev/main.tf` and `terraform/envs/prod/main.tf`
**Purpose:** Compose all modules for each environment.

**Key differences:**

| Setting | Dev | Prod |
|---------|-----|------|
| Dataflow workers | 1-3 | 5-20 |
| BQ retention | 30 days | 90 days |
| Composer size | Small | Medium |
| Budget alert | $500 | $5000 |

---

### Streaming Pipeline (Python/Apache Beam)

#### `src/streaming/pipeline.py`
**Purpose:** Main orchestrator that wires all transforms together.

**Data flow:**
```python
# Simplified pipeline structure
events = (
    pipeline
    | 'ReadKafka' >> ReadFromKafka(...)
    | 'ReadPubSub' >> ReadFromPubSub(...)
    | 'Flatten' >> beam.Flatten()
    | 'Normalize' >> beam.ParDo(NormalizeToEnvelope())
    | 'Validate' >> beam.ParDo(ValidateSchema())
    | 'Dedupe' >> beam.ParDo(StatefulDedupeDoFn())
    | 'Enrich' >> beam.ParDo(EnrichWithSideInputs(), dim_table=side_input)
    | 'MaskPII' >> beam.ParDo(MaskPII())
)

# Branch to two sinks
events | 'WriteGCS' >> WriteToGCS(...)
events | 'WriteBQ' >> WriteToBigQuery(...)
```

**Inputs:** Kafka topics, Pub/Sub subscriptions
**Outputs:** GCS (Bronze), BigQuery (Silver)

---

#### `src/streaming/sources/kafka_source.py`
**Purpose:** Reads events from external Kafka cluster.

**Key features:**
- SASL_SSL authentication
- Consumer group management
- Offset tracking

**Configuration from `config/base.yaml`:**
```yaml
kafka:
  bootstrap_servers: "kafka-cluster:9093"
  topics:
    - shipment-events
    - driver-events
  consumer_group: "logistics-dataflow"
```

---

#### `src/streaming/sources/pubsub_source.py`
**Purpose:** Reads events from GCP Pub/Sub.

**Key features:**
- Automatic acknowledgment
- Message attribute extraction
- Timestamp parsing

---

#### `src/streaming/transforms/normalize.py`
**Purpose:** Converts raw events from different sources into a common envelope format.

**Input:** Raw JSON/Avro from Kafka or Pub/Sub
**Output:** `EventEnvelope` dataclass

```python
# Example transformation
Raw input:
{
    "shipmentId": "SHP-123",
    "status": "created",
    "timestamp": "2024-01-15T10:30:00Z"
}

Normalized output (EventEnvelope):
{
    "event_id": "uuid-generated",
    "event_type": "shipment.created",
    "event_version": "v1",
    "event_time": "2024-01-15T10:30:00Z",
    "ingest_time": "2024-01-15T10:30:05Z",
    "source_system": "kafka",
    "trace_id": "trace-abc",
    "payload": { ... original data ... }
}
```

---

#### `src/streaming/transforms/validate.py`
**Purpose:** Validates events against JSON Schema contracts.

**How it works:**
1. Looks up schema based on `event_type` and `event_version`
2. Validates payload against schema
3. Routes invalid events to DLQ

**Schema location:** `config/event_schemas/{event_type}.json`

**Output:** Two PCollections
- `valid`: Events that pass validation
- `invalid`: Events that fail (sent to DLQ)

---

#### `src/streaming/transforms/dedupe.py`
**Purpose:** Removes duplicate events using stateful processing.

**How it works:**
```python
class StatefulDedupeDoFn(DoFn):
    SEEN_STATE = BagStateSpec('seen', StrUtf8Coder())

    def process(self, element, seen=DoFn.StateParam(SEEN_STATE)):
        event_id = element.event_id
        seen_ids = list(seen.read())

        if event_id not in seen_ids:
            seen.add(event_id)
            yield element
        # Duplicates are silently dropped
```

**State TTL:** 24 hours (configurable)
**Why needed:** Kafka/Pub/Sub can deliver duplicates during retries

---

#### `src/streaming/transforms/enrich.py`
**Purpose:** Adds reference data to events using side inputs.

**Example enrichment:**
```python
# Input event
{"facility_id": "FAC-001", ...}

# After enrichment (side input from dim_facility)
{
    "facility_id": "FAC-001",
    "facility_name": "Chicago Distribution Center",
    "facility_region": "MIDWEST",
    ...
}
```

**Side input source:** BigQuery dimension tables (refreshed hourly)

---

#### `src/streaming/transforms/pii.py`
**Purpose:** Protects personally identifiable information.

**Two modes:**
1. **Tokenization:** Reversible encryption for internal use
2. **Masking:** Irreversible for analytics

**Fields configured in `config/pii_config.yaml`:**
```yaml
pii_fields:
  - field_path: "customer.email"
    strategy: "mask"
    pattern: "email"
  - field_path: "customer.phone"
    strategy: "tokenize"
  - field_path: "customer.ssn"
    strategy: "mask"
    pattern: "ssn"
```

**Example:**
```python
# Before
{"customer": {"email": "john@example.com", "phone": "555-1234"}}

# After (masked)
{"customer": {"email": "j***@e*****.com", "phone": "TOKEN:abc123"}}
```

---

#### `src/streaming/transforms/route.py`
**Purpose:** Routes events to appropriate destinations.

**Routing logic:**
- Valid events → GCS + BigQuery
- Invalid events → DLQ topic
- Specific event types → Additional topics (e.g., alerts)

---

#### `src/streaming/sinks/gcs_sink.py`
**Purpose:** Writes events to GCS (Bronze layer).

**Output format:** Avro files
**Partitioning:** `gs://bucket/events/{year}/{month}/{day}/{hour}/`
**File naming:** `events-{window_start}-{shard}.avro`

---

#### `src/streaming/sinks/bq_sink.py`
**Purpose:** Writes events to BigQuery (Silver layer).

**Features:**
- Streaming inserts (real-time)
- Automatic schema detection
- Failed rows to error table

**Table routing:**
```python
event_type → table mapping:
"shipment.*" → clean.shipment_events
"facility.*" → clean.facility_events
"driver.*" → clean.driver_events
"delivery.*" → clean.delivery_events
```

---

#### `src/streaming/windows/tumbling.py`
**Purpose:** Applies windowing for time-based aggregations.

**Configuration:**
- Window size: 5 minutes
- Allowed lateness: 24 hours
- Trigger: AfterWatermark with early firings

```python
events | WindowInto(
    FixedWindows(5 * 60),  # 5 minutes
    trigger=AfterWatermark(
        early=AfterProcessingTime(60),  # Fire every minute
        late=AfterCount(1)  # Fire on each late element
    ),
    allowed_lateness=Duration(seconds=86400),  # 24 hours
    accumulation_mode=AccumulationMode.ACCUMULATING
)
```

---

### Batch Processing (Airflow/SQL)

#### `src/batch/dags/marts_daily.py`
**Purpose:** Builds Gold layer tables from Silver layer.

**Schedule:** Daily at 6 AM UTC

**Tasks:**
```
check_source_ready → build_dim_facility → build_dim_carrier
                  → build_fact_deliveries → run_data_quality → notify_complete
```

**SQL transformations (embedded in DAG):**
```sql
-- Build fact_deliveries from clean events
INSERT INTO curated.fact_deliveries
SELECT
    de.delivery_id,
    de.shipment_id,
    DATE(de.event_time) as delivery_date,
    de.payload.facility_id,
    de.payload.driver_id,
    c.carrier_id,
    de.payload.status,
    de.event_time as delivery_time,
    fa.first_attempt_time,
    fa.attempt_count,
    de.event_time <= se.expected_delivery as on_time_flag
FROM clean.delivery_events de
LEFT JOIN (
    SELECT delivery_id, MIN(event_time) as first_attempt_time, COUNT(*) as attempt_count
    FROM clean.delivery_events
    WHERE event_type = 'delivery.attempted'
    GROUP BY delivery_id
) fa ON de.delivery_id = fa.delivery_id
LEFT JOIN clean.shipment_events se ON de.shipment_id = se.shipment_id
LEFT JOIN curated.dim_carrier c ON de.payload.carrier_code = c.carrier_code
WHERE de.event_type = 'delivery.completed'
  AND DATE(de.event_time) = '{{ ds }}'
```

---

#### `src/batch/dags/reconciliation.py`
**Purpose:** Handles late-arriving data.

**Schedule:** Every 4 hours

**How it works:**
1. Identifies partitions with late arrivals
2. Rebuilds affected Gold layer partitions
3. Updates data quality metrics

---

#### `src/batch/dags/sla_monitoring.py`
**Purpose:** Monitors pipeline health and SLA compliance.

**Schedule:** Every 15 minutes

**Checks:**
- Pipeline lag (events behind real-time)
- Error rates (DLQ volume)
- Data freshness (last event time)
- Delivery SLA compliance

**Alerts:** Sends to PagerDuty on SLA breach

---

### Analytics API (FastAPI)

#### `src/api/main.py`
**Purpose:** REST API for analytics consumers.

**Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check for load balancer |
| `/api/v1/shipments/{id}/timeline` | GET | Event history for a shipment |
| `/api/v1/facilities/{id}/metrics` | GET | Facility performance metrics |
| `/api/v1/analytics/delivery-performance` | GET | Delivery KPIs |

**Example response:**
```json
GET /api/v1/shipments/SHP-123/timeline

{
    "shipment_id": "SHP-123",
    "events": [
        {"event_type": "shipment.created", "time": "2024-01-15T08:00:00Z"},
        {"event_type": "shipment.in_transit", "time": "2024-01-15T10:30:00Z"},
        {"event_type": "delivery.completed", "time": "2024-01-15T14:22:00Z"}
    ],
    "current_status": "delivered",
    "total_transit_hours": 6.37
}
```

---

#### `src/api/services/bigquery_service.py`
**Purpose:** Wrapper for BigQuery queries.

**Features:**
- Connection pooling
- Query caching (5 minute TTL)
- Parameterized queries (SQL injection prevention)
- Timeout handling

---

### Configuration Files

#### `config/base.yaml`
**Purpose:** Shared configuration across all environments.

```yaml
gcp:
  project_id: "${GCP_PROJECT_ID}"
  region: "us-central1"

pubsub:
  topics:
    shipment: "shipment-events"
    facility: "facility-events"
    dlq: "events-dlq"

bigquery:
  datasets:
    raw: "raw"
    clean: "clean"
    curated: "curated"

pipeline:
  window_size_seconds: 300
  allowed_lateness_hours: 24
  dedupe_ttl_hours: 24

api:
  rate_limit: 1000
  cache_ttl_seconds: 300
```

---

#### `config/dev.yaml` and `config/prod.yaml`
**Purpose:** Environment-specific overrides.

**Key differences:**
```yaml
# dev.yaml
pipeline:
  window_size_seconds: 60  # Faster for testing
  max_workers: 3

# prod.yaml
pipeline:
  window_size_seconds: 300
  max_workers: 20
  autoscaling: true
```

---

#### `config/pii_config.yaml`
**Purpose:** Defines PII fields and handling strategies.

```yaml
pii_fields:
  - field_path: "payload.customer.email"
    strategy: "mask"
    mask_char: "*"

  - field_path: "payload.customer.phone"
    strategy: "tokenize"
    token_prefix: "PHONE"

  - field_path: "payload.customer.address.street"
    strategy: "redact"
```

---

### BigQuery Schemas (SQL)

#### `schemas/clean/shipment_events.json`
**Purpose:** Silver layer table schema.

```json
{
    "fields": [
        {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
        {"name": "event_type", "type": "STRING", "mode": "REQUIRED"},
        {"name": "event_version", "type": "STRING", "mode": "REQUIRED"},
        {"name": "event_time", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "ingest_time", "type": "TIMESTAMP", "mode": "REQUIRED"},
        {"name": "trace_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "shipment_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "facility_id", "type": "STRING", "mode": "NULLABLE"},
        {"name": "payload", "type": "JSON", "mode": "REQUIRED"}
    ],
    "timePartitioning": {
        "type": "DAY",
        "field": "event_time"
    },
    "clustering": ["shipment_id", "event_type"]
}
```

---

#### `schemas/curated/fact_deliveries.json`
**Purpose:** Gold layer fact table schema.

**Partitioning:** By `delivery_date` (daily)
**Clustering:** By `facility_id`, `carrier_id`

---

#### `schemas/curated/dim_facility.json`
**Purpose:** Gold layer dimension table (SCD Type 2).

**SCD Type 2 columns:**
- `valid_from`: When this version became active
- `valid_to`: When this version was superseded (NULL = current)
- `is_current`: Boolean flag for current version

---

### Docker Containers

#### `docker/Dockerfile.dataflow`
**Purpose:** Container for Dataflow Flex Template.

```dockerfile
FROM gcr.io/dataflow-templates-base/python311-template-launcher-base:latest

# Install dependencies
COPY pyproject.toml ./
RUN pip install .

# Copy source code
COPY src/ ./src/
COPY config/ ./config/

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]
```

**Built image:** `gcr.io/{project}/dataflow-pipeline:latest`
**Used by:** Dataflow service

---

#### `docker/Dockerfile.api`
**Purpose:** Container for Cloud Run API.

```dockerfile
FROM python:3.11-slim

# Security: Run as non-root
RUN useradd --create-home appuser
USER appuser

# Install and run
COPY . .
RUN pip install .
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Built image:** `gcr.io/{project}/analytics-api:latest`
**Used by:** Cloud Run service

---

### CI/CD Pipelines

#### `.github/workflows/ci.yaml`
**Purpose:** Validates pull requests.

**Triggers:** On PR to main branch

**Jobs:**
1. **Lint:** Run ruff, black, mypy
2. **Test:** Run unit tests, contract tests
3. **Terraform:** Validate and plan infrastructure

---

#### `.github/workflows/cd.yaml`
**Purpose:** Deploys to environments.

**Triggers:** On merge to main branch

**Flow:**
```
Merge to main
     │
     ▼
Deploy to Dev ──────────────────┐
     │                          │
     ▼                          │
Run Integration Tests           │
     │                          │
     ▼                          │
Manual Approval Gate ◄──────────┘
     │
     ▼
Deploy to Prod
     │
     ▼
Run E2E Smoke Tests
     │
     ▼
Notify Slack
```

---

## Data Layers Explained

### Bronze Layer (GCS)
**Location:** `gs://{project}-raw-{env}/events/`

**Characteristics:**
- Raw, immutable archive
- Exactly as received from source
- Avro format (schema embedded)
- Partitioned by date/hour

**Use cases:**
- Disaster recovery
- Reprocessing after bug fixes
- Compliance/audit requirements
- Debug production issues

---

### Silver Layer (BigQuery)
**Location:** `{env}_clean` dataset

**Characteristics:**
- Validated against schema
- Deduplicated (exactly-once semantics)
- PII masked/tokenized
- Common envelope format

**Use cases:**
- Real-time dashboards
- Ad-hoc queries
- Source for Gold layer builds

---

### Gold Layer (BigQuery)
**Location:** `{env}_curated` dataset

**Characteristics:**
- Business-oriented models
- Pre-aggregated for performance
- Dimension tables (SCD Type 2)
- Fact tables (daily grain)

**Use cases:**
- BI dashboards (Looker, Tableau)
- Executive reporting
- ML feature engineering
- API serving

---

## Deployment Flow

### Initial Setup (One-time)

```bash
# 1. Set GCP project
gcloud config set project YOUR_PROJECT_ID

# 2. Enable required APIs
gcloud services enable \
    compute.googleapis.com \
    bigquery.googleapis.com \
    pubsub.googleapis.com \
    dataflow.googleapis.com \
    composer.googleapis.com \
    run.googleapis.com \
    secretmanager.googleapis.com

# 3. Initialize Terraform
cd terraform/envs/dev
terraform init

# 4. Deploy infrastructure
terraform plan -out=plan.tfplan
terraform apply plan.tfplan
```

### Deploy Streaming Pipeline

```bash
# Build and push Docker image
docker build -f docker/Dockerfile.dataflow -t gcr.io/$PROJECT/dataflow-pipeline:latest .
docker push gcr.io/$PROJECT/dataflow-pipeline:latest

# Create Flex Template
gcloud dataflow flex-template build \
    gs://$BUCKET/templates/logistics-pipeline.json \
    --image gcr.io/$PROJECT/dataflow-pipeline:latest \
    --sdk-language PYTHON

# Launch pipeline
gcloud dataflow flex-template run logistics-streaming \
    --template-file-gcs-location gs://$BUCKET/templates/logistics-pipeline.json \
    --region us-central1 \
    --parameters env=dev
```

### Deploy Airflow DAGs

```bash
# Get Composer bucket
COMPOSER_BUCKET=$(gcloud composer environments describe dev-composer \
    --location us-central1 \
    --format='get(config.dagGcsPrefix)')

# Sync DAGs
gsutil -m rsync -r src/batch/dags/ $COMPOSER_BUCKET/dags/
```

### Deploy Analytics API

```bash
# Build and push Docker image
docker build -f docker/Dockerfile.api -t gcr.io/$PROJECT/analytics-api:latest .
docker push gcr.io/$PROJECT/analytics-api:latest

# Deploy to Cloud Run
gcloud run deploy analytics-api \
    --image gcr.io/$PROJECT/analytics-api:latest \
    --region us-central1 \
    --platform managed \
    --allow-unauthenticated
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Terraform 1.5+
- Google Cloud SDK
- Docker

### Local Development

```bash
# Install dependencies
make install

# Run linting
make lint

# Run unit tests
make test-unit

# Run API locally
make run-api-local

# Run pipeline with DirectRunner (local)
make run-pipeline-direct
```

### Deploy to GCP

```bash
# Deploy dev environment
make terraform-apply ENV=dev
make deploy-dataflow ENV=dev
make sync-dags ENV=dev
make deploy-api ENV=dev

# Run integration tests
make test-integration ENV=dev
```

---

## Troubleshooting

### Common Issues

**Pipeline lag increasing:**
1. Check Dataflow worker logs
2. Verify Pub/Sub subscription backlog
3. Scale up workers if needed

**DLQ messages growing:**
1. Check `events-dlq` topic
2. Analyze failed message patterns
3. Update validation schema if needed

**Gold layer stale:**
1. Check Airflow DAG runs
2. Verify Silver layer has data
3. Check BigQuery slot availability

---

## License

MIT License - see LICENSE file for details.
