# Plano das Sprints 44 a 49 — correções por frente e assistente de conversa

Atualização: 21 de outubro de 2026. Base: `main` em `f9b03f3`, head Alembic
`a42c7d1e9f20`, produção pública no EasyPanel (projeto `papalino`, serviço
`aulas-ingles`) e estudo local em `localhost:5181`.

Este plano nasce da análise técnica de 21/10/2026, feita sobre o código com
lints, suíte backend (1161 aprovados, 1 instável sob carga), suíte frontend
(360 aprovados) e três revisões independentes de backend, frontend e
infra/operação. Ele continua a numeração da [Sprint 43](sprint_43_implantacao_estudo_2026-10-16.md)
e mantém a convenção das Sprints 37–42: **um ciclo tem um pacote por frente**
(`FE`, `BE`, `DB`, `SEC`, `INFRA`), e os pacotes do mesmo ciclo podem andar em
paralelo. A partir do ciclo 45 existe uma sexta frente, `IA`, para o assistente
de conversa, que consome entregas das outras cinco.

Regras herdadas que este plano não altera:

- recursos assistidos nascem desligados, com opt-in próprio, cota, custo e
  retenção controlados pela API; texto e áudio do aluno nunca entram em log;
- a camada determinística decide primeiro; o modelo explica, não dá nota;
- "implementado" não é "homologado": aceite humano, pedagógico ou de
  acessibilidade só fecha com revisor e data registrados;
- toda promoção ao estudo ou à produção repete a sequência da Sprint 43:
  backup anterior, ensaio em clone, migration pelo papel migrador, gates
  antes da web, backup posterior;
