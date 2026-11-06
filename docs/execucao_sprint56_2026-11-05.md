# Sprint 56 — migrations, grants e integridade

Código implementado e verificações locais executadas em 05/11/2026.
Próxima implementação por prioridade: **Sprint 57 — restante de PWA/offline**.
O módulo de listening segue planejado nas Sprints 59–61, após estabilização.

## Entregas

- **DB-01 / DB-06:** timeouts próprios de migration, validados e configurados
  na conexão; transação por revisão. CHECKs novos entram como NOT VALID e são
  validados numa revisão separada, liberando o lock forte entre as operações.
- **DB-05:** `ops/roles_policy.sql` como política operacional canônica; grants
  antigos nas migrations ficam como snapshots históricos. Aplicação atômica
  no EasyPanel e comparação de privilégios efetivos no laboratório. O reset
  revoga também ACLs de coluna, funções e concessões de PUBLIC.
- **DB-07:** downgrade de classificação recusa respostas acima de 200
  caracteres antes de alterar dados; removido o truncamento. A exceção à
  imutabilidade de migrations antigas está documentada e não muda o upgrade.
- **DB-11 / DB-12:** convenção de nomes no metadata, preservando nomes
  históricos; CHECKs para tamanho de transcrição, palavras temporizadas,
  respostas de diálogo e feedback assistido.
- **DB-13:** validação de faixas do catálogo. A sobreposição da Aula 40 entre
  31–40 e 40–44 é uma revisão intencional e agora exige anotação explícita,
  coerente com o checkpoint. IDs, faixas publicadas e conteúdo foram preservados.
- **DB-14:** decisão de risco restrita a credenciais públicas de laboratórios
  descartáveis e isolados, sem autorização para reutilização em produção.
- **OPS-09:** JWT com `kid`, chave ativa e anterior com prazo UTC absoluto;
  tokens legados sem kid continuam verificáveis na transição. Refresh emite
  com a chave ativa sem estender a validade original da família.
- **Eventos:** IDs e sequências de review_event, study_activity_event e
  study_active_interval, incluindo a FK event_id, passam a bigint. O downgrade
  recusa valores ou sequências que não caibam em integer.

Head Alembic: **`c56b1c8d9006`**, precedido por `a56b1c8d9004` e `b56b1c8d9005`.
Procedimento em [migrations, grants e JWT](migrations_grants_jwt_sprint56_2026-11-05.md).

## Evidências e correções de integração

- PostgreSQL 16 descartável: upgrade até o head, `alembic check` sem diferenças
  e seed das 82 aulas aprovados. Banco com identidade de teste, rede interna,
  PGDATA em tmpfs, sem portas publicadas nem volumes persistentes.
- Testes novos cobrem a janela JWT, kid desconhecido/algoritmo recusado,
  refresh HTTP preservando o prazo, timeout real com a tabela de versão
  bloqueada, faixas sobrepostas, downgrade sem truncamento, CHECKs com dados
  históricos inválidos e bigint preservando referências e recusando overflow.
- Suíte completa do backend: **1.474 aprovados de 1.481**, cobertura **94,04%**
  (piso 90%). Sete falhas: duas expectativas com head antigo, descrição OpenAPI
  desatualizada desde a Sprint 52, diagnóstico de locks ausente no laboratório
  e três falhas de sessão causadas por recuos de cerca de 25 segundos no relógio
  da VM, confirmados nos timestamps dos requests.
- Após ajustar as expectativas, o contrato e a configuração do laboratório,
  a rechecagem dos dez arquivos afetados teve **86 aprovados de 87**; os sete
  casos anteriores passaram. Outro teste sofreu recuo de relógio e passou
  isoladamente (**1/1**). Não se declara uma execução integral verde: a
  estabilização do relógio/portabilidade permanece no escopo da Sprint 58.
- Dois testes antigos foram alinhados: exclusão de diálogo agora confere a
  remoção do áudio entregue na Sprint 52; auditoria de arquivo usa tamanhos
  diferentes para detectar alteração sem depender da resolução do relógio.
  O OpenAPI e o comentário gerado em TypeScript foram sincronizados, sem
  mudança de payload ou assinatura de endpoint nesta sprint.
- Suíte operacional Linux: **379 descobertos, 371 aprovados, 8 opcionais
  ignorados**. O novo ensaio opt-in foi executado separadamente com imagem de
  produção: `aulas-dr-policy56-9e1589aaa071`, **21,698 s**. Comparação de grants
  aprovada; concessão indevida por coluna detectada; falha durante aplicação
  preservou a política anterior; reaplicação correta removeu a divergência.
  A pipeline de recovery passa a executar esse ensaio.
- Build da imagem de produção da API aprovado. Ruff, mypy no Linux (**108
  módulos de backend e 51 operacionais**), shellcheck, actionlint e validação
  dos Compose de produção local/EasyPanel com valores sintéticos aprovados.

## Limites e próximo passo

Não houve commit, push, deploy, rotação de segredos reais ou alteração em
banco de estudo/produção. Playwright completo e pipeline remota não executados.

Antes da publicação, ensaiar com backup e clone representativo: validação de
CHECK pode recusar dados históricos; bigint pode reescrever tabelas e índices.
Medir locks e duração. Como cada revisão confirma separadamente, uma falha
posterior exige conferir a versão aplicada antes de retomar. Nunca truncar
conteúdo para forçar a migration nem fazer downgrade automático.

A próxima sprint trata fila offline, telas Hoje/Mapa, gravação de posição de
áudio, exportação do Caderno e orçamento/chunks do frontend. A correção urgente
FE-01 já implementada deve ser preservada.
