# Sprint 53 — concorrência e continuidade do worker

Implementação e validações locais concluídas em **05/11/2026**. Escopo: BE-02,
BE-04, BE-05, DB-08 e BE-10/DB-09. Próxima prioridade: Sprint 54, backup e
recuperação. Listening permanece nas Sprints 59–61.

## Entrega

- O worker carrega os dados necessários e libera a conexão antes das chamadas
  externas de STT e diálogo. A chamada síncrona de diálogo roda com
  `asyncio.to_thread`; somente a gravação usa lock do diálogo. O caminho Roteiro
  mantém admissão e resposta na transação da API, sem provedor.
- Finalização de diálogo trava primeiro o diálogo e depois o job, seguindo a
  ordem de exclusão. Confere `status='processing'`, número da tentativa e
  expiração antes de gravar texto, custo ou evidência. Uma resposta atrasada
  não altera a tentativa que a substituiu nem recria dados apagados.
- A posse da tentativa é renovada enquanto o provedor trabalha, em transações
  curtas. `processing_started_at` passa a representar essa renovação. Ao perder
  a posse, o consumidor descarta o resultado. O heartbeat continua a cada dez
  segundos durante a espera; tarefas auxiliares são aguardadas no encerramento.
- O boot recusa `ASSIST_JOB_STALE_SECONDS < 2 * ASSIST_TIMEOUT_SECONDS + 15`.
  A margem contempla as duas chamadas do diálogo com áudio. O teste também
  força settings legadas com `stale == timeout` e confirma que a renovação
  impede uma segunda chamada por outro consumidor.
- Erro inesperado de um job é terminal com `unexpected_worker_error`. Erros
  inesperados da iteração são registrados sem texto da exceção e recebem espera
  limitada; o consumidor continua. Cancelamento não é engolido. Limpeza de
  arquivos e processamento de jobs recebem trabalho na mesma iteração.
- SIGTERM/SIGINT solicitam parada após a tentativa ativa. Compose passa a usar
  janela padrão de 150 segundos. API e worker validam orçamento de conexões no
  boot; sessões usam `idle_in_transaction_session_timeout=60000`.
  Compose de produção/EasyPanel/E2E declara três processos (dois Uvicorn e um
  consumidor); desenvolvimento declara dois. Réplicas adicionais exigem ajuste.
- PostgreSQL recebe `log_lock_waits=on` e limite de transação ociosa. Os limites
  de parâmetros de logs normal e de erro ficam em zero, para não acrescentar
  valores de parâmetros aos diagnósticos. A semântica está na
  [documentação do PostgreSQL 16](https://www.postgresql.org/docs/16/runtime-config-logging.html#GUC-LOG-PARAMETER-MAX-LENGTH).
- Corrigida a montagem de voz do worker no EasyPanel e na produção local com
  papéis separados: a fila de exclusão das Sprints 40/52 precisa remover arquivos.
  O volume permite escrita; o filesystem raiz e as capacidades restritas do
  serviço público continuam configurados como antes. Os testes Compose verificam
  a permissão necessária no volume de voz.

## Índices e medição

Nova revisão `f53a1b8c9003`, filha de `e52a1b8c9002`, sem alterar migrations
publicadas. Cria com `CONCURRENTLY`:

- `(status,next_attempt_at,id) WHERE status='queued'`, para claim ordenado;
- `(processing_started_at,id) WHERE status='processing'`, para recuperação.

Depois remove os índices anteriores de `(kind,status,next_attempt_at)`, `status`
e `next_attempt_at`. Índices de FKs e de retenção permanecem. Preflight recusa
artefato inválido/divergente; repetição aceita etapas já concluídas. Downgrade
recria os três índices anteriores antes de remover os novos.

Antes da migration, o benchmark criou uma tabela temporária com 200 mil jobs
sintéticos, dos quais mil estavam na fila e cem em processamento. Comparou cinco
execuções do SELECT com lock e mediana:

| Configuração | Mediana | Espaço dos índices comparados |
|---|---:|---:|
| Três índices anteriores | 29,705 ms | 15.917.056 bytes |
| Parcial de claim | 0,045 ms | 57.344 bytes |

O plano deixou de ordenar adicionalmente e passou a usar o índice parcial.
O espaço da segunda linha mede somente o índice de claim; não inclui o índice
de recuperação. É uma distribuição sintética favorável à distinção entre fila
e histórico, não uma previsão de desempenho da produção.

## Validação local

- **151 cenários distintos de backend** aprovados em Linux: diálogo, voz,
  aprendizado, custos, reprise, manutenção, CLI, saúde, configuração, migração,
  posse, duas execuções concorrentes e benchmark.
- **19 testes de EasyPanel** aprovados em Linux; **5 testes Compose** aprovados,
  incluindo diagnóstico do PostgreSQL, janela de parada e volume de voz.
- **1 ensaio Docker de parada real** aprovado: após o marcador de chamada ao
  provedor sintético, `docker stop --time 15` encerrou o worker com exit 0;
  o primeiro job ficou `completed/attempt_count=1` e o segundo `queued/0`.
  O fixture restringe o worker à sua conta sintética e remove seus dados ao final.
  O CI passa a executar esse ensaio após o E2E, com o worker regular parado.
- Ruff e mypy do backend aprovados; contratos Compose e estrutura do workflow
  verificados. `alembic check` valida alinhamento entre modelos e schema.

Um cenário de voz apresentou 401 após a VM Docker recuar aproximadamente 25
segundos, invalidando temporariamente um JWT recém-emitido. O cenário passou na
repetição sem relaxar autenticação. O teste de permissões 0600 de configuração
privada foi executado no Linux; o filesystem Windows não oferece essa semântica.

## Publicação pendente

Migrations rodaram somente no projeto descartável `aulas-ingles-sprint53-test`,
com papel limitado e marcador de segurança. Antes de publicar: backup validado,
ensaio em clone e migration pelo migrador conforme a Sprint 43. Conferir pools,
total de réplicas, reserva de conexões e janela de parada antes de recriar os
serviços. Com o boot novo, orçamento incompatível ou banco inacessível impede
inicialização. Na produção com papéis separados, validar remoção de áudio com
o UID e volume reais no clone.

O ensaio local usou imagem Python já disponível; não executou a pipeline remota
nem o E2E completo da stack pública. A deduplicação de cobrança fora da aplicação
continua dependendo da política de idempotência do provedor; lease e guarda de
finalização protegem o estado local. A janela de parada deve acompanhar timeouts
customizados; SIGKILL não permite concluir uma chamada em andamento.

Containers e rede do ensaio encerrados, volume sintético preservado. Nenhum
commit, push, deploy ou alteração de banco de estudo/produção foi realizado.
