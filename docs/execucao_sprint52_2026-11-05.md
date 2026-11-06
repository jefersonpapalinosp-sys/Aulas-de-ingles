# Sprint 52 — privacidade, retenção e exclusão

Implementação e validações locais concluídas em **05/11/2026**. Escopo: SEC-03,
DB-04, DB-02, DB-03 e FE-02. Próxima prioridade: Sprint 53, worker de assistência
e diálogo. As Sprints 59–61 de listening continuam planejadas.

## Comportamento entregue

- Excluir um diálogo remove também seus registros de gravação. Um trigger
  registra a chave opaca do arquivo na mesma transação; rollback mantém a
  gravação e não deixa tarefa de limpeza. A API tenta remover os arquivos após
  o commit. Falhas permanecem na fila para o worker, sem reabrir o diálogo.
- Áudios de diálogo seguem o `expires_at` do turno, calculado na admissão com
  `ASSIST_RETENTION_DAYS` (padrão: **30 dias**). A manutenção remove os registros
  vencidos e enfileira arquivos, mesmo com `MAINTENANCE_CLEANUP_ENABLED=false`.
  Metadados de prática permanecem. A política de shadowing não foi alterada.
- A mesma varredura recolhe gravações antigas com `origin='dialogue'` sem turno.
  O lote é limitado a 500 e aceita ensaio seco. Upload e admissão permanecem
  transacionais, portanto um upload ainda não confirmado não aparece como órfão.
- A fila `dialogue_audio_deletion` guarda somente chave opaca, número de
  tentativas, próxima tentativa e código de falha. Usa `SKIP LOCKED`, remoção
  idempotente e até dez tentativas com espera crescente. Na exclusão de conta,
  uma tarefa já associada ao recibo evita enfileirar a mesma chave novamente.
- Exclusão de conta confirmada encerra a sessão e limpa os dados daquela conta
  no navegador: rascunhos, fila IndexedDB e recibos, posições, progresso local e
  gravação temporária. O adaptador também remove entradas legadas daquela conta
  e mantém o tombstone contra reimportação. Outras contas são preservadas.
- Falha de IndexedDB não impede tentar remover os demais dados. Falha de
  limpeza ou remoção do perfil produz aviso explícito após encerrar a sessão;
  não informa sucesso completo nem pede novo DELETE de uma conta já removida.
- Modelo de ameaças corrigido para nove rotas e exclusão do diálogo inteiro.

## Schema e aplicação operacional

Novas revisões, sem modificar migrations publicadas:

1. `d52a1b8c9001`: fila, trigger de exclusão e função de retenção de áudio.
2. `e52a1b8c9002`: cinco índices criados com `CONCURRENTLY`: FKs
   `study_active_interval.event_id`, `review_event.item_id` e
   `practice_session.source_session_id`; parcial de texto pendente de anonimização
   em `dialogue_turn(expires_at,id)`; parcial dos áudios `origin='dialogue'`.

A migration de índices aceita repetição após criação parcial e recusa índice
inválido, incompleto ou com colunas/predicado divergentes. Inspecionar o artefato
e tratar somente o índice afetado antes de repetir. A fila recusa downgrade com
tarefas pendentes, inclusive as que esgotaram tentativas. Áudios apagados não são
recuperáveis por downgrade.

Antes da publicação: backup validado, ensaio em clone, migration pelo papel
migrador e atualização de API/worker/web conforme a Sprint 43. O arquivo
`ops/roles_policy.sql` acompanha os grants da migration. O worker pode executar
a função limitada e concluir tarefas; o trigger cria tarefas com direitos do
owner e `search_path` fixo. Execução pública das funções foi revogada.

Verificar `dialogue_audio_pending` e `dialogue_audio_failed` nos contadores de
manutenção do heartbeat e das métricas privadas. Falhas ao atingir dez tentativas
exigem corrigir armazenamento/permissões e reagendar somente as tarefas afetadas
(`attempt_count=0`, `next_attempt_at=now()`, `last_error_code=NULL`). Não apagar a
fila para zerar contadores. O prazo depende do worker e da disponibilidade do
armazenamento; atraso não é tratado como remoção concluída. Rollback da aplicação
precisa manter um worker capaz de concluir essa fila.

O teste local não comprova permissões, desempenho ou duração de locks da base
pública. Esses aceites e a publicação continuam pendentes.

## Evidências

- **103 cenários distintos de backend aprovados em Linux**, selecionando
  exclusão, retenção, migrations, índices, diálogo/posse, worker, saúde,
  isolamento do banco e referência editorial ao novo head.
- Exclusão via API de conta com **10 mil eventos e 10 mil intervalos** em
  **0,534 s** no ensaio registrado; `statement_timeout=30s` confirmado e ambas
  as tabelas verificadas sem registros restantes. É evidência sintética local.
- Testes confirmam ausência de arquivo e registro após excluir diálogo,
  isolamento entre contas, rollback, retry após falha, limite de tentativas,
  retenção vencida/vigente, remoção de órfãos e ausência de tarefa duplicada na
  exclusão de conta.
- **33 testes de frontend** aprovados: sessão real, Meus dados e inventário,
  incluindo confirmação antiga recebida após troca de conta.
- **5 testes Playwright/Chromium** aprovados: exclusão com limpeza de localStorage
  e IndexedDB verificada após navegar novamente, preservação de outra conta,
  falha de IndexedDB, falha de remoção do perfil, senha incorreta e rate limit.
  Os dois últimos constituem cenários separados. API sintética; componentes e
  armazenamento reais. Não equivale ao E2E completo da stack pública.
- Ruff, mypy (108 módulos backend), ESLint, TypeScript, build e sincronismo do
  contrato OpenAPI aprovados. `alembic check`: nenhuma operação nova detectada
  entre os modelos e o schema migrado.
- Bundle gzip: inicial **129,3/132,0 KiB**, base **183,9/184,0 KiB**, conjunto
  **190,8/192,0 KiB**. Tetos preservados; permanece o aviso preexistente do ciclo
  de chunks `lesson-study → writing → lesson-study`.

Uma regressão de posição inválida falhou no primeiro lote porque o relógio da
VM Docker recuou aproximadamente 22 segundos entre registro e criação de diálogo,
tornando o JWT recém-emitido ainda não válido. Os quatro casos de posição passaram
na repetição, sem alterar validação de tokens ou enfraquecer o teste.

Banco usado: projeto descartável `aulas-ingles-sprint52-test`, papel limitado
`aulas_test`, marcador de segurança e migrations/seed por `app.testing`. Nenhuma
migration ou limpeza foi executada na base de estudo ou em produção. Containers
e rede de teste encerrados; volume sintético preservado. Sem commit, push ou deploy.
