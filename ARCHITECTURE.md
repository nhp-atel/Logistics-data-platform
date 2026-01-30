# GCP Event-Driven Logistics Data Platform (Flagship Project)

This document explains the **architecture** and how **components + repo files interact end-to-end**, including the **testing strategy**.

---

## 1) High-level architecture (textual diagram)

**Producers → Dual ingestion (Kafka + Pub/Sub) → Stream ETL (Dataflow/Beam) → Raw/Clean/Curated layers → Consumers (BI/ML/APIs)**

```
[Edge/Apps/IoT/3P Carriers]
    | (JSON/Avro events)
    v
+-------------------+                         +----------------------+
|   Apache Kafka    |                         |       Pub/Sub        |
|  (self-managed or |                         | (native GCP ingest)  |
|   Confluent Cloud)|                         +----------------------+
|  topics/partitions|                           ^           |
+-------------------+                           |           |
    | (Dataflow KafkaIO)                        |           | (sub)
    v                                           |           v
+---------------------------------------------------------------+
|                 Dataflow (Apache Beam)                         |
|  - parsing + validation + DQ rules                              |
|  - event-time windowing, late data, dedupe                      |
|  - enrich (static dims), standardize, PII tokenization          |
|  - write to:                                                    |
|       GCS Raw (append-only)                                     |
|       BigQuery Clean (canonical)                                |
|       BigQuery Curated (analytics marts) via streaming tables   |
+---------------------------------------------------------------+
     |                           |
     v                           v
[GCS Raw Zone]               [BigQuery Clean Zone]
 (bronze)                     (silver)
     |                           |
     v                           v
+-------------------+       +------------------------+
| Airflow (Composer)|       | BigQuery Curated Zone  |
| - batch backfills |       | (gold marts/features)  |
| - reconciliation  |       | - BI marts             |
| - daily aggregates|       | - ML feature tables    |
+-------------------+       +------------------------+
     |                           |
     v                           v
[BigQuery DQ/Recon tables]    [Consumers]
                              - BI (Looker/Mode)
                              - ML (Vertex AI / notebooks)
                              - API (FastAPI/Cloud Run)
```

---

## 2) Why Kafka **and** Pub/Sub?

### Kafka (enterprise integration + replay + cross-cloud)
- **Best when** you need:
  - tight control over partitions, ordering, consumer groups
  - long retention & **replay semantics** for downstream rebuilds
  - integration with existing enterprise event bus / on-prem / hybrid
- **Tradeoffs**: capacity planning, ops burden, upgrades, rebalancing, storage.

### Pub/Sub (GCP-native scale + simpler ops)
- **Best when** you need:
  - managed, elastic ingest; minimal ops
  - straightforward fan-out to many consumers
  - native integration (Dataflow, Cloud Functions, BigQuery subscriptions)
- **Tradeoffs**: different ordering guarantees; replay via retention + seek is possible but is not Kafka-like log semantics; message size limits.

### Pattern used here
- Treat Kafka as the **system-of-record event log** in many enterprises, while Pub/Sub is a **GCP-native ingest plane** for services already running in GCP.
- Both feed the same Beam pipeline to show practical interoperability and portability.

---

## 3) Repo layout (buildable by one engineer)

```
logistics-data-platform/
  README.md
  docs/
    ARCHITECTURE.md                <-- this file
    DATA_CONTRACTS.md
    RUNBOOKS.md
  infra/
    terraform/
      modules/
        gcp_base/                  (project, apis, networks)
        iam/                       (service accounts + roles)
        pubsub/                    (topics/subscriptions + DLQs)
        gcs/                       (raw/clean/curated buckets)
        bigquery/                  (datasets, tables, policies)
        composer/                  (Airflow/Composer env)
        dataflow/                  (templates, parameters)
      envs/
        dev/
          main.tf
          backend.tf               (remote state)
          variables.tf
          dev.tfvars
        prod/
          main.tf
          backend.tf
          variables.tf
          prod.tfvars
  pipelines/
    streaming/
      beam/
        src/
          main.py                  (pipeline entry)
          options.py               (Beam options)
          transforms/
            parse_validate.py
            dedupe.py
            enrich.py
            pii.py
            sinks.py
          schemas/
            logistics_event.avsc
            shipment_event.avsc
            driver_event.avsc
        tests/
          test_parse_validate.py
          test_dedupe.py
          test_windowing.py
        pyproject.toml
    batch/
      airflow/
        dags/
          daily_marts.py
          backfill_reprocess.py
          late_data_reconciliation.py
        plugins/
          bq_sla_callbacks.py
        tests/
          test_dags_import.py
          test_task_graph.py
      sql/
        clean_to_curated/
          mart_shipments.sql
          mart_on_time_performance.sql
          features_driver_behavior.sql
  services/
    analytics_api/
      app/
        main.py                    (FastAPI)
        routes/
          v1_shipments.py
        cache.py                   (Redis/Memorystore)
        auth.py                    (service-to-service auth)
      tests/
        test_routes.py
      Dockerfile
  ci/
    github/
      workflows/
        test.yml
        terraform_plan.yml
        terraform_apply.yml
```

