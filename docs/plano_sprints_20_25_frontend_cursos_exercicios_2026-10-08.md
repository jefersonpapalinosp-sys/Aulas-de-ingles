# Plano das Sprints 20–25 — frontend escalável, cursos e exercícios

Data da análise: 8 de outubro de 2026  
Estado: Sprints 20–24 implementadas; Sprint 25 permanece planejada
Próxima prioridade: Sprint 25 — piloto Level 2, unidade 1–5

## 1. Objetivo

Preparar o Aulas de Inglês para três mudanças já conhecidas:

1. concluir o recorte curricular adotado do *Let's Learn English — Level 1*, avançando da Aula 40
   até a Aula 52;
2. iniciar o *Let's Learn English — Level 2*, que possui outra numeração e maior complexidade;
3. oferecer uma página de exercícios por aula com prática curta, explicação e retomada, inspirada
   nas mecânicas observadas no Wordwall, mas com conteúdo, interface e feedback autorais.

Neste roadmap, `total_lessons = 52` registra a extensão oficial do Level 1 da VOA. O recorte
curricular implementado pelo projeto começa na Aula 31; as Aulas 1–30 não fazem parte do seed.
Portanto, “conclusão do Level 1” e eventual certificado significam concluir o recorte 31–52, e não
ter publicado ou estudado as 52 aulas oficiais dentro deste aplicativo.

A decisão principal é não acrescentar dezenas de itens à barra lateral atual. O problema mostrado
na captura não é apenas o tamanho da fonte ou a presença de uma barra de rolagem: a interface usa
uma lista plana como navegação, catálogo, progresso e acesso às ações globais. Esse modelo já está
no limite com dez aulas e não representa dois cursos com aulas de mesmo número.

O caminho proposto é:

```text
curso/nível → unidade → aula ou revisão → etapa de estudo/exercícios
```

## 2. Fontes analisadas

### 2.1 VOA Learning English

