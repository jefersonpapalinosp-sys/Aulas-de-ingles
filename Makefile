# Aulas de Inglês — atalhos do dia a dia.
# `make up` precisa funcionar a partir de um clone limpo.

COMPOSE := docker compose --env-file .env -f infra/compose.yml
TEST_COMPOSE := docker compose -f infra/compose.test.yml
E2E_COMPOSE := docker compose --env-file infra/e2e.env -p aulas-ingles-e2e -f infra/compose.e2e.yml
RECOVERY_COMPOSE := docker compose --env-file infra/e2e.env -p aulas-ingles-recovery -f infra/compose.recovery.yml
UPGRADE_COMPOSE := docker compose --env-file infra/e2e.env -p aulas-ingles-upgrade42 -f infra/compose.upgrade.yml
OPS := uv run --project backend python
ROLES_COMPOSE := docker compose --env-file infra/e2e.env -p aulas-ingles-roles -f infra/compose.roles.yml
.DEFAULT_GOAL := help

.PHONY: help up down logs ps reset api web test test-api test-web test-e2e lint fmt health \
        migrate migration seed seed-plan editorial-audit editorial-reorder-plan openapi assist-gate assist-worker prod-up prod-down prod-logs \
        prod-seed backup restore cov test-db-up test-db-down test-api-prepare e2e-up e2e-down e2e-check \
        recovery-lab-up recovery-lab-prepare recovery-lab-down upgrade-lab-up upgrade-lab-prepare upgrade-lab-down backup-verify test-recovery \
        test-recovery-integration test-upgrade-integration roles-lab-up roles-lab-prepare test-roles roles-lab-down \
        notebook-benchmark review-benchmark speaking-benchmark writing-benchmark database-benchmark dialogue-benchmark \
        operations-check operations-alert public-probe cue-audit test-failure-rehearsal easypanel-env easypanel-check

help: ## Lista os comandos principais; help-all inclui laboratórios e ferramentas
	@grep -E '^[a-z0-9-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

help-all: ## Lista também ferramentas avançadas e laboratórios
	@grep -E '^[a-z0-9-]+:.*?##@? .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?##@? "};{printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

.PHONY: help-all

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

reset: ##@ Derruba tudo e APAGA o volume do banco
	$(COMPOSE) down -v

logs: ## Acompanha os logs
	$(COMPOSE) logs -f

ps: ## Estado dos containers
	$(COMPOSE) ps

health: ## Bate no /api/health e mostra a resposta
	@curl -s -o /dev/stdout -w "\nHTTP %{http_code}\n" http://localhost:$${API_HOST_PORT:-8010}/api/health

operations-check: ## Avalia readiness/alertas; lê OPERATIONS_TOKEN sem imprimi-lo
	$(OPS) -m ops.observability_check --base-url "$${OPERATIONS_BASE_URL:-http://127.0.0.1:8011}"

operations-alert: ## Para o cron da VM: silencioso quando está bom, falante quando não
	@$(OPS) -m ops.observability_check --base-url "$${OPERATIONS_BASE_URL:-http://127.0.0.1:8011}" > /tmp/aulas-gate.json 2>/tmp/aulas-gate.err \
		|| { echo "ALERTA operacional em $$(date -Is)"; cat /tmp/aulas-gate.json /tmp/aulas-gate.err 2>/dev/null; rm -f /tmp/aulas-gate.json /tmp/aulas-gate.err; exit 1; }
	@rm -f /tmp/aulas-gate.json /tmp/aulas-gate.err

public-probe: ## Probe externo do domínio público; não usa credencial
	$(OPS) -m ops.public_probe --base-url "$${PUBLIC_PROBE_ORIGIN:?defina PUBLIC_PROBE_ORIGIN}"

cue-audit: ## Inventaria cada cue/aula/versão e seu aceite auditivo humano
	$(OPS) -m ops.cue_audit_inventory --summary

test-failure-rehearsal: test-api-prepare ## Ensaia falhas controladas de banco, provedor e retomada do worker
	cd backend && uv run pytest -q \
		tests/test_maintenance.py::test_worker_recovers_database_failure_and_remains_cancellable \
		tests/test_writing.py::test_feedback_assistido_e_opcional_avaliavel_e_tem_fallback \
		tests/test_speaking.py::test_falha_do_provedor_mantem_audio_e_autoavaliacao \
		tests/test_speaking.py::test_worker_repete_com_backoff_e_chave_idempotente \
		tests/test_speaking.py::test_worker_retoma_job_interrompido_apos_timeout \
		tests/test_provider_incident.py

easypanel-env: ## Gera segredos locais; origin=https://dominio-publico é opcional
	python3 -m ops.easypanel_deploy init $(if $(origin),--origin "$(origin)",)