---

## 4) End-to-end data flow (what happens to one event)

### Step A — Event generation (producers)
Example: `shipment.status.changed` from a shipping microservice.

1. Producer creates event with:
   - **event_id** (UUID)
   - **event_type**
   - **event_time** (when it occurred)
   - **producer_time** (when emitted)
   - **payload** (shipment_id, status, location, etc.)
2. Producer writes:
   - to **Kafka** topic (enterprise bus) *and/or*
   - to **Pub/Sub** topic (GCP-native path)

### Step B — Streaming ETL (Dataflow/Beam)
Beam pipeline:
1. Read from KafkaIO and Pub/Sub (two branches), normalize to a common envelope.
2. Validate schema + required fields; invalid → **DLQ** (Pub/Sub dead-letter) + raw quarantine.
3. **Deduplicate** by `(event_id)` and/or `(shipment_id, status, event_time)` depending on event type.
4. Apply event-time windowing (e.g., 5-min tumbling + allowed lateness 24h).
5. Enrich with slowly changing dims (carrier, lane, facility) from BigQuery side-input snapshots.
6. Tokenize PII fields (driver phone/email) before writing clean/curated.
7. Write:
   - **GCS raw**: append-only, partitioned by ingest_date/event_type
   - **BigQuery clean**: canonical, partitioned by event_date, clustered by shipment_id
   - Optional: **curated streaming tables** for near-real-time dashboards

### Step C — Batch orchestration (Airflow)
- Nightly (and on-demand) jobs:
  - build curated marts (gold) from clean tables
  - compute late-data reconciliation diffs
  - run backfills for selected date ranges

### Step D — Consumption
- BI queries curated marts.
- ML uses feature tables with point-in-time correctness.
- API serves versioned endpoints from curated/feature datasets with caching.

---

## 5) Data contracts + schemas (logistics realism)

### Canonical event envelope (BigQuery `clean.events`)
Fields (suggested):
- `event_id STRING` (required)
- `event_type STRING` (required) e.g. shipment.status.changed
- `event_version INT64` (required)
- `event_time TIMESTAMP` (required) **event-time**
- `ingest_time TIMESTAMP` (required) **processing-time**
- `source STRING` (producer name)
- `trace_id STRING` (optional)
- `tenant_id STRING` (optional, multi-tenant)
- `payload JSON` (or STRUCT per event type)
- `schema_hash STRING` (for evolution)
- `dedupe_key STRING` (computed)

### Example: `shipment.status.changed` payload
- `shipment_id STRING`
- `status STRING` (created, picked_up, in_transit, out_for_delivery, delivered, exception)
- `facility_id STRING`
- `geo STRUCT<lat FLOAT64, lon FLOAT64>`
- `carrier_code STRING`
- `eta TIMESTAMP` (nullable)

### Schema evolution strategy
- Use **versioned event types** (`event_version`) with backward-compatible additions.
- Producers publish schema to `docs/DATA_CONTRACTS.md`.
- Beam supports:
  - tolerant parsing (unknown fields ignored)
  - required fields enforced by version
  - write `schema_hash` to detect drift

---

## 6) BigQuery modeling (raw / clean / curated)

### Raw (bronze) — Cloud Storage
- GCS bucket: `gs://<env>-raw-events/`
- Layout:
  - `event_type=shipment.status.changed/ingest_date=YYYY-MM-DD/part-*.jsonl.gz`
- Purpose: immutable archive, replay source, forensics.

### Clean (silver) — BigQuery canonical tables
Datasets:
- `clean` dataset holds normalized events:
  - `clean.events` (envelope)
  - optional typed tables for high-volume types: `clean.shipment_status_events`

**Partitioning**
- Partition by `DATE(event_time)` (event date) OR `ingest_date` for some sources.
- Prefer `event_time` partitions for analytics alignment; keep an `ingest_date` column for ops.

**Clustering**
- `shipment_id`, `event_type`, `facility_id` to reduce scan costs.

