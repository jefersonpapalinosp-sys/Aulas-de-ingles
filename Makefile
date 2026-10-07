# Aulas de Inglês — atalhos do dia a dia.
# `make up` precisa funcionar a partir de um clone limpo.

COMPOSE := docker compose --env-file .env -f infra/compose.yml
.DEFAULT_GOAL := help

.PHONY: help up down logs ps reset api web test test-api test-web lint fmt health migrate migration seed openapi

help: ## Lista os comandos
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

.env:
	@cp .env.example .env && echo "✓ .env criado a partir do .env.example"

up: .env ## Sobe db + api + web, aplica migrations e carrega o seed
	$(COMPOSE) up -d --build
	$(COMPOSE) exec -T api alembic upgrade head
	$(COMPOSE) exec -T api python -m app.cli seed
	@echo ""
	@echo "  web  http://localhost:$${WEB_HOST_PORT:-5180}"
	@echo "  api  http://localhost:$${API_HOST_PORT:-8010}/api/health"
	@echo "  db   localhost:$${POSTGRES_HOST_PORT:-5433}"

down: ## Derruba os containers (mantém o volume do banco)
	$(COMPOSE) down

reset: ## Derruba tudo e APAGA o volume do banco
	$(COMPOSE) down -v

logs: ## Acompanha os logs
	$(COMPOSE) logs -f

ps: ## Estado dos containers
	$(COMPOSE) ps

health: ## Bate no /api/health e mostra a resposta
	@curl -s -o /dev/stdout -w "\nHTTP %{http_code}\n" http://localhost:$${API_HOST_PORT:-8010}/api/health

api: .env ## Roda a API no host (contra o Postgres do compose)
	cd backend && DATABASE_URL=postgresql+asyncpg://aulas:aulas_local@localhost:5433/aulas_ingles \
		uv run uvicorn app.main:app --reload --port 8010

web: ## Roda o Vite no host
	cd frontend && VITE_API_PROXY_TARGET=http://localhost:8010 npm run dev

test: test-api test-web ## Roda as duas suítes

test-api: ## pytest contra o Postgres do compose
	cd backend && uv run pytest -q

test-web: ## vitest
	cd frontend && npm run test

lint: ## ruff + mypy + eslint + tsc
	cd backend && uv run ruff check . && uv run mypy app
	cd frontend && npm run lint && npm run typecheck

fmt: ## Formata o backend
	cd backend && uv run ruff format . && uv run ruff check --fix .

migrate: ## Aplica as migrations pendentes
	$(COMPOSE) exec -T api alembic upgrade head

migration: ## Gera uma revisão a partir dos modelos — make migration m="texto"
	$(COMPOSE) exec -T api alembic revision --autogenerate -m "$(m)"

seed: ## Carrega seed/lessons.json (idempotente)
	$(COMPOSE) exec -T api python -m app.cli seed

openapi: ## Regrava o baseline do contrato em backend/openapi.json
	cd backend && uv run python -m app.openapi_dump
