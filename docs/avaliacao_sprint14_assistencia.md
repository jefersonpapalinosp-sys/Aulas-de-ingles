# Avaliação da Sprint 14 — assistência opcional

Data: 7 de outubro de 2026

## Resultado

A transcrição de fala e a análise aberta de escrita foram adicionadas como experimentos
opcionais. Elas ficam **desativadas por padrão**, exigem configuração explícita do gateway e
nunca substituem os recursos locais: a gravação, a autoavaliação oral, o rascunho e a rubrica
determinística continuam disponíveis quando o provedor falha ou a cota termina.

Na interface, todo resultado assistido é identificado como automatizado e em avaliação. A
confiança média e a confiança por palavra aparecem na transcrição; valores abaixo de 75% são
destacados e não são apresentados como uma nota absoluta de pronúncia. O aluno pode informar
se o resultado foi útil e excluir somente a transcrição, mantendo seu áudio.

## Ativação e configuração

Variáveis disponíveis em `.env.example` e `.env.prod.example`:

| Variável | Padrão | Função |
|---|---:|---|
| `ASSISTED_FEATURES_ENABLED` | `false` | chave geral dos experimentos |
| `ASSIST_TRANSCRIPTION_URL` | vazio | gateway de speech-to-text |
| `ASSIST_WRITING_URL` | vazio | gateway de análise de escrita |
| `ASSIST_PROVIDER_KIND` | `gateway` | `gateway` externo ou `ollama` local |
| `ASSIST_PROVIDER_NAME` | `external` | identificação exibida e persistida |
| `ASSIST_PROVIDER_TOKEN` | vazio | bearer token enviado ao gateway |
| `ASSIST_OLLAMA_BASE_URL` | host Docker, porta 11434 | API local do Ollama |
| `ASSIST_OLLAMA_MODEL` | `qwen2.5:7b` | modelo local para feedback de escrita |
| `ASSIST_DAILY_QUOTA` | `5` | chamadas assistidas por aluno e por dia |
| `ASSIST_RETENTION_DAYS` | `30` | retenção dos resultados de transcrição |
| `ASSIST_TIMEOUT_SECONDS` | `20` | limite de espera por chamada |

Em produção, os gateways configurados precisam usar HTTPS e possuir token. Uma URL pode ficar
vazia para habilitar apenas uma das modalidades. O endpoint autenticado `GET /api/assist/status`
informa disponibilidade, cota usada/restante, retenção e custo acumulado no dia.

Quando `ASSIST_PROVIDER_KIND=ollama`, somente a assistência de escrita usa a API local
`/api/chat`; `ASSIST_WRITING_URL` e token permanecem vazios. O backend exige que o Ollama fique
em `localhost`, `127.0.0.1` ou `host.docker.internal` em produção. O modelo recebe um JSON Schema,
temperatura zero e instrução para não atribuir nota nem repetir o texto completo. Como a API não
fornece probabilidade calibrada para esse feedback, a confiança é registrada conservadoramente
como `0.5`, mantendo visível o aviso de baixa confiança.

Antes da chamada, a rubrica determinística é calculada no servidor. O Ollama recebe somente os
checks com `passed: false`; o schema permite apenas os códigos desses checks e a resposta é
filtrada novamente no backend. Critérios inventados e comentários sobre checks aprovados são
descartados. Quando não há pendências objetivas, o servidor devolve uma confirmação local e não
chama o modelo. O provedor continua sem poder alterar `ready`, progresso ou nota.

## Contrato do gateway

O backend usa HTTP simples e não depende do SDK de um fornecedor. O gateway de transcrição
recebe o áudio bruto, preserva seu `Content-Type` e autentica por `Authorization: Bearer` quando
há token. A resposta esperada é:

```json
{
  "text": "A taxi is faster than a bus.",
  "words": [
    {"text": "A", "start_ms": 0, "end_ms": 90, "confidence": 0.98}
  ],
  "cost_microusd": 1200
}
```

O gateway de escrita recebe JSON com `text` e `rubric` e responde:

```json
{
  "summary": "O texto comunica a ideia com clareza.",
  "suggestions": [
    {"criterion": "comparatives", "message": "Revise o uso de faster than."}
  ],
  "confidence": 0.86,
  "cost_microusd": 900
}
```

