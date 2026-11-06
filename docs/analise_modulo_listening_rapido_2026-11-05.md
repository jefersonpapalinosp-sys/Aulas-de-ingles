# Análise — módulo de prática rápida de listening

Data: **05/11/2026**. Base lida: `main`, commit `012e54a`. Registro do planejamento inicial.
Esta análise complementa o
[plano das Sprints 50–61](plano_sprints_50_58_auditoria_2026-11-04.md).
Na etapa de análise não houve implementação nem publicação. Posteriormente,
o catálogo externo da Sprint 59 foi implementado e validado localmente;
o [guia atual](listening_rapido.md) e as [evidências](execucao_sprint59_2026-11-05.md)
registram o contrato entregue. Piloto nativo, ativação e publicação seguem pendentes.

## Objetivo e decisão de produto

Oferecer prática curta por nível e assunto, acessível independentemente da jornada de
uma aula VOA. A primeira entrega reúne as atividades A2 do Test-English; a segunda
acrescenta exercícios completos dentro do aplicativo com conteúdo liberado para esse uso.

| Entrega | Experiência do aluno | Evidência de progresso |
|---|---|---|
| Catálogo externo — Sprint 59 | Escolhe um tema, abre o Test-English e faz a atividade na origem | Estado informado pelo aluno; sem nota importada |
| Piloto nativo — Sprint 60 | Ouve e responde no app, com correção e explicação | Tentativas corrigidas pelo backend e vinculadas à versão do conteúdo |
| Consolidação — Sprint 61 | Retoma sessão, consulta histórico e continua a prática | Histórico distingue estado externo e desempenho nativo |

Essa sequência permite acesso às lições solicitadas e entrega o fluxo nativo em um
incremento próprio. A2 é o nível informado pelo catálogo externo; não se assume equivalência
automática com o Level 2 da VOA. As 82 aulas e os checkpoints existentes mantêm seu currículo.

## Evidência consultada e limite da integração

