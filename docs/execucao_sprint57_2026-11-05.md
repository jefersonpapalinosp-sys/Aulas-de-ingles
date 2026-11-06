# Sprint 57 — PWA e offline

Implementação e validações locais em 05/11/2026. Próxima prioridade:
**Sprint 58 — qualidade, portabilidade e acabamento**. Listening rápido
continua planejado nas Sprints 59–61, após o ciclo de estabilização.

## Entregas

- **FE-03:** falhas 5xx são contadas por resposta no IndexedDB. Após três,
  o item fica pausado e a rodada pode seguir. O aluno pode usar **Pular por
  enquanto** após uma falha e **Retomar envio** para tentar novamente com
  o texto e a chave idempotente originais. A pausa sobrevive à recarga e
  aparece em outra aba; respostas pausadas não entram no descarte de
  incompatíveis e continuam impedindo tentativa duplicada ao retomar a sessão.
  Rede, autenticação, limite de solicitações e atualização
  obrigatória continuam interrompendo a rodada.
- **FE-04:** Hoje permite escolher uma aula pelo mapa offline; o mapa com
  currículo disponível continua navegável quando o progresso privado falha.
  Sem confirmação, não transforma ausência de dados em zero progresso,
  “pendente” ou “concluído”. Recomendações/metas não são apresentadas como
  atuais offline. Nenhum cache persistente de dados privados foi criado;
  texto público já visitado continua sujeito à política existente do SW.
- **FE-05:** posições intermediárias ainda não enviadas pela mesma instância
  do player são combinadas na mais recente. Conclusão, comandos de outra aba
  e operações despachadas ficam separados. Web Locks usa bloqueios distintos
  para envio e escrita curta: uma requisição lenta não impede salvar localmente.
  A marca de despacho é persistida antes da rede; resposta perdida não permite
  alterar o payload enviado. Sem Web Locks, preserva a fila sem combinar.
  A substituição grava a posição nova antes de remover a anterior; falha de
  armazenamento é informada e a cópia anterior é preservada.
- **FE-06:** exportação do Caderno anexa o link ao documento e adia a liberação
  do blob por 60 segundos. Remove o link e agenda a liberação também se o
  clique falhar; o download não depende da permanência na página.
- **FE-08:** escrita, áudio, aulas e ferramentas pessoais compartilham o
  pacote `study`, carregado sob demanda. Elimina o ciclo anterior entre
  `lesson-study` e `writing`, sem aumentar limites. Login/Hoje não antecipam
  o pacote de estudo e diálogo continua separado. Tradeoff: abrir a primeira
  aula ou ferramenta pessoal carrega o pacote conjunto de cerca de 52,8 KiB
  gzip; as próximas telas reutilizam o mesmo arquivo.
- **FE-01:** fluxo de atualização já antecipado foi preservado e revalidado
  em duas abas, inclusive falha de instalação e retenção da versão anterior.

O [guia do aluno](guia_do_aluno_retomada_offline_privacidade.md) foi atualizado.

## Verificação

- **480/480 testes do frontend**, em 55 arquivos. Incluem perda de resposta,
  gravação durante envio lento, falha de storage, isolamento entre contas,
  pausa/retomada, recarga e indicação correta de progresso desconhecido.
- **13/13 testes Chromium do harness de fila**, incluindo os dois novos da
  Sprint 57; **2/2 testes PWA**. Os casos novos foram reexecutados após a
  revisão final do áudio. Servidores em loopback, API sintética e nenhuma
  ligação com banco ou conta real.
- TypeScript, ESLint e sincronização `check:api` aprovados.
- Smoke do bundle de produção em Chromium: login renderizado e os quatro
  módulos JavaScript carregados sem erro de execução, com API sintética local.
- **14/14 testes dos scripts** aprovados em Node/Linux descartável, sem rede.
  Os scripts de shell usaram LF, como no build de produção. A execução nativa
  Windows expôs a limitação já conhecida dos caminhos POSIX desses testes.
- Build Vite e orçamento aprovados, sem aviso de chunks circulares:
  inicial **129,9/132 KiB**, base **183,5/184 KiB**, diálogo **7,0/8 KiB**,
  conjunto **190,4/192 KiB**, todos em gzip. A margem da base ainda é pequena;
  novas funcionalidades precisam continuar passando pelo gate.
- Corrigida uma comparação de caminho no teste de invalidação de queries:
  `join('api', 'invalidateStudy.ts')` permite executar o mesmo contrato no
  Windows e Linux. Não houve alteração do comportamento de invalidação.

## Limites

Sem commit, push, deploy, migration ou alteração de dados de estudo/produção.
Backend não mudou; sua suíte não foi repetida. A pipeline remota e o E2E
completo com backend real continuam pendentes para a Sprint 58.

Offline depende de conteúdo público previamente consultado e ainda presente
no cache. Áudios externos não passam a estar disponíveis offline. A validação
de navegador desta sprint usa Chromium; homologação pública e outros motores
continuam pendentes. Atualizar o aplicativo antes de usar os controles novos.
