# Plano das Sprints 26–30 — expansão do *Let's Learn English — Level 2*

- Data de criação: 9 de outubro de 2026
- Estado geral: Sprint 26 implementada em piloto, com QA auditiva e execução visual pendentes;
  Sprints 27–30 planejadas
- Curso: *Let's Learn English — Level 2*
- Dependência: Sprints 20–25 concluídas
- Escopo curricular: Aulas 6–30 e checkpoints dos blocos 6–10, 11–15, 16–20 e 21–25

## 1. Objetivo

Ampliar o piloto do Level 2 sem perder o isolamento entre cursos, a rastreabilidade editorial, a
acessibilidade e o formato de estudo já validado. O ciclo está dividido em blocos de cinco aulas:

| Sprint | Unidade | Fechamento | Estado |
|---|---|---|---|
| 26 | Aulas 6–10 | review oficial como fonte + checkpoint autoral | implementada em piloto; QA manual pendente |
| 27 | Aulas 11–15 | review oficial como fonte + checkpoint autoral | planejada |
| 28 | Aulas 16–20 | review oficial como fonte + checkpoint autoral | planejada |
| 29 | Aulas 21–25 | review oficial como fonte + checkpoint autoral | planejada |
| 30 | Aulas 26–30 | sem review oficial; fechamento autoral, se criado | planejada |

Cada sprint deve entregar conteúdo utilizável, e não apenas registros de catálogo. Uma unidade
só muda de `planned` para `published` quando todas as aulas previstas no bloco possuem conteúdo,
procedência, exercícios, testes e alternativas acessíveis suficientes para o fluxo completo.

## 2. Fontes e limites da análise

### Fontes oficiais

