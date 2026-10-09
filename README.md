# Aulas de Inglês

App de estudo construído sobre a série *Let's Learn English* da VOA. O catálogo já representa os
níveis 1 e 2, com unidades navegáveis, vocabulário com IPA, exercícios corrigidos no servidor,
progresso por usuário e revisão espaçada do que você errou.

**Estado: Sprints 6–14 e 20–25 concluídas; Sprint 26 implementada em piloto, com QA auditiva
manual e execução visual dos cenários browser pendentes.** Além do caderno, da conta, do painel
Hoje e da jornada multimodal, a aplicação possui catálogo multi-curso, mapas por unidade, rail
escalável, rotas canônicas por curso, laboratório retomável por aula e checkpoints curriculares
persistidos.
As **22 Aulas 31–52** e os checkpoints 40–44, 45–49 e 50–52 estão publicados no Level 1. O
fechamento do recorte separa conteúdo visto, aulas concluídas e desempenho apoiado por evidências;
as **Aulas 1–10** e os checkpoints 1–5 e 6–10 estão publicados no Level 2. As Aulas 11–30 desse nível
permanecem planejadas e indisponíveis, sem páginas vazias nem conteúdo fictício. Os recursos
assistidos ficam desligados por padrão até passarem pela avaliação humana.

O aplicativo trata como certificado interno apenas a conclusão do recorte 31–52. Depois das 22
aulas e dos três checkpoints atuais, libera por ação explícita uma consulta à página de revisão e
certificado da VOA, deixando claro que o certificado externo considera o curso oficial completo e
possui critérios próprios; nenhum download começa automaticamente.

O total de **52 aulas** exibido no catálogo corresponde à extensão oficial do Level 1. O recorte
curricular deste projeto começa na Aula 31: as Aulas 1–30 não estão no seed, e a conclusão
implementada é explicitamente a do recorte 31–52, não a publicação das 52 aulas pelo aplicativo.

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

Rotas úteis da unidade mais recente e do fechamento:

- mapa: <http://localhost:5180/cursos/voa-level-1/unidades/50-52>;
- checkpoint: <http://localhost:5180/cursos/voa-level-1/unidades/50-52/checkpoint>;
- avaliação escopada: <http://localhost:5180/cursos/voa-level-1/unidades/50-52/avaliacao>;
- conclusão: <http://localhost:5180/cursos/voa-level-1/conclusao>;
- mapa Level 2: <http://localhost:5180/cursos/voa-level-2/unidades/6-10>;
- checkpoint Level 2: <http://localhost:5180/cursos/voa-level-2/unidades/6-10/checkpoint>;
- classificação adjective/adverb: <http://localhost:5180/cursos/voa-level-2/aulas/8/exercicios>;
- revisão e caderno no mesmo contexto: `/revisar?course=voa-level-1&unit=50-52` e
  `/caderno?course=voa-level-1&unit=50-52`.

As portas não são as padrão de propósito: `5432`, `5444`, `5456`, `8000`, `8001`,
`8005`, `5173` e `5174` já estão em uso por outros projetos na máquina de origem.
Para mudar, edite o `.env` — nada está fixo no código.

## Comandos

```bash
make help       # lista tudo

# desenvolvimento
make up         # sobe db + api + worker + web, migra e semeia
make down       # derruba (mantém o banco)
make reset      # derruba e apaga o volume do banco
make logs       # acompanha os logs
make health     # bate no /api/health
make migrate    # aplica as migrations
make seed       # carrega seed/lessons.json (idempotente)
make openapi    # regrava o baseline do contrato

# testes
make test       # pytest + vitest
make cov        # pytest com relatório de cobertura
make test-e2e   # Playwright contra o compose de produção
make lint       # ruff + mypy + eslint + tsc

# produção local
make prod-up    # nginx + uvicorn + Postgres nas portas 5181/8011/5434
make prod-down
make prod-logs  # JSON, uma linha por requisição
make backup     # dump em backups/
make restore f=backups/aulas-....dump
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
course ── course_unit ─┬─ lesson ─┬─ lesson_goal
                       │          ├─ content_source
                       │          ├─ lesson_version
                       │          ├─ grammar_block ── grammar_row
                       │          ├─ phrase
                       │          ├─ lesson_media ── transcript_cue
                       │          ├─ writing_prompt
                       │          ├─ vocab_item
                       │          ├─ pronunciation_note
                       │          └─ exercise ─┬─ exercise_answer
                       │                       └─ exercise_hint
                       └─ course_review ── course_review_question

app_user ─┬─ study_session_progress ─┬─ lesson
          │                          └─ step_progress
          ├─ practice_session ─ practice_session_item ─┬─ exercise
          │                                             └─ exercise_attempt
          ├─ study_plan
          ├─ skill_evidence
          ├─ course_review_attempt ── course_review
          ├─ review_item ── lesson / origem da atividade
          ├─ media_progress ── lesson_media
          ├─ speaking_attempt ── transcription_job ── worker PostgreSQL
          └─ writing_draft ─┬─ writing_revision
                            └─ writing_feedback
```

