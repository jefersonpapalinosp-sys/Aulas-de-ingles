# Aulas de Inglês

App de estudo construído sobre a série *Let's Learn English* da VOA. O catálogo já representa os
níveis 1 e 2, com unidades navegáveis, vocabulário com IPA, exercícios corrigidos no servidor,
progresso por usuário e revisão espaçada do que você errou.

**Estado: Level 1 e Level 2 completos no recorte curricular do aplicativo.** As Sprints
31–36 publicaram as Aulas 1–30 do Level 1, e o fechamento posterior da unidade 31–40
encerrou a lacuna entre seus checkpoints. Além do caderno, da conta, do painel Hoje e
da jornada multimodal, a aplicação possui catálogo multi-curso, mapas por unidade, rail
escalável, rotas canônicas por curso, laboratório retomável por aula e checkpoints
curriculares persistidos.

O Level 1 publica **52 de 52 aulas e dez checkpoints**. O Level 2 publica **30 de 30
aulas e seis checkpoints**; seu fechamento 26–30 é autoral porque a VOA não oferece
uma revisão oficial com esse recorte. Recursos assistidos continuam desligados por
padrão até passarem pela avaliação humana.

O certificado interno acompanha somente o conteúdo efetivamente publicado no Level 1:
agora exige **52 aulas e dez checkpoints**. Ele não é um certificado da VOA. A consulta
ao certificado externo é sempre explícita, respeita os critérios próprios da fonte e
nunca inicia download automaticamente. Quem havia cumprido a regra anterior de nove
checkpoints precisa concluir também o fechamento 31–40 na versão atual; nenhuma
tentativa é criada ou aprovada automaticamente.

O total de **52 aulas** exibido no catálogo corresponde à extensão oficial do Level 1;
o campo de aulas publicadas deixa visível o recorte atualmente disponível no aplicativo.

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

Rotas úteis do fechamento 31–40:

- mapa: <http://localhost:5180/cursos/voa-level-1/unidades/31-40>;
- checkpoint: <http://localhost:5180/cursos/voa-level-1/unidades/31-40/checkpoint>;
- avaliação escopada: <http://localhost:5180/cursos/voa-level-1/unidades/31-40/avaliacao>;
- conclusão: <http://localhost:5180/cursos/voa-level-1/conclusao>;
- mapa Level 2: <http://localhost:5180/cursos/voa-level-2/unidades/26-30>;
- checkpoint Level 2: <http://localhost:5180/cursos/voa-level-2/unidades/26-30/checkpoint>;
- exercícios da Aula 40: <http://localhost:5180/cursos/voa-level-1/aulas/40/exercicios>;
- revisão e caderno no mesmo contexto: `/revisar?course=voa-level-1&unit=31-40` e
  `/caderno?course=voa-level-1&unit=31-40`.

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
make test       # pytest em banco exclusivo de testes + vitest
make cov        # prepara o banco exclusivo e roda pytest com cobertura
make test-db-down # para somente o banco de testes; mantém o volume
make e2e-up     # stack E2E exclusiva em 5198 (não usa dev/prod)
make test-e2e   # confere isolamento e executa Playwright
make e2e-down   # para somente E2E, mantém os volumes sintéticos
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

O que está carregado hoje: **82 aulas** — 52 do Level 1 e 30 do Level 2 —,
**16 checkpoints com 100 questões**, 328 objetivos, 247 blocos de gramática com 879
linhas, 436 frases, **835 itens de vocabulário**, 261 notas de pronúncia, **82 mídias
oficiais**, 408 trechos selecionados, 289 falas de transcrição integral nas Aulas
32–40 do Level 1, **82 propostas de escrita** e **687 exercícios** com
**769 respostas aceitas** e 1.287 dicas graduais. As aulas sem transcrição integral usam trechos
selecionados com texto e tradução; as unidades recentes seguem cinco por aula. Todas possuem
fonte oficial/autoral, estratégia, versão e status editorial explícitos.

O Level 2 está completo. Como a listagem oficial da VOA não oferece um review 26–30,
o fechamento desse bloco é identificado como autoral e nunca apresentado como revisão
oficial. A conferência auditiva dos cues das Sprints 27–30 e 34–36 permanece uma etapa
manual; os testes automatizados garantem limites, ordem, sobreposição e densidade do
texto, mas não substituem a escuta humana.