O [catálogo A2](https://test-english.com/listening/a2/) apresentava 31 links na consulta.
Três atividades foram examinadas como amostra de estrutura: uma
[conversa em hotel](https://test-english.com/listening/a2/checking-into-a-hotel-a2-english-listening-test/)
com sete questões de escolha única; uma de
[orientação urbana](https://test-english.com/listening/a2/giving-directions-a2-english-listening-test/)
com cinco diálogos e identificação em mapa; e uma sobre
[atividades de lazer](https://test-english.com/listening/a2/what-are-your-hobbies-a2-listening-test/)
com seleção de duas alternativas por pessoa. A análise verificou páginas e instruções;
não ouviu os vídeos nem validou gabaritos, duração ou nível de cada uma das 31 atividades.

Os [termos publicados](https://test-english.com/terms-of-use/), consultados em 05/11/2026,
autorizam compartilhar links e reservam os materiais ao uso no próprio site, restringindo
cópia, download, impressão, enquadramento e republicação. Por isso, o catálogo inicial
usará URLs com descrições próprias e crédito. Não incluirá questões, respostas, mapas,
miniaturas ou transcrições copiadas, nem iframe, proxy ou espelhamento do Test-English.

Incorporar essas mesmas lições no app exige autorização específica que cubra cada tipo
de material e o uso pretendido. Nenhuma autorização foi localizada ou solicitada nesta
tarefa. Para o piloto nativo, planeja-se conteúdo próprio ou com licença compatível,
com conferência editorial por ativo. Criar atividades originais sobre temas semelhantes
não significa traduzir ou parafrasear as perguntas protegidas do site.

Não foi identificado um contrato de API para resultados nas páginas examinadas. O plano
não depende de importar notas, rastrear o aluno no site externo ou acessar sua conta nele.

## Jornada e escopo inicial

1. Menu “Listening rápido” leva a `/listening`, com busca por assunto, nível A2 e filtro
   por estado. Cards mostram tema, fonte e duração apenas quando ela tiver sido conferida.
2. Atividades externas mostram “Abrir no Test-English” e abrem nova aba. No retorno, a
   marcação de conclusão é manual e reversível, identificada como “Concluída por mim”.
3. Atividades nativas publicadas mostram “Praticar no app”. Sua rota `/listening/:slug`
   oferece orientação curta, áudio, perguntas, feedback e resumo. O alvo editorial é
   5–10 minutos com 3–7 perguntas; essa é uma meta nova, não uma duração medida da fonte.
4. Transcrição e outros apoios acessíveis podem ser abertos pelo aluno; uso de apoio ou
   revelação fica explícito no resultado. Repetir trechos não exige gravar a voz do aluno.
5. Histórico distingue origem, versão, conclusão declarada e resultado corrigido. A
   primeira resposta conta para o resultado inicial; novas tentativas preservam a anterior.

O primeiro lote nativo terá três atividades, uma de cada formato observado. A expansão
para A1/B1/B2, importação integral das 31 lições, certificados novos, recomendação por IA,
gravação/transcrição da voz do aluno e download de mídia ficam fora deste ciclo.

## Encaixe no código existente

| Área inspecionada | Reutilização e mudança necessária |
|---|---|
| `frontend/src/App.tsx` e `components/trail/TrailShortcuts.tsx` | Inserir atalho utilitário e rotas lazy; manter separação do mapa de cursos |
| `components/ExerciseCard.tsx` e `features/exercise/ExerciseInputs.tsx` | Reutilizar campos, foco e feedback; separar apresentação do envio, hoje ligado a exercícios de aula; acrescentar checkboxes para `multi_select` |
| `features/media/LessonAudioPlayer.tsx` e `AudioTranscripts.tsx` | Extrair núcleo neutro de player; manter wrapper VOA e trocar persistência/atribuição conforme a origem |
| `backend/app/db/models.py` e `services/practice.py` | `Exercise`, `LessonMedia` e `PracticeSession` dependem de `lesson_id`; catálogo externo e sessão independente precisam de entidades próprias |
| `backend/app/domain/answers.py` | Reaproveitar regras puras aplicáveis; lista de respostas aceitas significa alternativas equivalentes, não seleção simultânea de duas opções |
| `backend/app/services/personal_export.py` e `account_deletion.py` | Acrescentar estado e sessões do módulo aos fluxos de dados pessoais desde a primeira persistência |
| `frontend/src/features/offline/`, `frontend/public/sw.js` e `services/offline_policy.py` | Adaptar armazenamento/filas por conta e versão; revisar whitelist apenas para texto público do catálogo próprio |
| `frontend/security-headers.conf`, `ops/` e `e2e/` | Conferir origens de mídia, recuperação e testes reais de navegador; links externos não requerem liberar frames na CSP |

Embora exista um endpoint genérico para tentativa de exercício, seu registro continua
vinculado a uma aula. Usá-lo diretamente para recursos independentes exigiria alterar
invariantes de progresso, revisão e exportação. A recomendação é um módulo próprio,
reutilizando componentes e funções puras, com adapters para persistência e transporte.

## Modelo e contrato propostos

Desenho para refinar na Sprint 59, sem migration criada nesta análise:

- **Recurso:** slug/chave editorial imutável, título autoral, tema, nível, fonte/URL,
  modo `external_link` ou `native`, estado editorial, versão e datas de conferência.
  Licença, atribuição, autorização e política de mídia são obrigatórias quando houver
  ativo nativo. A mudança de modo cria identidade própria; não converte conclusão externa
  em nota de uma atividade nativa.
- **Estado do aluno:** chave única aluno/recurso, marcação externa, datas e revisão.
  O servidor deriva o aluno da sessão autenticada; propriedade é checada em cada operação.
- **Atividade nativa versionada:** mídia, transcrição opcional, questões, opções com IDs,
  explicações e gabarito privado. Publicação e arquivamento não apagam versões referidas
  por tentativas. Mapa deve ter descrição/alternativa adequada, com apoio registrado.
- **Sessão/tentativa:** aluno, versão da atividade, posição, respostas, revelações e resultado.
  IDs de operações e revisão impedem duplicação e sobrescrita entre abas/dispositivos.
  Usar FKs reais, índices por aluno/recurso/data e constraints; validar retenção e grants.

Contratos sugeridos, a formalizar no OpenAPI:

| Operação | Endpoint proposto | Regra principal |
|---|---|---|
| Buscar catálogo/detalhe | `GET /api/listening/resources` e `GET /api/listening/resources/{slug}` | Somente metadados e conteúdo publicados; sem gabarito ou estado pessoal no cache público |
| Consultar estado próprio | `GET /api/me/listening/progress` | Autenticado e não cacheável publicamente |
| Marcar atividade externa | `PUT /api/me/listening/progress/{resource_id}` | Revisão e idempotência; sem nota externa |
| Iniciar/retomar sessão nativa | `POST /api/listening/sessions` e `GET /api/listening/sessions/{id}` | Apenas recursos nativos e proprietário da sessão |
| Salvar posição/rascunho | `PATCH /api/listening/sessions/{id}` | Revisão de estado, versão da atividade e confirmação de persistência |
| Enviar resposta | `POST /api/listening/sessions/{id}/answers` | Correção no servidor, versão fixada e chave idempotente |
| Consultar histórico | `GET /api/me/listening/history` | Paginação estável, filtros e distinção entre fontes |

Para `multi_select`, o contrato transmite IDs de opções, valida quantidade e rejeita
duplicatas/IDs estranhos. O acerto exige igualdade do conjunto selecionado com o gabarito,
independentemente da ordem; selecionar só uma resposta correta não basta. O piloto não
atribui pontuação parcial. Todas as questões têm peso igual, e revelação não vira acerto
inicial. A regra será coberta no domínio, API, interface e fluxo integrado.
Escolha única também compara o ID da opção; mudanças de texto não alteram o significado
de uma resposta já registrada.

## Progresso, offline e operação

O módulo terá progresso próprio. Conclusão autodeclarada externa não alimenta SM-2,
domínio de habilidades, tempo ativo medido ou certificados VOA. O painel Hoje poderá
apenas oferecer um atalho para continuar a prática, mantendo essa distinção visível.

Na Sprint 59, alteração de status exige conexão e confirmação da API. Na 61, rascunhos
e comandos nativos podem aguardar envio no armazenamento local por aluno/versão, com
estado “Pendente de envio”. Sair ou trocar de conta pausa o envio; excluir a conta limpa
os dados correspondentes do servidor e do dispositivo. Expiração/mudança editorial não
reaplica silenciosamente respostas antigas a uma versão nova.

A exportação contém os dados do aluno, IDs, versões, URLs e resultados. Material de
terceiros só acompanha o arquivo exportado quando a licença permitir; o snapshot usado
internamente para correção também exige uso autorizado. Excluir uma conta remove seus
estados, respostas e sessões; não remove mídia curricular compartilhada por outros alunos.

O cache poderá conter metadados autorais publicados do catálogo. Mídia começa com
`network_only`, seguindo o comportamento atual do service worker. Histórico privado,
gabaritos e conteúdo do Test-English não entram em cache público. Queda da fonte externa
deve produzir aviso e preservar o estado; não bloquear a navegação do aplicativo.

Migrations são expansivas, ensaiadas em base descartável e seguem o rollout existente.
Backup/restore deve incluir as novas tabelas e qualquer mídia própria armazenada; mídia
externa é referenciada, não tratada como arquivo recuperável no backup. Publicação usa
flag desabilitada até o aceite; desativá-la preserva histórico e acesso à exportação/exclusão.

## Sprints, dependências e critérios de conclusão

| Sprint | Entrega | Condições |
|---|---|---|
| 59 · esforço M | Inventário dos 31 links, catálogo, estado manual, exportação/exclusão e primeiro E2E | Base estabilizada; decisões de privacidade (52), grants (56), PWA/bundle (57) e ambiente E2E (58) |
| 60 · esforço G | Três atividades nativas, player neutro, correção simples/múltipla e dados protegidos | 59; conteúdo próprio/licenciado disponível e revisado |
| 61 · esforço M–G | Retomada, histórico, fila, homologação e publicação | 59–60; API/versões estáveis; build, recuperação e E2E aprovados |

A sequência preserva as prioridades de segurança/operação 50–58 e o cutover de 13/11
já registrado. Não há nova data de entrega assumida. Se a liberação editorial atrasar,
o catálogo externo é uma entrega utilizável; o piloto nativo permanece pendente.

Validar, no mínimo: inventário sem duplicatas; links indisponíveis; estado manual sem
conclusão automática; propriedade e exportação/exclusão; multi-select em qualquer ordem;
gabarito oculto; conteúdo revisto/arquivado; reenvio idempotente; dois usuários e duas abas;
offline/reconexão; indisponibilidade de áudio; teclado, foco, leitor de tela e mobile;
restauração; regressão do player VOA e orçamento de bundle após FE-08.

Usar fixtures locais próprias nos testes automatizados e executar Playwright na stack
isolada Linux/WSL, sem depender da disponibilidade do Test-English ou de vídeos de terceiros.
Homologação humana de áudio, acessibilidade e nível pedagógico complementa a suíte.
Esta tarefa validou o planejamento por leitura de código/documentação; não executou testes
da aplicação nem confirmou o estado atual do ambiente público.
