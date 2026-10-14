# Auditoria técnica e plano de evolução do sistema de inglês

Data: 13 de outubro de 2026. Base analisada: `main`, commit `a9f45c51a820532e2d0248a9cf49a4d9516c0a41`.

O conteúdo dos dois cursos está completo no recorte planejado, mas isso não encerra a qualidade técnica do produto. A prioridade agora é proteger os dados de estudo, corrigir a avaliação de escrita e tornar sessão, áudio e sincronização confiáveis. A expansão curricular não deve preceder essas correções.

Esta auditoria registra somente análise e planejamento na base indicada acima. Sua execução original não alterou código de aplicação, banco, configuração, dependências ou dados de usuários, nem aplicou migrations ou fez publicação. Atualizações posteriores de implementação estão identificadas separadamente e não reescrevem as evidências históricas.

## Documentos de execução

- [Sprints de frontend](sprints_37_42_frontend_2026-10-13.md).
- [Sprints de backend](sprints_37_42_backend_2026-10-13.md).
- [Sprints de banco de dados](sprints_37_42_banco_de_dados_2026-10-13.md).

As Sprints 37 a 42 são seis ciclos propostos, cada um com um pacote por frente. `FE-37`, `BE-37` e `DB-37` pertencem ao mesmo ciclo; não são três sprints cronológicas adicionais. No fechamento da auditoria nenhum pacote estava implementado. A numeração continua o [fechamento das Sprints 31 a 36](plano_sprints_31_36_level_1_1_a_30_2026-10-09.md).

Atualização posterior, 13/10/2026: a primeira entrega BE-37/DB-37 implementa
isolamento da suíte backend. O segundo incremento implementa escrita v2,
quantidades e snapshots de rubrica, com aviso de limitações na interface.
O terceiro incremento implementa renovação/reenvio de sessão no frontend,
distinção de indisponibilidade e preservação do trabalho local nesse fluxo;
o quarto entrega fila transacional, capacidade explícita por aluno, migração
v1/v2 e coordenação entre abas. Validado com 236 testes frontend e 3 testes
Chromium isolados de duas abas, com API simulada. O quinto incremento centraliza
armazenamento local, trata quota/indisponibilidade, adiciona barreiras de erro e
recuperação de chunks, além de mensagens adequadas ao aluno. Validação atual:
262 testes frontend e 4 testes Chromium isolados. Permanecem aceite integrado,
homologação de dispositivos, alertas das ferramentas de teste e itens BE-37/DB-37.
A Sprint 37 continua em andamento; acompanhar
resultados e pendências nos documentos de execução acima. Os achados abaixo
descrevem o commit auditado, não substituem o status dessas entregas.

### Atualização de fechamento técnico — 13/10/2026

O oitavo incremento encerrou tecnicamente FE/BE/DB-37, substituindo o status
provisório da atualização anterior. Foram aprovados 765 testes backend
(93,57% cobertura), 263 frontend, 98 E2E isolados, 50 guardas E2E, 38 testes
operacionais e duas repetições dos 4 cenários de browser controlados.
Escrita v2/82 exemplos e erros comuns entregues. Produção local em 5181
atualizada após backup real, restore/ensaio e prova de preservação de 39 tabelas;
papéis mínimos ativos. Desenvolvimento em 5180 não foi migrado/reiniciado.

Jeferson autorizou fechamento **técnico** com homologação pedagógica humana
pendente, e backup somente no Mac no estágio atual. Metas RPO/RTO/retenção
registradas como metas a validar, sem SLA, agendamento ou cópia externa.
Consulte [operação local](operacao_sprint_37.md) e os oitavos incrementos dos
planos por frente. Naquele fechamento as Sprints 38–42 permaneciam planejadas.

### Atualização de implementação — 14/10/2026

FE/BE/DB-38 implementadas e validadas em bases isoladas: conflitos explícitos de
rascunho, descarte de análise tardia, revisão SM-2 idempotente, merge de jornada,
refresh concorrente, limites de autenticação e migration aditiva com auditoria.
789 testes backend (93,54%), 270 frontend e 106 E2E aprovados; detalhes e limites
nos planos por frente. Após autorização, a base de estudo em 5181 recebeu a
Sprint 38 com backup restaurado, ensaio isolado e preservação das 39 tabelas
históricas. A auditoria detectou 20 jornadas antigas sem detalhamento completo,
15 delas também sem data de conclusão; foram preservadas, não reconciliadas.
Homologações humanas continuam pendentes. Sprints 39–42 permanecem planejadas.
Os achados abaixo descrevem a fotografia original, não são apagados pela implementação.

## Escopo e evidências

Foram examinados autenticação, catálogo, jornada, exercícios, checkpoints, escrita, speaking, revisão espaçada, assistência, exportação, modelos SQLAlchemy, migrations, seed, service worker, armazenamento local, navegação, testes, CI, Docker, Nginx e procedimentos de backup.

As verificações dinâmicas ficaram restritas a módulos em memória, funções puras, configuração efetiva e consultas PostgreSQL em transações somente leitura. Não houve teste de carga, pentest completo, execução de cenários destrutivos, escuta humana dos áudios ou homologação em leitores de tela. Condições de corrida descritas como risco precisam de reprodução concorrente em ambiente descartável.

### Situação observada

