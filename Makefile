# Aulas de Inglês — atalhos do dia a dia.
# `make up` precisa funcionar a partir de um clone limpo.

COMPOSE := docker compose --env-file .env -f infra/compose.yml
.DEFAULT_GOAL := help

.PHONY: help up down logs ps reset api web test test-api test-web test-e2e lint fmt health \
        migrate migration seed openapi prod-up prod-down prod-logs prod-seed backup restore cov

help: ## Lista os comandos
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

.env:
	@cp .env.example .env && echo "✓ .env criado a partir do .env.example"

up: .env ## Sobe db + api + web, aplica migrations e carrega o seed
	# Renova o volume anônimo de node_modules depois de reconstruir a imagem web.
	$(COMPOSE) up -d --build --renew-anon-volumes
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

test: test-api test-web ## Roda as duas suítes de unidade/integração

test-e2e: ## Playwright contra o compose de produção (precisa de `make prod-up`)
	cd e2e && npm test

cov: ## pytest com relatório de cobertura
	cd backend && uv run pytest --cov --cov-report=term-missing

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

# ---------- produção local ----------

PROD := docker compose --env-file .env.prod -f infra/compose.prod.yml

.env.prod:
	@echo "Crie o .env.prod a partir do .env.prod.example e troque os segredos." >&2
	@echo "  cp .env.prod.example .env.prod && openssl rand -hex 32" >&2
	@exit 1

prod-up: .env.prod ## Sobe o compose de produção (nginx + uvicorn + Postgres)
	$(PROD) up -d --build
	$(PROD) exec -T api alembic upgrade head
	$(PROD) exec -T api python -m app.cli seed
	@echo ""
	@echo "  web  http://localhost:$$(grep WEB_HOST_PORT .env.prod | cut -d= -f2)"

prod-down: ## Derruba o compose de produção (mantém o volume)
	$(PROD) down

prod-logs: ## Logs de produção (JSON, uma linha por requisição)
	$(PROD) logs -f api

prod-seed: ## Recarrega o seed em produção
	$(PROD) exec -T api python -m app.cli seed

# ---------- backup ----------

backup: ## Dump do banco de produção em backups/aulas-AAAAMMDD-HHMM.dump
	@mkdir -p backups
	@f=backups/aulas-$$(date +%Y%m%d-%H%M).dump; \
	 $(PROD) exec -T db pg_dump -U $${POSTGRES_USER:-aulas} -d $${POSTGRES_DB:-aulas_ingles} -Fc > $$f; \
	 echo "✓ $$f ($$(du -h $$f | cut -f1))"

restore: ## Restaura um dump — make restore f=backups/aulas-....dump
	@test -n "$(f)" || { echo "uso: make restore f=backups/aulas-....dump" >&2; exit 1; }
	$(PROD) exec -T db pg_restore -U $${POSTGRES_USER:-aulas} -d $${POSTGRES_DB:-aulas_ingles} \
		--clean --if-exists --no-owner < $(f)
	@echo "✓ restaurado de $(f)"