- o [plano multimodal](plano_evolucao_estudo_ingles_multimodal.md#11-priorização)
  lista "chat aberto genérico como tutor principal" em *não fazer agora*. O
  assistente deste plano **não** é isso: é um parceiro de conversa roteirizado
  e ancorado no conteúdo de cada aula, com cerca de tópico e limite de turnos.
  Essa decisão fica registrada aqui para não ser reaberta por acidente.

---

## Visão geral

| Ciclo | Tema | Gatilho ou prazo |
|---|---|---|
| 44 | Fechar a produção pública: backup remoto, segredos, cutover de 13/11 | antes de **13/11/2026** |
| 45 | Deploy confiável, extração de serviços, fundação do assistente | após 44 |
| 46 | Assistente no backend e no banco; motores de sincronização no frontend | após 45 |
| 47 | Assistente no browser; endurecimento das rotas novas; E2E com provedor simulado | após 46 |
| 48 | Piloto controlado em conta única e gate humano do assistente | após 47 |
| 49 | Enxugar topologia, scripts por sprint, documentação e lint | qualquer momento após 45 |

### Pacotes por frente

| Frente | 44 | 45 | 46 | 47 | 48 | 49 |
|---|---|---|---|---|---|---|
| **FE** | cutover no cliente, invalidação única, métrica de bundle | Caderno em camadas, estado derivado | motores de sync fora dos componentes | experiência do assistente | correções do piloto, a11y do assistente | lint type-aware, a11y de formulário, CSS por domínio |
| **BE** | cobertura pós-cutover, listagens com teto, teste instável | extração de serviços, `review` como serviço, `Literal` | motor de diálogo, provedor, fila e cota | evidência, revisão SM-2, Hoje, exportação 1.7 | correções do piloto, custo e retenção | `ops/` sob mypy, testes de fuso marcados |
| **DB** | índice do rate limit, restore do pacote de produção em laboratório | schema aditivo do assistente | migration, grants, exclusão em cascata | laboratório 1k/10k de turnos | retenção de turnos | política de downgrade e testes de migration unificados |
| **SEC** | segredos fora de `backups/`, guardas de config, `permissions` no CI | hardening de container, borda do nginx, análise estática de shell/Docker | modelo de ameaças e corpus adversarial do assistente | revisão das rotas novas: IDOR, replay, cota, tamanho | revisão de logs, runbook de incidente de provedor, rotação | ensaio de rotação de segredos |
| **INFRA** | backup da stack EasyPanel, retenção 7+4, limpeza de 523 MB | pipeline CI→deploy, seed fora do gate, resolver, healthcheck | provedor em produção, métricas e alerta do worker | gateway simulado no E2E, job de CI | painel de custo, backup verificado com tabelas novas | poda de stacks, scripts e docs |
| **IA** | — | definição, contrato e spike de latência | — | — | gate `conversation`, homologação pedagógica, decisão | — |

### Dependências que travam

- INFRA-44 antes de qualquer ativação do assistente em produção: sem backup
  remoto verificado, nada novo grava dado de aluno na stack pública.
- BE-44 e FE-44 antes de 13/11/2026 ou a data de `LEGACY_WRITES_UNTIL` é
  adiada por decisão explícita. Não existe terceira opção.
- IA-45 antes de DB-45 fechar o schema: a modelagem segue o contrato, não o
  contrário.
- SEC-46 antes de FE-47 ligar qualquer chamada ao provedor, mesmo em dev.
- IA-48 decide ligar ou não. Nenhum teste automatizado substitui essa decisão.

---

## Ciclo 44 — Fechar a produção pública

Prioridade P0/P1. A stack do EasyPanel está no ar sem backup alcançável pela
rotina de recuperação, e o cutover de 13/11 não é exercitado pela suíte.

### INFRA-44 Backup da produção pública e retenção real

Objetivo: fazer a rotina de recuperação alcançar a stack do EasyPanel e cumprir
a política escrita em
[politica_exclusao_e_backups_dev_2026-10-16.md](politica_exclusao_e_backups_dev_2026-10-16.md).

Entregas:

- [x] `make backup source=public`: captura do PostgreSQL e do volume de voz da
  stack EasyPanel via SSH na VM, com o mesmo manifesto e checksums de
  `ops/recovery_archive.py`; o pacote chega ao Mac já criptografado com `age`
  e chave que não mora no Mac.
- [x] `ops/recovery.py prune`: janela de 7 diários + 4 semanais, `--dry-run`
  por padrão, recusa apagar o pacote mais recente e qualquer `.partial-*`
  com menos de 24 h.
- [x] Remover `backups/recovery/sprint39-application-before-*` (523 MB de
  `api.tar`/`worker.tar` byte-idênticos, reconstruíveis do Git) e o
  `.partial-*` de 0 B.
- [x] Agendamento diário local (`launchd`) com registro de sucesso/falha em
  arquivo; cópia externa criptografada do pacote do dia (iCloud Drive).
- [x] Primeiro backup real pós-deploy registrado em
  [deploy_easypanel.md](deploy_easypanel.md).

Critérios de aceite:

1. Um pacote capturado da stack pública é restaurado no laboratório local
   (`infra/compose.recovery.yml`, destino vazio) e a aplicação lê catálogo e
   `alembic_version` do clone com HTTP 200.
2. `prune --dry-run` lista exatamente o que a janela 7+4 descarta; sem
   `--apply`, nada muda em disco.
3. `backups/` fica abaixo de 50 MB após a limpeza, e `git status` continua
   sem rastrear nada do diretório.
4. O agendamento roda dois dias seguidos com recibo; a ausência de recibo é
   visível no `make operations-check`.

Fora do escopo: snapshot online atômico banco+arquivo; backup incremental.

### SEC-44 Segredos no lugar certo e guardas de configuração

Objetivo: separar credenciais de dados e fechar três validações de boot que
hoje deixam passar combinações inseguras.

Entregas:

- [x] Mover `backups/recovery/roles-prod.env` e `roles-lab.env` para fora de
  `backups/` (diretório `secrets/` ignorado, perm `0600`) e ajustar
  `Makefile:166`.
- [x] `config.validar()`: exigir `COOKIE_SECURE=true` quando `APP_ENV=prod`,
  não só com `DEPLOYMENT_PROFILE=public`; alinhar `.env.prod.example`.
- [x] `config.validar()`: recusar `CORS_ORIGINS` contendo `*` enquanto
  `allow_credentials=True`.
- [x] Chave HMAC dos buckets de rate limit derivada de segredo próprio
  (`AUTH_BUCKET_SECRET` ou HKDF a partir do `JWT_SECRET` com rótulo), para
  que rotacionar o JWT não zere os contadores.
- [x] `OPERATIONS_TOKEN` persistido: conferido na configuração do EasyPanel e
  gravado no `.env.prod` da produção local, que vivia só no container.
- [x] `permissions: contents: read` no topo de `.github/workflows/ci.yml`.

Critérios de aceite:

1. Testes de `config` cobrem as três recusas novas com mensagens que não
   imprimem o valor do segredo.
2. `make backup source=public` e a cópia externa não contêm nenhuma URL com
   senha; verificação por `grep` automatizada no teste do pacote.
3. Recriar o container da API no EasyPanel mantém `/api/operations/metrics`
   respondendo com o mesmo token.

### BE-44 Cutover de 13/11, listagens com teto e teste instável

Objetivo: garantir que a API funcione no dia em que `LEGACY_WRITES_UNTIL`
expira e fechar duas pontas soltas de robustez.

Entregas:

- [x] Passo no job `backend` do CI que roda `tests/test_progress.py`,
  `tests/test_writing*.py`, `tests/test_review.py` e `tests/test_concurrency.py`
  com `LEGACY_WRITES_UNTIL` no passado; o `conftest` deixa de empurrar a
  janela quando essa variável vier do ambiente.
- [x] Decisão registrada: **13/11/2026 mantida**, confirmada por Jeferson em
  21/10/2026. Nenhum default muda.
- [x] `limit` com teto 100 em `GET /me/notebook`, `GET /review/items`,
  `GET /speaking/attempts` e `GET /writing/history`; os clientes antigos que
  não enviam `limit` recebem a primeira página e um cabeçalho indicando a
  rota paginada.
- [x] Investigar o 503 em `test_concurrent_modalities_share_atomic_quota`
  sob carga: identificar o `sqlstate` que vira 503 (lock `NOWAIT`, pool ou
  timeout do provedor simulado) e corrigir a causa ou documentar o limite de
  concorrência; o teste passa 10 vezes seguidas com outro processo pesado na
  máquina.

Critérios de aceite:

1. Com a janela expirada, um `PUT` sem `expected_revision` recebe 428 e o
   corpo segue o contrato de erro com `request_id`; com revisão, 200.
2. As quatro listagens têm `limit` no OpenAPI, baseline regravado e tipos do
   frontend regenerados no mesmo commit.
3. `make test-api` completo aprovado três vezes seguidas no Mac, sem falha.

### FE-44 Cliente pronto para o cutover e invalidação única

Objetivo: nenhum write do frontend pode ficar sem revisão em 13/11, e o cache
não pode divergir por desenho.

Entregas:

- [x] Auditoria de todos os `PUT`/`POST` mutáveis: cada um envia
  `expected_revision` ou `operation_key` quando o contrato pede; teste que
  falha se um novo write escapar.
- [x] Tratamento de 428: aviso "atualize o aplicativo" com recarga
  confirmada, sem perder rascunho ou fila.
- [x] Um único mapa `evento → chaves` em `api/invalidateStudy.ts`
  (`attempt`, `queueSync`, `writingFeedback`, `speakingUpload`, `reviewGrade`)
  e remoção da função homônima em `ConnectivityStatus.tsx` e das listas
  soltas em `ExerciseCard.tsx`, `review.ts`, `progress.ts`,
  `addReviewItem.ts`, `courseReviews.ts` e `ShadowingPractice.tsx`.
- [x] `check-bundle-budget.mjs` com dois tetos: carregamento inicial
  (entrada + CSS) e total de assets; o teto inicial fica abaixo do total
  atual para não penalizar chunk lazy.

Critérios de aceite:

1. Após uma tentativa de exercício, `skills` e `study-session` são
   invalidados; teste de componente comprova.
2. `grep -rn "invalidateQueries" src` fora de `api/invalidateStudy.ts`
   retorna zero ocorrências.
3. O orçamento falha quando a entrada cresce e **não** falha quando um
   chunk lazy novo é criado dentro do teto total.

### DB-44 Índice do rate limit e restore do pacote público

Entregas:

- [x] Índice em `auth_rate_bucket(window_start)` ou mover o `DELETE` de
  `auth_limits.py:52` para `services/maintenance.py`; medir antes e depois
  com `EXPLAIN` no laboratório.
- [x] Ensaio de restore do pacote público (INFRA-44) com comparação de
  contagens pela rotina de snapshot, como na Sprint 43 (recibo verificado em
  21/10/2026).
- [x] Unificar `test_notebook_index_migration.py`,
  `test_review_index_migration.py` e
  `test_writing_feedback_index_migration.py` em um teste parametrizado.

Critérios de aceite:

1. O plano do `DELETE` em `auth_rate_bucket` deixa de ser `Seq Scan` ou o
   comando sai do caminho de login.
2. Recibo do restore público guardado em `backups/recovery/restore-receipts/`.

### Registro de execução — Ciclo 44, 21/10/2026

Implementado na branch `sprint/44-producao-publica`, em seis commits (um por
pacote mais o de testes/CI), sem push. "Implementado" aqui é técnico; os itens
abaixo marcados como pendentes dependem de decisão ou ação de Jeferson.

**Validação executada:** ruff, mypy strict (92 arquivos), eslint, tsc e
`check:api` limpos. Backend: **1166 testes aprovados** na suíte normal (2 min
26 s) e **1166 aprovados com `LEGACY_WRITES_UNTIL` expirado** (2 min 53 s), zero
pulados pelo marcador `legacy_client`. Frontend: **46 arquivos, 396 testes**,
7 testes do script de orçamento, build e os dois tetos (inicial 127,5 de 132 KiB;
total 177,3 de 184 KiB). Operação: **133 testes** em `ops/tests`. Baseline
OpenAPI e `schema.d.ts` regenerados no mesmo commit. E2E não foi reexecutado.

| Pacote | Entregue | Evidência | Pendente |
|---|---|---|---|
| INFRA-44 | `make backup source=public`, `backup-public-check`, `backup-prune`/`-apply`, modelo launchd, runbook e política | primeiro pacote real `aulas-20261021T042626017843Z-bb04…`, revisão `a42c7d1e9f20`, 82 aulas, 1 usuário, dump 631.101 bytes, 32 s, verificado; dry-run do prune: manter 3, remover 10 (10,9 MB), 1 parcial, 29 fora da política | **feitos em 21/10/2026 com autorização:** 523 MB removidos e `backup-prune-apply` executado (`backups/` de 540 MB para 5,6 MB, 4 pacotes); `age` 1.3.2 instalado; par gerado em `secrets/`; destino externo no iCloud Drive; launchd diário instalado e testado (saída 0, recibo, cópia cifrada); pacote público restaurado em `target-db` (recibo verificado, 124 s). **Resta:** copiar `secrets/backup-age-identity.txt` para fora do Mac e comprovar recibos em dias consecutivos |
| SEC-44 | `roles-*.env/json` em `secrets/`; guardas de cookie em prod, `CORS_ORIGINS=*` e `AUTH_BUCKET_SECRET`; chave HMAC própria; `permissions` no CI | testes de `Settings` cobrem as três recusas sem imprimir segredo; `PROD_ROLES` e `ops/roles.py` leem `secrets/` | `OPERATIONS_TOKEN` conferido no EasyPanel (já persistido na configuração do serviço) e gravado no `.env.prod` local em 21/10/2026, que também passou a 600; opcionalmente definir `EASYPANEL_AUTH_BUCKET_SECRET` |
| BE-44 | `limit` ≤ 100 e `X-Paginated-Alternative` nas 4 listagens; 428 declarado no OpenAPI das 5 rotas com revisão; `conftest` respeita o ambiente e ganha `legacy_client`; passo de CI pós-cutover; 22 testes convertidos ao contrato novo; teste de cota tolera 503 por invariante; `sqlstate` no log de indisponibilidade | 1166/1166 com a janela expirada; o 503 do teste instável era `lock_timeout` sob contenção (máquina com dois agentes e Docker), reproduzido e eliminado quando isolado | data de 13/11/2026 **confirmada por Jeferson em 21/10/2026**; o critério "10 execuções seguidas sob carga" não foi medido formalmente |
| FE-44 | registro `REVISIONED_WRITES` (13 operações) com teste contra o OpenAPI nos dois sentidos, tipos apertados e guarda em dev; banner de 428 com recarga confirmada; fila offline mantém a tentativa; mapa único de invalidação (18 eventos); orçamento com dois tetos | `invalidateQueries` fora de `api/invalidateStudy.ts`: zero; `skills` e `study-session` invalidados após tentativa | — |
| DB-44 | migration `d2b7e4c9a150` (`ix_auth_rate_bucket_window_start`, CONCURRENTLY, idempotente); `Index` no modelo; teste parametrizado dos 4 índices | `EXPLAIN` no banco descartável com 200 mil linhas: Seq Scan custo 4370 → Bitmap Index Scan custo 968; restore do pacote público em laboratório verificado em 21/10/2026 | — |

Mudanças de operação que valem aviso: a produção local em 5181 passa a receber
`PUBLIC_ORIGIN=http://localhost:5181` por padrão do Compose quando for
recriada com este código (sem isso a guarda nova recusa o boot); os contadores
de rate limit zeram uma vez no primeiro deploy, porque a chave HMAC mudou de
derivação; o Makefile só encontra os papéis de produção local em
`secrets/roles-prod.env`.

Primeira execução do CI do PR #25: os jobs `recovery` e `e2e` caíram em 429
"Data limit exceeded" do espelho `public.ecr.aws` ao resolver os `FROM` dos
Dockerfiles (fragilidade pré-existente; o Postgres já tinha fallback, os builds
não). Correção antecipada do INFRA-45: `ops/ci_pull_bases.sh` pré-carrega as
quatro imagens-base por digest com duas origens, no mesmo padrão de
`ci_pull_postgres.sh`, e o job `e2e` usa o builder do daemon (`driver: docker`)
para enxergar o cache. Conferido localmente que `docker build` resolve um `FROM`
presente no cache sem consultar o registro.

Segunda execução do CI: o E2E "revisão multimodal filtra e permite suspender,
reativar e excluir" reprovou nos dois viewports. Causa: ao unificar a invalidação,
quatro `onSuccess` de hooks passaram a **devolver** a promessa de
`invalidateStudy`; o TanStack Query espera essa promessa (o refetch inteiro)
antes de chamar o `onSuccess` passado no `mutate()`, e a página de revisão usa
esse segundo callback para zerar a lista de suspensos, que antes rodava antes do
refetch e passou a apagar a lista recém-carregada. Correção: os hooks que na
`main` disparavam a invalidação com `void` voltam a não devolver a promessa
(status e exclusão de item de revisão, adicionar ao deck, plano de estudo).
Reproduzido localmente com a imagem anterior e verificado com a corrigida: 50 de
50 cenários do fluxo completo no Chromium.

**Merge e deploy público, 21/10/2026.** PR #25 mergeado por squash em `0ebb9be`
com CI verde nos cinco jobs. Deploy do mesmo SHA na stack do EasyPanel seguindo a
sequência da Sprint 43 (backup anterior, ensaio da migration no clone público,
gate `migrate → permissions → api → web`, smokes, gate operacional `ok`, backup
posterior); registro completo em
[deploy_easypanel.md](deploy_easypanel.md#registro-do-segundo-deploy--21102026-sprint-44).
A produção pública está em `d2b7e4c9a150`. No mesmo dia, com autorização, a
produção local de estudo em 5181 foi recriada com este código pela sequência da
Sprint 43 (registro no [runbook](operacao_sprint_37.md#sprint-44--implantação-autorizada-no-estudo-em-21102026));
a correção do `PUBLIC_ORIGIN` no worker e no migrador locais (`b42de48`) saiu
dessa implantação. Pendência que fica: copiar a chave privada `age` para fora
do Mac.

Achados da conversão dos testes, para o BE-45: `POST /writing/prompts/{id}/feedback`
aceita `expected_revision` no corpo e está no registro do frontend, mas o backend
não chama `require_revision` nela; e o 428 de `grade` sem `idempotency_key`
reaproveita o código `revision_required`, o que confunde o cliente sobre qual
campo falta.

---

## Ciclo 45 — Deploy confiável, serviços extraídos e fundação do assistente

### INFRA-45 Pipeline CI→deploy e resiliência da stack pública

Entregas:

- [x] Job `deploy` no CI com `needs: [backend, frontend, e2e, recovery]`,
  só em push na `main`, executando `ops/deploy_public.sh` por SSH (o painel
  não emitiu token de API); sem a secret `PUBLIC_DEPLOY_SSH_KEY` o job avisa
  e termina verde, desarmado. Smokes pós-deploy nas cinco rotas e schema
  compatível.
- [x] Decisão sobre o `seed` no gate de release: `migrate` só faz `upgrade` +
  `check`; o `seed` virou serviço próprio depois da API saudável. Falha dele
  sai vermelha no `up --wait` e no script de deploy, sem derrubar o site.
- [x] `resolver 127.0.0.11 valid=10s` e `proxy_pass` por variável em
  `frontend/nginx.conf`.
- [x] Healthcheck do worker (`python -m app.cli worker-health`) baseado em
  `worker_heartbeat` nos três Compose; provado no worker de dev.
- [x] `Cache-Control: no-cache, must-revalidate` em `/` e `/index.html`; um
  único `Cache-Control` em `/assets/`.
- [x] `timeout-minutes` em todos os jobs; `recovery` passou de 15 para 35.
- [ ] Build único da imagem com cache GHA, reutilizado por `security-inventory`,
  `recovery` e `e2e`. Adiado: a pré-carga por digest (Sprint 44) removeu a
  causa das falhas e o CI já fecha em cerca de 10 minutos de parede.
- [x] Trivy em SARIF com `upload-sarif`; `dependabot.yml` para npm, `uv` e
  actions.

Critérios de aceite:

1. Um merge em `main` com CI vermelho **não** chega ao EasyPanel; comprovado
   com um PR de teste que falha de propósito.
2. Recriar só o container `api` não gera 502 permanente no `web`.
3. Worker travado é reiniciado pelo Docker em até 3 minutos no laboratório.
4. Tempo total do CI cai abaixo de 20 minutos de parede.

### SEC-45 Hardening de container e borda

Entregas:

- [ ] `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]` e
  `read_only: true` onde couber, na stack EasyPanel primeiro.
- [ ] `server_tokens off`, `gzip_vary on`, `limit_req_zone` em `/api/auth/`.
- [ ] `docker-entrypoint.prod.sh` tolera volume read-only, removendo o
  `entrypoint: []` + UID duplicado em dois Compose.
- [ ] `shellcheck`, `hadolint` e `actionlint` no CI.
- [ ] Pins de patch nos estágios de build (`uv`, `node`).

Critérios de aceite: Trivy mantém zero críticas/altas; os quatro shell
scripts passam no shellcheck; a stack pública sobe com as três opções de
hardening e todos os smokes verdes.

### BE-45 Extração de serviços e tipagem

Entregas:

- [ ] `services/completion.py` a partir de `get_course_completion`
  (`api/courses.py:137`, 297 linhas); o router fica com validação, resolução
  e cabeçalhos.
- [ ] `services/writing_feedback.py` a partir de `analisar_texto`
  (`api/writing.py:292`, 205 linhas): rubrica, reserva de cota, provedor,
  persistência, evidência e revisão como funções nomeadas.
- [ ] Mover `adicionar_item_revisao`, `adicionar_cartas` e
  `remover_item_por_origem` de `api/review.py` para `services/review.py`;
  atualizar os quatro imports.
- [ ] Um helper único de conferência de idempotência em `tentar`
  (`api/progress.py:461` e `:501`).
- [ ] Colunas enum-like como `Mapped[Literal[...]]`; zero
  `type: ignore[arg-type]` em `app/`.
- [ ] Consolidar os pares "query legada / query de página" em `review.py`,
  `speaking.py`, `writing.py` e `me.py`; nenhum `-> Any` em `api/`.
- [ ] Alinhar `POST /writing/prompts/{id}/feedback` ao contrato de revisão:
  ou passa a chamar `require_revision` e declara o 428, ou sai do registro
  `REVISIONED_WRITES` do frontend. Hoje o cliente envia e o servidor ignora.
- [ ] 428 próprio (`idempotency_key_required`) quando `grade` recebe revisão
  mas não a chave; o frontend trata os dois códigos no mesmo banner.

Critérios de aceite: nenhum endpoint acima de 80 linhas em `api/`; cobertura
não cai abaixo de 93%; baseline OpenAPI inalterado neste pacote.

### FE-45 Caderno em camadas e estado derivado

Entregas:

- [ ] `api/notebook.ts` com 4 queries e 4 mutações via `useQuery`/
  `useMutation` lançando `ApiError`; fim dos 8 `throw Error()` vazios.
- [ ] `usePagedItems` substituído por `useInfiniteQuery`; remoção do
  `setSpeakingEntries` manual.
- [ ] `NotebookPage` dividida em `NotebookCompose`, `NotebookList`,
  `WritingHistorySection`, `SpeakingHistorySection`,
  `HistoricalEvidenceSection`.
- [ ] `LessonRail`: o toggle manual de unidade sobrevive a refetch do
  currículo.
- [ ] Política única de `retry`/`networkMode` documentada em `api/queries.ts`
  e aplicada a `dashboard.ts`, `review.ts` e `practice.ts`.

Critérios de aceite: nenhum arquivo de página acima de 300 linhas; teste de
regressão do toggle da `LessonRail`; mensagens de erro do Caderno exibem o
`request_id` quando existe.

### DB-45 Schema aditivo do assistente

Depende de IA-45. Migration única, aditiva, sem alterar tabelas existentes
além de ampliar duas constraints.

Entregas:

- [ ] Tabela `speaking_dialogue`: `user_id`, `lesson_id`, `mode`
  (`script`, `guided`, `free_unit`), `state`, `content_version` e fingerprint
  do recorte da aula, `provider_name`, `rubric_version`, `started_at`,
  `ended_at`, `turn_limit`.
- [ ] Tabela `dialogue_turn`: `dialogue_id`, `position`, `role`
  (`student`, `partner`), `input_kind` (`audio`, `text`),
  `speaking_attempt_id` opcional, `transcription_job_id` opcional,
  `transcript`, `checks` (JSONB, só códigos e booleanos), `partner_text`,
  `hints` (JSONB, só códigos permitidos), `confidence`, `cost_microusd`,
  `human_rating`, `created_at`; unicidade `(dialogue_id, position)`.
- [ ] `ck_assist_modality` passa a aceitar `conversation`;
  `skill_evidence.source_type` aceita `dialogue_turn`; origem de
  `review_item` aceita `dialogue_missed_term`.
- [ ] `ondelete` em todas as FKs, `timestamptz`, índice keyset
  `(dialogue_id, position)`, grants para `aulas_runtime` e `aulas_worker`.
- [ ] Exclusão de conta e exportação pessoal enxergam as duas tabelas.

Critérios de aceite: `alembic upgrade head` duas vezes e `alembic check`
limpos no laboratório; downgrade documentado como não destrutivo ou
bloqueado com motivo; o laboratório de papéis recusa escrita direta de
`aulas_runtime` em `dialogue_turn` fora das colunas permitidas.

### IA-45 Definição, contrato e spike do parceiro de conversa

Objetivo: decidir o que o assistente é, o que ele nunca faz, e medir se a
latência é viável antes de escrever uma linha de UI.

O parceiro de conversa tem três modos, liberados nesta ordem:

| Modo | O que faz | Precisa de |
|---|---|---|
| **Roteiro** | Role-play do diálogo oficial da aula a partir dos `transcript_cue`: o app fala um personagem (voz sintetizada no navegador), o aluno fala o outro; a fala do aluno é transcrita e comparada à fala esperada com `compare_transcript`. | STT já existente. Sem STT, equivale ao shadowing atual com falas alternadas e autoavaliação. |
| **Guiado** | O parceiro faz perguntas ancoradas nos objetivos, frases e vocabulário da aula; cada resposta passa pela camada determinística (termos-alvo usados, padrão gramatical do bloco da aula) e só os critérios reprovados vão ao modelo, que devolve o próximo turno e uma explicação curta. | STT + provedor de diálogo. |
| **Livre na unidade** | Conversa sobre os temas da unidade, com cerca de vocabulário e limite de turnos; o modelo redireciona ao tema quando o aluno sai. | Modo Guiado aprovado no gate humano. |

Pipeline de um turno do aluno:

```
VoiceRecorder (browser) ──PUT áudio do turno (limites e consentimento atuais)──▶ API 202 + job
   job (worker): STT via gateway com Idempotency-Key
             ──▶ domain/dialogue.py: cobertura de termos-alvo, padrão gramatical, comprimento
             ──▶ provedor de diálogo (gateway em prod; Ollama só em dev), JSON Schema:
                 { partner_text, hints[] ⊆ códigos reprovados, confidence }
             ──▶ filtro no backend: descarta códigos não permitidos, URLs, e-mails, excesso
             ──▶ persiste turno; cliente faz polling do job
browser: exibe transcrição + confiança + checks; fala o partner_text com speechSynthesis (en-US)
```

Entregas:

- [x] ADR `docs/adr_assistente_de_conversa.md` (escrito; aprovação pendente) com: os três modos; o que o
  modelo nunca faz (nota, "score de fluência", correção fonética, juízo
  sobre o aluno); cerca de tópico; limite de turnos por diálogo; fallback
  para o modo Roteiro quando o provedor falha; entrada por texto quando não
  há microfone.
- [x] Contrato OpenAPI rascunhado (tabela no ADR): `POST /api/speaking/dialogues`,
  `GET /api/speaking/dialogues/{id}`, `PUT .../turns/{position}/audio`,
  `POST .../turns/{position}/text`, `GET .../turns/{position}`,
  `PUT .../turns/{position}/rating`, `DELETE /api/speaking/dialogues/{id}`.
- [x] Prompt do sistema e esquema JSON versionados em `app/services/dialogue_prompts.py`,
  derivados exclusivamente de `seed/lessons.json` (objetivos, frases,
  vocabulário, blocos de gramática) e nunca da conversa anterior sem filtro.
- [ ] Spike de latência: 30 turnos sintéticos em Ollama `qwen2.5:7b` no Mac
  e 30 em um gateway HTTPS; registrar p50/p95 e custo por turno.
- [x] Decisão de TTS (registrada no ADR): `speechSynthesis` do navegador como padrão (zero custo,
  dado não sai do dispositivo, funciona offline); gateway de TTS fica para
  depois do piloto, se a qualidade da voz for reprovada.
- [ ] Manifesto de homologação do provedor para a modalidade `conversation`
  em `config/assist-provider-review.example.json`.

Critérios de aceite:

1. ADR aprovado por Jeferson antes de DB-45 fechar o schema.
2. p95 do turno completo (STT + checks + modelo) abaixo de 8 s no caminho
   escolhido para produção; acima disso, o modo Guiado não entra no ciclo 46
   e só o Roteiro avança.
3. Nenhum prompt contém dado pessoal do aluno além do texto do turno.

Fora do escopo definitivo: feedback fonético por fonema, nota única de
fluência, ranking, armazenar áudio no PostgreSQL, importar conteúdo novo da
VOA.

### Registro de execução — Ciclo 45, andamento em 21/10/2026

Branch `sprint/45-deploy-e-fundacao`. Dois pacotes avançaram no mesmo dia do
fechamento do ciclo 44; os demais (BE-45, FE-45, SEC-45, DB-45) não começaram.

| Pacote | Entregue | Pendente |
|---|---|---|
| INFRA-45 | nginx resolve a API por requisição e deixa `/` e `/index.html` sem cache; `worker-health` + healthcheck nos três Compose (provado no worker de dev: ok com 60 s, reprovado com 1 s); `seed` fora do gate como serviço próprio no EasyPanel; `ops/deploy_public.sh` (13 testes simulados, dry-run sem contato com a VM) e `make deploy-public`; job `deploy` gated por secrets; SARIF do Trivy na aba Security; `timeout-minutes` em todos os jobs; `cancel-in-progress` só fora da `main`; `dependabot.yml`. 161 testes operacionais verdes | criar as secrets `PUBLIC_DEPLOY_SSH_KEY`, `PUBLIC_DEPLOY_KNOWN_HOSTS` e `PUBLIC_DEPLOY_HOST` (ação de Jeferson, com chave SSH exclusiva); provas dos critérios 1 a 3 (PR vermelho não implanta; recriar só a API sem 502; worker travado reiniciado) ficam para quando a stack E2E ou a pública rodar o código novo; build único com cache GHA adiado |
| IA-45 | ADR `adr_assistente_de_conversa.md` com modos, pipeline, vedações, códigos de check, contrato HTTP, cota/retenção e voz do navegador; `app/services/dialogue_prompts.py` (brief do seed, roteiro por falante, prompt `dialogue-prompt-v1`, schema restrito aos códigos reprovados, saneamento) com 8 testes puros; `ops/dialogue_latency_spike.py` (mock, Ollama, gateway) com 6 testes e execução simulada 30/30 | ADR **aprovado por Jeferson em 21/10/2026**, liberando DB-45; escolha do provedor de diálogo e STT para a medição real (não há Ollama neste Mac); manifesto da modalidade `conversation` em `config/assist-provider-review.example.json` |

Dois agentes que implementavam o INFRA-45 foram interrompidos por limite de
sessão da API durante as validações; o trabalho foi revisado linha a linha,
um teste corrigido (vazamento de variável de ambiente no cenário de host) e as
validações concluídas antes do commit.

---

## Ciclo 46 — Assistente no backend e no banco; motores de sync no frontend

### BE-46 Motor de diálogo, provedor, fila e cota

Entregas:

- [ ] `domain/dialogue.py` puro: cobertura de termos-alvo com a normalização
  de `domain/answers.py`, verificação de padrões gramaticais declarados no
  bloco da aula, limites de comprimento, códigos de check estáveis.
- [ ] `services/dialogue.py`: criação de diálogo com fingerprint do recorte
  da aula, roteiro a partir dos `transcript_cue`, montagem do prompt,
  chamada a `call_dialogue_provider` (gateway/ollama) com JSON Schema e
  filtro de saída, persistência, fallback para o Roteiro.
- [ ] Turno de áudio reaproveita `audio_upload`, `audio_inspection`,
  `audio_storage` e a fila durável de transcrição; o job de diálogo é um
  tipo novo na mesma fila, com `FOR UPDATE SKIP LOCKED`, retomada e backoff.
- [ ] Modalidade `conversation` em `assist_quota` com cota diária própria
  (`ASSIST_DIALOGUE_DAILY_TURNS`, padrão 20) e custo somado de STT + modelo.
- [ ] Rotas do contrato IA-45 com ownership no `WHERE`, 404 para recurso
  alheio, idempotência por `(dialogue_id, position)`.
- [ ] Nenhum texto de turno, transcrição ou resposta do provedor em log;
  teste que inspeciona o log capturado.

Critérios de aceite:

1. Com `ASSISTED_FEATURES_ENABLED=false`, o modo Roteiro funciona por
   completo e os modos Guiado/Livre respondem `409 assist_disabled`.
2. Provedor indisponível no meio de um diálogo: o turno seguinte vem do
   roteiro, marcado como `fallback`, sem perder os turnos anteriores.
3. Cota esgotada: 429 antes de qualquer chamada externa; o diálogo pode ser
   concluído no modo Roteiro.
4. Resposta do provedor com código inventado, URL ou e-mail é descartada e
   registrada só como `invalid_provider_response`.

### DB-46 Migration, grants e exclusão em cascata

- [ ] Aplicar a migration de DB-45 no laboratório e no clone do estudo;
  `alembic check` limpo; grants mínimos; `account_deletion` cobre as duas
  tabelas; exportação pessoal 1.7 com diálogos e turnos.
- [ ] Retenção: `transcript` e `partner_text` seguem `ASSIST_RETENTION_DAYS`
  pelo job de manutenção; metadados agregados permanecem.

Aceite: contagens antes/depois iguais nas 39 tabelas históricas; exclusão de
conta sintética zera `speaking_dialogue` e `dialogue_turn` do usuário.

### FE-46 Motores de sincronização fora dos componentes

Prepara o terreno do assistente: a UI do diálogo precisará de uma máquina de
estados de turno fora do React, e o padrão já existe em
`features/media/positionSync.ts` com `useSyncExternalStore`.

- [ ] `features/writing/draftSync.ts` extraído de `WritingWorkspace.tsx`
  (fila serial, geração, conflito de revisão, espelho local).
- [ ] `features/practice/practicePosition.ts` extraído de `PracticeRunner.tsx`;
  telas internas viram `PracticeIntro`, `PracticeResume`, `PracticeSummary`.
- [ ] `features/speaking/speakingUpload.ts` extraído de `ShadowingPractice.tsx`.
- [ ] `ExerciseCard`: um componente por `activity_type`; `role="alert"` no
  veredito de erro.
- [ ] Casts de corpo de erro em `WritingWorkspace` substituídos por type
  guard sobre `ApiError`.

Aceite: os três motores têm testes sem DOM cobrindo perda de rascunho,
conflito e cancelamento; nenhum componente acima de 300 linhas; 360 testes
continuam verdes.

### SEC-46 Modelo de ameaças e corpus adversarial do assistente

Bloqueia FE-47.

- [ ] Modelo de ameaças do assistente: injeção via transcrição do aluno,
  exfiltração de prompt, saída com conteúdo inadequado, abuso de cota,
  IDOR em diálogo alheio, replay de turno, áudio malicioso.
- [ ] Corpus adversarial com no mínimo 20 transcrições (instruções ao
  modelo, pedidos de dados pessoais, troca de idioma, conteúdo ofensivo)
  como testes `pytest` que exigem saída dentro do esquema e sem eco de
  instrução.
- [ ] Fluxo de dados ao provedor documentado em
  `guia_do_aluno_retomada_offline_privacidade.md` e na política de mídia:
  o que sai (texto do turno, códigos de check), o que não sai (nome,
  e-mail, histórico, áudio quando o provedor é só de texto).
- [ ] Requisitos do provedor em produção: HTTPS, token, região, retenção
  menor ou igual à do projeto, sem uso para treinamento.

Aceite: os 20 casos passam; a revisão do fluxo de dados está assinada no
documento com data.

### INFRA-46 Provedor em produção, métricas e alerta

- [ ] Provedor de diálogo configurado na stack EasyPanel por gateway HTTPS
  com token; Ollama permanece restrito a dev (a VM é compartilhada com três
  outros projetos e não tem GPU).
- [ ] Métricas agregadas de diálogo em `/api/operations/metrics`: turnos/dia,
  p95 de latência, falhas de provedor, custo do dia, cota atingida.
- [ ] `make operations-check` agendado (cron na VM ou `schedule:` no GitHub)
  com alerta por e-mail quando o worker, a fila ou o custo saem do limiar.
- [ ] Probe externo de disponibilidade do domínio público.

Aceite: um worker parado por 2 minutos gera alerta; o custo do dia aparece
no painel operacional sem nenhum texto de aluno.

---

## Ciclo 47 — Assistente no browser e endurecimento das rotas novas

### FE-47 Experiência do parceiro de conversa

- [ ] `features/dialogue/dialogueSession.ts`: máquina de estados fora do
  React (`idle → listening → uploading → waiting → partner_speaking →
  idle`), polling do job, fallback, limite de turnos.
- [ ] Tela do diálogo dentro da etapa "Revisar" da jornada guiada: escolha
  do modo, personagem, fala do parceiro **sempre em texto** mais voz
  sintetizada (`speechSynthesis`, voz `en-US`, velocidade ajustável,
  botão de repetir), botão falar/parar reaproveitando `VoiceRecorder`,
  entrada por texto como alternativa.
- [ ] Após o turno: transcrição com confiança por palavra (padrão atual,
  abaixo de 75% destacado), termos-alvo usados e faltantes, dica do padrão
  gramatical, explicação do modelo rotulada "automatizado, em avaliação",
  botões "foi útil"/"não foi útil", excluir turno ou diálogo.
- [ ] Cota e custo visíveis com `AssistQuota`; estados offline, cota
  esgotada e provedor indisponível com mensagens próprias e caminho para o
  Roteiro.
- [ ] Acessibilidade: `aria-live` para a fala do parceiro, foco previsível
  entre turnos, legenda sempre visível, `prefers-reduced-motion`, operação
  completa por teclado, nenhuma dependência de cor.
- [ ] CSP inalterada: `speechSynthesis` é API do navegador; nenhum domínio
  novo em `connect-src`.

Aceite: fluxo completo testado em Vitest com API simulada; teste Playwright
isolado com `speechSynthesis` substituído; sem microfone, o diálogo continua
por texto; o orçamento de bundle inicial não cresce (a feature é chunk lazy).

### BE-47 Evidência, revisão e painel

- [ ] Cada turno do aluno gera `skill_evidence` de speaking com origem
  `dialogue_turn`; termos-alvo faltantes em dois turnos do mesmo diálogo
  entram na revisão SM-2 como `dialogue_missed_term`, idempotente.
- [ ] O painel Hoje sugere "praticar a conversa da Aula N" quando a aula foi
  estudada e não tem diálogo nos últimos 7 dias; a sugestão explica o motivo.
- [ ] Exportação pessoal 1.7 inclui diálogos, turnos, avaliações humanas,
  custo e fornecedor.

Aceite: um diálogo sintético de 6 turnos produz exatamente 6 evidências e
no máximo os itens de revisão esperados; repetir o processamento não
duplica nada.

### DB-47 Laboratório 1k/10k de turnos

- [ ] Carga sintética de 1k e 10k turnos por aluno no laboratório; medição
  das consultas de histórico e do Caderno com o índice keyset; ajuste de
  índice se o p95 passar de 100 ms.

### SEC-47 Revisão das rotas novas

- [ ] Testes de IDOR em cada rota de diálogo; replay de turno com a mesma
  posição; tentativa de furar a cota em paralelo (reaproveitar o padrão de
  `test_assist_quota`); limites de tamanho de áudio alinhados entre UI, API
  e nginx para o turno; `limit_req` em `/api/speaking/dialogues`.

### INFRA-47 Gateway simulado no E2E

- [ ] Container de gateway simulado (STT + diálogo) em `infra/compose.e2e.yml`,
  determinístico, com cenários de sucesso, lentidão, falha e resposta
  inválida; job de CI roda o fluxo completo do diálogo em desktop e mobile.

Aceite: E2E do diálogo verde no CI; o gateway simulado nunca é alcançável
fora da rede da stack E2E.

---

## Ciclo 48 — Piloto controlado e gate humano

### IA-48 Piloto em conta única e decisão

- [ ] Ativação do modo Guiado **só na conta de Jeferson**, em produção, com
  cota reduzida e orçamento definido no manifesto.
- [ ] No mínimo 30 turnos avaliados por pessoa ao longo de pelo menos cinco
  aulas diferentes; `python -m app.cli assist-gate modality=conversation`
  com os mesmos limiares das outras modalidades: 80% úteis, falha técnica
  abaixo de 5%, custo no orçamento, retenção do provedor compatível.
- [ ] Revisão pedagógica humana dos prompts e de dez diálogos reais: o
  parceiro ficou no tema, usou o vocabulário da aula, não deu nota, não
  corrigiu pronúncia, explicou só o que a camada determinística reprovou.
- [ ] Decisão registrada em `matriz_aceite_sprint_48.md`: liberar o Guiado
  para outras contas, manter só o Roteiro, ou desligar. O Livre na unidade
  só entra em pauta se o Guiado for aprovado.

### FE-48 / BE-48 Correções do piloto

- [ ] Correções priorizadas pelas avaliações "não foi útil"; homologação de
  acessibilidade da tela do diálogo com VoiceOver em macOS e iOS,
  registrando revisor e data (continua pendente para o resto do app, ver
  [matriz da Sprint 42](matriz_aceite_sprint_42_2026-10-16.md)).

### DB-48 Retenção de turnos

- [ ] Job de manutenção apaga `transcript` e `partner_text` após
  `ASSIST_RETENTION_DAYS`, preservando checks agregados e avaliações; teste
  com relógio injetado.

### SEC-48 Revisão de logs e incidente de provedor

- [ ] Amostragem dos logs da API e do worker em produção: zero ocorrências
  de texto de turno; runbook de incidente para vazamento ou indisponibilidade
  do provedor (revogar token, desligar flag, comunicar); procedimento de
  rotação do token do provedor ensaiado uma vez.

### INFRA-48 Custo e backup com as tabelas novas

- [ ] Painel de custo diário/mensal do assistente a partir das métricas
  agregadas; alerta em 80% do orçamento.
- [ ] Backup público restaurado em laboratório com as tabelas novas e lido
  pela aplicação; recibo registrado.

---

## Ciclo 49 — Enxugar e consolidar

Pode começar após o ciclo 45 sempre que houver folga.

### INFRA-49 Poda de topologia, scripts e documentação

- [ ] Remover os perfis `final39-check`, `assist-check` e `dev-check` de
  `infra/compose.recovery.yml`; remover `ops/sprint39_rollout.py` e seu
  teste; unificar `study_rollout`/`concurrency_rollout` em `ops/rollout.py`
  parametrizado; tirar `ops.rollback_image` do caminho do CI, mantendo-o
  como ferramenta sob demanda.
- [ ] Decidir o destino de `infra/compose.prod.yml` e do overlay
  `compose.roles.prod.yml` agora que `make prod-up` está desativado e a
  produção vive no EasyPanel.
- [ ] README: changelog de sprints sai para `docs/changelog.md`; o README
  volta a ter menos de 400 linhas e aponta para os runbooks.
- [ ] `docs/operacao_sprint_37.md` dividido em runbook vigente e histórico.
- [ ] Apagar as 15 branches locais já mergeadas; derrubar os containers de
  laboratório parados há dias (`recovery-study-check`, `upgrade42`).

Aceite: `docker ps` do projeto mostra só dev, estudo local e teste; o CI
continua verde após a poda; `make help` lista menos de 50 alvos.

### BE-49 Qualidade da suíte e de `ops/`

- [ ] Marcador `timezone` nos testes que tocam data; o passo
  `TZ=Pacific/Kiritimati` roda só esse subconjunto.
- [ ] `test_concurrency.py`: trocar igualdade exata de ticks e latência de
  parede por asserções de invariante.
- [ ] `ops/` sob `mypy --strict`; testes para `recovery_archive.py` e para
  os módulos de smoke sem cobertura.
- [ ] Separar `/api/health` público (sem versão do Postgres e revisões) do
  readiness interno.

### FE-49 Lint type-aware, a11y de formulário e CSS por domínio

- [ ] `tseslint.configs.recommendedTypeChecked` (ativa
  `no-floating-promises`) e `eslint-plugin-jsx-a11y`; `public/sw.js` e
  `scripts/` entram no lint.
- [ ] `aria-describedby`/`aria-invalid` em todos os formulários; texto de
  ajuda fora do `<label>` em `LoginPage`.
- [ ] `styles.css` dividido por domínio (`base`, `layout`, `study`,
  `practice`, `writing`, `speaking`, `dialogue`, `notebook`) sem seção por
  sprint; `!important` reduzido a casos documentados.
- [ ] Data de remoção para as migrações de chave de storage v1/v2.

### DB-49 Política de downgrade e testes

- [ ] Política escrita: migrations aditivas, downgrade permitido até qual
  revisão, o que o CI testa; `d06a4e9cb153` referenciada como marco.
- [ ] Limpeza do `conftest` por `TRUNCATE` das tabelas não-seed ou
  transação com rollback, substituindo o `DELETE` ad hoc da unidade `31-35`.

### SEC-49 Ensaio de rotação

- [ ] Rotacionar `JWT_SECRET`, token do provedor e senhas dos papéis de
  banco em laboratório, medindo impacto em sessões ativas e documentando a
  ordem segura.

---

## Definição de pronto comum

Um pacote só fecha com: ruff, mypy strict, eslint e tsc limpos; baseline
OpenAPI e `schema.d.ts` regenerados no mesmo commit quando a API muda;
`alembic check` limpo; cobertura backend acima de 90%; testes novos para
cada entrega; documento da frente atualizado com "Registro de execução" e
evidências agregadas; CI verde no PR. Mudança em estudo local ou produção
segue a sequência da Sprint 43 e deixa recibo em `backups/recovery/`.

## Evidência mínima para fechar cada ciclo

| Ciclo | Evidência que não pode faltar |
|---|---|
| 44 | pacote da stack pública restaurado em laboratório; CI com cenário pós-cutover verde; `backups/` abaixo de 50 MB |
| 45 | PR vermelho de propósito não chega ao EasyPanel; ADR do assistente aprovado; nenhum endpoint acima de 80 linhas |
| 46 | modo Roteiro completo com flag desligada; 20 casos adversariais verdes; alerta de worker parado disparado em laboratório |
| 47 | E2E do diálogo verde com gateway simulado; fluxo por texto sem microfone; bundle inicial inalterado |
| 48 | `assist-gate modality=conversation` executado com 30 avaliações reais; decisão assinada na matriz |
| 49 | `docker ps` enxuto; README abaixo de 400 linhas; lint type-aware verde |

## O que este plano não faz

- Não importa conteúdo novo da VOA nem altera o recorte curricular.
- Não cria nota de fluência, ranking ou qualquer comparação entre alunos.
- Não avalia pronúncia por fonema; a transcrição mede reconhecimento de
  palavras, como o plano multimodal já estabeleceu.
- Não liga o assistente para outras contas antes do gate humano do ciclo 48.
- Não troca o monólito FastAPI por serviços separados; o worker continua
  sendo o único processo além da API.
