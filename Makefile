# Makefile for GCP Logistics Data Platform
SHELL := /bin/bash
.PHONY: help install lint test test-unit test-contract test-integration test-e2e format clean build deploy-dataflow sync-dags terraform-plan terraform-apply

# Default environment
ENV ?= dev
PROJECT_ID ?= logistics-platform
REGION ?= us-central1

# Python settings
PYTHON := python3
PIP := pip3

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m

help: ## Show this help message
	@echo "Usage: make [target] [ENV=dev|prod]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

# ============================================================================
# Development Setup
# ============================================================================

install: ## Install all dependencies
	@echo "$(GREEN)Installing dependencies...$(NC)"
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

install-ci: ## Install dependencies for CI
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

# ============================================================================
# Code Quality
# ============================================================================

lint: ## Run linting checks
	@echo "$(GREEN)Running linters...$(NC)"
	ruff check src/ tests/
	ruff format --check src/ tests/

format: ## Format code
	@echo "$(GREEN)Formatting code...$(NC)"
	ruff format src/ tests/
	ruff check --fix src/ tests/

type-check: ## Run type checking
	@echo "$(GREEN)Running type checks...$(NC)"
	mypy src/ --ignore-missing-imports

# ============================================================================
# Testing
# ============================================================================

test: test-unit test-contract ## Run all tests

test-unit: ## Run unit tests
	@echo "$(GREEN)Running unit tests...$(NC)"
	pytest tests/unit/ -v --cov=src --cov-report=term-missing

test-contract: ## Run contract tests
	@echo "$(GREEN)Running contract tests...$(NC)"
	pytest tests/contract/ -v

test-integration: ## Run integration tests (requires GCP credentials)
	@echo "$(GREEN)Running integration tests for $(ENV)...$(NC)"
	pytest tests/integration/ -v --environment=$(ENV)

test-e2e: ## Run end-to-end tests (requires deployed environment)
	@echo "$(GREEN)Running e2e tests for $(ENV)...$(NC)"
	pytest tests/e2e/ -v --environment=$(ENV)

coverage: ## Generate coverage report
	@echo "$(GREEN)Generating coverage report...$(NC)"
	pytest tests/unit/ --cov=src --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# ============================================================================
# Build
# ============================================================================

build: ## Build Docker images
	@echo "$(GREEN)Building Docker images...$(NC)"
	docker build -t logistics-dataflow:local -f docker/Dockerfile.dataflow .
	docker build -t logistics-api:local -f docker/Dockerfile.api .

build-dataflow: ## Build Dataflow Docker image
	@echo "$(GREEN)Building Dataflow image...$(NC)"
	docker build -t logistics-dataflow:local -f docker/Dockerfile.dataflow .

build-api: ## Build API Docker image
	@echo "$(GREEN)Building API image...$(NC)"
	docker build -t logistics-api:local -f docker/Dockerfile.api .

# ============================================================================
# Deployment
# ============================================================================

deploy-dataflow: ## Deploy Dataflow pipeline
	@echo "$(GREEN)Deploying Dataflow pipeline to $(ENV)...$(NC)"
	./scripts/deploy_dataflow.sh --project $(PROJECT_ID) --region $(REGION) --environment $(ENV)

sync-dags: ## Sync DAGs to Cloud Composer
	@echo "$(GREEN)Syncing DAGs to Composer $(ENV)...$(NC)"
	./scripts/sync_dags.sh --project $(PROJECT_ID) --environment $(ENV)

deploy-api: ## Deploy API to Cloud Run
	@echo "$(GREEN)Deploying API to Cloud Run $(ENV)...$(NC)"
	gcloud run deploy $(ENV)-analytics-api \
		--image $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(ENV)-analytics-api/logistics-api:latest \
		--region $(REGION) \
		--platform managed

# ============================================================================
# Terraform
# ============================================================================

terraform-init: ## Initialize Terraform
	@echo "$(GREEN)Initializing Terraform for $(ENV)...$(NC)"
	cd terraform/envs/$(ENV) && terraform init

terraform-plan: ## Plan Terraform changes
	@echo "$(GREEN)Planning Terraform for $(ENV)...$(NC)"
	cd terraform/envs/$(ENV) && terraform plan -var="project_id=$(PROJECT_ID)"

terraform-apply: ## Apply Terraform changes
	@echo "$(YELLOW)Applying Terraform for $(ENV)...$(NC)"
	cd terraform/envs/$(ENV) && terraform apply -var="project_id=$(PROJECT_ID)"

terraform-destroy: ## Destroy Terraform resources (DANGEROUS)
	@echo "$(RED)WARNING: This will destroy all resources in $(ENV)!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [[ $$confirm == [yY] ]] || exit 1
	cd terraform/envs/$(ENV) && terraform destroy -var="project_id=$(PROJECT_ID)"

terraform-fmt: ## Format Terraform files
	terraform fmt -recursive terraform/

terraform-validate: ## Validate Terraform configuration
	cd terraform/envs/$(ENV) && terraform validate

# ============================================================================
# Local Development
# ============================================================================

run-api-local: ## Run API locally
	@echo "$(GREEN)Starting API locally...$(NC)"
	ENVIRONMENT=dev uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8080

run-pipeline-direct: ## Run pipeline in DirectRunner (local)
	@echo "$(GREEN)Running pipeline locally with DirectRunner...$(NC)"
	$(PYTHON) -m src.streaming.pipeline \
		--runner=DirectRunner \
		--input_subscription=projects/$(PROJECT_ID)/subscriptions/$(ENV)-unified-events-dataflow \
		--output_table=$(PROJECT_ID):$(ENV)_clean.shipment_events \
		--raw_bucket=$(PROJECT_ID)-$(ENV)-raw \
		--dlq_topic=projects/$(PROJECT_ID)/topics/$(ENV)-unified-events-dlq \
		--environment=$(ENV)

# ============================================================================
# Utilities
# ============================================================================

clean: ## Clean build artifacts
	@echo "$(GREEN)Cleaning build artifacts...$(NC)"
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ .mypy_cache/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

validate-schemas: ## Validate JSON schemas
	@echo "$(GREEN)Validating JSON schemas...$(NC)"
	$(PYTHON) -c "import json; import glob; [json.load(open(f)) for f in glob.glob('config/event_schemas/*.json')]"
	@echo "All schemas are valid JSON"

gen-docs: ## Generate documentation
	@echo "$(GREEN)Generating documentation...$(NC)"
	pdoc --html --output-dir docs/api src/

check-secrets: ## Check for exposed secrets
	@echo "$(GREEN)Checking for exposed secrets...$(NC)"
	@grep -r --include="*.py" --include="*.yaml" --include="*.json" -E "(password|secret|api_key|token).*=.*['\"]" . | grep -v "PLACEHOLDER" | grep -v ".pyc" || echo "No exposed secrets found"
