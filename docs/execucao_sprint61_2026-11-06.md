# Sprint 61 — Retomada e histórico de listening

Execução iniciada em 05/11/2026 e continuada em 06/11/2026. A implementação
técnica foi preparada em cópia isolada do repositório. O piloto permanece
desativado nos ambientes de estudo e produção: aceite editorial, áudio,
direitos e publicação continuam pendentes.

## Entrega e prioridade

1. Histórico paginado por conta, filtro de atividade, primeira/última prática,
   conclusão, nota inicial e resultado das tentativas mais recentes. Links para
   continuar uma sessão ou revisar erros; resultados externos autodeclarados
   permanecem separados dos resultados corrigidos no app.
2. Retomada do áudio por conta/sessão e versão, com revisão independente das
   respostas, idempotência e escolha explícita em conflito. O player compartilha
   o sincronizador de posição existente, com namespace próprio para listening.
3. Rascunhos, cópia da sessão e fila durável de respostas em IndexedDB por conta.
   Gravação atômica antes de informar pendência, reenvio com a mesma chave,
   proteção na troca de conta e preservação de rascunhos de editores diferentes.
   Uma limpeza local avança a geração para rejeitar callbacks antigos.
4. Migration expansiva `f61a1b8c9009`, índices, grants mínimos, exportação,
   exclusão em cascata, inventário/limpeza local e ensaio de recuperação.

O [guia do piloto](listening_nativo.md) e o [guia do aluno](guia_do_aluno_retomada_offline_privacidade.md)
descrevem uso, limitações e sequência de release/desativação. O plano das
Sprints 50–61 foi atualizado. Atalho no painel Hoje era opcional e não foi
incluído; progresso, habilidades, SM-2 e certificados VOA não foram alterados.

## Validação técnica

- Backend completo no Linux: **1.537 testes aprovados em 908,29 s**, com
  **94,21% de cobertura** (piso de 90%).
- Recorte inicial do backend: **39 testes aprovados**, incluindo retomada,
  idempotência, concorrência, histórico, privacidade, exportação e exclusão.
- Frontend completo final: **521 testes em 62 arquivos**. Cobertura: statements
  **80,77%**, branches **74,83%**, funções **78,50%**, linhas **86,43%**.
  Inclui armazenamento indisponível, quota, duas contas, duas abas, tombstone,
  resposta de outra versão, conflito explícito e paginação do histórico.
- Ruff de todo o backend, mypy de **116 arquivos**, ESLint, TypeScript,
  correspondência OpenAPI/TypeScript e build aprovados.
- Migration, `alembic check` e seed aprovados em PostgreSQL sintético.
  Ensaio com migrador/runtime/worker/backup aprovado: grants efetivos, detecção
  de privilégio indevido, dump/restore de versões/sessões/respostas/posições,
  cascata no banco restaurado e hashes dos três MP3s da imagem da release.
- E2E: **38 cenários distintos verificados entre rodadas**, em Chrome desktop e
  mobile, cobrindo catálogo externo, escolha múltipla, áudio, rascunhos, duas
  abas, reconexão, primeira nota, revisão de erros, troca de conta, exportação,
  exclusão e regressão VOA/PWA. Os 12 cenários da Sprint 61 passaram sobre o
  worker com recuperação do shell. **Reteste final: seis testes offline/PWA
  aprovados**, incluindo perda deliberada e recuperação do shell, desktop/mobile.
  O teste VOA passou a reconferir a disponibilidade depois da resposta editorial,
  evitando depender do timer inicial do painel. A suíte E2E geral não foi repetida.
  Axe e ausência de rolagem horizontal aprovados; captura do histórico mobile
  inspecionada. O login retorna à rota solicitada, e a troca de cookie para outra
  conta exige confirmação explícita, preservando as pendências anteriores.
- Latência do histórico (12 sessões sintéticas, página de dez, 12 amostras por
  navegador): desktop mediana **65,7 ms**, p95 amostral **275,4 ms**; mobile
  mediana **18,1 ms**, p95 **43,5 ms**. Medições incluem navegador/proxy/API no
  laboratório com CPU limitada e cargas concorrentes; não são SLO de produção
  nem ensaio de grande volume. A consulta usa cursor por ID e carrega eventos
  somente das sessões da página, sem consulta individual por sessão.
- **17 testes de scripts aprovados no Linux**: 14 do gate de bundle e três
  da recuperação do shell (recarga offline, hash de outra release, resposta
  privada e quota). Medição gzip final:
  entrada **130,7/132 KiB**, base **182,3/184 KiB**, diálogo **7,1/8 KiB**,
  catálogo externo **2,7/3 KiB** e listening/player/sincronização **12,6/13 KiB**.
  Total **204,6/208 KiB**. A reserva específica cresceu de 6 para 13 KiB para
  histórico/fila e passou a incluir o sincronizador de posição compartilhado
  com VOA, anteriormente contado na base. Os tetos inicial e base não mudaram.

A repetição da recarga offline expôs perda do cache público do shell. O fallback
anterior buscava HTML online sem reconstruir esse cache. A navegação agora o
recompõe somente após conferir o SHA-256 da release instalada e as regras de
cache público. O E2E remove o cache do shell deliberadamente, visita online e
retoma offline com a resposta ainda pendente. TTL, limites de cache, JWT e CSP
foram preservados; nenhuma URL de sessão ou resposta privada entra nesse cache.

O teste de duas abas revelou substituição de rascunho recebido de outro editor;
a correção preserva ambos e acrescentou regressão unitária. Um cenário longo
de quatro respostas, recarga, axe e captura atingiu o limite global de 30 s;
apenas esse teste passou a ter 60 s no laboratório com CPU limitada.

## Limites e sequência de liberação

O cache privado contém apenas sessões já abertas e projeções autorizadas da API.
Áudio e respostas HTTP privadas não entram no Cache Storage; material do
Test-English não foi copiado. Áudio, criação de sessão e revelação de apoio
exigem conexão. Não há sincronização com o aplicativo fechado nem garantia de
captura dos últimos segundos após encerramento abrupto do navegador.

Um conflito preserva a pendência para decisão explícita. Rascunhos/pendências
locais não integram a exportação do servidor e não migram automaticamente para
outro dispositivo. A fila tem limites documentados e não apaga itens para abrir
espaço. Desativação por flag preserva dados e exportação/exclusão; rollback não
usa downgrade destrutivo nem limpeza de storage.

LIST-09/10/11 têm implementação técnica; LIST-12 permanece parcialmente pendente
do aceite manual. Ordem restante: ouvir e revisar os três pilotos, registrar
direitos, criar nova versão aprovada, ensaiar release e publicar de forma
controlada. Nenhum campo de aprovação humana foi preenchido automaticamente.

Nenhum deploy, commit, push ou migration no banco de estudo foi executado.
