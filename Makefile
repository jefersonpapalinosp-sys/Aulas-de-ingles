# Aulas de Inglês — atalhos do dia a dia.
# `make up` precisa funcionar a partir de um clone limpo.

COMPOSE := docker compose --env-file .env -f infra/compose.yml
TEST_COMPOSE := docker compose -f infra/compose.test.yml
E2E_COMPOSE := docker compose --env-file infra/e2e.env -p aulas-ingles-e2e -f infra/compose.e2e.yml
RECOVERY_COMPOSE := docker compose --env-file infra/e2e.env -p aulas-ingles-recovery -f infra/compose.recovery.yml
OPS := uv run --project backend python
ROLES_COMPOSE := docker compose --env-file infra/e2e.env -p aulas-ingles-roles -f infra/compose.roles.yml
.DEFAULT_GOAL := help

.PHONY: help up down logs ps reset api web test test-api test-web test-e2e lint fmt health \
        migrate migration seed openapi assist-gate assist-worker prod-up prod-down prod-logs \
        prod-seed backup restore cov test-db-up test-db-down test-api-prepare e2e-up e2e-down e2e-check \
        recovery-lab-up recovery-lab-prepare recovery-lab-down backup-verify test-recovery \
        test-recovery-integration roles-lab-up roles-lab-prepare test-roles roles-lab-down

help: ## Lista os comandos
	@grep -E '^[a-z0-9-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

.env:
	@cp .env.example .env && echo "✓ .env criado a partir do .env.example"

up: .env ## Sobe db + api + worker + web, aplica migrations e carrega o seed
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

e2e-up: ## Sobe stack descartável em 5198; não lê .env/.env.prod nem usa dados do aluno
	node e2e/safety.mjs resources
	$(E2E_COMPOSE) up -d --build --wait --wait-timeout 180
	node e2e/safety.mjs stack

e2e-check: ## Confere containers, volumes e identidade real do banco antes de testar
	node e2e/safety.mjs stack

e2e-down: ## Para somente a stack E2E, preservando seus volumes sintéticos
	node e2e/safety.mjs resources
	$(E2E_COMPOSE) down

test-e2e: e2e-check ## Playwright somente na stack descartável (prepare com make e2e-up)
	cd e2e && npm test

test-db-up: ## Sobe só o PostgreSQL exclusivo e limitado dos testes (55435)
	$(TEST_COMPOSE) up -d --wait

test-db-down: ## Para o PostgreSQL de teste sem remover dados de outros ambientes
	$(TEST_COMPOSE) down

test-api-prepare: test-db-up ## Verifica isolamento, migra e semeia somente a base de teste
	cd backend && uv run python -m app.testing prepare

cov: test-api-prepare ## pytest com cobertura, somente na base exclusiva de testes
	cd backend && uv run pytest --cov --cov-report=term-missing

test-api: test-api-prepare ## pytest contra banco descartável, nunca contra dev/prod
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

assist-gate: ## Avalia o piloto: make assist-gate modality=writing review=../config/assist-provider-review.json
	cd backend && uv run python -m app.cli assist-gate \
		--modality "$(modality)" --review-file "$(review)"

assist-worker: ## Processa um job pendente da fila assistida
	$(COMPOSE) exec -T worker python -m app.cli assist-worker --once

# ---------- produção local ----------

PROD_ROLES := $(if $(wildcard backups/recovery/roles-prod.env),--env-file backups/recovery/roles-prod.env -f infra/compose.roles.prod.yml)
PROD := docker compose --env-file .env.prod -f infra/compose.prod.yml $(PROD_ROLES)

.env.prod:
	@echo "Crie o .env.prod a partir do .env.prod.example e troque os segredos." >&2
	@echo "  cp .env.prod.example .env.prod && openssl rand -hex 32" >&2
	@exit 1

prod-up: .env.prod ## Sobe o compose de produção (nginx + uvicorn + Postgres)
ifneq ($(PROD_ROLES),)
	@echo "Papéis separados: deploy exige backup/ensaio/migration; siga docs/operacao_sprint_37.md." >&2
	@exit 1
else
	$(PROD) up -d --build
	$(PROD) exec -T api alembic upgrade head
	$(PROD) exec -T api python -m app.cli seed
endif
	@echo ""
	@echo "  web  http://localhost:$$(grep WEB_HOST_PORT .env.prod | cut -d= -f2)"

prod-down: ## Derruba o compose de produção (mantém o volume)
	$(PROD) down

prod-logs: ## Logs de produção (JSON, uma linha por requisição)
	$(PROD) logs -f api

prod-seed: ## Recarrega o seed em produção
ifneq ($(PROD_ROLES),)
	@echo "Seed completo exige manutenção explícita com o migrador; consulte o README." >&2
	@exit 1
else
	$(PROD) exec -T api python -m app.cli seed
endif

# ---------- backup ----------

recovery-lab-up: ## Sobe laboratório de recuperação sem portas e sem volumes do aluno
	$(OPS) -m ops.recovery lab-resources
	docker build -f backend/Dockerfile.prod -t aulas-ingles-recovery-tools:local .
	$(RECOVERY_COMPOSE) up -d --wait --wait-timeout 120
	$(OPS) -m ops.recovery lab-resources

recovery-lab-prepare: ## Prepara apenas a origem vazia do laboratório, com WAV sintético
	$(OPS) -m ops.recovery lab-prepare

recovery-lab-down: ## Para só o laboratório de recuperação; preserva todos os seus volumes
	$(OPS) -m ops.recovery lab-resources
	$(RECOVERY_COMPOSE) down

backup: ## Banco + voz: make backup source=lab|prod (origem precisa estar em manutenção)
	$(OPS) -m ops.recovery backup --source "$(source)"

backup-verify: ## Confere manifesto/checksums: make backup-verify f=backups/recovery/aulas-...
	$(OPS) -m ops.recovery verify "$(f)"

restore: ## Somente destino vazio isolado: make restore f=... confirm=aulas-ingles-recovery/target-db
	$(OPS) -m ops.recovery restore "$(f)" --confirm "$(confirm)"

test-recovery: ## Testes operacionais puros, sem Docker ou banco
	$(OPS) -m unittest discover -s ops/tests -v

test-recovery-integration: ## Ensaia 2 backups e 1 restore; exige laboratório preparado e destino vazio
	$(OPS) -m ops.recovery_smoke

roles-lab-up: ## Sobe somente o banco sintético para permissões, sem portas
	$(OPS) -m ops.roles resources
	docker build -f backend/Dockerfile.prod -t aulas-ingles-recovery-tools:local .
	$(ROLES_COMPOSE) up -d --wait

roles-lab-prepare: ## Provisiona papéis, aplica migrations e seed somente no laboratório
	$(OPS) -m ops.roles prepare

test-roles: ## Recusas de privilégio, HTTP runtime, worker e backup limitado
	$(OPS) -m ops.roles_smoke

roles-lab-down: ## Encerra somente laboratório de papéis, preserva o volume
	$(OPS) -m ops.roles resources
	$(ROLES_COMPOSE) down
