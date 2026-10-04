.PHONY: up down test eval lint

up:
	docker compose up -d

down:
	docker compose down

test:
	uv run pytest tests/ -v

eval:
	uv run python evals/runner.py

lint:
	uv run ruff check .
