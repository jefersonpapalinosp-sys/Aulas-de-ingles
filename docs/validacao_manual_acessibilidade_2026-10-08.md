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

Legenda: `PENDENTE`, `APROVADO`, `REPROVADO` ou `NÃO APLICÁVEL`.

## Matriz obrigatória

| Ambiente | Verificação | Rotas mínimas | Estado | Evidência/observação |
|---|---|---|---|---|
| macOS + VoiceOver | ordem de leitura, títulos, landmarks, nomes e estados anunciados | `/`, `/aulas/31`, `/aulas/40/estudar/assistir`, `/revisao`, `/caderno` | PENDENTE | — |
| iOS + VoiceOver | gestos, foco, player, formulário e retorno de erro | `/`, `/aulas/40/estudar/assistir`, `/revisao` | PENDENTE | — |
| Android + TalkBack | gestos, foco, player, formulário e retorno de erro | `/`, `/aulas/40/estudar/assistir`, `/revisao` | PENDENTE | — |
| Desktop, teclado | fluxo completo com Tab, Shift+Tab, Enter, Espaço e Escape | login, jornada, exercício, revisão e caderno | PENDENTE | — |
| Desktop, zoom 200% | reflow sem rolagem horizontal na largura equivalente a 1280 px | `/`, aula, jornada, revisão e caderno | PENDENTE | — |
| Windows, contraste forçado | texto, foco, bordas, botões, links e estados continuam distinguíveis | `/`, aula, jornada, revisão e caderno | PENDENTE | — |

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