O fechamento 31–40 do Level 1 também é autoral: não existe review oficial com esse
recorte exato. Os reviews oficiais
[30–34](https://learningenglish.voanews.com/a/lets-learn-english-lesson-30-34-review/3569049.html),
[35–39](https://learningenglish.voanews.com/a/lets-learn-english-review-lessons-35-39/3625403.html)
e [40–44](https://learningenglish.voanews.com/a/lets-learn-english-review-lessons-40-44/3688551.html)
servem somente como referências curriculares adjacentes. As dez questões, alternativas,
explicações e correção são do projeto; a retomada de listening usa o áudio oficial da
Aula 40 sem duplicar a mídia.

O laboratório também aceita `classification`: cada item recebe uma categoria em um
`select` nativo, a API rejeita respostas parciais ou adulteradas e o gabarito permanece
somente no servidor. O tipo atende desde “adjective ou adverb” até relações espaciais,
tempos verbais, funções gramaticais e as classificações pedagógicas das Aulas 16–30.

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

Após a separação de papéis da Sprint 37, o ambiente local existente usa também
infra/compose.roles.prod.yml e backups/recovery/roles-prod.env. Os comandos
antigos prod-up/prod-seed são bloqueados nesse perfil. Para manutenção e
retomada, siga o [runbook local](docs/operacao_sprint_37.md); não reinicie
código novo antes de aplicar migrations compatíveis.

Diferente do `.env` de dev, aqui **não há default para segredo**: a stack
recusa subir sem `POSTGRES_PASSWORD`, `DATABASE_URL` e `JWT_SECRET` próprios,
e a aplicação valida que o segredo tem pelo menos 32 bytes.

`COOKIE_SECURE=false` em localhost é intencional: com `Secure` ligado o
navegador simplesmente não envia o cookie por HTTP, e o login para de
funcionar. Ligue junto com HTTPS, não antes.

### Observabilidade

Uma linha de log em JSON por requisição, com `request_id` que também volta no
cabeçalho `X-Request-ID`. Um id externo só é aceito com até 128 caracteres
ASCII seguros (letras, números, ponto, hífen ou underscore); caso contrário
um identificador novo é gerado, sem registrar o valor inválido.

```json
{"ts":"2026-10-07T19:43:50.752Z","level":"INFO","logger":"app.request",
 "msg":"GET /api/health 200","request_id":"3bb1c073923e4001",
 "method":"GET","path":"/api/health","status":200,"duration_ms":27.6}
```

`/api/live` é *liveness* e não toca em dependência; `/api/health` é
*readiness* e abre conexão no banco.

### Backup e restore

Os comandos da DB-37 substituem as receitas legadas. Agora o backup é um
**diretório com PostgreSQL + voz + manifesto/checksums**, não um `.dump`
isolado. O restore aceita **somente o destino vazio do laboratório**, nunca
desenvolvimento/produção. Requisitos: Docker local por socket Unix, Compose,
`uv` e Python 3.12 do projeto (não o Python 3.9 fornecido pelo macOS).

```bash
make test-recovery                 # testes puros, sem banco
make recovery-lab-up               # projeto/volumes próprios, sem portas
make recovery-lab-prepare          # só origem vazia; seed + WAV sintético
make test-recovery-integration     # 2 backups, restore e recusa de repetição
make recovery-lab-down             # encerra só o laboratório; mantém volumes
```

Alternativa por etapas, **em vez** de executar o ensaio integrado acima:

```bash
make backup source=lab
# Copie o caminho completo publicado pelo comando; não escolha um .partial-*.
make backup-verify f=backups/recovery/aulas-IDENTIFICADOR-EXATO
make restore f=backups/recovery/aulas-IDENTIFICADOR-EXATO confirm=aulas-ingles-recovery/target-db
```

`make backup source=prod` exige uma **janela de manutenção autorizada**: API,
worker e qualquer outro escritor devem permanecer parados durante toda a
captura. O comando verifica os serviços, mounts e conexões antes/depois,
mas não os para, não mata sessões e não impede um administrador de iniciar
outros escritores. Não há garantia de snapshot online atômico entre banco
e filesystem. No fechamento técnico da Sprint 37, o backup real foi restaurado
em destino isolado antes da migration. Há um segundo pacote pós-migration
verificado, capturado pelo papel limitado de backup. Detalhes e limites no
[runbook local](docs/operacao_sprint_37.md).

Os pacotes ficam em `backups/recovery/`, com diretórios 700 e arquivos 600,
fora do Git e do contexto de build Docker. Falhas preservam `.partial-*`
sem anunciá-los como válidos. Verificar checksums não substitui o restore.
O destino ocupado é recusado sem limpeza; após o primeiro ensaio ele deve
ser preservado. Não existe reset automático nem suporte a `--clean`.

Checksums detectam alteração, **não autenticam nem criptografam** o pacote.
Somente restaure dumps de origem confiável; o laboratório não é sandbox de
SQL malicioso. Por decisão de Jeferson para o desenvolvimento local, as cópias
ficam neste Mac (FileVault ativo, sem criptografia independente ou cópia externa).
Metas acordadas: RPO 24h, RTO 60min a validar, retenção manual 7 diários + 4
semanais. Sem agendamento instalado ou SLA garantido. Detalhes históricos no
[registro DB-37](docs/sprints_37_42_banco_de_dados_2026-10-13.md#sétimo-incremento--backup-conjunto-e-restore-isolado-13102026).

## Testes

| Suíte | O que cobre | Como rodar |
|---|---|---|
| pytest | Unitários e integração em PostgreSQL exclusivo, com guardas de isolamento | `make test-api` |
| vitest | Componentes, fluxo, armazenamento e parser | `make test-web` |
| Playwright | Fluxos completos em desktop e mobile, na stack exclusiva | `make e2e-up` e `make test-e2e` |

### Banco exclusivo para testes backend (Sprint 37)

`make test-api` e `make cov` iniciam `infra/compose.test.yml`, verificam o
destino e aplicam migrations/seed antes da suíte. O projeto Compose é
`aulas-ingles-test`, o volume é `aulas-ingles-test_test_pgdata` e a porta é
`127.0.0.1:55435`. Nada disso compartilha o banco de desenvolvimento ou de
produção local. Não é necessário executar `make up` nem `make prod-up`.

A suíte usa o banco `aulas_ingles_test` e o papel `aulas_test`, sem superusuário,
criação de bancos ou criação de roles. Esse papel é proprietário **somente do
banco descartável**, pois as migrations de teste precisam criar tabelas; ele
não representa o futuro papel runtime da aplicação. As credenciais desse
Compose são públicas, exclusivas de teste e não devem ser usadas em produção.

Antes da primeira operação da aplicação em cada conexão física, a guarda
confere ambiente, URL, banco efetivo, usuário, marcador de descarte e
privilégios. Uma URL de desenvolvimento/produção, marcador ausente ou papel
administrativo aborta a execução; não existe fallback para as portas 5433/5434.
O preflight também protege a preparação e o Alembic em `APP_ENV=test`.

Se o terminal exporta `DATABASE_URL` ou `APP_ENV` de outro ambiente, a execução
é recusada, sem sobrescrever essas variáveis silenciosamente. Use um terminal
sem essa configuração. `TEST_DATABASE_URL` é opcional para outro host/porta de
teste, mas exige os mesmos banco, papel e marcador; se `DATABASE_URL` também
estiver definida, ambas precisam coincidir. O CI backend usa a mesma topologia
e as mesmas guardas.

Depois de preparar a base, é possível rodar `cd backend && uv run pytest -q`.
Testes de regras puras não abrem conexão nem executam limpeza de usuários:

```bash
cd backend
uv run pytest -q tests/test_sm2.py tests/test_writing_domain.py
```

`make test-db-down` para apenas o ambiente de testes, preservando seu volume.
Uma base separada, `aulas_test_sentinel`, contém um registro sintético para
verificar isolamento; o papel da suíte não tem permissão de conexão nela.

### Stack exclusiva para E2E (Sprint 37)

Instale uma vez `cd e2e && npm ci && npx playwright install chromium`. Na raiz:

```bash
make e2e-up     # constrói imagens próprias e prepara somente o banco sintético
make test-e2e   # desktop + mobile; cria contas sintéticas, nunca use sua conta real
make e2e-down   # encerra os containers E2E; não remove seus volumes
```

`infra/compose.e2e.yml` usa projeto fixo `aulas-ingles-e2e`, origem exclusiva
`http://127.0.0.1:5198` e volumes próprios `aulas-ingles-e2e_pgdata` e
`aulas-ingles-e2e_speaking_data`. Não lê `.env`/`.env.prod`, não publica porta
de PostgreSQL/API e não herda os volumes globais da produção. O CI usa o mesmo
comando. Prepare aplica migrations/seed sob a guarda de identidade do banco;
a API só sobe após a preparação terminar e o web espera o readiness da API.

São os Dockerfiles de produção (bundle/nginx e API sem reload), mas com
`APP_ENV=test` para habilitar guardas, credenciais públicas **somente de teste**
e assistência externa desabilitada. Não há worker neste escopo; isto não
homologa configuração/segredos de produção nem processamento assistido.

Antes de criar contas, o setup do Playwright confere projeto, rede, portas,
mounts, labels/driver dos volumes, configuração da API, identidade/privilégios
reais da conexão e readiness HTTP. A base sentinela sintética é lida antes e
depois da suíte. Falha de verificação aborta, sem fallback para outro ambiente.
`cd e2e && npm test` também executa essa guarda. Overrides de `E2E_BASE_URL`
para 5180/5181 ou qualquer outra origem são recusados; testes exigem acesso
ao Docker local via socket Unix (macOS/Linux). Endpoints Docker TCP/SSH são
recusados também antes de subir/parar a stack. `cd e2e && npm run test:safety`
testa as recusas sem banco.
Estas barreiras evitam enganos operacionais; não são isolamento contra um
administrador que altere o daemon/configuração durante a execução.

Há uma suíte separada para fila offline e recuperação: `cd e2e && npm run test:queue`.
Ela inicia seu próprio frontend em `127.0.0.1:5197`, com API simulada e sem proxy
ou banco. Exige dependências de `frontend`/`e2e` e Chromium do Playwright
(`cd e2e && npx playwright install chromium`). Não equivale à suíte integrada
dos comandos acima e pode rodar sem iniciar a stack integrada.

### Escrita v2 — Sprint 37

Atualização da Sprint 37: a escrita usa `writing-rules-v2`, com palavras e
expressões literais, alternativas `any/all`, quantidade de ocorrências/termos
distintos e falas entre aspas. Os novos feedbacks guardam um snapshot e hash da
rubrica usada; os antigos ficam identificados como `legacy-v1`, sem reavaliação.
O workspace e o Caderno explicitam que passar nos critérios não garante gramática
correta ou atendimento completo à proposta.

A migration `c95f3d8ba042` deve preceder a ativação do backend novo, seguida da
carga das rubricas atualizadas. Nesta entrega, ambos foram ensaiados somente na
base descartável; a atualização das bases de estudo não foi executada. Evidências,
contrato e pendências estão no [registro da Sprint 37](docs/sprints_37_42_backend_2026-10-13.md).

Validação deste incremento: 668 testes backend (93,79% de cobertura), 169 testes
frontend, lint, tipagem, build e orçamento de bundle aprovados. Testes E2E e
homologação visual não foram repetidos nesta entrega.

### Sessão e reenvio — Sprint 37, terceiro incremento

POST/PUT passam a preparar o corpo antes do primeiro envio e repetem uma única
vez após 401 e renovação válida. JSON, upload de Blob e downloads privados
compartilham a renovação na mesma aba; streams não são reenviados automaticamente.
Falhas temporárias na renovação mantêm o trabalho local e mostram uma opção
de confirmar a sessão novamente, sem tratar 503/rede como logout.

A sessão confirma o proprietário antes de repetir operações, ignora respostas
de autenticação antigas após logout/troca de conta e pausa a fila se a conta
mudar durante a sincronização. A correção de capacidade e coordenação entre
abas foi entregue no quarto incremento abaixo; a Sprint 37 ainda está em andamento.

Validação: 212 testes frontend, lint, tipagem, build e orçamento aprovados,
incluindo autosave do editor real com refresh 503. Nenhum banco ou serviço foi
alterado; não houve E2E ou homologação visual. A atualização da escrita v2 na
base de estudo continua pendente. Detalhes e próxima etapa no
[registro FE-37](docs/sprints_37_42_frontend_2026-10-13.md).

### Fila offline — Sprint 37, quarto incremento

A fila passa a usar IndexedDB transacional, com limite explícito de 100 respostas
por aluno e sincronização serializada entre abas por Web Locks. A resposta 101
fica no campo com aviso, sem eliminar a primeira nem afirmar que foi salva.
Falhas de quota/commit preservam o texto; um retry da operação incerta conserva
a chave idempotente. O painel permite consultar respostas e motivos de bloqueio,
com confirmação antes de remover bloqueadas da fila ativa.

As filas v1/v2 são importadas sem truncamento. As cópias antigas permanecem para
recuperação; recibos impedem reimportar itens já confirmados/descartados. Feche
ou recarregue abas antigas antes de usar a nova versão. Não limpe dados do
navegador para resolver erro de migração: pendências ainda podem existir somente
neste dispositivo. Sem Web Locks, a fila é preservada e a sincronização apresenta
um aviso; use HTTPS ou localhost. Retenção/limpeza de snapshots e cópias antigas
serão tratadas na política de dados locais.

Validação: **236 testes frontend e 3 testes Chromium de duas abas aprovados**,
além de lint, tipagem, build e orçamento (**168,1 KiB gzip**). Os testes Chromium
usam armazenamento/locks nativos, mas API simulada; não houve E2E integrado,
homologação visual/manual ou alteração do banco de estudo neste incremento.
O `npm audit` encontrou alertas preexistentes nas ferramentas de teste; a
atualização major sugerida não foi aplicada sem revisão. Detalhes, limitações e
próximos itens no [registro FE-37](docs/sprints_37_42_frontend_2026-10-13.md).

### Armazenamento e recuperação — Sprint 37, quinto incremento

Falhas de armazenamento local agora são tratadas em escrita, jornada, prática,
áudio, autoavaliação e perfil. A interface distingue dados apenas na tela de
dados gravados; quota cheia não impede continuar digitando ou tentar salvar na
conta. Se uma cópia antiga não puder ser removida, há aviso para conferir ao reabrir.

Barreiras de erro protegem a aplicação e as rotas de estudo. Falha ao carregar
uma tela oferece recuperação com foco e controles de teclado; recarregar exige
confirmação, sem limpar rascunhos/fila ou entrar em laço automático. Dados nunca
persistidos ainda podem ser perdidos ao sair ou recarregar. As mensagens gerais
deixam de sugerir `make up` ao aluno e oferecem detalhes técnicos opcionais.

Validação: **262 testes frontend, 4 testes Chromium isolados, lint, tipagem,
build e orçamento aprovados**. O teste novo bloqueia um import real e verifica
recuperação por teclado e conservação de dados locais sintéticos; não é a
homologação integrada da aplicação. O bundle ficou em aproximadamente 170 KiB
gzip, com pouca margem no teto existente. Não houve alteração do banco de estudo
ou novas dependências nesta etapa. Alertas anteriores das ferramentas de teste,
isolamento E2E/backup e aceite integrado continuam pendentes. Detalhes no
[registro FE-37](docs/sprints_37_42_frontend_2026-10-13.md).

### Integração isolada — Sprint 37, sexto incremento

O E2E integrado agora usa exclusivamente `infra/compose.e2e.yml`, porta 5198,
banco/voz sintéticos e guardas locais; não aponta mais para produção local.
Comandos e limites estão na [seção de testes](#stack-exclusiva-para-e2e-sprint-37).

Validação final: **48 testes de segurança e 96 execuções E2E aprovados**
(48 cenários desktop/mobile em uma rodada completa sem retries locais).
Fila IndexedDB, reenvio idempotente à API real e escrita v2 atravessam a stack
completa. Build dos containers, configuração Compose e workflow (`actionlint`)
validados localmente; CI remoto não executado. A sentinela sintética permaneceu
intacta, e nenhum banco/áudio de estudo foi usado pelos testes.

Naquele incremento, o próximo passo era o backup conjunto, entregue e
ensaiado com dados sintéticos no registro abaixo. Permanecem papéis mínimos
de produção, aceites pedagógicos/erros BE-37, alertas das ferramentas de teste
e homologações humanas. Detalhes no
[registro DB-37](docs/sprints_37_42_banco_de_dados_2026-10-13.md).

### Backup e recuperação — Sprint 37, sétimo incremento

Rotina operacional separada em `ops/`: pacote conjunto, validação de falhas,
publicação por rename, manifesto/checksums e restore apenas em destino vazio
isolado. **29 testes operacionais aprovados**; ensaio real recuperou 82 aulas,
um usuário e um WAV de silêncio sintéticos, com referência e checksum
conferidos. Dois backups no mesmo minuto não colidiram; repetir o restore
no destino preenchido foi recusado sem apagar dados. O CI ganhou um job
próprio para reproduzir esse ensaio, ainda não executado remotamente.

**Situação histórica do sétimo incremento:** Sprint 37 ainda em andamento.
Naquele momento, o próximo incremento recomendado era
ensaiar separação de papéis runtime/worker/migrador/backup, ainda em ambiente
descartável, antes de alterar credenciais/grants reais. O rollout da escrita
v2 continua pendente: a produção local permanece em `b84e2c7a9d31`, sem
interrupção dos serviços e sem backup real neste incremento.

### Sprint 37 — fechamento técnico, 13/10/2026

**FE-37, BE-37 e DB-37 encerradas tecnicamente.** Jeferson autorizou manter a
homologação pedagógica humana dos 82 exemplos **pendente**, sem declará-la aprovada.
Naquele fechamento, a próxima implementação era a Sprint 38 conjunta, registrada abaixo.

- Escrita v2 com 82 exemplos naturais, negativos discriminantes e metadados de
  avaliação; erros seguros comuns de sessão, conflito e indisponibilidade.
- **765 testes backend**, **93,57% de cobertura**, **263 frontend**, **98 E2E
  integrados**, 50 guardas E2E, 38 testes operacionais e 4 cenários controlados
  de browser repetidos duas vezes aprovados. Ruff/mypy, lint/TypeScript,
  OpenAPI, build e orçamento aprovados.
- Vitest 4.1.11 e npm audit sem vulnerabilidades reportadas na árvore frontend.
  Bundle 170,2 KiB gzip; limite total documentado de 172 KiB, individuais mantidos.
- Backup real restaurado/ensaiado antes de alterar a origem; migration
  c95f3d8ba042 e 82 rubricas aplicadas sem seed completo nem recálculo histórico.
  Prova de preservação das 39 tabelas de conteúdo/dados pessoais aprovada.
- API com aulas_runtime, worker com aulas_worker e voz read-only, migrador
  separado, owner NOLOGIN e backup de leitura. Administrador preservado para
  recuperação; segredos fora do Git.
- **localhost:5181 atualizado e saudável**; desenvolvimento em 5180 não foi
  migrado/reiniciado. Ensaios sem testes mutáveis na conta real.

Procedimentos, proteção local e limitações:
[operação da Sprint 37](docs/operacao_sprint_37.md).
Não houve commit, push ou execução remota do CI nesta entrega.
Esse registro descreve a entrega e o rollout da Sprint 37.

### Sprint 38 — implementação e implantação local, 14/10/2026

**FE-38, BE-38 e DB-38 implementadas, testadas em ambientes isolados e implantadas
no estudo em http://localhost:5181/.** Schema instalado: `d06a4e9cb153`.
O desenvolvimento em 5180 não foi alterado por esta manutenção.

- Escrita com revisão esperada, autosave serial e conflito recuperável: comparar
  os textos, manter o local, usar o da conta ou preparar cópia dos dois.
  Análises atrasadas não avaliam outro texto; backups locais ficam identificados.
- Avaliação SM-2 com chave idempotente e recibo transacional: repetir uma operação
  após perder a resposta não duplica a nota. Interface bloqueia repetição de atalhos,
  preserva o item pendente e atualiza Hoje/progresso/competências/conclusão.
- Refresh concorrente converge para um sucessor; logout revoga a família.
  Login/cadastro têm limites compartilhados e senhas são processadas fora do
  event loop, com concorrência limitada. Perfil público exige HTTPS/cookie Secure;
  implantação de proxy/TLS público não está incluída nem homologada.
- Migration aditiva `d06a4e9cb153`, preflight sem correção silenciosa, auditoria
  read-only de 22 regras e permissões mínimas para as novas tabelas. Histórico
  anterior não foi reavaliado e nenhum recibo antigo foi inventado.

Validação: **789 testes backend (93,54% de cobertura), 270 frontend e 106 E2E**
em Chromium desktop/mobile. Ensaio adicional de atualização de Hoje por navegação
interna, sem recarregar, aprovado nos dois viewports. Ruff/mypy (63 arquivos),
ESLint/TypeScript, OpenAPI, Alembic check e build aprovados. Bundle: **171,8 KiB gzip**,
limite mantido em 172 KiB. Também passaram 39 testes operacionais, 50 guardas E2E
e 27 recusas de operações SQL proibidas no laboratório de papéis.

Compatibilidade de clientes antigos sem revisão termina em **13/11/2026 às 00:00 UTC**
(`LEGACY_WRITES_UNTIL`); depois a API exige atualização do cliente (HTTP 428).
O frontend novo já envia revisão e chave de operação quando necessárias.

Implantação autorizada em 14/10, com backup prévio restaurado em clone novo,
migration ensaiada duas vezes e comparação das 39 tabelas históricas antes/depois.
Há também backup pós-migration verificado. Página, health, catálogo e Aula 31
responderam 200; API/worker mantiveram papéis mínimos, e o HTML servido corresponde
ao novo container. Foram aprovados **47 testes operacionais** após acrescentar
as proteções específicas deste rollout. Nenhum seed completo, reset ou exclusão
de dados de estudo foi realizado.

A auditoria detectou **20 jornadas antigas sem todos os registros detalhados de
etapa; 15 também sem data de conclusão**. Foram preservadas, não corrigidas:
as outras 20 regras passaram e hashes/contagens demonstraram nenhuma regressão.
Reconciliação dessas jornadas e homologações humanas de leitores de tela/escrita
permanecem pendentes. Não houve commit/push nem CI remoto.

**Não executar `make up` como atualização da base de estudo.** O procedimento
Sprint 38 usa `ops/concurrency_rollout.py`; `ops/study_rollout.py` permanece fixo na
Sprint 37. Procedimentos, backups e limites de recuperação estão no
[registro operacional](docs/operacao_sprint_37.md#sprint-38--implantação-autorizada-em-14102026).

Contratos, escopo e checklists: [frontend](docs/sprints_37_42_frontend_2026-10-13.md#sprint-38-escrita-e-revisão-sem-conflitos-silenciosos),
[backend](docs/sprints_37_42_backend_2026-10-13.md#sprint-38-autenticação-e-mutações-concorrentes)
e [banco](docs/sprints_37_42_banco_de_dados_2026-10-13.md#sprint-38-integridade-transacional-e-eventos-de-revisão).
Próxima sprint de implementação: **39 — áudio, continuidade offline, tempo de estudo e cotas**.

### Histórico de validação anterior

No fechamento 31–40, os 237 testes backend passaram no fuso local e em
`Pacific/Kiritimati`; os 166 testes frontend, lint, tipagem e build também passaram.
O backend manteve **94% de cobertura**, o bundle ficou em **163,2 KiB gzip**, o seed
com 82 aulas foi aplicado duas vezes e as 96 execuções Playwright passaram contra o
compose de produção em desktop e mobile.

O frontend possui uma **jornada guiada** nas 82 aulas publicadas dos dois níveis. Ela divide o
estudo em preparar, assistir, estudar, praticar e revisar. A etapa atual é salva localmente e na conta,
permitindo continuar em outro navegador. Em “Assistir”, o player usa o áudio oficial da VOA,
sincroniza a posição na conta e oferece velocidade, saltos de cinco segundos, repetição A–B e
408 trechos selecionados com tradução opcional. As atividades de compreensão são corrigidas pela
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
           lessons.json                — conteúdo das 82 aulas publicadas
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
O plano de expansão do Level 1 nas Sprints 31–36 está em
[docs/plano_sprints_31_36_level_1_1_a_30_2026-10-09.md](docs/plano_sprints_31_36_level_1_1_a_30_2026-10-09.md).
O plano de expansão das Sprints 26–30 está em
[docs/plano_sprints_26_30_level_2_2026-10-09.md](docs/plano_sprints_26_30_level_2_2026-10-09.md).
