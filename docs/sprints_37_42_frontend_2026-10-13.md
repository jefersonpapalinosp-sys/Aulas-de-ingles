# Sprints de frontend para confiabilidade e experiência de estudo

Atualização: 16 de outubro de 2026. **Implementação FE-39G/H concluída e FE-40, FE-41 e FE-42 tecnicamente concluídas e implantadas no ambiente de estudo.** A promoção da `main` foi realizada com backup anterior, clone restaurado, gates e backup posterior; consulte a [Sprint 43](sprint_43_implantacao_estudo_2026-10-16.md). O aceite integral ainda depende das homologações físicas, auditivas e pedagógicas registradas neste plano; nenhuma recebeu aprovação fictícia.

Schema do estudo: `a42c7d1e9f20`. O frontend de `localhost:5181` usa o build atual com PWA; desenvolvimento 5180 usa Vite e não registra o service worker. O rollout preservou o histórico e os arquivos de voz. Consulte o registro vigente antes de usar comandos históricos.

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

### Incremento 39A — 14/10/2026 (disponível no desenvolvimento)

Retomada de áudio e tempo ativo implementados na branch `sprint/39-audio-tempo-ativo`.
A Sprint 39 **não está encerrada**. Não houve commit/push/merge deste incremento.
O banco dev foi alinhado de `b84e2c7a9d31` para `e17b5fad0264` após backup/restore/ensaio,
e API/worker/web de 5180 foram reiniciados. As 23 verificações HTTP pelo proxy passaram,
incluindo áudio e tempo; a conta temporária foi removida. Não houve nova homologação
visual/de dispositivo nesta manutenção. 5181 permanece na Sprint 38, sem alteração.
Regressão final do build otimizado aprovada: 112 cenários Playwright, desktop e mobile
emulado, em 6,1 minutos. Upload/microfone avançaram no incremento 39B abaixo; PWA e cotas
assistidas continuam pendentes. Implantação em 5181 exige manutenção própria.

Contrato de retomada:

- Fila por conta/mídia/operação; revisão e UUID imutáveis em retries. Cache confirmado
  não é confundido com confirmação atual da conta. GET antigo não apaga fila offline.
- Conclusão enfileirada como posição zero e `completed=true`; eventos atrasados
  de pause/timeupdate não revertem conclusão. API mantém tombstone, não apaga a linha.
- HTTP 409 exige escolha entre dispositivo e conta. Posição antiga v1 sem data
  não vence automaticamente uma posição remota. Relógio local não decide o vencedor.
- Reconexão/foco reprocessam a fila, sempre verificando identidade, token e perfil
  confirmado. Falhas de quota/leitura/remoção são visíveis; limite de 1.000 comandos
  por conta/mídia, sem descarte automático de operações pendentes.

Contrato de tempo:

- Somente jornada guiada: aba visível/em foco e interação nos últimos 120 segundos,
  ou áudio em reprodução. Não coleta tecla, texto digitado ou identificador permanente
  do dispositivo. É estimativa de atividade, não comprovação de atenção/aprendizagem.
- Relógio monotônico, âncora do servidor e blocos de aproximadamente 15 segundos;
  saltos maiores que 2,5 segundos não são contados. Saída persiste o bloco parcial.
- Primeiro uso exige conexão para obter âncora. Eventos já ancorados podem aguardar
  offline por até 7 dias; eventos vencidos permanecem locais com aviso e não entram
  na meta. Limite de 5.000 eventos pendentes por conta; falha de storage é explícita.
- Plano semanal recebe fuso IANA (padrão UTC, editável); início na segunda-feira
  local. Histórico estimado antigo fica separado dos minutos ativos da semana.