easypanel-check: ## Valida o arquivo privado e o Compose público sem exibir segredos
	python3 -m ops.easypanel_deploy check

api: .env ##@ Roda a API no host (contra o Postgres do compose)
	cd backend && DATABASE_URL=postgresql+asyncpg://aulas:aulas_local@localhost:5433/aulas_ingles \
		uv run uvicorn app.main:app --reload --port 8010

web: ##@ Roda o Vite no host
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

notebook-benchmark: test-api-prepare ##@ Mede Caderno 1k/10k só no PostgreSQL descartável
	$(OPS) -m ops.notebook_performance

dialogue-benchmark: test-api-prepare ##@ Mede histórico e Caderno com 1k/10k turnos sintéticos
	$(OPS) -m ops.dialogue_performance $(DIALOGUE_BENCHMARK_ARGS)

review-benchmark: test-api-prepare ##@ Mede Revisão 1k/10k só no PostgreSQL descartável
	$(OPS) -m ops.review_performance

speaking-benchmark: test-api-prepare ##@ Mede Speaking 1k/10k só no PostgreSQL descartável
	$(OPS) -m ops.speaking_performance $(SPEAKING_BENCHMARK_ARGS)

writing-benchmark: test-api-prepare ##@ Mede escrita 1k/10k só no PostgreSQL descartável
	$(OPS) -m ops.writing_performance $(WRITING_BENCHMARK_ARGS)

database-benchmark: test-api-prepare ##@ Mede usuários/eventos/jobs 1k/10k só no banco descartável
	$(OPS) -m ops.database_performance

test-web: ## vitest
	cd frontend && npm run test

lint: ## ruff + mypy + eslint + tsc
	cd backend && uv run ruff check . && uv run mypy app
	uv run --project backend mypy --config-file mypy-ops.ini
	cd frontend && npm run lint && npm run typecheck

fmt: ## Formata o backend
	cd backend && uv run ruff format . && uv run ruff check --fix .

migrate: ## Aplica as migrations pendentes
	$(COMPOSE) exec -T api alembic upgrade head

migration: ##@ Gera uma revisão a partir dos modelos — make migration m="texto"
	$(COMPOSE) exec -T api alembic revision --autogenerate -m "$(m)"

seed-plan: ## Prévia somente leitura do seed; código 1 se houver alterações bloqueadas
	$(COMPOSE) exec -T api python -m app.cli seed --dry-run

seed: ## Insere conteúdo novo; bloqueia alterações/omissões do existente (40B.1)
	$(COMPOSE) exec -T api python -m app.cli seed

editorial-audit: ## Audita rubricas/proveniência em snapshot somente leitura
	$(COMPOSE) exec -T api python -m app.cli editorial-audit

editorial-reorder-plan: ## Valida pacote de reordenação sem escrever; file=... é opcional
	$(COMPOSE) exec -T api python -m app.cli editorial-reorder-plan $(if $(file),--file "$(file)",)

openapi: ## Regrava o baseline do contrato em backend/openapi.json
	cd backend && uv run python -m app.openapi_dump

assist-gate: ## Avalia o piloto: make assist-gate modality=writing review=../config/assist-provider-review.json
	cd backend && uv run python -m app.cli assist-gate \
		--modality "$(modality)" --review-file "$(review)"

assist-worker: ##@ Processa um job pendente da fila assistida
	$(COMPOSE) exec -T worker python -m app.cli assist-worker --once

# ---------- estudo local (nome legado prod) ----------

# Credenciais dos papéis moram em secrets/ (ignorado pelo Git), nunca junto dos dumps.
PROD_ROLES := $(if $(wildcard secrets/roles-prod.env),--env-file secrets/roles-prod.env -f infra/compose.roles.prod.yml)
PROD := docker compose --env-file .env.prod -f infra/compose.prod.yml $(PROD_ROLES)

.env.prod:
	@echo "Crie o .env.prod a partir do .env.prod.example e troque os segredos." >&2
	@echo "  cp .env.prod.example .env.prod && openssl rand -hex 32" >&2
	@exit 1

prod-up: .env.prod ##@ Fluxo legado bloqueado; estudo local exige rollout pelo runbook
	@echo "Fluxo legado bloqueado: ele iniciava código antes de migration/seed." >&2
	@echo "Use o checklist versionado em docs/runbook_sprint_42.md." >&2
	@exit 1

prod-down: ##@ Para o estudo local em 5181 (mantém o volume)
	$(PROD) down

prod-logs: ##@ Logs do estudo local em 5181 (JSON)
	$(PROD) logs -f api

prod-seed: ##@ Seed genérico bloqueado no estudo local
	@echo "Seed completo genérico bloqueado; use plano editorial auditado por release." >&2
	@echo "Consulte docs/runbook_sprint_42.md." >&2
	@exit 1

