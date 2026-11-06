# Fila durável da assistência de transcrição

Data: 8 de outubro de 2026  
Backlog: item 4 da fila de fechamento

## Resultado

O processamento de transcrição deixou de depender de `BackgroundTasks` do processo HTTP. A API
agora persiste o job e responde `202 Accepted`; um serviço `worker` separado consome a fila no
PostgreSQL. Reiniciar a API ou o worker não perde a solicitação nem o áudio.

O feedback assistido de escrita continua síncrono porque não possui entidade de job nem depende
de processamento posterior. Ele mantém timeout, fallback determinístico e gate humano próprios.

## Garantias implementadas

- `FOR UPDATE SKIP LOCKED` impede dois workers de reivindicarem o mesmo job;
- `attempt_count` e `max_attempts` limitam o total de tentativas;
- `next_attempt_at` implementa backoff exponencial entre falhas transitórias;
- `processing_started_at` registra a última renovação da posse desde a Sprint 53;
  permite retomar jobs abandonados após reinício ou timeout;
- `idempotency_key` é criada uma vez, persistida e enviada como `Idempotency-Key` em todo retry;
- resultados só são gravados se `status` e número da tentativa ainda pertencerem ao worker;
- áudio ausente é falha terminal; indisponibilidade e resposta inválida têm retry limitado;
- conteúdo do aluno, áudio e exceções do provedor continuam fora dos logs.

## Configuração

| Variável | Padrão | Função |
|---|---:|---|
| `ASSIST_JOB_MAX_ATTEMPTS` | `3` | máximo de chamadas por job |
| `ASSIST_JOB_RETRY_BASE_SECONDS` | `5` | base do backoff exponencial |
| `ASSIST_JOB_STALE_SECONDS` | `120` | tempo para considerar um worker interrompido |
| `ASSIST_WORKER_POLL_SECONDS` | `1` | intervalo quando a fila está vazia ou pausada |

Desde a Sprint 53, `ASSIST_JOB_STALE_SECONDS` deve ser pelo menos
`2 * ASSIST_TIMEOUT_SECONDS + 15`: um diálogo de áudio pode fazer STT e diálogo.
A posse é renovada a cada `min(10s, stale/3)`, com piso de 50 ms; o heartbeat continua
durante a chamada externa. A finalização de diálogo verifica estado, tentativa e
expiração antes de gravar resultado, custo e evidências. Desligar
`ASSISTED_FEATURES_ENABLED` pausa novas solicitações e o consumo da fila sem apagar jobs.

SIGTERM/SIGINT impedem nova iteração e deixam a tentativa ativa concluir. O Compose
usa `WORKER_STOP_GRACE_PERIOD=150s`; ao aumentar timeouts, ajustar essa janela para
cobrir ambas as chamadas e a persistência. Uma parada forçada continua deixando a
tentativa registrada, sujeita à retomada por stale e ao limite de tentativas.

API e worker checam o orçamento declarado de conexões no boot. Declarar o total
de processos em `DATABASE_PROCESS_BUDGET`, incluindo réplicas. O cálculo por
processo multiplica esse total pelo seu pool máximo; o processo com o maior pool
fornece o teto conservador para pools diferentes. A comparação desconta conexões
reservadas do PostgreSQL e `DATABASE_CONNECTION_RESERVE` (padrão 10).

## Operação

Os arquivos Compose de desenvolvimento e produção possuem um serviço `worker` com o mesmo código,
banco e volume de gravações da API. Para consumir somente uma pendência durante diagnóstico:

```bash
make assist-worker
```

O comando equivalente no container é:

```bash
python -m app.cli assist-worker --once
```

## Limite de idempotência

O backend garante uma chave estável e não grava duas vezes o resultado da mesma tentativa lógica.
A deduplicação de processamento e cobrança fora da aplicação depende de o gateway contratado
respeitar o header `Idempotency-Key`; isso precisa constar na homologação do fornecedor.

## Evidência de aceite

- migration cria e restringe os campos operacionais sem remover jobs existentes;
- teste de dois workers concorrentes comprova uma única reivindicação;
- teste de retry comprova backoff, limite e reutilização da chave;
- teste de retomada converte job `processing` abandonado em nova tentativa;
- falha final preserva áudio e autoavaliação;
- feature flags dos arquivos de exemplo continuam desligadas.
