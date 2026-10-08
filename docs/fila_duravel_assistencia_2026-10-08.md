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
- `attempt_count` e `max_attempts` limitam o total de chamadas;
- `next_attempt_at` implementa backoff exponencial entre falhas transitórias;
- `processing_started_at` permite retomar jobs abandonados após reinício ou timeout;
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

`ASSIST_JOB_STALE_SECONDS` não pode ser menor que `ASSIST_TIMEOUT_SECONDS`. Desligar
`ASSISTED_FEATURES_ENABLED` pausa novas solicitações e o consumo da fila sem apagar jobs.

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
