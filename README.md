# Aulas de Inglês

App de estudo construído sobre a série *Let's Learn English* (VOA, nível 1).
Catálogo de aulas, vocabulário com IPA, exercícios corrigidos no servidor,
progresso por usuário e revisão espaçada do que você errou.

**Estado: sprint 1 (modelo e conteúdo).** As 10 aulas do bloco 31–40 vivem no
Postgres e saem pela API. O frontend que consome isso entra na sprint 2.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 19 + TypeScript + Vite |
| Backend | FastAPI + SQLAlchemy 2.0 async + asyncpg |
| Banco | PostgreSQL 16 (container, volume nomeado) |
| Testes | pytest · Vitest · Playwright (a partir da S5) |

## Subir o projeto

Pré-requisitos: Docker e `make`. Mais nada — Python e Node rodam dentro dos containers.

```bash
git clone git@github.com:jefersonpapalinosp-sys/Aulas-de-ingles.git
cd Aulas-de-ingles
cp .env.example .env
make up
```

| Serviço | URL |
|---|---|
| Frontend | <http://localhost:5180> |
| API | <http://localhost:8010/api/health> |
| Aulas | <http://localhost:8010/api/lessons> |
| OpenAPI | <http://localhost:8010/docs> |
| Postgres | `localhost:5433` |

As portas não são as padrão de propósito: `5432`, `5444`, `5456`, `8000`, `8001`,
`8005`, `5173` e `5174` já estão em uso por outros projetos na máquina de origem.
Para mudar, edite o `.env` — nada está fixo no código.

## Comandos

```bash
make help     # lista tudo
make up       # sobe db + api + web
make down     # derruba (mantém o banco)
make reset    # derruba e apaga o volume do banco
make logs     # acompanha os logs
make health   # bate no /api/health
make migrate  # aplica as migrations
make seed     # carrega seed/lessons.json (idempotente)
make openapi  # regrava o baseline do contrato
make test     # pytest + vitest
make lint     # ruff + mypy + eslint + tsc
```

### Rodar fora do container

Útil para debugar com breakpoint. O banco continua no Docker.

```bash
make up        # sobe pelo menos o db
make api       # uvicorn no host, porta 8010
make web       # vite no host, porta 5180
```

## Como as peças se falam

```
navegador → :5180 Vite ──proxy /api──→ :8000 FastAPI ──asyncpg──→ :5432 Postgres
```

O browser **nunca** chama a API direto: tudo passa por `/api` na mesma origem,
via proxy do Vite. Isso elimina CORS em dev e deixa o caminho pronto para o
cookie `httpOnly` da sprint 3.

## Health check

`/api/live` é *liveness*: responde 200 enquanto o processo estiver de pé, sem
tocar em dependência alguma.

`/api/health` é *readiness*: abre uma conexão e pergunta a versão ao Postgres.

```bash
$ make health
{"status":"ok","db":"up","version":"PostgreSQL 16.10","env":"dev"}
HTTP 200
```

Com o banco fora do ar vira `503` com `"db":"down"` — é isso que faz o endpoint
valer alguma coisa:

```bash
docker stop aulas-db && make health   # HTTP 503
docker start aulas-db
```

## Conteúdo das aulas

### Modelo

```
lesson ─┬─ lesson_goal
        ├─ grammar_block ── grammar_row
        ├─ phrase
        ├─ vocab_item
        ├─ pronunciation_note
        └─ exercise ── exercise_answer
```

`exercise_answer` é tabela à parte porque um exercício aceita mais de uma
resposta certa (`should` e `ought to`, por exemplo) e todas valem igual.

O que está carregado hoje: **10 aulas**, 40 objetivos, 31 blocos de gramática
com 156 linhas, 76 frases, **115 itens de vocabulário**, 45 notas de pronúncia
e **62 exercícios** com 84 respostas aceitas.

### Formato do texto

Todo campo de texto exibível guarda um **subconjunto de Markdown** —
`**negrito**`, `*itálico*`, `` `código` `` e `~~riscado~~`. HTML cru não entra
no banco: elimina a superfície de XSS, deixa o seed editável à mão e mantém a
aparência sob controle do frontend. Há um teste que falha se HTML vazar no
payload.

### Seed

`seed/lessons.json` é a fonte do conteúdo. `make seed` é idempotente:

- `lesson`, `vocab_item` e `exercise` são atualizados no lugar, pela chave
  natural. A partir da S3 as tentativas e as cartas de revisão apontam para
  esses ids, e eles não podem trocar a cada novo seed.
- O resto é descritivo: apaga e reinsere.

### Contrato

`backend/openapi.json` é o baseline versionado. Um teste compara o contrato
gerado pelo código com o arquivo commitado e **falha se divergirem** — mudança
de contrato tem que aparecer no diff do PR, como decisão consciente.

```bash
make openapi   # regrava o baseline depois de mudar a API
```

## Estrutura

```
backend/   app/{api,core,db,schemas}   — FastAPI, uv, pytest
           alembic/                    — migrations
           openapi.json                — baseline do contrato
frontend/  src/                        — React, Vite, Vitest
infra/     compose.yml                 — db + api + web
seed/      lessons.json                — conteúdo das 10 aulas
```

## Convenções

- Trabalho em `sprint/N-slug`, entregue por PR com squash merge em `main`.
- *Conventional commits*.
- Toda migration precisa aplicar **e** reverter num banco limpo antes do merge.
- Teste que toca banco roda contra o Postgres do compose — mock de banco não
  conta como teste de integração.
- Tag `sN` a cada sprint fechada.

O plano completo das seis sprints está no roadmap do projeto.