`exercise_answer` é tabela à parte porque um exercício aceita mais de uma
resposta certa (`should` e `ought to`, por exemplo) e todas valem igual.

O que está carregado hoje: **32 aulas** — 22 do Level 1 e dez do Level 2 —, **cinco
checkpoints com 30 questões**, 128 objetivos, 97 blocos de gramática com 351 linhas, 186 frases,
**335 itens de vocabulário**, 111 notas de pronúncia, **32 mídias oficiais**, 158 trechos
selecionados, 289 falas de transcrição integral nas Aulas 32–40 do Level 1, **32 propostas de
escrita** e **287 exercícios** com 318 respostas aceitas e 487 dicas graduais. As Aulas 41–52 do
Level 1 e 1–10 do Level 2 usam cinco trechos selecionados com texto e tradução por aula, mas não
possuem transcrição integral. Os timestamps dos 50 trechos do Level 2 são conservadores e ainda
não foram validados por escuta humana. As 32 aulas possuem fonte oficial/autoral, estratégia,
versão e status editorial explícitos.

O Level 2 permanece deliberadamente parcial: as unidades 11–30 continuam `planned`, e a listagem
oficial da VOA não oferece um review 26–30. O projeto não apresenta um fechamento autoral desse
bloco como se fosse uma revisão oficial.

O laboratório agora também aceita `classification`: cada item recebe uma categoria em um
`select` nativo, a API rejeita respostas parciais ou adulteradas e o gabarito permanece somente no
servidor. A Aula 8 usa o tipo para “adjective ou adverb” como complemento autoral claramente
identificado; as Aulas 6 e 10 o reutilizam para relações espaciais e `hope/wish`.

Os packs autorais das Aulas 31, 38 e 40 estão na versão 2 e possuem objetivo pedagógico
explícito (`recognize`, `apply`, `correct`, `produce` ou `listen`) e duas dicas progressivas por
item. O payload inicial nunca inclui gabarito, texto da dica ou explicação; esses dados só são
liberados pelas ações autenticadas adequadas.

### Formato do texto

Todo campo de texto exibível guarda um **subconjunto de Markdown** —
`**negrito**`, `*itálico*`, `` `código` `` e `~~riscado~~`. HTML cru não entra
no banco: elimina a superfície de XSS, deixa o seed editável à mão e mantém a
aparência sob controle do frontend. Há um teste que falha se HTML vazar no
payload.

### Seed

`seed/courses.json` define cursos e unidades; `seed/lessons.json` guarda o conteúdo publicado.
`make seed` aplica os dois arquivos de forma idempotente:

- `lesson`, `vocab_item`, `exercise` e `writing_prompt` são atualizados no lugar, pela chave
  natural. A partir da S3 as tentativas e as cartas de revisão apontam para
  esses ids, e eles não podem trocar a cada novo seed.
- sessões de prática guardam a versão editorial e um fingerprint interno do recorte. Se o seed
  alterar enunciado, opção, dica, explicação ou resposta, a sessão antiga é detectada e não mistura
  correções de versões diferentes.
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

## Instalação e modo offline

O build de produção é uma PWA. Depois da primeira visita, o navegador pode instalar o app e
reabrir o shell e aulas públicas já visitadas sem conexão. O aviso de conectividade mostra
quantas tentativas aguardam envio; ao voltar à rede, a sessão é renovada e a fila sincroniza
automaticamente com a chave idempotente original.

O access token continua apenas em memória. O navegador guarda somente o perfil mínimo do
último aluno para associar corretamente a fila. Cada tentativa pendente preserva a chave
idempotente e, quando aplicável, sessão, curso e aula para reconciliar o runner depois da volta da
rede. Dados privados, gabaritos, progresso, revisão,
escrita, speaking, áudio e vídeo não entram no cache. Cada mídia declara licença, atribuição,
data de revisão e política offline na API. A política operacional está em
`docs/politica_midia_offline_2026-10-08.md`; a auditoria PWA e WCAG está em
`docs/auditoria_sprint13_qualidade_offline.md`.

