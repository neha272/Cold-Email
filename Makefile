.PHONY: help install test lint format type-check clean run-dry run-live init-db

help: ## Show this help message
	@echo "Available commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies
	poetry install

test: ## Run tests
	poetry run pytest

test-cov: ## Run tests with coverage
	poetry run pytest --cov=cold_emailer --cov-report=term-missing --cov-report=html

lint: ## Run linters
	poetry run ruff check src tests
	poetry run mypy src

format: ## Format code
	poetry run black src tests
	poetry run ruff check --fix src tests

type-check: ## Run type checker
	poetry run mypy src

clean: ## Clean generated files
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -r {} +
	rm -rf .pytest_cache .coverage htmlcov dist build

init-db: ## Initialize database
	poetry run cold-emailer init-db

run-dry: ## Run automation in dry-run mode
	poetry run cold-emailer run data/prospects.xlsx --dry-run

run-live: ## Run automation in live mode (requires --confirm-send)
	@echo "⚠️  This will send real emails!"
	poetry run cold-emailer run data/prospects.xlsx --confirm-send

ingest: ## Ingest prospects
	poetry run cold-emailer ingest data/prospects.xlsx

status: ## Show prospect status
	poetry run cold-emailer status

export-events: ## Export events to JSONL
	poetry run cold-emailer export-events --out logs/events.jsonl

all: format lint type-check test ## Run all checks (format, lint, type-check, test)
