# Aulas de Inglês

Aplicativo de estudo baseado em *Let's Learn English*, da VOA: **52 aulas do
Level 1 e 30 do Level 2**, com 16 checkpoints no recorte publicado.
Inclui vocabulário com IPA, exercícios corrigidos no servidor, áudio, escrita,
revisão espaçada, Caderno, progresso e exportação dos dados do aluno.

Recursos assistidos são opcionais e permanecem desligados por padrão. Testes
automatizados não substituem a homologação pedagógica, o piloto ou a avaliação
com leitores de tela. O certificado interno não é um certificado da VOA.

## Começar no desenvolvimento

Pré-requisitos: Docker e Make. Para ferramentas fora dos containers, instalar
`uv` com Python 3.12 e Node compatível com o projeto.

```bash
git clone git@github.com:jefersonpapalinosp-sys/Aulas-de-ingles.git
cd Aulas-de-ingles
cp .env.example .env
make up
```

| Serviço de desenvolvimento | Endereço |
|---|---|
| Aplicativo | <http://localhost:5180> |
| Saúde da API | <http://localhost:8010/api/health> |
| OpenAPI | <http://localhost:8010/docs> |
| PostgreSQL | `localhost:5433` |

`make up` prepara somente o desenvolvimento. O estudo local com dados do aluno
fica em **5181**, no projeto `aulas-ingles-prod`. A produção pública fica no
**EasyPanel**, com configuração própria; consulte os runbooks antes de operar.

## Comandos principais

```bash
make help          # comandos do dia a dia
make help-all      # inclui ferramentas avançadas e laboratórios
make logs          # logs do desenvolvimento
make health        # readiness do desenvolvimento
make down          # encerra desenvolvimento, preservando volumes
make seed-plan     # prévia editorial somente leitura
make openapi       # atualiza o contrato OpenAPI versionado
make lint          # Ruff, mypy, ESLint e TypeScript
```

O seed bloqueia alterações editoriais incompatíveis. Migrations e seed não
são comandos genéricos de reparação. `make prod-up` e `make prod-seed` permanecem
bloqueados; o estudo exige a sequência de release documentada.

## Testes

Instalar as dependências de `frontend` e `e2e` com `npm ci` nos respectivos
diretórios. Para a suíte completa de navegador, instalar os browsers definidos
no Playwright: `cd e2e && npx playwright install`.

```bash
make test-api       # PostgreSQL exclusivo em 55435; migra, semeia e testa
make test-db-down   # encerra esse banco; mantém seu volume sintético
make test-web       # Vitest
make test-recovery  # testes puros dos scripts operacionais
make e2e-up         # stack E2E exclusiva em 5198
make test-e2e       # verifica isolamento antes de executar Playwright
make e2e-down       # encerra somente E2E, preservando volumes
```

Nunca executar testes mutáveis no desenvolvimento, estudo ou produção. As
fixtures verificam ambiente, URL, identidade do banco e privilégios; não há
fallback para outro banco. Detalhes na
[política de isolamento e migrations](docs/politica_migrations_downgrade_2026-10-29.md).

O CI verifica contrato, lint/tipos, cobertura, navegadores, segurança, backup,
restore e upgrade com leitura pela aplicação anterior. Resultados e pendências
por entrega estão no [plano vigente](docs/plano_sprints_44_49_frentes_e_assistente_de_fala_2026-10-21.md).

## Arquitetura

React 19 + TypeScript + Vite no frontend; FastAPI + SQLAlchemy async no backend;
PostgreSQL 16 e worker separado para jobs. O navegador usa `/api` na mesma
origem, via proxy do Vite no desenvolvimento e nginx no release.

| Pasta | Responsabilidade |
|---|---|
| `frontend/` | Interface, PWA, sincronização e armazenamento local |
| `backend/` | API, serviços, worker, modelos e migrations |
| `seed/` | Conteúdo curricular versionado |
| `e2e/` | Playwright e guardas da stack descartável |
| `infra/` | Compose, imagens e configuração EasyPanel |
| `ops/` | Backup, recuperação, deploy, métricas e ensaios |
| `docs/` | Runbooks, contratos, planos e histórico |

`/api/live` verifica o processo; `/api/health` verifica banco e schema sem expor
versões internas. Métricas e detalhes operacionais exigem autenticação própria.
Texto, áudio e credenciais do aluno não entram em logs.

## Documentação

- [Operação vigente: ambientes, manutenção, testes e recuperação](docs/operacao_local.md).
- [Produção pública e deploy no EasyPanel](docs/deploy_easypanel.md).
- [Checklist de release e incidentes](docs/runbook_sprint_42.md).
- [Sequência de implantação no estudo](docs/sprint_43_implantacao_estudo_2026-10-16.md).
- [Referência técnica, catálogo e inclusão de aulas](docs/guia_tecnico.md).
- [Política de migrations/downgrade](docs/politica_migrations_downgrade_2026-10-29.md).
- [Política de migrações do storage](docs/politica_migracoes_storage_2026-10-29.md).
- [Rotação de segredos: ensaio e ordem operacional](docs/rotacao_segredos_2026-10-29.md).
- [Plano e pendências das Sprints 44–49](docs/plano_sprints_44_49_frentes_e_assistente_de_fala_2026-10-21.md).
- [Changelog das entregas](docs/changelog.md).
- [Histórico operacional das Sprints 37–44](docs/historico_operacao_sprints_37_44.md).

Pacotes privados ficam fora do Git, com manifesto e recibos. O restore aceita
somente destino vazio e isolado; não existe downgrade destrutivo automático.
Configuração local, credenciais, dumps e gravações não devem ser versionados.
