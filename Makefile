.PHONY: format lint lint-fix type test test-front test-integration test-all test-random test-e2e db-init audit check clean clean-all docker-up docker-down staging staging-clean staging-down staging-logs

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

test-front:
	cd web && npm test -- --sequence.shuffle

test-integration:
	ORBION_POSTGRES__DB=orbion_test .venv/bin/python -m pytest tests/integration/ --cov=app --cov-fail-under=80

test-all:
	ORBION_POSTGRES__DB=orbion_test .venv/bin/python -m pytest tests/ --cov=app --cov-fail-under=80

test-random:
	@for i in 1 2 3 4 5 6 7 8 9 10; do \
		echo "=== Random run $$i/10 ==="; \
		ORBION_POSTGRES__DB=orbion_test .venv/bin/python -m pytest tests/ -q || exit 1; \
	done

test-e2e:
	cd web && npx playwright install && npx playwright test

db-init:
	.venv/bin/python scripts/init-test-dbs.py

audit:
	.venv/bin/pip-audit

check: format lint type test-all test-front audit

docker-up:
	docker compose up -d

docker-down:
	docker compose down

clean:
	find app/ tests/ -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache/ .ruff_cache/ .mypy_cache/ htmlcov/ .coverage node_modules/

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
