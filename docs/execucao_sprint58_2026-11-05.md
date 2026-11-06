# Sprint 58 — Qualidade, portabilidade e acabamento

Código e aceite integrado local concluídos. Implementação iniciada em 05/11/2026.
A próxima prioridade é a Sprint 59: catálogo A2
de listening rápido com links externos e progresso autodeclarado.

## Correções

- **BE-08/09:** a criação de sessões de prática adquire o lock da conta antes
  de procurar a chave idempotente e a sessão ativa. IDs usados após rollback
  são capturados antes dele. Requisições simultâneas com a mesma chave em
  aulas diferentes produzem uma criação e um conflito. A listagem legada
  de revisões desempata `created_at` pelo ID, como a listagem paginada.
- **BE-07:** preservado o algoritmo `sm2-multimodal-v1`: o fator do tipo de
  carta é aplicado a cada revisão, sobre o intervalo anterior. O teste de
  carta gramatical agora verifica quatro revisões: 1, 5, 10 e 20 dias.
  Não houve mudança silenciosa do histórico nem migration do agendamento.
- **QA-02:** a auditoria lê cada áudio duas vezes e exige hashes iguais,
  além de conferir identidade e metadados. O orçamento desconta ambas as
  leituras. O teste regrava bytes diferentes do mesmo tamanho e simula
  metadados inalterados; o arquivo fica protegido, sem remoção.
- Cotas convertem instantes conscientes de fuso para UTC e recusam datas sem
  fuso. Aspas tipográficas de ambos os lados são normalizadas; o apóstrofo
  continua distinguindo `we'll` de `well`.
- Transcrição desativada por configuração/piloto responde **409** com
  `assist_disabled`, seguindo o contrato de diálogo. **503** continua
  reservado a indisponibilidade transitória. A interface explica a desativação
  e preserva a gravação.
- **QA-05:** JWT aceita até 30 segundos de `iat`/`nbf` futuro. A expiração
  permanece estrita, assim como o encerramento da chave anterior. Testes
  cobrem o limite, token expirado e relógio controlado. Revisão usa um instante
  fixo por cenário; a limpeza de conta é testada exatamente no horário
  agendado no banco.

## Interface, PWA e portabilidade

- **FE-09 a FE-12:** rolagem por JavaScript respeita movimento reduzido;
  rótulos de 10 px passam a 12 px; carregamento identifica a sessão ou a rota.
  Ícones PNG de 180, 192 e 512 px foram rasterizados do SVG existente.
  Manifesto e Apple touch icon apontam para os formatos adequados.
  Para regenerá-los após editar o SVG: `npm run icons --prefix e2e`, com
  dependências E2E e Chromium instalados.
- Os ícones entram no hash da release e no cache de arquivos estáticos.
  O cache da página offline mantém seu limite, sem disputar espaço com os
  novos ícones. A regressão de atualização inclui instalação interrompida.
- Logout também aparece na gaveta de navegação do celular.
- **FE-07, INF-10, OPS-14:** LF declarado em `.gitattributes`; mypy analisa a
  plataforma Linux explicitamente; atalhos locais usam o Python do projeto;
  `curl` não depende de `/dev/stdout`. A temporização de arquivos operacionais
  já usa `tempfile`/`mktemp`, sem acrescentar caminhos globais fixos.
- **QA-01:** E2E completo requer Linux/WSL ou macOS com Docker local por socket
  Unix. Windows nativo não é apresentado como suportado para esse laboratório.
  A causa da guarda aparece sem `actual`, `expected`, stack ou stderr que
  possam expor valores do ambiente recusado. Os limites de alvo e volume foram
  mantidos. `infra/Dockerfile.e2e-runner` fixa a imagem Playwright 1.63.0 usada
  no ensaio Linux com Docker Desktop.
- **QA-04:** `tzdata` integra o grupo dev no Windows. Testes de descritores,
  links, permissões e fsync POSIX declaram a restrição de plataforma; quarentena
  não importa `fcntl` durante coleta no Windows. Integração completa de API,
  áudio e operação continua sendo validada no Linux.

## Qualidade e automação

- **QA-03:** chamadas HTTP de preparação antes descartadas agora usam
  `assert_status`, com falha próxima da origem. O diagnóstico inclui método,
  caminho e status, sem corpo, cookies ou query. O cenário de login inválido
  declara seu 401 esperado.
- **QA-06/07:** o comando Node portável do harness de fila já estava corrigido.
  Upload lento usa cancelamento no próximo yield; o teste de aba oculta usa
  relógio do navegador e espera as respostas efetivamente enviadas. O primeiro
  crédito de estudo continua sendo medido contra o servidor real.
- **QA-08/cobertura:** testes de exclusão e transcrição atravessam o transporte
  real até `fetch`. Mocks unitários de estados de tela permanecem; App/estudo,
  renovação, logout e exclusão também têm jornadas contra a API real no E2E.
  V8 mede todo `src`, exceto testes, declarações, setup e bootstrap. O CI exige
  80% de statements, 74% de branches, 78% de funções e 85% de linhas.
