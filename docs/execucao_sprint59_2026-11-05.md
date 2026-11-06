# Sprint 59 — Catálogo A2 de listening rápido

Código e validações locais concluídos. Implementação iniciada em 05/11/2026;
publicação e ativação em ambiente de estudo/produção não executadas.

## Entrega

- 31 links do Test-English reconciliados com o catálogo A2, com metadados
  autorais e data de conferência; sem cópia de conteúdo ou duração inventada.
- Rota `/listening`, acesso pelo menu em até duas ações, busca sem distinção
  de acentos, filtro e marcação manual reversível. Abrir a origem não conclui.
- Catálogo independente do currículo VOA, progresso por conta e recibos de
  idempotência. Revisão evita sobrescrita entre abas; recibos antigos não
  desfazem um estado posterior. Falhas não são apresentadas como gravação salva.
- Exportação completa e exclusão incluem os novos dados mesmo com a flag
  desligada. Seed reexecutável sem apagar recursos ou histórico, com versão
  obrigatoriamente maior para alterações editoriais.
- Migration expansiva, grants mínimos, flag desativada por padrão e contratos
  OpenAPI/TypeScript atualizados. Nenhuma origem foi acrescentada à CSP/cache.

Detalhes de uso, contrato, manutenção dos links e ativação estão no
[guia de listening rápido](listening_rapido.md). A Sprint 60 permanece separada:
três atividades próprias/licenciadas, com mídia e revisão editorial antes de publicar.

## Evidências

- Backend completo no Linux: **1.506 testes aprovados** em **829,04 s**,
  com **94,08% de cobertura**, acima do piso de 90%.
- Backend direcionado: **38 testes aprovados**, incluindo privacidade,
  concorrência, repetição, catálogo indisponível e preservação do currículo.
- Frontend: **496 testes em 59 arquivos**; cobertura de linhas **85,94%**,
  statements **80,48%**, branches **74,71%** e funções **78,49%**. Pisos do CI
  preservados. ESLint, build, Ruff, mypy e contrato gerado aprovados.
- E2E de listening: **8 testes aprovados** em desktop/celular; acesso pelo menu,
  abertura externa sem concluir, persistência após refresh, exportação/exclusão,
  conflito real entre abas, offline/reconexão e axe no conteúdo da nova tela.
- Migration até o head, `alembic check` e seed aprovados no banco sintético;
  ensaio com papel migrador e verificação efetiva de grants também aprovados.
  O teste operacional confirmou leitura de backup, ausência de acesso do worker
  e recusa de UPDATE em catálogo/recibos pelo runtime.
- **13 testes do gate de bundle aprovados no Linux**. Medição: entrada
  **130,1/132 KiB**, base **183,7/184 KiB**, diálogo **7,0/8 KiB** e listening
  **2,8/3 KiB**, todos gzip. O conjunto mediu **193,5/195 KiB**.
- E2E geral: **172 cenários coletados**, **167 aprovados** e **dois skips
  declarados** (medição de desempenho exclusiva do Chromium), em 14 minutos.
  Duas verificações de teclado ainda esperavam a ordem anterior dos atalhos;
  foram atualizadas para incluir Listening rápido. Um cenário de aula offline
  no celular falhou nessa rodada e não reproduziu no reteste.
- Reteste final: **12 cenários aprovados em 1,8 minuto**, cobrindo as três
  falhas e todas as oito jornadas novas, em desktop/celular. Incluiu também
  o cenário offline do desktop. Assim, os **170 cenários executáveis** ficaram
  verificados entre a rodada geral e o reteste; não se declara uma rodada
  única de 170 aprovações. Capturas desktop/mobile da nova tela foram inspecionadas.

A regressão detectou uma fixture antiga de ícone no cache de shell; ela agora
prepara o cache estático usado pelo service worker. A invalidação de listening
integra o mapa central existente e afeta somente `listening-progress`.
Os laboratórios usam bancos sintéticos separados. API e banco de cada suíte
compartilham um núcleo da VM, mantendo a mitigação de relógio observada na Sprint 58.
No reteste, o navegador também foi fixado nesse núcleo. A política de cache da
PWA não foi alterada para fazer o cenário passar; a causa da falha intermitente
não foi estabelecida somente pelo reteste.
Nenhum commit, push, deploy ou migration do banco de estudo foi realizado.