O browser fala com a API pelo proxy do Vite, na mesma origem. Isso não é
detalhe de conforto: cookie `httpOnly` com `credentials` **não funciona** com
`allow_origins=["*"]`, então a saída certa é a mesma origem, não CORS aberto.

## Assistência opcional

Speech-to-text e feedback aberto de escrita são experimentos por opt-in e ficam desativados por
padrão. Sem eles, a autoavaliação oral e a rubrica determinística continuam funcionando. Quando
ativados, a interface identifica o conteúdo automatizado, destaca confiança inferior a 75%,
mostra a cota restante e permite avaliar ou excluir a transcrição sem apagar o áudio.

A API controla feature flags, cota diária, custo e retenção. Em produção, gateways precisam usar
HTTPS e token; texto e áudio não entram nos logs. Configuração, contrato HTTP, política de
privacidade, fallback e gate de avaliação humana estão em
`docs/avaliacao_sprint14_assistencia.md`.

O gate é executável e falha fechado. Copie
`config/assist-provider-review.example.json` para o arquivo local ignorado
`config/assist-provider-review.json`, preencha a homologação e rode uma modalidade por vez:

```bash
make assist-gate modality=writing review=../config/assist-provider-review.json
make assist-gate modality=transcription review=../config/assist-provider-review.json
```

O comando só produz métricas agregadas e retorna código `0` quando todos os critérios passam,
`1` quando a liberação continua bloqueada e `2` para configuração inválida. Ele não altera a
feature flag.

As transcrições usam uma fila durável no PostgreSQL. A API responde `202` depois de persistir o
job, e o serviço `worker` do Compose faz o processamento. Jobs interrompidos voltam para a fila,
falhas transitórias usam backoff e cada tentativa envia a mesma chave `Idempotency-Key` ao
gateway. Os limites são configurados por `ASSIST_JOB_MAX_ATTEMPTS`,
`ASSIST_JOB_RETRY_BASE_SECONDS`, `ASSIST_JOB_STALE_SECONDS` e
`ASSIST_WORKER_POLL_SECONDS`. Para consumir uma única pendência manualmente, use:

```bash
make assist-worker
```

### Ollama local para escrita

O backend também adapta diretamente a API local do Ollama. Para um piloto de desenvolvimento:

```dotenv
ASSISTED_FEATURES_ENABLED=true
ASSIST_PROVIDER_KIND=ollama
ASSIST_PROVIDER_NAME=ollama-qwen2.5-7b
ASSIST_OLLAMA_BASE_URL=http://host.docker.internal:11434
ASSIST_OLLAMA_MODEL=qwen2.5:7b
ASSIST_TRANSCRIPTION_URL=
```

Ollama atende somente ao feedback aberto de escrita neste projeto. Speaking, gravação,
autoavaliação e shadowing continuam locais, mas transcrição automática permanece indisponível
até existir um gateway de speech-to-text separado.

O modelo não decide se o texto está correto ou pronto. Primeiro, a aplicação executa a rubrica
determinística; o Ollama recebe somente os critérios reprovados e pode explicá-los. O JSON Schema
restringe a resposta a esses códigos, e o backend descarta sugestões inventadas ou relacionadas
a critérios que já passaram. Se todos os critérios passarem, nenhuma inferência é executada.

### Correção de exercício

A resposta certa **não** faz parte do contrato de leitura. Mandá-la ao
navegador para o JavaScript comparar seria publicar o gabarito. Então:

| Ação | Endpoint |
|---|---|
| Responder (confere e **grava**) | `POST /api/exercises/{id}/attempt` |
| Pedir dica gradual | `GET /api/exercises/{id}/hints/{level}` |
| Ver o gabarito (o usuário pede) | `GET /api/exercises/{id}/answer` |
| Avaliação por unidade | `GET /api/exercises?course={curso}&unit={unidade}` |
| Marcar / desmarcar aula | `PUT` / `DELETE /api/courses/{curso}/lessons/{n}/studied` |
| Ler / salvar retomada | `GET` / `PUT /api/courses/{curso}/lessons/{n}/study-session` |
| Ler / responder checkpoint | `GET /api/courses/{curso}/units/{unidade}/review` / `POST .../review/attempts` |
| Resumo privado de conclusão | `GET /api/courses/{curso}/completion` |
| Ler / salvar rascunho | `GET` / `PUT /api/writing/prompts/{id}/draft` |
| Criar versão do texto | `POST /api/writing/prompts/{id}/versions` |
| Analisar critérios | `POST /api/writing/prompts/{id}/feedback` |
| Meu progresso contextual | `GET /api/me/progress?course={curso}&unit={unidade}` |
| Revisão contextual | `GET /api/review/due?course={curso}&unit={unidade}` |