- **QA-09/10:** IDs curtos substituem parâmetros de respostas de 1 MB e de
  áudio binário; a coleta não imprime esses payloads como nomes de teste. Chamadas positivas
  a validadores sem retorno são testes de aceitação por ausência de exceção,
  complementados pelos cenários negativos; não foram adicionadas asserções
  artificiais `None == None`. As jornadas do arquivo de quase 2.800 linhas
  foram divididas em nove specs por área, com helpers compartilhados. A
  execução permanece com um worker, respeitando o banco compartilhado.
- **QA-12:** um job independente do CI executa os seis benchmarks sintéticos
  de 1k/10k, preserva relatórios JSON por 14 dias e encerra sua base exclusiva.
  Falhas de execução bloqueiam o job; tempos medidos não representam capacidade
  de produção. Os testes operacionais novos cobrem inventário de rollout,
  nomes de tabelas, provas de rotação e destino fixo da conexão.

## Evidências locais

- Backend Linux: **1.489 testes passaram em cada uma de três execuções
  completas consecutivas**, com **94,05% de cobertura** nas três (piso: 90%).
  Durações: 918,20 s, 774,57 s e 746,72 s. Os ajustes finais de coleta para
  Windows em quarentena/inspeção também passaram no Linux: **63 testes**.
- Frontend: **485 testes**, cobertura de linhas **85,73%**; statements 80,25%,
  branches 74,31%, funções 78,21%. ESLint e TypeScript aprovados.
- Bundle: entrada **129,9/132 KiB gzip**, base **183,6/184 KiB**, conjunto com
  diálogo **190,6/192 KiB**. Limites preservados.
- **66 guardas E2E**, **14 testes de scripts no Linux**, **2 testes PWA**.
- E2E completo no Linux: **162 testes passaram em 13,6 minutos**, com dois
  skips declarados da medição de desempenho em Firefox/WebKit; essa medição
  roda somente no Chromium. As jornadas incluem desktop e celular, além de
  acessibilidade em Firefox e WebKit. Os 44 blocos originais foram preservados
  na divisão das specs, conferidos após normalização de finais de linha.
- Operação: **384 testes no Linux, 8 skips declarados**; cinco testes novos
  de rollout/rotation também passaram no Windows. A suíte operacional completa
  usa recursos POSIX e não é declarada compatível com Windows nativo.
- Windows: **28 testes portáveis passaram, 52 POSIX foram pulados** no recorte
  de respostas, upload, auditoria e quarentena. Ambiente temporário com lock e
  `tzdata` instalado, separado do ambiente original.
- A coleta completa dos **1.489 testes** também foi validada no Windows;
  isso não equivale à execução integral nativa dos cenários POSIX.
- Ruff, mypy da aplicação e actionlint aprovados. Migrations até o head,
  `alembic check` e seed aprovados no banco sintético Linux.
- Seis benchmarks executados em base independente dos testes, com relatórios
  em [docs/evidencias/sprint58](evidencias/sprint58/). O cenário de
  diálogo informou `p95_pass=true`. A medição local utilizou um núcleo da VM;
  não é uma homologação de carga da infraestrutura pública.

O ensaio detectou retrocesso de aproximadamente 25 segundos no relógio da VM.
Os testes temporais citados acima foram estabilizados sem ampliar validade de
sessões ou retirar asserções. Rodadas preliminares interrompidas e falhas
diagnósticas não contam como aceite. API/DB de pytest foram fixados no mesmo
núcleo do laboratório; API, worker e DB do E2E também compartilham um núcleo,
distinto do pytest. E2E, benchmarks e pytest usam bancos sintéticos distintos.
As 53 dependências instaladas no Linux correspondem ao lock; `colorama` e
`tzdata` são condicionais ao Windows. Os contêineres E2E foram encerrados ao
final, preservando seus volumes. Nenhum relógio do host foi alterado.

## Reproduzir

Linux/WSL, na raiz do repositório:

```sh
uv sync --project backend --group dev --locked
make test-api-prepare
for run in 1 2 3; do
  test_tmp=$(mktemp -d) || exit 1
  (cd backend && uv run pytest -q --basetemp "$test_tmp" --cov=app --cov-report=term --cov-fail-under=90) || exit 1
done
make e2e-up
npm ci --prefix e2e
(cd e2e && npx playwright install --with-deps)
make test-e2e
make e2e-down
```

No Windows, o recorte portável pode usar `uv run python -m pytest
tests/test_answers.py tests/test_audio_upload.py` a partir de `backend`,
com `--basetemp` apontando para um diretório
temporário exclusivo e gravável. Não reutilizar uma pasta com arquivos pessoais:
o pytest gerencia e limpa esse diretório. E2E e testes POSIX rodam no WSL/Linux.

No frontend: `npm ci`, `npm run test:coverage`, `npm run build` e
`npm run check:budget`. No PowerShell, usar `npm.cmd` caso a política de scripts
impeça executar `npm.ps1`.

Nenhum deploy, migration de ambiente de estudo, commit ou push faz parte deste
ensaio. Os aceites operacionais das sprints anteriores continuam separados.
