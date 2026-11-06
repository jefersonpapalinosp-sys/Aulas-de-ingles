# Plano das Sprints 50 a 61 — auditoria e prática rápida de listening

Atualizado em **05/11/2026**: as Sprints 50–58 preservam o escopo da auditoria de
04/11; as Sprints 59–61 acrescentam o módulo de prática rápida de listening solicitado.
O nome deste arquivo foi preservado para manter os links existentes. A implementação
concluiu o código das Sprints 50–59 e preparou o piloto nativo da Sprint 60.
Os aceites operacionais/publicação continuam pendentes. A Sprint 60 possui
três rascunhos próprios, player e correção integrados, mas seu **aceite editorial
continua pendente**: áudio, nível A2 e direitos exigem revisão humana.
A Sprint 61 permanece planejada, sem data de publicação confirmada.
A Sprint 59 segue utilizável independentemente do piloto, desativada por padrão.

Base: `main` em `012e54a` (PR #42), head Alembic `c92f4a8d710e`. A auditoria usou sete
especialistas, somente leitura: segurança, corretude do backend, frontend/PWA, banco e
migrations, infra/CI, scripts de `ops/` e QA (execução das suítes). Foram **89 achados**:
1 crítico e 15 altos.
Este plano continua a numeração do [plano das Sprints 44–49](plano_sprints_44_49_frentes_e_assistente_de_fala_2026-10-21.md)
e agrupa por **tema**, não por frente. Cada achado mantém o ID do relatório (SEC, BE, FE, DB, INF, OPS, QA).

Regras herdadas: recursos assistidos continuam desligados por padrão; texto e áudio do aluno
não entram em log; toda mudança de schema segue a sequência da Sprint 43 (backup, ensaio em
clone, migration pelo papel migrador).

## Pendências identificadas na auditoria de 04/11/2026

Este registro descreve o ponto de partida. A Sprint 58 executou o E2E completo
no Linux (162 testes aprovados e dois skips declarados), mediu a cobertura do
frontend e validou as suítes portáteis e POSIX nos ambientes correspondentes.
O estado atualizado e as limitações estão nas
[evidências da Sprint 58](execucao_sprint58_2026-11-05.md).

- **E2E completo não executado.** Os cerca de 72 testes Playwright e as checagens axe não
  rodaram: a guarda `e2e/safety.mjs` exige socket Unix e recusa o Docker Desktop do Windows
  (QA-01). É a maior lacuna de verificação desta auditoria.
- **Falsos positivos no Windows.** Falhas de `vitest`, `test:scripts`, `check:api`, `mypy`,
  de 70 testes de `ops/` e as 98 do `pytest` vêm de separador de caminho, CRLF, `tzdata`
  ausente, pasta temporária sem permissão e APIs POSIX. Não indicam bug do produto.
- **Resultado real do backend (Linux, contêiner descartável):** 1421 testes, 1417 passaram,
  cobertura 93,6 % (piso do CI: 90 %). Das 4 falhas, 3 são transitórias (o relógio da VM do
  Docker recuou cerca de 22 s) e 1 é determinística (QA-02).
- **Não verificado:** se o Traefik do EasyPanel descarta `X-Forwarded-For` vindo do cliente
  (decide a gravidade real de SEC-01 em produção); o estado do CI no commit `012e54a`; o
  kernel do host de produção (decide se QA-02 se manifesta lá); a cobertura do frontend; os
  laboratórios de integração de `ops/`.

## Visão geral

| Sprint | Tema | Prioridade | Achados / itens | Esforço |
|---|---|---|---|---|
| 50 | Vigilância e alertas que realmente alertam | Crítica | OPS-01, INF-01, BE-03, INF-04, INF-11, INF-12 | P |
| 51 | Borda, sessão e autenticação | Alta | SEC-01/BE-06, INF-09, SEC-02, SEC-04, BE-01, SEC-05, SEC-06, INF-13 | P a M |
| 52 | Privacidade e exclusão de dados (LGPD) | Alta | SEC-03, DB-04, DB-02, DB-03, FE-02 | M |
| 53 | Worker de assistência e diálogo | Alta | BE-02, BE-04, BE-05, DB-08, BE-10/DB-09 | M |
| 54 | Continuidade: backup e recuperação | Alta | OPS-02/INF-03, OPS-03, OPS-07, OPS-10, OPS-11, OPS-12, OPS-08 | M a G |
| 55 | Deploy seguro e cadeia de suprimentos | Média-alta | INF-02/OPS-04, INF-05, INF-06, INF-07, INF-08, OPS-05, OPS-06, OPS-15, INF-14 a INF-17 | M |
| 56 | Migrations, grants e integridade | Média | DB-01, DB-05, DB-06, DB-07, DB-11, DB-12, DB-13, DB-14, OPS-09 | M a G |
| 57 | PWA e offline | Média | FE-01, FE-03, FE-04, FE-05, FE-06, FE-08 | M |
| 58 | Qualidade, portabilidade e acabamento | Baixa a média (QA-01 alta) | FE-07, FE-09 a FE-12, BE-07 a BE-09, INF-10, OPS-13, OPS-14, QA-01 a QA-12 | P a M |
| 59 | Listening rápido: catálogo A2 e acesso às atividades externas | Média, após estabilização | LIST-01 a LIST-04 | M |
| 60 | Listening rápido: piloto de prática dentro do aplicativo | Média, expansão condicionada ao conteúdo | LIST-05 a LIST-08 | G |
| 61 | Listening rápido: retomada, histórico e publicação validada | Média | LIST-09 a LIST-12 | M a G |

## Ordem de execução por prioridade — 05/11/2026

| Ordem | Sprint / recorte | Motivo e condição para avançar |
|---|---|---|
| 1 | **50 — alertas e continuidade do worker** | Corrigir falhas silenciosas antes das próximas mudanças; iniciar pelos testes locais, depois validar instalação/recebimento do alerta no ensaio |
| 2 | **57 — antecipar FE-01 e verificar FE-08** | Atualização da PWA precisa funcionar antes do corte de clientes legados em 13/11/2026; não aumentar o teto de bundle |
| 3 | **51 — autenticação e borda** | Reduzir riscos de sessão, abuso e confiança nos proxies |
| 4 | **52 — privacidade e exclusão** | Corrigir dados órfãos, índices e limpeza por conta antes de criar novos dados pessoais |
| 5 | **53 — processamento de assistência** | Resolver locks, concorrência, posse de jobs e desligamento do worker |
| 6 | **54 — backup e recuperação** | Definir agendamento/custódia e demonstrar restore público antes de depender da recuperação |
| 7 | **55 — deploy e dependências** | Fortalecer publicação, rollback e bloqueios de segurança do CI |
| 8 | **56 — migrations e integridade** | Consolidar grants/constraints após os índices introduzidos na 52 |
| 9 | **57 — restante de PWA/offline** | Fila, telas offline e desempenho, preservando as correções antecipadas |
| 10 | **58 — qualidade e portabilidade** | Fechar verificações integradas e execução E2E de referência em Linux/WSL |
| 11 | **59 — catálogo de listening** | Liberar os links A2 e o progresso autodeclarado sobre a base estabilizada |
| 12 | **60 — piloto de listening no app** | Depende de três atividades próprias/licenciadas revisadas e da 59 |
| 13 | **61 — retomada e publicação de listening** | Consolidar histórico, sincronização e homologação do módulo |

Esta é a ordem de integração e aceite. Tarefas independentes podem ser desenvolvidas
em paralelo, mas falhas encontradas nos testes precisam ser resolvidas antes da integração.
A instalação do monitoramento e o recebimento de alertas são verificações operacionais
separadas dos testes de código; não considerar a Sprint 50 encerrada só por testes locais.

O módulo novo segue **59 → 60 → 61**, após o ciclo de estabilização 50–58. A análise
editorial e o desenho do catálogo podem ser preparados antes, sem deslocar a Sprint 50
nem a correção FE-01. As estimativas P/M/G são relativas, não compromissos de calendário.
Privacidade (52), migrations/grants (56), atualização PWA/bundle (57) e E2E isolado (58)
são dependências explícitas. O piloto nativo da 60 exige mídia e exercícios próprios ou
autorizados; essa condição não impede entregar o catálogo externo da 59.

Escopo, decisões de produto, arquitetura e fontes estão na
[análise do módulo de listening rápido](analise_modulo_listening_rapido_2026-11-05.md).

---

## Sprint 50 — Vigilância e alertas que realmente alertam

**Estado:** código implementado e validado localmente em 05/11/2026; aceite
operacional pendente de instalação e ensaio de alerta. Acompanhamento e evidências em
[execução da Sprint 50 e antecipação FE-01](execucao_sprint50_e_fe01_2026-11-05.md).

**Objetivo:** hoje, API fora ou worker parado não gera alerta nenhum.

- **OPS-01 (crítica)** `operations.yml:59,76`: o `tee` sem `pipefail` mascara o código de saída
  e o job nunca falha. Usar `shell: bash` ou gravar em arquivo sem pipe.
- **INF-01** criar a secret `OPERATIONS_TOKEN`; instalar o cron da VM (1–2 min) com
  `make operations-alert`; fazer o workflow falhar quando o probe existe e o token não.
- **BE-03** `transcription_queue.py:471-479`: separar o `sweep()` do heartbeat e do claim, com
  `try/except` próprio. Falha permanente de manutenção hoje para os jobs e derruba o healthcheck.
- **INF-04** rotação de logs (`max-size`, `max-file`) em todos os composes.
- **INF-11** healthcheck da API em `/api/live`; `/api/health` fica para readiness.
- **INF-12** `shm_size` no Postgres e `pids_limit` nos serviços.

**Aceite:** derrubar o worker de propósito em ensaio e receber o alerta em até 5 minutos;
workflow vermelho quando o gate falha; teste que prova o código de saída propagado.

## Sprint 51 — Borda, sessão e autenticação

**Estado:** código implementado e validado localmente em 05/11/2026. Configurar
os proxies confiáveis e confirmar a cadeia real do Traefik antes de publicar.
[Escopo e evidências da Sprint 51](execucao_sprint51_2026-11-05.md).

- **SEC-01 / BE-06** `Dockerfile.prod:40-41` usa `--forwarded-allow-ips "*"` e o nginx anexa o
  `X-Forwarded-For` do cliente. O limite por origem do login é contornável. Restringir ao IP do
  nginx ou usar `$remote_addr`. Confirmar o comportamento do Traefik antes de fechar a gravidade.
- **INF-09** `limit_req` keyed pelo IP do Traefik vira teto global de login (DoS barato).
  Usar `set_real_ip_from` com a rede do proxy.
- **SEC-02** reuso de refresh fora da janela deve revogar a família inteira, como o logout faz.
  Fixar teto absoluto de vida da família. Corrigir o teste que só confere o 401.
- **SEC-04** `DELETE /me/account` confere senha sem rate limit. Aplicar `rate_limit` por e-mail.
- **BE-01** senha errada na exclusão devolve 401, o cliente renova, reenvia e desloga o aluno.
  Trocar por 403 com `code=password_mismatch`.
- **SEC-05** adaptador `gateway` segue redirects com `Authorization`. Usar `NoRedirect`.
- **SEC-06** desligar `/docs`, `/redoc` e `/openapi.json` em prod/public.
- **INF-13** timeouts e buffering explícitos no proxy; `proxy_request_buffering off` no upload.
- Opcionais: **SEC-07** (enumeração no registro), **SEC-08** (bloqueio dirigido por e-mail).

**Aceite:** teste de integração com `X-Forwarded-For` forjado; teste de reuso de refresh que
revoga a cadeia; teste E2E de senha errada sem logout.

## Sprint 52 — Privacidade e exclusão de dados (LGPD)

**Código e validações locais concluídos em 05/11/2026.** Publicação e ensaio em
clone continuam pendentes. [Escopo e evidências da Sprint 52](execucao_sprint52_2026-11-05.md).

- **SEC-03 / DB-04** excluir um diálogo deixa a gravação de voz órfã, invisível ao aluno e fora
  da retenção. `DELETE /speaking/attempts/{id}` responde 404 para `origin='dialogue'`. Apagar a
  linha e o arquivo junto com o diálogo; decidir o prazo de retenção do áudio de diálogo (30 dias
  como o texto, ou exceção documentada).
- **DB-02** FKs sem índice no caminho da exclusão de conta: `study_active_interval.event_id`,
  `review_event.item_id`, `practice_session.source_session_id`. Com `statement_timeout` de 30 s a
  exclusão passa a falhar quando as tabelas crescerem. Índices `CONCURRENTLY`.
- **DB-03** índice parcial para a varredura de retenção de diálogos, que hoje recresce sempre.
- **FE-02** excluir a conta deve limpar rascunhos, fila IndexedDB e posições do dispositivo.
- Atualizar `docs/modelo_ameacas_assistente_2026-10-26.md`: diz "sete rotas" (há nove) e
  "excluir o turno" (só existe excluir o diálogo inteiro).

**Aceite:** teste de exclusão com conta populada por 10 mil eventos dentro do timeout; teste que
confirma ausência de arquivo e de linha de áudio após excluir o diálogo.

## Sprint 53 — Worker de assistência e diálogo

**Código e validações locais concluídos em 05/11/2026.** Publicação e ensaio em
clone continuam pendentes. [Escopo e evidências da Sprint 53](execucao_sprint53_2026-11-05.md).

- **BE-02** `dialogue.py:560-596`: lock de linha mantido durante `urlopen` síncrono no event loop.
  Usar `asyncio.to_thread` e travar só para gravar. Hoje o aluno recebe 503 e o heartbeat congela.
- **BE-04** catch-all no loop do worker, tratamento de SIGTERM e marcação de job venenoso.
- **BE-05** guarda de posse na finalização do job de diálogo; `validar()` deve exigir
  `ASSIST_JOB_STALE_SECONDS >= 2 × timeout + folga`.
- **DB-08** trocar o índice composto da fila por `(status, next_attempt_at, id) WHERE status='queued'`
  após medição; remover índices single-column redundantes.
- **BE-10 / DB-09** aplicar `database_connection_budget` ou removê-lo; checar `max_connections`
  no boot; `idle_in_transaction_session_timeout` e `log_lock_waits` no Postgres.

**Aceite:** ensaio com dois workers e `stale == timeout` sem chamada duplicada ao provedor;
`docker stop` durante um job sem perda de tentativa.

## Sprint 54 — Continuidade: backup e recuperação

**Código e validações locais concluídos em 05/11/2026.** Instalação do timer,
custódia separada, recebimento do alerta e DR em VM nova continuam pendentes.
[Escopo e evidências da Sprint 54](execucao_sprint54_2026-11-05.md) e
[runbook de recuperação pública](backup_recuperacao_publica_2026-11-05.md).

- **OPS-02 / INF-03** o backup depende de um Mac ligado às 03:10 e a única chave `age` está nele.
  Mover o agendamento para a VM ou runner, guardar a chave em custódia separada e expor
  `last_backup_age_hours` no gate (alerta acima de 24 h).
- **OPS-03** não existe restauração para a stack pública. Escrever o runbook de DR e o
  `public_restore`, ensaiar em VM descartável e registrar o RTO medido.
- **OPS-07** a poda apaga o backup pré-migration do mesmo dia. Criar marcador `hold`.
- **OPS-10** checagem de drift estrita demais invalida o backup noturno; comparar só voz.
- **OPS-11** lock órfão após crash; adicionar `lease-break` com confirmação.
- **OPS-12** retenção das cópias `.tar.age` externas.
- **OPS-08** diagnóstico sanitizado nos 13 pontos que engolem a exceção.

**Aceite:** restore completo cronometrado numa VM nova; falha de backup gera alerta.

## Sprint 55 — Deploy seguro e cadeia de suprimentos

**Código implementado e validado localmente em 05/11/2026.**
[Evidências e pendências](execucao_sprint55_2026-11-05.md): rollback sintético
em 8,773 s; nginx UID 101; scan final sem CRITICAL. Instalação do usuário/comando
SSH, required reviewers, ensaio de deploy na VM e eventual remoção de branches
continuam pendentes. Nenhum PR Dependabot foi mesclado automaticamente.

- **INF-02 / OPS-04** deploy e backup entram como `root` com IP fixo no repositório. Criar
  usuário de deploy no grupo `docker`, `authorized_keys` com `restrict,command=`, host só por
  secret, *required reviewers* no environment `production`.
- **INF-05** fixar imagens-base por digest nos Dockerfiles de produção.
- **INF-06** incluir `infra-lint` no `needs` do deploy e um Trivy `CRITICAL` bloqueante.
- **INF-07** fixar actions por SHA.
- **INF-08** triar os 12 PRs do Dependabot e incluir o ecossistema `docker`.
- **OPS-05** preservar a imagem anterior e oferecer `--rollback` sem rebuild.
- **OPS-06** janela de 503 a cada migration; construir antes do `up` ou tolerar schema à frente.
- **OPS-15** `flock` e timeout no deploy manual.
- **INF-14 a INF-17** nginx sem root, `.dockerignore`, stack de dev e branches antigas.

**Aceite:** deploy de ensaio com usuário restrito; rollback medido em menos de 5 minutos.

## Sprint 56 — Migrations, grants e integridade

**Estado:** código implementado e validações locais executadas em 05/11/2026.
As falhas determinísticas encontradas foram corrigidas; recuos do relógio da VM
impediram uma execução integral sem falhas, e os casos afetados passaram na
rechecagem. Ensaio em clone representativo, rotação real e publicação pendentes.
[Escopo e evidências da Sprint 56](execucao_sprint56_2026-11-05.md).

- **DB-01** `lock_timeout` e `statement_timeout` nas migrations (`alembic/env.py:50`).
- **DB-05** uma só fonte de grants; teste no lab de papéis que compara os privilégios efetivos.
- **DB-06** regra de revisão: CHECK e FK sempre `NOT VALID` seguido de `VALIDATE`.
- **DB-07** guarda de contagem no downgrade de `b84e2c7a9d31`.
- **DB-11 / DB-12** convenção completa de nomes e CHECK de tamanho em campos vindos do provedor.
- **DB-13** validador do seed contra faixas de unidade sobrepostas (`31-40` e `40-44`).
- **DB-14** registrar as senhas literais dos laboratórios como risco aceito.
- **OPS-09** rotação de JWT com `kid` e dupla validade (esforço G, pode virar sprint própria).
- Melhoria: PKs `bigint` nas tabelas de evento antes do volume real.

## Sprint 57 — PWA e offline

**Estado:** código implementado e validações locais concluídas em 05/11/2026.
FE-01 preservado; fila com pausa/retomada, navegação offline, coalescência de
posições e exportação corrigidas. Bundle dentro dos limites existentes.
[Escopo e evidências da Sprint 57](execucao_sprint57_2026-11-05.md).
Publicação e homologação no ambiente público continuam pendentes.

- **FE-01 (alta)** "Atualize o aplicativo" e "Recarregar" não trazem a versão nova: o SW antigo
  serve o shell e nunca faz `skipWaiting`. Isso colide com o cutover de 13/11. Enviar
  `SKIP_WAITING`, aguardar `controllerchange` e então recarregar.
- **FE-03** a fila trava em cascata num item com 5xx persistente; contador por item e opção de pular.
- **FE-04** Hoje e Mapa viram tela de erro offline mesmo com o currículo em cache.
- **FE-05** uma gravação de posição de áudio a cada 5 s; coalescer comandos pendentes.
- **FE-06** revogação síncrona do blob na exportação do Caderno.
- **FE-08** orçamento de bundle a 17 bytes do teto e chunk circular `lesson-study` e `writing`.
  Resolver primeiro, ou qualquer correção desta sprint estoura o orçamento.

## Sprint 58 — Qualidade, portabilidade e acabamento

**Código e aceite integrado local concluídos:** backend com 1.489 testes
aprovados em três execuções consecutivas no Linux (94,05% de cobertura),
frontend com 485 testes e E2E com 162 aprovados e dois skips declarados.
[Escopo e evidências da Sprint 58](execucao_sprint58_2026-11-05.md).
Publicação e os aceites operacionais anteriores continuam pendentes.

- **FE-07, OPS-14, INF-10, OPS-13** `.gitattributes` com LF, `platform = linux` no mypy, `python`
  em vez de `python3`, `curl` sem `-o /dev/stdout` e `mktemp` no Makefile.
- **FE-09 a FE-12** reduced motion no scroll por JS, rótulos de 10 px, ícones PNG, textos de rota.
- **BE-07** fator por tipo de carta composto a cada revisão (decidir a intenção e testar).
- **BE-08, BE-09** corrida em `create_practice_session` e desempate na ordenação de `/review/items`.
- Melhorias menores dos seis relatórios (UTC da cota, normalização de aspas, 503 permanente).

Achados de QA (execução das suítes):

- **QA-01 (alta)** `e2e/safety.mjs:30-33,118-121`: E2E, `e2e-check` e `e2e-down` não rodam no
  Windows, e o `catch` troca a causa por uma mensagem genérica. Aceitar o `npipe` local do
  Docker Desktop ou declarar o E2E como Linux/WSL-only e imprimir a asserção original.
- **QA-02** `audio_audit.py:157-165`: arquivo alterado durante o hash só é percebido por
  inode, tamanho e timestamps; regravação de mesmo tamanho passa despercebida no kernel 6.6
  (180 de 200 medições). Comparar um segundo hash; no teste, cobrir o caso de mesmo tamanho.
- **QA-03** 62 chamadas `await client.<verbo>(...)` com a resposta descartada em 11 arquivos de
  teste: a preparação que falha aparece longe da causa. Criar helper que valida o status.
- **QA-04** suíte do backend não roda limpa no Windows: `tzdata` condicional no grupo dev,
  `skipif` nos testes POSIX e `--basetemp` documentado.
- **QA-05** `security.py:75`, `review.py:122,188`: sessão e revisão sem tolerância de relógio
  causaram 5 falhas espúrias. Decidir `leeway` no `jwt.decode`; congelar o relógio nos testes.
- **QA-06** `e2e/playwright.queue.config.ts:11`: comando do `webServer` só funciona em shell
  POSIX. Chamar `node ../frontend/node_modules/vite/bin/vite.js` (validado: 6 de 6).
- **QA-07** esperas fixas: 18 s de `waitForTimeout` em `sprint39.spec.ts:86-88` e timeout de
  0,01 s contra `sleep(0.1)` em `test_audio_upload.py:59-64`. Usar relógio controlado.
- **QA-08** `App.test.tsx`, `StudyPage.test.tsx` e `PersonalDataPage.test.tsx` simulam os
  módulos de API; a exclusão de conta só é validada contra API simulada. Simular no `fetch`.
- **QA-09 a QA-12** id de teste de 1 MB em `test_cloudflare_provider.py:75`; 4 testes sem
  asserção; `fluxo-completo.spec.ts` com 2778 linhas em série; benchmarks de carga só manuais.
- **Lacunas de cobertura:** logout e exclusão de conta sem E2E; refresh só com rota
  interceptada; frontend sem medição nem piso de cobertura (16 de 21 módulos de `src/api` sem
  teste unitário); `ops/rollout` e `rotation_probe` sem teste dedicado.

**Aceite:** E2E completo executado ao menos uma vez num host Linux ou WSL, com o resultado
registrado; `make test-api` verde no Linux em três execuções seguidas.

---

## Sprint 59 — Listening rápido: catálogo A2 e atividades externas

**Código e validações locais concluídos:** catálogo com 31 links, progresso
manual por aluno, exportação/exclusão, migration/seed e interface responsiva.
Backend: 1.506 testes; frontend: 496; E2E com oito jornadas novas aprovadas e
reteste de regressão registrado nas [evidências da Sprint 59](execucao_sprint59_2026-11-05.md).
Ativação e publicação seguem pendentes; veja o [guia de operação e uso](listening_rapido.md).

**Objetivo:** disponibilizar uma entrada independente para as 31 atividades observadas no
[catálogo A2 do Test-English](https://test-english.com/listening/a2/) em 05/11/2026.
Esse total é a referência inicial do inventário, não uma sincronização automática.

- **LIST-01 · Conteúdo:** inventariar os 31 links com identificador estável, rótulo e
  descrição autorais, tema, nível informado pela fonte, data de conferência e disponibilidade.
  Duração só aparece quando verificada. Os
  [termos do Test-English](https://test-english.com/terms-of-use/) permitem compartilhar
  links, mas restringem cópia, download, enquadramento e republicação dos materiais.
  A entrega usa links; perguntas, imagens, transcrições e vídeos do site não são importados.
- **LIST-02 · Backend/banco:** criar catálogo independente e estado por aluno, seed
  idempotente e contratos de leitura/escrita. Incluir os novos dados em exportação,
  exclusão de conta e testes de isolamento já nesta sprint; atualizações usam revisão e
  idempotência. Nenhuma alteração na contagem, conclusão ou certificado dos cursos VOA.
- **LIST-03 · Frontend:** atalho “Listening rápido”, rota `/listening`, busca por tema,
  filtro por estado e cards com fonte. “Abrir no Test-English” abre nova aba; o aluno
  pode marcar manualmente “Não iniciada”, “Em andamento” ou “Concluída por mim”.
  Abrir o link não conclui a atividade e não importa nota ou tempo do site externo.
- **LIST-04 · QA/infra:** validar links e indisponibilidade, controle de acesso, concorrência,
  navegação por teclado/mobile, ausência de incorporação de terceiros e comportamento sem rede.
  Acesso externo depende de internet; gravação de estado só é confirmada após resposta da API.

**Aceite:** inventário dos 31 links reconciliado, sem duplicatas; atividades disponíveis
acessíveis em até duas ações a partir do menu; origem e estado autodeclarado claros;
estado persiste após login e integra exportação/exclusão; nenhum resultado VOA é alterado.
Itens indisponíveis ficam sinalizados, preservando o histórico. Contrato, migration/seed,
testes de API, interface e E2E isolado aprovados. Esta entrega já permite usar as lições externas.

## Sprint 60 — Listening rápido: piloto nativo

**Estado:** implementação técnica do piloto preparada; aceite editorial e publicação
pendentes. LIST-05 tem três rascunhos originais (4 + 3 + 3 questões), com áudio sintético,
transcrição, explicações e mapa acessível. LIST-06/07 implementam versões imutáveis,
correção no servidor e interface; LIST-08 cobre migração, grants, privacidade e
recuperação. Veja o [guia e material para revisão](listening_nativo.md) e as
[evidências de execução](execucao_sprint60_2026-11-05.md).

**Objetivo:** completar o fluxo “escolher → ouvir → responder → conferir” dentro do app,
com **três atividades piloto** e duração-alvo de **5–10 minutos** por atividade, a validar.
Conteúdo do Test-English só entra mediante autorização específica; a alternativa executável
é produzir material próprio ou usar material com licença compatível, com revisão humana.

- **LIST-05 · Conteúdo:** preparar três atividades originais/licenciadas com 3–7 questões,
  cobrindo escolha única, seleção de duas alternativas e interpretação de mapa/diálogo.
  Validar nível A2, áudio, gabarito, explicações, transcrição e direitos por ativo.
  Mapas precisam de alternativa acessível; revelar apoio textual deve ser identificado
  como apoio, sem impedir seu uso. Temas sugeridos: hospedagem, orientação urbana e lazer.
- **LIST-06 · Backend/banco:** modelar versão da atividade, questões, sessão e respostas
  fora das tabelas de progresso VOA. Corrigir no servidor e ocultar gabaritos antes de
  responder/revelar. Criar `multi_select` com IDs estáveis: conjunto completo, sem importar
  ordem, rejeitando duplicatas/IDs desconhecidos e validando a quantidade exigida.
  Nota usa a primeira resposta de cada questão; repetição/revelação têm marcação própria.
- **LIST-07 · Frontend:** rota `/listening/:slug`, player neutro extraído do player atual,
  sem autoplay, com velocidade, repetição e atribuição; exercícios acessíveis, feedback,
  transcrição opcional e conclusão. Extrair os campos visuais reaproveitáveis do exercício;
  os endpoints atuais não aceitam recursos sem vínculo com aula. Carregar a rota sob demanda.
- **LIST-08 · QA/infra:** migration expansiva e grants mínimos; teste da correção simples
  e múltipla, idempotência, versões, mídia indisponível e acessibilidade. Acrescentar dados
  nativos à exportação/exclusão e ao ensaio de backup/restore. Mídia começa somente online;
  se houver nova origem, CSP permite apenas o domínio revisado, sem curingas.

**Aceite:** três atividades publicáveis completas, com revisão editorial e licença
registradas; nenhuma nota inferida de site externo; acertos reproduzíveis no servidor;
reenvio não duplica tentativas; nenhuma regressão em aulas/players VOA; build, orçamento
de bundle e testes integrados aprovados. Até esse aceite, piloto fica desabilitado.
Sem material liberado, a sprint fica explicitamente pendente; o catálogo da 59 segue utilizável.

## Sprint 61 — Listening rápido: retomada, histórico e publicação validada

**Estado:** implementação técnica de LIST-09/10/11 preparada e validada em
ambiente sintético. LIST-12 tem testes e ensaio operacional; homologação manual
de conteúdo/áudio/direitos e publicação permanecem pendentes. Flags desativadas.
O [guia](listening_nativo.md) descreve os fluxos e o [relatório de execução](execucao_sprint61_2026-11-06.md)
registra evidências. Ordem restante: revisão humana → nova versão editorial aprovada
→ ensaio de release → publicação controlada. Nenhum novo nível ou lote de 31
atividades foi incluído implicitamente.

- **LIST-09 · Produto/frontend:** histórico e “Continuar de onde parei”, com posição de
  áudio, respostas e versão da sessão nativa. Exibir separadamente conclusão autodeclarada
  externa e resultado corrigido no app. Atalho opcional no painel Hoje não altera o cálculo
  de domínio de habilidades, revisão SM-2 ou certificado VOA.
- **LIST-10 · Backend/privacidade:** histórico paginado, primeira/última tentativa e
  estado de conclusão; isolamento por usuário, revisão de estado e snapshot/versionamento
  editorial. Consolidar exportação, exclusão, índices e recuperação das novas tabelas.
- **LIST-11 · PWA:** preservar rascunhos próprios e respostas pendentes por conta/versão;
  adaptar a fila de comandos sem assumir `lesson_id`. A interface distingue “Pendente de
  envio” de “Confirmado”. Atualizar aplicação, trocar conta ou abrir duas abas não pode
  perder respostas nem atribuí-las a outro aluno. Catálogo próprio pode ser cacheado;
  mídia e conteúdo do Test-English permanecem fora do cache.
- **LIST-12 · QA/operação:** E2E em Linux/WSL com stack isolada e mídia sintética local,
  incluindo escolha múltipla, retomada, duas abas, reconexão, exportação/exclusão e navegação
  acessível. Fazer homologação manual de áudio e conteúdo, medir bundle/latência e registrar
  release, desativação do módulo por flag e preservação dos dados.

**Aceite:** fluxo externo e piloto nativo validados em desktop/mobile; retomada fiel e
histórico separado; exportação/exclusão e recuperação completas; suíte existente sem
regressão. Atualizar README, guia do aluno e runbook com o que foi efetivamente publicado.
Expansão para outros níveis ou internalização das 31 lições exige novo lote editorial e
direitos correspondentes; não está implicitamente incluída no piloto de três atividades.

---

## Pontos fortes confirmados na auditoria de 04/11/2026

Posse de recurso no `WHERE` com 404 uniforme, Argon2id com hash dummy, token de acesso só em memória,
refresh httpOnly restrito, pipeline de áudio isolado, schema 100% alinhado aos models, contrato
OpenAPI idêntico ao código (77 rotas), imagens multi-stage com usuário sem privilégio em produção,
backup com manifesto e SHA-256, 456 de 457 testes de frontend passando no Windows, cobertura
de 93,6 % no backend e guarda de isolamento do banco de teste efetiva em cada conexão.