Ler o conteúdo das aulas é público; responder e marcar exigem conta.
Os endpoints antigos em `/api/lessons/...` permanecem compatíveis e resolvem o Level 1.
Cada tentativa guarda **o texto exato digitado** — é isso que vai permitir,
na S4, descobrir *qual* item a pessoa erra, e não só que ela errou.

A comparação vive em `app/domain/answers.py`, isolada de banco e de HTTP:
ignora caixa, pontuação, espaço sobrando e tipo de apóstrofo — digitar
`Won't`, `wont` ou `won’t` não pode ser a diferença entre acerto e erro.
Quando há erro, o mesmo domínio o classifica como palavra faltando, palavra
extra, ordem, ortografia ou escolha de palavra. O cliente recebe marcações
somente sobre o que digitou; a resposta esperada continua protegida. Cada
requisição também leva uma chave de idempotência, evitando duplicar tentativas
quando a conexão oscila.

Na Aula 31, o motor já renderiza lacuna, múltipla escolha, transformação, ditado e ordenação.
A primeira dica
pode ser aberta diretamente; a segunda exige uma tentativa errada. O gabarito
continua em uma ação separada e explícita.

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
**4 dos 63 exercícios** do bloco: eles treinam gramática, não palavra. O
grosso do deck vem de marcar a aula como estudada.

Adicionar é idempotente: um item que já está no deck não tem o agendamento
reiniciado — isso apagaria o histórico de quem já estuda.

### Fuso

`due_at` é `timestamptz` e sempre em UTC; a conversão acontece na borda.
A suíte roda idêntica sob `TZ=UTC`, `America/Sao_Paulo`, `Pacific/Kiritimati`
(UTC+14) e `Pacific/Midway` (UTC−11).

## Produção local

O compose de produção é diferente do de dev de propósito: bundle buildado
servido por **nginx**, API sob uvicorn com workers e **sem reload**, imagem
sem pytest/ruff/mypy dentro, processo rodando como usuário sem root.

```bash
cp .env.prod.example .env.prod
openssl rand -hex 32          # para o JWT_SECRET
make prod-up                  # http://localhost:5181
```

Diferente do `.env` de dev, aqui **não há default para segredo**: a stack
recusa subir sem `POSTGRES_PASSWORD`, `DATABASE_URL` e `JWT_SECRET` próprios,
e a aplicação valida que o segredo tem pelo menos 32 bytes.

`COOKIE_SECURE=false` em localhost é intencional: com `Secure` ligado o
navegador simplesmente não envia o cookie por HTTP, e o login para de
funcionar. Ligue junto com HTTPS, não antes.

### Observabilidade

Uma linha de log em JSON por requisição, com `request_id` que também volta no
cabeçalho `X-Request-ID`. Um id vindo de fora é respeitado, para um proxy na
frente conseguir amarrar o rastro de ponta a ponta.

```json
{"ts":"2026-10-07T19:43:50.752Z","level":"INFO","logger":"app.request",
 "msg":"GET /api/health 200","request_id":"3bb1c073923e4001",
 "method":"GET","path":"/api/health","status":200,"duration_ms":27.6}
```

`/api/live` é *liveness* e não toca em dependência; `/api/health` é
*readiness* e abre conexão no banco.

### Backup e restore

```bash
make backup                              # backups/aulas-AAAAMMDD-HHMM.dump
make restore f=backups/aulas-....dump    # --clean --if-exists
```

Testado derrubando o schema inteiro (`drop schema public cascade`) e
restaurando: usuários, cartas de revisão e tentativas voltam intactos.

## Testes

| Suíte | O que cobre | Como rodar |
|---|---|---|
| pytest | 221 testes contra o Postgres do compose | `make test-api` |
| vitest | 157 testes de componente, fluxo e parser | `make test-web` |
| Playwright | 39 cenários em desktop e mobile (78 execuções), contra **produção** | `make prod-up && make test-e2e` |

Na Sprint 26, pytest, Vitest, lint, tipagem, build e orçamento de bundle foram executados com
sucesso. Os 78 casos Playwright foram listados e compilados, mas a execução visual permanece
pendente porque o ambiente controlado da entrega não disponibilizou um navegador.