### Curated (gold) — marts + features
- `curated.mart_shipments_daily`
- `curated.mart_on_time_performance`
- `features.driver_behavior_daily` (ML)
- Use wide tables for BI performance; maintain star schema dims if needed.

**Wide-table vs dimensional tradeoff**
- Wide tables = faster BI, fewer joins, easier for dashboards.
- Dimensional model = better reuse, governance, and consistency.
- Approach: keep dims in `curated.dim_*` and also publish a denormalized mart for BI.

---

## 7) Streaming semantics & distributed systems details

### Event-time vs processing-time
- Use `event_time` as Beam timestamp for windowing.
- `ingest_time` tracked separately for SLAs and lateness metrics.

### Windowing strategies
- Near-real-time KPIs: 5-min tumbling windows with triggers:
  - early (processing-time) + on-time + late firings
- Facility throughput: 1-min sliding windows
- Daily aggregates: fixed windows by event-time day

### Late & out-of-order handling
- Allowed lateness: 24h (configurable per event type).
- Late events update:
  - clean tables (append-only + dedupe)
  - curated via:
    - streaming updates if feasible, or
    - batch reconciliation DAG recomputing affected partitions.

### Exactly-once vs at-least-once
- Kafka & Pub/Sub ingest are **at-least-once**.
- End-to-end exactly-once is hard; design for **idempotent writes**:
  - BigQuery: dedupe keys + MERGE in batch for curated
  - Streaming: write append-only to clean + periodic compaction MERGE

### Backpressure & scaling
- Dataflow autoscaling with:
  - runner v2
  - parallelism via sharding (Kafka partitions, Pub/Sub subscriptions)
- Prevent hotspots by:
  - partition keys with high cardinality (`shipment_id`) and salting if needed.

### Failure recovery scenarios
- Dataflow worker failures → retry and checkpointing.
- Poison messages → DLQ + quarantine bucket + Airflow reprocess.
- BigQuery quota errors → exponential backoff + batch load jobs.

---

## 8) Airflow orchestration design

### DAGs
1. `daily_marts.py`
   - builds daily curated marts from clean
   - `mart_shipments_daily`, `mart_otp`, `mart_exceptions`
2. `late_data_reconciliation.py`
   - compares clean vs curated for last N days
   - recompute partitions with anomalies or late arrivals
3. `backfill_reprocess.py`
   - parameterized date range and event types
   - runs Beam batch pipeline (or BQ SQL rebuild) and backfills curated

### SLAs + monitoring
- Define SLAs per table (e.g., curated marts ready by 06:30 local).
- Use callbacks to publish metrics and alert (email/Slack) on misses.
- Store reconciliation metrics in `ops.recon_results`.

### Failure recovery
- Retries with jitter for transient errors.
- Persistent failures:
  - mark partition as `needs_rebuild`
  - route to runbook instructions in `docs/RUNBOOKS.md`.

---

## 9) Terraform & IaC (state, environments, IAM)

### Module structure (why)
- Separate **modules** for composability and reviewable changes.
- Separate **envs** for dev/prod with isolated state.

### State management best practices
- Use remote backend (GCS bucket) with:
  - versioning enabled
  - bucket-level retention
  - state locking (Terraform supports GCS locking patterns; if using Terraform Cloud, use remote runs)

### IAM least privilege (key service accounts)
- `sa-dataflow-streaming@`:
  - Pub/Sub Subscriber, BigQuery Data Editor (specific datasets), GCS Writer (raw bucket), Logging/Monitoring writer
- `sa-airflow@`:
  - BigQuery Job User, Data Viewer/Editor scoped to curated datasets, ability to trigger Dataflow templates
- `sa-analytics-api@`:
  - BigQuery Data Viewer (curated/features only), Secret Manager accessor, optional Memorystore access

Environment separation:
- distinct projects preferred (`proj-dev`, `proj-prod`) to avoid policy bleed.
- if single project: strict naming + IAM boundaries + separate datasets/buckets.

---

## 10) Observability + cost controls

### Metrics (must-have)
- ingest lag (Kafka consumer lag, Pub/Sub backlog)
- event-time lateness distribution
- DLQ rate and top error codes
- dedupe drop rate (duplicate %)
- BigQuery scan bytes per key dashboard query
- Dataflow CPU/memory and autoscaling events

### Logging
- structured logs with `trace_id`, `event_type`, `pipeline_stage`.
- correlate producers → pipeline → BigQuery inserts.

### Cost management
- BigQuery:
  - partition pruning enforced (require partition filter)
  - clustering on frequent predicates
  - materialized views / aggregate tables for heavy dashboards