Validação: API com 802 testes; frontend com 289 testes; cenários E2E registrados no README.
Build, lint e tipos aprovados. A primeira medição de 176,0 KiB gzip reprovou. A
minificação Terser 5.51.2, fixada no lockfile, com 4 passes conservadores e 2 workers,
reduziu para **176.099 bytes / limite 176.128 bytes (171,97 KiB / 172 KiB)**.
Limites individuais também passaram; nenhum limite ou navegador-alvo foi alterado.
Margem de somente 29 bytes: a próxima entrega deve medir novamente, não presumir
folga. Referência de configuração: [Vite 6 — build](https://v6.vite.dev/config/build-options#build-minify).
Há testes unitários de sinais de foco/visibilidade/ociosidade; E2E
injeta visibilidade no DOM porque Chromium headless mantém páginas em foco.
Isso não homologa suspensão/foco do sistema operacional nem Safari/iOS reais.

### Incremento 39B — envio de voz e ciclo do microfone (14/10/2026)

- A prática oral consulta `GET /api/speaking/policy`: teto padrão de **2.000.000
  bytes decimais**, duração declarada de até **30 segundos** e formatos permitidos.
  A configuração da API pode reduzir o teto, nunca ultrapassar o Nginx. Sem conseguir
  consultar a política, é possível gravar/ouvir/baixar localmente, mas não enviar.
- Limites e erros de formato/tamanho ficam visíveis. HTTP 413, 415, 401/403, 408,
  409 e falha de conexão têm orientação; a gravação local não é apagada na falha.
  Retry do PUT usa o mesmo ID e Blob; não faz DELETE compensatório de um envio
  possivelmente confirmado. A autoavaliação não muda após criar a tentativa.
- Se a sessão expirar durante o envio, uma referência temporária ao Blob pode ser
  recuperada por até **cinco minutos**, na **mesma aba, conta, aula e trecho**,
  sem recarregar/fechar a aba. Só memória; não usa IndexedDB/localStorage nem reenvia
  automaticamente. Recuperação exige novo consentimento. Download local fica disponível.
- `VoiceRecorder` invalida permissões tardias, encerra tracks/timer ao sair/cancelar,
  trata erro de gravação e escolhe WebM/MP4/Ogg conforme `isTypeSupported`, não por
  identificação do navegador. Libera também URLs temporárias na recuperação em StrictMode.
- Módulos compartilhados de aula/prática foram agrupados no chunk lazy `lesson-study`,
  sem mudar os tetos de bundle nem os navegadores-alvo. O E2E verifica que Hoje não
  antecipa esse download; aulas/prática podem carregar mais recursos juntos.

Validação: **307 testes frontend**, TypeScript e ESLint aprovados; seis novos cenários
Playwright em Chromium desktop/mobile emulado passaram pelo Nginx real do laboratório
5198. Cobrem limite exato e excedido com/sem Content-Length, retry após resposta perdida
e permissão concedida depois da troca de etapa. A suíte backend tem **820 testes**.
Microfone é simulado; não é homologação física, de Safari/iOS ou Android real. Seleção
de MP4 tem teste de capacidade simulado, não certificação de gravação/reprodução no Safari.

Regressão completa aprovada: **118 E2E (5,7 min)**. Depois do ajuste final de liberação
de URLs temporárias, os 307 testes frontend e os seis E2E específicos foram repetidos
com sucesso. Build final: **172.624 bytes gzip / limite 176.128 bytes** (168,58/172 KiB),
sem aumentar orçamento; laboratório parado, volumes sintéticos preservados.

Não há persistência durável da gravação não enviada. Resposta perdida no POST inicial
sem ID conhecido ainda pode deixar metadado `pending`; a idempotência garantida aqui
é a do PUT de uma tentativa conhecida. Não prometer recuperação após fechar a aba.
Na entrega 39B, codec/duração decodificados, PWA, cotas e manutenção ficaram pendentes;
o avanço de inspeção de arquivos está registrado no incremento 39C abaixo.
Referências: [permissão de microfone](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
e [capacidade do gravador](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/isTypeSupported_static).

### Incremento 39C — contrato de áudio efetivamente inspecionado (14/10/2026)

O servidor agora decodifica o arquivo antes de publicá-lo. A interface mostra o teto
real de 30 s/2.000.000 bytes e mono/estéreo, enquanto o timer local usa o alvo de
29 s da política para permitir o fechamento do codec. Não trunca nem altera a voz.
HTTP 422 (arquivo inválido/duração excedida) recebe orientação específica e mantém
download local; o teste de retry inclui esse status. Limites de recuperação de 39B
permanecem: memória transitória, mesma conta/contexto e consentimento renovado.

**308 testes frontend**, ESLint/TypeScript, build e orçamento aprovados. Bundle:
**172.697 bytes gzip / 176.128 bytes permitidos** (168,65/172 KiB). Oito cenários
de upload no navegador passaram contra API/Nginx Linux, incluindo MIME falso e
31 segundos reais declarados como 1 ms. Silêncio WAV do gravador simulado substitui
strings inválidas nos testes de integração. Testes de codecs reais no backend não
equivalem a homologação física/Safari. PWA/cotas continuam sem fechamento.

Regressão completa: **120 E2E aprovados em 6,4 min**, incluindo desktop e mobile
simulados. Isso não substitui testes com microfone e dispositivos reais.

### Integração 39D — sem nova interface (14/10/2026)

A persistência e a quarentena administrativa foram reforçadas no backend, sem mudar
rotas, respostas ou controles do aluno. Nenhuma gravação do aluno é movida por uma
ação automática da interface. Download local e retry de 39B/C continuam vigentes.
O operador não tenta recuperar áudio perdido apenas na memória do navegador e não
publica uma tentativa `pending` por suposição. PWA, cotas e homologações reais
continuam pendentes; o incremento operacional não representa fechamento de FE-39.

Regressão direcionada: **8 E2E de upload aprovados em 19,9 s**, desktop/mobile
simulados contra a imagem Linux atual. Sem reexecução dos 120 E2E ou 308 testes
frontend completos nesta entrega; os números de 39C permanecem evidência histórica.

### Incremento 39E — PWA, cache limitado e estados offline (14/10/2026)

- O build gera versão por SHA-256 do worker, HTML, assets e manifesto. A instalação
  confere o hash do HTML e prepara somente entrada/CSS/imports estáticos; não
  antecipa o chunk de estudo. Assets das outras telas entram no cache ao visitá-las.
- Sem `skipWaiting`, reload automático ou apagamento de storage pessoal. Nova
  versão aguarda **todas** as abas/janelas anteriores fecharem. Aviso orienta salvar
  textos e enviar/baixar voz antes de fechar. Falha de instalação conserva a versão
  anterior; limpeza das versões anteriores ocorre na ativação segura.
- Painel recolhível **Offline e atualizações** apresenta quantidade/bytes de textos,
  validade da aula atual, falha de armazenamento, atualização aguardando e verificação
  explícita. Limpeza exige confirmação e apaga **somente textos públicos**, não
  rascunhos, fila IndexedDB, sessão, voz ou dados remotos.
- Áudio é identificado como online mesmo quando a licença permitir cache; não existe
  download offline implícito. Gravação local sem confirmação de envio tem aviso
  próprio e não é confundida com a fila de respostas dos exercícios.
- Consultas editoriais alcançam o worker offline em vez de ficarem pausadas pelo
  React Query. A leitura privada da jornada pode falhar e liberar a retomada local;
  isso **não** torna essa resposta cacheável nem muda o transporte das mutações.

Limites por release (bytes do corpo, sem prometer tamanho físico exato do navegador):

| Cache | Quantidade | Total / item | Validade máxima |
| --- | --- | --- | --- |
| Shell | 3 | 1 MiB / 512 KiB | 30 dias |
| Assets permitidos pelo build | 64 | 8 MiB / 2 MiB | 30 dias |
| JSON editorial público | 120 | 8 MiB / 512 KiB | 7 dias |

Escritas/podas são serializadas; expiração é verificada no acesso, não por um job
em segundo plano. Enquanto abas antigas estão abertas, caches de releases anteriores
podem coexistir e esses limites **não são uma cota global do dispositivo**. O navegador
pode desalojar storage. Não há promessa de funcionar offline em telas nunca abertas,
em login novo ou após expiração/desalojamento. Após atualizar, abrir as aulas online
novamente prepara o cache público da nova versão.

API pública exige marcador explícito `X-Aulas-Offline: public-text-v1`, JSON 200 e
ausência de política privada; worker usa requisição anônima e chaves sem credenciais.
Dados de conta, erros privados, uploads, áudio/vídeo e origens externas não são
interceptados. Navegações usam um único shell sem armazenar URLs individuais.

Validação 39E: **334 testes frontend, 124 E2E (6,2 min) e 2 ensaios de lifecycle
PWA aprovados**; lint/tipos/build e orçamento original aprovados (170,2 KiB gzip
de assets JS/CSS, worker adicional medido separadamente no runbook). Nenhuma
homologação de Safari/iOS, VoiceOver/TalkBack ou Windows real foi adicionada. PWA é exercitado em
build/5198 e servidor sintético 5196; o Vite 5180 não registra o worker. Estudo 5181
continua na Sprint 38. Cotas/jobs/retenção de assistência e rollout seguem abertos.

Referências: [ciclo de vida do service worker](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers),
[Cache API e expiração controlada pela aplicação](https://developer.mozilla.org/en-US/docs/Web/API/Cache).
Operação: [runbook 39E](operacao_sprint_37.md#sprint-39e--pwa-e-cache-público-em-14102026).

### Entregas

- [x] Unificar indicação de tamanho/duração permitidos de voz com o contrato da API e a configuração do proxy (39B; duração real decodificada em 39C).
- [x] Tratar upload 413, formato não suportado, token expirado e falha de rede com opção de tentar novamente sem perder a gravação local (39B; limites de recuperação acima).
- [x] Controlar o ciclo do microfone para encerrar tracks e timers também quando a permissão chegar depois da troca de rota (39B; homologação em dispositivos reais pendente).
- [x] Definir retomada de áudio por revisão e momento de alteração, sem preferir uma posição remota antiga só por existir (39A local).
- [x] Serializar avanço, pause e término; uma gravação atrasada não deve restaurar posição que acabou de ser limpa (39A local).
- [x] Mostrar separadamente áudio online, conteúdo textual disponível offline e envio pessoal pendente (39E; disponibilidade medida, sem prometer download de mídia).
- [x] Implementar ciclo de atualização do service worker com versão de release, capacidade/expiração do cache e aplicação segura de atualização (39E; ativação após fechar todas as abas, sem reload forçado; limites por release).
- [x] Informar consumo, cota e indisponibilidade sem tratar 429 como erro genérico; 39G/H acrescenta heartbeat/idade e quantidade da fila da própria conta.
- [x] Integrar sinais de atividade/visibilidade para a métrica de tempo do backend, com privacidade e baixo volume de eventos (39A local).

### Critérios de aceite

1. Um arquivo permitido pelo contrato passa também pelo Nginx; maior que o limite falha de forma consistente e compreensível.
2. Nenhum indicador de microfone permanece ativo após sair da prática, inclusive se o usuário aceitar a permissão tardiamente.
3. Avanço local mais recente não é perdido ao recuperar conexão; conflito entre dispositivos tem regra documentada.
4. Após terminar o áudio, PUT atrasado não recria posição; ordem inversa dos eventos também tem teste.
5. Atualização do PWA não destrói rascunho/fila/sessão e não cacheia áudio sem licença e ação explícita.
6. Aba oculta ou sessão abandonada não é apresentada como estudo ativo contínuo; reconexão não duplica eventos de tempo.
7. Safari/iOS e Chromium geram/reproduzem formato aceito, ou apresentam alternativa clara quando recurso não estiver disponível.

Fora do escopo: baixar todos os MP3 da VOA, reconhecimento de fala garantido em todos os navegadores e nota automática de pronúncia apresentada como avaliação especializada.

### Incremento 39F — saldo compartilhado e reenvio da escrita (14/10/2026)

Escrita e speaking exibem o mesmo saldo: disponível, reservado, utilizado, renovação
à meia-noite UTC e custo confirmado/parcial. O texto informa que exclusões/falhas
após iniciar processamento não devolvem cota. Consulta privada é atualizada após
ações; polling enquanto há reservas e atualização periódica quando assistência está
habilitada mantêm a informação do worker sem publicar saldo em cache offline.

Uma análise de escrita recebe UUID. Perda de resposta conserva a chave para o retry
do mesmo texto/contexto; 409 orienta consultar histórico, mantendo o editor intacto.
Chave é de memória, não uma fila offline: recarregar a aba perde essa deduplicação.
Texto/conta/proposta diferentes geram outra chave; sucesso encerra a operação.
Transcrição 429 continua distinguida de indisponibilidade do provedor, e exclusão
atualiza o saldo sem presumir reembolso. Nenhum spinner substitui a correção local.

Testes de interface incluem reenvio por Enter em Chromium desktop/mobile simulado,
com gateway/status interceptados. Essa simulação não prova a cota real: a admissão
concorrente é ensaiada separadamente no PostgreSQL. Sem nova homologação em leitor
de tela real. Contrato OpenAPI/tipos regenerados, sem dependência nova.
[Evidências e pendências 39F](operacao_sprint_37.md#sprint-39f--reservas-e-cotas-assistidas-em-14102026).

### Incremento 39G/H — conclusão da implementação (15/10/2026)

- Painel assistido informa processador ativo/sem sinal recente, quantidade própria
  na fila e espera aproximada. Não exibe volume ou conteúdo de outros estudantes.
- Gravação marcada pelo operador como ausente/alterada mantém histórico e exibe
  orientação; reprodução e pedido de transcrição ficam bloqueados. Restauração
  validada usa nova chave de arquivo e preserva identidade da tentativa.
- **338 testes frontend**, lint/typecheck/build/orçamento aprovados; **126 E2E**
  desktop/mobile emulados e **2 PWA** aprovados. A primeira execução da jornada
  teve timeout transitório; três repetições e a segunda suíte completa passaram.
- Backend e migrations incluem o rollout coordenado dos incrementos anteriores,
  após backup/restore em clones exclusivos e smoke autenticado sem provedores.

O navegador interativo não estava disponível; a habilidade de navegador confirmou
essa limitação. Microfone dos E2E é sintético. **Não homologados:** gravação e
reprodução física Safari/macOS/iPhone, suspensão do sistema e dispositivos móveis
reais. O critério de aceite 7 continua pendente; não confundir implementação
concluída com aprovação integral da sprint. Checklist no [runbook 39G/H](operacao_sprint_37.md#sprint-39gh--retenção-integridade-e-implantação-em-15102026).

## Sprint 40 Histórico e controle dos dados pessoais

Achados: B09, B11, D04 e D07. Dependências: exportação versionada e política editorial BE-40/DB-40.

### Entregas

- [x] Criar área “Meus dados” para exportação, escopo dos arquivos e exclusão/limpeza com confirmação proporcional ao risco.
- [x] Diferenciar exportação JSON de backup de conta e download dos áudios pessoais (40A).
- [x] Manter estados explícitos no contrato síncrono atual; jobs de exportação grande não foram adotados e volumes acima do teto falham integralmente, sem estado fictício.
- [x] Identificar versão do conteúdo em tentativa/checkpoint e permitir consultar resultado histórico sem apresentá-lo como correção da versão atual.
- [x] Exibir conteúdo capturado no histórico conforme política definida, sem criar links quebrados para aula indisponível ou reconstruir legado ausente.
- [x] Oferecer limpeza deste dispositivo separada de exclusão na conta, com inventário de itens não sincronizados.
- [x] Apresentar a regra atual de conclusão com justificativa e versão, preservando o significado de “certificado interno”.

### Critérios de aceite

1. O usuário entende quais dados são exportados, se inclui áudio e por quanto tempo o download fica disponível.
2. Checkpoint e sessão de prática exportados podem ser localizados no histórico correspondente.
3. Uma edição de conteúdo não altera silenciosamente o enunciado/feedback exibido numa tentativa histórica.
4. Limpeza local não remove dados remotos; exclusão remota exige autenticação/confirmação de acordo com o contrato.
5. Rascunhos e respostas pendentes nunca são apagados por uma ação rotulada apenas “limpar cache”.
6. Os fluxos funcionam com teclado e comunicam erros/irreversibilidade em linguagem clara.

Fora do escopo: envio automático por e-mail, armazenamento em serviços externos e mudança de política de retenção sem decisão do responsável.

### Incremento 40A — portabilidade e inventário local, 15/10/2026

Implementado `/meus-dados`, acessível pelo menu e pelo caderno. Exportação explícita,
estados de preparação/falha/nova tentativa, download do JSON e de cada áudio com a
sessão autenticada. O download iniciado não é apresentado como salvamento confirmado.
Saída da rota cancela a requisição; dados do JSON não vão para storage ou React Query.
Manifesto permanece somente na memória da tela. A rota privada não entra no cache PWA.

Inventário por conta mostra rascunhos, fila pendente/bloqueada, comandos de posição,
eventos de tempo e cópias de progresso/autoavaliação. Falha de armazenamento aparece
como **não confirmado**, não como zero. Recuperação de voz em memória é observada
sem consumir o áudio; outras abas e dados não persistidos têm limitação explícita.
Limpeza confirma **somente textos públicos**, preservando dados pessoais e remotos.
A exclusão integral local/remota ainda não foi implementada.

O contrato síncrono 2.0 não cria jobs nem arquivos temporários no servidor. Não há
link público com prazo: o áudio exige a conta atual e é validado novamente no
download; o JSON já baixado não expira nem pode ser revogado remotamente.
Contas acima de 10 mil registros/20 MiB recebem erro explícito, sem exportação parcial.

**Sprint 40 em andamento.** Próximos incrementos: 40B identidade/versionamento,
arquivamento e prévia do seed; 40C procedimento de exclusão e decisão sobre backups;
40D interfaces históricas, conclusão/aceite e implantação no estudo. Não marcar os
itens agregados de exclusão/histórico como concluídos apenas por entregar esta tela.
Evidências e limites no [runbook 40A](operacao_sprint_37.md#sprint-40a--exportação-e-meus-dados-em-15102026).

### Continuidade 40B.1 — proteção editorial, 15/10/2026

Entrega de infraestrutura do seed, sem mudança de interface, rotas, contrato HTTP
ou bundle: prévia read-only e bloqueio de alterações/omissões em conteúdo existente.
Isso impede o seed de reinterpretar ou apagar referências históricas, mas **não**
entrega visualização de snapshots ou conteúdo arquivado. FE-40 permanece em
andamento; depende do contrato de identidade/versionamento/arquivamento 40B.2.
[Evidências e limitações](operacao_sprint_37.md#sprint-40b1--prévia-e-barreira-editorial-do-seed-em-15102026).

### Continuidade 40B.2a — contrato histórico disponível para integração

Novo contrato privado por evidência: `/api/me/history/{kind}/{evidence_id}/content`,
com estados `available/unavailable`; ausência não deve ser exibida como correção
da versão atual. Exportação 2.0 inclui `content_snapshots` opcionais, sem quebrar
o download existente. Tipos gerados atualizados; sem novo componente ou nova rota
de tela nesta etapa. IDs de itens de prática estão na seção `practice_items` da
exportação; a navegação histórica amigável ainda pertence à integração FE-40.

Não marcar a tela de histórico como entregue: laboratório/prática e apresentações
legadas ainda dependem da integração explícita dos snapshots. Captura permanece
desligada no DEV/estudo até o rollout ensaiado. Regressão frontend, tipagem e bundle
foram conferidos; não houve nova homologação física de acessibilidade.
[Evidências 40B.2a](operacao_sprint_37.md#sprint-40b2a--snapshots-privados-de-evidências-em-15102026).

### Continuidade 40B.2b.1 — contrato de disponibilidade, 15/10/2026

Backend agora recusa novas atividades também por IDs diretos quando curso/unidade
não estão publicados; catálogo omite arquivados e não apresenta aulas/checkpoints
como disponíveis em curso planejado. Dados privados já existentes continuam
consultáveis por seu dono. Checkpoint não incorpora mídia de outra unidade arquivada.

Não há tela nova nem alteração do schema OpenAPI neste incremento. Faltam mensagens
de conteúdo arquivado nas telas históricas, navegação sem links quebrados e política
de invalidação dos textos públicos já cacheados. Não confundir esconder conteúdo na
API online com revogar cópias offline. Nenhuma unidade foi arquivada no DEV/estudo.
[Contrato e evidências](operacao_sprint_37.md#sprint-40b2b1--disponibilidade-e-prévia-de-arquivamento-em-15102026).

### Continuidade 40B.2b.2 — identidade para futura integração histórica, 15/10/2026

Backend/seed agora têm chaves editoriais imutáveis para seis tipos de conteúdo.
Novos snapshots privados podem incluir essas chaves como metadados, mantendo o
envelope 1.0; não usar conteúdo atual para preencher ausência histórica. Rotas e
IDs públicos atuais permanecem iguais, sem alteração de OpenAPI/tipos ou tela nova.

**347 testes frontend aprovados** neste incremento. Ainda faltam consumo histórico
nas telas, mensagens de arquivados, navegação e política de cache/offline. As chaves
não invalidam cópias antigas sozinhas nem autorizam atualização do conteúdo existente.
Nenhuma migration ou ativação de snapshots em DEV/estudo. FE-40 continua parcial.
[Contrato e evidências](operacao_sprint_37.md#sprint-40b2b2--identidade-editorial-estável-em-15102026).

### Continuidade 40B.2b.3 — arquivamento ensaiado, interface ainda pendente

Aplicação auditada disponível apenas por CLI opt-in para ensaios locais. Novas
admissões podem receber 503 transitório durante manutenção; após arquivamento,
permanece a política 404 para conteúdo indisponível e leitura privada do histórico.
Repetição de operação pessoal continua respeitando seus contratos anteriores.

Não foi criada tela administrativa ou histórica, nem alterado OpenAPI/tipos.
**347 testes frontend**, lint, tipagem, build e orçamento aprovados (171,9 KiB gzip).
API online não invalida cópias offline por si só. Mensagens de arquivados, links,
cache, conclusão versionada e aceite integrado continuam pendentes; por isso
prod/public permanecem bloqueados e DEV/estudo não receberam arquivamento.
[Contrato e evidências](operacao_sprint_37.md#sprint-40b2b3--arquivamento-auditado-local-em-15102026).

### Continuidade 40B.2c — contrato de proveniência sem data inventada

O único efeito no frontend é contratual: `LessonVersion.reviewed_at` agora aceita
`null`, representando data desconhecida. OpenAPI e tipos TypeScript foram regenerados;
as telas atuais não exibiam a data e não precisaram de mudança visual. Nenhuma
rubrica do DEV foi atualizada nem feedback histórico recalculado.

**347 testes frontend**, lint, TypeScript, build e orçamento de 171,9 KiB gzip
aprovados. Uma futura interface editorial deve exibir “data não comprovada” e
pendência pedagógica, nunca converter `null` em 07/10 ou na data atual.
[Resultado da auditoria](operacao_sprint_37.md#sprint-40b2c--auditoria-de-rubricas-e-proveniência-15102026).

### Continuidade 40B.2d — ausência histórica honesta na fala

O contrato de prática inclui o ID do item e o estado do snapshot; feedbacks de
escrita e tentativas/transcrições de fala também recebem
`historical_content_status`. No histórico oral, `cue_text` vem da captura e pode
ser `null`: nesse caso a tela apresenta “Texto original indisponível”, mantém o
áudio reproduzível e oculta a ação de transcrição, sem mostrar a legenda atual
como se fosse a usada na gravação. OpenAPI e tipos foram regenerados.

Esta etapa ainda não cria uma central visual para abrir todo snapshot de prática
ou checkpoint. A consulta privada já é correlacionável pelo ID, mas a interface
histórica completa e o conteúdo arquivado permanecem no restante da FE-40.

### Continuidade 40B.2e — contrato de listening independente da ordem

`LessonMediaOut` agora entrega `listening_exercise_id`, que permanece apontando
para o mesmo exercício quando a ordem visual muda. O campo
`listening_exercise_position` continua no contrato durante a transição, marcado
como obsoleto; nenhuma tela deve adotá-lo como nova identidade. OpenAPI e tipos
TypeScript foram regenerados.

As telas atuais já selecionavam atividades de listening pelo conjunto recebido e
não exigiram mudança visual. Este incremento não executou uma reordenação nem cria
interface editorial. Histórico completo de prática/checkpoint, conteúdo arquivado,
cache/offline e rollout continuam pendentes; DEV/estudo não foram alterados.

### Continuidade 40B.2f — nenhuma mutação ou interface editorial

A prévia de reordenação é uma ferramenta operacional de backend e não modifica o
contrato OpenAPI, os tipos TypeScript ou a ordem apresentada ao aluno. Não foi criada
tela administrativa, nem houve reordenação dos seeds reais. O contrato garante que
uma futura troca de ordem preserve os IDs já consumidos pelo frontend e exija versão
nova antes de qualquer apply.

Por isso não há alegação de aceite visual neste incremento. Interface histórica
completa, comunicação de conteúdo arquivado, invalidação de cache/offline e teste
integrado após uma reordenação real continuam pendentes na FE-40.

### Continuidade 40B.2g — IDs preservados, interface ainda pendente

O apply operacional preserva os IDs numéricos e UUIDs consumidos pelo frontend;
somente a posição visual muda e a versão é incrementada. Não houve alteração de
OpenAPI, tipos TypeScript, componentes ou seeds reais neste incremento.

O ensaio técnico não substitui o aceite da experiência depois de uma reordenação
curricular real. Ainda faltam validar retomada, histórico, foco, cache/offline e
explicação de versão no frontend antes de liberar esse fluxo no ambiente de estudo.

### Fechamento técnico FE-40C/40D — exclusão, histórico e regra versionada, 16/10/2026

A tela “Meus dados” agora separa três ações: cache textual público, limpeza privada
somente da conta neste navegador e exclusão remota. A limpeza privada remove fila
offline, recibos, rascunhos, posições, progresso e voz temporária do usuário
selecionado; mantém outras contas, cache editorial e servidor. Um tombstone impede
que fontes v1/v2 restaurem a fila apagada. Falha de storage não vira sucesso visual.

A exclusão remota exige senha, frase exata e confirmação nativa. Após a API confirmar
o banco excluído, a sessão e o cache autenticado são encerrados; arquivo de áudio
pendente recebe mensagem distinta. Outros dispositivos e downloads continuam
explicitamente fora do alcance da ação.

O Caderno ganhou a central paginada “Conteúdo histórico preservado” para exercício,
prática, escrita, fala e checkpoint. Os detalhes são carregados sob demanda da rota
privada, exibem somente o snapshot original e suas versões. Ausência legada não é
substituída pelo seed atual. A lista é global à conta, explica que não segue os
filtros curriculares e não cria link para aula que possa estar arquivada.

Na conclusão, `course-certificate-v1` identifica a regra recalculada no estado atual.
A interface explica que isso não altera resultados históricos nem representa arquivo
já emitido. O significado e o fluxo externo da VOA não foram redefinidos.

Validação dirigida: 45 testes frontend, lint e TypeScript aprovados. A suíte completa,
build e orçamento são registrados no runbook ao final do fechamento integrado.
Homologações físicas da Sprint 41 continuam externas e não são convertidas em aceite
por estes testes. [Política operacional](politica_exclusao_e_backups_dev_2026-10-16.md).

## Sprint 41 Acessibilidade e interfaces sustentáveis

Achados: F09, F11 e B10.

### Entregas

- [x] Definir título, foco e anúncio de contexto nas mudanças de rota, mantendo retorno de foco para drawer e diálogos.
- [ ] Tornar o fundo de modal realmente inerte e testar navegação virtual do leitor de tela, não só Tab.
- [ ] Homologar VoiceOver macOS/iOS, TalkBack Android e contraste forçado em Windows real; atualizar a matriz de acessibilidade existente com rotas atuais.
- [x] Acrescentar testes WebKit e Firefox a uma matriz suportada e realista, sem considerar emulação mobile como dispositivo real.
- [x] Paginar históricos de escrita, voz e caderno; estados vazios e “carregar mais” com foco preservado.
- [x] Refatorar componentes extensos por responsabilidade: gravação, transporte, histórico, navegação e apresentação de feedback.
- [x] Organizar estilos e tokens sem trocar framework; preservar design atual e comportamento responsivo.
- [ ] Medir performance de carga e interação nas rotas Hoje, aula, laboratório e caderno com dados sintéticos representativos.

### Critérios de aceite

1. Percurso completo sem mouse: autenticação, curso, aula, player, exercício/classificação, escrita, revisão, exportação e saída.
2. Zoom/reflow continuam aprovados; foco não fica encoberto por barras fixas e conteúdo não exige rolagem horizontal desnecessária.
3. Evidência real de cada plataforma inclui versão, data, cenário e resultado; pendência não recebe status “aprovado” por axe.
4. Alterar filtro com histórico paginado não mistura curso/usuário nem perde a indicação de carregamento/erro.
5. Orçamento de bundle existente continua aprovado. Métricas de experiência recebem baseline e meta antes de definir um percentual arbitrário de melhoria.
6. A refatoração mantém regressões de todas as modalidades; testes verificam comportamento do aluno, não detalhes internos de implementação.

Dependência externa: acesso aos dispositivos e leitores de tela. Falta de equipamento mantém somente essa homologação pendente; não invalida entregas técnicas verificadas nem autoriza inventar resultado.

### Continuidade 41A — contrato visual preservado

A primeira otimização foi interna ao detalhe da aula: o JSON público permaneceu
idêntico e nenhum componente ou tipo TypeScript mudou. Em ambiente local com a
sonda habilitada, os headers agregados de duração, SQL, bytes e pool podem ser
lidos em mesma origem e estão liberados pelo CORS de desenvolvimento.

Isso ainda não mede Web Vitals, renderização, interação nem as rotas Hoje,
laboratório e caderno no navegador. A entrega de performance frontend da Sprint 41
continua aberta e precisará de dados sintéticos representativos, sem usar o header
de duração da API como substituto da experiência do usuário.

### Continuidade 41B — painel Hoje com contrato estável

A otimização de recomendação não mudou campos, links, prioridade ou estados do
painel Hoje. Uma conta nova continua recebendo a próxima aula; revisão vencida,
retomada incompleta e checkpoint elegível mantêm a ordem anterior. O frontend não
precisou de alteração nem regeneração de tipos.

Os 38 → 8 SQLs medem apenas o trabalho da API. Tempo de carregamento e interação do
painel no navegador, inclusive rede lenta e listas maiores, continuam pendentes.

### Continuidade 41C — Caderno incremental e escopo estável

O Caderno deixou de baixar todas as anotações em uma resposta. A primeira página
tem 20 itens e o botão nativo **Carregar mais anotações** acrescenta a página
seguinte sem substituir o que já está visível. Durante a requisição, a seção mantém
os itens anteriores e anuncia carregamento; o botão só volta se existir outro
cursor. Falhas continuam anunciadas pelo estado de erro da seção.

Curso, unidade, aula e tipo pertencem à chave da consulta. Alterar qualquer filtro
limpa o acumulado e reinicia na primeira página, impedindo mistura visual entre
escopos. Mutações recarregam a primeira página, e o contrato gerado evita cursores
montados pelo frontend. Quatro testes da página cobrem CRUD, segunda página,
histórico de escrita e exportação.

A implementação reutiliza `useQuery` já presente, formata datas uma vez por módulo
e mantém o carregamento tardio do Caderno. Passaram 349 testes frontend, TypeScript,
ESLint e build. O bundle ficou em **176.122 bytes gzip (171,99 KiB)**, seis bytes
abaixo do teto inalterado de 172 KiB. O fluxo ainda precisa de medição humana no
navegador com 1 mil/10 mil itens, rede lenta e teclado; a margem de bundle exige
atenção no próximo incremento.

### Continuidade 41D — escala validada sem ampliar o bundle

O incremento não alterou componentes, rotas visuais nem o contrato TypeScript. O
laboratório de backend percorreu 1 mil e 10 mil notas usando a mesma API consumida
pelo botão **Carregar mais anotações** e comprovou 200 páginas estáveis no maior
conjunto, inclusive com timestamps empatados. O índice escolhido é transparente
para a interface.

Como não houve código frontend, permanecem válidos os 349 testes e o bundle de
176.122 bytes gzip (171,99 KiB), seis bytes abaixo do teto. A verificação humana
no navegador com rede lenta, teclado e lista longa continua pendente; o benchmark
de API não substitui responsividade, foco, anúncio assistivo ou percepção de
carregamento.

### Continuidade 41E — escrita e correções carregadas sob demanda

O editor separou o rascunho atual da lista de versões. A primeira página contém 20
versões e **Carregar mais versões** acrescenta a próxima sem apagar as anteriores;
criar uma versão a insere imediatamente no topo. A troca de usuário ou prompt
zera visualmente o escopo e impede mistura entre atividades.

No Caderno, textos usam um resumo paginado, sem baixar conteúdo integral, versões e
análises em cada linha. **Carregar mais textos** mantém o acumulado; o histórico de
análises só é consultado quando seu detalhe é aberto e também oferece carregamento
incremental. O total carregado é um status focalizável após a ação, preservando o
contexto de teclado. Erro e carregamento continuam explícitos e cada consulta inclui
curso/unidade ou prompt na chave de cache.

Dois testes novos atravessam segundas páginas, conferem os cursores, mantêm itens
anteriores e verificam o destino do foco. A regressão passou com **351 testes
frontend**, TypeScript, ESLint e build. Para manter o teto sem remover recursos,
foram eliminados seletores da navegação antiga sem consumidores e agrupadas no
chunk tardio as dependências de conclusão, revisão e inventário usadas por essas
mesmas páginas. Resultado: **176.000 bytes gzip (171,88 KiB)** no teto inalterado
de 172 KiB.

Ainda faltam speaking/revisão, medição humana com listas extensas/rede lenta e a
matriz real de leitores de tela. O benchmark de escrita 1k/10k também permanece no
backend/banco antes de qualquer índice adicional.

### Continuidade 41F — gravações incrementais no Caderno

A seção **Gravações mantidas** deixou de baixar todo o histórico. A primeira página
traz 20 itens e **Carregar mais gravações** acrescenta a página seguinte sem
substituir as anteriores. Curso e unidade fazem parte da chave da consulta; trocar
o escopo limpa itens, cursor e estado de foco. Após carregar, o total focalizável
confirma a atualização para teclado/leitor de tela.

Reprodução e exclusão continuam usando os endpoints privados já existentes. Depois
de excluir, o item sai do acumulado sem descartar as outras páginas já carregadas.
Estados vazio, carregando e erro não apagam itens válidos presentes durante uma
página adicional.

Um teste novo percorre duas páginas, confirma o cursor, mantém a gravação anterior
e verifica o foco no anúncio. A regressão fechou com **352 testes frontend**,
TypeScript, ESLint e build. A remoção de um seletor CSS comprovadamente sem uso
compensou o código incremental: **176.092 bytes gzip (171,96 KiB)**, apenas 36
bytes abaixo do teto inalterado de 172 KiB. A margem deve permanecer um gate; não
autoriza elevar o orçamento na próxima funcionalidade.

Paginação da revisão, medição humana com rede lenta/lista extensa e a matriz real
de VoiceOver, TalkBack e contraste forçado continuam pendentes.

### Continuidade 41G — suspensos incrementais na revisão

**Itens suspensos** passou a carregar 20 registros por vez. **Carregar mais**
acrescenta a página seguinte, preserva o que já estava visível e move o foco para
o total carregado. Trocar curso ou unidade limpa o acumulado e o cursor antes de
apresentar o novo escopo, inclusive quando a primeira página está em cache.
Reativar e excluir retiram somente o item afetado das páginas presentes.

A acumulação e o retorno de foco foram consolidados em um hook usado também pelo
Caderno, sem mudar os contratos de suas listas. A pequena mutação que adiciona
vocabulário ao deck foi separada da API completa da página, evitando dependência
cruzada entre os chunks de aula e ferramentas pessoais. Regras CSS do layout
antigo, sempre sobrescritas pela navegação atual, foram removidas.

O teste novo atravessa duas páginas, preserva o primeiro item, valida cursor/foco e
reativa um item antigo sem apagar os demais. A regressão fechou com **353 testes
frontend**, TypeScript, ESLint e build aprovados. O bundle ficou em **176.118 bytes
gzip (171,99 KiB)**, 10 bytes abaixo do teto de 172 KiB. A margem continua sendo
gate, não justificativa para elevar o limite.

Permanecem pendentes os ensaios humanos de lista longa/rede lenta, WebKit/Firefox
e a matriz real de VoiceOver, TalkBack e contraste forçado.

### Continuidade 41H — sustentação medida da lista de revisão

Não houve alteração visual neste incremento. O backend que alimenta **Itens
suspensos** foi percorrido com 1 mil e 10 mil registros sintéticos através da rota
real, preservando o contrato consumido pelo hook incremental: 20/200 páginas sem
lacunas ou duplicatas, 2 SQLs por resposta e no máximo um checkout. O índice
promovido reduziu o trabalho do plano profundo e uma repetição com o índice final
respondeu 10/10 páginas concorrentes.

Isso fecha a evidência automatizada do servidor para volume, mas não substitui a
homologação da interface. Permanecem pendentes lista longa/rede lenta em navegador
real, WebKit/Firefox, VoiceOver, TalkBack e contraste forçado. O ambiente de estudo
não foi usado no ensaio e o bundle/frontend não mudou.

### Continuidade 41I — fechamento técnico e matriz preparada, 16/10/2026

`RouteStatus` passou a definir um título específico, anunciar a página em região
`status` e mover o foco para `#main-content` depois de cada mudança de rota. O
drawer móvel agora usa o elemento nativo `dialog` aberto com `showModal()`: o
navegador torna o restante do documento inerte, Escape fecha e o foco retorna ao
botão que abriu. O fallback existe somente para DOMs de teste sem `showModal`.

A configuração E2E ganhou projetos focais de Firefox e WebKit, além de Chromium
desktop/mobile. O cenário verifica `:modal`, Escape/retorno de foco, título,
anúncio e foco pós-rota. Um segundo cenário prepara a coleta das rotas Hoje, aula,
laboratório e caderno, com ambiente e meta absoluta de 5 s anexados ao relatório.
`playwright test --list` carregou os quatro projetos e 138 casos totais sem erro de
configuração, mas nenhum navegador está disponível nesta sessão; por isso a matriz
e o baseline não são apresentados como executados ou aprovados.

As responsabilidades já estão separadas entre `voiceRecorder`, APIs de transporte,
`usePagedItems`, painel de navegação e `WritingFeedbackProvenance`. Tokens de cor e
tipografia permanecem centralizados em `:root`, com regras próprias de contraste
forçado e movimento reduzido; não houve troca de framework nem alteração do design.
TypeScript, ESLint, **354 testes frontend**, build e orçamento passaram. O total é
**176.078 bytes gzip (172,0 KiB)**, 50 bytes abaixo do teto inalterado.

Na auditoria pré-commit de 16/10, `npm run check:api` deixou de depender de
`git diff`: o gate agora gera o contrato em memória e compara seu conteúdo com
`schema.d.ts`. Assim, detecta drift real também antes do commit, sem confundir a
alteração gerada e ainda não versionada com contrato inconsistente.

Status honesto: implementação técnica concluída. Permanecem abertas somente as
evidências dependentes de navegador/dispositivo real: navegação virtual de leitor
de tela, VoiceOver macOS/iOS, TalkBack Android, contraste forçado no Windows e a
execução registrada do baseline das quatro rotas. Axe, `:modal` e emulação mobile
não substituem essas homologações.

## Sprint 42 Homologação da experiência de estudo

Achados: F09 a F11, B12 e pendências pedagógicas da auditoria.

### Entregas

- [x] Executar jornada integrada com rede estável, rede lenta, offline, expiração de sessão e atualização de versão.
- [x] Revisar textos de interface para explicar diferença entre correção objetiva, rubrica de escrita, assistência e autoavaliação oral.
- [x] Exibir origem/período/amostra das competências e não apresentar poucos acertos repetidos como certificação de nível.
- [x] Separar duração de cada item e orçamento de sessão curta de revisão, caso esse modo seja aprovado no refinamento.
- [x] Concluir ou registrar individualmente a conferência auditiva humana dos cues pendentes, com associação à aula/versão.
- [x] Consolidar guia do aluno sobre retomada, sincronização, limites offline, privacidade e recuperação de erros.
- [x] Registrar a matriz de aceite final e pendências residuais, sem marcar o pacote inteiro como concluído com homologações obrigatórias abertas.

### Critérios de aceite

1. Aluno consegue estudar uma aula completa e retomar de outro dispositivo sem perda silenciosa de escrita/progresso.
2. Todas as respostas da fila têm destino verificável: confirmada, pendente ou bloqueada com explicação.
3. Erros recuperáveis mantêm uma ação possível e não exigem conhecimento de Docker/API.
4. Evidências de listening e leitores de tela são humanas quando o critério depende de percepção/tecnologia assistiva real.
5. Mudanças de competência/conclusão são compreensíveis e versionadas; não se promete certificado oficial VOA.

### Evidência executada em 16/10/2026

No Chromium contra a stack E2E descartável passaram: cadastro até revisão,
envio deliberadamente atrasado sem duplicação, expiração de sessão com o
rascunho preservado no dispositivo e aula previamente visitada offline. No
fixture PWA isolado passaram a troca coordenada entre duas abas, preservando
rascunho/fila, e a falha de instalação que mantém a versão anterior disponível.
Foram **6 cenários aprovados**. A homologação física de acessibilidade e a
escuta humana continuam separadas e não são substituídas por esses testes.

As competências agora informam origem, período, quantidade e limiar de três
amostras. Correção objetiva, rubrica local, sugestão assistida e autoavaliação
oral usam textos distintos. O modo rápido comunica orçamento de até 10 minutos
e referência aproximada de 2 minutos por item, sem transformar a estimativa em
cronômetro obrigatório.

O inventário versionado identifica os **408 cues** por curso, aula, versão,
mídia e chave editorial. Todos estão registrados honestamente como
`pending_human_listening`; registrar cada pendência encerra a tarefa técnica,
não a homologação auditiva.

## Regras de conclusão por pacote

- `make test-api` prepara e usa somente a base marcada como descartável; D01 foi resolvido na Sprint 37.
- Testes unitários/integração/E2E executados com ambiente, versão e resultado registrados.
- Cada correção possui vínculo com o achado e teste de regressão; cada melhoria possui comportamento esperado e medida de sucesso.
- Não remover dados locais antigos sem migração e opção de recuperação.
- Nenhum novo fluxo coloca tokens em localStorage nem transforma conteúdo privado em cache público.
- Caixas concluídas acima possuem implementação e evidência; homologações externas permanecem abertas na matriz final.