| Área | Evidência |
|---|---|
| Catálogo no banco de produção local | Level 1 com 52 aulas, 10 unidades e 10 checkpoints; Level 2 com 30 aulas, 6 unidades e 6 checkpoints |
| Esquema de produção local | 40 tabelas no schema `public`, incluindo controle de migrations; revisão `b84e2c7a9d31`, correspondente ao head da cadeia atual |
| Stack | React, TypeScript, React Query, FastAPI, SQLAlchemy assíncrono e PostgreSQL 16 |
| Ambientes locais | Desenvolvimento em 5180/8010/5433 e produção local em 5181/5434; portas publicadas vinculadas a `127.0.0.1` |
| Índices e integridade | Unicidades por usuário, FKs, checks e índice parcial para sessão ativa já existem; há lacunas específicas, não ausência de modelagem |
| Verificação agregada de dados | Zero gravações `ready` sem metadados obrigatórios e zero evidências órfãs nas três origens consultadas, nesta fotografia |
| Histórico de qualidade | O fechamento anterior registra 237 testes backend, 166 frontend, 96 execuções E2E e 94% de cobertura; esses números são histórico documentado, não uma nova execução desta auditoria |

Os testes backend não foram executados porque a configuração padrão permite apagar usuários do banco de desenvolvimento, conforme D01. O pipeline possui verificação real do baseline OpenAPI em `backend/tests/test_openapi_baseline.py:11`; não há motivo para planejar esse controle como se estivesse ausente.

### Proteções existentes que devem ser preservadas

- Access token em memória, refresh HttpOnly, senha com Argon2 e verificação de propriedade dos principais recursos privados.
- Respostas dos exercícios ocultas na leitura inicial; correção no servidor.
- Idempotência e revisão de estado nas sessões de prática; idempotência com fingerprint do pedido nos checkpoints.
- Fila de transcrição persistida em PostgreSQL, com `FOR UPDATE SKIP LOCKED`, tentativas limitadas e proteção contra conclusão por worker antigo.
- Catálogo separado por curso e unidade; sidebar já recolhível, busca e navegação mobile. Não é necessário refazer a Sprint 20.
- Service worker com lista explícita de conteúdo público; áudios e dados privados não entram no cache offline automaticamente.
- Formulários nativos, skip link, foco visível, CSS de contraste forçado e testes de teclado existentes.
- Consentimento para salvar voz, opt-in separado para assistência e opção de excluir gravação/transcrição.

## Critérios de prioridade

- **P0:** risco imediato de perda de dados no fluxo operacional; resolver antes de voltar a usar o comando afetado.
- **P1:** falha de estudo, persistência ou segurança que merece correção nos primeiros ciclos; alguns riscos são condicionados à exposição pública.
- **P2:** robustez, escala, acessibilidade ou governança com execução programada.
- **P3:** evolução de produto opcional, posterior à estabilização.

“Confirmado” significa demonstrado por código/configuração ou execução controlada, conforme indicado. “Risco” identifica uma sequência plausível que ainda exige teste isolado. “Melhoria” não implica que a funcionalidade atual esteja quebrada. Prioridade não é uma pontuação CVSS.

## Resumo de achados

| ID | Prioridade | Achado | Frente principal | Ciclo inicial |
|---|---|---|---|---|
| D01 | P0 | Testes locais podem excluir todas as contas do banco de desenvolvimento | Banco/backend | 37 |
| B01 | P1 | Critérios de escrita com expressões não podem passar no corretor atual | Backend | 37 |
| F01 | P1 | Reenvio após refresh tenta clonar corpo já consumido | Frontend | 37 |
| F02 | P1 | Indisponibilidade no refresh encerra sessão; binários não renovam token | Frontend/backend | 37 |
| F03 | P1 | Fila offline descarta respostas antigas ao exceder 100 itens | Frontend | 37 |
| D02 | P1 | Backup não inclui voz e pode informar sucesso após erro no dump | Banco/operação | 37 |
| D03 | P1 | Perfil padrão do banco utiliza papel superusuário | Banco/operação | 37 |
| B02 | P1 | Rotação de refresh não consome a sessão de forma atômica | Backend | 38 |
| B03 | P1 | Login sem limitação de tentativas e hash síncrono no caminho assíncrono | Backend | 38 |
| B04 | P1 | Avaliação SM-2 não tem idempotência nem proteção contra concorrência | Backend/frontend | 38 |
| B05 | P1 | Escrita e jornada não têm contrato uniforme de conflito entre dispositivos | Backend/banco | 38 |
| F04 | P1 | Feedback assíncrono pode reaparecer para texto já alterado | Frontend | 38 |
| B06 | P1 | Minutos da semana somam tempo histórico das aulas tocadas na semana | Backend/banco | 39 |
| B07 | P1 | Limites de áudio divergem entre interface, API e Nginx | Backend/frontend | 39 |
| B08 | P1 | Cota assistida depende de registros apagáveis; expiração incompleta | Backend/banco | 39 |
| B09 | P1 | Exportação pessoal não acompanha todas as entidades atuais | Backend | 40 |
| D04 | P1 | Atualização editorial pode apagar dados ligados ou mudar seu significado | Banco/backend | 40 |
| D08 | P1 | Evolução do banco carece de validação de upgrade com dados e readiness de schema | Banco/backend | 42 |
| F05 | P2 | Cache offline sem limite e sem fluxo explícito de atualização | Frontend | 39 |
| F06 | P2 | Falha de chunk ou renderização não possui ErrorBoundary global | Frontend | 37 |
| F07 | P2 | Retomada do áudio e ciclo do microfone têm riscos assíncronos | Frontend | 39 |
| F08 | P2 | Escritas locais falham sem política uniforme de recuperação e limpeza | Frontend | 37 |
| F09 | P2 | Acessibilidade entre rotas e em dispositivos reais ainda exige fechamento | Frontend | 41 |
| F10 | P2 | Mensagens técnicas e atualização parcial do painel confundem o aluno | Frontend | 37 |
| F11 | P2 | Componentes extensos e históricos sem paginação dificultam evolução | Frontend/backend | 41 |
| B10 | P2 | Históricos ilimitados e carregamento ORM amplo elevam custo por consulta | Backend/banco | 41 |
| B11 | P2 | Rotas por ID não aplicam uniformemente a política de publicação | Backend | 40 |
| B12 | P2 | Operação tem logs, mas faltam alertas, limites e gates de implantação | Backend/operação | 42 |
| D05 | P2 | Algumas invariantes existem apenas na API; origens polimórficas não têm FK | Banco | 38 |
| D06 | P2 | Índices precisam acompanhar filtros e ordenações reais, com medição | Banco | 41 |
| D07 | P2 | Revisão e retenção não dispõem de histórico operacional independente | Banco | 38 |