- Dataflow:
  - autoscaling
  - right-size worker types
  - avoid expensive per-record calls (use side inputs, batch lookups)

---

## 11) Testing strategy (production-grade)

### A) Unit tests (fast)
**Beam transforms**
- `pipelines/streaming/beam/tests/`
- Use `TestPipeline` and Beam `PAssert` for:
  - schema validation behavior
  - dedupe correctness
  - windowing + allowed lateness logic
  - PII tokenization

**Airflow DAG integrity**
- `pipelines/batch/airflow/tests/`
- Test DAG imports; validate task graph, schedule, SLA callbacks.

**API**
- `services/analytics_api/tests/` using `pytest` + test client
- Mock BigQuery client; verify query templates + auth enforcement.

### B) Integration tests (medium)
- Spin up ephemeral infra in **dev** project:
  - Pub/Sub topic/sub
  - BigQuery dataset
  - GCS buckets
- Run a small Beam pipeline with DirectRunner against test topics and validate BQ outputs.

### C) Contract tests (critical for event platforms)
- Validate producer events against Avro/JSON Schema in CI.
- Consumer contract tests for schema evolution (e.g., v1 → v2 adds fields).

### D) End-to-end smoke tests (release gate)
- Deploy Dataflow template to dev.
- Publish a known fixture batch of events.
- Assert curated marts update as expected within SLA window.

### E) Data quality tests (warehouse)
- Great Expectations or dbt tests (optional) on curated tables:
  - not-null keys, referential integrity, accepted values
  - distribution/anomaly checks (z-score, seasonality)

---

## 12) How the key components interact (file → runtime mapping)

### Dataflow pipeline
- `pipelines/streaming/beam/src/main.py`
  - wires sources (KafkaIO + Pub/Sub), applies transforms, writes sinks
- `transforms/parse_validate.py`
  - schema checks, required fields, DLQ routing
- `transforms/dedupe.py`
  - stateful dedupe (windowed) + dedupe key computation
- `transforms/enrich.py`
  - side input snapshots from BigQuery dims or GCS
- `transforms/pii.py`
  - tokenization/hashing; keep mapping in restricted dataset if needed
- `transforms/sinks.py`
  - write to GCS (raw) and BigQuery (clean)

### Airflow orchestration
- `daily_marts.py`
  - runs BigQuery SQL from `pipelines/batch/sql/clean_to_curated/*`
- `late_data_reconciliation.py`
  - scans last N partitions for deltas; triggers rebuild tasks
- `backfill_reprocess.py`
  - parameterized reprocess that can call:
    - Dataflow template (batch mode) or
    - BigQuery SQL rebuild

### Analytics API
- `services/analytics_api/app/routes/v1_shipments.py`
  - reads curated datasets, applies query params, returns JSON
- `cache.py`
  - caches common queries (e.g., last 24h OTP by facility)
- `auth.py`
  - validates identity (IAP/JWT/service-to-service)

### Terraform
- `infra/terraform/modules/*`
  - one responsibility per module
- `infra/terraform/envs/dev|prod`
  - composes modules + sets variables for each environment

---

## 13) Interview-ready failure scenarios (and mitigations)

1. **Producer retries cause duplicates**
   - Mitigation: event_id + dedupe keys; append-only + compaction MERGE.
2. **Late events arrive after dashboards computed**
   - Mitigation: allowed lateness + reconciliation DAG recomputing affected partitions.
3. **Schema breaking change deployed**
   - Mitigation: schema registry + contract tests + versioned event types.
4. **Kafka partition hotspot**
   - Mitigation: key design + salting; monitor lag; repartition if needed.
5. **BigQuery cost explosion**
   - Mitigation: partition filters enforced, pre-aggregations, clustering, query governance.

---

## 14) 5-minute narrative (how to explain this project)

> “I built an event-driven logistics data platform on GCP. Operational systems publish shipment, facility, and driver events into Kafka for enterprise replay and into Pub/Sub for GCP-native fanout. A Dataflow/Beam streaming pipeline validates schemas, handles event-time windowing with late data, deduplicates at-least-once deliveries, tokenizes PII, and writes immutable raw archives to GCS plus canonical clean events into BigQuery. Airflow orchestrates curated marts, backfills, and late-data reconciliation so dashboards and ML features stay correct. Everything is provisioned with Terraform across dev/prod with least-privilege service accounts. Observability includes lag, lateness distributions, DLQ rates, and cost controls via partitioning and clustering. The system is designed to survive duplicates, late arrivals, schema drift, and scaling spikes while remaining explainable and operable.”
