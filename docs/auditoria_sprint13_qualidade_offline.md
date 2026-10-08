# Auditoria da Sprint 13 — qualidade, offline e instalação

Data: 7 de outubro de 2026

## Resultado

A aplicação pode ser instalada como PWA e mantém o shell e o conteúdo textual público já
visitado quando a conexão cai. Tentativas objetivas feitas offline ficam em uma fila local,
vinculada ao ID da conta, e são enviadas com a mesma chave idempotente depois que a sessão é
renovada. Trocar de conta não envia itens de outro aluno.

O service worker não armazena endpoints autenticados, gabaritos, progresso, escrita, speaking
ou revisão. Áudio e vídeo também são excluídos do cache; a mídia oficial continua dependente da
origem enquanto não houver autorização e política de armazenamento específicas.

## Matriz offline

| Recurso | Estratégia | Motivo |
|---|---|---|
| HTML, JS, CSS, manifesto e ícone | precache/cache-first | abrir a interface instalada |
| `GET /api/lessons`, aula por número, exercícios e vocabulário | network-first, fallback recente | conteúdo público textual |
| tentativa de exercício | fila local + POST idempotente | não perder a resposta |
| autenticação e dados da conta | rede; perfil mínimo só para identificar a sessão offline | não persistir token |
| gabarito, dicas, progresso, revisão, escrita e speaking | somente rede | conteúdo privado ou mutável |
| áudio e vídeo | somente rede | licença, origem e volume de armazenamento |

Limites da fila: 100 tentativas recentes por navegador. A resposta digitada é necessária para
a sincronização e permanece no armazenamento local do navegador até a confirmação da API.

## Auditoria WCAG 2.2 AA — escopo do frontend

| Área | Evidência | Resultado |
|---|---|---|
| 1.3.1 estrutura | `nav`, `main`, títulos, listas, tabelas e `fieldset/legend` semânticos | aprovado |
| 1.4.3 contraste | tokens escuros/claros consistentes e estados não dependem apenas de cor | aprovado por inspeção dos tokens; manter regressão visual |
| 1.4.10 reflow | layout colapsa abaixo de 860 px; E2E também roda em Pixel 5 | aprovado |
| 2.1.1 teclado | controles nativos, foco visível e exercícios de ordenar acionáveis por botão | aprovado |
| 2.4.1 blocos | link “Pular para o conteúdo” aparece ao receber foco | aprovado |
| 2.4.6 títulos/rótulos | campos e ações têm nome visível ou `aria-label` contextual | aprovado |
| 3.3.1 erros | mensagens usam texto e `role="alert"`/`role="status"` | aprovado |
| 4.1.3 status | conexão, fila, sincronização e feedback usam região viva | aprovado |

Esta é uma auditoria técnica do código e dos fluxos automatizados, não uma certificação. Antes
de publicação pública, repetir uma rodada manual com VoiceOver/TalkBack, zoom a 200% e contraste
forçado do sistema. A execução e suas evidências são acompanhadas em
`docs/validacao_manual_acessibilidade_2026-10-08.md`.

## Performance

O gate `npm run check:budget`, executado depois do build, falha quando:

- qualquer bundle JavaScript ultrapassa 140 KiB gzip;
- qualquer CSS ultrapassa 15 KiB gzip;
- a soma de JavaScript e CSS ultrapassa 170 KiB gzip.

Medição desta entrega: **117,5 KiB JS + 7,7 KiB CSS = 125,2 KiB gzip**.

## Telemetria e privacidade

O backend registra somente timestamp, nível, logger, mensagem técnica, request ID, método,
caminho sem query string, status e duração. Corpo, resposta digitada, e-mail, cabeçalho de
autorização, áudio e query string não são coletados. Um teste de regressão envia valores
sentinela nesses campos e confirma que nenhum aparece no JSON do log.

## Evidência automatizada

- 119 testes backend, incluindo privacidade da telemetria;
- 62 testes frontend, incluindo fila, idempotência, isolamento por usuário e sessão offline;
- 10 cenários E2E em Desktop Chrome e Pixel 5 (20 execuções);
- cenário PWA: visita online, reload offline, resposta na fila e sincronização ao reconectar;
- ESLint, TypeScript, build e orçamento de bundle no CI.