- [Let's Learn English — Level 1](https://learningenglish.voanews.com/p/5644.html)
- [Revisão das Lessons 40–44](https://learningenglish.voanews.com/a/lets-learn-english-review-lessons-40-44/3688551.html)
- [Revisão das Lessons 45–49](https://learningenglish.voanews.com/a/lets-learn-english-review-lesson-45-49/3765169.html)
- [Revisão das Lessons 50–52](https://learningenglish.voanews.com/a/lets-learn-english-review-lessons-50-51-52/3805506.html)
- [Exemplo de página individual — Lesson 41](https://learningenglish.voanews.com/a/lets-learn-english-lesson-41-teamwork/3635015.html)
- [Let's Learn English — Level 2](https://learningenglish.voanews.com/p/6765.html)
- [Revisão do Level 2 — Lessons 1–5](https://learningenglish.voanews.com/a/lets-learn-english-leve-2-review-of-lessons-1-5/4058114.html)
- [Exemplo de página individual — Level 2, Lesson 1](https://learningenglish.voanews.com/a/lets-learn-english-level-2-lesson1/3960391.html)

### 2.2 Referências de interação

- [Comparative and Superlative Adjectives](https://wordwall.net/pt/resource/98572095/english/comparative-and-superlative-adjectives)
- [Adverb or Adjective?](https://wordwall.net/resource/746380/esl-tefl/19-adverb-or-adjective)

Esses dois recursos são referências de mecânica, não fontes para copiar perguntas. O projeto deve
criar enunciados, alternativas, explicações, imagens e áudio próprios ou compatíveis com a política
de mídia já documentada.

## 3. Diagnóstico da interface atual

### 3.1 O que a captura evidencia

Com apenas as Aulas 31–40:

- a lista de aulas já ocupa praticamente toda a altura da janela;
- a área “Fechamento” fica abaixo da dobra e exige rolagem dentro da barra;
- títulos e focos gramaticais usam duas ou três linhas por item;
- cada aula adiciona dois controles ao teclado: link e botão de conclusão;
- os pequenos quadrados de conclusão não comunicam claramente o estado sem depender da posição;
- conteúdo principal e barra lateral possuem rolagens independentes;
- existe bastante espaço livre à direita em monitores largos, enquanto a navegação está congestionada.

Acrescentar as Aulas 41–52 criaria 22 linhas. Achatar também as 30 aulas e revisões do Level 2
transformaria a barra em um catálogo com dezenas de itens e mais de cem paradas de foco.

### 3.2 Limitações confirmadas no código

| Área | Estado atual | Consequência |
|---|---|---|
| `LessonRail.tsx` | fixa “Level 1” e “Bloco 31–40” e renderiza todas as aulas | lista cresce indefinidamente |
| `styles.css` | rail com `height: 100vh` e `overflow-y: auto` | ações globais somem abaixo da lista |
| responsividade | abaixo de 860 px, o rail inteiro fica antes do conteúdo | dezenas de aulas antecederiam o estudo no celular e no zoom |
| `App.tsx` | rotas usam apenas `/aulas/:numero` | Level 1/Aula 1 e Level 2/Aula 1 colidem |
| `Lesson.number` | número globalmente único no banco | o Level 2 não pode coexistir corretamente |
| API de aulas | devolve uma lista global ordenada só por número | não há curso, unidade ou revisão |
| `MapPage.tsx` | texto e título fixos em 31–40 | mapa não representa novo conteúdo |
| `LessonPage.tsx` | anterior/próxima e Level 1 codificados | fronteiras não são dirigidas pelo currículo |
| `StudyPage.tsx` | aquecimento e foco de listening ficam no componente | cada aula nova exigiria código frontend |
| `TestPage.tsx` | prova fixa do bloco 31–40 | revisões e avaliações não possuem escopo próprio |
| testes | várias expectativas literais de dez aulas e 31–40 | a expansão quebra testes por desenho, não por regressão |

O seed atual possui dez aulas e 110 exercícios: 61 lacunas, 19 múltiplas escolhas, dez ditados,
dez ordenações e dez transformações. Isso significa que o motor de atividades já é uma base útil;
o frontend precisa de uma sessão melhor, não de um segundo motor paralelo.

### 3.3 Problemas que não devem ser resolvidos apenas com CSS

Não é suficiente:

- reduzir fonte, espaçamento ou altura de cada aula;
- deixar a lista com uma rolagem ainda maior;
- virtualizar todas as aulas;
- esconder títulos e manter apenas números;
- criar outra sidebar exclusiva para o Level 2.

Essas opções preservariam a colisão de identidade, a falta de unidades e o excesso de navegação.
Virtualização também adicionaria complexidade de foco e leitura de tela sem necessidade: unidades
recolhidas e uma busca simples já reduzem o DOM.

## 4. Análise da expansão curricular

### 4.1 Fechamento do Level 1

A página oficial descreve o Level 1 como um curso iniciante de 52 semanas, com speaking,
vocabulário, escrita, materiais e avaliações. Depois da Aula 40 restam doze aulas. As revisões
oficiais mostram uma divisão pedagógica melhor que um único “bloco 41–52”.

| Unidade proposta | Aula | Foco principal | Exercícios adequados |
|---|---:|---|---|
| 40–44 | 41 | condicional real com `if` | completar duas partes, consequência provável, stress contrastivo |
| 40–44 | 42 | reflexivos, `while` e past continuous | linha do tempo, sequência, pronome correto, listening |
| 40–44 | 43 | `could`, `would`, `be able to`, obrigação e `too` | pedido polido, transformação e escolha de registro |
| 40–44 | 44 | `must`, `mustn't`, `should`, `don't have to` | classificar obrigação, conselho, proibição e ausência de necessidade |
| 45–49 | 45 | future continuous | linha do tempo, previsão e lacuna contextual |
| 45–49 | 46 | `lend`, `borrow` e `loan` | identificar papéis, completar diálogo e pedir permissão |
| 45–49 | 47 | revisão de continuous e reflexivos | correção, sequência e respostas para oferecer ajuda |
| 45–49 | 48 | present perfect | experiências, particípios e recomendações |
| 45–49 | 49 | present perfect versus presente/passado | escolher tempo por contexto e justificar a pista temporal |
| 50–52 | 50 | present perfect continuous | duração, `for`/`since` e compreensão oral |
| 50–52 | 51 | present perfect, gerúndio e infinitivo | classificar verbos, hábito e transformação |
| 50–52 | 52 | phrasal verbs e revisão de tempos | associação de sentido, contexto, revisão cumulativa e produção |

As revisões 40–44, 45–49 e 50–52 devem ser itens curriculares próprios. Elas não são aulas falsas:
têm objetivo de consolidação, listening quiz e métricas diferentes. A unidade 40–44 retoma a Aula
40 já existente e depois introduz 41–44.

Após a Aula 52, o produto deve mostrar a conclusão do recorte 31–52 do Level 1, revisão final,
competências observadas e acesso contextual ao Level 2. A revisão histórica 50–52 menciona um curso
seguinte da época de publicação; o aplicativo não deve copiar esse chamado antigo. A continuidade
atual deve apontar para a página oficial e para o catálogo presente do Level 2.

### 4.2 Level 2

O Level 2 é apresentado como intermediário e possui 30 aulas. Sua numeração recomeça em 1, o que
torna obrigatória uma identidade composta por curso e número, ou um ID/slug global estável.

A listagem oficial intercala checkpoints após:

- Lessons 1–5;
- Lessons 6–10;
- Lessons 11–15;
- Lessons 16–20;
- Lessons 21–25.

Não há uma revisão 26–30 na listagem principal. Caso o projeto crie um fechamento próprio, ele
deve ser identificado como conteúdo autoral, e não como revisão oficial da VOA.

As páginas do Level 2 também não têm exatamente a mesma composição das páginas do Level 1. O
template do projeto deve ser orientado por capacidades, por exemplo:

```text
has_main_video
has_conversation_audio
has_transcript
has_speaking_media
has_pronunciation_media
has_listening_quiz
has_downloads
```

Uma seção só aparece quando a capacidade e o conteúdo existem. O frontend não deve usar condições
como `if lesson.number === 41` nem presumir que todas as aulas têm as mesmas mídias.

## 5. Arquitetura de informação proposta

### 5.1 Hierarquia

```text
Cursos
├── Level 1 · iniciante
│   ├── Unidade 31–40
│   ├── Unidade 40–44 + revisão
│   ├── Unidade 45–49 + revisão
│   └── Unidade 50–52 + revisão/conclusão
└── Level 2 · intermediário
    ├── Unidade 1–5 + revisão
    ├── Unidade 6–10 + revisão
    ├── Unidade 11–15 + revisão
    ├── Unidade 16–20 + revisão
    ├── Unidade 21–25 + revisão
    └── Unidade 26–30
```

“Unidade 31–40” pode permanecer como unidade editorial existente durante a migração. A duplicação
da Aula 40 na revisão seguinte é uma retomada pedagógica, não uma segunda entidade de aula.

### 5.2 Rotas

Rotas canônicas sugeridas:

```text
/inicio
/cursos
/cursos/voa-level-1
/cursos/voa-level-1/unidades/40-44
/cursos/voa-level-1/aulas/41
/cursos/voa-level-1/aulas/41/estudar/assistir
/cursos/voa-level-1/aulas/41/exercicios
/cursos/voa-level-2/aulas/1
```

As rotas antigas devem continuar funcionando por redirecionamento:

```text
/aulas/31 → /cursos/voa-level-1/aulas/31
/aulas/31/estudar/assistir → equivalente no Level 1
```

O redirecionamento precisa preservar a etapa, parâmetros permitidos e links salvos. Novos vínculos
internos usam somente a rota canônica.

### 5.3 Navegação desktop

O rail passa a ter três regiões:

1. **Cabeçalho fixo:** seletor de curso, unidade atual e progresso contextual.
2. **Região central rolável:** somente a unidade atual expandida, com busca e aula ativa visível.
3. **Utilidades fixas:** Hoje, Cursos, Revisar, Caderno e avaliação da unidade.

Regras:

- apenas uma unidade fica expandida;
- uma lista visível não deve ultrapassar doze aulas;
- o tópico completo aparece no catálogo ou detalhe, não em todas as linhas compactas;
- a aula ativa recebe `aria-current="page"` e é posicionada dentro da região rolável;
- progresso do curso e da unidade têm rótulos e denominadores distintos;
- conclusão não usa apenas um quadrado vazio; deve haver ícone, texto acessível e estado visível;
- alvos recorrentes devem ser confortáveis para toque, acima do mínimo atual de 24 × 24 px.

### 5.4 Navegação móvel e zoom

Em celular, tablet estreito e equivalente a 200%:

- uma barra contextual curta substitui a lista acima do conteúdo;
- “Abrir trilha” apresenta curso, unidades e aulas em drawer ou diálogo;
- `Escape` fecha, o foco fica contido durante a abertura e retorna ao botão de origem;
- o título do conteúdo principal aparece antes de dezenas de links no fluxo de leitura;
- anterior, próxima e “Continuar” permanecem disponíveis fora do drawer;
- não pode existir rolagem horizontal do documento.

O stepper das cinco etapas precisa mostrar claramente que há mais conteúdo ou, preferencialmente,
usar uma versão compacta com etapa atual, anterior e próxima em telas pequenas.

### 5.5 Catálogo

A página de cursos/unidades assume a função de catálogo integral. Cada unidade mostra:

- nível e faixa de aulas;
- progresso e estado: não iniciada, em andamento ou concluída;
- aula atual ou próxima recomendação;
- número de aulas e presença de revisão;
- estimativa de estudo somente quando houver dados editoriais confiáveis.

O rail deixa de tentar cumprir essa função.

## 6. Página de exercícios por aula

### 6.1 Decisão de produto

A etapa “Praticar” e a nova página devem reutilizar o mesmo componente de sessão. Não haverá duas
correções, dois históricos ou dois contratos. A visão guiada pode mostrar um subconjunto dentro da
aula, enquanto a rota de exercícios oferece sessão completa, retomada e repetição de erros.

### 6.2 O que aproveitar das referências

Dos recursos do Wordwall, aproveitar apenas:

- instrução curta;
- uma decisão principal por questão;
- progresso visível;
- resposta imediata;
- ritmo de quiz.

Melhorias obrigatórias no projeto:

- explicar por que a resposta está certa ou errada;
- permitir nova tentativa antes do gabarito;
- ensinar a função da palavra, não apenas o sufixo;
- distinguir primeira tentativa de conclusão após dica ou resposta revelada;
- incluir listening, correção, produção e revisão espaçada;
- evitar generalizações sobre gênero/idade e afirmações factuais frágeis;
- explicar variantes informais em vez de chamá-las automaticamente de inválidas;
- não usar ranking público ou pressão de tempo por padrão.

### 6.3 Estrutura proposta

```text
Level 1 / Unidade 31–40 / Aula 40

The Woods Are Alive
Exercícios · Advérbios de modo                  [Voltar à aula]

[Prática guiada] [Desafio rápido] [Repetir meus erros]
[Todos] [Reconhecer] [Corrigir] [Produzir] [Ouvir]

Questão 3 de 10                   progresso 30%
┌─────────────────────────────────────────────────────────┐
│ instrução                                                │
│ enunciado autoral                                        │
│ controles nativos/teclado                                │
│ [Verificar] [Dica] [Rever teoria]                        │
│ feedback explicativo                                     │
└─────────────────────────────────────────────────────────┘

[Anterior]                                        [Próxima]
```

Ao concluir:

- acertos na primeira tentativa;
- itens concluídos depois de correção;
- respostas reveladas, sem contá-las como domínio;
- conceitos frágeis;
- ação “Repetir somente erros”;
- itens enviados à revisão existente;
- sugestão de escrita ou speaking relacionada à aula.

### 6.4 Tipos de interação

| Tipo | Uso | Situação atual |
|---|---|---|
| múltipla escolha | escolher forma ou sentido em contexto | suportado |
| lacuna | produzir forma curta | suportado como entrada textual |
| transformação/correção | reescrever frase inadequada | suportado |
| ordenação | montar frase sem depender de arrastar | suportado por botões |
| ditado | ouvir e escrever | suportado |
| classificação | adjetivo/advérbio, obrigação/conselho | evolução posterior do contrato |
| produção aberta | escrita ou speaking contextual | usar workspaces existentes |

Classificação por colunas não é requisito da primeira entrega. Ela exige resposta estruturada,
alternativa completa por teclado e critérios próprios. No primeiro corte, uma múltipla escolha pode
perguntar a função e uma segunda questão pode pedir a forma correta.

### 6.5 Pilotos editoriais

#### Aula 31 — comparativos

- `-er` versus `more`;
- presença de `than`;
- regras ortográficas;
- intensificadores de comparação;
- formas irregulares;
- correção de dupla marcação, como `more` junto de `-er`;
- listening e uma comparação pessoal.

#### Aula 38 — superlativos

- `-est` versus `most`;
- artigo `the`;
- comparação dentro de um grupo;
- formas irregulares;
- diferença entre comparativo e superlativo;
- contextos verificáveis, sem generalizações frágeis.

#### Aula 40 — adjetivos e advérbios

- identificar a palavra modificada;
- adjetivo antes do substantivo e depois de verbo de ligação;
- advérbio modificando ação ou adjetivo;
- formação com `-ly`;
- `good` versus `well`;
- `fast`, `hard`, `early` e `late`;
- adjetivos terminados em `-ly`, como `friendly`, `lovely` e `lonely`;
- diferenças de registro em usos informais.

Cada pack deve ter de oito a doze atividades, equilibrando reconhecimento, aplicação, correção,
listening e produção. Quantidade não substitui revisão editorial.

### 6.6 Estados da página

A implementação deve projetar e testar explicitamente:

- carregando;
- erro com nova tentativa;
- aula sem exercícios;
- introdução;
- sessão nova e retomada;
- questão não respondida ou parcialmente respondida;
- envio;
- correta;
- incorreta com nova tentativa;
- dica aberta;
- resposta revelada;
- tentativa offline e sincronização pendente;
- versão do conteúdo alterada durante uma sessão;
- áudio carregando, pronto ou indisponível com alternativa textual;
- sessão concluída e resumo.

Após trocar de questão, o foco vai para o novo enunciado. Feedback e progresso usam regiões vivas
sem repetir anúncios. Nenhuma atividade pode depender exclusivamente de cor, mouse, gesto ou drag.

## 7. Contrato e persistência necessários

Embora o foco inicial seja frontend, a navegação multi-curso exige suporte mínimo de backend e banco.

### 7.1 Modelo curricular

Modelo conceitual:

```text
course
  id, slug, title, level, proficiency_label, provider,
  source_url, position, status

course_unit
  id, course_id, slug, title, position, status

lesson
  id, course_id, unit_id, number, slug, position, ...

course_review
  id, unit_id, slug, title, position, source_kind, source_url, ...
```

O número deixa de ser identidade global. A restrição passa a ser equivalente a
`unique(course_id, number)`, preservando os IDs atuais das Aulas 31–40 para não perder tentativas,
progresso, revisão, textos ou gravações.

Revisão deve ser entidade curricular própria ou item discriminado no contrato. Não deve ser
armazenada como uma aula inventada apenas para caber na interface.

### 7.2 Dados que devem sair do frontend

- pergunta de aquecimento;
- foco da segunda escuta;
- unidade e posição;
- disponibilidade/status editorial;
- duração estimada, quando revisada;
- capacidades de mídia;
- anterior e próximo item curricular.

### 7.3 Contratos sugeridos

```text
GET /api/courses
GET /api/courses/{course_slug}/curriculum
GET /api/courses/{course_slug}/units/{unit_slug}
GET /api/courses/{course_slug}/lessons/{number}
GET /api/courses/{course_slug}/lessons/{number}/exercises
```

O resumo de aula precisa incluir ao menos:

```text
id
course_slug
unit_slug
number
slug
position
title
title_pt
grammar_tag
availability
studied/progress summary
```

### 7.4 Sessão de exercícios

O histórico de `exercise_attempt` e a idempotência atuais permanecem. Para retomada precisa em
outro dispositivo, considerar:

```text
practice_session
  id, user_id, lesson_id, lesson_version, mode, status,
  current_position, started_at, updated_at, completed_at

practice_session_item
  session_id, exercise_id, position, attempt_count,
  first_try_correct, answer_revealed, completed_at
```

O endpoint de tentativa pode receber `practice_session_id`. A resposta correta continua fora do
payload inicial.

## 8. Roadmap

| Sprint | Resultado principal | Dependência | Estado |
|---|---|---|---|
| 20 | navegação e catálogo escaláveis, com identidade multi-curso | nenhuma nova aula deve entrar antes dela | concluída |
| 21 | página de exercícios por aula e packs 31/38/40 | contrato da Sprint 20 | concluída |
| 22 | unidade Level 1 40–44 e revisão | Sprints 20 e 21 | concluída |
| 23 | unidade Level 1 45–49 e revisão | Sprint 22 | concluída |
| 24 | unidade Level 1 50–52, conclusão do recorte e transição | Sprint 23 | concluída |
| 25 | piloto Level 2 1–5 e prova de isolamento entre cursos | Sprint 24 | próxima |

## 9. Sprint 20 — navegação escalável e catálogo de cursos

**Estado:** concluída e validada em 8 de outubro de 2026.

**Objetivo:** resolver a dívida de frontend mostrada na captura e preparar a aplicação para dois
níveis sem aumentar indefinidamente a barra lateral.

**Foco:** frontend, com a menor migração de domínio necessária.

### Frontend

- criar shell de navegação global e contextual;
- criar seletor de curso/nível;
- separar progresso do curso e da unidade;
- criar catálogo de cursos e unidades;
- transformar a lista completa em unidade expansível/drawer;
- manter somente a unidade atual aberta;
- adicionar busca por número, título e tópico;
- trazer a aula ativa para a área visível;
- mover Hoje, Revisar, Caderno e avaliação para região sempre acessível;
- usar anterior/próxima segundo a ordem da API;
- substituir limites e textos fixos de 31–40;
- criar rotas canônicas com curso e redirecionamentos legados;
- projetar mobile/zoom com drawer ou diálogo acessível;
- ampliar alvos de toque e tornar o estado concluído inequívoco.

### Backend e banco indispensáveis

- criar curso e unidade;
- associar aulas existentes ao Level 1/unidade 31–40;
- trocar unicidade global por curso + número;
- expor currículo ordenado e progresso contextual;
- preservar IDs e todo o histórico existente;
- manter compatibilidade temporária nos endpoints antigos.

### Testes

- componente do novo rail/drawer;
- curso com mais de 52 aulas em fixture;
- Level 1/Aula 1 e Level 2/Aula 1 coexistindo;
- deep link para aula de unidade recolhida;
- busca sem resultado;
- teclado, `Escape`, foco contido e retorno de foco;
- desktop baixo, Pixel 5, 320 px e equivalente a 200%;
- redirects com todas as etapas de estudo;
- upgrade/downgrade da migration preservando IDs.

### Critérios de aceite

- destinos globais ficam acessíveis sem percorrer todas as aulas;
- nenhum grupo aberto mostra mais de doze aulas;
- no máximo uma unidade permanece expandida;
- a aula correta abre quando dois cursos possuem o mesmo número;
- aula ativa possui `aria-current="page"`;
- controles de expansão comunicam `aria-expanded`;
- não há rolagem horizontal do documento nos viewports definidos;
- no mobile, o conteúdo principal aparece antes do catálogo completo;
- progresso de um curso não altera o denominador de outro;
- nenhuma regra 31/40 permanece na navegação ou no cálculo anterior/próximo;
- URLs antigas continuam válidas;
- histórico das Aulas 31–40 permanece íntegro.

### Registro de conclusão

- catálogo e mapas de curso/unidade foram publicados com rotas canônicas por curso;
- o rail desktop foi dividido em progresso, atalhos, busca e unidades recolhíveis, sem lista plana;
- o mobile usa drawer modal com foco inicial, contenção de foco, `Escape` e retorno ao acionador;
- Course e CourseUnit passaram a fazer parte do domínio, e a identidade da aula agora inclui o curso;
- Level 1 e Level 2 estão no catálogo, com 52 e 30 aulas planejadas respectivamente;
- as dez aulas existentes permanecem no Level 1/unidade 31–40 com os mesmos IDs;
- endpoints antigos continuam resolvendo o Level 1, enquanto as rotas canônicas isolam progresso e
  sessão de estudo por curso;
- catálogo, currículo e detalhe público da aula canônica funcionam após recarga offline; áudio,
  progresso e dados privados continuam fora do cache;
- o OpenAPI e os tipos TypeScript foram regenerados no mesmo conjunto de mudanças;
- validação: 160 testes backend, 85 testes frontend e 38 execuções E2E em desktop/mobile;
- migration aprovada em upgrade, downgrade e novo upgrade, com seed idempotente e IDs preservados;
- lint, mypy, TypeScript, build, axe/WCAG e orçamento de 133,8 KiB gzip aprovados.

VoiceOver e TalkBack continuam como validações manuais transversais antes de uma publicação ampla;
eles não foram substituídos pelos testes automatizados.

### Fora do escopo

- cadastrar Aula 41;
- importar as 30 aulas do Level 2;
- redesenhar todos os componentes internos da aula;
- virtualizar a navegação.

## 10. Sprint 21 — laboratório de exercícios por aula

**Estado:** concluída e validada em 8 de outubro de 2026.

**Objetivo:** criar uma experiência reutilizável, curta e explicativa para exercícios por aula,
sem copiar Wordwall e sem duplicar o motor atual.

### Frontend

- criar rota canônica de exercícios;
- construir runner de uma questão por vez;
- oferecer prática guiada, desafio rápido e repetição de erros;
- adicionar filtros por objetivo sem ocultar o total real;
- mostrar progresso e estimativa somente com base em dados confiáveis;
- reutilizar `ExerciseCard` por adaptadores de interação;
- compartilhar a sessão com a etapa “Praticar”;
- criar retomada, resumo final e CTA para revisão;
- mover foco e anunciar feedback corretamente;
- criar link contextual para teoria, escrita e speaking;
- projetar todos os estados descritos na seção 6.6.

### Conteúdo piloto

- pack autoral da Aula 31 para comparativos;
- pack autoral da Aula 38 para superlativos;
- pack autoral da Aula 40 para adjetivos e advérbios;
- revisão editorial dos exemplos para neutralidade, precisão e registro.

### Backend e banco

- manter o gabarito fora da leitura inicial;
- adicionar sessão e retomada sincronizada, se validado pelo desenho técnico;
- registrar primeira tentativa, dica, revelação e conclusão separadamente;
- permitir filtrar exercícios por curso, aula, modalidade e objetivo;
- continuar usando idempotência e fila offline existentes;
- versionar o conjunto para detectar conteúdo alterado.

### Critérios de aceite

- os cinco tipos atuais funcionam sem outro motor de correção;
- recarregar retoma a mesma questão e seu estado permitido;
- responder errado permite dica, nova tentativa e explicação;
- resposta revelada não conta como acerto inicial;
- itens errados alimentam a revisão existente sem duplicação;
- a sessão inteira funciona somente por teclado;
- ordenação não depende de arrastar;
- troca de questão posiciona o foco no enunciado;
- feedback e progresso têm anúncio acessível e não repetitivo;
- tentativa offline sincroniza com a mesma chave idempotente;
- testes cobrem carregamento, vazio, erro, offline, correta, incorreta, dica, revelação e conclusão;
- nenhum texto, opção, imagem ou layout do Wordwall é reproduzido.

### Registro de conclusão

- foi criada a rota canônica `/cursos/:courseSlug/aulas/:numero/exercicios`, com uma questão por
  vez e o mesmo runner reutilizado na etapa **Praticar**;
- a página da aula deixou de repetir todos os cards e agora apresenta um resumo com CTA para o
  laboratório;
- prática guiada, desafio rápido e repetição de erros materializam uma ordem estável no servidor;
- filtros por tipo, competência e objetivo mostram simultaneamente o recorte e o total real do
  pack;
- sessão, posição, primeira tentativa, dicas, revelação e conclusão são sincronizadas por conta;
- um fingerprint interno detecta alteração de conteúdo sem publicar hashes do gabarito;
- leitura inicial não entrega resposta, dica nem explicação; a explicação só aparece depois de
  acerto ou revelação explícita;
- `ExerciseCard` continua sendo o único motor para lacuna, escolha, transformação, ordenação por
  botões e ditado;
- a fila offline v2 preserva a mesma chave idempotente e o contexto de sessão, curso e aula; uma
  queda durante envio ou sincronização não perde a tentativa;
- foco vai para o novo enunciado, progresso e feedback possuem anúncios acessíveis, e tentativa
  ainda não corrigida fica separada do total confirmado;
- packs autorais revisados foram publicados como versão 2: Aula 31 com 10 itens, Aula 38 com 11 e
  Aula 40 com 12, todos com objetivo explícito e duas dicas progressivas;
- a migração preserva IDs e tentativas anteriores e foi validada em instalação limpa e no ciclo
  `upgrade → downgrade → upgrade`;
- OpenAPI, tipos TypeScript e cache público dos enunciados foram atualizados; sessões e feedback
  privado permanecem `no-store`;
- validação final: 174 testes backend, 111 testes frontend e 50 execuções E2E em desktop/mobile;
- lint, mypy, TypeScript, build, axe/WCAG e orçamento de 141,3 KiB gzip foram aprovados.

### Fora do escopo

- ranking público;
- cronômetro obrigatório;
- classificação drag-and-drop;
- geração automática de questões por IA;
- liberar feedback assistido sem o gate já documentado.

## 11. Sprint 22 — Level 1, unidade 40–44

**Estado:** concluída e validada em 8 de outubro de 2026.

**Objetivo:** disponibilizar as Aulas 41–44 e o primeiro checkpoint no novo desenho.

### Implementação entregue

- Aulas 41–44 publicadas na unidade `40-44`, com áudio oficial, trechos de estudo,
  teoria, vocabulário, pronúncia, escrita e laboratório autoral;
- checkpoint `40–44` modelado como entidade curricular própria, com seis questões,
  listening da Aula 40, correção no servidor, idempotência, histórico por conta e indicação
  de bloco consolidado ou aulas a reforçar;
- mapa e rail exibem o checkpoint sem duplicar nem mover a Aula 40;
- painel Hoje recomenda o checkpoint depois das aulas necessárias;
- jornada e página completa passaram a usar presença de conteúdo e mídia como capacidade,
  oferecendo alternativa textual e omitindo seções vazias;
- procedência distingue a base oficial da VOA das explicações e atividades autorais;
- migrations, seed, OpenAPI e tipos TypeScript atualizados sem condições por número no frontend.
- validação final: 187 testes backend, 125 testes frontend e 52 execuções E2E em
  desktop/mobile, além de lint, tipagem, build de produção e ciclos limpos das migrations.

### Conteúdo e experiência

- auditar páginas, lesson plans, áudio, transcrição, speaking e pronúncia oficiais;
- cadastrar 41–44 com objetivos, estratégia, procedência e revisão editorial;
- criar exercícios originais adequados aos focos da seção 4.1;
- reutilizar player, listening, escrita, speaking e laboratório sem condições por número;
- criar item de revisão 40–44 com listening e retomada da Aula 40;
- mostrar o que foi concluído e o que será reforçado no checkpoint.

### Critérios de aceite

- Aula 41 aparece na unidade correta sem alongar o rail global;
- todas as quatro aulas passam pelo fluxo Preparar → Assistir → Estudar → Praticar → Revisar;
- mídias ausentes degradam com alternativa textual e sem cartão vazio;
- checkpoint possui identidade, progresso e resultado próprios;
- conteúdo oficial e conteúdo autoral ficam identificados;
- nenhuma condição `lesson.number === 41...44` é necessária no frontend;
- áudio e transcrição obedecem à política de licença/offline existente.

## 12. Sprint 23 — Level 1, unidade 45–49

**Estado:** concluída em 8 de outubro de 2026.

**Objetivo:** avançar pelo future continuous e present perfect usando a mesma arquitetura.

### Implementação entregue

- Aulas 45–49 publicadas na unidade `45-49`, totalizando 19 aulas disponíveis no recorte do
  Level 1;
- cada nova aula possui objetivos, teoria, vocabulário, pronúncia, proposta de escrita, áudio
  oficial da conversa com cinco trechos selecionados e oito exercícios autorais — ao menos quatro
  deles de listening;
- `Checkpoint 45–49` publicado como item curricular próprio, com seis questões, retomada do áudio
  da Aula 49, correção no servidor e resultado persistido por conta;
- explicações da revisão passaram a justificar o tempo verbal pelas pistas do contexto, como
  `at this time tomorrow`, `now`, `last night`, `for` e `never ... before`;
- avaliação, revisão espaçada, caderno, histórico de escrita, tentativas de fala, progresso e mapa
  de competências aceitam o escopo composto por curso e unidade;
- a avaliação da unidade seleciona uma questão de cada aula usando `course_slug + lesson_number`,
  sem deduplicar apenas pelo número;
- caderno e históricos mostram curso, unidade e aula, e seus links sempre retornam à rota canônica
  correta;
- a primeira aula de uma unidade oferece retorno ao checkpoint anterior; a última conduz ao
  checkpoint atual, e o resultado do checkpoint 40–44 continua para a Aula 45;
- contrato OpenAPI e tipos TypeScript foram atualizados para transportar a identidade curricular
  composta nos recursos privados;
- a suíte E2E da sprint cobre catálogo, unidade 45–49, fronteiras de navegação, avaliação escopada,
  áudio do checkpoint, correção, explicações temporais e restauração do resultado salvo.

### Entregas

- cadastrar Aulas 45–49 e revisão oficial da unidade;
- criar atividades de linha do tempo, `lend/borrow`, continuous, experiências e contraste de tempos;
- adicionar listening e produção ligados aos objetivos de cada aula;
- filtrar prova, revisão, caderno e progresso por curso/unidade;
- validar navegação entre unidades e retorno ao checkpoint anterior;
- garantir que o mapa de competências não misture amostras de outro curso.

### Critérios de aceite

- anterior/próxima funciona nas fronteiras 44→45 e 49→revisão;
- avaliação usa somente o escopo configurado da unidade;
- `TestPage` não deduplica aulas apenas pelo número global;
- revisão de present perfect explica pistas temporais, não só compara strings;
- histórico e caderno exibem curso + aula quando houver ambiguidade;
- catálogo permanece rápido e navegável com 19 aulas publicadas no Level 1.

## 13. Sprint 24 — Level 1, unidade 50–52 e conclusão do recorte

**Estado:** concluída em 8 de outubro de 2026.

**Objetivo:** concluir o recorte curricular 31–52 do Level 1 com revisão cumulativa e transição
responsável.

### Implementação entregue

- Aulas 50–52 publicadas na unidade `50-52`, totalizando 22 aulas no recorte 31–52, cada uma
  com teoria, vocabulário, pronúncia, escrita, áudio oficial, cinco trechos selecionados e oito
  exercícios autorais — quatro deles de listening;
- `Checkpoint 50–52` publicado como item curricular próprio, com seis questões, retomada do áudio
  da Aula 52, correção no servidor e procedência que separa a revisão oficial das atividades
  autorais;
- nova rota autenticada `/cursos/:courseSlug/conclusao`, acessível pelo mapa e pelo resultado do
  último checkpoint;
- resumo de fechamento derivado dos dados existentes, sem efeitos colaterais, distinguindo aulas
  vistas, aulas explicitamente concluídas e tendências de competência sustentadas por tentativas
  de exercícios, fala e escrita, com checkpoints apresentados separadamente; o endpoint consulta
  apenas as colunas necessárias, sem materializar teoria, exercícios e mídias de cada aula;
- unidades e checkpoints pendentes permanecem navegáveis e concluir somente a Aula 52 não altera
  qualquer outra aula;
- elegibilidade do certificado exige as 22 aulas concluídas e tentativas na versão atual dos três
  checkpoints dentro do recorte; somente então a tela oferece consulta manual à página oficial,
  avisa que o certificado externo considera o curso completo e nunca inicia download automático;
  o rótulo do escopo é derivado das unidades do curso, sem fixar `31–52` na tela genérica, e a
  publicação é conferida unidade por unidade para que faltas e excessos não se compensem;
- Level 2 apresentado a partir do catálogo atual como intermediário, recomendado e opcional, com
  autoavaliação curta sem produzir nota ou diagnóstico clínico/pedagógico fictício;
- contrato OpenAPI, cliente TypeScript, invalidação de cache e testes de backend, frontend e E2E
  atualizados para o fechamento do recorte.

### Entregas

- cadastrar Aulas 50–52;
- criar revisão oficial final com listening;
- criar resumo de conclusão por competência e evidência;
- disponibilizar certificado somente com regra clara de conclusão;
- permitir rever unidades incompletas sem bloquear o aluno;
- apresentar o Level 2 como intermediário e recomendado, não obrigatório;
- criar diagnóstico/preview curto antes de começar o próximo nível;
- preservar livre acesso às aulas já concluídas.

### Critérios de aceite

- concluir a Aula 52 não marca automaticamente todas as unidades;
- o resumo diferencia conteúdo visto, concluído e dominado com evidência;
- o CTA para Level 2 usa o catálogo atual, não texto histórico da revisão antiga;
- revisão final mantém origem oficial e itens autorais identificados;
- navegação volta corretamente da conclusão para qualquer unidade do Level 1;
- nenhuma mídia ou certificado é baixado automaticamente.

## 14. Sprint 25 — piloto Level 2, unidade 1–5

**Objetivo:** comprovar em produção local que a arquitetura suporta um segundo curso com numeração
reiniciada e padrão de conteúdo diferente.

### Entregas

- cadastrar metadados do catálogo completo de 30 aulas, sem publicar conteúdo incompleto;
- publicar conteúdo auditado apenas para as Aulas 1–5 e sua revisão;
- adaptar o template às capacidades reais do Level 2;
- mostrar “Level 2 · Aula 1” em toda referência ambígua;
- isolar progresso, caderno, revisão, gravações e recomendações por curso;
- ajustar recomendação “Hoje” para respeitar curso ativo e sessões incompletas;
- validar present perfect continuous, phrasal verbs, past perfect e revisão de comparativos no piloto.

### Critérios de aceite

- Level 1/Aula 1 e Level 2/Aula 1 coexistem com IDs, URLs e histórico distintos;
- troca de curso mantém o contexto e não mistura progresso;
- o catálogo mostra aulas futuras como indisponíveis/em preparação sem links quebrados;
- página do Level 2 não renderiza espaços vazios para mídia inexistente;
- revisão 1–5 é item próprio e contém listening;
- nenhuma revisão 26–30 é apresentada como oficial se for criada pelo projeto;
- bundle permanece dentro do orçamento atual de 170 KiB gzip;
- E2E cobre desktop, mobile, zoom equivalente a 200%, teclado e retomada entre cursos.

## 15. Critérios transversais de qualidade

### Acessibilidade

- landmarks e títulos coerentes;
- lista de aulas semântica;
- estados não dependem apenas de cor;
- alvo de toque adequado;
- ordem de foco curta e previsível;
- `aria-current`, `aria-expanded`, regiões vivas e nomes acessíveis;
- zoom/reflow a 200%;
- contraste forçado e movimento reduzido;
- roteiro manual com VoiceOver e TalkBack antes de publicação ampla.

### Performance

- buscar resumos, não aulas completas, para o catálogo;
- não pré-carregar áudio ou vídeo de unidades fechadas;
- manter chaves de cache por curso e aula;
- evitar biblioteca grande apenas para drawer, acordeão ou busca;
- preservar o orçamento de 170 KiB gzip;
- medir catálogo com pelo menos 82 aulas sintéticas e checkpoints.

### Editorial e direitos

- todo exercício novo precisa de explicação;
- exemplos devem ser verificáveis, neutros e adequados ao nível;
- conteúdo oficial, adaptação e autoria do projeto permanecem identificados;
- mecânicas pedagógicas podem inspirar o produto, mas banco de questões, imagens e redação externa
  não devem ser copiados;
- mídias continuam `network_only` até cumprir todos os requisitos da política offline.

### Testes

- remover expectativas fixas de `1/10`, 31–40 e dez links;
- adicionar testes unitários para rail, drawer, catálogo e runner;
- cobrir duas aulas com o mesmo número em cursos diferentes;
- cobrir fronteiras de unidade e curso;
- cobrir tentativa errada → dica → nova tentativa → correta;
- cobrir resposta revelada, offline e sincronização idempotente;
- usar axe como complemento, não substituto da validação manual;
- validar migrations em upgrade e downgrade sem perda de histórico.

## 16. Métricas de produto

Não usar apenas nota final. Acompanhar:

- tempo/cliques para retomar a aula atual;
- uso da busca versus navegação por unidade;
- abandono antes de chegar ao conteúdo no mobile;
- conclusão por unidade e curso;
- acerto na primeira tentativa;
- correção depois de feedback;
- taxa de resposta revelada;
- conceitos que retornam na revisão;
- retomada bem-sucedida de sessão;
- erros de rota, mídia ou conteúdo indisponível.

Telemetria não deve coletar texto livre, áudio, resposta completa ou dado sensível fora das políticas
já estabelecidas.

## 17. Riscos e decisões

| Risco | Mitigação |
|---|---|
| cadastrar Aula 41 antes da fundação | concluir Sprint 20 primeiro |
| perder histórico ao mudar identidade | preservar IDs e testar migration/rollback |
| duplicar motor de exercícios | runner compartilhado com `ExerciseCard` e endpoints atuais |
| misturar progresso entre níveis | chaves e queries sempre incluem `course_id`/slug |
| página continuar longa | uma questão por vez e catálogo fora do rail |
| copiar conteúdo externo | apenas mecânicas; redação e materiais autorais |
| presumir mídias iguais nos níveis | renderização orientada por capacidades |
| excesso de dependências frontend | preferir componentes nativos e biblioteca atual |
| criar revisão inexistente 26–30 | marcar explicitamente como conteúdo autoral |
| Storybook aumentar manutenção cedo | reavaliar somente se o catálogo reutilizável ultrapassar o limiar documentado |

## 18. Definição de pronto do roadmap

O ciclo 20–25 estará concluído quando:

- a navegação não depender de lista plana nem de números globais;
- recorte curricular 31–52 do Level 1 completo e Level 2/1–5 coexistirem;
- revisões forem itens curriculares próprios;
- a página de exercícios funcionar nas Aulas 31, 38, 40 e nas novas unidades;
- nenhuma rota, progresso, prova ou caderno misturar cursos;
- todos os fluxos relevantes tiverem estados de erro, vazio, offline e retomada;
- testes automatizados e validações manuais de acessibilidade estiverem documentados;
- orçamento de performance, licença de mídia e privacidade continuarem aprovados.

## 19. Próxima ação recomendada

Iniciar a Sprint 25 sobre o contrato multi-curso e o fechamento validados na Sprint 24, publicando
somente as Aulas 1–5 auditadas do Level 2 e seu checkpoint. A numeração reiniciada deve provar o
isolamento de progresso, caderno, revisão, gravações e recomendações entre os níveis. As demais
aulas do catálogo continuam em preparação, sem páginas vazias nem conteúdo fictício, e cada novo
item permanece condicionado à auditoria de fonte, mídia, licença e autoria antes do seed principal.