## Achados de frontend

### F01 Reenvio de requisições com corpo após expiração

**P1, confirmado em reprodução controlada.** Em [client.ts](../frontend/src/api/client.ts#L87), o middleware recebe o 401, renova o token e só então chama `request.clone()` na linha 102. O `openapi-fetch` instalado entrega ao middleware o mesmo Request passado ao fetch. Um corpo enviado já pode estar consumido.

Um POST de tentativa, com transporte simulado que consome o corpo, retornou `TypeError: unusable`; houve chamada original e refresh, mas nenhum reenvio. Os testes atuais de refresh bem-sucedido são GETs e os mocks não consomem o corpo (`client.test.ts:51`). O comportamento é coerente com a restrição de [Request.clone](https://developer.mozilla.org/en-US/docs/Web/API/Request/clone).

**Impacto:** escrita, envio de exercício ou outra mutação pode falhar justamente após os 15 minutos de validade do access token. Uma exceção TypeError também pode ser confundida com falha de rede.

**Direção:** preparar uma cópia/reconstrução segura antes do primeiro envio, limitar a uma repetição e preservar corpo, headers, cancelamento e chave de idempotência. Testar POST/PUT reais além de GET; não habilitar retentativa irrestrita de mutações.

### F02 Sessão indisponível tratada como sessão encerrada

**P1, confirmado em módulo isolado; binários confirmados por código.** `client.ts:49–68` converte tanto 401 quanto 503 ou falha de rede no refresh em `null`; `client.ts:94–98` limpa a sessão. A simulação de refresh 503 acionou `aoPerderSessao`.

O helper `authenticatedFetch`, linhas 26–29, injeta token, mas não compartilha renovação/reenvio. Ele é usado para baixar e enviar voz em `ShadowingPractice.tsx:241,269`. O single-flight existente também é por módulo/aba, não entre abas.

**Direção:** distinguir credencial revogada, falha temporária e offline; preservar trabalho pendente; unificar JSON e binários sob política explícita. Coordenar abas com a solução de B02. Logout local não deve prometer revogação remota quando a rede falhar.

### F03 Perda silenciosa na fila offline

**P1, descarte reproduzido; concorrência entre abas é risco.** [attemptQueue.ts](../frontend/src/features/offline/attemptQueue.ts#L169) persiste `attempts.slice(-MAX_ATTEMPTS)`, com limite global de 100. Enfileirar 101 respostas em armazenamento simulado conservou apenas IDs 2 a 101. O primeiro item não havia sido sincronizado nem descartado pelo estudante.

O limite é compartilhado por usuários do mesmo navegador. Além disso, `readAll → writeAll` não é transacional: duas abas podem sobrescrever atualizações da fila, mesmo que a API evite duplicar tentativas já recebidas.

**Direção:** limite explícito sem descarte de pendências; feedback antes de aceitar a resposta 101; armazenamento transacional ou mecanismo equivalente; sincronização coordenada entre abas. Manter migração v1/v2 e os estados bloqueados existentes. Não apagar a fila automaticamente no logout.

### F04 Feedback pode não corresponder ao texto visível

**P1, sequência identificada no código; reprodução de UI pendente.** `WritingWorkspace.tsx:126–141` captura o texto, aguarda análise e faz `setFeedback(data)` sem verificar se o texto continua igual. O textarea permanece editável durante a análise (`:204–212`). `changeText` limpa o feedback, mas uma resposta antiga pode recolocá-lo depois.

A serialização do autosave e a checagem `textRef.current === value` já protegem o backup contra resposta antiga na mesma instância (`:81–104`); essa proteção não deve ser removida nem descrita como inexistente. Entre dispositivos, porém, falta versão condicional no servidor, conforme B05.

**Direção:** associar feedback ao texto e à versão analisados; descartar/rotular resultado obsoleto. Exibir conflito entre versões locais/remotas com opção de preservar ambas, sem sobrescrita automática.

### F05 Cache offline precisa de ciclo de vida

**P2, risco operacional.** `public/sw.js:1` usa versão manual fixa; `:55–79` armazena navegações, textos e assets sem orçamento, expiração ou contagem. A ativação limpa nomes de versões anteriores, mas atualizações de conteúdo/chunks não necessariamente modificam `sw.js`. `skipWaiting` e `clients.claim` não têm coordenação com rascunho ou exercício em curso.

**Direção:** orçamento e expiração por classe, versão de release, mensagem de atualização segura e tela para inspecionar/limpar apenas downloads autorizados. Manter a exclusão de mídia privada e o bloqueio de cache de áudio. Não confundir modo offline textual com disponibilidade offline de voz.

### F06 Falhas de renderização e chunks sem recuperação

**P2, lacuna confirmada.** `App.tsx:14–22,57–122` usa lazy loading e Suspense, mas não há ErrorBoundary no shell. Suspense trata espera, não uma rejeição definitiva de importação ou exceção de renderização.

**Impacto:** abrir pela primeira vez uma rota não cacheada sem rede, ou manter uma aba aberta durante mudança de bundles, pode derrubar a interface sem saída orientada.

**Direção:** barreiras de erro no shell e nas áreas de estudo; mensagem específica para chunk indisponível; recarregamento controlado que não destrua rascunhos nem filas. Não fazer reload automático em laço.

### F07 Retomada de mídia e microfone

**P2, riscos a reproduzir.** `LessonAudioPlayer.tsx:67–79` prefere qualquer posição remota com `updated_at` à posição local, que não guarda timestamp. Um avanço offline mais recente pode ser substituído por posição remota antiga. PUTs usam fila de mutation, mas DELETE ao terminar não compartilha essa mesma fila (`api/media.ts:28–64`), permitindo que uma gravação atrasada recrie a posição apagada.

Em `ShadowingPractice.tsx:106–117,164–200`, a limpeza fecha streams existentes, mas um `getUserMedia` que resolva somente depois da desmontagem ainda pode iniciar uma gravação. Faltam guardas de ciclo de vida para esse cenário.

**Direção:** sequência/revisão de posição com horário local, serialização do encerramento e descarte seguro de permissão tardia. Testar mudança de aula durante gravação, negativa de permissão, formato gerado pelo navegador e token expirado ao reproduzir histórico.

### F08 Armazenamento local e dispositivo compartilhado

**P2, lacuna confirmada.** Há chamadas a `localStorage.setItem/getItem` sem tratamento uniforme em auth, writing, player, shadowing e jornada. Quota excedida ou armazenamento bloqueado pode interromper o handler de interação. Os dados são separados logicamente por usuário, mas continuam no mesmo perfil do navegador após sair.

**Direção:** serviço único de armazenamento com validação, tratamento de falhas e fallback explícito. Oferecer “limpar dados deste dispositivo”, discriminando rascunhos, respostas pendentes e conteúdo público; pedir confirmação antes de descartar trabalho não enviado. Separação de chaves não equivale a criptografia ou proteção contra alguém com acesso ao mesmo perfil.

### F09 Homologação de acessibilidade incompleta

**P2, pendência documentada e risco de navegação.** A matriz existente aprova teclado e zoom, mas mantém VoiceOver macOS/iOS, TalkBack e Windows real pendentes. Não reabrir como falha o suposto corte de cadastro já esclarecido. A suíte E2E só configura Chromium desktop e emulação Pixel 5 (`e2e/playwright.config.ts:26–29`).

No código não há atualização central do título da página nem gestão geral de foco após mudança de rota. O drawer possui trap de Tab/Escape, mas o fundo não é tornado `inert`; `aria-modal` por si não desativa interações. O efeito real em cada leitor precisa de teste.

**Direção:** foco e anúncio de contexto por rota, revisão de idioma de trechos em inglês, matriz real de leitores de tela, Safari/WebKit e Firefox, além de gravação em iOS. Atualizar rotas antigas da matriz, inclusive `/revisao`, para os caminhos efetivamente suportados.

### F10 Estados e indicadores pouco consistentes

**P2, confirmado por código.** O componente global de erro orienta qualquer aluno a iniciar `localhost:8010` com `make up` (`States.tsx:11–18`). Após avaliar revisão, `useAvaliar` invalida revisão e progresso, mas não `today` (`api/review.ts:68–82`), ao contrário de suspender/excluir. O cache padrão fica fresco por cinco minutos, sem refetch no foco.

**Direção:** mensagens por rede/autorização/conflito/servidor, detalhes técnicos recolhidos e request-id para suporte. Centralizar invalidação de painel, competências e conclusão. Distinguir zero real, carregamento e erro na sidebar. Clarificar que “Até 5 min” no filtro de revisão limita cada item, não uma sessão inteira.

### F11 Crescimento do frontend e históricos

**P2, melhoria de manutenção e escala.** `LessonRail`, `ShadowingPractice`, `PracticeRunner`, páginas de estudo/caderno e a folha global concentram muitos estados e responsabilidades. Históricos chegam completos e são renderizados a partir de listas sem contrato paginado.

**Direção:** extrair responsabilidades por comportamento, não fazer reescrita de framework; definir tokens e componentes de estados; paginar históricos com a API. Medir renderizações, tamanho inicial e uso de rede antes de adotar virtualização. Para 82 aulas, agrupar por unidade continua mais útil que introduzir uma lista virtual complexa.

## Achados de backend

### B01 Critérios de escrita impossíveis de satisfazer

**P1, confirmado por função pura e varredura do seed.** [writing.py](../backend/app/domain/writing.py#L25) transforma o texto em um conjunto de palavras e compara cada termo da rubrica por igualdade (`:44–50`). Expressões como `are you`, `this is` e termos com espaço final, como `he `, nunca pertencem a esse conjunto.

No seed atual há **236 requisitos**, dos quais **108 possuem apenas alternativas com espaços ou hífen**, incompatíveis com esse matching. Afetam **66 aulas: 42 do Level 1 e 24 do Level 2**. A contagem identifica essa classe de incompatibilidade, não certifica os outros 128 critérios. Exemplos: `seed/lessons.json:524,1086,1643`.

Reprodução: `Are you Anna?`, com requisito `terms=["are you"]`, retorna `passed=False`. O texto `He is here. She is here. They are here.` também reprova o requisito com `he `, `she `, `they `.

**Impacto:** prontidão e evidências de competência podem permanecer baixas mesmo com produção correta. Como a assistência recebe a rubrica local e não altera a prontidão, Ollama não corrige a causa.

**Direção:** contrato de requisito tipado, normalização e matching de expressão com limites de palavra; suportar explicitamente quantidade e `any/all` quando pedagogicamente necessário. Não corrigir usando substring irrestrita, que aceitaria `he` dentro de `the`. Validar exemplos positivos e negativos de todas as 82 propostas. Não reescrever notas históricas sem versão e decisão explícita.

### B02 Rotação de refresh concorrente

**P1, risco confirmado na estrutura transacional.** `api/auth.py:119–137` lê refresh, verifica `revoked_at`, marca revogação e cria sucessor, sem lock ou update condicional. Duas transações que leiam antes do primeiro commit podem aceitar o mesmo refresh. O bloqueio em memória do frontend não cobre abas ou clientes diferentes.

**Direção:** consumo atômico e política documentada para repetição legítima/reutilização suspeita; considerar família de sessões sem introduzir logout indevido por corrida normal. Usar restrições e transações, não apenas botão desabilitado. [Bloqueios de linha do PostgreSQL](https://www.postgresql.org/docs/16/explicit-locking.html) oferecem uma das ferramentas possíveis.

### B03 Proteção de autenticação antes de exposição pública

**P1 para publicação, lacunas confirmadas.** `auth.py:63–98` não limita tentativas e chama hashing/verificação Argon2 síncronos dentro de handlers async. A existência do e-mail é consultada antes do insert, sem tratamento da corrida de cadastro. A validação de configuração exige segredo próprio em produção, mas não exige cookie Secure (`core/config.py:65–106`).

A stack observada é local, vinculada a loopback; isso reduz exposição e não comprova ataque remoto. Para acesso público, é necessário um perfil HTTPS explícito, limites por conta/IP, hash fora do event loop com concorrência limitada, resposta controlada à colisão de cadastro e política de recuperação de conta. A [orientação de autenticação OWASP](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#login-throttling) sustenta limitação de tentativas e controles contra automação.

Revisar também headers de segurança e `Cache-Control: private, no-store` de todos os recursos privados. O service worker já não os armazena, mas isso não substitui a política HTTP.

### B04 Avaliação de revisão não é idempotente

**P1, confirmado por contrato e código.** `api/review.py:322–363` lê o item, calcula SM-2 e sobrescreve contadores/datas, sem chave de evento, revisão ou bloqueio. O frontend aceita atalhos numéricos enquanto o pedido anterior está em curso (`ReviewPage.tsx:89–130`).

**Impacto:** repetição de tecla, retry após resposta perdida ou duas abas podem contar avaliações extras ou perder uma atualização. Isso altera diretamente o próximo dia de revisão.

**Direção:** evento de avaliação idempotente, lock/revisão de estado e histórico imutável. Desabilitar UI durante envio ajuda, mas não garante integridade. Preservar as regras SM-2 já testadas.

### B05 Conflitos em escrita e jornada

**P1, riscos transacionais identificados.** `writing.py:107–122` faz update de rascunho sem versão esperada; `:157–166` aloca revisão com `MAX(version)+1`. A unicidade impede duplicata, mas duas requisições podem resultar em erro não tratado ou sobrescrita. `progress.py:258–330` substitui `completed_steps` e soma tempo com base em estado lido sem lock.

Marcar aula e inserir itens de revisão também usam leitura seguida de insert (`progress.py:123–133`, `review.py:59–100`). A API de prática já possui controle de concorrência mais forte; o problema é falta de uniformidade, não ausência de proteção em toda a API.

**Direção:** CAS/revisão ou ETag para rascunho; sequência de revisão dentro de lock; merge explícito de etapas concluídas; idempotência do evento de tempo; upserts e respostas de conflito com códigos estáveis.

### B06 Métrica semanal soma tempo de semanas anteriores

**P1, erro lógico confirmado.** `dashboard.py:281–296` soma `StudySessionProgress.total_seconds` de linhas atualizadas nesta semana. Esse total é acumulado por aula, não por semana. Uma aula com 60 minutos antigos, revisitada por dois minutos, pode contribuir com os 62 minutos na semana atual.

O cálculo do tempo em `progress.py:289` também atribui até 30 minutos do intervalo desde a última atualização ao retornar à aula, mesmo que o aluno tenha fechado a aplicação. O teto limita o erro, mas não mede presença.

**Direção:** registrar intervalos/eventos ativos com timestamp e idempotência; somar os eventos dentro da semana e fuso definidos. Pausar contagem quando a página estiver oculta/inativa. Não distribuir retroativamente totais antigos entre semanas sem evidência; identificá-los como legado.

### B07 Upload e armazenamento de áudio

**P1, divergência confirmada; demais condições são riscos.** Interface e API aceitam até 2.000.000 bytes. O `nginx -T` da produção local não define `client_max_body_size`, portanto aplica o padrão de 1 MiB e rejeita parte dos arquivos que a interface permite. Esse padrão e a resposta 413 constam da [documentação do Nginx](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).

Em `speaking.py:167–189`, sem Content-Length confiável, `request.body()` lê todo o corpo antes de conferir o limite. O MIME é declarado pelo cliente; duração e conteúdo real não são inspecionados. Dois uploads para a mesma tentativa `pending` não possuem lock de transição. Há exclusão compensatória se o commit falhar, mas remoção via cascade/seed não passa pelo serviço de arquivos.

**Direção:** alinhar limites ponta a ponta; leitura limitada em streaming; validar formato/duração com recurso limitado; consumo atômico da tentativa; limpar pendências e reconciliar arquivos órfãos com período de segurança. Não enviar gravações reais a serviços externos durante validações técnicas.

### B08 Cota assistida e retenção

**P1, confirmado por desenho; corrida a reproduzir.** `assist.py:19–41` calcula uso diário contando feedbacks e jobs. `speaking.py:366–375` permite excluir jobs; a exclusão reduz a cota consumida, possibilitando novo processamento no mesmo dia. Pedidos paralelos também podem ler a mesma cota antes de persistir consumo. No writing, a chamada externa ocorre enquanto a sessão/transação aberta após as leituras continua viva (`writing.py:199–250`).

A expiração é aplicada somente quando o usuário lista gravações ou solicita nova transcrição (`speaking.py:101–107,241,302`). O worker não filtra `expires_at` ao reivindicar jobs (`transcription_queue.py:70–92`), e exportação pode ler registros expirados.

**Direção:** reserva atômica de consumo independente do conteúdo apagável, política de reembolso por falha, janitor agendado, filtro de expiração em leituras/worker e métricas de fila. Liberar conexão/transação antes da espera do provedor. A configuração de 30 dias atual se refere à transcrição; retenção de rascunhos/voz exige política própria, não uma suposição.

### B09 Exportação pessoal incompleta

**P1, confirmado.** `schemas/notebook.py:58–72` e `api/me.py:201–478` não exportam sessões de prática/itens nem tentativas de checkpoint. Feedbacks de escrita são agrupados e emitidos apenas para prompts com `WritingDraft`; feedback criado antes de salvar rascunho pode ficar fora da exportação (`me.py:239–257,410–444`).

O áudio exportado é descrito por metadados, não empacotado como arquivo. Isso deve ficar claro, sem chamar o JSON de backup completo. Também falta versão consistente da fotografia entre consultas se houver escrita concorrente.

**Direção:** inventário de todas as entidades pessoais, contrato versionado, exportação incremental/assíncrona para grandes contas e download autorizado dos binários. Planejar exclusão de conta e dados locais com escopo, consentimento e reconciliação; não implementar automaticamente política jurídica de retenção.

### B10 Consultas e históricos amplos

**P2, parte medida e parte melhoria.** Em conexão read-only no container, `lesson_summaries` para Level 1 executou **1 SQL**; `lesson_by_course_number` para a Aula 31 executou **17 SQLs**. Foram amostras únicas, sem valor de p95. A comparação mostra que existem projeções leves, mas o detalhe aciona muitas relações `selectin`, inclusive unidade/checkpoint.

Históricos de escrita (`writing.py:332–385`), speaking (`speaking.py:233–277`), notebook (`me.py:95–111`) e suspensos (`review.py:297`) não têm paginação. Autosave de escrita devolve todas as revisões. O painel percorre checkpoints e consulta pré-requisitos dentro de loop (`dashboard.py:169–183`).

**Direção:** projeções por caso de uso, evitar carregar gabaritos/relações não serializadas, cursores estáveis e limites. Medir SQL count, payload e p50/p95 com dados sintéticos antes de criar caches ou índices. Não há evidência de que Redis ou microserviços sejam necessários.

### B11 Política de publicação inconsistente por rota

**P2, confirmado no código; sem conteúdo atualmente oculto demonstrado.** `services/curriculum.py:12–26` exige curso/unidade publicados. Já `progress.py:74–82`, `writing.py:64–70`, `speaking.py:131–135` e `media.py:17` resolvem recursos diretamente por ID. Fluxos de revisão também não filtram publicação uniformemente.

Isso não é evidência de acesso a dados de outro usuário: propriedade e publicação são controles distintos. Ao arquivar uma unidade, porém, o catálogo pode escondê-la enquanto IDs antigos continuam permitindo prática ou leitura de material.

**Direção:** definir se histórico arquivado é consultável, quais escritas são permitidas e como os endpoints por ID aplicam a decisão. Reutilizar política de domínio; não apagar histórico para resolver visibilidade.

### B12 Operação e preparação para publicação

**P2, melhoria operacional.** Existem logs JSON, request-id, `/live`, `/health` e CI. Faltam metas/alertas de latência, erro, fila, capacidade de armazenamento e recuperação. `/health` verifica conexão, não revisão de schema; o compose usa `/live` para saúde e sobe serviços antes de migrations/seed (`Makefile:98–101`).

O Nginx não configura CSP, proteção contra framing e política consistente de cache privado. O CI verificado não contém auditoria periódica de dependências, ensaio de carga ou restauração de backup. Isso não demonstra uma CVE específica.

**Direção:** gates de deploy, readiness compatível com schema, métricas sem textos/áudios, heartbeat do worker, timeouts e runbooks. Segurança pública deve ser testada no perfil HTTPS; não ativar HSTS no ambiente HTTP local.

## Achados de banco de dados

### D01 Suíte local com limpeza destrutiva

**P0, confirmado por configuração.** `backend/tests/conftest.py:8–10` escolhe por padrão o mesmo banco usado no desenvolvimento em `localhost:5433/aulas_ingles`. O fixture autouse executa `delete(User)` sem filtro e commit após cada teste (`:24–49`). FKs em cascade removem os dados de estudo associados. `make test-api` e `make cov` não substituem a URL (`Makefile:54–58`).

**Medida imediata:** não executar esses comandos contra uma base com dados reais. Não foi necessário provocar exclusão para comprovar o risco.

**Direção:** banco/role/volume de teste exclusivos, guardas verificadas antes de qualquer mutação e falha fechada se a URL apontar para desenvolvimento/produção. `APP_ENV=test` sozinho não isola dados. Mesmo um teste de função pura hoje recebe o teardown autouse, razão para não rodar pytest nesta auditoria.

### D02 Recuperação incompleta e falso positivo no backup

**P1, confirmado.** `Makefile:116–125` salva apenas `pg_dump`; o volume `speaking_data_prod` é separado. Restaurar esse dump não recupera os áudios. O comando de dump é seguido por `echo` na mesma receita sem interromper explicitamente por falha, podendo imprimir sucesso apesar de erro no dump. Nome por minuto pode sobrescrever um backup feito no mesmo minuto.

O restore usa `--clean --if-exists` diretamente no destino e não exige ensaio em banco vazio, validação de arquivo ou coordenação de gravações.

**Direção:** backup versionado e atômico de banco + binários, checksums, manifesto, verificação de exit code, criptografia/controle de acesso e cópia fora do host conforme necessidade. Restaurar primeiro em ambiente descartável; definir RPO/RTO com o responsável. Não chamar rollback de migration de recuperação de backup.

### D03 Privilégios excessivos

**P1 antes de exposição pública, confirmado no runtime.** Consulta somente leitura em `aulas-prod-db` mostrou `aulas` com `rolsuper`, `rolcreatedb` e `rolcreaterole` verdadeiros. Uma segunda consulta, aberta a partir da configuração efetiva da API de produção local, confirmou que o runtime também usa esse papel com os três privilégios. Nenhuma senha ou URL de conexão foi extraída.

**Direção:** separar proprietário/migrador, runtime, worker, backup e testes. Runtime não precisa criar banco, role ou executar DDL. Restringir grants e `search_path`; testar API e worker com o papel mínimo antes da troca. RLS pode ser defesa adicional futura, mas não substitui filtros por usuário e não deve ser adicionada sem testes de contexto de conexão.

### D04 Seed e preservação histórica

**P1, risco de perda confirmado nas relações.** `seed.py:684–690,713–715,759–761,787–789` exclui cues, mídias, vocabulário, exercícios ou prompts removidos do conteúdo. Prompts têm drafts/versões em cascade; cues têm speaking/transcrições em cascade; vocabulário tem itens de revisão em cascade. Exercícios usados por `PracticeSessionItem` têm RESTRICT, podendo bloquear o seed em vez de excluir.

Mesmo preservando ID por posição, alterar enunciado/gabarito muda o contexto de tentativas antigas. `_attempt_out` recomputa feedback com o gabarito atual (`progress.py:91`) embora `correct` seja o valor histórico. Sessões de prática detectam alteração via fingerprint, mas isso não é snapshot completo do exercício histórico.

`seed.py:582–584` ainda fixa revisão/publicação em 7 de outubro de 2026 para versões editoriais posteriores. É um problema de proveniência, não de timezone.

**Direção:** diff editorial antes da aplicação, arquivamento/versões imutáveis para entidades referenciadas, identidade estável independente de posição e snapshots de correção. Manter remoção controlada para conteúdo nunca utilizado. Não renumerar ou reavaliar histórico silenciosamente.

### D05 Invariantes incompletas

**P2, lacunas de defesa no banco.** O modelo de speaking valida duração/tamanho positivo, mas não amarra `status=ready` à existência de chave/MIME/tamanho (`models.py:506–527`). Notebook não possui check de `kind`; jornada não limita passo/total no banco; revisão não limita contadores e intervalo não negativos (`:973–1016,1248–1292`).

`SkillEvidence.source_type/source_id` e `ReviewItem.source_type/source_id` são referências polimórficas sem FK, e algumas relações de usuário com recurso poderiam aceitar associação cruzada por SQL direto. A API hoje faz verificações de propriedade; não foi demonstrado vazamento. A amostra consultada não tinha evidências órfãs.

**Direção:** inventariar invariantes, consultar violações antes de criar checks, validar em etapas e definir integridade das origens. Evitar validar o mesmo JSON de forma incompatível entre Pydantic, seed e PostgreSQL. Preservar checks existentes de classificação e checkpoints.

### D06 Índices por carga de trabalho

**P2, oportunidade, sem lentidão comprovada.** `pg_indexes` confirmou principalmente índices individuais em `review_item`, `writing_feedback`, `skill_evidence` e jobs. Consultas combinam usuário, status, data e ordenação; índices compostos/parciais podem ajudar, mas o tamanho real e os planos precisam justificar cada criação.

**Candidatos para ensaio**, não DDL pronto para produção:

- revisão: `(user_id, due_at, id)` parcial para `status='active'`;
- históricos: `(user_id, created_at DESC, id DESC)` e variantes com `prompt_id` conforme acesso;
- fila: `(next_attempt_at, id)` parcial para `status='queued'`;
- sessão/atividade: `(user_id, updated_at DESC)` ou data de eventos no modelo novo;
- retenção: `expires_at` em refresh, se a rotina de limpeza e volume justificarem.

Usar `EXPLAIN (ANALYZE, BUFFERS)` somente em SELECTs seguros/ambiente de ensaio, registrar custo de escrita e avaliar sobreposição com índices de unicidade. Um scan sequencial em tabela pequena pode ser correto.

### D07 Histórico de revisão e políticas de retenção

**P2, lacuna confirmada.** `ReviewItem` mantém só o estado SM-2 atual, não a sequência de avaliações. Não permite auditar qual retry alterou a data ou reconstruir evolução após mudança do algoritmo. O consumo de assistência também se perde ao excluir o conteúdo que o representa, conforme B08.

`ReviewCardLegacy` continua mantido desde a estratégia expand/contract da Sprint 12 (`models.py:1212–1241`). Isso é dívida de manutenção a avaliar, não autorização para apagar a tabela.

**Direção:** eventos de revisão e consumo independentes, com payload mínimo, versão e prazo definidos. Retenção separada para sessão, job, texto, voz, eventos e backups. Documentar condições para eventual retirada do legado após reconciliação e janela de rollback.

### D08 Migrações com dados e compatibilidade de deploy

**P1 operacional.** CI testa upgrade/downgrade/upgrade e seed, mas o fluxo principal recria schema em base de teste; isso não equivale a migrar um retrato anonimizado com versões, vozes, exercícios em curso e revisões vencidas. A base local está no head, portanto não foi identificada migration pendente nesta fotografia.

**Direção:** ensaio de atualização com dados sintéticos representativos, detecção de divergência modelo/schema, avaliação de locks e tempo, backup validado e gates de readiness. Usar expand/contract para contratos em uso; estabelecer rollback de aplicação e recuperação de dados sem executar downgrade destrutivo por reflexo.

## Melhorias pedagógicas após as correções

O laboratório já contém múltipla escolha, lacunas, transformação, ditado e classificação; não planejar novamente a criação desses tipos. A próxima evolução deve tornar a prática mais confiável e compreensível:

- **Escrita:** separar critérios formais, aderência à tarefa e correção gramatical. Presença de palavra-chave não demonstra uso correto; o feedback deve explicar esse limite.
- **Competências:** média histórica de todas as tentativas e autoavaliação de voz não são teste de proficiência. Apresentar origem, período, quantidade e diversidade de evidências; ensaiar recência e primeira tentativa sem apagar dados anteriores.
- **Revisão:** separar tempo máximo por atividade de orçamento da sessão; oferecer sessões curtas com fim claro e retomada dos erros relevantes.
- **Listening:** conferir cues por escuta humana, diferenciar transcrição integral de trechos selecionados e oferecer contexto de retomada. O catálogo possui 82 mídias, mas a transcrição integral registrada no fechamento cobre um subconjunto, não todo o curso.
- **Conclusão:** manter explícito que o certificado é interno e decorre dos critérios atuais de participação/conclusão, não de certificação oficial de nível. Alterar a regra exige decisão de produto e versão, não uma “correção” automática.

A sobreposição de cobertura da unidade `40-44` com a Aula 40 é deliberada e está explicada no roadmap anterior. Não é falha de matrícula nem deve ser “corrigida” renumerando conteúdo.

## Sequência proposta

| Ciclo | Resultado integrado | Dependências |
|---|---|---|
| 37 | Ambiente de teste seguro, escrita corrigível, sessão e fila sem perda silenciosa, backup verificável | Começar por DB-37/BE-37 antes de executar testes integrados |
| 38 | Concorrência e eventos idempotentes em sessão, escrita, jornada e revisão | Contratos e migrations antes da UI de conflitos |
| 39 | Minutos reais por período, áudio consistente, assistência com cota e retenção | Eventos e contratos do ciclo 38 |
| 40 | Conteúdo versionado e dados pessoais exportáveis/preservados | Backup e ensaio de migration disponíveis |
| 41 | Performance medida, históricos paginados e acessibilidade homologada | Contratos paginados e massa de dados isolada |
| 42 | Release com recuperação testada, monitoramento e fechamento pedagógico | Aceites técnicos anteriores e disponibilidade de testes humanos |

Trabalhos de menor dependência podem avançar em paralelo entre frentes, mas uma sprint não deve ser declarada concluída se apenas o frontend simula um contrato que ainda não existe. Os documentos por frente especificam entregáveis, cenários, dependências e critérios de aceite.

## Evidência mínima para fechar as novas sprints

- Reprodução do defeito antes e teste de regressão depois; testes em base isolada comprovadamente descartável.
- Contrato OpenAPI, tipos gerados e compatibilidade de clientes existentes quando houver mudança.
- Dois usuários, duas abas e pedidos simultâneos para toda alteração de estado privado/idempotente.
- Erro de rede, 401, 409, 413, 429, 5xx, quota local e reinício de processo nos fluxos correspondentes.
- Migrations com pré-verificação de dados, estratégia de rollback e preservação do histórico.
- Performance com massa e ambiente declarados, distinguindo amostra pontual de percentil.
- Evidências humanas de VoiceOver/TalkBack/Windows e cues, sem substituir pendências por aprovação automática de axe.
- Nenhum log ou relatório contendo senhas, tokens, texto pessoal, áudio ou dados identificáveis de estudantes.

## Verificações realizadas nesta auditoria

1. Estado Git e código no commit de referência; leitura de testes, configurações e documentação existente.
2. SQL somente leitura para catálogo, revisão Alembic, índices, privilégios do papel consultado e duas invariantes agregadas. Nenhum conteúdo pessoal foi extraído.
3. Reprodução em memória de clone de Request consumido, refresh 503 e limite de 101 respostas offline.
4. Função pura de escrita com exemplos multiword e varredura estrutural dos 236 requisitos do seed.
5. Contagem de 1 consulta para resumo de catálogo e 17 para detalhe da Aula 31, sem escrita e sem afirmar benchmark de carga.
6. Leitura de `nginx -T` e conferência do limite padrão na documentação oficial.

Não foi feita restauração, exclusão, seed, migration, teste de upload real, emissão de token de usuário ou homologação em dispositivo. Os achados não atestam ausência de outras falhas; delimitam um backlog executável baseado no estado observado.
