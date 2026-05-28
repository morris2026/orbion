.PHONY: format lint lint-fix type test test-integration test-all audit check clean clean-all docker-up docker-down

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