- [Índice do Let's Learn English — Level 2](https://learningenglish.voanews.com/p/6765.html)
- lesson plans oficiais indicados no próprio índice para as Aulas 1–10, 11–20 e 21–30;
- página oficial de cada aula e de cada review existente;
- [Termos de uso da VOA](https://learningenglish.voanews.com/p/6861.html);
- [política de mídia e uso offline do projeto](politica_midia_offline_2026-10-08.md).

O índice oficial confirma os títulos, a ordem das 30 aulas e reviews após os blocos 1–5, 6–10,
11–15, 16–20 e 21–25. Ele **não apresenta review das Aulas 26–30**.

Este documento não atribui objetivos gramaticais, vocabulário, pronúncia ou habilidades a uma
aula apenas pelo seu título. Esses focos só entram no produto após auditoria da página individual,
do lesson plan e das mídias oficiais. Os títulos abaixo são os únicos metadados individuais já
considerados confirmados para as aulas ainda não auditadas.

### Uso de material externo

- a fonte oficial pode orientar sequência, contexto e objetivos, com atribuição;
- explicações em português, perguntas, alternativas, dicas e feedback do aplicativo são autorais;
- transcrições, imagens, vídeos e áudios não devem ser copiados nem disponibilizados offline sem
  permissão compatível e registro de procedência;
- URLs oficiais devem ser armazenadas como fonte, não como comprovação automática de licença;
- timestamps de listening são inicialmente conservadores e precisam de validação humana por
  escuta antes de serem descritos como sincronização auditada;
- uma indisponibilidade da mídia externa deve degradar para transcrição ou atividade textual,
  sem bloquear toda a aula.

## 3. Contrato comum das Sprints 26–30

### Conteúdo mínimo por aula

Depois da auditoria editorial, cada aula publicada deve possuir:

- título, URL oficial, objetivos e procedência;
- introdução e orientação de estudo em português;
- teoria e exemplos autorais aderentes ao lesson plan auditado;
- vocabulário e notas de pronúncia quando sustentados pela fonte;
- atividade de listening quando houver mídia adequada, com cues revisados por escuta;
- proposta de escrita e/ou fala coerente com os objetivos confirmados;
- pack autoral de exercícios com dicas e explicação de resposta;
- alternativas textuais para capacidades de mídia ausentes ou indisponíveis.

Não é obrigatório repetir uma quantidade fixa de blocos, termos ou mídias. A interface continua
orientada por capacidades e deve omitir seções vazias.

### Frontend comum

- preservar as rotas canônicas com `courseSlug` e número da aula;
- exibir somente aulas `published` como destinos navegáveis;
- atualizar rail, mapa, busca, anterior/próxima e painel Hoje por dados da API;
- manter o fluxo Preparar → Assistir → Estudar → Praticar → Revisar;
- reutilizar o laboratório de exercícios, player, caderno, escrita e fala;
- sinalizar claramente fonte oficial, adaptação e conteúdo autoral;
- manter estados de carregamento, vazio, erro, offline e mídia indisponível;
- preservar reflow a 200%, navegação por teclado e leitores de tela;
- impedir que conteúdo planejado gere links vazios ou contagens enganosas.

### Backend comum

- consultar aulas, progresso, sessões, tentativas, revisão e competências por curso e unidade;
- manter gabaritos fora dos payloads iniciais;
- corrigir novos tipos de exercício no servidor;
- registrar tentativa, dica, revelação e conclusão de forma idempotente;
- aceitar capacidades diferentes entre aulas sem regras condicionais por número;
- produzir checkpoints como entidades curriculares próprias, nunca como aulas artificiais;
- preservar `Cache-Control: private, no-store` nos recursos privados;
- manter compatibilidade de contrato ou versionar explicitamente mudanças incompatíveis.

### Banco de dados e seed comuns

- preservar a identidade composta por curso + aula e curso + unidade;
- manter IDs e histórico existentes em migrations de upgrade e downgrade;
- registrar estado editorial (`planned`, `published` ou equivalente) separadamente da existência
  da unidade no catálogo;
- persistir fonte, autoria, política offline e estado de auditoria da mídia;
- versionar packs para que mudanças de conteúdo não corrompam tentativas anteriores;
- tornar o seed idempotente e determinístico;
- não criar aulas futuras apenas para completar contadores.

### Testes comuns

- pytest para API, correção, filtros, isolamento entre cursos, idempotência e migrations;
- Vitest para páginas, runner, estados de capacidade, navegação e feedback;
- Playwright em desktop e mobile para uma jornada completa da unidade e seu checkpoint;
- axe e verificações estruturais de acessibilidade, complementadas por testes manuais;
- teste de teclado sem depender de arrastar, apontar ou ouvir;
- teste de queda de mídia externa e alternativa textual;
- lint, tipagem, build de produção e orçamento de até 170 KiB gzip;
- migrations em instalação limpa e no ciclo `upgrade → downgrade → upgrade`;
- inspeção editorial das questões antes da publicação e registro explícito dos cues que ainda
  aguardam escuta humana.

## 4. Sprint 26 — Level 2, Aulas 6–10 e classificação

**Estado:** implementação concluída em piloto em 9 de outubro de 2026; validação humana dos
timestamps de listening e execução visual dos cenários browser ainda pendentes e registradas.

**Objetivo:** publicar o segundo bloco do Level 2, seu checkpoint e um tipo reutilizável de
exercício de classificação, mantendo o contrato de qualidade do piloto 1–5.

### Catálogo oficial confirmado

| Aula | Título e página oficial auditada | Foco confirmado no lesson plan/review |
|---:|---|---|
| 6 | [*Will It Float?*](https://learningenglish.voanews.com/a/lesson-6-will-it-float/4064553.html) | preposições de lugar; compartilhar informações; consultar fontes |
| 7 | [*Tip Your Tour Guide*](https://learningenglish.voanews.com/a/lesson-7-tip-your-tour-guide/4064769.html) | posição e movimento; descrever lugares; recomendações e conhecimento prévio |
| 8 | [*The Best Barbecue*](https://learningenglish.voanews.com/a/lets-learn-english-level-2-lesson-8-best-barbecue/4073994.html) | voz passiva; dar razões; culinária/cultura e perguntas |
| 9 | [*Pets Are Family, Too!*](https://learningenglish.voanews.com/a/lets-learn-english-level-2-lesson-9-pets-are-family-too/4074883.html) | modais sobre o passado; tag questions; opiniões, animais e cooperação |
| 10 | [*Visit to Peru*](https://learningenglish.voanews.com/a/lets-learn-english-lesson-10-visit-to-peru/4079037.html) | hope/wish; tradições e acontecimentos da vida; apoio dos sons à compreensão |

O índice também confirma o [**Review of Level 2 Lessons
6–10**](https://learningenglish.voanews.com/a/lets-learn-english-review-lesson-6-10/4079032.html).
O review é a fonte da consolidação; as perguntas e explicações do checkpoint do aplicativo são
autorais.

### Conteúdo e auditoria

- [x] auditar individualmente as cinco páginas, os lesson plans e o review 6–10;
- [x] inventariar mídia, duração, URL oficial, transcrição disponível e restrições de uso;
- [x] registrar apenas objetivos e focos confirmados nas fontes auditadas;
- [x] criar explicações, atividades, dicas e feedback autorais;
- [x] publicar MP3 oficial nas Aulas 6, 7, 9 e 10 e usar a faixa sonora do MP4 oficial na Aula 8,
  cuja página não oferece MP3 separado;
- [x] revisar documentalmente clareza, nível e correspondência entre objetivo e exercício;
- [x] publicar checkpoint autoral 6–10 com listening da Aula 9;
- [ ] conferir por escuta humana os 25 timestamps conservadores antes de chamá-los de
  sincronização auditada.

### Exercício de classificação

Adicionar `classification` ao contrato compartilhado de exercícios para atividades em que o aluno
distribui itens entre categorias. O primeiro uso aborda “adjetivo ou advérbio” na Aula 8 como
**complemento autoral solicitado para o projeto**, identificado separadamente do foco oficial da
aula, que é voz passiva. O tipo não fica acoplado ao tema e também é usado para posição/movimento
na Aula 6 e hope/wish na Aula 10.

#### Frontend

- apresentar categorias com nomes e instrução acessíveis;
- permitir classificar por botões, seleção ou teclado, sem exigir drag-and-drop;
- permitir alterar uma escolha antes do envio;
- mostrar a categoria escolhida sem depender apenas de cor ou posição;
- anunciar erros e explicações sem revelar o gabarito antes da correção;
- funcionar no runner compartilhado, na retomada e na repetição de erros;
- preservar ordem previsível de foco em telas pequenas e zoom de 200%.

#### Backend e banco

- incluir `classification` no enum/contrato de tipo de exercício;
- modelar categorias e itens de modo estruturado e validável;
- aceitar uma atribuição por item e rejeitar item ausente, duplicado ou categoria inexistente;
- normalizar a resposta sem transformar categorias semanticamente diferentes na mesma chave;
- manter o mapa correto somente no servidor até o envio;
- devolver resultado por item e explicação após correção ou revelação;
- serializar sessão e fila offline sem perder as atribuições;
- preservar a leitura de exercícios antigos em migrations e seeds.

### Critérios de aceite

- Aulas 6–10 percorrem as cinco etapas de estudo e aparecem na unidade correta;
- títulos, fontes e objetivos publicados possuem evidência editorial registrada;
- checkpoint 6–10 possui identidade e histórico próprios;
- concluir o bloco não altera o progresso 1–5 nem o Level 1;
- `classification` funciona por teclado, toque e ponteiro sem arrastar;
- correção rejeita payload parcial, duplicado ou adulterado;
- retomada online e sincronização offline preservam as classificações;
- feedback informa quais itens precisam de revisão sem depender de cor;
- mídia e procedência foram auditadas; os cues permanecem marcados como timestamps conservadores
  até a conferência humana por escuta;
- verificações automatizadas executáveis no ambiente passam antes de mudar a unidade para
  `published`; qualquer validação visual impedida pelo ambiente fica registrada como QA pendente.

### Evidências da implementação

- seed validado com 32 aulas, 5 checkpoints, 287 exercícios e 3 atividades de classificação;
- migration validada em instalação limpa e no ciclo `upgrade → downgrade → upgrade`;
- contratos OpenAPI e TypeScript regenerados e conferidos;
- 221 verificações backend aprovadas, incluindo o baseline OpenAPI;
- 157 testes frontend, lint, tipagem, build e orçamento de bundle aprovados;
- 39 cenários Playwright versionados para desktop e mobile, totalizando 78 execuções previstas;
- execução visual dos cenários Playwright pendente porque não havia navegador disponível no
  ambiente controlado desta entrega;
- conferência humana por escuta dos 25 cues pendente, sem apresentá-los como sincronização
  auditada.

### Fora do escopo

- usar drag-and-drop como única interação;
- copiar itens de classificação do Wordwall ou de outra plataforma;
- publicar as Aulas 11–30;
- gerar automaticamente focos ou exercícios sem revisão editorial.

## 5. Sprint 27 — Level 2, Aulas 11–15

**Estado:** planejada.

**Objetivo:** publicar o terceiro bloco do Level 2 e consolidá-lo em um checkpoint próprio,
reutilizando o motor de exercícios ampliado na Sprint 26.

### Catálogo oficial confirmado

| Aula | Título confirmado no índice | Foco linguístico |
|---:|---|---|
| 11 | *The Big Snow* | a confirmar na auditoria da aula e do lesson plan |
| 12 | *Run! Bees!* | a confirmar na auditoria da aula e do lesson plan |
| 13 | *Save the Bees!* | a confirmar na auditoria da aula e do lesson plan |
| 14 | *Made for Each Other* | a confirmar na auditoria da aula e do lesson plan |
| 15 | *Before and After* | a confirmar na auditoria da aula e do lesson plan |

O índice confirma **Review of Level 2 Lessons 11–15**.

### Escopo

- auditar as cinco aulas, o lesson plan 11–20 e o review 11–15;
- publicar conteúdo teórico e prático autoral segundo os focos confirmados;
- cadastrar somente capacidades e mídias realmente disponíveis;
- criar checkpoint 11–15 com procedência, correção e histórico;
- validar navegação 10 → checkpoint 6–10 → 11 e 15 → checkpoint 11–15;
- reutilizar `classification` apenas quando houver objetivo pedagógico compatível;
- manter o bloco 16–30 indisponível e sem links vazios.

### Critérios de aceite

- as cinco aulas e o checkpoint são acessíveis pelas rotas canônicas;
- anterior/próxima respeita aulas, limites de unidade e checkpoints;
- busca e painel Hoje localizam o novo bloco sem carregar aulas completas;
- avaliação, revisão, caderno, escrita e fala mantêm o escopo do Level 2;
- nenhum foco linguístico é publicado sem fonte auditada;
- todos os testes comuns passam.

## 6. Sprint 28 — Level 2, Aulas 16–20

**Estado:** planejada.

**Objetivo:** publicar o quarto bloco do Level 2 e seu checkpoint, comprovando que narrativas
relacionadas ou aulas em partes continuam independentes no progresso.

### Catálogo oficial confirmado

| Aula | Título confirmado no índice | Foco linguístico |
|---:|---|---|
| 16 | *Find Your Joy!* | a confirmar na auditoria da aula e do lesson plan |
| 17 | *Flour Baby, Part 1* | a confirmar na auditoria da aula e do lesson plan |
| 18 | *Flour Baby, Part 2* | a confirmar na auditoria da aula e do lesson plan |
| 19 | *Movie Night* | a confirmar na auditoria da aula e do lesson plan |
| 20 | *The Test Drive* | a confirmar na auditoria da aula e do lesson plan |

O índice confirma **Review of Level 2 Lessons 16–20**.

### Escopo

- auditar as cinco aulas, o lesson plan 11–20 e o review 16–20;
- publicar conteúdo e exercícios autorais com as capacidades confirmadas;
- criar checkpoint 16–20 com resultado persistido e recomendação de retomada;
- tratar *Part 1* e *Part 2* como aulas distintas, sem conclusão automática em cadeia;
- testar deep links e retomada independente nas Aulas 17 e 18;
- manter a publicação do bloco independente das unidades posteriores.

### Critérios de aceite

- concluir uma parte não conclui a outra;
- retomada abre exatamente a aula e a etapa registradas;
- checkpoint recomenda aulas com base em evidência, não apenas em ordem numérica;
- conteúdo e mídia possuem procedência e estado de auditoria;
- todos os testes comuns passam.

## 7. Sprint 29 — Level 2, Aulas 21–25

**Estado:** planejada.

**Objetivo:** publicar o quinto bloco do Level 2 e o último checkpoint explicitamente listado
pela VOA para o curso.

### Catálogo oficial confirmado

| Aula | Título confirmado no índice | Foco linguístico |
|---:|---|---|
| 21 | *Trash to Treasure, Part 1* | a confirmar na auditoria da aula e do lesson plan |
| 22 | *Trash to Treasure, Part 2* | a confirmar na auditoria da aula e do lesson plan |
| 23 | *Rock Star* | a confirmar na auditoria da aula e do lesson plan |
| 24 | *I Feel Super!* | a confirmar na auditoria da aula e do lesson plan |
| 25 | *Only Human* | a confirmar na auditoria da aula e do lesson plan |

O índice confirma **Review of Level 2 Lessons 21–25**.

### Escopo

- auditar as cinco aulas, o lesson plan 21–30 e o review 21–25;
- publicar conteúdo e atividades autorais conforme os focos confirmados;
- criar checkpoint 21–25 com listening somente após auditoria de mídia;
- manter independentes as Aulas 21 e 22, ainda que formem uma narrativa em partes;
- preparar a transição para 26–30 sem apresentar um review oficial inexistente;
- revisar se o volume publicado continua dentro das metas de catálogo e performance.

### Critérios de aceite

- review oficial e checkpoint autoral aparecem com procedências distintas;
- a conclusão do checkpoint leva à Aula 26 planejada apenas quando ela estiver publicada;
- progresso e evidências das partes 1 e 2 permanecem separados;
- o catálogo continua navegável e dentro do orçamento de bundle;
- todos os testes comuns passam.

## 8. Sprint 30 — Level 2, Aulas 26–30 e fechamento autoral

**Estado:** planejada.

**Objetivo:** publicar as cinco aulas finais do Level 2 e concluir o curso no aplicativo sem
atribuir à VOA uma revisão que não existe no índice oficial.

### Catálogo oficial confirmado

| Aula | Título confirmado no índice | Foco linguístico |
|---:|---|---|
| 26 | *Look-alikes* | a confirmar na auditoria da aula e do lesson plan |
| 27 | *Fish out of Water* | a confirmar na auditoria da aula e do lesson plan |
| 28 | *For the Birds* | a confirmar na auditoria da aula e do lesson plan |
| 29 | *Where There's Smoke...* | a confirmar na auditoria da aula e do lesson plan |
| 30 | *Dream a Little Dream* | a confirmar na auditoria da aula e do lesson plan |

**Limite editorial:** o índice oficial consultado lista a Aula 30 e, em seguida, materiais gerais
do curso. Não há **Review of Level 2 Lessons 26–30**. Qualquer checkpoint, revisão cumulativa ou
fechamento criado pelo projeto deve receber rótulo visível de **conteúdo autoral do aplicativo**.

### Escopo

- auditar as cinco aulas e o lesson plan 21–30;
- publicar conteúdo e exercícios autorais segundo os objetivos confirmados;
- decidir editorialmente se haverá checkpoint 26–30, revisão cumulativa e/ou tela de conclusão;
- se criado, identificar o fechamento como autoral na UI, API, banco e documentação;
- derivar qualquer resumo de competências somente de evidências registradas;
- definir requisitos de conclusão sem alegar certificação oficial da VOA;
- manter livre acesso às aulas e unidades concluídas.

### Critérios de aceite

- Aulas 26–30 funcionam pelo fluxo completo e possuem auditoria editorial;
- a interface não usa “review oficial” para nenhum fechamento 26–30;
- eventual checkpoint autoral tem identidade, procedência e histórico próprios;
- concluir a Aula 30 não marca automaticamente aulas, checkpoints ou competências;
- resumo final diferencia conteúdo visto, concluído e desempenho observado;
- nenhuma tela promete diploma, equivalência ou certificação da VOA;
- todos os testes comuns passam, incluindo o curso completo com numeração sobreposta ao Level 1.

## 9. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| inferir gramática pelo título | exigir auditoria da página e lesson plan antes do seed publicado |
| copiar exercícios ou redação externos | usar apenas a mecânica; criar banco autoral e revisar procedência |
| confundir review oficial com checkpoint local | mostrar origem separada na UI, API e banco |
| apresentar review 26–30 como oficial | rotular todo fechamento desse bloco como autoral |
| cues imprecisos | validar início, fim e texto por escuta humana |
| indisponibilidade de mídia remota | oferecer alternativa textual e não bloquear a aula |
| `classification` depender de arrastar | fornecer interação primária por botões/seleção e teclado |
| novo tipo vazar gabarito | validar e corrigir no servidor; entregar respostas só após correção |
| misturar aulas de mesmo número | exigir curso + aula em URLs, consultas, caches e exportações |
| unidades planejadas inflarem progresso | calcular somente com conteúdo publicado |
| crescimento prejudicar a navegação | manter unidades recolhíveis, busca e payloads resumidos |
| regressão de histórico | migrations reversíveis, seed idempotente e testes com dados existentes |

## 10. Definição de pronto do ciclo 26–30

O ciclo estará concluído quando:

- as Aulas 6–30 estiverem publicadas a partir de fontes auditadas;
- os reviews oficiais 6–10, 11–15, 16–20 e 21–25 estiverem referenciados corretamente;
- os quatro checkpoints correspondentes tiverem conteúdo autoral e histórico próprio;
- qualquer fechamento 26–30 estiver identificado como autoral;
- `classification` estiver integrado ao runner, API, persistência, offline e acessibilidade;
- progresso, Hoje, revisão, competências, caderno, escrita, fala e exportação permanecerem
  isolados por curso;
- conteúdo planejado não aparecer como aula disponível nem alterar denominadores;
- todas as migrations, testes automatizados e verificações de qualidade estiverem aprovados;
- cues e fluxos essenciais tiverem validação humana documentada;
- o bundle permanecer dentro do limite vigente de 170 KiB gzip.

## 11. Ordem de execução registrada

1. concluir a QA manual de áudio e a execução visual da Sprint 26, sem bloquear a evolução do
   código já implementado;
2. executar a Sprint 27 somente após auditoria das Aulas 11–15;
3. executar a Sprint 28 somente após auditoria das Aulas 16–20;
4. executar a Sprint 29 somente após auditoria das Aulas 21–25;
5. executar a Sprint 30 somente após auditoria das Aulas 26–30 e decisão editorial explícita
   sobre o fechamento autoral.

As Sprints 27–30 ficam registradas neste arquivo como backlog formal. O estado `planned` não
autoriza publicar placeholders, inferir conteúdo ou expor rotas vazias.