Campos textuais, quantidades e valores de confiança são validados e limitados antes de serem
persistidos. Falhas viram códigos técnicos como `provider_unavailable` e
`invalid_provider_response`; o conteúdo do aluno e as respostas externas não entram nos logs.

## Privacidade, consentimento e retenção

- O áudio só chega ao servidor após o consentimento já exigido no fluxo de speaking.
- Pedir transcrição é uma segunda ação explícita; salvar o áudio não chama o provedor.
- A análise aberta de escrita possui opt-in próprio e desmarcado por padrão.
- Resultados de transcrição expiram conforme `ASSIST_RETENTION_DAYS` e também podem ser
  excluídos imediatamente sem apagar a gravação.
- Excluir a gravação exclui em cascata a transcrição relacionada.
- Feedbacks, transcrições, palavras, áudio e texto não entram na telemetria técnica.
- A exportação pessoal identifica o modo, o fornecedor, a confiança, o custo e a avaliação
  humana dos resultados assistidos.

O gateway externo precisa ter sua própria base legal, contrato de tratamento, região e política
de retenção avaliados antes de receber dados reais. A aplicação não presume que um provedor
configurado atende a esses requisitos.

## Fallback e continuidade

| Situação | Comportamento |
|---|---|
| feature flag desligada | mostra que o experimento está indisponível; recursos locais continuam |
| cota diária atingida | não chama o gateway; a rubrica de escrita continua sendo calculada |
| timeout ou resposta inválida | registra somente o código técnico e preserva áudio/rascunho |
| baixa confiança | mostra alerta e palavras abaixo de 75%; não transforma o valor em nota |
| exclusão da transcrição | remove resultado assistido, mas mantém a produção oral |

A transcrição usa uma fila durável no PostgreSQL e um processo worker separado da API. O worker
reivindica jobs com `FOR UPDATE SKIP LOCKED`, retoma registros `processing` que excederam o
timeout, limita tentativas e aplica backoff exponencial. Uma chave persistida é enviada no header
`Idempotency-Key` em todas as tentativas do mesmo job, permitindo deduplicação pelo gateway.
Resultados atrasados só são gravados se o worker ainda possuir o número daquela tentativa.

## Gate de avaliação humana

O recurso continua fora da liberação ampla. A ativação para mais usuários só deve ocorrer após
uma rodada controlada, separada por modalidade, com no mínimo 30 resultados avaliados por
pessoas e os seguintes critérios:

- pelo menos 80% dos resultados marcados como úteis;
- taxa de falha técnica inferior a 5%;
- revisão manual sem feedback discriminatório, inseguro ou apresentado como certeza indevida;
- confirmação de que baixa confiança e automação são compreendidas pelos participantes;
- nenhum incidente de privacidade e custo dentro do orçamento definido para o piloto.

Os botões “Foi útil” e “Não foi útil” alimentam `human_rating`. Custo é persistido em
microunidades de dólar para evitar arredondamento e somado no status diário. Esses dados apoiam
a decisão, mas não autorizam automaticamente a feature flag.

### Gate operacional acrescentado no fechamento

O comando `python -m app.cli assist-gate` transforma os critérios acima em uma decisão que falha
fechado, separada para `writing` e `transcription`. Ele combina somente métricas agregadas do
banco com um manifesto local de homologação baseado em
`config/assist-provider-review.example.json`.

O relatório não contém texto, áudio, transcrição, e-mail nem identificador de aluno. Mesmo quando
todos os critérios passam, o comando apenas retorna aprovação; ele não liga
`ASSISTED_FEATURES_ENABLED` automaticamente. A decisão de ativar continua sendo uma mudança
operacional explícita e revisável.

## Evidência automatizada

- 151 testes backend, incluindo fila, concorrência, retomada, gateway, cotas e preservação;
- 67 testes frontend, incluindo estado de retry, opt-in, automação, baixa confiança e avaliação;
- 10 cenários E2E em Desktop Chrome e Pixel 5, totalizando 20 execuções aprovadas;
- contrato OpenAPI e tipos TypeScript regenerados;
- migração aplicada e comparada aos modelos sem operações pendentes;
- produção local avançou de `d79a1c35b681` para `e91c4a7d2b30`, preservando 166 usuários,
  14 feedbacks de escrita e 661 itens de revisão existentes;
- feature flags desligadas nos exemplos e nos dois arquivos Compose.
