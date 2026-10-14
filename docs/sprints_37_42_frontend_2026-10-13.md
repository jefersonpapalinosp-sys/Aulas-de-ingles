# Sprints de frontend para confiabilidade e experiência de estudo

Atualização: 14 de outubro de 2026. **FE-38 implementada, validada em ambiente isolado e implantada em 5181; homologação com leitores de tela reais pendente.** FE-39 a FE-42 permanecem planejados. A homologação pedagógica humana da escrita continua pendente, sem aprovação fictícia.

Estado instalado em 5181: Sprint 38; [registro operacional](operacao_sprint_37.md#sprint-38--implantação-autorizada-em-14102026). Desenvolvimento em 5180 não foi atualizado nesta manutenção.

Base: [auditoria técnica](auditoria_tecnica_frontend_backend_banco_2026-10-13.md). Os IDs F, B e D referem-se aos achados desse relatório. Estes pacotes não substituem as Sprints 20 a 36 já entregues: a trilha por curso/unidade, o laboratório e a classificação devem ser preservados.

O objetivo é permitir que o aluno estude, interrompa e retome com confiança, inclusive em rede instável, sem perder respostas nem receber correções referentes a outro texto. A prioridade visual é clareza de estado, navegação e feedback, não um redesenho cosmético completo.

## Organização e dependências

| Pacote | Resultado | Prioridade | Dependência principal |
|---|---|---|---|
| FE-37 | Sessão, fila e recuperação de erro confiáveis | P1 | Isolamento de testes DB-37 antes de E2E integrado |
| FE-38 | Escrita, revisão e jornada com conflitos explícitos | P1 | Contratos BE-38 e revisões DB-38 |
| FE-39 | Áudio e experiência offline consistentes | P1/P2 | BE-39 e DB-39 |
| FE-40 | Histórico e dados pessoais compreensíveis | P1/P2 | BE-40 e DB-40 |
| FE-41 | Acessibilidade, paginação e componentes sustentáveis | P2 | BE-41 e matriz de dispositivos |
| FE-42 | Homologação completa da experiência de estudo | P2 | Fechamento dos ciclos anteriores |

Uma equipe pode dividir um pacote em entregas menores sem alterar a ordem de dependências. Não há estimativa de prazo fechada: conflitos, requisitos de dispositivos e desenho de contrato devem ser refinados antes de compromisso de calendário.

## Sprint 37 Sessão e preservação do trabalho

Achados: F01, F02, F03, F06, F08 e F10. Integração: B01, D01 e D02.

### Entregas

- [x] Corrigir reenvio de POST/PUT após 401 preparando corpo reutilizável antes do primeiro envio, com apenas uma renovação/repetição e preservação da idempotência.
- [x] Unificar o comportamento de chamadas JSON e binárias sem reenviar corpos não reproduzíveis automaticamente.
- [x] Separar estados de sessão válida, expirada/revogada, temporariamente indisponível e offline. 503 ou falha de rede no refresh não devem apagar o trabalho local.
- [x] Impedir descarte silencioso da fila. Ao atingir capacidade, informar limite e não aceitar uma nova resposta como “salva” se não houver persistência.
- [x] Definir persistência transacional e coordenação entre abas, preferencialmente com IndexedDB ou solução equivalente demonstrada. Preservar usuário, curso, aula, sessão e chave idempotente.
- [x] Oferecer status de fila com pendentes/bloqueadas, motivo de bloqueio e ações seguras; manter suporte aos dados v1/v2 existentes.
- [x] Centralizar acesso ao armazenamento local e tratar quota/indisponibilidade. Não mostrar sucesso quando a gravação falhar.
- [x] Adicionar ErrorBoundary de aplicação/área de estudo e recuperação de chunk indisponível sem laço de reload.
- [x] Substituir a instrução global de `make up` por mensagens adequadas ao aluno, com detalhe técnico e request-id opcionais.

### Critérios de aceite

1. POST e PUT com corpo realmente consumido pelo transporte renovam e repetem o pedido uma única vez; teste cobre token inválido também na repetição.
2. Refresh 503/offline mantém respostas/rascunhos e apresenta indisponibilidade; refresh definitivamente revogado conduz a autenticação sem misturar contas.
3. As respostas 1 a 101 não desaparecem silenciosamente. O produto deve ou conservar todas, ou recusar a nova de forma explícita antes de afirmar sucesso.
4. Duas abas enfileiram e sincronizam simultaneamente sem perda; a API recebe a mesma chave em repetição e registra uma só tentativa.
5. Falta de quota local produz mensagem e preserva o texto em memória; o usuário sabe o que ainda não está salvo.
6. Abrir rota lazy não disponível offline produz uma tela de recuperação acessível, não tela vazia.
7. Nenhum teste integrado toca a base real de estudo. A aprovação de DB-37 é requisito para esse gate.

### Cenários e arquivos

Testar GET/POST/PUT, Blob, duas abas, troca de usuário, StrictMode, 401/503/rede, migração de fila antiga, payload inválido e quota cheia. Áreas principais: `api/client.ts`, `api/auth.tsx`, `features/offline`, `components/States.tsx`, `App.tsx` e testes correspondentes.

Fora do escopo: download offline de mídia, mudança visual integral e novo provedor de IA.

### Registro de execução — terceiro incremento, sessão e reenvio, 13/10/2026

Implementado em `api/session.ts`, `api/client.ts`, `api/auth.tsx`, `SessionStatus`,
shell e integração mínima com a fila existente:

- A cópia de JSON é preparada antes do primeiro fetch. POST/PUT são repetidos
  somente após 401 e renovação válida, uma vez, preservando bytes, método,
  headers, sinal de cancelamento e chave idempotente. Falha de rede/5xx na
  operação original não dispara repetição automática de uma mutação.
- Upload de Blob e download privado usam a mesma renovação. Streams recebidos
  pelo helper binário não são copiados nem repetidos; o chamador recebe a
  resposta original. O helper recusa URLs externas para não enviar o token.
- Bootstrap, JSON e áudio compartilham uma renovação por vez **na mesma aba**.
  Um 401 atrasado aproveita o token já renovado. A resposta antiga de uma
  renovação não restaura a sessão depois de logout ou login em outra conta.
- Refresh 429/5xx/rede ou resposta inválida produz indisponibilidade, não logout.
  O cliente devolve 503 local com `X-Session-State` à operação interrompida;
  isso é uma decisão do transporte frontend, não um novo contrato do backend.
  Refresh 401 ou novo 401 na única repetição encerram a sessão local.
- Quando há proprietário conhecido, o token renovado é confirmado em `/auth/me`
  antes de repetir a operação. Cookie de outra conta exige autenticação; não
  envia uma escrita antiga com o novo proprietário. GETs de conteúdo público
  podem alcançar o cache textual sem Authorization quando só há perfil local;
  escritas ficam bloqueadas até a confirmação do perfil.
- A interface diferencia falta de conexão de indisponibilidade da sessão,
  oferece “Tentar confirmar sessão” e retoma a validação no evento `online`.
  O aviso fica no fluxo da página, sem sobrepor o indicador fixo da fila.
  Falhas ao persistir/remover o perfil são avisadas sem desfazer login/logout.
  Logout sem confirmação do servidor não promete revogação remota.
- A rodada de sincronização confere conta e geração da sessão antes de enviar
  cada item e antes de confirmar o resultado. Troca de conta/cancelamento
  interrompe a rodada preservando itens e chaves para reconciliação posterior.
  Isso **não** implementa coordenação de fila entre abas nem remove seu limite
  antigo de 100 itens.

Validação automatizada, sem conexão a banco ou conta de estudo:

- 212 testes frontend aprovados; 30 do cliente, 17 do provider integrado e
  10 da fila. Os testes do cliente consomem o Request original com `text()` ou
  `arrayBuffer()` antes de devolver 401, em vez de deixar o corpo intacto.
- Cenários: POST/PUT, bytes de Blob, download, stream sem repetição, segundo
  401, 429/5xx/rede/JSON inválido, chamadas simultâneas e atrasadas, StrictMode,
  cancelamento, cookie de outro usuário, perfil indisponível, logout e quota.
- Teste com o **WritingWorkspace real** confirma manutenção do mesmo editor,
  texto e backup local após autosave → 401 → refresh 503. Teste integrado da
  fila mantém a tentativa pendente, sem convertê-la em bloqueada ou removê-la.
- ESLint, TypeScript, build e orçamento de bundle aprovados. Não houve ensaio
  com servidor HTTP real, E2E, inspeção visual em navegador ou leitores de tela
  neste incremento. A suíte backend não foi repetida por não haver mudança
  de backend ou schema; os resultados anteriores continuam no registro BE-37.

Próximo passo identificado naquele incremento: fila sem descarte silencioso,
persistência transacional/migração v1/v2 e coordenação entre abas, atendidos no
quarto incremento abaixo. Permanecem armazenamento dos demais recursos,
barreiras de erro e mensagens gerais.
Revalidação do cookie entre abas e atomicidade da rotação continuam em BE-38;
o single-flight deste incremento não resolve essas corridas de servidor.
A atualização de migration/seed na base de estudo e o isolamento E2E continuam
pendentes em DB-37. Nenhum banco, serviço Docker, commit ou remoto Git foi
alterado nesta etapa.

### Registro de execução — quarto incremento, fila transacional, 13/10/2026

Implementado em `attemptQueueStore.ts`, `attemptQueue.ts`, `ConnectivityStatus`,
`ExerciseCard` e `PracticeRunner`:

- IndexedDB `aulas:offline-attempts:v3`, schema 1, com chave composta por aluno
  e chave idempotente. Consulta de capacidade e inclusão acontecem na mesma
  transação. São até **100 respostas por aluno**, incluindo bloqueadas; a
  resposta 101 é recusada explicitamente e continua no campo, sem deslocar a
  mais antiga. Falha de quota/armazenamento não gera “Na fila” nem progresso.
- A interface aguarda o commit, não apenas o sucesso do pedido de gravação.
  Controles de resposta ficam desabilitados durante o envio/persistência.
  Se a rede perde a resposta e a gravação local falha, repetir o mesmo texto
  reutiliza a chave da operação incerta.
- Migração transacional da união das filas localStorage v1/v2: preserva
  respostas, datas, contexto e bloqueios, inclusive mais de 100 itens legados.
  Dados inválidos ou colisão de chave com respostas diferentes interrompem a
  migração, sem substituir a fila por uma lista vazia. A cópia original não é
  removida nem reescrita, pois uma aba antiga pode estar escrevendo nela.
- Snapshots identificam fontes já importadas; recibos locais mínimos
  (`userId`, `idempotencyKey`) impedem que uma cópia antiga recrie um item já
  confirmado ou descartado. Confirmar o recibo e remover a pendência é uma
  transação única. Falha nesse commit mantém a tentativa para repetir a mesma
  chave, mesmo se a API já a recebeu. Resultado 200 sem ID/booleano válidos
  não autoriza remoção.
- Web Locks serializa a sincronização por origem/aluno. Fechar a aba libera
  o lock e permite retomada por outra. Continua a verificação da conta e da
  geração da sessão antes/depois de cada envio. Sem Web Locks, a aplicação
  conserva a fila e informa que não pode sincronizar com segurança; não usa
  uma flag local como substituto. Usar HTTPS ou localhost.
- BroadcastChannel avisa mudanças/resultados às outras abas, sem respostas,
  textos ou credenciais. Foco e alterações das chaves legadas também relêem
  a fila. Falha de notificação não desfaz um commit válido. A sessão de prática
  e os indicadores relacionados são reconsultados após sincronização.
- O painel permite consultar texto, aula e motivo HTTP dos bloqueios.
  Remover bloqueadas exige confirmação e se limita às chaves selecionadas
  daquele aluno; preserva pendentes e dados de outras contas. A ação remove
  da fila ativa, não apaga histórico remoto ou as cópias legadas de recuperação.

A separação entre sucesso de um request e conclusão da transação orienta a
persistência; a exclusão mútua entre abas usa o mecanismo do navegador.
Referências: [MDN — IDBTransaction](https://developer.mozilla.org/en-US/docs/Web/API/IDBTransaction)
e [MDN — Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API).

Validação em 13/10/2026:

- **236 testes frontend aprovados**, em 30 arquivos, incluindo 18 testes do
  armazenamento transacional, 10 do fluxo da fila, 22 do cartão e 3 do painel.
  Cobrem limite por aluno, última vaga concorrente, aborto após sucesso do
  request, quota, migração atômica, dados corrompidos, bloqueios, retry com a
  mesma chave e indisponibilidade de IndexedDB/Web Locks/BroadcastChannel.
- **3 testes Chromium com duas abas reais aprovados**: 100 inclusões concorrentes
  sem perda e uma submissão por chave na rodada coordenada; fechamento da aba
  durante envio e retomada idempotente; migração concorrente sem ressurreição
  da cópia antiga. IndexedDB, Web Locks e BroadcastChannel são nativos nesses
  testes; a API é simulada. Isso não substitui um ensaio com backend real.
- TypeScript, ESLint, build e orçamento aprovados: **168,1 KiB gzip** de JS/CSS.
- Novo comando isolado: `cd e2e && npm run test:queue`. Abre Vite exclusivo em
  `127.0.0.1:5197`, sem proxy para a API, não reutiliza servidor existente nem
  lê `E2E_BASE_URL`. Requisições `/api/` sem interceptação recebem 503 local.
  Não cria usuários nem toca bancos/volumes de estudo. Chromium deve estar
  instalado pelo Playwright. Esse gate foi acrescentado ao job frontend do CI;
  a execução remota do workflow não foi realizada nesta entrega.
- Única dependência adicionada: `fake-indexeddb@6.2.5`, de desenvolvimento.
  Nenhuma migration, seed, alteração de serviço Docker, commit ou push nesta
  etapa. A suíte backend não foi repetida; os números anteriores são históricos.

Limites e cuidados operacionais:

1. Fechar/recarregar abas com o código antigo antes de usar a versão nova.
   A migração recolhe mudanças observadas nas fontes antigas, mas não corrige
   o algoritmo de truncamento/sincronização de uma versão antiga ainda aberta.
2. Recibos e snapshots não têm expiração automática nesta entrega. As cópias
   legadas podem conter texto de respostas; logout não as apaga. Retenção e
   exclusão completa de dados locais exigem política em FE-40/DB-40, sem
   comprometer recuperação ou permitir reimportação de itens antigos.
3. Persistência local não equivale a backup externo: limpar dados do navegador
   ou perder o dispositivo pode eliminar respostas ainda não sincronizadas.
   Não limpar dados para contornar erro de migração/quota.
4. Não houve homologação visual/manual, VoiceOver/TalkBack, Windows real ou
   E2E integrado com API/PostgreSQL. O teste isolado acima não fecha o requisito
   de isolamento da stack E2E local em DB-37.
5. Coordenação da fila não corrige rotação concorrente do cookie por outras
   chamadas; atomicidade do refresh continua em BE-38. Rollout da escrita v2
   na base de estudo depende do backup verificável e permanece pendente.

Alerta de dependências encontrado durante a instalação: `npm audit` reportou
**1 alerta moderado e 2 críticos** na árvore de ferramentas de teste existente
(`@vitest/mocker`, `tinypool`, `vitest`). O lockfile manteve Vitest 3.2.7; a
correção sugerida pelo npm envolve atualização major, que não foi aplicada
automaticamente. Não é evidência de exploração da aplicação em produção.
Referências do relatório: [mocker](https://github.com/advisories/GHSA-82fw-gwwq-j7x9),
[tinypool — primeiro aviso](https://github.com/advisories/GHSA-5gmw-xhrv-c9v3) e
[tinypool — segundo aviso](https://github.com/advisories/GHSA-85c8-ppgw-ccpr).
Tratar em uma atualização dedicada das ferramentas, com compatibilidade,
lockfile e nova execução completa dos testes; não usar `npm audit fix --force`
sem revisão.

O próximo incremento identificado nesta etapa foi armazenamento dos demais
recursos, ErrorBoundary/recuperação de chunks e mensagens, atendido abaixo.
O alerta de dependências continua aberto, sem atualização major automática.

### Registro de execução — quinto incremento, armazenamento e recuperação, 13/10/2026

Entregas de código:

- `storage/local.ts` centraliza os acessos a localStorage do código de aplicação.
  Leitura, gravação e remoção retornam sucesso/falha explícitos, inclusive quando
  o próprio getter de armazenamento lança SecurityError. Não usa cache em memória
  fingindo persistência nem registra textos/credenciais nas mensagens de erro.
  IndexedDB da fila continua transacional; a leitura das fontes legadas usa o
  novo adaptador e mantém a interrupção segura se não puder conferir a origem.
- Escrita mantém o texto editável após falha local, distingue “apenas nesta tela”,
  “salvo neste dispositivo” e confirmação remota. Autosave remoto continua mesmo
  quando o backup local falha. Falha ao remover backup depois de sucesso remoto
  apresenta aviso específico, sem transformar esse sucesso em falha da API.
  A análise indisponível não afirma mais que o texto está salvo.
- Jornada, posição da prática, player, autoavaliação de fala e perfil usam o
  mesmo adaptador. Falha de quota não interrompe avanço, reprodução ou tentativa
  de sincronizar na conta; a interface avisa que a cópia local não foi confirmada.
  A jornada legada ainda pode ser recuperada em memória se copiar para a chave
  multi-curso falhar. O perfil indisponível não impede abrir o login.
- `ErrorBoundary` na raiz protege shell/providers; outra barreira envolve as
  rotas de estudo e preserva a navegação externa à área com erro. Trocar de rota
  permite recuperação da área. O fallback recebe foco e tem controles nativos.
  Import dinâmico/CSS indisponível tem mensagem própria; não tenta repetir um
  `React.lazy` rejeitado indefinidamente. Recarregar exige duas ações explícitas
  e avisa sobre dados ainda apenas na memória. Não há limpeza de caches,
  localStorage, IndexedDB ou recarga automática.
- O componente global `Erro` deixa de orientar o aluno a executar `make up`.
  Orienta reconexão, sessão, conteúdo ausente ou espera por limite de pedidos;
  erros desconhecidos recebem orientação genérica. Catálogo, currículo, aula,
  exercícios, checkpoint e conclusão carregam `ApiError` com status/request-id
  quando disponíveis. Os detalhes ficam recolhidos; não mostram corpos, tokens
  nem mensagens arbitrárias de exceções. Códigos de negócio padronizados no
  servidor continuam pendentes em BE-37.

Validação em 13/10/2026:

- **262 testes frontend aprovados em 33 arquivos**, incluindo falha do getter,
  quota cheia, remoção bloqueada, continuidade de escrita/áudio/fala/jornada/
  prática, migração local, mensagens HTTP, foco, erro de render e import lazy.
  O teste integrado do editor segue confirmando preservação durante refresh 503;
  agora aguarda a falha remota, pois o salvamento local já é anunciado antes dela.
- **4 testes Chromium isolados aprovados** pelo comando `cd e2e && npm run
  test:queue`: os três cenários da fila continuam e foi acrescentada uma fixture
  de recuperação que bloqueia um import real. Verifica foco, Tab/Enter, retorno
  ao início, confirmação/cancelamento de recarga e conservação de dados locais
  sintéticos. Em viewport de 320 px, a fixture não tem rolagem horizontal.
  Isso não homologa toda a aplicação por teclado, zoom ou leitor de tela.
- TypeScript, ESLint, build e orçamento aprovados. Total JS/CSS arredondado:
  **170,0 KiB gzip**, abaixo do teto existente, sem aumentar limites. A margem
  é pequena; monitorar o gate nas próximas alterações. Mensagens de remoção
  foram compartilhadas e textos redundantes reduzidos para preservar o teto.
- A suíte de navegador usa porta 5197 e continua sem proxy/API/banco reais.
  Nenhuma nova dependência, migration, seed, operação Docker, commit ou push
  neste incremento. Não foi executado CI remoto nem a suíte backend novamente.

Limites e próximos passos para aceite:

1. A barreira trata renderização/efeitos/imports do React, não substitui tratamento
   de eventos/promises nem consegue recuperar dados que nunca foram persistidos.
   Também não cobre falha no download do próprio bundle inicial antes de o React
   iniciar. Não interpretar a confirmação de recarga como garantia de salvar
   gravação em memória ou texto cujo armazenamento foi bloqueado.
2. Conflitos de escrita entre dispositivos, feedback tardio e precedência da
   posição de áudio não foram resolvidos aqui; continuam em FE-38/FE-39.
   Uma cópia cuja remoção falhou pode reaparecer ao reabrir; conferir o aviso.
3. Concluir isolamento E2E/backup verificável de DB-37 antes de validar com API
   e banco reais descartáveis e antes do rollout da escrita v2 na base de estudo.
   Não executar `make test-e2e` contra a conta de estudo para fechar esse aceite.
4. Revisar em entrega dedicada os alertas de Vitest/mocker/tinypool registrados
   acima, com compatibilidade e revalidação da atualização. Não foram corrigidos
   nem reauditados nesta etapa. Exemplos pedagógicos e erros de negócio BE-37
   também permanecem abertos.
5. Homologar telas reais e acessibilidade assistiva na matriz de dispositivos.
   O pacote FE-37 tem seus itens de implementação atendidos, mas ainda não tem
   aceite integrado completo; não avançar o status da Sprint 37 para concluída.

Referências de implementação: barreiras React isolam falhas dos descendentes,
mas não substituem captura de eventos e tarefas assíncronas; o carregamento de
chunks do Vite pode falhar após uma publicação e exige recuperação controlada.
[React — Error Boundary](https://react.dev/reference/react/Component#catching-rendering-errors-with-an-error-boundary),
[Vite — load error handling](https://vite.dev/guide/build.html#load-error-handling).

### Sexto incremento — integração na stack descartável, 13/10/2026

O Playwright passa a usar a stack exclusiva descrita no
[registro DB-37](sprints_37_42_banco_de_dados_2026-10-13.md#sexto-incremento--stack-e2e-isolada-13102026),
com frontend buildado/nginx, API e PostgreSQL próprios. A configuração padrão
não aceita mais as portas da aplicação de estudo; o setup bloqueia os testes
quando não consegue comprovar o alvo descartável.

A suíte integrada foi atualizada para o contrato já implementado:

- A jornada de escrita espera “Critérios automáticos atendidos”, sem recuperar
  a promessa anterior de texto pronto/gramática correta.
- A fila é lida diretamente do IndexedDB v3, schema 1, em transação readonly.
  O teste falha se a base estiver ausente, em vez de criá-la como efeito da
  inspeção. Confere proprietário, exercício, resposta, chave, curso, aula e sessão.
- Após sincronizar, a suíte reenvia à API real a mesma resposta/chave/sessão
  e exige o mesmo `attempt_id` e `attempt_count=1`; verifica recibo local e
  ausência de tentativa pendente também depois de recarregar a página.
  Isso substitui a inspeção `postDataJSON()` que devolveu `null` para o envio
  com stream no navegador, sem remover a verificação de idempotência.
- O helper de cadastro aguarda e exige HTTP 201 antes de verificar a navegação.
  Na rodada exploratória, uma resposta levou 10,17 s e ultrapassou os 10 s da
  asserção de URL. O timeout global dos testes não foi aumentado. Esse dado
  isolado não é benchmark nem prova da causa de lentidão do servidor.

O frontend de produto não recebeu mudança adicional neste incremento;
as alterações são infraestrutura, testes e documentação. Aprovação automatizada
de Tab/Enter, reflow, axe e emulação de contraste não equivale a VoiceOver,
TalkBack ou Windows real. Os testes de duas abas continuam nas fixtures
isoladas já registradas; este incremento não homologa todas as corridas de
refresh, duas contas/dispositivos ou falhas de quota contra servidor real.

Validação final: **96 execuções E2E aprovadas** em uma rodada completa, sem
retries locais (48 cenários em Chromium desktop e mobile emulado, 6 min),
incluindo jornada com escrita v2, sincronização/reenvio real, recibo IndexedDB,
PWA offline, voz sintética, checkpoints, teclado, reflow e axe. **48 testes das
guardas** também passaram. Build de container (incluindo TypeScript), configuração
Compose, `actionlint` e diff check aprovados. As suítes de 262 testes frontend,
668 backend e quatro fixtures isoladas não foram repetidas nesta etapa;
seus resultados anteriores permanecem registrados como históricos.

Na conclusão do sexto incremento, backup/restore com voz, papéis de produção,
exemplos pedagógicos/códigos BE-37 e alertas de dependências continuavam abertos.
A escrita v2 não foi aplicada à
base de estudo. A Sprint 37 conjunta permanece em andamento.

Atualização do sétimo incremento: a rotina conjunta de backup/restore foi
implementada e ensaiada com dados sintéticos, sem mudar telas ou servir o
código novo sobre a base real. Foram 29 testes operacionais e um restore real
no laboratório, com conferência do áudio. As suítes frontend/E2E anteriores
não foram repetidas nesta etapa. Backup real em manutenção, papéis mínimos,
demais aceites técnicos e homologações humanas permanecem pendentes. Ver
[registro DB-37](sprints_37_42_banco_de_dados_2026-10-13.md#sétimo-incremento--backup-conjunto-e-restore-isolado-13102026).

### Oitavo incremento — fechamento técnico, 13/10/2026

- **263 testes frontend** aprovados, ESLint/TypeScript/build aprovados.
- **98 cenários Playwright integrados** aprovados: Chromium desktop e mobile
  emulado, exclusivamente em 5198, com API/PostgreSQL reais descartáveis.
  Acrescentado cenário de duas abas, duas aulas e sincronização concorrente:
  nenhuma resposta perdida, duas chaves distintas e retry devolvendo o mesmo
  attempt_id com attempt_count igual a 1 em cada sessão.
- **50 guardas E2E** aprovadas. Caminho Docker Desktop permitido somente por
  correspondência exata no macOS; flag real do provedor assistido desativada.
- **4 cenários controlados**, repetidos duas vezes (**8 execuções**), aprovados:
  capacidade de fila, fechamento de aba, migração concorrente e recuperação de
  import por teclado. Uma execução a frio sofreu reload do servidor de testes;
  HMR foi desativado **somente no harness**, mantendo a asserção de que o produto
  não recarrega automaticamente. API do harness continua bloqueada.
- Vitest atualizado para **4.1.11**, com lockfile; npm audit retornou **zero
  vulnerabilidades** nesta árvore, nesta execução. Não significa auditoria
  de toda a infraestrutura nem garantia futura.
- Contrato de erros integrado: sessão inválida, conflito e indisponibilidade,
  com orientações seguras e request-id; sem instrução global para rodar make up.
- Bundle total: **170,2 KiB gzip**. Limite total revisado explicitamente de
  170 para **172 KiB** devido às funcionalidades FE-37; limites individuais
  de JS/CSS mantidos. Essa mudança não é resultado de otimização de tamanho.
- Rollout em **localhost:5181** concluído após backup/restore/ensaio;
  health, catálogo e Aula 31 responderam 200. Nenhum teste mutável usou a
  conta de estudo. Containers de desenvolvimento em 5180 não foram reiniciados.

Aceites técnicos 1–7 atendidos pela combinação de testes de transporte,
armazenamento, browser e API real. Não se declara refresh concorrente resolvido
(BE-38), VoiceOver/TalkBack/Windows real homologados (FE-41), nem revisão
pedagógica humana feita. CI remoto, commit e push não foram executados.

## Sprint 38 Escrita e revisão sem conflitos silenciosos

Achados: F04, F10, B04 e B05. Contratos: versão de rascunho, conflito de jornada e evento idempotente de revisão.

### Entrega técnica e implantação em 14/10/2026

Autosave serial envia revisão esperada. Conflitos mostram texto local, texto da
conta, revisão e data, com escolha explícita e área selecionável para copiar ambos.
Backup legado sem revisão não sobrescreve a conta automaticamente. Respostas de
análise atrasadas e de componentes desmontados são descartadas da interface;
contagem de palavras não participa mais da região de anúncio de salvamento.
Avaliação de revisão congela o item, bloqueia repetição de teclado/clique e
reenvia a mesma chave/nota em caso de resposta perdida. Um invalidator compartilhado
atualiza revisão, Hoje, progresso, competências e conclusão. Jornada une conclusões
locais/remotas em vez de escolher apenas a lista mais longa.

Validação de componentes: 270 testes aprovados; lint, TypeScript, build e orçamento
de bundle aprovados (171,8 KiB gzip, limite preservado em 172 KiB). A margem é pequena;
novas funcionalidades não devem elevar o orçamento automaticamente.
Testes de navegador usam somente a stack isolada 5198. Nenhum teste novo de leitor
de tela real foi declarado aprovado; semântica de anúncio está coberta por testes
e axe no conflito. O critério 6 ainda exige homologação com VoiceOver/TalkBack.
Esta entrega não modifica o layout curricular nem o conteúdo das 82 aulas.

Regressão integrada: **106 E2E aprovados**, incluindo oito cenários novos de
conflito em dois dispositivos, análise atrasada, perda de resposta depois do commit
e merge de jornada/revisão. A atualização de Hoje foi ainda repetida com cache
previamente carregado e somente navegação SPA, aprovada em desktop/mobile.
O teste antigo de jornada precisava filtrar seu status de conclusão, pois agora
existe também status de salvamento da escrita; o seletor foi corrigido sem retirar
a verificação. API: 789 testes aprovados. Bundle implantado em 5181 após ensaio,
backup e migration autorizada; hash do HTML servido conferido com o container.
5180 não foi atualizado. Homologações humanas permanecem pendentes; não houve
commit ou push. As jornadas legadas inconsistentes foram preservadas, sem inventar
conclusões ou datas; essa pendência não deve aparecer como corrigida pela interface.

### Entregas

- [x] Associar análise ao texto/versão de origem e impedir que uma resposta tardia apareça como avaliação do texto atual.
- [x] Preservar a fila serial de autosave já existente. Acrescentar revisão esperada e tratamento de 409/412 conforme contrato escolhido (409).
- [x] Criar apresentação de conflito com versões local/remota, data e ações para manter local, usar remota ou copiar ambas; nenhuma sobrescrita implícita.
- [x] Identificar rascunho local recuperado e diferenciar “neste dispositivo”, “na conta” e “pendente”.
- [x] Enviar chave idempotente ao avaliar revisão; bloquear repetição de clique/atalho enquanto houver avaliação pendente, incluindo `KeyboardEvent.repeat`.
- [x] Manter resultado de revisão estável até confirmar o servidor, com retry da mesma operação quando a resposta se perder.
- [x] Atualizar painel Hoje, progresso, competências e conclusão com uma política central de invalidação.
- [x] Reconciliação da jornada preservando etapas concluídas segundo o contrato BE-38, sem usar simples “última resposta vence”.
- [x] Informar corretamente que rubrica de escrita formal não equivale a correção gramatical completa nem a proficiência (antecipado na entrega BE-37).

### Critérios de aceite

1. Iniciar análise do texto A, editar para B e receber resposta de A não aplica feedback de A a B.
2. Dois dispositivos editam a mesma versão: o segundo recebe conflito recuperável; os dois textos continuam acessíveis.
3. Segurar tecla numérica na revisão não aplica múltiplas notas à mesma interação. Retry após timeout conserva a chave.
4. Após concluir a última revisão pendente, Hoje e o contador atualizam sem esperar cinco minutos ou recarregar.
5. Dois dispositivos concluindo etapas distintas não removem conclusões já confirmadas.
6. Leitor de tela anuncia salvamento, conflito e resultado sem interrupção a cada caractere.

### Testes e integração

Usar respostas atrasadas e fora de ordem, desmontagem de componente, conflito de conteúdo editorial e interrupção após commit. Validar primeiro os contratos em fixtures e depois contra API real isolada. Preservar testes da sessão de prática que já usa `state_revision`.

Fora do escopo: editor colaborativo simultâneo, CRDT e reavaliação automática de textos históricos.

Integração antecipada, 13/10/2026: `WritingFeedbackProvenance` identifica regra
e rubrica no workspace e no Caderno. Resultados legados recebem aviso de
limitações, sem parecer que foram corrigidos. O título de sucesso agora diz
“Critérios automáticos atendidos”. Essa mudança não resolve resposta tardia
para texto editado nem conflito de rascunho. O avanço posterior de sessão está
registrado separadamente em FE-37, seguido da fila transacional no quarto incremento.
Testes de componente cobrem a regra atual, legado e abertura do histórico.

## Sprint 39 Áudio e continuidade offline

Achados: F05, F07, B06, B07 e B08.

### Entregas

- [ ] Unificar indicação de tamanho/duração permitidos de voz com o contrato da API e a configuração do proxy.
- [ ] Tratar upload 413, formato não suportado, token expirado e falha de rede com opção de tentar novamente sem perder a gravação local.
- [ ] Controlar o ciclo do microfone para encerrar tracks e timers também quando a permissão chegar depois da troca de rota.
- [ ] Definir retomada de áudio por revisão e momento de alteração, sem preferir uma posição remota antiga só por existir.
- [ ] Serializar avanço, pause e término; uma gravação atrasada não deve restaurar posição que acabou de ser limpa.
- [ ] Mostrar separadamente áudio online, conteúdo textual disponível offline e envio pessoal pendente.
- [ ] Implementar ciclo de atualização do service worker com versão de release, capacidade/expiração do cache e aplicação segura de atualização.
- [ ] Informar consumo e indisponibilidade da assistência segundo a reserva/cota do backend, sem tratar 429 como erro genérico.
- [ ] Integrar sinais de atividade/visibilidade para a métrica de tempo do backend, com privacidade e baixo volume de eventos.

### Critérios de aceite

1. Um arquivo permitido pelo contrato passa também pelo Nginx; maior que o limite falha de forma consistente e compreensível.
2. Nenhum indicador de microfone permanece ativo após sair da prática, inclusive se o usuário aceitar a permissão tardiamente.
3. Avanço local mais recente não é perdido ao recuperar conexão; conflito entre dispositivos tem regra documentada.
4. Após terminar o áudio, PUT atrasado não recria posição; ordem inversa dos eventos também tem teste.
5. Atualização do PWA não destrói rascunho/fila/sessão e não cacheia áudio sem licença e ação explícita.
6. Aba oculta ou sessão abandonada não é apresentada como estudo ativo contínuo; reconexão não duplica eventos de tempo.
7. Safari/iOS e Chromium geram/reproduzem formato aceito, ou apresentam alternativa clara quando recurso não estiver disponível.

Fora do escopo: baixar todos os MP3 da VOA, reconhecimento de fala garantido em todos os navegadores e nota automática de pronúncia apresentada como avaliação especializada.

## Sprint 40 Histórico e controle dos dados pessoais

Achados: B09, B11, D04 e D07. Dependências: exportação versionada e política editorial BE-40/DB-40.

### Entregas

- [ ] Criar área “Meus dados” para exportação, escopo dos arquivos e exclusão/limpeza com confirmação proporcional ao risco.
- [ ] Diferenciar exportação JSON de backup de conta e download dos áudios pessoais.
- [ ] Apresentar estados de preparação, processamento, conclusão, expiração e falha de exportações grandes, se o contrato adotar jobs.
- [ ] Identificar versão do conteúdo em tentativa/checkpoint e permitir consultar resultado histórico sem apresentá-lo como correção da versão atual.
- [ ] Exibir conteúdo arquivado no histórico conforme política definida, sem criar links quebrados para aula indisponível.
- [ ] Oferecer limpeza deste dispositivo separada de exclusão na conta, com inventário de itens não sincronizados.
- [ ] Apresentar mudança de regra de conclusão de curso com justificativa e versão, preservando o significado de “certificado interno”.

### Critérios de aceite

1. O usuário entende quais dados são exportados, se inclui áudio e por quanto tempo o download fica disponível.
2. Checkpoint e sessão de prática exportados podem ser localizados no histórico correspondente.
3. Uma edição de conteúdo não altera silenciosamente o enunciado/feedback exibido numa tentativa histórica.
4. Limpeza local não remove dados remotos; exclusão remota exige autenticação/confirmação de acordo com o contrato.
5. Rascunhos e respostas pendentes nunca são apagados por uma ação rotulada apenas “limpar cache”.
6. Os fluxos funcionam com teclado e comunicam erros/irreversibilidade em linguagem clara.

Fora do escopo: envio automático por e-mail, armazenamento em serviços externos e mudança de política de retenção sem decisão do responsável.

## Sprint 41 Acessibilidade e interfaces sustentáveis

Achados: F09, F11 e B10.

### Entregas

- [ ] Definir título, foco e anúncio de contexto nas mudanças de rota, mantendo retorno de foco para drawer e diálogos.
- [ ] Tornar o fundo de modal realmente inerte e testar navegação virtual do leitor de tela, não só Tab.
- [ ] Homologar VoiceOver macOS/iOS, TalkBack Android e contraste forçado em Windows real; atualizar a matriz de acessibilidade existente com rotas atuais.
- [ ] Acrescentar testes WebKit e Firefox a uma matriz suportada e realista, sem considerar emulação mobile como dispositivo real.
- [ ] Paginar históricos de escrita, voz e caderno; estados vazios e “carregar mais” com foco preservado.
- [ ] Refatorar componentes extensos por responsabilidade: gravação, transporte, histórico, navegação e apresentação de feedback.
- [ ] Organizar estilos e tokens sem trocar framework; preservar design atual e comportamento responsivo.
- [ ] Medir performance de carga e interação nas rotas Hoje, aula, laboratório e caderno com dados sintéticos representativos.

### Critérios de aceite

1. Percurso completo sem mouse: autenticação, curso, aula, player, exercício/classificação, escrita, revisão, exportação e saída.
2. Zoom/reflow continuam aprovados; foco não fica encoberto por barras fixas e conteúdo não exige rolagem horizontal desnecessária.
3. Evidência real de cada plataforma inclui versão, data, cenário e resultado; pendência não recebe status “aprovado” por axe.
4. Alterar filtro com histórico paginado não mistura curso/usuário nem perde a indicação de carregamento/erro.
5. Orçamento de bundle existente continua aprovado. Métricas de experiência recebem baseline e meta antes de definir um percentual arbitrário de melhoria.
6. A refatoração mantém regressões de todas as modalidades; testes verificam comportamento do aluno, não detalhes internos de implementação.

Dependência externa: acesso aos dispositivos e leitores de tela. Falta de equipamento mantém somente essa homologação pendente; não invalida entregas técnicas verificadas nem autoriza inventar resultado.

## Sprint 42 Homologação da experiência de estudo

Achados: F09 a F11, B12 e pendências pedagógicas da auditoria.

### Entregas

- [ ] Executar jornada integrada com rede estável, rede lenta, offline, expiração de sessão e atualização de versão.
- [ ] Revisar textos de interface para explicar diferença entre correção objetiva, rubrica de escrita, assistência e autoavaliação oral.
- [ ] Exibir origem/período/amostra das competências e não apresentar poucos acertos repetidos como certificação de nível.
- [ ] Separar duração de cada item e orçamento de sessão curta de revisão, caso esse modo seja aprovado no refinamento.
- [ ] Concluir ou registrar individualmente a conferência auditiva humana dos cues pendentes, com associação à aula/versão.
- [ ] Consolidar guia do aluno sobre retomada, sincronização, limites offline, privacidade e recuperação de erros.
- [ ] Registrar a matriz de aceite final e pendências residuais, sem marcar o pacote inteiro como concluído com homologações obrigatórias abertas.

### Critérios de aceite

1. Aluno consegue estudar uma aula completa e retomar de outro dispositivo sem perda silenciosa de escrita/progresso.
2. Todas as respostas da fila têm destino verificável: confirmada, pendente ou bloqueada com explicação.
3. Erros recuperáveis mantêm uma ação possível e não exigem conhecimento de Docker/API.
4. Evidências de listening e leitores de tela são humanas quando o critério depende de percepção/tecnologia assistiva real.
5. Mudanças de competência/conclusão são compreensíveis e versionadas; não se promete certificado oficial VOA.

## Regras de conclusão por pacote

- Não usar `make test-api` na base atual até D01 ser resolvido.
- Testes unitários/integração/E2E executados com ambiente, versão e resultado registrados.
- Cada correção possui vínculo com o achado e teste de regressão; cada melhoria possui comportamento esperado e medida de sucesso.
- Não remover dados locais antigos sem migração e opção de recuperação.
- Nenhum novo fluxo coloca tokens em localStorage nem transforma conteúdo privado em cache público.
- Estado inicial desta lista permanece “planejado”; caixas serão marcadas somente numa implementação autorizada posteriormente.
