# Sprint 60 — Piloto nativo de listening

Implementação iniciada em 05/11/2026. Piloto preparado para revisão local;
**aceite editorial e publicação pendentes**. O plano exige revisão humana do
nível A2, áudio, respostas e direitos antes da publicação. As flags permanecem
desativadas nos ambientes de estudo e produção.

## Entrega

- Três atividades originais em rascunho, dez questões, transcrições e explicações:
  hotel (quatro), orientação com mapa acessível (três) e lazer (três, incluindo
  seleção de duas opções). MP3s sintéticos de aproximadamente 77 segundos cada,
  com procedência e hashes; a duração pedagógica alvo de 5–10 minutos não foi validada.
- Versões editoriais imutáveis e sessões com versão fixa, separadas das tabelas
  VOA. Correção no servidor, IDs estáveis, validação de cardinalidade/conjunto,
  proteção contra duplicatas, isolamento entre contas e recibos de idempotência.
- Primeira resposta define a nota; revelação inicial vale zero; repetição não
  substitui o resultado inicial. Apoio textual fica identificado e persistido.
- Rota lazy `/listening/:slug`, início explícito, player sem autoplay, velocidade,
  repetição A/B, atribuição, mapa, feedback, transcrição e conclusão. Controles de
  player/seleção extraídos e compartilhados com o fluxo VOA.
- Migration `e60a1b8c9008`, grants mínimos, exportação/exclusão e ensaio real de
  backup/restore. O áudio é autenticado e somente online; sem alteração da CSP.

O [guia do piloto](listening_nativo.md) reúne os MP3s, pacote de revisão,
contratos, ativação em clone e procedimento de release. Somente a stack E2E
sintética habilitou a prévia; nenhum banco de estudo foi migrado.

## Validação

- API direcionada: **50 testes aprovados**, cobrindo catálogo nativo e externo,
  correção, idempotência, concorrência, versões, mídia ausente, isolamento,
  exportação, exclusão e inventário de tabelas de teste.
- Frontend completo: **507 testes em 60 arquivos**. Cobertura: statements
  **80,72%**, branches **74,99%**, funções **78,95%**, linhas **86,17%**.
  Após o tratamento de endereço de sessão inválido, os dez testes da tela
  foram repetidos e aprovados. Ruff, mypy, ESLint, TypeScript e contrato
  OpenAPI/TypeScript aprovados.
- E2E de listening: **16 testes aprovados** em desktop e celular, incluindo
  áudio real, correção, mapa, axe, exportação, recarga e cache/offline.
- Migration, `alembic check` e seed aprovados em PostgreSQL descartável.
  Ensaio operacional com migrador/runtime/worker/backup aprovado: privilégio
  mínimo, dump e restauração de versões/sessões/respostas, cascata de exclusão
  no banco restaurado e hashes dos três áudios em container novo da imagem.
- **14 testes do gate de bundle aprovados no Linux**. Medição final gzip:
  entrada **130,4/132 KiB**, base **183,9/184 KiB**, diálogo **7,0/8 KiB**,
  catálogo externo **2,6/3 KiB** e piloto/player/CSS compartilhado **5,0/6 KiB**.
  Conjunto **198,5/201 KiB**. A reserva nova identifica apenas os chunks lazy
  do piloto, player neutro e estilo compartilhado; os tetos inicial/base foram preservados.

- Backend completo no Linux: **1.526 testes aprovados em 813,81 s**, com
  **94,13% de cobertura**, acima do piso de 90%. Após enriquecer a exportação
  com nota, versão e indicação de apoio, o recorte final de 50 testes foi
  repetido para conferir esse ajuste.
- Regressão VOA: 17 dos 18 cenários passaram na primeira rodada. Uma falha
  de seletor ambíguo no helper E2E encontrava o botão e o rótulo “Resposta”;
  o seletor foi limitado ao feedback. **Reteste final: dez cenários aprovados**,
  cobrindo esse fluxo em desktop/mobile e os oito cenários nativos, sobre a
  stack recompilada. Os 34 cenários distintos dos recortes listening + VOA
  ficaram verificados entre as rodadas; a suíte E2E geral não foi repetida.
- Capturas de desktop/celular foram geradas; a apresentação mobile foi
  inspecionada. Não houve mudança nos limites de cache, JWT ou CSP para
  fazer os testes passarem.

## Limites e sequência

LIST-05 continua pendente de aceite humano. Os campos de revisão/licença não
foram preenchidos automaticamente e nenhum material foi declarado publicável.
A mesma voz sintética lê os nomes dos interlocutores; naturalidade, pausas e
inteligibilidade precisam de avaliação. Publicação exige uma nova versão aprovada.

A Sprint 61 permanece planejada: posição do áudio/rascunhos, histórico, revisão
de erros e publicação controlada. O endereço de uma sessão já permite consultar
respostas confirmadas; isso não equivale à retomada completa prevista na 61.

Nenhum deploy, commit, push ou migration em banco de estudo foi executado.
