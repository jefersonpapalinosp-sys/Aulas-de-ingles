# Plano de evolução do Aulas de Inglês

**Versão do documento:** 1.1
**Data:** 7 de outubro de 2026
**Base analisada:** aplicação `v1.0.0`, caderno pessoal de estudos e VOA *Let's Learn English - Level 1*, lições 31 a 40
**Prioridade:** experiência frontend para estudo teórico e prático, com texto, correção, listening e speaking

## 1. Visão do produto

O projeto deve evoluir de um caderno digital com exercícios e revisão de vocabulário para um **ambiente pessoal de estudo de inglês**. A aplicação deve conduzir o estudante por uma rotina curta e clara:

1. entender o objetivo da aula;
2. assistir ou ouvir inglês autêntico;
3. estudar a teoria necessária;
4. praticar compreensão e escrita com correção explicada;
5. ouvir, repetir e gravar a própria voz;
6. refletir sobre os erros;
7. revisar no momento adequado.

O resultado esperado não é apenas “terminar uma aula”, mas melhorar competências separadas e observáveis: **vocabulário, gramática, listening, reading, writing, speaking e pronúncia**.

## 2. Fontes e análise do conteúdo

### 2.1 Materiais analisados

- [Caderno pessoal de estudos no Google Docs](https://docs.google.com/document/d/1tS8cnAA_Nk-QNhq0jsDPLvwQ4T2Y1BgDkslUgkhZ1VE/edit?usp=sharing)
- [VOA - Let's Learn English Level 1](https://learningenglish.voanews.com/p/5644.html)
- [VOA - material das lições 31 a 40](https://learningenglish.voanews.com/a/5273657.html)
- [VOA - guia de uso do curso](https://learningenglish.voanews.com/a/5181859.html)
- Aplicação local, seed, contrato OpenAPI, modelos, frontend e testes da versão `v1.0.0`

### 2.2 O que a VOA oferece

O curso Level 1 foi desenhado para iniciantes e distribuído em 52 semanas. O objetivo declarado é fazer o aluno compreender conversas e criar conversas próprias. Cada lição usa uma combinação consistente de:

- vídeo principal contextualizado;
- vídeo de palavras-chave e speaking;
- vídeo específico de pronúncia;
- diálogo em áudio MP3;
- transcrição da conversa;
- estratégia de aprendizagem;
- atividade comunicativa;
- quiz de listening;
- proposta de escrita;
- folha de atividades e material para o professor.

O guia oficial sugere pelo menos quatro dias de atividades por lição. Para uso individual, isso deve ser convertido em sessões curtas de 15 a 25 minutos, mantendo a sequência pedagógica e permitindo continuar do ponto em que o aluno parou.

### 2.3 O que o caderno pessoal acrescenta

O Google Docs contém material que não aparece de forma personalizada na VOA:

- explicações em português;
- exemplos ligados a trabalho, família, viagens, jogos e rotina;
- registro de respostas certas e erradas;
- percentuais de desempenho oral e escrito;
- exercícios criados durante as aulas;
- dúvidas de pronúncia anotadas foneticamente;
- links complementares;
- uma rotina semanal de listening, speaking, escrita, revisão e aula.

Esse material revela uma necessidade importante: o sistema deve permitir **anotações e exemplos pessoais sem misturá-los ao conteúdo oficial**. Dados pessoais e rascunhos devem pertencer ao usuário, enquanto o conteúdo curricular deve permanecer revisado e compartilhável.

### 2.4 Auditoria editorial necessária

As anotações são excelentes como memória de estudo, mas não devem ser importadas automaticamente como resposta correta. Há exemplos que precisam de revisão, como o uso de `fastly` no lugar de `fast`, `I don't used to` no lugar de `I don't use to`, traduções imprecisas e confusão entre nomes de pessoas e objetos.

Cada conteúdo deverá ter:

- fonte e URL de origem;
- tipo: oficial, explicação própria, exemplo pessoal ou exercício;
- status editorial: rascunho, revisado ou publicado;
- versão e data da última revisão;
- observação de licença e atribuição quando houver mídia externa.

Também é necessário evitar copiar letras completas ou outros materiais protegidos. Atividades com músicas podem guardar título, artista, vocabulário autoral e link externo, mas não devem armazenar a letra integral sem autorização.

### 2.5 Mapa pedagógico das lições 31 a 40

| Aula | Núcleo oficial | Estratégia | Listening/speaking e pronúncia |
|---|---|---|---|
| 31 | comparativos; pedir e dar conselho | visualizar | comparações; redução de `than` |
| 32 | objetos diretos e indiretos; interjeições | monitorar | pedir ajuda/informação; interjeições |
| 33 | nomes de agente e explicação de processos | sequenciar | explicar uma atividade; final `-er` americano |
| 34 | `might` e `will`; probabilidade | inferir | falar do futuro; ênfase em `might` e `will` |
| 35 | contáveis, incontáveis e unidades de medida | cooperar | pedir quantidades; redução de `of` |
| 36 | preposições de lugar | substituir | localizar objetos; substantivos compostos |
| 37 | pronomes possessivos e opinião | personalizar | concordar/discordar; possessivos |
| 38 | superlativos e descrição | avaliar | descrever pessoas e lugares; ênfase no superlativo |
| 39 | prefixos negativos | perguntar para esclarecer | analisar anúncios; `comfortable/uncomfortable` |
| 40 | advérbios, feedback e comparação de advérbios | autoavaliar | pedir feedback; projeção da voz |

A auditoria encontrou uma divergência prioritária: a Aula 32 estava centrada em `going to / will`, enquanto o caderno e o guia oficial definem objetos diretos/indiretos e interjeições como objetivos principais. O piloto iniciado em 7 de outubro de 2026 já corrigiu o seed, os exemplos e os exercícios dessa aula.

## 3. Diagnóstico da versão atual

### 3.1 Pontos fortes

- arquitetura full stack funcional e coberta por testes;
- conteúdo estruturado para dez aulas;
- autenticação segura para o contexto atual;
- respostas corrigidas no servidor sem publicar o gabarito;
- progresso por usuário;
- revisão SM-2 de vocabulário;
- OpenAPI como contrato entre backend e frontend;
- ambiente de desenvolvimento e produção em Docker;
- CI com lint, tipagem, testes, migrations e E2E;
- frontend responsivo e sem HTML arbitrário vindo do banco.

### 3.2 Limitações em relação à visão

| Área | Situação atual | Evolução necessária |
|---|---|---|
| Jornada | página longa por aula | sessão guiada com etapas e retomada |
| Mídia | link externo para a VOA | player integrado, transcrição e progresso |
| Listening | não medido | escuta segmentada, ditado e quiz |
| Speaking | notas estáticas de pronúncia | gravação, repetição, autoavaliação e feedback |
| Writing | respostas curtas de completar | editor, rubrica, versões e correção explicada |
| Correção | certo/errado + gabarito | diferenças, categorias de erro, dicas graduais |
| Revisão | somente vocabulário | revisão de frases, erros, listening e produção |
| Progresso | aula estudada e tentativas | competências, tempo, sequência e domínio |
| Conteúdo | seed monolítico | conteúdo versionado, mídia, transcrição e atividades |
| Personalização | conta e deck | metas, agenda, diário e exemplos pessoais |

## 4. Princípios de experiência

1. **Uma ação principal por tela.** O aluno deve saber o que fazer agora.
2. **Teoria perto da prática.** A explicação aparece imediatamente antes do exercício que a utiliza.
3. **Feedback ensina.** Não basta informar erro; é preciso mostrar o tipo, a diferença e uma próxima tentativa.
4. **Áudio é parte da aula.** Listening e speaking não podem ser apenas links externos.
5. **Resposta antes do gabarito.** Dicas progressivas preservam a recuperação ativa.
6. **Retomar sem esforço.** A sessão guarda etapa, posição do áudio e rascunhos.
7. **Português como apoio, não muleta.** Traduções podem ser ocultadas e reveladas sob demanda.
8. **Privacidade por padrão.** Gravações e textos pessoais pertencem ao usuário.
9. **Mobile first e teclado completo.** Estudar no celular não pode eliminar atalhos no desktop.
10. **Acessibilidade real.** Legendas, transcrição, foco visível, contraste, leitor de tela e redução de movimento.

## 5. Jornada de estudo proposta

### 5.1 Sessão de uma aula

Cada lição será uma trilha com progresso independente por etapa:

| Etapa | Objetivo | Atividade principal |
|---|---|---|
| Preparar | ativar conhecimento prévio | objetivo, pergunta inicial e autoavaliação |
| Assistir | compreender o contexto | vídeo principal com ou sem legenda |
| Entender | validar compreensão | perguntas de ideia geral e detalhes |
| Estudar | aprender a regra | teoria curta, exemplos e contraste PT/EN |
| Ouvir | reconhecer a fala real | áudio segmentado, ditado e ordenação |
| Praticar | produzir com apoio | completar, transformar, ordenar e responder |
| Falar | treinar fluência e pronúncia | shadowing, gravação e autoavaliação |
| Escrever | usar o conteúdo pessoalmente | produção curta com rubrica e revisão |
| Revisar | consolidar | cartões gerados pelos erros da sessão |

O aluno pode sair e retornar a qualquer momento. “Concluir aula” exige evidência mínima em compreensão, prática e produção, e não apenas abrir a página.

### 5.2 Rotina semanal sugerida

- **Dia 1:** vídeo, contexto, vocabulário e compreensão geral.
- **Dia 2:** teoria, prática guiada e listening detalhado.
- **Dia 3:** speaking, shadowing e produção escrita.
- **Dia 4:** quiz, correção dos erros e revisão espaçada.
- **Dias seguintes:** revisões curtas geradas pelo sistema.

## 6. Evolução do frontend

### 6.1 Nova arquitetura de navegação

Rotas sugeridas:

```text
/inicio                         painel de hoje
/trilhas                        catálogo de cursos/blocos
/trilhas/voa-level-1            mapa da trilha
/aulas/:numero                  visão geral da aula
/aulas/:numero/estudar/:etapa   sessão guiada
/revisar                        fila de revisão multimodal
/caderno                        textos, gravações, notas e erros
/progresso                      competências e histórico
/configuracoes                  áudio, privacidade e preferências
```

No celular, a navegação principal deve ter no máximo quatro destinos: **Hoje, Trilhas, Revisar e Progresso**. A conta e as configurações ficam no menu de perfil.

### 6.2 Painel “Hoje”

O painel deve responder três perguntas:

- o que estudar agora;
- quanto tempo isso deve levar;
- por que essa atividade foi escolhida.

Componentes:

- botão “Continuar aula” com etapa e tempo estimado;
- revisões vencidas por tipo;
- plano da semana;
- sequência de dias sem punição visual excessiva;
- evolução por competência;
- última correção importante;
- ação rápida para gravar ou escrever.

### 6.3 Workspace da aula

Substituir a página única muito longa por um workspace composto por:

- cabeçalho com objetivo, fonte, duração e progresso;
- índice lateral no desktop e barra de etapas no celular;
- conteúdo central com uma tarefa por vez;
- painel contextual de vocabulário/notas;
- rodapé persistente com anterior, dica e continuar;
- salvamento automático de rascunhos e posição;
- modo foco, com tradução e explicações recolhidas.

Componentes candidatos:

```text
features/study-session/
  StudySessionShell
  StepNavigator
  ResumeBanner
  SessionSummary

features/media/
  LessonMediaPlayer
  TimedTranscript
  TranscriptCue
  ABLoopControl
  PlaybackRateControl

features/practice/
  ChoiceActivity
  GapFillActivity
  ReorderActivity
  DictationActivity
  TransformationActivity
  FeedbackPanel

features/speaking/
  ShadowingPrompt
  AudioRecorder
  RecordingReview
  SpeakingSelfAssessment

features/writing/
  WritingPrompt
  WritingEditor
  CorrectionDiff
  RubricPanel
  RevisionHistory
```

Organizar o frontend por funcionalidades reduz o acoplamento das futuras páginas de mídia, speaking e writing. Componentes visuais genéricos ficam em `components/ui`; regras de estudo ficam em `features`.

### 6.4 Player de áudio e vídeo

O primeiro player deve usar APIs nativas do navegador e funcionar sem serviço de IA:

- play/pause e avanço/retorno de 5 segundos;
- velocidades `0.75x`, `1x`, `1.25x` e `1.5x`;
- loop de trecho A-B;
- seleção de uma frase da transcrição;
- destaque sincronizado quando existirem timestamps;
- legenda em inglês, tradução opcional e modo sem legenda;
- marcador “ouvir novamente depois”;
- atalhos de teclado documentados;
- controles acessíveis e operáveis por leitor de tela.

Não depender de autoplay. Navegadores o bloqueiam e isso também prejudica acessibilidade.

### 6.5 Listening prático

Tipos de atividade em ordem de implementação:

1. escolher o sentido geral após ouvir;
2. marcar palavras reconhecidas;
3. ordenar trechos de uma frase;
4. completar lacunas após ouvir;
5. ditado de frase completa;
6. ouvir sem texto e revelar a transcrição progressivamente;
7. distinguir pares difíceis para falantes de português.

O feedback do ditado deve destacar inserções, remoções e substituições, preservando contrações e aceitando variantes cadastradas. Pontuação e maiúsculas podem ser avaliadas separadamente do conteúdo.

### 6.6 Speaking e pronúncia

#### Primeira entrega: gravação e autoavaliação

Usar `getUserMedia` e `MediaRecorder` para:

- pedir permissão apenas ao iniciar a gravação;
- exibir claramente quando o microfone está ativo;
- gravar um trecho curto;
- ouvir modelo e gravação lado a lado;
- repetir sem salvar;
- salvar somente com consentimento;
- avaliar clareza, ritmo, volume e confiança com uma rubrica simples.

O shadowing deve seguir o ciclo: ouvir frase, ver marcações de ritmo, gravar, comparar, tentar novamente.

#### Segunda entrega: transcrição assistida

Uma etapa posterior pode enviar a gravação para speech-to-text e comparar a transcrição com o texto esperado. Essa comparação mede reconhecimento de palavras, não pronúncia fonética completa. O sistema não deve apresentar um “score de pronúncia” absoluto baseado apenas no texto transcrito.

#### Terceira entrega: feedback fonético

Somente após validar a experiência básica, avaliar alinhamento por palavra/fonema, confiança do modelo e feedback específico para sons difíceis. Resultados de baixa confiança devem ser apresentados como sugestão, nunca como verdade.

### 6.7 Escrita e correção textual

Haverá dois níveis de correção.

**Objetiva e determinística:**

- normalização controlada;
- respostas alternativas cadastradas;
- comparação token a token;
- categoria do erro: vocabulário, verbo, ordem, preposição, artigo, ortografia ou pontuação;
- dica 1 conceitual, dica 2 estrutural e resposta somente quando solicitada;
- nova tentativa após o feedback.

**Produção aberta:**

- editor com salvamento automático;
- prompt relacionado à vida do aluno;
- rubrica para conteúdo, gramática, vocabulário e clareza;
- marcações ligadas a trechos do texto;
- explicação em português e exemplo corrigido em inglês;
- botão para aceitar, rejeitar ou editar uma sugestão;
- versões “original”, “após feedback” e “final”.

A correção aberta deve começar com regras e rubricas manuais. Um corretor baseado em modelo de linguagem é opcional e posterior, atrás de feature flag, com limites de custo, remoção de dados pessoais e aviso de que sugestões podem falhar.

### 6.8 Feedback visual

O componente unificado `FeedbackPanel` deve apresentar:

- resultado da tentativa;
- trecho correto e trecho digitado;
- explicação curta;
- link para a teoria relacionada;
- ação “tentar de novo”;
- ação “adicionar este erro à revisão”;
- nível de confiança quando o feedback vier de IA ou speech-to-text.

Evitar depender apenas de vermelho e verde. Usar ícone, texto e estado anunciado por `aria-live`.

### 6.9 Progresso por competência

Exibir separadamente:

- aulas iniciadas e concluídas;
- minutos de escuta e fala;
- textos produzidos e revisados;
- acerto na primeira tentativa;
- retenção nas revisões;
- desempenho por competência;
- tópicos que precisam de atenção.

O painel não deve inventar precisão. Com poucas atividades, mostrar “dados insuficientes” em vez de uma porcentagem enganosa.

### 6.10 Caderno pessoal

O caderno reunirá:

- anotações livres por aula;
- frases favoritas;
- exemplos pessoais;
- erros recorrentes;
- textos e suas versões;
- gravações mantidas pelo aluno;
- itens marcados para perguntar ao professor.

Conteúdo pessoal nunca deve alterar o seed ou aparecer para outro usuário.

### 6.11 Acessibilidade e responsividade

Critérios obrigatórios:

- WCAG 2.2 AA como referência;
- navegação completa por teclado;
- foco visível e ordem lógica;
- transcrição para toda mídia de fala;
- legenda e alternativa textual;
- controles com rótulos claros;
- alvos de toque adequados;
- layout funcional a partir de 320 px;
- respeito a `prefers-reduced-motion`;
- nenhuma atividade dependente apenas de ouvir, enxergar cor ou arrastar.

## 7. Evolução do backend

### 7.1 Organização por domínios

Manter FastAPI e SQLAlchemy, mas separar o crescimento em módulos:

```text
app/
  api/
    content.py
    study_sessions.py
    activities.py
    media.py
    writing.py
    speaking.py
    progress.py
    review.py
  domain/
    correction/
    scheduling/
    transcription/
  services/
    object_storage.py
    speech_to_text.py
    text_feedback.py
```

Integrações externas devem ficar atrás de interfaces. Assim, o projeto pode usar implementação local nos testes e trocar provedor de armazenamento, transcrição ou correção sem mudar endpoints e regras de domínio.

### 7.2 Endpoints propostos

```text
GET    /api/learning-paths
GET    /api/lessons/{number}/study-plan

POST   /api/study-sessions
GET    /api/study-sessions/current
PATCH  /api/study-sessions/{id}
POST   /api/study-sessions/{id}/complete-step

GET    /api/activities/{id}
POST   /api/activities/{id}/attempts
GET    /api/activities/{id}/hints/{level}

GET    /api/media/{id}/transcript
GET    /api/media/{id}/position
PUT    /api/media/{id}/position
DELETE /api/media/{id}/position

POST   /api/speaking/attempts
POST   /api/speaking/attempts/{id}/upload-url
POST   /api/speaking/attempts/{id}/transcribe
DELETE /api/speaking/attempts/{id}

POST   /api/writing/submissions
POST   /api/writing/submissions/{id}/revisions
POST   /api/writing/submissions/{id}/feedback

GET    /api/me/skills
GET    /api/me/today
GET    /api/me/notebook
```

O endpoint de tentativa deve receber uma chave de idempotência para evitar duplicação quando a conexão móvel oscilar.

### 7.3 Processamento assíncrono

Playback, exercícios determinísticos e gravação local não precisam de fila. Transcrição e correção por IA podem exceder o tempo de uma requisição; quando forem introduzidas, usar jobs com estado:

```text
queued -> processing -> completed | failed | canceled
```

Para a primeira versão, uma tabela de jobs e worker simples é suficiente. Adotar Redis/Celery somente quando volume ou confiabilidade justificarem a complexidade.

### 7.4 Armazenamento de áudio

- PostgreSQL guarda metadados, permissões, duração e status.
- Arquivos ficam em object storage, nunca em colunas binárias do banco.
- Upload em produção deve usar URL assinada e limite de tamanho/duração.
- Formatos aceitos devem considerar o resultado real do `MediaRecorder` por navegador.
- O usuário precisa conseguir excluir a gravação.
- Gravações temporárias devem ter expiração automática.

## 8. Evolução do banco de dados

### 8.1 Conteúdo curricular

| Tabela | Finalidade | Campos centrais |
|---|---|---|
| `learning_path` | curso ou trilha | `id`, `slug`, `title`, `level`, `language` |
| `learning_path_lesson` | ordem das aulas | `path_id`, `lesson_id`, `position` |
| `lesson_version` | versão editorial | `lesson_id`, `version`, `status`, `published_at` |
| `content_source` | origem e atribuição | `url`, `publisher`, `license_note`, `accessed_at` |
| `lesson_media` | áudio/vídeo externo ou próprio | `kind`, `source_url`, `duration_seconds` |
| `transcript_cue` | trecho sincronizado | `media_id`, `start_ms`, `end_ms`, `speaker`, `text_en`, `text_pt` |
| `exercise` | item de atividade reutilizável | `lesson_id`, `activity_type`, `skill`, `prompt`, `position` |
| `exercise_answer` | variantes objetivas | `exercise_id`, `value`, `position` |
| `exercise_hint` | dicas graduais | `exercise_id`, `level`, `content` |
| `rubric` | critérios de produção | `activity_id`, `criteria` |

`payload`, `criteria` e regras variáveis podem usar JSONB, mas relações consultadas e métricas devem continuar normalizadas.

**Decisão implementada:** o modelo não ganhou um invólucro `activity` vazio. `exercise` representa
o item executável e já contém tipo e competência; `exercise_answer` e `exercise_hint` normalizam
as partes repetidas. Essa estrutura atende aos cinco tipos atuais com menos junções e sem
duplicar o conceito existente.

### 8.2 Progresso e produção do usuário

| Tabela | Finalidade | Campos centrais |
|---|---|---|
| `study_session` | retomada da sessão | `user_id`, `lesson_id`, `current_step`, `status`, `started_at`, `ended_at` |
| `step_progress` | progresso granular | `session_id`, `step`, `status`, `seconds_spent` |
| `media_progress` | retomada de áudio/vídeo | `user_id`, `media_id`, `position_seconds`, `updated_at` |
| `activity_attempt` | tentativa generalizada | `user_id`, `item_id`, `answer`, `score`, `feedback`, `created_at` |
| `writing_submission` | texto original | `user_id`, `activity_id`, `content`, `status` |
| `writing_revision` | versões do texto | `submission_id`, `version`, `content`, `created_at` |
| `speaking_attempt` | metadados da fala | `user_id`, `activity_id`, `storage_key`, `duration_ms`, `consent_at` |
| `transcription_job` | processamento de fala | `attempt_id`, `status`, `provider`, `result`, `confidence` |
| `notebook_entry` | nota pessoal | `user_id`, `lesson_id`, `kind`, `content` |
| `skill_evidence` | evidência de competência | `user_id`, `skill`, `source_type`, `source_id`, `score`, `occurred_at` |
| `study_plan` | meta e agenda | `user_id`, `weekly_minutes`, `preferred_days`, `goal` |

### 8.3 Evolução da revisão espaçada

Generalizar `review_card` para aceitar mais de um tipo de conteúdo:

- vocabulário;
- frase com lacuna;
- erro gramatical recorrente;
- trecho de ditado;
- prompt de speaking;
- pergunta conceitual.

Uma abordagem segura é manter as cartas atuais e adicionar `review_item` com `item_type` e referência ao conteúdo. A migração deve preservar integralmente o histórico SM-2 já existente.

## 9. Estratégia de correção

### 9.1 Ordem de prioridade

1. respostas cadastradas e regras determinísticas;
2. análise de diferenças e categorias explícitas;
3. rubrica preenchida pelo próprio aluno;
4. feedback semiautomático baseado em regras;
5. speech-to-text para apoio ao speaking;
6. modelo de linguagem para texto aberto, opcional.

Essa ordem mantém custo, privacidade e resultados sob controle. IA não deve bloquear a conclusão de uma aula.

### 9.2 Histórico de erro

Registrar a categoria do erro permite responder perguntas úteis:

- o aluno erra mais artigos ou preposições?
- reconhece uma palavra no texto, mas não no áudio?
- escreve corretamente, mas não consegue produzir sem dica?
- melhorou após revisar?

Não guardar apenas `correct = true/false`; guardar também a evidência que explica o resultado.

## 10. Roadmap de implementação

Cada sprint deve manter a aplicação utilizável e incluir frontend, backend, banco, testes e documentação.

### Estado do piloto em 7 de outubro de 2026

Concluído no primeiro corte vertical:

- jornada guiada das Aulas 31–40 em cinco etapas, com retomada por usuário;
- correção editorial da Aula 32 para objetos diretos/indiretos e interjeições;
- metadados de mídia no banco e no contrato OpenAPI;
- players dos dez áudios oficiais da VOA com velocidade, saltos, loop A–B e posição sincronizada
  entre dispositivos, mantendo fallback local;
- 48 trechos de estudo selecionados nas Aulas 31–40, tradução opcional e navegação pelo áudio;
- atividades de listening em todas as Aulas 31–40 corrigidas no servidor;
- fontes oficiais/autorais e versões editoriais explícitas para as dez aulas;
- prática de *shadowing* com gravação local, reprodução e autoavaliação por frase;
- workspace de escrita da Aula 31 com autosave, fallback local, feedback determinístico e
  histórico de versões privado por conta;
- motor de atividades com lacuna, múltipla escolha, transformação, ditado e ordenação,
  tentativas idempotentes, cinco categorias de erro e dicas graduais na Aula 31;
- prática oral opcional com consentimento explícito, upload privado, histórico por conta e
  exclusão conjunta do metadado e do arquivo;
- caderno pessoal com notas por aula, textos, gravações, comparação de versões, histórico de
  feedback e exportação JSON dos dados do aluno;
- retomada da jornada sincronizada por conta, com fallback imediato no navegador;
- migration reversível, seed idempotente e cobertura unitária, integração e E2E.

As Sprints 6–14 estão concluídas no corte vertical. A assistência opcional permanece desligada
por padrão até cumprir o gate de avaliação humana. Próximas expansões possíveis são a
transcrições editoriais integrais, mais atividades de listening por aula e uma fila
durável para processamento assistido.

### Sprint 6 - Auditoria curricular e fundação da experiência

**Objetivo:** alinhar o conteúdo às fontes e preparar o frontend para crescimento.

**Estado:** concluída. As dez aulas possuem estratégia, origem oficial, explicação autoral,
versão e status editorial no banco e no contrato. A Aula 32 foi alinhada ao plano oficial, e a
interface expõe fonte e revisão sem misturar as anotações privadas do aluno. A migration cria
`content_source` e `lesson_version`; o seed é idempotente e preserva IDs referenciados.

Frontend:

- criar layout do painel Hoje e workspace da aula;
- criar barra de etapas e retomada local simulada;
- estabelecer tokens visuais, estados e componentes de formulário;
- revisar responsividade e navegação por teclado.

Backend:

- adicionar metadados de fonte e versão de conteúdo;
- criar leitura do plano de estudo de uma aula;
- manter compatibilidade com endpoints atuais.

Banco/conteúdo:

- corrigir o alinhamento da Aula 32;
- auditar lições 31–40 contra o guia da VOA;
- marcar conteúdo oficial, autoral e pessoal;
- criar migrations para `content_source` e `lesson_version`.

Aceite:

- cada aula tem objetivo oficial, estratégia, fonte e status editorial;
- nenhuma regressão nos fluxos atuais;
- workspace funciona em 320 px e por teclado.

### Sprint 7 - Player, transcrição e listening básico

**Objetivo:** transformar mídia externa em atividade de estudo.

**Estado:** concluída nas Aulas 31–40. Todas possuem áudio hospedado na VOA,
trechos textuais selecionados, tradução revelável e atividade de listening. A posição é
salva em `media_progress` por conta e também localmente para tolerar falhas de rede. O motor
existente `exercise`/`exercise_answer`/`exercise_hint` cumpre o papel originalmente chamado de
`activity`/`activity_item`, conforme a decisão de modelo registrada acima.

Frontend:

- implementar player acessível;
- velocidade, retorno, loop A-B e posição persistida;
- transcrição por frases e tradução revelável;
- atividades de compreensão geral e lacunas.

Backend:

- endpoints de mídia, transcrição e posição;
- servir metadados sem fazer proxy desnecessário de arquivos grandes.

Banco:

- `media_asset`, `transcript_cue`, `activity` e `activity_item`;
- conteúdo completo inicialmente para as aulas 31 e 32.

Aceite:

- aluno ouve, pausa, repete um trecho, acompanha a transcrição e conclui um exercício;
- progresso retorna após recarregar a página;
- mídia possui alternativa textual.

### Sprint 8 - Motor de atividades e feedback explicativo

**Objetivo:** suportar prática variada sem criar um componente específico por aula.

**Estado:** concluída no piloto da Aula 31. O mesmo contrato cobre lacuna, múltipla escolha,
ordenação, transformação e ditado, com feedback sem vazamento do gabarito, cinco categorias
de erro, dicas em dois níveis, nova tentativa e idempotência.

Frontend:

- lacuna, escolha, ordenação, transformação e ditado;
- `FeedbackPanel` com diferença, categoria e dicas;
- fluxo de nova tentativa antes do gabarito.

Backend:

- serviço de correção por tipo de atividade;
- tentativas idempotentes;
- dicas graduais e criação de item de revisão por erro.

Banco:

- respostas aceitas, dicas e tentativa generalizada;
- migrar exercícios atuais sem perder histórico.

Aceite:

- ao menos cinco tipos de atividade compartilham o mesmo contrato;
- feedback nunca expõe resposta antes da ação permitida;
- exercícios existentes continuam funcionando.

### Sprint 9 - Speaking, gravação e shadowing

**Objetivo:** tornar produção oral parte normal da aula.

**Estado:** concluída no piloto da Aula 31. A gravação nasce local, o upload só é liberado
após consentimento explícito e o histórico autenticado permite ouvir e excluir cada tentativa.
O áudio fica em volume privado, fora do PostgreSQL, limitado a 30 segundos e 2 MB. A política
de retenção é controlada pelo aluno: o arquivo permanece na conta até sua exclusão manual. Os
fluxos E2E rodam tanto no perfil Desktop Chrome quanto na emulação móvel Pixel 5.

Frontend:

- permissão e diagnóstico de microfone;
- gravador com duração máxima;
- comparação modelo/gravação;
- shadowing por frase;
- rubrica de autoavaliação e opção de excluir.

Backend:

- criação, upload e exclusão de tentativa oral;
- URLs assinadas ou armazenamento local em desenvolvimento;
- política de retenção.

Banco:

- `speaking_attempt` e consentimento;
- sem áudio binário no PostgreSQL.

Aceite:

- fluxo funciona no Chrome desktop e Android e degrada com explicação em navegador sem suporte;
- nenhuma gravação é enviada antes da confirmação;
- exclusão remove metadado e arquivo.

### Sprint 10 - Escrita, correção e caderno pessoal

**Objetivo:** apoiar produção escrita e aprendizado pelos próprios erros.

**Estado:** concluída no piloto da Aula 31. O editor mantém autosave e versões, mostra um diff
por palavras entre uma versão e o texto atual e persiste cada feedback estruturado. O caderno
privado reúne cinco tipos de anotação, produções escritas e gravações. A exportação JSON inclui
os dados pessoais de estudo sem senha, tokens ou chaves internas de armazenamento.

Frontend:

- editor com autosave;
- rubrica, diff e histórico de versões;
- caderno com notas, erros e frases favoritas.

Backend:

- submissões, revisões e feedback estruturado;
- serviço determinístico inicial de análise;
- exportação dos dados do aluno.

Banco:

- `writing_submission`, `writing_revision`, `notebook_entry` e feedback.

Aceite:

- aluno escreve, recebe feedback, revisa e compara versões;
- rascunho sobrevive a falha de rede;
- notas pessoais nunca aparecem no conteúdo público.

### Sprint 11 - Painel, plano semanal e competências

**Objetivo:** orientar consistência sem gamificação punitiva.

**Estado:** concluída. A entrada combina o painel Hoje com o mapa completo, mantendo livre o
acesso a qualquer aula. A recomendação segue uma ordem determinística — revisão vencida,
sessão incompleta e próxima aula — e mostra o motivo e o tempo estimado. O plano semanal pode
ser editado por meta, minutos e dias preferidos. As competências de gramática, compreensão
oral, escrita e fala recebem evidências das atividades já existentes; percentuais ficam
ocultos enquanto houver menos de três observações. A tabela `study_session_progress` existente
foi ampliada como sessão canônica, ligada a `step_progress`, sem duplicar o conceito em uma
segunda tabela.

Frontend:

- painel Hoje funcional;
- agenda semanal editável;
- progresso por competência e tópicos frágeis;
- resumo de sessão.

Backend:

- recomendação determinística da próxima atividade;
- agregação de evidências por competência;
- métricas de tempo e conclusão.

Banco:

- `study_plan`, `study_session`, `step_progress` e `skill_evidence`.

Aceite:

- sistema explica por que recomendou uma tarefa;
- percentuais só aparecem com amostra suficiente;
- o usuário pode estudar fora do plano sem perder progresso.

### Sprint 12 - Revisão multimodal adaptativa

**Objetivo:** revisar mais do que palavras isoladas.

**Estado:** concluída. A fila reúne vocabulário, erros gramaticais, listening, frases favoritas,
prompts de escrita e trechos de speaking, com filtros por tipo, competência e duração estimada.
Cada item explica sua origem e por que voltou. Erros e produções usam chaves de origem
idempotentes, portanto uma nova tentativa atualiza a revisão existente sem duplicá-la. O aluno
pode suspender, reativar ou excluir qualquer item. A migração expand/contract mantém
`review_card` como legado seguro e copia cada carta para `review_item` preservando ID e todo o
estado SM-2; a validação em produção local confirmou 523 de 523 cartas migradas e nenhuma
divergência de facilidade, intervalo, repetições, lapsos ou vencimento.

Frontend:

- fila única com vocabulário, erros, áudio, frases e prompts;
- filtros por duração e competência;
- prévia do motivo pelo qual o item voltou.

Backend/banco:

- `review_item` generalizado;
- migração do deck atual;
- agendamento por desempenho e tipo de atividade.

Aceite:

- todo histórico existente permanece válido;
- erros relevantes geram revisão sem duplicação;
- aluno pode suspender ou excluir um item.

### Sprint 13 - Qualidade, offline e instalação

**Objetivo:** permitir estudo confiável em celular e conexão instável.

**Estado:** concluída. A aplicação possui manifesto e service worker instaláveis, cacheia
somente o shell e o conteúdo textual público visitado e mantém áudio, dados privados e
gabaritos fora do cache. Tentativas sem rede entram em uma fila limitada, isolada por usuário,
e reutilizam a chave idempotente na sincronização. O perfil local mínimo permite abrir o
conteúdo já visitado sem persistir access token. O estado offline e a quantidade pendente são
anunciados visualmente e por região viva. O CI aplica orçamento de 170 KiB gzip para JS + CSS;
a medição da entrega foi 125,2 KiB. A auditoria WCAG e a política de telemetria estão em
`docs/auditoria_sprint13_qualidade_offline.md`.

- PWA instalável;
- cache do shell e conteúdo textual recente;
- fila local de tentativas com sincronização idempotente;
- estado offline explícito;
- auditoria WCAG e orçamento de performance;
- telemetria técnica sem texto, áudio ou dado sensível.

Áudio externo só deve ficar offline quando licença, origem e armazenamento permitirem.

### Sprint 14 - Transcrição e correção assistidas, opcionais

**Objetivo:** experimentar IA sem tornar o produto dependente dela.

**Estado:** concluída no piloto, com liberação ampla bloqueada. A transcrição assíncrona mostra
confiança por palavra e compara o texto reconhecido com a frase esperada sem chamar isso de nota
de pronúncia. A escrita mantém a rubrica determinística e oferece análise aberta apenas por
opt-in. Ambos os fluxos identificam automação e baixa confiança, registram avaliação humana,
cota e custo, possuem retenção configurável e preservam a produção quando o gateway falha. As
features ficam desligadas por padrão; critérios de liberação, privacidade, contrato do gateway e
a limitação da fila em processo estão em `docs/avaliacao_sprint14_assistencia.md`.

- speech-to-text assíncrono com confiança por palavra;
- comparação entre transcrição e frase esperada;
- feedback de texto aberto por rubrica;
- feature flags, cotas, métricas de custo e fallback;
- exclusão de dados e retenção configurável;
- avaliação humana de qualidade antes de liberar amplamente.

Aceite:

- usuário sabe quando o feedback foi automatizado;
- baixa confiança é visível;
- falha do provedor não perde a produção nem impede a aula.

## 11. Priorização

### Fazer primeiro

- auditoria das lições e correção da Aula 32;
- workspace guiado;
- player com transcrição;
- listening determinístico;
- feedback explicado;
- gravação e autoavaliação sem IA;
- editor e histórico de escrita.

### Fazer depois

- avaliar o speech-to-text e o feedback textual com usuários antes da liberação ampla;
- mover jobs assistidos para uma fila durável;
- alinhamento fonético;
- recomendações adaptativas mais sofisticadas;
- modo offline de mídia.

### Não fazer agora

- chat aberto genérico como tutor principal;
- ranking social;
- nota única de “fluência”;
- armazenar áudio no PostgreSQL;
- importar o Google Docs diretamente para o seed;
- copiar vídeos, áudios ou letras sem confirmar condições de uso.

## 12. Testes e qualidade

### Frontend

- Vitest e Testing Library para todos os estados de atividade;
- testes de teclado, foco e anúncios de feedback;
- `axe` automatizado nas páginas principais do E2E;
- testes do player com relógio e mídia simulados;
- testes de autosave e retomada;
- Storybook é opcional; adotar apenas se o catálogo de componentes justificar.

### Backend e banco

- testes unitários de correção e agendamento;
- integração real com PostgreSQL;
- migrations com upgrade, downgrade e preservação de dados;
- contrato OpenAPI e tipos do frontend sempre sincronizados;
- idempotência de tentativas e uploads;
- testes de autorização entre usuários.

### E2E

Fluxos mínimos:

1. iniciar e retomar aula;
2. ouvir trecho e responder listening;
3. errar, usar dica, corrigir e gerar revisão;
4. gravar, ouvir e excluir áudio com dispositivo falso do Playwright;
5. escrever, salvar, revisar e comparar versões;
6. concluir sessão e visualizar progresso;
7. operar em tela móvel e por teclado.

Arquivos de áudio de teste devem ser pequenos, próprios e livres para uso; não incluir grandes mídias da VOA no Git.

## 13. Métricas de produto

Métricas úteis, sem transformar estudo em competição:

- sessões iniciadas e concluídas;
- retorno após 1, 7 e 30 dias;
- tempo ativo por competência;
- acerto na primeira tentativa;
- melhora entre primeira e última tentativa;
- taxa de uso de dicas e gabarito;
- retenção das cartas após 7 e 30 dias;
- número de regravações antes de salvar;
- quantidade de textos revisados;
- erros recorrentes que diminuíram.

Não enviar conteúdo de texto, transcrição ou áudio para analytics. Métricas pedagógicas detalhadas ficam na conta do usuário e precisam de política clara de retenção.

## 14. Riscos e decisões

| Risco | Mitigação |
|---|---|
| links ou mídia da VOA mudarem | guardar fonte, metadados e fallback para abrir a origem |
| conteúdo pessoal conter erro | workflow editorial e separação entre nota e conteúdo publicado |
| correção automática ensinar algo errado | regras primeiro, confiança visível e revisão humana |
| “score de pronúncia” enganoso | separar STT, autoavaliação e avaliação fonética |
| áudio consumir armazenamento | limites, compressão, retenção e exclusão pelo usuário |
| permissões de microfone falharem | diagnóstico, instrução e alternativa sem gravação |
| roadmap ficar complexo demais | entregas verticais começando por duas aulas |
| perda de dados nas migrations | testes de preservação e backups antes de migrar |
| material externo ter restrições | atribuição, link/embeds preferenciais e auditoria de licença |

## 15. Definição de pronto

Uma funcionalidade pedagógica só está pronta quando:

- objetivo de aprendizagem e comportamento esperado estão documentados;
- conteúdo foi revisado;
- frontend cobre carregamento, vazio, erro, offline e sucesso;
- teclado, leitor de tela e mobile foram verificados;
- API possui autorização, validação e contrato atualizado;
- migration aplica, reverte e preserva dados;
- testes unitários, integração e E2E relevantes passam;
- métricas não coletam conteúdo sensível;
- README e documentação de operação foram atualizados.

## 16. Fila de fechamento

As Sprints 6–14 estão encerradas no bloco das Aulas 31–40 e o Pull Request desse ciclo já foi
mesclado. A ordem abaixo é o backlog canônico para fechar as expansões restantes; um item só
avança para concluído quando produzir a evidência indicada.

1. **Em andamento — validação manual de acessibilidade.** Zoom de 200% e percurso por teclado
   estão aprovados. O contraste forçado passou por emulação e ainda requer confirmação visual
   em Windows real. Faltam VoiceOver no macOS/iOS e TalkBack no Android. A matriz fica em
   `docs/validacao_manual_acessibilidade_2026-10-08.md`.
2. **Pendente — aprofundamento pedagógico das Aulas 32–40.** Adicionar transcrições integrais,
   mais atividades de listening por aula, propostas de escrita e ampliar ditado, ordenação,
   transformação, speaking e shadowing.
3. **Pendente e opcional — assistência por IA.** Contratar/configurar gateways de transcrição
   e escrita, validar privacidade e executar o gate humano definido para a Sprint 14 antes de
   ligar as feature flags.
4. **Pendente antes de escalar a assistência — fila durável.** Persistir jobs, retomar após
   reinício, limitar tentativas e garantir idempotência no gateway.
5. **Pendente — acabamento operacional.** Definir licença e política para áudio offline,
   revisar a documentação ao fim de cada etapa e adotar Storybook somente se o catálogo de
   componentes justificar.
