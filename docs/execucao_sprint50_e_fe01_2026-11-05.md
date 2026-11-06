# Execução — Sprint 50 e atualização urgente da PWA

Início: **05/11/2026**. Base: `012e54a`. Código da Sprint 50 e correção FE-01
implementados e validados localmente; publicação e aceite operacional ainda pendentes.
A ordem definida por prioridade está no
[plano das Sprints 50–61](plano_sprints_50_58_auditoria_2026-11-04.md).

## Escopo deste incremento

- **OPS-01:** workflow preserva códigos de falha e publica os relatórios no resumo;
  usa Bash explícito. Gate privado também executa quando o probe falha, salvo cancelamento.
- **INF-01, parte de código:** origem configurada sem token operacional reprova o job;
  runner de cron preserva falhas e é silencioso quando saudável. Modelo de cron e de
  configuração privada incluídos; nada instalado em VM ou no GitHub neste incremento.
- **BE-03:** falha de manutenção não interrompe heartbeat nem processamento;
  novas tentativas respeitam o intervalo configurado e não falsificam a última manutenção
  concluída. Cancelamento continua propagando.
- **INF-04/INF-12:** rotação de logs, limites de processos e memória compartilhada do
  PostgreSQL nos composes; validação antes de aplicar em ambientes persistentes.
- **INF-11:** liveness do processo no healthcheck dos containers da API; readiness de
  banco/schema continua sendo verificada pelos probes e pelo procedimento de release.
  O deploy público verifica readiness interna em até seis tentativas, inclusive
  com `--skip-smoke`, antes de declarar sucesso.
- **FE-01 antecipada:** atualização solicitada pelo aluno ativa o worker novo antes
  da recarga e preserva rascunhos/fila local. Versão já instalada pode ser ativada
  offline; a interface permanece montada durante a transição. O helper integra
  o shell inicial para não depender de download de outro chunk na recuperação.
  A antecipação decorre do cutover previsto para 13/11/2026.
  No primeiro rollout, salvar pendências e fechar todas as abas/janelas uma vez
  ainda é necessário para receber o próprio bundle corrigido. As atualizações
  seguintes usam o botão novo; testes de interoperabilidade não comprovam entrega
  retroativa de código a uma aba que continua executando o bundle antigo.

## Validação

- **Backend:** 38 testes passaram, incluindo manutenção, continuidade do worker,
  healthchecks e métricas operacionais.
- **Operações:** 86 testes passaram em container Linux descartável, sem rede e
  com código somente para leitura. Cobrem propagação dos códigos 0/1/2 no workflow,
  alerta de cron, gates e retries de deploy, probes e regressões de rollout/EasyPanel.
- **Compose:** quatro testes de contrato passaram; a configuração renderizada
  comprova limites de PID/logs, shared memory e liveness. O PostgreSQL de ensaio
  confirmou `pids_limit=256`, `shm_size=256m` e logs de `10m` com três arquivos.
- **Análise estática:** Ruff nas alterações do backend e em `ops/`; mypy sem erros
  em 107 módulos de backend e 41 módulos operacionais, com plataforma-alvo Linux.
- **Frontend:** 44 testes passaram em cinco arquivos focados na atualização,
  recuperação, resposta 428 e worker; ESLint, TypeScript e build Vite passaram.
- **PWA em navegador:** dois testes Playwright/Chromium passaram com servidor
  sintético. Executam o helper real contra worker legado sem handler de ativação,
  verificam duas abas, recarga somente da solicitante, preservação de localStorage
  e IndexedDB e recuperação offline após instalação com shell incompatível.
- **Bundle (gzip):** inicial **129,0/132,0 KiB**, base **183,5/184,0 KiB**,
  diálogo **7,0/8,0 KiB**, conjunto **190,5/192,0 KiB**. Tetos preservados;
  agrupamento de módulos de caderno/histórico/paginação reduziu overhead.
  O aviso preexistente de chunk circular `lesson-study → writing → lesson-study`
  permanece; a suíte E2E completa continua pendente da Sprint 58.
- **Portabilidade:** o script de deploy foi normalizado para LF; `.gitattributes`
  preserva LF nos scripts shell para checkouts futuros.

A base PostgreSQL usada para integração pertence ao projeto `aulas-ingles-sprint50-test`, porta 55435,
volume sintético próprio e papel limitado `aulas_test`; os dados de estudo/dev não são alvos.
Migrations existentes e seed são preparados pela guarda `app.testing`.
O container e a rede desse ensaio foram encerrados após a validação, preservando
o volume sintético. Ambientes dev/estudo/public não foram reiniciados.

## Aceite operacional pendente

Publicar as alterações, conferir/configurar `PUBLIC_PROBE_ORIGIN` e `OPERATIONS_TOKEN`
no GitHub, instalar o cron no host com arquivo privado e validar a entrega do canal de
alerta. Em stack de ensaio, parar o worker, receber alerta em até cinco minutos, religar
e confirmar recuperação. Registrar evidência; o cron GitHub de 30 minutos não cumpre
sozinho esse prazo.

Testes sintéticos de saída e de manutenção não confirmam configuração remota ou recebimento
de e-mail. Este incremento não inclui deploy, commit/push, mudança de secrets remotos,
remoção de volumes, ativação de assistência ou implantação do módulo de listening.

## Próxima implementação

O código da **Sprint 51 — borda, sessão e autenticação** foi implementado na
[entrega seguinte](execucao_sprint51_2026-11-05.md), mantendo o aceite operacional
da 50 explícito como pendência. A próxima implementação é a Sprint 52.
O catálogo de listening permanece
na 59, seguido do piloto nativo na 60 e da retomada/histórico na 61.