# ---------- backup ----------

recovery-lab-up: ##@ Sobe laboratório de recuperação sem portas e sem volumes do aluno
	$(OPS) -m ops.recovery lab-resources
	docker build -f backend/Dockerfile.prod -t aulas-ingles-recovery-tools:local .
	$(RECOVERY_COMPOSE) up -d --wait --wait-timeout 120
	$(OPS) -m ops.recovery lab-resources

recovery-lab-prepare: ##@ Prepara apenas a origem vazia do laboratório, com WAV sintético
	$(OPS) -m ops.recovery lab-prepare

recovery-lab-down: ##@ Para só o laboratório de recuperação; preserva todos os seus volumes
	$(OPS) -m ops.recovery lab-resources
	$(RECOVERY_COMPOSE) down

upgrade-lab-up: ##@ Sobe DB-42; prepare a imagem anterior conforme operacao_local.md
	docker image inspect aulas-ingles-rollback42:local --format '{{.Id}}' >/dev/null
	$(OPS) -m ops.recovery upgrade-lab-resources
	docker build -f backend/Dockerfile.prod -t aulas-ingles-recovery-tools:local .
	$(UPGRADE_COMPOSE) up -d --wait --wait-timeout 120
	$(OPS) -m ops.recovery upgrade-lab-resources

upgrade-lab-prepare: ##@ Cria origem DB-42 diretamente na revisão anterior com dados sintéticos
	$(OPS) -m ops.recovery upgrade-lab-prepare

upgrade-lab-down: ##@ Para apenas o laboratório DB-42; preserva volumes e recibos
	$(OPS) -m ops.recovery upgrade-lab-resources
	$(UPGRADE_COMPOSE) down

backup: ## Banco + voz: make backup source=lab|dev|prod|public (local exige manutenção; public lê a VM por SSH)
	$(if $(filter public,$(source)),$(OPS) -m ops.public_backup capture $(if $(recipient),--recipient-file "$(recipient)",) $(if $(copy_to),--copy-to "$(copy_to)",),$(OPS) -m ops.recovery backup --source "$(source)")

backup-public-check: ## Pré-voo da stack pública: SSH, containers, papel de backup e revisão, sem capturar
	$(OPS) -m ops.public_backup check

backup-verify: ## Confere manifesto/checksums: make backup-verify f=backups/recovery/aulas-...
	$(OPS) -m ops.recovery verify "$(f)"

restore: ## Somente destino vazio isolado: make restore f=... confirm=aulas-ingles-recovery/target-db
	$(OPS) -m ops.recovery restore "$(f)" --confirm "$(confirm)"

test-recovery: ## Testes operacionais puros, sem Docker ou banco
	$(OPS) -m unittest discover -s ops/tests -v

test-recovery-integration: ##@ Ensaia 2 backups e 1 restore; exige laboratório preparado e destino vazio
	$(OPS) -m ops.recovery_smoke

test-upgrade-integration: ##@ Faz backup/restore/upgrade da revisão anterior e prova preservação
	$(OPS) -m ops.upgrade_smoke

roles-lab-up: ##@ Sobe somente o banco sintético para permissões, sem portas
	$(OPS) -m ops.roles resources
	docker build -f backend/Dockerfile.prod -t aulas-ingles-recovery-tools:local .
	$(ROLES_COMPOSE) up -d --wait

roles-lab-prepare: ##@ Provisiona papéis, aplica migrations e seed somente no laboratório
	$(OPS) -m ops.roles prepare

test-roles: ##@ Recusas de privilégio, HTTP runtime, worker e backup limitado
	$(OPS) -m ops.roles_smoke

roles-lab-down: ##@ Encerra somente laboratório de papéis, preserva o volume
	$(OPS) -m ops.roles resources
	$(ROLES_COMPOSE) down

backup-prune: ## Plano da janela 7 diários + 4 semanais em backups/recovery; dry-run, nada é apagado
	$(OPS) -m ops.recovery prune --dry-run

backup-prune-apply: ## Executa a poda planejada; preserva o pacote mais recente e .partial-* < 24 h
	$(OPS) -m ops.recovery prune --apply

.PHONY: backup-prune backup-prune-apply backup-public-check

# ---------- deploy público (EasyPanel por SSH) ----------

deploy-public: ## Publica um SHA de origin/main na stack pública: make deploy-public sha=<sha>
	bash ops/deploy_public.sh "$(sha)"

deploy-public-dry-run: ## Imprime os comandos do deploy sem contatar a VM: make deploy-public-dry-run sha=<sha>
	bash ops/deploy_public.sh --dry-run "$(sha)"

.PHONY: deploy-public deploy-public-dry-run
