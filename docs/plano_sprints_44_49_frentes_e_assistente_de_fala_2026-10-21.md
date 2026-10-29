# Plano das Sprints 44 a 49 — correções por frente e assistente de conversa

Atualização: 29 de outubro de 2026. Base original de 21/10: `main` em `f9b03f3`, head Alembic
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

## Situação consolidada em 29/10/2026

Este quadro atualiza o estado presente; os registros datados abaixo preservam
as evidências e limitações da ocasião. Caixas de entregas técnicas já provadas
foram reconciliadas com esses registros. Implementação não encerra aceite humano.

| Ciclo/frente | Estado atual | O que permanece |
|---|---|---|
| 44–45 | Entregas técnicas publicadas; deploy automático operacional | Comprovar pendências de guarda externa da chave e recibos do backup; build único compartilhado no CI segue adiado |
| 46 | Backend, schema, retenção, frontend e defesas implementados | Revisão SEC-46 assinada, provedor real e vigilância configurados, medições operacionais de aceite DB-46 |
| 47 | Interface e E2E implementados; CI remoto verde | Liberação da interface condicionada à revisão SEC-46; assistência continua desligada |
| 48 | Gate, métricas de custo, runbook e ensaios sintéticos prontos | Manifesto real, piloto na conta autorizada, avaliações/pedagogia/VoiceOver, orçamento e alertas reais, aceites operacionais |
| BE-49 | Concluído, incluindo os cinco smokes | Nenhuma entrega de código pendente neste pacote |
| FE-49 | Publicada no PR #41; CI e deploy aprovados | Aceite manual de acessibilidade, sem encerrar o piloto |
| DB-49 | Publicada no PR #41; CI remoto aprovado | Nenhuma entrega de código pendente neste pacote |
| INFRA-49 | Publicada no PR #41; upgrade aprovado no CI | Nenhuma entrega de código pendente neste pacote |
| SEC-49 | Publicada no PR #41; rotação aprovada no CI | Nenhuma entrega de código pendente; ensaio não altera segredos reais |