O frontend possui uma **jornada guiada** nas 32 aulas publicadas dos dois níveis. Ela divide o
estudo em preparar, assistir, estudar, praticar e revisar. A etapa atual é salva localmente e na conta,
permitindo continuar em outro navegador. Em “Assistir”, o player usa o áudio oficial da VOA,
sincroniza a posição na conta e oferece velocidade, saltos de cinco segundos, repetição A–B e
158 trechos selecionados com tradução opcional. As atividades de compreensão são corrigidas pela
API sem enviar o gabarito antes da
resposta. Na revisão, o aluno pode praticar *shadowing*, gravar a voz localmente, comparar com
o modelo e salvar uma autoavaliação. O áudio permanece local por padrão; somente após
consentimento explícito pode ser salvo no volume privado da conta, ouvido no histórico e
excluído junto com seus metadados. Essa etapa também oferece produção escrita com autosave,
backup local em caso de falha, checklist de critérios e histórico de versões privado por
conta, incluindo comparação visual entre versões. O **Caderno** centraliza notas por aula,
frases favoritas, exemplos, erros, perguntas, textos e gravações; o aluno também pode exportar
seus dados em JSON. A página completa da aula continua disponível durante a evolução do novo
fluxo.

Na entrada, o painel **Hoje** sugere deterministicamente revisar itens vencidos, retomar a
sessão mais recente ou começar a próxima aula — e sempre explica o motivo. O plano semanal é
editável e não bloqueia a navegação livre. Gramática, listening, escrita e fala acumulam
evidências separadas; para evitar falsa precisão, o percentual de uma competência só aparece
depois de três evidências. Tempo aproximado, conclusão e retomada são registrados por etapa.

A revisão usa uma fila única para vocabulário, erros gramaticais, listening, frases favoritas,
prompts de escrita e trechos de speaking. O aluno pode filtrar por tipo, competência e duração,
entender por que cada item voltou e suspender, reativar ou excluir uma revisão. O intervalo SM-2
continua orientado pelo desempenho, com ajuste por tipo de atividade. A migração copia IDs,
intervalos, facilidade, repetições, lapsos e vencimentos do deck antigo sem recalculá-los.

O CI roda os três, mais: `ruff`, `mypy --strict`, `eslint`, `tsc`, o build de
produção, migrations para frente e para trás, seed rodado duas vezes, piso de
**90% de cobertura**, orçamento de bundle e a suíte inteira de novo sob
`TZ=Pacific/Kiritimati`.

## Como adicionar uma aula nova

1. Confirme ou crie o curso e a unidade em `seed/courses.json`.
2. Acrescente o objeto em `seed/lessons.json`, incluindo `course_slug`, `unit_slug`, `slug` e
   `position` (texto em Markdown, nunca HTML).
3. `make seed` — é idempotente, as aulas existentes não são recriadas.
4. Se o modelo mudou: `make migration m="o que mudou"`, confira o arquivo
   gerado, e `make migrate`.
5. Se a API mudou: `make openapi` e, no frontend, `npm run gen:api`. Os dois
   arquivos entram no mesmo commit que a mudança.

## Estrutura

```
backend/   app/{api,core,db,domain,schemas}  — FastAPI, uv, pytest
           alembic/                    — migrations
           openapi.json                — baseline do contrato
frontend/  src/api/                    — cliente tipado + schema GERADO
           src/components/             — Markdown, gramática, exercício
           src/features/               — jornada guiada, mídia, speaking e writing
           src/pages/                  — mapa, aula, estudo, revisão, prova, conclusão
infra/     compose.yml                 — dev: db + api + worker + web
           compose.prod.yml            — prod local: nginx + uvicorn + db
e2e/       testes/                     — Playwright, fluxo completo
seed/      courses.json                — catálogo de cursos e unidades
           lessons.json                — conteúdo das 32 aulas publicadas
```

## Convenções

- Trabalho em `sprint/N-slug`, entregue por PR com squash merge em `main`.
- *Conventional commits*.
- Toda migration precisa aplicar **e** reverter num banco limpo antes do merge.
- Teste que toca banco roda contra o Postgres do compose — mock de banco não
  conta como teste de integração.
- Tag `sN` a cada sprint fechada.

O plano das Sprints 20–25 está em
[docs/plano_sprints_20_25_frontend_cursos_exercicios_2026-10-08.md](docs/plano_sprints_20_25_frontend_cursos_exercicios_2026-10-08.md).
O plano de expansão das Sprints 26–30 está em
[docs/plano_sprints_26_30_level_2_2026-10-09.md](docs/plano_sprints_26_30_level_2_2026-10-09.md).
