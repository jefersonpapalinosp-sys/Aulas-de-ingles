# Referência técnica e conteúdo

Catálogo, contratos e estratégias de testes extraídos do README em 29/10/2026.
Para execução, ambientes e manutenção, siga o [runbook atual](operacao_local.md).
Resultados por sprint estão no [changelog](changelog.md).

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 19 + TypeScript + Vite |
| Backend | FastAPI + SQLAlchemy 2.0 async + asyncpg |
| Banco | PostgreSQL 16 (container, volume nomeado) |
| Testes | pytest · Vitest · Playwright (a partir da S5) |

## Como as peças se falam

```
navegador → :5180 Vite ──proxy /api──→ :8000 FastAPI ──asyncpg──→ :5432 Postgres
```

O browser **nunca** chama a API direto: tudo passa por `/api` na mesma origem,
via proxy do Vite. Isso elimina CORS em dev e deixa o caminho pronto para o
cookie `httpOnly` da sprint 3.

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
`config/assist-provider-review.json`, preencha a homologação e rode uma modalidade por vez.
O exemplo identifica `"modality": "conversation"`; ajuste esse campo para a modalidade
avaliada antes de executar os comandos de escrita ou transcrição:

```bash
make assist-gate modality=writing review=../config/assist-provider-review.json
make assist-gate modality=transcription review=../config/assist-provider-review.json
make assist-gate modality=conversation review=../config/assist-provider-review.json
```

O comando só produz métricas agregadas e retorna código `0` quando todos os critérios passam,
`1` quando a liberação continua bloqueada e `2` para configuração inválida. Ele não altera a
feature flag.

Para conversa, o gate considera os turnos do aluno no modo Guiado, vinculados ao
`provider_name` do manifesto, e exige 30 avaliações válidas em pelo menos cinco aulas.
Roteiro, modo Livre e outros provedores não entram na amostra. Fallback e falha terminal
contam como falha técnica; só respostas concluídas sem fallback/erro entram na avaliação
de utilidade. Custo desconhecido bloqueia a aprovação; áudio e diálogo são somados uma
única vez pelo custo do turno. O exemplo permanece sem aprovações de privacidade ou
segurança preenchidas: executar o comando não substitui a revisão humana.

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

O CI executa a suíte completa com cobertura e repete os cenários temporais sob
`TZ=Pacific/Kiritimati` com `uv run pytest -q --strict-markers -m timezone`.
Marque novos testes de calendário, expiração, retenção ou serialização de datas
com `@pytest.mark.timezone`; use `pytestmark = pytest.mark.timezone` somente
quando o módulo inteiro tratar dessas regras. A seleção é explícita e inclui
cenários de quota, custos por dia/mês, revisão, sessão, áudio e histórico.
Para comparar localmente, execute o mesmo comando com `TZ=UTC` e depois com
`TZ=Pacific/Kiritimati`, sem rodar processos de pytest simultâneos nessa base.

Os testes de concorrência de autenticação usam eventos para verificar que
`/api/live` responde enquanto hashes estão pendentes e que o trabalho respeita
o limite configurado de threads. Os timeouts desses eventos apenas impedem
deadlock nos testes; não representam uma meta de latência de produção.

`make test-db-down` para apenas o ambiente de testes, preservando seu volume.
Uma base separada, `aulas_test_sentinel`, contém um registro sintético para
verificar isolamento; o papel da suíte não tem permissão de conexão nela.

### Testes e tipagem dos scripts operacionais (BE-49)

`make test-recovery` executa os testes puros de `ops/`, com arquivos sintéticos
temporários e transporte simulado. Não exige Docker nem banco. Os ensaios
integrados de restauração continuam separados em `make test-recovery-integration`.

Na raiz, `uv run --project backend mypy --config-file mypy-ops.ini` verifica
estritamente toda a pasta `ops/` (incluindo novos módulos automaticamente). A configuração inclui
novos scripts automaticamente e é executada por `make lint` e pelo job `recovery`
do CI. Somente `ops/tests/` fica fora do mypy; os testes continuam verificados pela
execução da suíte e Ruff. No fechamento BE-49, eram 341 testes operacionais; os cinco smokes restantes
receberam 34 testes, com cobertura local entre 88% e 98%. A tipagem e os testes
simulados não substituem os ensaios integrados de banco, papéis e restauração.

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

## Como adicionar uma aula nova

1. Confirme ou crie o curso e a unidade em `seed/courses.json`.
2. Acrescente o objeto em `seed/lessons.json`, incluindo `course_slug`, `unit_slug`, `slug` e
   `position` (texto em Markdown, nunca HTML).
3. `make seed-plan` — prévia somente leitura; depois `make seed` se o pacote for
   permitido. Na barreira temporária **40B.1**, alterações/omissões de registros
   existentes e extensões dentro de aula/checkpoint existente são bloqueadas,
   mesmo aumentando a versão. Reaplicar conteúdo idêntico não recria registros.
   Publicar/editar conteúdo já existente depende do versionamento/arquivamento
   **40B.2**; não há opção `--force`. Não apague dados para contornar o bloqueio.
4. Se o modelo mudou: `make migration m="o que mudou"`, confira o arquivo
   gerado, e `make migrate`.
5. Se a API mudou: `make openapi` e, no frontend, `npm run gen:api`. Os dois
   arquivos entram no mesmo commit que a mudança.

Prévia operacional: `python -m app.cli seed --dry-run [--file caminho/lessons.json]`
(o catálogo `courses.json` deve estar ao lado do arquivo informado). Saída JSON;
código 0 = plano permitido, 1 = bloqueio/falha operacional, 2 = pacote/argumentos
inválidos. O comando de aplicação revalida o banco e não aceita uma prévia antiga
como autorização. [Evidências 40B.1 e pendências](historico_operacao_sprints_37_44.md#sprint-40b1--prévia-e-barreira-editorial-do-seed-em-15102026).

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
[docs/plano_sprints_20_25_frontend_cursos_exercicios_2026-10-08.md](plano_sprints_20_25_frontend_cursos_exercicios_2026-10-08.md).
O plano de expansão do Level 1 nas Sprints 31–36 está em
[docs/plano_sprints_31_36_level_1_1_a_30_2026-10-09.md](plano_sprints_31_36_level_1_1_a_30_2026-10-09.md).
O plano de expansão das Sprints 26–30 está em
[docs/plano_sprints_26_30_level_2_2026-10-09.md](plano_sprints_26_30_level_2_2026-10-09.md).