**Publicação mais recente:** [PR #41](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/41)
integrada em `9cc14fe74caf6180ca8dd63f6d2176e6f9562719` em 29/10/2026.
[CI e deploy da main](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/actions/runs/40926233714)
aprovados. Os **677 arquivos versionados** da VM coincidiram com o release;
web, API, worker e banco saudáveis. Backups anterior e posterior verificados
na própria VM. O primeiro deploy falhou por readiness transitório do worker;
o probe oficial voltou a passar, e a repetição somente do deploy foi aprovada.
Não houve mudança de schema neste pacote nem rotação de segredos de produção.

As referências a publicação/CI pendentes nos registros locais abaixo são
históricas e ficam superadas por esta comprovação. A próxima frente é o
fechamento operacional da 46 e a preparação do piloto da 48, acompanhados na
[matriz de aceite](matriz_aceite_sprint_48.md).

**Publicações anteriores:** PR #39 integrada em `41aa3f7`; PR #40 em
`ef47515`, corrigindo os chunks antigos que retornavam 404 no Caderno após
um deploy. CI e deploy da `main` aprovados no run `40880779035`; os 636
arquivos versionados da VM foram comparados com o código local, sem divergência.
Web, API, worker e banco saudáveis. Os bundles antigos recuperados responderam
HTTP 200 com SHA-256 idêntico ao artefato original. O volume de assets passa a
reter versões por mais de 30 dias após sua retirada.

O release anterior incluiu backup público, restore em clone isolado na própria
VM, ensaio de migration/leitura pela aplicação e backup posterior. Isso não
substitui as avaliações do piloto com diálogos reais, a revisão assinada ou
os aceites operacionais específicos ainda indicados no ciclo 48.

**Correções do checklist:** SEC/BE/FE-45 já tinham implementação registrada;
o spike IA-45 e o manifesto exemplo já existem; DB-46 já está aplicado; a
retenção descrita em DB-48 foi antecipada em DB-46 e possui testes; INFRA-47
já foi aprovado remotamente. Nenhum desses itens deve gerar retrabalho.

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
Sprint 43 (registro no [runbook](historico_operacao_sprints_37_44.md#sprint-44--implantação-autorizada-no-estudo-em-21102026));
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

- [x] `security_opt: [no-new-privileges:true]`, `cap_drop: [ALL]` e
  `read_only: true` onde couber, na stack EasyPanel primeiro.
- [x] `server_tokens off`, `gzip_vary on`, `limit_req_zone` em `/api/auth/`.
- [x] `docker-entrypoint.prod.sh` tolera volume read-only, removendo o
  `entrypoint: []` + UID duplicado em dois Compose.
- [x] `shellcheck`, `hadolint` e `actionlint` no CI.
- [x] Pins de patch nos estágios de build (`uv`, `node`).

Critérios de aceite: Trivy mantém zero críticas/altas; os quatro shell
scripts passam no shellcheck; a stack pública sobe com as três opções de
hardening e todos os smokes verdes.

### BE-45 Extração de serviços e tipagem

Entregas:

- [x] `services/completion.py` a partir de `get_course_completion`
  (`api/courses.py:137`, 297 linhas); o router fica com validação, resolução
  e cabeçalhos.
- [x] `services/writing_feedback.py` a partir de `analisar_texto`
  (`api/writing.py:292`, 205 linhas): rubrica, reserva de cota, provedor,
  persistência, evidência e revisão como funções nomeadas.
- [x] Mover `adicionar_item_revisao`, `adicionar_cartas` e
  `remover_item_por_origem` de `api/review.py` para `services/review.py`;
  atualizar os quatro imports.
- [x] Um helper único de conferência de idempotência em `tentar`
  (`api/progress.py:461` e `:501`).
- [x] Colunas enum-like como `Mapped[Literal[...]]`; zero
  `type: ignore[arg-type]` em `app/`.
- [x] Consolidar os pares "query legada / query de página" em `review.py`,
  `speaking.py`, `writing.py` e `me.py`; nenhum `-> Any` em `api/`.
- [x] Alinhar `POST /writing/prompts/{id}/feedback` ao contrato de revisão:
  ou passa a chamar `require_revision` e declara o 428, ou sai do registro
  `REVISIONED_WRITES` do frontend. Hoje o cliente envia e o servidor ignora.
- [x] 428 próprio (`idempotency_key_required`) quando `grade` recebe revisão
  mas não a chave; o frontend trata os dois códigos no mesmo banner.

Critérios de aceite: nenhum endpoint acima de 80 linhas em `api/`; cobertura
não cai abaixo de 93%; baseline OpenAPI inalterado neste pacote.

### FE-45 Caderno em camadas e estado derivado

Entregas:

- [x] `api/notebook.ts` com 4 queries e 4 mutações via `useQuery`/
  `useMutation` lançando `ApiError`; fim dos 8 `throw Error()` vazios.
- [x] `usePagedItems` substituído por `useInfiniteQuery`; remoção do
  `setSpeakingEntries` manual.
- [x] `NotebookPage` dividida em `NotebookCompose`, `NotebookList`,
  `WritingHistorySection`, `SpeakingHistorySection`,
  `HistoricalEvidenceSection`.
- [x] `LessonRail`: o toggle manual de unidade sobrevive a refetch do
  currículo.
- [x] Política única de `retry`/`networkMode` documentada em `api/queries.ts`
  e aplicada a `dashboard.ts`, `review.ts` e `practice.ts`.

Critérios de aceite: nenhum arquivo de página acima de 300 linhas; teste de
regressão do toggle da `LessonRail`; mensagens de erro do Caderno exibem o
`request_id` quando existe.

### DB-45 Schema aditivo do assistente

Depende de IA-45. Migration única, aditiva, sem alterar tabelas existentes
além de ampliar duas constraints.

Entregas:

- [x] Tabela `speaking_dialogue`: `user_id`, `lesson_id`, `mode`
  (`script`, `guided`, `free_unit`), `state`, `content_version` e fingerprint
  do recorte da aula, `provider_name`, `rubric_version`, `started_at`,
  `ended_at`, `turn_limit`.
- [x] Tabela `dialogue_turn`: `dialogue_id`, `position`, `role`
  (`student`, `partner`), `input_kind` (`audio`, `text`),
  `speaking_attempt_id` opcional, `transcription_job_id` opcional,
  `transcript`, `checks` (JSONB, só códigos e booleanos), `partner_text`,
  `hints` (JSONB, só códigos permitidos), `confidence`, `cost_microusd`,
  `human_rating`, `created_at`; unicidade `(dialogue_id, position)`.
- [x] `ck_assist_modality` passa a aceitar `conversation`;
  `skill_evidence.source_type` aceita `dialogue_turn`; origem de
  `review_item` aceita `dialogue_missed_term`.
- [x] `ondelete` em todas as FKs, `timestamptz`, índice keyset
  `(dialogue_id, position)`, grants para `aulas_runtime` e `aulas_worker`.
- [x] Exclusão de conta e exportação pessoal enxergam as duas tabelas.

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
- [x] Spike de latência: 30 turnos sintéticos em Ollama `qwen2.5:7b` no Mac
  e 30 em um gateway HTTPS; registrar p50/p95 e custo por turno.
- [x] Decisão de TTS (registrada no ADR): `speechSynthesis` do navegador como padrão (zero custo,
  dado não sai do dispositivo, funciona offline); gateway de TTS fica para
  depois do piloto, se a qualidade da voz for reprovada.
- [x] Manifesto **exemplo** para a modalidade `conversation` em
  `config/assist-provider-review.example.json`; aprovações reais continuam
  pendentes no IA-48 e não são inferidas do exemplo.

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

Branch `sprint/45-deploy-e-fundacao`. Três pacotes avançaram no mesmo dia do fechamento do ciclo 44 (INFRA-45,
IA-45 e DB-45); o BE-45 e o FE-45 foram executados em 25/10/2026 e o SEC-45 em 26/10/2026 —
os seis pacotes do ciclo estão implementados.

| Pacote | Entregue | Pendente |
|---|---|---|
| INFRA-45 | nginx resolve a API por requisição e deixa `/` e `/index.html` sem cache; `worker-health` + healthcheck nos três Compose (provado no worker de dev: ok com 60 s, reprovado com 1 s); `seed` fora do gate como serviço próprio no EasyPanel; `ops/deploy_public.sh` (13 testes simulados, dry-run sem contato com a VM) e `make deploy-public`; job `deploy` gated por secrets; SARIF do Trivy na aba Security; `timeout-minutes` em todos os jobs; `cancel-in-progress` só fora da `main`; `dependabot.yml`. 161 testes operacionais verdes | criar as secrets `PUBLIC_DEPLOY_SSH_KEY`, `PUBLIC_DEPLOY_KNOWN_HOSTS` e `PUBLIC_DEPLOY_HOST` (ação de Jeferson, com chave SSH exclusiva); provas dos critérios 1 a 3 (PR vermelho não implanta; recriar só a API sem 502; worker travado reiniciado) ficam para quando a stack E2E ou a pública rodar o código novo; build único com cache GHA adiado |
| IA-45 | ADR `adr_assistente_de_conversa.md` com modos, pipeline, vedações, códigos de check, contrato HTTP, cota/retenção e voz do navegador; `app/services/dialogue_prompts.py` (brief do seed, roteiro por falante, prompt `dialogue-prompt-v1`, schema restrito aos códigos reprovados, saneamento) com 8 testes puros; `ops/dialogue_latency_spike.py` (mock, Ollama, gateway) com 6 testes e execução simulada 30/30 | ADR **aprovado por Jeferson em 21/10/2026**, liberando DB-45. Provedor escolhido: Cloudflare Workers AI; spike real com 4 corridas de 30 turnos (tabela no ADR): modelo p95 ≈ 2 s; critério de 8 s atendido só com `whisper-tiny-en` (turno p95 3,6 s, ~5,4 neurons, ~1.850 turnos/dia na cota); `turbo` e `base` reprovam pela cauda da transcrição. Resta o manifesto da modalidade `conversation` em `config/assist-provider-review.example.json` (IA-48). **Decisões de produto fechadas por Jeferson em 26/10/2026**, as três registradas no ADR com a consequência que as motivou: 12 turnos do aluno por diálogo no Guiado; cota diária de **24** — mantida como dois diálogos completos, porque com limite 12 uma cota de 20 daria 429 no turno 8 do segundo diálogo, no meio da conversa; voz do `speechSynthesis` do navegador, com **legenda como único caminho quando o dispositivo não tem voz en-US**, para que uma voz ruim não passe por aprovada no gate humano. Nenhuma decisão de produto bloqueia o BE-46 |
| DB-45 | Migration `e3a1c7d9b250`, aditiva: `speaking_dialogue` e `dialogue_turn` com `ondelete` em todas as FKs, `timestamptz`, unicidade/keyset `(dialogue_id, position)`, checks de forma (`jsonb_typeof` em `checks`/`hints`), estados, limites e `expires_at` para a retenção dos textos; `ck_assist_modality` aceita `conversation`; a auditoria de origens aceita `dialogue_turn` em `review_item` (motivo `dialogue_missed_term`) e em `skill_evidence`; grants por coluna na migration e em `ops/roles_policy.sql` (API só altera `human_rating` do turno; worker preenche o resultado e nunca apaga; cascatas são do PostgreSQL); exclusão de conta por cascata e exportação 2.1 com `dialogues`/`dialogue_turns`; prévia editorial conta as duas tabelas. Provas em 21/10/2026: `alembic upgrade head` duas vezes e `alembic check` limpos na base de teste; laboratório de papéis reprovisionado do zero e `make test-roles` verde com as sondas novas; downgrade não destrutivo (reverte só com tabelas vazias, senão bloqueia com motivo); teste da migration em schema sintético, testes de exportação e de exclusão | Aplicar no clone do estudo e na produção pela sequência de release (DB-46). Retenção de `transcript`/`partner_text` entra com o job em BE-46 (`expires_at` já existe). Decisões registradas: `dialogue_turn.user_id` desnormalizado para as regras de posse e a exportação; `state`, `error_code`, `fallback` e `completed_at` no turno para o contrato GET. Dois pontos exigem migration própria em BE-46: áudio do Guiado sem `transcript_cue` (`speaking_attempt.transcript_cue_id` é obrigatório hoje) e o job de diálogo na fila (`transcription_job.speaking_attempt_id` é obrigatório); o worker também precisará de SELECT nas tabelas de conteúdo que montam o brief |
| BE-45 | `services/completion.py` (rota 296 → 28 linhas), `services/writing_feedback.py` (205 → 11, com rubrica, reserva, provedor, persistência, evidência e revisão como funções nomeadas), `services/review.py` com as três origens da fila e os quatro imports repontados, `services/operations_metrics.py` + `schemas/operations.py` (metrics 153 → 9); `_conferir_idempotencia` único nos dois caminhos de `tentar` (177 → 65) e helpers nomeados em `painel_hoje` (143 → 31), `create_practice_session` (115 → 66), `submit_course_review` (115 → 80), `meu_progresso` (104 → 44) e `enviar_audio` (91 → 41); `app/domain/enums.py` como fonte única dos conjuntos fechados, colunas enum-like em `Mapped[Literal[...]]` e **zero `type: ignore` em `app/`** (eram 17, todos da mesma causa); recorte de curso/unidade compartilhado pelas listas legadas e paginadas em `review`, `speaking`, `writing` e `me`, com `Select[*tuple[Any, ...]]`/`Row[*tuple[Any, ...]]` no lugar de `Any`; `/feedback` deixa de declarar `expected_revision` (herdado por acidente e ignorado) e passa a exigir `operation_key` com 428 `idempotency_key_required`; `grade` ganha o mesmo código em vez de reaproveitar `revision_required`. Provas em 25/10/2026: nenhuma rota de `api/` acima de 80 linhas (medido por AST), ruff e mypy strict limpos em 99 arquivos, pytest **1183 passaram** com cobertura **94%**, passo pós-cutover (`LEGACY_WRITES_UNTIL` no passado) **135 passaram**, 166 testes de `ops/` e vitest 397 | O baseline do contrato mudou **de propósito** nas duas últimas entregas (o gate existe para o diff aparecer no PR): `openapi.json` e `schema.d.ts` regerados. O registro `REVISIONED_WRITES` do frontend passou a `['operation_key']` no feedback e o `WritingWorkspace` parou de enviar a revisão que o servidor ignorava |
| FE-45 | `api/notebook.ts` com as 4 listas em `useInfiniteQuery` (+ a das análises salvas) e 4 mutações, todas lançando `ApiError`: os 8 `throw Error()` vazios do Caderno viraram zero e as mensagens mostram o `request_id` quando a API devolve um (`failureMessage`). `usePagedItems` sai do Caderno — as páginas acumulam no cache, não num `useState` da página — e o `setSpeakingEntries` manual da exclusão vira uma edição precisa do cache (`setQueriesData`) somada ao evento `speakingDelete` do mapa único; o mapa ganhou `notebookEntry` porque a regra do FE-44 vale (nenhum outro módulo de produção invalida cache por conta própria, e o teste pega até menção em comentário). `NotebookPage` 712 → 124 linhas, dividida em `NotebookCompose`, `NotebookList`, `WritingHistorySection`, `SpeakingHistorySection` e `HistoricalEvidenceSection` em `features/notebook/`, com `labels.ts` e o `useAnnouncedPaging` que preserva o foco no total anunciado. `LessonRail`: a unidade aberta passou a ser **estado derivado** (escolha do aluno no escopo > unidade da busca > unidade da rota > primeira do currículo) e o `useEffect` que dependia de `curriculum.data` saiu — era ele que fechava a unidade a cada revalidação. `READ_POLICY` (networkMode/retry) documentada em `api/readPolicy.ts` e aplicada aos 8 módulos de consulta. Provas em 25/10/2026: eslint, tsc e `check:api` limpos; vitest **400 passaram** (3 novos: regressão do toggle sob revalidação — reprova se o efeito antigo volta —, `request_id` na falha do Caderno e a linha 2.x da exportação); orçamento de bundle verde (127,6 de 132 KiB iniciais, 178,6 de 184 totais) com `WritingHistorySection` virando chunk lazy próprio | A política ficou em `api/readPolicy.ts`, não em `queries.ts`: nove testes substituem `queries.ts` por mock e a constante desapareceria junto com os hooks. **O critério "nenhum arquivo de página acima de 300 linhas" vale hoje para o Caderno, não para o resto**: `CourseCompletionPage` (529), `StudyPage` (507), `ReviewPage` (443), `MapPage` (443) e `CourseReviewPage` (374) seguem acima da linha. Nenhuma delas aparece nas entregas do FE-45, e o próprio FE-46 repete o critério de forma mais ampla ("nenhum componente acima de 300 linhas") junto das extrações de `WritingWorkspace`, `PracticeRunner` e `ShadowingPractice` — é lá que essas páginas caem sem retrabalho. Decidir antecipar isso para o FE-45 é do Jeferson. `usePagedItems` continua em uso na `ReviewPage` |
| SEC-45 | **Hardening**: `security_opt: [no-new-privileges:true]` nos 7 serviços da stack pública; `cap_drop: [ALL]` com apenas as capabilities que o entrypoint usa (`CHOWN`/`FOWNER` para ajustar o diretório das gravações, `SETUID`/`SETGID` para sair de root) nos serviços do backend, só `SETUID`/`SETGID` no worker e `CHOWN`/`SETGID`/`SETUID`/`NET_BIND_SERVICE` no nginx; `read_only: true` + `tmpfs` no `web` e no `worker`. O mesmo foi aplicado à `compose.prod.yml` — é ela que ensaia a produção, divergir tiraria o valor do ensaio. O `db` fica só com `no-new-privileges` porque o Postgres ajusta o dono do PGDATA e troca de usuário no primeiro boot do volume. **Borda**: `server_tokens off`, `gzip_vary on` e `limit_req_zone`/`limit_req` (600 r/m, rajada 120, **429**) em `/api/auth/`, com as diretivas de proxy extraídas para `frontend/api-proxy.conf` para `/api/` e `/api/auth/` não divergirem. **Entrypoint**: `docker-entrypoint.prod.sh` tolera volume e FS read-only, o que removeu o `entrypoint: []` + `user: "10001:10001"` dos dois Compose — o UID volta a existir num lugar só (o Dockerfile). **CI**: job `infra-lint` com shellcheck 0.11.0, hadolint 2.14.0 e actionlint 1.7.7 em container de versão fixa. **Pins**: `node:24.22.0-alpine3.24`, `uv:0.11.33`, `su-exec=0.3-r0`. Provas em 26/10/2026, na stack pública subida num projeto descartável local (`aulas-sec45-lab`, volumes próprios, derrubada depois): gate `migrate → permissions` ok, `api`/`web`/`worker` **healthy**, seed concluído, schema `e3a1c7d9b250`; `/api/health` 200 atravessando o nginx endurecido; `Server: nginx` sem versão e `Vary: Accept-Encoding` confirmados no ar; registro 201 pela rota com limite; `/app/data/speaking` com `drwx------ app app` (o chown funcionou sob `cap_drop: ALL`); uvicorn como `app` no PID 1; worker como `app` **sem `user:` nem `entrypoint: []`**, com `/app/teste` recusado por FS read-only, `/tmp` gravável e `worker-health` exit 0; `/api/operations/metrics` com as 7 seções. shellcheck, hadolint e actionlint passam nos 6 scripts, 5 Dockerfiles e nos workflows. 17 testes em `ops/tests/test_easypanel_deploy.py` verdes, 6 deles novos | O gate de hardening virou teste (`ContainerHardeningTests`), senão um edit futuro desfaz as três camadas em silêncio. A extração do `api-proxy.conf` quebrou 2 testes de contrato do nginx, atualizados para ler os dois arquivos e exigir que as duas rotas incluam o mesmo proxy. **Critério "Trivy mantém zero críticas/altas": a API está em 0; a web saiu de 5 para 3 altas e não chegou a zero.** As 5 originais também estão na imagem da `main` — drift do base fixado por digest contra o banco de CVEs, não regressão deste pacote. O upstream republicou o tag `nginx:1.30.6-alpine3.24` sobre o alpine 3.24.3: re-ancorar o digest em `ci_pull_bases.sh` (`sha256:970364…` → `sha256:47928b…`, idêntico nas duas origens) encerrou CVE-2026-77214 (`libexpat`) e CVE-2026-88806 (`libx11`). As 3 restantes (`brotli-libs`, `curl`, `libcurl`) **não têm correção em nenhuma imagem nginx alpine3.24 publicada hoje** e nenhuma tem caminho de execução no runtime (comprimimos com gzip, não brotli; o nginx não invoca curl) — triagem registrada em `docs/politica_triagem_seguranca_sprint_42.md` no formato que a política exige, com a decisão de aceite reservada ao release manager. Lição: **o gate `test_ci_pull_bases` pegou meu pin do node**, porque o pré-carregamento é por digest e o alias tem de bater com o `FROM`; o digest do node não mudou (o tag novo aponta para a mesma imagem), só o nome. A prova na VM pública **foi feita depois, no release do ciclo**, nos containers reais: ver "Fechamento e release" adiante |

Dois agentes que implementavam o INFRA-45 foram interrompidos por limite de
sessão da API durante as validações; o trabalho foi revisado linha a linha,
um teste corrigido (vazamento de variável de ambiente no cenário de host) e as
validações concluídas antes do commit.

**Fechamento e release, 26/10/2026.** PR #26 publicado e integrado por merge
(`37d28b6`). A `main` disparou o **primeiro deploy automático** do projeto:
3m39s até a stack pública de pé, sem passo manual. Produção no schema
`e3a1c7d9b250`. O endurecimento do SEC-45 foi conferido nos containers reais
por SSH, e não apenas no laboratório descartável: `web` e `worker` com
`read_only=true` e o `worker` com somente `SETGID`/`SETUID` entre as
capabilities. A sequência de release fechou com backup cifrado antes e depois,
guardados fora da VM. As 3 altas restantes da imagem `web` foram aceitas pelo
release manager, com a triagem registrada em
`docs/politica_triagem_seguranca_sprint_42.md` no formato que a política exige.

---

## Ciclo 46 — Assistente no backend e no banco; motores de sync no frontend

### BE-46 Motor de diálogo, provedor, fila e cota

Entregas:

- [x] `domain/dialogue.py` puro: cobertura de termos-alvo com a normalização
  de `domain/answers.py`, verificação de padrões gramaticais declarados no
  bloco da aula, limites de comprimento, códigos de check estáveis.
- [x] `services/dialogue.py`: criação de diálogo com fingerprint do recorte
  da aula, roteiro a partir dos `transcript_cue`, montagem do prompt,
  chamada a `call_dialogue_provider` (gateway/ollama) com JSON Schema e
  filtro de saída, persistência, fallback para o Roteiro.
- [x] Turno de áudio reaproveita `audio_upload`, `audio_inspection`,
  `audio_storage` e a fila durável de transcrição; o job de diálogo é um
  tipo novo na mesma fila, com `FOR UPDATE SKIP LOCKED`, retomada e backoff.
- [x] Modalidade `conversation` em `assist_quota` com cota diária própria
  (`ASSIST_DIALOGUE_DAILY_TURNS`, padrão **24** pela decisão de 26/10/2026 —
  dois diálogos completos) e custo somado de STT + modelo.
- [x] Rotas do contrato IA-45 com ownership no `WHERE`, 404 para recurso
  alheio, idempotência por `(dialogue_id, position)`.
- [x] Nenhum texto de turno, transcrição ou resposta do provedor em log;
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

- [x] Aplicar a migration de DB-45 no laboratório e no clone do estudo;
  `alembic check` limpo; grants mínimos; `account_deletion` cobre as duas
  tabelas; exportação pessoal 1.7 com diálogos e turnos.
- [x] Retenção: `transcript` e `partner_text` seguem `ASSIST_RETENTION_DAYS`
  pelo job de manutenção; metadados agregados permanecem.

Aceite: contagens antes/depois iguais nas 39 tabelas históricas; exclusão de
conta sintética zera `speaking_dialogue` e `dialogue_turn` do usuário.

### FE-46 Motores de sincronização fora dos componentes

Prepara o terreno do assistente: a UI do diálogo precisará de uma máquina de
estados de turno fora do React, e o padrão já existe em
`features/media/positionSync.ts` com `useSyncExternalStore`.

- [x] `features/writing/draftSync.ts` extraído de `WritingWorkspace.tsx`
  (fila serial, geração, conflito de revisão, espelho local).
- [x] `features/practice/practicePosition.ts` extraído de `PracticeRunner.tsx`;
  telas internas viram `PracticeIntro`, `PracticeResume`, `PracticeSummary`.
- [x] `features/speaking/speakingUpload.ts` extraído de `ShadowingPractice.tsx`.
- [x] `ExerciseCard`: um componente por `activity_type`; `role="alert"` no
  veredito de erro.
- [x] Casts de corpo de erro em `WritingWorkspace` substituídos por type
  guard sobre `ApiError`.

Aceite: os três motores têm testes sem DOM cobrindo perda de rascunho,
conflito e cancelamento; nenhum componente acima de 300 linhas; 360 testes
continuam verdes.

### SEC-46 Modelo de ameaças e corpus adversarial do assistente

Bloqueia FE-47.

- [x] Modelo de ameaças do assistente: injeção via transcrição do aluno,
  exfiltração de prompt, saída com conteúdo inadequado, abuso de cota,
  IDOR em diálogo alheio, replay de turno, áudio malicioso.
- [x] Corpus adversarial com no mínimo 20 transcrições (instruções ao
  modelo, pedidos de dados pessoais, troca de idioma, conteúdo ofensivo)
  como testes `pytest` que exigem saída dentro do esquema e sem eco de
  instrução.
- [x] Fluxo de dados ao provedor documentado em
  `guia_do_aluno_retomada_offline_privacidade.md` e na política de mídia:
  o que sai (texto do turno, códigos de check), o que não sai (nome,
  e-mail, histórico, áudio quando o provedor é só de texto).
- [ ] Requisitos do provedor em produção: HTTPS, token, região, retenção
  menor ou igual à do projeto, sem uso para treinamento. **HTTPS e token
  passaram a ser exigidos no boot; região, retenção e não-treinamento
  dependem do gate da modalidade `conversation`, que é do IA-48.**

Aceite: os 20 casos passam; a revisão do fluxo de dados está assinada no
documento com data.

### INFRA-46 Provedor em produção, métricas e alerta

- [ ] Provedor de diálogo configurado na stack EasyPanel por gateway HTTPS
  com token; Ollama permanece restrito a dev (a VM é compartilhada com três
  outros projetos e não tem GPU). **`ASSIST_DIALOGUE_URL` e
  `ASSIST_DIALOGUE_DAILY_TURNS` já são declaradas nas duas Compose; falta só
  o valor no painel, que é ação de Jeferson.** A restrição do Ollama ao host
  local em produção já é recusada no boot desde o BE-45.
- [x] Métricas agregadas de diálogo em `/api/operations/metrics`: turnos/dia,
  p95 de latência, falhas de provedor, custo do dia, cota atingida.
- [ ] Ativar o gate de métricas agendado e comprovar o alerta de worker,
  fila e custo. Código e workflow existem; em 29/10 a secret operacional
  do GitHub está ausente, e não há entrada reconhecida no cron root/sistema
  da VM nem comando `sendmail`. Ver inventário abaixo.
- [x] Probe externo de disponibilidade do domínio público.

Aceite: um worker parado por 2 minutos gera alerta; o custo do dia aparece
no painel operacional sem nenhum texto de aluno.

---

### Registro de execução — Ciclo 46, BE-46 em 26/10/2026

Branch `sprint/46-assistente-backend`, sete commits locais.

| Entrega | Estado |
|---|---|
| `domain/dialogue.py` | pronto: quatro códigos estáveis, cobertura de termo por sequência de palavras (não substring) e tolerante a apóstrofo, limites de tamanho nas fronteiras exatas |
| `services/dialogue.py` | pronto: `brief_for_lesson` do banco, `content_fingerprint` só do que o parceiro enxerga, `expectation_for` girando os termos, `admit_turn`/`resolve_turn`/`partner_reply`, fallback para o roteiro |
| Turno na fila durável | pronto: `kind` no job, despacho por tipo reaproveitando `FOR UPDATE SKIP LOCKED`, retomada e backoff; turno por texto não gasta STT |
| Modalidade `conversation` na cota | pronto: orçamento próprio (24/dia), `daily_limit`/`_group`, `/api/assist/status` escopado ao grupo legado |
| Rotas do contrato IA-45 | pronto: 7 endpoints, posse no `WHERE`, idempotência por `operation_key` e por `(dialogue_id, position)` |
| Nenhum texto em log | pronto, com teste que varre o log capturado |

**Critérios de aceite, todos provados.** (1) Com a assistência desligada o Roteiro é completo e o provedor lança se for chamado. (2) Provedor fora do ar devolve `fallback=true` sem perder turno anterior, com os checks idênticos. (3) Cota esgotada recusa na **admissão**, antes de qualquer rede — e o 429 aparece no diálogo seguinte, não no turno 13 do atual, porque o limite do diálogo vem primeiro. (4) Resposta com código inventado ou URL é descartada como `invalid_provider_response`, com o custo já incorrido registrado.

**Correção de costura, registrada por honestidade:** o primeiro desenho da cota ficou dentro da função que fala com o provedor — costura de fluxo síncrono, que cobraria na hora errada num contrato `202 + job_id`. Corrigido para reserva na admissão e consumo no despacho, como a fila de transcrição já fazia.

**Divergência deliberada do ADR:** a tabela previa `202 + job_id` para todo turno. O Roteiro resolve na própria requisição e não enfileira — fazê-lo passar pela fila o tiraria do ar justamente quando o worker estivesse fora, e ele é o modo que precisa sobreviver a isso. Reversível, se a uniformidade do contrato pesar mais.

Dívida que o BE-46 pagou do BE-45: dez colunas enum-like ainda eram `Mapped[str]` com `CheckConstraint` no banco (`mode`, `state`, `role`, `input_kind`, `human_rating` do turno, entre outras). Agora seguem a regra, com os conjuntos em `domain/enums.py`. `app/` continua com zero `type: ignore`.

Provas: ruff e mypy strict limpos (103 arquivos), pytest **1223**, passo pós-cutover **186** (o arquivo de rotas novas entrou na lista do CI), eslint/tsc/`check:api`/vitest 400 e orçamento de bundle verdes. O baseline do contrato mudou de propósito: 7 rotas e 6 schemas novos, com **zero** rotas ou schemas existentes alterados — conferido por comparação semântica, porque o diff por linha de JSON ordenado é ilegível por natureza.

**Falta no ciclo 46:** nada de implementação. O que resta é ação de Jeferson:
assinar a revisão do fluxo de dados (SEC-46), pôr a URL e o token do provedor
no painel e instalar o cron da VM (INFRA-46), e coletar as duas medições de
aceite do DB-46 contra a produção.

---

### Registro de execução — Ciclo 46, INFRA-46 em 26/10/2026

| Entrega | Estado |
|---|---|
| Métricas de diálogo | pronto: seção `dialogue` em `/api/operations/metrics` com turnos, concluídos, falhos, fallback, falhas de provedor, p95 do turno, custo e a cota |
| Gate com custo | pronto: teto de custo, taxa de falha do provedor com amostra mínima, e um check que acusa API mais antiga que o gate |
| Vigilância agendada | pronto nos dois relógios: `operations.yml` em `*/30` como rede externa e `make operations-alert` para o cron da VM |
| Probe externo | pronto: `ops/public_probe.py`, sem credencial, com 5 testes |
| Provedor no painel | **pendente de Jeferson**: as variáveis já são declaradas nas duas Compose; falta o valor |

**Só turnos do aluno entram em `turns`.** A resposta do parceiro vive na mesma
linha do turno, e contar as duas pontas dobraria justamente o número que o
painel compara com a cota.

**A conta da cota no painel é a mesma do 429.** `quota_used` reusa a definição
de `assist_quota.usage` — reservado ainda válido mais consumido, no dia UTC.
Duas definições de consumo divergiriam na primeira mudança de regra, e o painel
passaria a discordar do erro que o aluno recebeu.

**Defeito encontrado ao preparar o item 1:** `ASSIST_DIALOGUE_URL` não existia
em nenhuma das duas Compose de produção. Preencher a URL no painel não chegaria
ao container, e o Guiado ficaria desligado em silêncio — `409 assist_disabled`,
que é indistinguível de "desligado de propósito". As duas variáveis entraram na
`easypanel/compose.yml` e na `compose.prod.yml`, porque divergir tiraria o
valor do ensaio (lição do SEC-45).

**O fixture saudável do gate precisou da seção nova, e foi o teste existente
que pegou isso** — ele reprovou porque a seção ausente passou a ser crítica. O
check `dialogue_quota_accounting` existe por causa disso: uma API anterior ao
INFRA-46 não traz a chave, e indexar direto daria "gate falhou" sem dizer que a
causa é diferença de versão.

**Dois relógios, e a razão de cada um.** O cron do GitHub é melhor-esforço e
atrasa; ele não entrega a resolução de 2 minutos que o aceite pede. O caminho
principal é o cron da VM (`make operations-alert`, silencioso quando está bom,
falante quando não — o contrato que o `cron` espera para mandar e-mail); o
workflow é a rede de segurança para quando a VM inteira estiver fora e nenhum
cron dela for reclamar. O alerta por e-mail não usa segredo de SMTP: no GitHub
é a notificação nativa de falha de workflow agendado, e na VM é o `MAILTO` do
crontab — **que depende de um MTA funcionando lá**, e isso está escrito no
runbook em vez de assumido.

**O aceite, ponto a ponto.** "Worker parado por 2 minutos gera alerta": provado
em `test_worker_parado_por_dois_minutos_gera_alerta`, com o limiar de 60 s que
já existia. "O custo do dia aparece no painel sem nenhum texto de aluno":
provado nos dois lados — `test_custo_do_dia_aparece_no_relatorio_sem_texto_de_aluno`
no gate e `test_metrica_de_dialogo_conta_o_dia_sem_dizer_o_que_foi_falado` na
API, que varre a resposta procurando a transcrição, a fala do parceiro e o
e-mail da conta.

Provas em 26/10/2026: ruff e mypy strict limpos; pytest **1287**; pós-cutover
**186**; **180 testes operacionais**; actionlint limpo no workflow novo;
`make easypanel-check` aprovado; baseline do contrato regravado com 1 schema
novo e **zero rotas alteradas**; frontend 431 com `check:api` alinhado.

---

### Inventário operacional e ativação do probe — 29/10/2026, após PR #41

Antes desta intervenção, o repositório tinha somente as três secrets de deploy;
não havia `PUBLIC_PROBE_ORIGIN`, `OPERATIONS_TOKEN` nem variáveis de orçamento.
O estado verde do workflow, sozinho, não comprovava vigilância ativa.

`PUBLIC_PROBE_ORIGIN` foi configurada com o domínio público existente, e o
[run 40932540081](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/actions/runs/40932540081)
executou o **probe público com sucesso**. A etapa autenticada ficou `skipped`,
como esperado enquanto faltar a secret operacional. O agendamento existente
é a cada 30 minutos, sujeito aos atrasos do GitHub; não comprova alerta em 2 minutos.

Inventário somente leitura, retornando apenas booleanos: API e worker com
`ASSISTED_FEATURES_ENABLED=false`, `DIALOGUE_PRACTICE_ENABLED=false`, URL de
diálogo e token do provedor ausentes; token operacional presente nos dois
containers. Não foi exportado nenhum segredo. Crontab de root, `/etc/crontab`
e `/etc/cron.d` não continham referências a `operations-alert`,
`operations-check` ou `observability_check`; `sendmail` não estava disponível.
Isso não inventaria agendadores de outros usuários ou serviços personalizados.

O avaliador `ops.observability_check` foi executado uma vez dentro da API,
usando o token existente sem copiá-lo para fora da VM: **14 checks `ok` e
dois `warning`**, somente para orçamento diário/mensal ainda indefinidos.
Não houve teste de entrega de e-mail nem parada deliberada de worker.

A decisão histórica de provedor já existe: Cloudflare Workers AI, conforme
o ADR. Faltam endpoint de gateway, credencial em armazenamento privado e
revisão SEC-46. A matriz da 48 foi criada sem presumir assinatura ou consentimento.
O responsável informou uso do plano gratuito nesta continuação: limite de gasto
adotado de **USD 0/dia, USD 0/mês e USD 0 no piloto**, sem habilitar cobrança.
O monitor local foi ajustado para aceitar zero explícito; custo positivo ou
desconhecido continua crítico. A modalidade efetiva da conta e a conciliação
da franquia ainda precisam de comprovação. Ruff, mypy e **345 testes
operacionais** passaram; o novo suporte a orçamento zero ainda não foi publicado.
Também é necessário preparar a restrição do piloto a uma conta: o status
e a admissão de diálogos usam configuração global, sem allowlist por conta
nesses caminhos. Não ligar a flag global como se ela restringisse o piloto.

### Registro de execução — Ciclo 46, SEC-46 em 26/10/2026

| Entrega | Estado |
|---|---|
| Modelo de ameaças | pronto: `docs/modelo_ameacas_assistente_2026-10-26.md`, sete ameaças com defesa, prova e risco residual |
| Corpus adversarial | pronto: 23 casos em cinco categorias, 54 testes em `tests/test_dialogue_adversarial.py` |
| Fluxo de dados documentado | pronto: seção nova no guia do aluno e na política de mídia, mais a tabela no modelo de ameaças |
| Requisitos do provedor | HTTPS e token exigidos no boot; região, retenção e não-treinamento **sem verificação** (ver bloqueio) |
| Revisão assinada | **pendente**: é ato do responsável, e o FE-47 segue bloqueado até ela |

**O corpus não prova que o modelo se comporta** — ele não roda nos testes.
Prova as três coisas que não dependem disso: a transcrição entra achatada em uma
linha e na posição de dado, o `system_prompt` sai **idêntico byte a byte**
qualquer que seja a transcrição, e a resposta é recusada ou sai dentro do
contrato. Treze dos 23 casos esperam recusa (`invalid_provider_response`), e o
aluno recebe o roteiro da aula.

**Três defeitos reais foram fechados, dois deles meus:**

1. *Meu, do BE-46.* O gate de produção que exige HTTPS e token listava só
   `assist_transcription_url` e `assist_writing_url`. A URL do diálogo, que eu
   adicionei, ficou de fora: em produção o texto do aluno poderia sair em HTTP
   puro e sem token **sem o boot reclamar**. Dois testes novos cobrem os dois
   lados da recusa e um o caminho válido.
2. *Meu, do IA-45.* A saída que ecoa o prompt passava pelo saneador se fosse
   curta e sem URL — o aluno leria as instruções, que é a ameaça 2 do próprio
   modelo. `leaks_prompt` recusa a resposta que traz de volta marca nossa.
3. *Descoberto pelo teste, não previsto.* O aplicativo nunca manda dado do
   aluno, mas o aluno pode dizer o dele dentro da frase — "my email is…" é
   plausível numa aula de inglês, e o item 3 do pacote promete que e-mail não
   sai. O que sai passou a ser redigido; a transcrição **guardada** fica
   intacta, porque é o histórico de prática dele e os checks rodam aqui sobre o
   texto original. Idade, hora e número de aula passam (limite de 8 dígitos).

**Risco residual aceito e escrito:** não há moderação de conteúdo na saída. Uma
resposta grosseira dentro de 280 caracteres, sem URL e sem eco de prompt, chega
ao aluno. A mitigação é processual — recurso experimental, instalação de um
aluno que é o próprio responsável, e o gate humano do IA-48 antes de qualquer
liberação. Um filtro de palavras meia-boca daria falsa garantia e foi
deliberadamente **não** implementado; o caso `pede_nota` está no corpus com
`esperado="saneada"` para que esse limite fique visível no teste, e não só no
documento.

**Bloqueio identificado em 26/10, corrigido localmente em 29/10 no registro IA-48 abaixo:**
naquela execução, o gate de liberação cobria `transcription` e
`writing`; a modalidade `conversation` não existe nele — `AssistModality` é
`Literal["transcription", "writing"]` e `evaluate_gate` decide
`provider_configured` como "transcrição, senão escrita", de modo que uma
conversa seria julgada pela configuração do provedor **de escrita**. O banco já
aceita `conversation` (DB-45) e a cota já a trata (BE-46). Enquanto o gate não
a conhecer, região, retenção e não-treinamento do provedor de diálogo são
promessa escrita sem verificação.

Provas em 26/10/2026: ruff e mypy strict limpos (103 arquivos); pytest
**1285 passando** (eram 1228 no fim do DB-46); passo pós-cutover **186**.

---

### Registro de execução — Ciclo 46, FE-46 em 26/10/2026

| Entrega | Estado |
|---|---|
| `features/writing/draftSync.ts` | pronto: fila serial, revisão imutável, espelho local e conflito, com 9 testes sem DOM |
| `features/practice/practicePosition.ts` | pronto: espelho da posição, reconciliação e a chave de idempotência reaproveitada, com 10 testes sem DOM |
| `features/speaking/speakingUpload.ts` | pronto: envio em dois passos, aborto e travessia de sessão, com 11 testes sem DOM |
| `ExerciseCard` por `activity_type` | pronto: 4 componentes de campo, `useExerciseActions`, `ExerciseVerdict` com `role="alert"` no erro |
| Type guard no lugar do cast | pronto: `conflictingDraft` valida o corpo do 409 |
| Nenhum componente acima de 300 linhas | pronto: 11 componentes desceram da linha, o maior agora tem 293 |

**Os três motores seguem o padrão do `positionSync`**: classe sem React,
transporte injetado, `useSyncExternalStore` no hook. Não é simetria por gosto —
é o que permite provar sem DOM os casos em que o aluno perde trabalho, e é a
máquina de estados que a tela do diálogo (IA-47) vai reusar.

**Quatro defeitos apareceram ao traduzir componente em motor.** Dois eram meus,
introduzidos na tradução, e dois vinham do código original:

1. *Meu.* No `speakingUpload`, a identidade do envio virou o `AbortController`,
   que o `finally` anula antes da checagem: todo envio bem-sucedido parecia
   obsoleto, `saving` nunca voltava a falso e o reenvio era recusado. Virou uma
   geração.
2. *Meu.* No `draftSync`, `createVersion` não esperava a fila: a versão corria
   com o autosave do mesmo texto e a ordem era o acaso do temporizador. Agora
   ela dá `flush` antes.
3. *Do original.* Em `practicePosition`, uma confirmação em voo apagava o
   espelho local mesmo quando o aluno já tinha avançado para outra posição —
   perdendo a navegação mais nova, a única que existia fora da tela. O espelho
   só é esquecido se ainda for a posição que a conta confirmou.
4. *Do original.* Em `speakingUpload`, o id da tentativa era anotado **depois**
   de olhar a sessão: uma troca de sessão entre a criação e o áudio esquecia
   uma tentativa que já existia na conta, e o reenvio criava outra. O id passa
   a ser anotado antes.

**O veredito do exercício passou a alertar.** "Ainda não" e "Erro" pedem ação do
aluno e eram anunciados com `role="status"`, que espera o silêncio. Agora são
`role="alert"`; acerto, gabarito e fila seguem `status`. Dois testes afirmam os
dois lados, senão a distinção se perde no próximo edit.

**O orçamento de bundle precisou de atenção, e o teto não foi tocado.** As
pastas novas caíam fora dos padrões por caminho do `manualChunks` e viravam um
chunk avulso de 10 KiB duplicando código compartilhado; `features/{review,
completion,checkpoint}/` foram para `study-tools` e `features/exercise/` para
`lesson-study`. Mesmo corrigido, o total subiu de 179,7 para **182,6 de 184,0
KiB** — custo por módulo da divisão —, e a margem caiu de 4,3 para 1,4 KiB.
Levantar o teto é decisão a ser tomada de frente, não efeito colateral de uma
refatoração; fica registrado para quem decidir.

Provas em 26/10/2026: eslint, tsc e `check:api` limpos; vitest **431 passando**
(eram 400 no fim do FE-45; 30 dos novos são dos três motores e 1 do veredito);
orçamento verde; e — o que mais importa num pacote de refatoração — dos **141
testes dos 11 componentes tocados, 139 passam sem uma linha alterada** (os
outros 2 são os novos do veredito), incluindo os arquivos de teste de 413
linhas do `WritingWorkspace`, 530 do `PracticeRunner` e 562 do
`ShadowingPractice`.

---

### Registro de execução — Ciclo 46, DB-46 em 26/10/2026

| Entrega | Estado |
|---|---|
| Migration `b7e5f1c38a42` | pronta: `aulas_retention_batch` ganha o escopo `dialogues`, o único dos cinco que **anonimiza** em vez de apagar linha; índice de varredura por `expires_at`; downgrade recusa quando há turno de diálogo |
| Escopo no job de manutenção | pronto: `dialogues` entra na varredura **mesmo com `MAINTENANCE_CLEANUP_ENABLED` desligada** |
| Item 1 do pacote (migration do DB-45 em produção) | aplicado no release do ciclo 45 (`e3a1c7d9b250`), com `alembic check` limpo, grants mínimos, exclusão por cascata e exportação 2.1 provados em DB-45 — **sem** as duas medições de aceite (ver abaixo) |

**O turno vence; a prova de que o aluno praticou fica.** É a diferença deste
escopo. Apagar a linha levaria junto `checks`, custo, `confidence`, `position` e
`human_rating` — exatamente a evidência que o gate humano do IA-48 vai usar e o
histórico que o aluno vê. Então o lote zera `transcript`, `partner_text` e
`hints` e deixa a linha de pé. A idempotência vem do próprio filtro: a segunda
passada não encontra mais nada para anonimizar e conta 0, senão o lote giraria
para sempre sobre as mesmas linhas.

**Por que não fica atrás da flag.** Os escopos que apagam linha ou tocam arquivo
são opt-in por `MAINTENANCE_CLEANUP_ENABLED`; este não pode ser. Uma instalação
que não ligou a flag guardaria transcrição de aluno além do prazo prometido — e
o prazo de retenção é promessa, não preferência de instalação.

**Defeito meu, encontrado pela suíte completa.** O teste que roda o `sweep` sem
a flag não pedia `session` nem `client`, logo não passava por `banco_por_teste`
— a fixture que faz `dispose_engine()` no teardown. O pool ficava com conexões
presas no event loop daquele teste e o teste seguinte que abria conexão morria
com `attached to a different loop`, aparecendo como ERROR em
`test_dialogue_routes.py`. **Primeiro atribuí isso a cascata do teste vizinho
que falhava; estava errado** — o vizinho foi corrigido e o ERROR continuou.
Quem abre conexão depende da fixture, sem exceção.

**Achado operacional que vale para quem algum dia rodar `downgrade`.** Um
`alembic downgrade` abortado no meio pode deixar o banco **estampado no head e
fisicamente sem um índice**: o `CREATE/DROP INDEX CONCURRENTLY` de
`c82f4a9d117e` vive num `autocommit_block()`, então o `DROP` commita por fora e
o rollback da transação do Alembic não o desfaz. Reproduzido aqui na base de
teste; só o `alembic check` revelou. A migration se recupera sozinha quando é
reaplicada (o preflight dela cria o índice ausente e recusa artefato inválido),
mas a recuperação não é automática — precisa de alguém rodando `check`. Em
produção o risco é remoto, porque desde a Sprint 38 o downgrade destrutivo é
recusado, mas o `alembic check` depois de qualquer downgrade deixa de ser
opcional.

**Falta para fechar o aceite do pacote**, e não é trabalho de código: a
comparação de contagens antes/depois nas 39 tabelas históricas e a exclusão de
conta sintética, ambas contra a produção. `ops/study_rollout.py` faz a prova de
preservação, mas tem `HEAD` fixado em `c95f3d8ba042` e precisa ser re-ancorado
antes de servir para este release.

Provas em 26/10/2026: `tests/test_dialogue_retention.py` **5 passando** (texto
vencido sai e a evidência permanece; turno no prazo intacto; segunda passada
conta 0; escopo roda sem a flag; escopo inválido recusado antes do banco);
ciclo da migration reversível com `alembic check` limpo; ruff e mypy strict
limpos (103 arquivos); suíte completa **1228 passando, zero erro**; passo
pós-cutover **186**, com a lista de arquivos extraída do `ci.yml` pelo parser de
YAML em vez de transcrita — foi transcrição errada que produziu um falso verde
no SEC-45.

---

## Ciclo 47 — Assistente no browser e endurecimento das rotas novas

### FE-47 Experiência do parceiro de conversa

- [x] `features/dialogue/dialogueSession.ts`: máquina de estados fora do
  React (`idle → listening → uploading → waiting → partner_speaking →
  idle`), polling do job, fallback, limite de turnos.
- [x] Tela do diálogo dentro da etapa "Revisar" da jornada guiada: escolha
  do modo, personagem, fala do parceiro **sempre em texto** mais voz
  sintetizada (`speechSynthesis`, voz `en-US`, velocidade ajustável,
  botão de repetir), botão falar/parar reaproveitando `VoiceRecorder`,
  entrada por texto como alternativa.
- [x] Após o turno: transcrição com confiança por palavra (abaixo de 75%
  identificada também em texto), critérios determinísticos de vocabulário,
  gramática e tamanho, dicas rotuladas "automatizado, em avaliação",
  avaliação útil/não útil e exclusão do diálogo com confirmação.
- [x] Detalhar os termos-alvo usados/faltantes pelo nome e os padrões
  gramaticais identificados/ausentes, com vínculo ao recorte avaliado no
  turno. Legados sem detalhes são apresentados explicitamente, sem
  reconstrução a partir do vocabulário atual.
- [ ] Liberar a interface após a revisão assinada SEC-46. O código local
  está preparado, mas `DIALOGUE_PRACTICE_ENABLED` permanece `false`.
- [x] Cota e custo visíveis com `AssistQuota`; estados offline, cota
  esgotada e provedor indisponível com mensagens próprias e caminho para o
  Roteiro.
- [x] Acessibilidade: `aria-live` para a fala do parceiro, foco previsível
  entre turnos, legenda sempre visível, `prefers-reduced-motion`, operação
  completa por teclado, nenhuma dependência de cor.
- [x] CSP inalterada: `speechSynthesis` é API do navegador; nenhum domínio
  novo em `connect-src`.

Aceite: fluxo completo testado em Vitest com API simulada; teste Playwright
isolado com `speechSynthesis` substituído; sem microfone, o diálogo continua
por texto; o orçamento de bundle inicial não cresce (a feature é chunk lazy).

### Registro de execução — preparação local do FE-47 em 28/10/2026

O parceiro está integrado à etapa Revisar via `DialogueEntry`. A entrada
consulta `GET /api/speaking/dialogues/status` privado e só aparece se a
flag de prática estiver habilitada. O workspace é carregado por import
lazy após abrir a conversa. Nenhuma configuração de ambiente foi ativada
nesta entrega; a assinatura SEC-46 e o gate do fornecedor IA-48 continuam
pendentes. A preparação foi validada com respostas sintéticas.

`DialogueSession` concentra criação, envio, consulta e cancelamento fora
do React. Uma perda de resposta preserva a chave, a posição e os bytes do
pedido; outra entrada fica bloqueada até esclarecer o resultado. Após o
aceite confirmado, uma falha de GET repete apenas a consulta. A troca de
conta invalida respostas tardias, e o desmonte encerra requisições, polling,
microfone e reprodução. O polling para após 40 consultas e permite retomada
manual. Texto e gravação ficam em memória, sem fila offline ou persistência
local de dados privados.

O Roteiro trabalha por texto, sem transcritor. Guiado oferece áudio somente
com STT configurado e política de limites disponível: o consentimento começa
desmarcado em cada gravação, e tamanho, duração e MIME são verificados antes
do upload. A tela permite ouvir e baixar a gravação local. A resposta do
parceiro permanece em texto; a leitura opcional aceita somente voz local
`en-US` do navegador, com três velocidades, repetição e parada. Falta de
microfone ou de voz local mantém o fluxo por texto. A mudança para uma nova
conversa no Roteiro preserva a conversa anterior no banco.

**Ajustes de contrato necessários à interface:** status e cota exclusivos de
conversa; `words` no turno com a confiança real do STT; job com falha é
apresentado como turno falho, encerrando a espera da UI. O worker autoriza a
reserva antes de chamar o STT (antes a autorização vinha depois), e registra
a soma de STT + diálogo, mantendo custo parcial quando algum valor não é
confirmado. Áudio no Roteiro agora recebe 409 em vez de gerar avaliação de
texto vazio. Excluir a conversa também remove seus jobs e as cópias de texto
neles, liberando só reservas ainda não consumidas; áudio segue a retenção já
existente, explicitada na confirmação. Tipos e OpenAPI foram regenerados.

A invalidação usa o evento `dialogueChange` no mapa único de cache para
atualizar cota, revisão, Hoje e competências. O histórico continua com
posse no SQL; esta entrega não altera publicação ou dados reais de estudo.

**Bundle:** inicial **128,1/132 KiB gzip**, base sem diálogo **183,2/184 KiB**,
workspace lazy (JS + CSS) **6,7 KiB**. O teto antigo de 184 KiB não comportava
a nova feature: foi adicionada uma reserva explícita de **8 KiB somente
para `DialogueWorkspace`**, total máximo **192 KiB**. Os limites da entrada,
da base e por arquivo permanecem; a reserva não pode pagar crescimento de
outros módulos, e carregar o workspace na entrada reprova o check. Os 11
testes do script cobrem esses limites e passaram a rodar também no CI.

**Frontend:** 451 testes Vitest passando, incluindo 19 novos do motor,
componente e voz e um novo evento no mapa de invalidação. ESLint, tsc,
`check:api`, build e orçamento passaram. Playwright isolado passou em
1280px e 390px: envio por teclado, polling, fallback, foco após resposta,
voz substituída, avaliação e confirmação de exclusão; axe sem violações e
sem overflow horizontal, também com movimento reduzido. O harness bloqueia
API real e não usa banco ou fornecedor; isso não substitui o gateway
simulado e o fluxo com worker do INFRA-47. Imagens locais de revisão em
`e2e/test-results/dialogue-1280.png` e `dialogue-390.png`. O job isolado
completo do CI (fila, recuperação e diálogo) passou com seis testes.

**Backend:** suíte completa com **1.335 testes passando**, cobertura de
**93,90%**; ruff e mypy strict limpos. Os quatro testes novos de contrato
cobrem status/cota, rejeição de áudio no Roteiro, confiança/custo/exclusão
e autorização da reserva antes de qualquer STT. O job pós-cutover foi
extraído do YAML do CI e passou com **234 testes**, incluindo esse arquivo.

### Complemento FE-47 — critérios históricos, concluído em 29/10/2026

`dialogue_turn.check_details` guarda os termos e padrões do recorte usado
na avaliação, com a cobertura de cada um. A mesma regra determinística de
palavras e expressões inteiras usada nos booleanos produz os detalhes;
nenhum texto livre do aluno ou do provedor entra nesse campo. Roteiro e
Guiado persistem os dados junto ao resultado, e reentregas preservam o
resultado original mesmo se o recorte editorial tiver mudado.

A API privada e a exportação pessoal incluem o campo. A tela mostra os
nomes dos termos usados/não identificados e dos padrões identificados/não
identificados; ausência de detalhes legados tem mensagem própria. Os dados
editoriais e seus indicadores de cobertura permanecem junto aos checks
após a retenção apagar transcrição, resposta e dicas. A revisão recorrente
também usa os recortes persistidos, ignorando faltas antigas sem recorte;
assim uma edição de vocabulário não cria retroativamente uma segunda falta.

Migration `c92f4a8d710e`: coluna JSONB opcional, sem backfill; atualização
permitida ao worker, sem ampliar as escritas do runtime. O downgrade recusa
apagar a coluna enquanto houver detalhes históricos. Teste em schema
sintético cobre legado nulo, bloqueio do downgrade e reaplicação sem perda
do texto anterior.

**Validação local:** 53 testes direcionados do backend, seguidos pela suíte
completa com **1.344 testes passando e 93,91% de cobertura**; **454 testes**
do frontend passaram. Os nove testes novos de backend cobrem cobertura de
expressões, replay, mudança editorial, ausência de recorte legado e
migração; exportação e retenção ganharam verificações do campo. Os três
testes novos de apresentação cobrem nomes, legado e critérios não exigidos.
ESLint, TypeScript, contrato OpenAPI, ruff e mypy strict ficaram limpos.
O Playwright isolado passou nos seis cenários, incluindo nomes dos termos
em 1280px e 390px, axe sem violações e sem overflow horizontal. Bundle:
inicial **128,1/132 KiB**, base **183,2/184 KiB**, diálogo lazy **6,9/8 KiB**,
conjunto **190,1/192 KiB**. Os 181 testes operacionais passaram.

`make test-roles` passou com runtime e worker reais; o worker persistiu e
releu os detalhes, e a tentativa de atualizá-los pelo runtime foi recusada.
`alembic check` não encontrou diferenças entre modelos e banco. O laboratório
de papéis foi encerrado, preservando seu volume sintético. O contrato novo
também foi incluído no passo pós-cutover do CI; a execução local desse
passo, extraído diretamente do YAML, passou com **243 testes** e
`LEGACY_WRITES_UNTIL=2000-01-01T00:00:00Z`.

Na validação deste complemento, o INFRA-47 ainda estava pendente: a stack
E2E não possuía gateway nem worker. O ensaio de navegador usava API simulada;
o ensaio de permissões usava
PostgreSQL e papéis reais com provedor substituído. Nenhum deles representa
o fluxo integrado com gateway, implementado posteriormente na seção INFRA-47
abaixo. A flag de prática fora do laboratório segue desligada; revisão
assinada SEC-46 e gate IA-48 não foram liberados.

### BE-47 Evidência, revisão e painel

- [x] Cada turno do aluno gera `skill_evidence` de speaking com origem
  `dialogue_turn`; termos-alvo faltantes em dois turnos do mesmo diálogo
  entram na revisão SM-2 como `dialogue_missed_term`, idempotente.
- [x] O painel Hoje sugere "praticar a conversa da Aula N" quando a aula foi
  estudada e não tem diálogo nos últimos 7 dias; a sugestão explica o motivo.
- [x] Exportação pessoal (schema atual 2.1) inclui diálogos, turnos, avaliações humanas,
  custo e fornecedor.

Aceite: um diálogo sintético de 6 turnos produz exatamente 6 evidências e
no máximo os itens de revisão esperados; repetir o processamento não
duplica nada.

### Registro de execução — Ciclo 47, BE-47 em 28/10/2026

Implementação local na branch `sprint/46-assistente-backend`. Não houve deploy,
ativação de assistência nem assinatura em nome do responsável. O FE-47 mantém
as dependências de SEC-46 e IA-48 registradas acima.

- `services/dialogue_learning.py` registra uma evidência de fala por turno
  concluído, com origem `dialogue_turn` e unicidade no banco. O valor interno é
  a proporção de checks determinísticos satisfeitos; não usa confiança,
  avaliação humana ou texto do provedor como nota. A origem exibida no painel
  esclarece que esses checks não avaliam fluência ou pronúncia.
- Um termo solicitado e ausente em dois turnos da mesma conversa cria uma
  carta `speaking_prompt`, com motivo `dialogue_missed_term`. A carta usa o
  vocabulário editorial, sem copiar a transcrição. Há uma carta por termo e
  diálogo; reentregas preservam prazo SM-2, suspensão e revisões feitas.
- O resumo de competências inclui a nova origem respeitando curso, unidade e
  publicação. A exclusão autenticada do diálogo remove suas evidências e
  cartas na mesma transação, sem apagar outras origens.
- O painel prioriza revisão vencida, retomada e checkpoint antes da conversa.
  A sugestão exige aula estudada e ausência de diálogo iniciado nos últimos
  sete dias. Está atrás de `DIALOGUE_PRACTICE_ENABLED=false`: só deve ser
  habilitada junto do FE-47, após a revisão assinada, para não oferecer um
  destino ainda incompleto. A variável está declarada nas Compose de dev e
  produção local; no EasyPanel usa `EASYPANEL_DIALOGUE_PRACTICE_ENABLED`,
  também falsa por padrão. O contrato OpenAPI e os tipos foram regerados;
  a única alteração pública é o novo tipo de recomendação `conversation`.
- A exportação 2.1 já cobria diálogos e turnos desde DB-45. O teste agora
  verifica também fornecedor, custo e avaliação humana, além do isolamento
  entre contas; não houve mudança desnecessária de versão.

**Correções encontradas na integração com os papéis reais.** O Roteiro antes
inseria o turno pendente e tentava atualizá-lo, embora o runtime só possa
alterar `human_rating`. Agora insere o resultado completo. O Guiado insere o
turno já associado ao job, eliminando outro UPDATE proibido. O worker carrega
apenas o recorte editorial necessário, sem buscar gabaritos; a migration
`a18d7e4c2b91` concede essa leitura e INSERT nas tabelas derivadas, com SELECT
restrito às colunas de identificação. Não concede UPDATE/DELETE de evidências,
leitura de senhas, gabaritos ou textos das cartas.

**Retomada e concorrência.** A resolução serializa por diálogo; um turno já
concluído não chama o provedor outra vez. Resultado, evidência, revisão, custo
e confirmação do job são gravados na mesma transação. O teste injeta falha
antes de persistir o custo e prova que a retomada conclui sem resultado parcial.
Dois turnos concorrentes geram duas evidências e uma única carta recorrente.

**Validação:** o cenário sintético de seis turnos gera seis evidências e duas
cartas, preservadas no replay; testes cobrem limite de sete dias, isolamento,
publicação, exclusão, fallback, concorrência e falha transacional. O ensaio
`make test-roles` passou com criação de 12 turnos no Roteiro pelo runtime e
resolução de 12 turnos Guiados pelo worker, sem provedor externo. Vitest:
431 testes; testes operacionais: 180; eslint, TypeScript, contrato, ruff e
mypy strict (104 arquivos) limpos. Build e orçamento: 128,1/132 KiB iniciais e
182,6/184 KiB totais. Suíte completa do backend: **1.297 testes passaram**.
Passo pós-cutover extraído diretamente do `ci.yml`: **196 passaram**, com
`LEGACY_WRITES_UNTIL=2000-01-01T00:00:00Z` e o novo arquivo incluído no CI.
A migration foi revertida e reaplicada no laboratório com dados sintéticos:
contagens de turnos, evidências e revisões preservadas, privilégios conferidos
nas duas direções e `alembic check` limpo. O laboratório de papéis foi encerrado
após o ensaio, mantendo o volume sintético.

**Ajuste da suíte:** duas expectativas do head Alembic foram atualizadas para
a nova migration. O teste de job expirado usava o instante atual do host,
enquanto a retenção compara com o relógio do PostgreSQL; falhou na suíte e
passou isolado. Agora cria um prazo anterior aos dois relógios, mantendo a
mesma exigência de retenção, sem espera artificial.

### DB-47 Laboratório 1k/10k de turnos

- [x] Carga sintética de 1k e 10k turnos por aluno no laboratório; medição
  das consultas de histórico e do Caderno com o índice keyset; ajuste de
  índice se o p95 passar de 100 ms.

### SEC-47 Revisão das rotas novas

- [x] Testes de IDOR em cada rota de diálogo; replay de turno com a mesma
  posição; tentativa de furar a cota em paralelo (reaproveitar o padrão de
  `test_assist_quota`).
- [x] Limites de áudio na API e nginx para o turno; consentimento explícito;
  `limit_req` em `/api/speaking/dialogues` sem limitar GET de polling.
- [x] Validar os limites e o consentimento na UI preparada do diálogo
  (FE-47), consumindo `/api/speaking/policy` e enviando
  `X-Audio-Consent: true` somente após a confirmação do aluno.
  Prova local com transporte simulado; ativação depende da revisão SEC-46.

### Registro de execução — DB-47 e segurança da API em 28/10/2026

**Histórico:** `GET /api/speaking/dialogues` retorna metadados privados, sem
transcrições, com `limit` de 1 a 100 (padrão 20) e cursor opaco ordenado por
`started_at DESC, id DESC`. A contagem dos turnos usa uma subconsulta
correlacionada; não há uma consulta adicional por conversa. A listagem
preserva o acesso ao histórico próprio independentemente da publicação
atual da aula. Posse, datas empatadas, cursor inválido e ausência de cache
estão cobertos nos testes. OpenAPI e tipos do frontend foram regenerados.

**Desempenho:** ensaio no PostgreSQL 16.15 descartável, com 1.000 e 10.000
turnos por conta, distribuídos em 84 e 834 diálogos, além de 1.000 e 10.000
notas sintéticas no Caderno. Foram 30 amostras por rota depois de duas de
aquecimento, página de 50 itens e cursor profundo após 90% dos registros.
Medição HTTP local via ASGI, incluindo autenticação e serialização; não
representa latência da rede ou capacidade da produção.

| Carga | Histórico inicial p95 | Histórico profundo p95 | Caderno inicial p95 | Caderno profundo p95 |
| --- | --- | --- | --- | --- |
| 1.000 turnos | 7,27 ms | 4,17 ms | 5,38 ms | 7,14 ms |
| 10.000 turnos | 5,36 ms | 12,79 ms | 12,24 ms | 20,31 ms |

Todas as páginas fizeram duas consultas SQL (autenticação + listagem) e
no máximo uma aquisição de conexão. O percurso completo conferiu a ordem
e a ausência de perdas/duplicatas, inclusive nas datas empatadas. No caso
10k, `EXPLAIN ANALYZE` usou `ix_dialogue_user_started` e
`uq_dialogue_turn_position` no histórico (0,386 ms), e
`ix_notebook_entry_user_updated_id` no Caderno (0,645 ms). Na carga menor,
o otimizador preferiu varredura sequencial dos 84 diálogos (0,108 ms).
Não foi necessário adicionar índice ou migration.

Reprodução: `make dialogue-benchmark`; aceita `DIALOGUE_BENCHMARK_ARGS`
com `--samples` e `--output`. A guarda recusa banco/papel não descartáveis,
o ensaio usa advisory lock e remove somente suas contas sintéticas no
`finally`. Não executar simultaneamente com pytest, cujo teardown limpa
as contas de teste. As duas contas do ensaio foram removidas. Relatório
agregado: [db47_dialogue_performance_2026-10-28.json](db47_dialogue_performance_2026-10-28.json).

**Segurança:** o upload agora exige o header `X-Audio-Consent: true` e
registra a data do consentimento e SHA-256 dos bytes inspecionados.
Reenvio do mesmo áudio mantém um único arquivo, tentativa, job e reserva;
outros bytes na mesma posição recebem 409. A rejeição por cota desfaz a
tentativa SQL e remove o arquivo somente depois de confirmar que ele não
está referenciado no banco. A compensação é compartilhada com shadowing,
preservando o arquivo quando o resultado do commit é desconhecido.

A criação é serializada por conta para quatro pedidos simultâneos com
a mesma `operation_key` devolverem o mesmo diálogo. A reserva de turno
inclui o identificador do diálogo no fingerprint: reutilizar a chave em
outra conversa recebe 409, em vez de tentar reutilizar o job. Dezesseis
admissões simultâneas em duas conversas respeitaram exatamente a cota de
12, com quatro respostas 429. Posições fora dos limites são rejeitadas
antes das constraints SQL.

O nginx aplica 120 escritas/minuto, rajada de 24, com resposta 429 em
`/api/speaking/dialogues` e suas subrotas. Atrás do Traefik é um teto global
de borda, sem confiar em cabeçalhos de IP fornecidos pelo cliente; a cota
por aluno continua transacional no banco. GET não consome essa zona.
API e proxy compartilham o teto de 2.000.000 bytes decimais; a API também
inspeciona o limite real de 30 segundos. `nginx -t` passou na imagem
1.30.6-alpine3.24, em container descartável sem rede.

**Validação local:** backend completo com **1.331 testes passando** e
**93,50% de cobertura** (piso de 90%); **431 testes do frontend** e
**181 testes operacionais** passando. Ruff do backend e de `ops` com a
configuração do CI, mypy strict (106 arquivos), ESLint, TypeScript e
conferência do schema gerado passaram. Os 34 casos novos de segurança
estão em `backend/tests/test_dialogue_security.py` e também integram o
job de compatibilidade pós-cutover. Esse job foi extraído do `ci.yml` com
parser YAML e executado localmente com `LEGACY_WRITES_UNTIL` no passado:
**230 testes passando**.

O teste de limites e consentimento da UI foi concluído na preparação local
do FE-47, registrada acima. A revisão assinada do SEC-46 continua pendente.
Não houve deploy ou ativação do provedor.

### INFRA-47 Gateway simulado no E2E

- [x] Container de gateway simulado (STT + diálogo) em `infra/compose.e2e.yml`,
  determinístico, com cenários de sucesso, lentidão, falha e resposta
  inválida; worker real e fluxo completo do diálogo em desktop e mobile
  incluídos no job E2E do CI.
- [x] Execução remota verde confirmada nos releases das PRs #39 e #40,
  incluindo o E2E com gateway simulado. Os registros de preparação abaixo
  preservam o estado que existia em cada execução local.

Aceite: E2E do diálogo verde no CI; o gateway simulado nunca é alcançável
fora da rede da stack E2E.

### Registro de execução — INFRA-47 em 29/10/2026

`infra/e2e-gateway` contém um servidor Python sem dependências adicionais,
com respostas fixas de STT e diálogo. Cada modalidade pode responder com
sucesso, atraso de três segundos, HTTP 503 ou JSON incompatível. O controle
dos cenários ocorre por `docker compose exec`; não há porta do gateway
publicada no host nem proxy no frontend. O container roda sem root, sem
mounts, com filesystem somente leitura e apenas na rede `gateway`, marcada
como interna. API e worker acessam essa rede além da rede do banco; o web
não participa dela. As métricas de teste guardam somente chave idempotente,
quantidade de bytes e tipo de conteúdo, sem áudio ou texto enviado.

As guardas de E2E passaram a verificar worker, gateway, rede interna e URLs
exatas `http://gateway:8080/stt` e `/dialogue`, recusando URLs externas,
tokens e provedores alternativos. As flags de assistência e conversa são
habilitadas **somente na stack descartável**; configurações de dev/produção
e os gates SEC-46/IA-48 não foram liberados por esta entrega. O STT do
diálogo fica disponível; shadowing continua sujeito à flag de snapshots
editoriais, ainda desligada nessa stack. Escrita assistida continua desativada.

`sprint47-dialogue.spec.ts` acrescenta sete cenários em cada projeto Chromium
desktop/mobile: fluxo completo, lentidão separada em STT e diálogo, falha
e resposta inválida de cada modalidade. Usa a entrada sintética de áudio
do Chromium e o `MediaRecorder` nativo, observando seu evento de início;
nenhuma resposta HTTP da aplicação é substituída. O service worker fica
bloqueado nesse arquivo, pois PWA tem suíte própria. O fluxo verifica
consentimento, upload validado, job real, polling, confiança por palavra,
critérios históricos, custo sintético de 7 + 3 + 7 = 17 microunidades de USD,
avaliação humana, exportação e exclusão. Reenviar a mesma posição mantém o
job e não aumenta chamadas ao gateway ou consumo. Falha de diálogo usa o
roteiro; falha de STT encerra a espera e permite o próximo turno por texto.

**Correções encontradas pelo fluxo integrado:** após áudio, o foco agora
aguarda o textarea ser reabilitado pela remoção da gravação local. A
exportação pessoal deixou de pressupor cue em toda gravação: áudios de
diálogo usam a aula associada ao turno; se a conversa já foi excluída, o
áudio continua exportável com referências editoriais nulas até a retenção.
O campo `origin` identifica a procedência da gravação. Testes do componente
e de contrato cobrem as duas regressões, incluindo exportação após excluir
a conversa.

**Validações auxiliares:** 64 testes das guardas, 181 testes operacionais,
454 testes frontend e 12 testes backend de contrato/exportação passaram.
ESLint, TypeScript (inclusive os novos arquivos E2E), contrato OpenAPI,
ruff e mypy strict limpos. Build dentro dos limites: inicial 128,1/132 KiB,
base 183,2/184 KiB, conversa lazy 6,9/8 KiB, conjunto 190,1/192 KiB.

**E2E integrado local:** os 14 novos casos de conversa passaram (sete em
desktop e sete em mobile), com revisão das capturas nas duas dimensões.
A execução completa terminou em 9,7 minutos com 154 casos aprovados,
dois ignorados pela configuração e duas falhas no teste legado de
consentimento: a expectativa havia sido alterada para STT habilitado,
embora shadowing ainda dependa dos snapshots editoriais. Restaurada a
expectativa original, ambos passaram em reexecução isolada (3,8 segundos).
Assim, os 156 casos executáveis foram verificados entre a execução completa
e essa reexecução; não se trata de uma única execução integral verde.
Os casos de navegação/acessibilidade em Firefox e WebKit também passaram;
o baseline duplicado desses projetos permanece ignorado pela configuração.
A stack descartável foi encerrada com `make e2e-down`, preservando volumes.

O job existente do CI já inclui os cenários pelo diretório `e2e/testes` e
agora coleta também logs de worker/gateway quando falha. Reprodução:
`make e2e-up`; `cd e2e && npm test -- testes/sprint47-dialogue.spec.ts`;
`make e2e-down` na raiz. Para a regressão completa, `make test-e2e`.

---

## Ciclo 48 — Piloto controlado e gate humano

### Registro de preparação — gate de conversa em 29/10/2026

O CLI aceita `--modality conversation` e usa `dialogue_assist_configured`,
sem herdar a configuração da escrita. O manifesto exemplo identifica a
modalidade explicitamente, mas continua com aprovações falsas e dados
desconhecidos como `null`. Conversa exige `modality=conversation`; manifestos
antigos sem esse campo continuam válidos apenas para escrita/transcrição.
Uma modalidade declarada diferente da solicitada bloqueia qualquer gate.

A coleta usa somente agregados SQL dos turnos do aluno no modo Guiado e do
provedor identificado no manifesto. Roteiro, Livre, turnos de parceiro e
outros provedores ficam fora. Turno concluído com fallback ou erro conta
como falha técnica, assim como estado `failed`; pendentes não entram no
denominador dos resultados terminais. As 30 avaliações e as cinco aulas
distintas são contadas apenas sobre respostas concluídas sem fallback/erro.
O limiar de utilidade é >= 80% e o de falha técnica é < 5%, comparados sem
arredondamento; as taxas arredondadas são apenas para exibição.

O custo do turno já reúne STT e diálogo, portanto não é somado novamente ao
do job. Qualquer turno terminal sem confirmação de custo na reserva bloqueia
o gate (`cost_known`), inclusive quando o job/reserva já não existe. Corrigido
o worker para registrar também custo **zero confirmado** em turnos por texto.
O gate antigo de transcrição agora filtra `kind=transcription`, para não
misturar os jobs de conversa com as avaliações de STT.

O relatório não contém texto, áudio, e-mail ou identidade do aluno. A amostra
corresponde aos registros ainda existentes no banco, sem recorte por conta
ou período; não substitui o painel de faturamento nem recupera conversas
excluídas. O piloto continua restrito operacionalmente à conta autorizada.
Nenhuma flag é alterada, nenhuma chamada ao provedor é feita pelo gate e
nenhuma aprovação humana foi presumida. Revisão assinada SEC-46, manifesto
real preenchido, piloto e decisão IA-48 permanecem pendentes.

Reprodução: preencher o manifesto local ignorado e executar
`make assist-gate modality=conversation review=../config/assist-provider-review.json`.
O comando retorna 0 para aprovação, 1 para critérios não atendidos e 2 para
manifesto/argumento inválido; os testes usam apenas o banco descartável.

Validação local: **126 testes direcionados passaram**, em duas execuções de
63 casos: gate/CLI/contrato/retenção (4,66 s) e assistência/serviço/rotas/
aprendizagem/cota (12,73 s). Incluem coleta real no PostgreSQL descartável,
recusa de manifesto incompatível, custo desconhecido, limites exatos de
80% e 5%, cinco aulas, exclusão de Roteiro/Livre/outros provedores, ausência
de conteúdo pessoal no relatório e custo zero confirmado pelo worker.
Ruff e formatação limpos; mypy strict passou nos 106 arquivos de `app`.
Não houve execução remota do CI, deploy ou homologação com provedor real.

### IA-48 Piloto em conta única e decisão

- [x] Suporte local de `conversation` no gate, coleta agregada, manifesto por
  modalidade e critérios de cinco aulas/custo confirmado, sem ativar produção.
- [ ] Ativação do modo Guiado **só na conta de Jeferson**, em produção, com
  cota reduzida e orçamento definido no manifesto.
- [ ] No mínimo 30 turnos avaliados por pessoa ao longo de pelo menos cinco
  aulas diferentes; `make assist-gate modality=conversation`
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

- [x] Job de manutenção apaga `transcript` e `partner_text` após
  `ASSIST_RETENTION_DAYS`, preservando checks agregados e avaliações; teste
  com relógio injetado.

### SEC-48 Revisão de logs e incidente de provedor

- [x] Runbook de contenção, evidências, comunicação e rotação, com ensaio
  HTTP local em texto/áudio e inspeção dos logs capturados da API/worker.
- [ ] Amostragem dos logs da API e do worker em produção: zero ocorrências
  de texto de turno; runbook de incidente para vazamento ou indisponibilidade
  do provedor (revogar token, desligar flag, comunicar); procedimento de
  rotação do token do provedor ensaiado uma vez.

### Registro de preparação — incidentes SEC-48 em 29/10/2026

`docs/modelo_ameacas_assistente_2026-10-26.md` ganhou procedimento operacional
para revogação, pausa da assistência, preservação de fila/histórico, coleta
restrita de evidências, comunicação e retomada após decisão humana. Registra
que `ASSIST_PROVIDER_TOKEN` é compartilhado pelas três modalidades e que
configuração é cacheada por processo: alterar o painel sem recriar API e
worker não aplica a pausa ou a chave nova. Também diferencia requisição já
transmitida de job ainda não despachado e orienta não reabrir turnos terminais.

`tests/test_provider_incident.py` usa gateway HTTP em loopback, banco
descartável, tokens e áudio sintéticos. Nos caminhos texto/áudio, executa
sucesso, revogação com 401, pausa sem reivindicar o job pendente, Roteiro sem
rede, rotação e retomada uma vez, além de indisponibilidade 503 com chave
válida. O worker usa seu transporte HTTP real; somente o provedor é simulado.
Os logs formatados da API e do worker são conferidos contra marcadores de
token, texto do aluno/parceiro, autorização e corpo sensível de erro.

O comando existente `make test-failure-rehearsal` inclui esses dois caminhos:
**7 testes passaram em 5,03 s**, incluindo os ensaios anteriores de falha de
banco, fallback, backoff e retomada de worker. Os sete testes existentes de
logging também passaram durante a validação inicial. Nenhum código de
produção precisou ser alterado nesta preparação. A fixture inicial de STT
foi corrigida para incluir metadados por palavra exigidos pelo contrato.

Isso prova o comportamento local com configuração simulada no processo do
teste. Não prova recriação de containers no EasyPanel, revogação de token
real, ausência de conteúdo em logs de produção ou entrega de comunicação.
Esses recibos, a revisão assinada SEC-46 e a liberação IA-48 seguem pendentes;
nenhuma credencial real ou flag de produção foi alterada e nenhum aviso foi
enviado. O bloqueio histórico do gate no modelo de ameaças foi atualizado
para refletir a implementação local de `conversation`, sem presumir revisão.

### INFRA-48 Custo e backup com as tabelas novas

- [x] Preparação local: agregados de custo diário/mensal no endpoint privado
  e no relatório operacional; alerta em 80% do orçamento explicitamente definido.
- [ ] Painel de custo diário/mensal do assistente a partir das métricas
  agregadas; alerta em 80% do orçamento. Código local pronto; falta configurar
  os dois orçamentos aprovados no cron/variables e comprovar o alerta no ambiente real.
- [ ] Backup público restaurado em laboratório com as tabelas novas e lido
  pela aplicação; recibo registrado.
- [x] Ensaio sintético separado das tabelas de conversa: backup/restore real,
  leitura pela aplicação e recibo local, sem acessar a produção.

### Registro de preparação — recuperação INFRA-48 em 29/10/2026

O laboratório `aulas-ingles-recovery48` usa quatro volumes próprios, rede
interna, nenhuma porta publicada e papéis PostgreSQL limitados com os
marcadores existentes. Não reutiliza nem remove volumes dos ensaios antigos.
`ops/dialogue_recovery.py` admite somente esse projeto e recusa origem ou
destino já preenchidos. O destino foi registrado separadamente dos destinos
legados para preservar suas regras de isolamento.

A fixture acrescenta à base sintética uma conversa concluída, dois turnos
(texto e áudio), critérios históricos, avaliações útil/não útil, duas reservas
consumidas com custo confirmado e seus jobs. O custo sintético é 17 microusd.
Há dois arquivos WAV de silêncio: um do exercício oral e um da conversa.
Nenhum modelo ou provedor externo participa.

O ensaio executou `pg_dump`, pacote com banco/voz, restauração transacional
em destino vazio e conferência dos arquivos. Além do snapshot comum, comparou
contagem e digest de todas as colunas de `speaking_dialogue`, `dialogue_turn`,
`assist_reservation` e `transcription_job`. A aplicação corrente leu histórico
e exportação pessoal, verificando critérios, avaliações, texto, custo e bytes
dos áudios com filesystem/voz somente leitura e transações de leitura.
Os digests da origem e do destino permaneceram iguais após a leitura.

Recibo privado de restauração:
`backups/recovery/restore-receipts/aulas-20261029T041512200702Z-b7901f1433ee49f0b973eede4e734d4e.json`.
Prova complementar da leitura da conversa no mesmo diretório:
`aulas-20261029T041512200702Z-b7901f1433ee49f0b973eede4e734d4e-conversation.json`.
Uma segunda tentativa de restore foi recusada por destino não vazio; os
digests foram conferidos novamente sem alteração. Os containers novos foram
encerrados, preservando volumes, pacote e recibos.

Reprodução em laboratório ainda vazio, na raiz do projeto:

```sh
uv run --project backend python -m ops.dialogue_recovery up
uv run --project backend python -m ops.dialogue_recovery prepare
uv run --project backend python -m ops.dialogue_recovery check
uv run --project backend python -m ops.dialogue_recovery down
```

O comando `down` não apaga volumes; repetir `prepare` ou `check` sobre dados
existentes recusa sobrescrita. Em falha, preservar os parciais para diagnóstico.
O job `recovery` do CI passou a executar esse fluxo, com encerramento em
`always()`, sem publicar dumps, áudios ou manifestos como artifacts.

Validação: **193 testes operacionais passaram**; Ruff limpo em `ops` com a
configuração do backend; Actionlint 1.7.7 aprovou o workflow. As guardas de
identidade, papel, mounts e portas foram exercitadas também nos dois bancos
novos. O restore sintético e a leitura da aplicação passaram localmente.
O CI remoto não foi executado nesta entrega. O item de backup **público**
permanece pendente: este recibo é sintético e não atesta uma cópia da produção.

### Registro de preparação — custos operacionais INFRA-48 em 29/10/2026

`/api/operations/metrics` ganhou `assist_costs.daily` e `monthly`: janelas
UTC de calendário, contagem de reservas consumidas, custo acumulado e custos
desconhecidos. A fonte é `assist_reservation`, não turnos descartáveis. As
três modalidades entram uma vez por reserva; apagar conversa/job não apaga
o custo. Reservas liberadas ou apenas reservadas ficam fora. O recorte usa
`dispatched_at`, com `created_at` como fallback legado, até o instante da
amostra. Não depende do fuso da conexão nem soma custo do job ao do turno.

O monitor lê `OPERATIONS_ASSIST_DAILY_BUDGET_MICROUSD` e
`OPERATIONS_ASSIST_MONTHLY_BUDGET_MICROUSD`. Sem orçamento, avisa; em 80%,
avisa; em 100%, marca crítico. Custo desconhecido ou métricas ausentes não
passam como zero confirmado. O cron e o workflow recebem saída 1 para os
dois níveis de alerta. O workflow agora publica o resumo antes de propagar
essa saída, para não perder o relatório ao falhar. As variáveis não foram
configuradas remotamente e nenhum alerta foi enviado durante os testes.

OpenAPI e tipos frontend atualizados. Validação local: **29 testes backend**
(operação, cota e gate de conversa) e **186 testes operacionais** passaram.
As provas cobrem dia/mês UTC sob conexão `Pacific/Kiritimati`, ano bissexto,
virada de ano, instante de despacho, valores futuros, custo parcial/zero,
limiares exatos 80%/100%, configuração inválida antes da rede e saída do CLI.
Mypy strict passou em 106 arquivos; Ruff passou nos arquivos alterados com
a configuração do backend; contrato TypeScript sincronizado e compilação
TypeScript limpa. Actionlint 1.7.7 aprovou o workflow operacional.

Limite explícito: exclusão de conta remove o ledger daquela conta. O relatório
é uma visão do ledger ainda existente, não substitui a fatura do provedor.
Nenhuma flag de assistência foi habilitada. Configuração e comprovação em
produção, revisão humana e restauração do backup continuam pendentes.
Operação documentada em `docs/deploy_easypanel.md`, na vigilância agendada.

---

## Ciclo 49 — Enxugar e consolidar

Pode começar após o ciclo 45 sempre que houver folga.

### INFRA-49 Poda de topologia, scripts e documentação

- [x] Remover os perfis `final39-check`, `assist-check` e `dev-check` de
  `infra/compose.recovery.yml`; remover `ops/sprint39_rollout.py` e seu
  teste; unificar `study_rollout`/`concurrency_rollout` em `ops/rollout.py`
  parametrizado; tirar `ops.rollback_image` do caminho do CI, mantendo-o
  como ferramenta sob demanda.
- [x] Decidir o destino de `infra/compose.prod.yml` e do overlay
  `compose.roles.prod.yml` agora que `make prod-up` está desativado e a
  produção vive no EasyPanel.
- [x] README: changelog de sprints sai para `docs/changelog.md`; o README
  volta a ter menos de 400 linhas e aponta para os runbooks.
- [x] `docs/operacao_sprint_37.md` dividido em runbook vigente e histórico.
- [x] Apagar as 15 branches locais já mergeadas; derrubar os containers de
  laboratório parados há dias (`recovery-study-check`, `upgrade42`).

Aceite: `docker ps` do projeto mostra só dev, estudo local e teste; o CI
continua verde após a poda; `make help` lista menos de 50 alvos.

**Execução em 29/10/2026 — implementação e validação local concluídas;
publicação/CI remoto pendentes.**

`ops.rollout` reúne os perfis históricos `study`/`concurrency` com seleção
explícita, mantendo revisões, destinos, hashes, política de legado e nomes dos
recibos. Os consumidores e testes foram migrados. `ops.sprint39_rollout` e seus
oito testes específicos foram retirados; o histórico Git preserva esse código.
Os testes compartilhados continuam verificando o smoke de assistência ativo.

O Compose principal de recuperação perdeu os três perfis indicados. Os dois
alinhamentos históricos ainda referenciados (`dev-check`/`assist-check`) ficam
no overlay opt-in `infra/compose.legacy-rehearsal.yml`, fora da stack padrão e
do CI. O perfil `final39-check`, seus destinos e declarações de volumes saíram.
Nenhum volume existente foi apagado.

O CI faz checkout do SHA completo do release anterior e build explícito para
a prova de upgrade/leitura. `upgrade-lab-up` exige a imagem já preparada;
`ops.rollback_image` permanece sob demanda. O smoke de compatibilidade segue
no CI: não foi substituído por uma simples verificação de configuração.

Decisão sobre os arquivos `compose.prod.yml`/`compose.roles.prod.yml`:
**mantidos para o estudo local 5181**, com identificação corrigida. Projeto,
nomes de volumes e credenciais permanecem compatíveis. A produção pública usa
`infra/easypanel/compose.yml`; os fluxos genéricos `prod-up`/`prod-seed` continuam
bloqueados. `make help` mostra **43 comandos**; `help-all` preserva o acesso aos
atalhos avançados e de laboratório.

README reduzido de **1.652 para 112 linhas**. As entregas datadas foram para
[changelog](changelog.md), a referência de produto/testes para
[guia técnico](guia_tecnico.md), e a operação foi dividida em
[runbook vigente](operacao_local.md) e
[histórico 37–44](historico_operacao_sprints_37_44.md). O arquivo antigo aponta
para os novos destinos; links internos e âncoras foram atualizados.

As **15 branches locais** ancestrais de `main` e fora de worktrees foram
retiradas com `git branch -d`, preservando `main`, a branch de trabalho e as
branches remotas. O inventário Docker confirmou apenas desenvolvimento e
estudo local ativos neste projeto: os laboratórios antigos já estavam
encerrados. Containers de outros projetos não foram alterados.

Validação local: **336 testes operacionais** aprovados (341 anteriores, menos
oito exclusivos do script retirado, mais três testes dos perfis), Ruff limpo,
mypy estrito dos **37 módulos**, Compose principal/overlay válidos e actionlint
do workflow alterado aprovado. O ensaio integrado de upgrade será comprovado
pelo CI remoto; não foi reexecutado sobre volumes de ensaios anteriores.
Continuação **SEC-49** registrada abaixo. FE/DB/INFRA/SEC-49 ainda aguardam
publicação e CI remoto para fechamento comum.

### BE-49 Qualidade da suíte e de `ops/`

- [x] Marcador `timezone` nos testes que tocam data; o passo
  `TZ=Pacific/Kiritimati` roda só esse subconjunto.
- [x] `test_concurrency.py`: trocar igualdade exata de ticks e latência de
  parede por asserções de invariante.
- [x] `ops/` sob `mypy --strict`, incluindo novos scripts automaticamente.
- [x] Testes para `recovery_archive.py`.
- [x] Testes para os cinco módulos de smoke restantes; resultados no registro
  de fechamento dos smokes abaixo.
- [x] Separar `/api/health` público (sem versão do Postgres e revisões) do
  readiness interno.

#### Registro de execução — saúde pública e readiness BE-49 em 29/10/2026

Implementação local: `/api/health` conserva a verificação de conexão e igualdade
das revisões, retornando apenas `status`, `db`, `schema` e `code`. Banco fora do
ar ou schema incompatível continuam em 503. `/api/operations/readiness` fornece
versão do Postgres, ambiente e revisões somente com `OPERATIONS_TOKEN`; retorna
404 sem configuração ou 401 para credencial ausente/incorreta, sem consultar o
banco nesses casos. As respostas da API continuam privadas e sem cache.

Gate operacional atualizado para a rota autenticada; smoke de deploy exige
`status=ok`, `db=up` e `schema=compatible`; probe externo reprova os quatro
campos internos no health público sem copiar seus valores ao relatório. A
guarda E2E valida o contrato público e conserva a comprovação de ambiente de
teste por containers, rede, volumes e marcador/papel do banco. OpenAPI e tipos
TypeScript regenerados juntos. Runbook em `docs/deploy_easypanel.md` atualizado.

Validação local: 17 testes de health/operações, 194 testes de `ops/` e 65 testes
da guarda E2E aprovados; Ruff, mypy do backend, contrato OpenAPI/TypeScript,
compilação TypeScript e ShellCheck 0.11.0 do deploy limpos. `make e2e-up`
reconstruiu as imagens e aprovou a guarda com todos os serviços saudáveis;
HTTP real pelo nginx em `127.0.0.1:5198` confirmou health 200 com apenas quatro
campos e `private, no-store`, e readiness 404 sem token configurado. Stack
encerrada com `make e2e-down`, preservando volumes sintéticos. A suíte completa
de navegador não foi repetida. O build web concluiu com aviso de dependência
circular entre os chunks `lesson-study` e `writing`.

CI remoto e implantação não executados; publicar API e monitor operacional
juntos para que a nova rota exista no destino.
Naquele ponto, os demais itens do BE-49 e o aceite completo do ciclo continuavam pendentes.

#### Registro de execução — fusos e concorrência BE-49 em 29/10/2026

Marcador `timezone` registrado no pytest e aplicado explicitamente aos cenários
de calendário, validade de sessão/token, cotas, custos diários/mensais, retenção,
revisão, áudio, curso e histórico com datas. Módulos dedicados a regras temporais
usam marcação de módulo; os demais marcam funções individuais. A coleção local
seleciona **136 de 1.376 casos**, deixando 1.240 fora da repetição em outro fuso.
Não há inferência dinâmica de marcadores no `conftest`. O CI mantém a suíte
completa com cobertura e troca somente a segunda execução por
`TZ=Pacific/Kiritimati uv run pytest -q --strict-markers -m timezone`.

Os testes de concorrência abandonaram pausas artificiais, igualdade de ticks e
o teto de um segundo de latência. Eventos coordenam trabalho de hash em threads
e liberação pelo event loop: os limites 1, 2 e 4 são respeitados, as seis tarefas
terminam e nenhum trabalho fica ativo ao final. O teste HTTP comprova que
`/api/live` responde enquanto há verificações de senha pendentes; depois da
liberação, os oito logins verificam Argon2 real e retornam 200. Timeouts de cinco
segundos protegem contra deadlock no teste, sem representar SLA de produção.
O antigo diagnóstico `SPRINT38_LOAD` de RSS/latência foi removido desse teste.

Validação local: **136 testes aprovados em UTC (17,33 s)** e os mesmos **136 em
Pacific/Kiritimati (17,10 s)**; **22 testes de concorrência aprovados**, tanto
na janela normal quanto com `LEGACY_WRITES_UNTIL=2000-01-01T00:00:00Z`
(4,92 s e 3,51 s, respectivamente). Ruff da suíte, mypy dos 106 arquivos da
aplicação e Actionlint 1.7.7 passaram. README
documenta os comandos e o critério para marcar testes novos. Nenhum código de
produção foi alterado neste incremento; CI remoto e deploy não executados.
Permanece aberto no BE-49 o pacote de tipagem estrita e cobertura de `ops/`.

#### Registro de preparação — tipagem e testes operacionais BE-49 em 29/10/2026

Primeira etapa, sem marcar o item global como concluído. A varredura
`MYPYPATH=backend uv run --project backend mypy --strict --exclude 'ops/tests/' ops`
reportava 1.060 erros em 29 arquivos, examinando 39 módulos. Após este incremento,
reporta **755 erros em 24 arquivos**. Esses números incluem chamadas a funções
sem anotação; não representam contagem de defeitos de execução independentes.

`mypy-ops.ini` passa em **14 módulos**, com `strict = True`, importação dos tipos
reais do backend e nenhuma supressão global de erros. A lista contempla formato
e transferência de backup, probes público/operacional/rollback, EasyPanel,
inventário de cues, spike de diálogo, benchmarks já tipados e leitura pós-upgrade.
O comando entrou em `make lint` e no job `recovery` antes dos ensaios Docker.
Os módulos restantes continuam visíveis no levantamento completo; a lista deve
crescer nas próximas etapas. Os testes de `ops/` ficam fora do escopo de tipagem,
mas seguem no Ruff e na execução integral da suíte.

`recovery_archive.py` ganhou contratos de entrada/saída, `FileInfo` tipado,
validação explícita de formato do manifesto/snapshot e recusa de entrada de tar
sem conteúdo regular. A transferência de voz preserva a execução isolada com
apenas os dois arquivos montados no helper. O probe de rollback agora trata
health JSON que não seja objeto como falha controlada, com retry e saída 2 no
prazo limite, em vez de escapar com `AttributeError`. O cálculo de orçamento
explicita a validação de inteiro antes da comparação; seus limites permanecem
os mesmos. O benchmark de escrita restringe o tipo dos parâmetros HTTP.

**223 testes operacionais aprovados** (194 anteriores + 29 novos). Testes novos
cobrem manifesto malformado, tar truncado, limites de inventário, referência
duplicada, symlink, fsync interrompido sem publicação, recibo sem sobrescrita,
helper standalone, timeouts/limites HTTP, ausência de credencial, erros sem
vazamento e recusas do smoke de restauração (fixture inesperada, origem errada,
áudio ausente, recusa incorreta de destino ocupado e alteração dos snapshots).
Rede, Docker e bancos não foram acionados por esses testes.

Cobertura de linhas medida localmente nos módulos trabalhados: formato de
backup **99%**, probe público **99%**, gate operacional **98%**, probe de rollback
**96%**, smoke de recuperação **84%** e transferência de voz **88%**. Os testes
do helper em subprocesso não entram na medição do processo principal. Estes
percentuais não são a cobertura de todo `ops/` nem um piso novo do CI.
Ruff de `ops/`, mypy dos 14 módulos, Actionlint 1.7.7 e `git diff --check` passaram.
CI remoto, restore integrado e deploy não executados neste incremento.

#### Registro de execução — núcleo de recuperação BE-49 em 29/10/2026

Segunda etapa da tipagem operacional: `mypy-ops.ini` passou de **14 para 22
módulos**. Entraram `recovery`, `recovery_prune`, `recovery_smoke`,
`recovery_fixture`, `dialogue_recovery`, `dialogue_recovery_data`,
`upgrade_smoke` e `rollback_image`. Os comandos de subprocesso têm argumentos,
streams binários e retornos definidos; alvos, planos de poda, seleção de
retenção, contextos de lock e fixtures têm contratos explícitos. O JSON
heterogêneo de Docker/psql continua como fronteira dinâmica; não há supressão
global de erros nem desativação da análise dos módulos importados.

Guardas acrescentadas recusam inspeção Docker que não seja objeto, inventário
de voz inválido antes de acessar o destino, fingerprints de tabelas com formato
incorreto e resposta de leitura da aplicação que não seja objeto. A fixture
confirma chave e hash presentes antes de ler o áudio.

A revisão encontrou uma divergência entre as listas de destinos: `restore`
aceitava `DIALOGUE_RESTORE`, mas `voice(..., "import")` não consultava
`DIALOGUE_DESTINATIONS`. A guarda agora inclui esse registro explícito.
Testes comprovam importação somente para destinos cadastrados, mantendo
recusa para as três origens sintéticas e para variantes com outro volume ou
projeto de produção. O helper conserva rede `none`, raiz somente leitura e
mount gravável limitado ao volume do destino. Política de retenção, nomes dos
alvos e comandos de preparação permanecem os mesmos.

**228 testes operacionais aprovados** (223 anteriores + 5 novos), Ruff de
`ops/`, mypy estrito dos **22 módulos** e `git diff --check` limpos. O comando
completo de diagnóstico, excluindo `ops/tests/`, caiu de **755 erros em 24
arquivos para 410 em 16 arquivos**, examinando os mesmos 39 módulos. O item
global de tipagem de `ops/` continua aberto; os maiores grupos restantes estão
em `roles_smoke`, `public_backup` e `assist_alignment`.

Os testes usaram arquivos temporários e comandos simulados; nenhum backup,
restore ou poda real foi executado. Laboratórios e evidências existentes foram
preservados. A checagem ampliada usa o comando já presente no CI e em `make lint`;
CI remoto e deploy não foram executados neste incremento.

#### Registro de execução — backup público BE-49 em 29/10/2026

Terceira etapa: `public_backup.py` entrou em `mypy-ops.ini`, elevando a checagem
estrita para **23 módulos**. Contratos explícitos para streams de SSH, opções
repassadas ao processo, inventário dos containers, snapshot, arquivo cifrado,
cópia e relatório de pré-voo. Snapshots exigem revisões não vazias, contagens
inteiras não negativas e lista de referências; extensões são preservadas na
comparação antes/depois para não esconder alterações durante a captura. Recibos
recusam metadados inválidos antes de criar seu diretório.

O ensaio local com `age` real encontrou arquivos AppleDouble (`._*`) acrescentados
pelo BSD tar no macOS. Eles invalidavam o pacote depois de decifrar/extrair.
O subprocesso de tar agora recebe `COPYFILE_DISABLE=1`; teste com tar real
confere que somente os arquivos do pacote são emitidos. A criação do cifrado
é exclusiva e antecede o subprocesso; a limpeza de falha só remove saída criada
pela própria chamada. Um arquivo criado concorrentemente permanece intacto.

A cópia externa também usa criação exclusiva, permissão 600, flush/fsync e
comparação de hash/tamanho antes e depois. Recusa origem que seja symlink antes
de escrever no destino e preserva arquivos concorrentes. Erro de cópia preserva
o destino parcial e não anuncia sucesso. Não houve cópia para serviço externo:
os testes usaram somente pastas temporárias locais.

**242 testes operacionais aprovados** (228 anteriores + 14 novos), Ruff de
`ops/`, mypy dos **23 módulos** e `git diff --check` limpos. Os testes cobrem
snapshot malformado, drift em campos adicionais, recibos, CLI, falha de tar/age,
timeout, criação concorrente, checksum da cópia e empacotamento real. A medição
local de cobertura de `public_backup.py` ficou em **88%**; não é um piso novo
nem a cobertura de todo `ops/`.

Prova adicional com ferramentas reais locais: chave age sintética temporária,
criação do pacote, criptografia, cópia local cifrada com hash idêntico e modo
600, decifragem e extração sob filtro `data`; os três artefatos permaneceram
idênticos e `verify_bundle` aprovou o pacote extraído. Chave e temporários foram
removidos ao final. Não houve SSH, leitura da VM, backup de dados reais, restore
de banco, mudança de destinatário operacional ou deploy.

A varredura completa dos mesmos 39 módulos, excluindo `ops/tests/`, passou de
**410 erros em 16 arquivos para 342 em 15 arquivos**. O item global permanece
aberto, com `roles_smoke` e `assist_alignment` entre os maiores grupos restantes.
CI remoto não executado; o comando já configurado no CI passa a incluir o módulo.

#### Registro de execução — papéis de banco BE-49 em 29/10/2026

Quarta etapa: `roles.py`, `roles_smoke.py`, `roles_app_smoke.py`,
`roles_archive_smoke.py`, `roles_assist_smoke.py`, `roles_dialogue_smoke.py` e
`roles_reorder_smoke.py` entraram em `mypy-ops.ini`, totalizando **30 módulos**.
Contratos explícitos para alvo, SQL por stdin, credenciais, inventário de papéis,
retornos dos ensaios assíncronos e grafo editorial. O `Any` do alvo fica limitado
ao resultado heterogêneo de Docker inspect; banco e administrador são strings.

Credenciais exigem objeto com os quatro papéis de login previstos e senhas
válidas, sem reproduzir valores na recusa. Escopos e papéis inválidos são
recusados antes de consultar recursos ou criar arquivos. Inventário malformado,
papel desconhecido/duplicado, origem de backup inválida e recibo que não seja
objeto não permitem avançar no provisionamento. As vinculações existentes do
recibo a backup, destino e snapshot foram mantidas.

O smoke HTTP agora possui `main()` e pode ser importado sem iniciar servidor ou
alterar o ambiente. Suas respostas atravessam validação de objeto/lista, token e
metadados editoriais antes do uso. Guardas do laboratório, loopback, verificações
de replay e encerramento do servidor em falha permanecem. O smoke de diálogo
exige transcrição presente antes de resolver o turno. A sonda de recusa SQL exige
stderr em bytes com SQLSTATE `42501`, sem aceitar falha de conexão como evidência
de privilégio insuficiente.

**257 testes operacionais aprovados** (242 anteriores + 15 novos), Ruff de
`ops/`, mypy dos **30 módulos** e `git diff --check` limpos. Testes novos cobrem
estrutura e privacidade das credenciais, inventário, recibos, SQL por stdin,
privilégios globais, dump vazio, transporte HTTP, ambiente incorreto, limite de
tentativas, token inválido e divergência de replay. Cobertura local medida:
`roles.py` **64%**, `roles_smoke.py` **95%** e `roles_app_smoke.py` **99%**;
esses números não representam execução integrada nem um piso global de `ops/`.

Todos os comandos de banco, Docker e HTTP foram simulados nesta etapa. Não houve
provisionamento real, alteração de grants, rotação de senhas, acesso à VM ou
deploy. Os ensaios integrados com papéis reais não foram reexecutados.

A varredura dos mesmos 39 módulos passou de **342 erros em 15 arquivos para
196 em 8 arquivos**. Restam `study_rollout`, `concurrency_rollout`,
`dev_alignment`, `assist_alignment`, `assist_alignment_smoke`, `sprint39_rollout`,
`bootstrap_editorial_keys` e `dialogue_performance`. O item global continua
aberto. A lista ampliada será verificada pelo comando já configurado no CI;
CI remoto não executado neste incremento.

#### Registro de execução — provas de migração BE-49 em 29/10/2026

Quinta etapa: `study_rollout.py`, `concurrency_rollout.py` e `dev_alignment.py`
entraram em `mypy-ops.ini`, elevando a lista estrita para **33 módulos**.
Alvos, comandos, manifests, recibos e fingerprints possuem contratos explícitos;
os fingerprints mantêm contagem inteira e SHA-256 de cada tabela histórica.

Inventários de tabelas malformados/duplicados e resultados que não sejam listas
de registros são recusados antes de gerar a prova. Provas carregadas exigem
nomes válidos, hashes de 64 caracteres hexadecimais e contagens não negativas;
campos inesperados não são descartados silenciosamente. Os hashes continuam
independentes da ordem das linhas, detectando alterações e duplicação de dados.

A auditoria valida todas as contagens antes de imprimir seu relatório. Valores
textuais, booleanos, nulos, fracionários ou negativos não aparecem como resultado
válido nem vazam conteúdo pela saída. A prova esperada deve conter exatamente
as regras atuais com contagens válidas; `audit: null` não desliga a comparação
nos fluxos de desenvolvimento/concorrência. A opção de preservar divergências
legadas exige o mesmo booleano capturado. Nenhum reparo de dados foi adicionado.

Leitura de prova privada exige objeto JSON, arquivo privado e ausência de links;
erros de leitura/decodificação recebem mensagem operacional sem conteúdo bruto.
A identificação da imagem exige um único resultado com ID não vazio. Ações
inválidas do rollout de estudo são recusadas antes de consultar o backup.

**274 testes operacionais aprovados** (257 anteriores + 17 novos), Ruff de
`ops/`, mypy dos **33 módulos** e `git diff --check` limpos. Os testes novos
cobrem estruturas inválidas, privacidade da auditoria, hashes/contagens,
identidade da imagem e fluxo completo de captura → ensaio → aplicação com
recibos em diretório temporário. O fluxo verifica vínculos de backup, imagem,
clone e revisão, permissão 600, ausência de ensaio, alteração da origem e
divergência histórica após a migration; falhas não publicam recibo de sucesso.

Cobertura local medida: `study_rollout.py` **59%**, `concurrency_rollout.py`
**54%** e `dev_alignment.py` **84%**. Permanecem caminhos sem cobertura; esses
valores não são cobertura global nem evidência de ensaio integrado.
Banco, voz, Docker e migrations foram simulados. Nenhum ambiente real foi
migrado, restaurado, parado ou reaberto; nenhum deploy foi executado.

A varredura completa dos mesmos 39 módulos caiu de **196 erros em 8 arquivos
para 94 em 5 arquivos**. Restam `assist_alignment`, `assist_alignment_smoke`,
`sprint39_rollout`, `bootstrap_editorial_keys` e `dialogue_performance`.
O item global de tipagem e cobertura continua aberto. O comando existente de
CI/`make lint` inclui os três módulos; CI remoto não executado neste incremento.

#### Registro de execução — alinhamento do assistente BE-49 em 29/10/2026

Sexta etapa: `assist_alignment.py` e `sprint39_rollout.py` entraram em
`mypy-ops.ini`, totalizando **35 módulos**. Contratos explícitos de alvo,
configuração, comandos, manifests, fingerprints e recibos; ambos os alinhamentos
validam as provas históricas carregadas antes de prosseguir. O rollout 39 também
valida a auditoria esperada antes da migration. Contagens de backfill, baseline
de integridade e reservas legadas exigem inteiros não negativos.

Foi corrigida uma referência antiga em `sprint39_rollout.configuration`: a
guarda de credenciais exigia `backups/roles-prod.json`, enquanto a leitura já
usava `secrets/roles-prod.json`. Agora a guarda verifica o diretório privado
correto. Arquivo ausente continua bloqueando a operação antes de chamar a rotina
que poderia gerar credenciais; um arquivo legado em `backups/` não satisfaz a
guarda. Prova com credenciais sintéticas em diretório temporário, sem leitura ou
alteração das credenciais operacionais existentes.

A validação do relatório HTTP é compartilhada pelos dois alinhamentos: exige
exatamente o modo clone, 11 verificações, nenhuma conta sintética restante e
nenhuma chamada ao provedor. Além dos valores, valida os tipos: `verified: 1`,
`provider_calls: false` e `checks: 11.0` não são aceitos por igualdade implícita
de Python. Recibos continuam vinculados aos scripts, imagem, backup e destino.

**283 testes operacionais aprovados** (274 anteriores + 9 novos), Ruff de
`ops/`, mypy dos **35 módulos** e `git diff --check` limpos. Testes novos cobrem
o caminho de credenciais e sua ausência, escopo inválido, env-file temporário
600 sem segredo em argv, sucesso dos dois smokes, retry limitado de readiness,
falha após 20 tentativas, relatório inválido e divergência histórica após HTTP.
Os smokes simulados encerram/removem somente o container que criaram, e falhas
não publicam recibo de sucesso. O teste existente de aplicação recebeu fixtures
com inventário de áudio e hashes completos para continuar exercitando as guardas
de ensaio/preservação, em vez de falhar antes por fixture incompleta.

Cobertura local medida: `assist_alignment.py` **77%** e `sprint39_rollout.py`
**50%**. Ainda há caminhos sem cobertura; esses valores não representam ensaio
integrado ou cobertura global. Docker, banco, migration e HTTP foram simulados;
nenhum container real foi iniciado, nenhuma senha foi rotacionada e nenhum
deploy foi executado.

A varredura dos mesmos 39 módulos caiu de **94 erros em 5 arquivos para
28 em 3 arquivos**: `assist_alignment_smoke.py` (14),
`bootstrap_editorial_keys.py` (6) e `dialogue_performance.py` (8).
O item global de tipagem e cobertura permanece aberto. O comando já configurado
no CI/`make lint` passa a incluir os dois módulos; CI remoto não executado.

#### Registro de execução — tipagem completa de `ops/` BE-49 em 29/10/2026

Sétima etapa: os últimos **28 erros em 3 arquivos foram eliminados**.
`assist_alignment_smoke.py`, `bootstrap_editorial_keys.py` e
`dialogue_performance.py` passaram na checagem estrita. `mypy-ops.ini` deixou de
usar uma lista parcial: agora verifica a pasta `ops/` inteira, excluindo apenas
`ops/tests/`. Os **39 módulos** incluem `ops/__init__.py`; novos scripts entram
automaticamente no comando já usado pelo CI e por `make lint`. Não foram usados
`ignore_errors`, `follow_imports=skip` ou supressões para encerrar a migração.

O smoke HTTP possui contratos de transporte, validação de objetos/listas e
validação do ID do prompt. O descarte do engine foi movido para `finally`,
incluindo falhas de conexão, HTTP e limpeza. Testes comprovam as 11 verificações,
uso do ledger sem provedor, DELETE restrito ao ID + e-mail exatos da conta
sintética, ausência de recibo de sucesso em falha e descarte do engine.

O bootstrap valida coleções, registros e coordenadas antes de escrever. O cast
local só ocorre depois de validar o objeto e suas chaves, preservando a mesma
instância para adicionar a identidade. Testes em arquivos temporários cobrem
dry-run sem alteração de bytes, aplicação nos seis tipos editoriais, preservação
do conteúdo, recusa de nova aplicação, coordenada duplicada e estrutura inválida.
A leitura adicional do seed real detectou posições iniciadas em zero: a validação
foi ajustada para aceitá-las, com regressão de identidade para exercício e cue.
Os **2.194 registros** existentes foram percorridos sem escrita e todos mantêm
suas chaves. O seed real não recebeu bootstrap nem escrita.

O benchmark possui contratos de métricas, datasets e travessias; valida IDs e
cursores das páginas e compila a consulta de histórico com o dialect da própria
conexão. Testes puros cobrem paginação, limites de amostras, recusa de ambiente,
emissão do relatório/código de saída e compilação PostgreSQL/asyncpg sem conectar.
O benchmark de 1k/10k não foi reexecutado nesta etapa.

**304 testes operacionais aprovados** (283 anteriores + 21 novos), Ruff de
`ops/` e `git diff --check` limpos. Tanto o comando configurado quanto a varredura
independente `MYPYPATH=backend uv run --no-sync --project backend mypy --strict
--exclude 'ops/tests/' ops` passaram com **zero erros nos 39 módulos**.
Coberturas locais: smoke HTTP **92%**, bootstrap **99%**, benchmark de diálogo
**39%**; o caminho do benchmark com banco permanece fora dessa execução.

A pendência combinada foi desdobrada para registrar o que está comprovado:
tipagem completa e testes do arquivo de backup concluídos; cobertura restante
dos smokes ainda aberta. Nesta suíte, `roles_archive_smoke`, `roles_assist_smoke`,
`roles_dialogue_smoke`, `roles_reorder_smoke` e `upgrade_smoke` continuam em
**0%**. Já `recovery_archive` está em **99%**, `recovery_smoke` em **83%**,
`roles_app_smoke` em **99%** e `roles_smoke` em **95%**. Esses percentuais não
substituem ensaios integrados nem significam cobertura completa de `ops/`.

Sessões de banco, HTTP e provedores foram simulados; arquivos de escrita eram
sintéticos e temporários. Nenhuma conta real, banco, stack ou credencial foi
alterado. CI remoto e deploy não executados neste incremento.

#### Registro de execução — fechamento dos smokes BE-49 em 29/10/2026

Os cinco módulos restantes receberam **34 testes**, elevando a suíte operacional
para **338 testes aprovados**, com banco, Docker e provedor simulados. Cobertura
local: `roles_archive_smoke` **98%**, `roles_reorder_smoke` **98%**,
`roles_assist_smoke` **96%**, `roles_dialogue_smoke` **98%** e `upgrade_smoke`
**88%**. A execução CLI de upgrade não está inteiramente coberta por essa suíte;
a cobertura não substitui os ensaios integrados do CI.

Os cenários verificam guardas de ambiente/papel/banco, identidade dos recibos,
retry idempotente, rollback, invariância das contagens, consumo e custo da cota,
12 turnos por modalidade, evidências e revisões do worker, isolamento do clone,
limite de tempo de migration, rollback da aplicação e recusa de recibo em caso
de divergência de schema, dados, voz, locks ou diretório inseguro.

Os smokes de assistência e diálogo agora podem ser importados sem executar
serviços. Os editoriais recusam banco fora do laboratório e descartam o engine
em `finally`; flags e provedor simulado são restaurados. O timeout da migration
remove com `docker rm -f` somente o contêiner temporário criado pelo ensaio,
preservando o banco e os volumes para diagnóstico.

Ruff com a configuração do backend e mypy estrito dos **39 módulos operacionais**
aprovados. Frontend: **454 testes**, lint, tipos, contrato OpenAPI, build,
orçamento de bundle e **11 testes de scripts** aprovados. A atualização foi
solicitada para Git/produção; este registro descreve a validação local e não
constitui confirmação de deploy.

O CI integrado revelou incompatibilidade na preparação do upgrade: os modelos
atuais inseriam `speaking_attempt.origin` na revisão anterior, onde a coluna
não existe. A fixture passou a usar a imagem anterior fixa; a migration e a
verificação continuam com a imagem atual. Um teste verifica tanto a criação
quanto a retomada da origem antiga. Dois testes adicionais cobrem o diagnóstico
do smoke sem exposição de payload de exceções externas: **341 testes
operacionais** após esses ajustes. A suíte local completa do backend passou
com **1.376 testes e 94,30% de cobertura**; 65 guardas E2E também passaram.

### FE-49 Lint type-aware, a11y de formulário e CSS por domínio

- [x] `tseslint.configs.recommendedTypeChecked` (ativa
  `no-floating-promises`) e `eslint-plugin-jsx-a11y`; `public/sw.js` e
  `scripts/` entram no lint.
- [x] `aria-describedby`/`aria-invalid` em todos os formulários; texto de
  ajuda fora do `<label>` em `LoginPage`.
- [x] `styles.css` dividido por domínio (`base`, `layout`, `study`,
  `practice`, `writing`, `speaking`, `dialogue`, `notebook`) sem seção por
  sprint; `!important` reduzido a casos documentados.
- [x] Data de remoção para as migrações de chave de storage v1/v2.

**Execução em 29/10/2026 — implementação e validação local concluídas.**

O lint passou a usar tipos e regras JSX de acessibilidade, incluindo service
worker e scripts. Mocks de rede/áudio foram tipados; promessas intencionais
foram explicitadas. Exceções pontuais documentadas cobrem referências de spies,
o teclado do `dialog` nativo e áudios com texto associado ou gravação privada
sem transcrição autorizada. Isso não equivale a homologação com leitor de tela.

Os seis formulários (login, plano, exercícios, checkpoint, autoavaliação e
exclusão de conta) associam ajuda/feedback por IDs. Erros nativos são anunciados;
a edição limpa somente o erro do campo alterado. Radios usam o estado de
invalidez no grupo, sem atributo incompatível no controle. Falha de rede não
marca uma resposta como inválida. A prévia de áudio deixou de usar `<label>`.

`styles.css` é agora um índice de 24 arquivos por domínio, com ordem da cascata
preservada e regras responsivas compartilhadas em `layout`. O diálogo mantém
seu CSS lazy. Os únicos `!important` restantes atendem movimento reduzido e
cores forçadas, com justificativa no arquivo. A classe antiga `map-title`, sem
uso no JSX, foi retirada. Os tetos de bundle existentes foram mantidos.

A [política de migrações de storage](politica_migracoes_storage_2026-10-29.md)
define **29/01/2027** como data-alvo condicionada à recuperação/migração;
nenhum dado expira ou é apagado por calendário. Formatos ativos v1/v2 ficam
fora da retirada.

Verificações locais aprovadas: contrato OpenAPI em sincronia, lint sem avisos, TypeScript, 456 testes
Vitest, 14 testes de scripts, 65 guardas de isolamento, seis cenários de
fila/diálogo/recuperação e dois cenários de atualização PWA. Build aprovado;
bundle inicial 128,5 KiB gzip, base abaixo de 184 KiB e diálogo abaixo de 8 KiB.
A suíte completa passou com **158 E2E aprovados e dois skips previstos**
(medição de baseline restrita a Chromium). Inclui o novo cenário de validação
nativa e axe em cadastro/plano, desktop e celular, além de teclado/modalidade
em Firefox e WebKit. Execução: `make e2e-up` e `npm --prefix e2e test`, na
stack descartável com isolamento verificado, em 10,2 minutos.

Na continuação de 29/10, a conferência adicional foi autorizada e concluída:
os oito assets JS/CSS servidos pelo Docker em `127.0.0.1:5198` têm SHA-256
idêntico ao build local. `make e2e-down` encerrou os sete contêineres e as duas
redes da stack descartável, preservando os volumes sintéticos. A indisponibilidade
anterior do serviço de aprovação deixou de bloquear essas duas verificações.

Esta entrega está na branch `sprint/49-frontend-quality`, ainda sem publicação.
O quadro inicial registra as publicações anteriores. Aceite manual de
VoiceOver/piloto continua pendente no ciclo 48. A continuação abaixo executa
**DB-49**; depois ficam as frentes operacionais INFRA/SEC-49.

### DB-49 Política de downgrade e testes

- [x] Política escrita: migrations aditivas, downgrade permitido até qual
  revisão, o que o CI testa; `d06a4e9cb153` referenciada como marco.
- [x] Limpeza do `conftest` por `TRUNCATE` das tabelas não-seed ou
  transação com rollback, substituindo o `DELETE` ad hoc da unidade `31-35`.

**Execução em 29/10/2026 — implementação e validação local concluídas.**

A [política de migrations e downgrade](politica_migrations_downgrade_2026-10-29.md)
documenta expansão/contração, o ciclo legado vazio até `c95f3d8ba042`, o marco
irreversível `d06a4e9cb153` e as condições de retorno por aplicação compatível
ou restauração em outra base. O CI passa a repetir `upgrade head` antes do
`alembic check`; não foi liberado downgrade de dados de aluno.

O isolamento classifica explicitamente as 53 tabelas dos modelos: 19 de seed
e 34 transitórias. A fixture confirma ambiente e identidade real, limpa as
transitórias com `TRUNCATE ... RESTART IDENTITY RESTRICT` antes/depois de cada
cenário e preserva commits e conexões independentes dos testes de concorrência.
Inventário incompleto/sobreposto e dependência externa recusam a limpeza.

O cenário curricular `31-35` usa agora transação externa e savepoints, com
rollback inclusive após commit e exceção. Foram retirados os deletes por slug.
Cinco novos testes cobrem preservação integral do seed, limpeza idempotente,
recusa de alvo/inventário/dependência e visibilidade/rollback pela API.
As simulações de ambiente de produção nos testes de quarentena e edição
terminam antes do teardown, mantendo a recusa de limpeza fora do ambiente de teste.

Ruff e mypy estrito aprovados na aplicação (106 módulos) e no helper de
isolamento. Os 15 testes direcionados de isolamento, cursos e migration
passaram. Após ajustar as simulações de ambiente, a suíte completa passou
com **1.381 testes e 94,30% de cobertura**, em 7min05s. O helper também foi
revalidado isoladamente, com cinco testes aprovados após o ajuste de importação.

A identidade do PostgreSQL descartável foi confirmada; `upgrade head` rodou
duas vezes e `alembic check` terminou sem novas operações. O ciclo legado
vazio não foi repetido sobre essa base já migrada; permanece no CI. Nenhuma
migration nova foi necessária. `make test-db-down` encerrou o contêiner e a
rede de testes, preservando o volume sintético.

Publicação e CI remoto das entregas FE/DB-49 ainda pendentes. A continuação
INFRA-49 está registrada acima; o ensaio SEC-49 está registrado abaixo.

### SEC-49 Ensaio de rotação

- [x] Rotacionar `JWT_SECRET`, token do provedor e senhas dos papéis de
  banco em laboratório, medindo impacto em sessões ativas e documentando a
  ordem segura.

#### Registro de execução — 29/10/2026

O [runbook de rotação](rotacao_segredos_2026-10-29.md) registra a ordem
**backup → migrador → worker → runtime**, seguida da troca coordenada do JWT
e da sobreposição/revogação do token do provedor quando suportada.
O laboratório exclusivo `aulas-ingles-rotation49` usa banco marcado, rede
interna sem portas, credenciais aleatórias e gateway HTTP sintético.

As quatro senhas antigas foram recusadas em conexões novas; as quatro novas
foram aceitas. Conexões abertas sobreviveram. Runtime com senha desatualizada
respondeu health 503; após atualização, health 200 e sessão anterior válida.
O JWT novo invalidou access/refresh antigos (401); novo login/refresh passou
(200). Instâncias com chaves diferentes demonstraram respostas 200/401 à mesma
sessão. A sequência do gateway foi 200/200/200/401/200 usando o cliente real.

Nota sintética, grants de tabelas, atributos/membros dos papéis e chaves do
limitador com segredo explícito foram preservados. A conta criada foi removida;
zero usuários restantes. O proprietário NOLOGIN e a senha administrativa não
foram rotacionados. Não houve alteração de segredos ou dados de produção.

Execução final: **9.772 ms** totais; senhas/reinício **3.513 ms**, JWT
**1.376 ms**, gateway **505 ms**. Medições locais não equivalem a SLA.
Recibos privados contêm somente agregados e hashes dos scripts. O laboratório
foi encerrado preservando seu volume; ausência de containers do projeto
confirmada, sem limpeza global de Docker.

Validação: **343 testes operacionais** (sete novos), Ruff, mypy estrito em
**40 módulos**, Compose e actionlint aprovados. Ensaio integrado repetido com
os scripts finais. Etapas adicionadas ao CI, incluindo encerramento obrigatório.
Jobs longos, provedor externo e rascunhos/áudio no navegador não foram ensaiados.

**Publicação concluída:** FE/DB/INFRA/SEC-49 integradas no PR #41, com CI e
deploy aprovados, incluindo upgrade e rotação; ver quadro consolidado.
**Próxima frente:** fechar os requisitos operacionais e a revisão SEC-46,
publicar e configurar a restrição do piloto à conta autorizada e preencher a
[matriz da Sprint 48](matriz_aceite_sprint_48.md). Acessibilidade manual e
pendências de backup continuam abertas; este ensaio não encerra esses itens.

---

## Registro de execução — restrição do piloto (29/10/2026)

Implementação local de `DIALOGUE_PILOT_USER_IDS`, lista validada de IDs positivos.
Produção/perfil público negam acesso assistido quando a lista está vazia.
Status, criação e novos turnos verificam a conta; upload recusado não grava
áudio. Worker filtra a fila por participante e verifica novamente antes de
consumir cota e chamar STT/LLM. Roteiro e portabilidade permanecem disponíveis.
Compose repassa a lista à API e ao worker, inclusive no EasyPanel.

Validação local: **1.399 testes backend aprovados**, incluindo 18 novos casos,
com **94,31% de cobertura**; **345 testes operacionais** aprovados. Ruff,
mypy (106 módulos backend e 40 operacionais), ESLint e TypeScript sem erros.
Composes de produção/EasyPanel conferidos com lista vazia e lista explícita
iguais na API e no worker. Baseline OpenAPI preservado. Provedores simulados,
sem envio real de áudio/texto e sem alteração em produção.

**Estado:** ainda não publicado/aplicado à VM; assistência continua desligada.
Próximos passos: publicação, vínculo privado da conta autorizada, gateway real,
monitoramento autenticado e revisão SEC-46. Antes de habilitar áudio, restringir
também a STT compartilhada, que atende uma modalidade fora da conversa. Um
piloto somente texto mantém URLs de STT/escrita ausentes. Orçamento permanece USD 0.
Detalhes e limites operacionais na [matriz](matriz_aceite_sprint_48.md).

## Registro de execução — gateway e áudio do piloto (29/10/2026)

A lista do piloto passou a proteger também STT compartilhada e escrita, na
admissão/status e no worker antes de consumo/rede. Roteiro, histórico, áudio
salvo, exportação e exclusão permanecem disponíveis. Produção/public com lista
vazia bloqueiam todas as modalidades assistidas.

Gateway HTTPS direto Workers AI implementado, com origem/modelos fixos, sem
redirects nem retries automáticos. O modelo Llama 3.3 70B fp8 fast passou no
schema/saneamento reais; Whisper Tiny EN passou com voz sintetizada. O candidato
3.1 fp8 da conta não aceita JSON Schema (erro 5025), por isso foi substituído.
Confiança STT ausente agora é `null` no contrato e “não informada” na interface.
Nenhum dado do aluno foi enviado no ensaio; a qualidade exige o piloto real.

Revisão técnica SEC-46 concluída, com correção da promessa de anonimização e
explicitação do áudio bruto enviado à STT. Aceite informado solicitado ao
responsável; não foi presumido da autorização para transferir a credencial.
Credencial e lista de uma conta preparadas em arquivo privado 0600 na VM, após
autorização expressa. Ambiente ativo/flags não modificados nesta preparação.
Workers Free declarado pelo usuário; leitura de faturamento devolveu 403, sem
upgrade ou compra de créditos. Orçamento permanece USD 0.

Validação: regressão **1.420 testes backend / 94,22%**, **457 testes frontend**,
**345 testes operacionais**, lint/types e build/budget aprovados. Um caso adicional
cobre o marcador vazio observado na STT real; rodada final de 45 testes
aprovada, cobertura consolidada **94,26%**. OpenAPI e tipos frontend atualizados.
Publicação e aplicação do ambiente serão registradas na [matriz](matriz_aceite_sprint_48.md).

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
