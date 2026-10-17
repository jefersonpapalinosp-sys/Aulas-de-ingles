# Sprint 43 — implantação segura no ambiente de estudo

Atualização: 16 de outubro de 2026. Esta sprint promove o fechamento técnico das
Sprints 40–42 para o ambiente local de estudo, sem transformar homologações
humanas ou HTTPS público em aceites automáticos.

## Objetivo e resultado

O ambiente de estudo em `http://localhost:5181` foi atualizado do schema
`a39d7bc02486` para `a42c7d1e9f20`, usando o commit
`c3ee3cc2e5386b734773d26fafd7e4cf2f0ada03` da `main`. Banco e volume de voz
foram preservados. API, worker, frontend/PWA e o gate operacional voltaram ao ar
com resultado aprovado.

Estado da Sprint 43: **implantação técnica concluída**. O pacote maior continua
sem aceite humano integral enquanto permanecerem abertas as validações listadas
em [Pendências que continuam abertas](#pendências-que-continuam-abertas).

## Condições da mudança

- ambiente autorizado pelo responsável como ambiente de estudo com dados de teste;
- manutenção temporária autorizada, com backup anterior à migration;
- banco mantido no volume original; não houve restore sobre a origem;
- ensaio executado a partir do backup real em banco e volume de voz novos,
  internos e sem portas publicadas;
- migration aplicada somente com `aulas_migrator`; API e worker usam seus papéis
  limitados;
- segredos, dumps, áudio e conteúdo pessoal não foram incluídos no Git nem nos
  relatórios.

## Evidência da implantação

### 1. Candidata e estado inicial

- worktree limpa e sincronizada com `origin/main` antes da operação;
- head Alembic embarcado: `a42c7d1e9f20`;
- estudo antes da manutenção: `a39d7bc02486`, API saudável;
- imagens de API, worker, migrador e web construídas antes da manutenção;
- PR 24 e CI do commit candidato aprovados em backend, frontend, recovery,
  segurança e E2E.

### 2. Backup e ensaio isolado

O pacote anterior à mudança foi publicado e verificado sob o identificador
`aulas-20261016T195455844134Z-43bcd1cccd804c43b3f3631e2ba0fe10`.
Ele foi restaurado no alvo descartável `aulas-ingles-recovery/study-check-db`.
O restore conferiu snapshot do banco, inventário e checksums do volume de voz.

No clone foram executadas as 12 migrations entre `a39d7bc02486` e
`a42c7d1e9f20`, seguidas de:

- segunda execução idempotente de `alembic upgrade head`;
- `alembic check` sem operação pendente;
- prévia insert-only do seed com zero criações, alterações, omissões e bloqueios;
- preservação explícita de três metadados editoriais históricos;
- readiness e catálogo da aplicação candidata com HTTP 200;
- todas as contagens pessoais monitoradas e referências de voz idênticas;
- zero chaves editoriais ausentes, vínculos de listening não resolvidos,
  constraints inválidas e locks aguardando;
- tabelas novas de snapshot, auditoria e exclusão sem recibos inventados.

O primeiro comando de prévia do seed foi recusado porque o entrypoint tentou criar
`/app/data` num container deliberadamente read-only. A execução foi repetida com
o entrypoint Python explícito. Isso não foi falha de migration ou de dados e não
alterou a origem.

### 3. Aplicação no estudo

A mesma cadeia foi aplicada pelo papel migrador com web, API e worker parados.
A segunda execução foi vazia, o drift continuou zerado e a prévia editorial
repetiu o resultado aprovado do clone. Antes de religar os serviços foram
confirmados:

- schema atual e requerido iguais a `a42c7d1e9f20`;
- contagens e referências de voz iguais ao backup anterior;
- zero chaves editoriais ausentes e zero vínculos não resolvidos;
- zero constraints inválidas e zero locks aguardando.

API e worker foram iniciados antes da web. O readiness retornou banco disponível
e schema compatível. O gate operacional aprovou nove sinais: readiness, taxa de
5xx, idade da fila, heartbeat do worker, manutenção, locks, exclusões de conta,
reconciliação de `review_card` e espaço do volume de voz.

Imagens implantadas:

| Serviço | ID imutável da imagem |
|---|---|
| API | `sha256:235d643f292a0fa19615dcabff71f6320a1141390f06f0b61a6165b62aa183ab` |
| worker | `sha256:d37fd7e1e32b4dca250f5a1108d26fadd69d4c215e0e120068b037c79beb14fe` |
| web | `sha256:544e1b9bf5d883ded4e954db516ab78a94c1768df9dd94c75aac0dfb669cef70` |

### 4. Liberação e backup posterior

Depois dos gates, `/`, `/inicio`, `/sw.js`, `/api/health` e `/api/courses`
responderam HTTP 200 por `localhost:5181`. A página estática apresentou CSP,
`nosniff`, política de referência, política de permissões e COOP.

O backup pós-migration foi publicado e verificado sob o identificador
`aulas-20261016T200025682120Z-bbd9ecf94b4f4304983f76043728d582`.
Após a captura, os mesmos containers foram reabertos; readiness, gate operacional
e os cinco smokes HTTP passaram novamente.

A janela observada entre a publicação do primeiro pacote e a validação final foi
inferior a sete minutos. Isso comprova o procedimento desta implantação planejada
e fica abaixo da meta de 60 minutos, mas não inclui detecção e decisão de um
desastre não planejado; portanto não é apresentado como SLA de recuperação.

## Pendências que continuam abertas

| Item | Estado honesto | Próxima evidência necessária |
|---|---|---|
| RPO de 24 h | pendente | comprovar a execução diária ao longo da janela acordada, não apenas dois pacotes no mesmo release |
| RTO de desastre | parcial | ensaio cronometrado que inclua detecção, decisão, restauração, troca e liberação |
| token operacional | ativo apenas no container atual | persistir um valor privado de 32+ bytes na configuração local antes da próxima recriação da API |
| HTTPS público | pendente | domínio/proxy/certificado reais, cookie seguro e HSTS no perfil público |
| listening | homologação humana pendente | ouvir e decidir os 408 cues inventariados, registrando revisor e data |
| escrita | homologação humana pendente | professor/Jeferson revisar os 82 exemplos |
| acessibilidade | homologação física pendente | VoiceOver macOS/iOS, TalkBack Android, contraste forçado Windows e navegação virtual |
| performance percebida | pendente | executar e registrar as quatro rotas com listas representativas e rede lenta em navegador real |

## Regra de continuidade

Uma futura implantação deve repetir backup anterior, restore isolado, ensaio com a
mesma imagem, migration pelo papel correto, gates antes da web e backup posterior.
O clone e os pacotes desta execução são evidência privada local; não devem ser
commitados. Nenhuma pendência humana acima pode ser encerrada apenas por axe,
emulação, teste unitário ou sucesso do deploy.

## Preparação do deploy público no EasyPanel

Foi criada uma trilha separada para publicar a aplicação sem misturar os dados e
segredos do estudo local:

- Compose sem nomes fixos ou portas do host;
- PostgreSQL 16 persistente com papéis separados de administração, migration,
  runtime, worker e backup;
- migrations, conferência de drift, seed e grants como gates anteriores à API;
- nginx preservando o `X-Forwarded-Proto=https` recebido do Traefik, com HSTS
  somente no perfil HTTPS;
- gerador de segredos independentes e verificador de origem/Compose que não
  imprime credenciais;
- assistência remota desligada no primeiro deploy;
- runbook de domínio, TLS, aceite, backup e rollback em
  [deploy_easypanel.md](deploy_easypanel.md).

A consulta ao painel confirmou capacidade de CPU, RAM e disco para esta stack,
porém a licença atual retornou `canCreateProject=false` com três projetos
existentes. O destino escolhido passou a ser o projeto `papalino`, após a remoção
autorizada dos serviços legados Grandprime, e a origem HTTPS definida é
`https://ingles.papalino.com.br`. Ainda falta integrar a branch na `main`, criar
o serviço `aulas-ingles` e executar o checklist remoto. O estado desta etapa é
**preparado, não publicado**.
