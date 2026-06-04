.PHONY: format lint lint-fix type test test-integration test-all test-e2e audit check clean clean-all docker-up docker-down staging staging-clean staging-down staging-logs

format:
	.venv/bin/ruff format app/ tests/

lint:
	.venv/bin/ruff check app/ tests/

lint-fix:
	.venv/bin/ruff check --fix app/ tests/

type:
	.venv/bin/mypy app/ tests/

test:
	.venv/bin/python -m pytest tests/unit/ --cov=app --cov-fail-under=80

test-integration:
	.venv/bin/python -m pytest tests/integration/ --cov=app --cov-fail-under=80

test-all:
	.venv/bin/python -m pytest tests/ --cov=app --cov-fail-under=80

test-e2e:
	# 前置：docker-up（PostgreSQL）+ migrations + npm run build + playwright install
	cd web && npm run build && npx playwright test

audit:
	.venv/bin/pip-audit

check: format lint type test-all audit

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	find app/ tests/ -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/ .coverage

clean-all: clean docker-down
	rm -rf .venv/ data/ repo/

staging:
	bash scripts/deploy-staging.sh

staging-clean:
	bash scripts/deploy-staging.sh --clean

staging-down:
	docker compose -f docker-compose.staging.yml down

staging-logs:
	docker compose -f docker-compose.staging.yml logs -f