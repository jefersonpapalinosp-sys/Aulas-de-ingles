# Aulas de Inglês

App de estudo construído sobre a série *Let's Learn English* (VOA, nível 1).
Catálogo de aulas, vocabulário com IPA, exercícios corrigidos no servidor,
progresso por usuário e revisão espaçada do que você errou.

**Estado: sprint 4 (repetição espaçada).** O vocabulário que você estuda vira
um deck SM-2 e volta no dia em que está prestes a ser esquecido.

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

`backend/openapi.json` é o baseline versionado, e ele é a fonte dos tipos do
frontend — nenhuma interface de API é escrita à mão.

```bash
make openapi                  # regrava o baseline depois de mudar a API
cd frontend && npm run gen:api  # regenera src/api/schema.d.ts a partir dele
```

Dois gates no CI garantem que ninguém esquece:

- um teste do backend falha se o contrato gerado pelo código divergir do
  arquivo commitado;
- um passo do frontend falha se `src/api/schema.d.ts` estiver desatualizado.

## Autenticação

| O quê | Onde fica | Por quê |
|---|---|---|
| Senha | Argon2id no banco | nunca em claro, nunca em log |
| Access token | **memória** do frontend, 15 min | o que o JS lê, um XSS também lê |
| Refresh token | cookie `httpOnly`, `SameSite=Lax`, `Path=/api/auth` | o JS não enxerga, e só a rota de refresh o recebe |
| Sessão de refresh | tabela `refresh_session` | sem isso `logout` seria decorativo |

O refresh **roda**: usar um invalida o anterior. Reapresentar um refresh já
usado devolve 401 e pede login — é o que limita o estrago de um token vazado.

Recarregar a página perde o access token (ele é de memória) e a aplicação
pede um `/refresh` automaticamente. Se o cookie ainda valer, a sessão volta
sem passar pela tela de login.

O browser fala com a API pelo proxy do Vite, na mesma origem. Isso não é
detalhe de conforto: cookie `httpOnly` com `credentials` **não funciona** com
`allow_origins=["*"]`, então a saída certa é a mesma origem, não CORS aberto.

### Correção de exercício

A resposta certa **não** faz parte do contrato de leitura. Mandá-la ao
navegador para o JavaScript comparar seria publicar o gabarito. Então:

| Ação | Endpoint |
|---|---|
| Responder (confere e **grava**) | `POST /api/exercises/{id}/attempt` |
| Ver o gabarito (o usuário pede) | `GET /api/exercises/{id}/answer` |
| Marcar / desmarcar aula | `PUT` / `DELETE /api/lessons/{n}/studied` |
| Meu progresso | `GET /api/me/progress` |

Ler o conteúdo das aulas é público; responder e marcar exigem conta.
Cada tentativa guarda **o texto exato digitado** — é isso que vai permitir,
na S4, descobrir *qual* item a pessoa erra, e não só que ela errou.

A comparação vive em `app/domain/answers.py`, isolada de banco e de HTTP:
ignora caixa, pontuação, espaço sobrando e tipo de apóstrofo — digitar
`Won't`, `wont` ou `won’t` não pode ser a diferença entre acerto e erro.

### Markdown no frontend

`src/components/Markdown.tsx` renderiza o subconjunto para nós do React. Não
existe `dangerouslySetInnerHTML` em lugar nenhum do projeto, então texto vindo
do banco nunca vira markup.

## Repetição espaçada

O algoritmo é o **SM-2**, o mesmo do Anki, em `app/domain/sm2.py` — função
pura, sem banco e sem relógio global: o `agora` entra como argumento, para o
teste simular trinta dias sem esperar trinta dias.

### A curva

Acertando sempre com nota máxima, uma carta volta em:

| revisão | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| **dias** | 1 | 6 | 16 | 45 | 130 | 390 |

Errar zera a sequência e conta um lapso, mas **não** zera o fator de
facilidade: a dificuldade que a carta já demonstrou é informação acumulada.

Dois detalhes que mudam o resultado e por isso estão fixados em teste:

- o intervalo usa o fator de facilidade **anterior** à revisão, como no SM-2
  original — inverter a ordem adianta o efeito em um passo;
- o fator é arredondado a duas casas em cada passo. Somar `0.1` em float
  acumula erro (`2.8 + 0.1 = 2.9000000000000004`), e esse erro chega ao
  intervalo: `45 × 2.9000000000000004` dá `130.50000000000003`, que arredonda
  para 131 em vez de 130.

### Como as cartas entram no deck

| Gatilho | O que entra |
|---|---|
| Marcar uma aula como estudada | todo o vocabulário da aula |
| Botão **+ revisar** na tabela de vocabulário | aquele item |
| Errar um exercício cuja resposta é um termo do vocabulário | aquele item |

O terceiro gatilho estava no plano como a fonte principal, mas vale para
**4 dos 62 exercícios** do bloco: eles treinam gramática, não palavra. O
grosso do deck vem de marcar a aula como estudada.

Adicionar é idempotente: um item que já está no deck não tem o agendamento
reiniciado — isso apagaria o histórico de quem já estuda.

### Fuso

`due_at` é `timestamptz` e sempre em UTC; a conversão acontece na borda.
A suíte roda idêntica sob `TZ=UTC`, `America/Sao_Paulo`, `Pacific/Kiritimati`
(UTC+14) e `Pacific/Midway` (UTC−11).

## Estrutura

```
backend/   app/{api,core,db,domain,schemas}  — FastAPI, uv, pytest
           alembic/                    — migrations
           openapi.json                — baseline do contrato
frontend/  src/api/                    — cliente tipado + schema GERADO
           src/components/             — Markdown, gramática, exercício
           src/pages/                  — mapa, aula, revisão, prova
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
