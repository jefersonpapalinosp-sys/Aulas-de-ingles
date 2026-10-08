# Validação manual de acessibilidade — Sprint 15

Data de abertura: 8 de outubro de 2026

## Objetivo

Validar manualmente os fluxos principais das Aulas 31–40 além da cobertura automatizada de
WCAG, desktop e mobile. Esta rodada é o primeiro item da fila de fechamento do projeto.

## Estado

**Em andamento.** A suíte automatizada, incluindo axe, teclado, desktop e emulação móvel,
passou no Pull Request #7. A execução manual abaixo ainda requer uma sessão interativa de
navegador e os leitores de tela dos sistemas-alvo. Nenhum item manual deve ser marcado como
aprovado apenas com base nos testes automatizados.

Legenda: `PENDENTE`, `EM RETESTE`, `INCONCLUSIVO`, `APROVADO`, `REPROVADO` ou
`NÃO APLICÁVEL`.

## Matriz obrigatória

| Ambiente | Verificação | Rotas mínimas | Estado | Evidência/observação |
|---|---|---|---|---|
| macOS + VoiceOver | ordem de leitura, títulos, landmarks, nomes e estados anunciados | `/`, `/aulas/31`, `/aulas/40/estudar/assistir`, `/revisao`, `/caderno` | PENDENTE | — |
| iOS + VoiceOver | gestos, foco, player, formulário e retorno de erro | `/`, `/aulas/40/estudar/assistir`, `/revisao` | PENDENTE | — |
| Android + TalkBack | gestos, foco, player, formulário e retorno de erro | `/`, `/aulas/40/estudar/assistir`, `/revisao` | PENDENTE | — |
| Desktop, teclado | fluxo completo com Tab, Shift+Tab, Enter, Espaço e Escape | login, jornada, exercício, revisão e caderno | INCONCLUSIVO | A primeira execução não conseguiu confirmar eventos reais de Tab/Enter. |
| Desktop, zoom 200% | reflow sem rolagem horizontal na largura equivalente a 1280 px | `/`, aula, jornada, revisão e caderno | EM RETESTE | Login aprovado. O segundo teste confirmou o campo Nome, mas encontrou o topo do cadastro em `-135px`; a nova correção aguarda confirmação manual. |
| Windows, contraste forçado | texto, foco, bordas, botões, links e estados continuam distinguíveis | `/`, aula, jornada, revisão e caderno | PENDENTE | — |

## Resultado da primeira execução

- a tela de login não apresentou rolagem horizontal no equivalente a 200% de zoom;
- campos e botões do login usam elementos nativos e possuem ordem lógica no documento;
- o campo **Nome** do cadastro crescia para aproximadamente 220 px de altura porque herdava
  `flex-basis: 220px` da regra geral dos exercícios;
- quando o cadastro ficava mais alto que o viewport, a centralização vertical cortava o topo e
  impedia alcançá-lo;
- a automação usada nessa execução não confirmou eventos reais de Tab/Enter, portanto o teste
  de teclado permanece inconclusivo;
- nenhuma solicitação de acesso ao site local foi apresentada.

Correção aplicada: o formulário de autenticação agora neutraliza o `flex-basis` geral dos
inputs, ocupa a largura disponível e mantém o cartão ancorado no topo com espaçamento seguro.
Ao trocar para o cadastro, o foco segue para o novo campo Nome em vez de permanecer no botão
inferior. Em viewports baixos, todo o início do formulário permanece alcançável. Um teste
E2E cobre altura do campo Nome, posição do cartão e ausência de overflow horizontal em viewport
de 640 × 360, equivalente ao reflow esperado em 200% sobre 1280 × 720.

## Resultado da segunda execução

- login aprovado em equivalente a 200%, sem rolagem horizontal e com todos os controles
  alcançáveis por rolagem vertical;
- cadastro reprovado porque o topo do cartão ficou em `-135px`, cortando o título e parte da
  introdução;
- o campo Nome permaneceu com altura normal; a altura de aproximadamente 220 px não voltou a
  ocorrer;
- campos e botões são nativos, possuem nomes acessíveis e participam da ordem de foco;
- o percurso efetivo com Tab, Enter e Espaço continuou inconclusivo por limitação do
  controlador utilizado;
- a aba terminou limpa, no tamanho normal e na tela inicial.

A causa remanescente era a rolagem automática de `focus()` ao mover o foco para Nome. A segunda
correção usa `focus({ preventScroll: true })` e posiciona a janela no topo. A regressão E2E agora
exige `scrollY === 0` sem corrigir a rolagem dentro do próprio teste.

## Critérios de aprovação

- o link “Pular para o conteúdo” é o primeiro foco útil;
- nenhum controle recebe foco invisível ou fica inacessível pelo teclado;
- títulos, regiões, rótulos, erros, progresso e estados de sincronização são anunciados;
- a ordem do foco acompanha a ordem visual e não prende o usuário;
- player, velocidade, saltos e repetição A–B possuem nome e estado compreensíveis;
- exercícios não dependem exclusivamente de cor, gesto de arrastar, áudio ou visão;
- em 200% de zoom não há perda de conteúdo nem rolagem horizontal bidimensional;
- no contraste forçado, foco, seleção, erro e ação principal permanecem distinguíveis;
- qualquer falha encontrada recebe rota, passos, resultado esperado, resultado obtido e
  severidade antes da correção.

## Encerramento

Esta etapa só pode ser marcada como concluída quando todas as linhas obrigatórias estiverem
aprovadas ou possuírem uma justificativa explícita de `NÃO APLICÁVEL`, e toda falha crítica ou
séria tiver sido corrigida e retestada.
