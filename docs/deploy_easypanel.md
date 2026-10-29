# Deploy público no EasyPanel

Atualização: 16 de outubro de 2026.

Este runbook prepara o primeiro deploy público sem reutilizar dados, volumes ou
segredos dos ambientes locais. O destino escolhido é o projeto `papalino` e a
origem pública é `https://ingles.papalino.com.br`. Este documento só passa a ser
registro de publicação depois que o aceite pós-deploy for anexado.

## Estado da implantação

- capacidade observada no servidor: 2 CPUs, 7,76 GiB de RAM e 51,2 GB livres;
- estimativa local da aplicação: aproximadamente 0,33 GiB de RAM em repouso e
  0,32 GB entre imagens exclusivas e banco inicial;
- assistência por IA permanece desligada; o Ollama `qwen2.5:7b` não deve dividir
  este servidor com a aplicação;
- a conta permite listar os três projetos existentes, mas
  `canCreateProject=false`: não há cota para criar um quarto projeto;
- o serviço Compose usará o nome `aulas-ingles` no projeto existente `papalino`;
- a origem pública definida é `https://ingles.papalino.com.br`;
- branch integrada na `main` pelo merge `49a6d89be8a0f2e99b9df8f8af47ebde1131545c`;
- primeiro deploy concluído no serviço `papalino/aulas-ingles`; o domínio próprio
  continua aguardando o registro DNS público.

### Registro do primeiro deploy — 16/10/2026

- ação EasyPanel: `cmvbsa80x006w06mu6tc4cjfq`;
- origem Git: `main`, no merge `49a6d89`;
- build path: `/infra/easypanel`; arquivo: `compose.yml`;
- imagens de banco, migration, permissões, API, worker e web construídas;
- banco saudável, migration/seed concluídos, grants concluídos e API saudável;
- worker e web iniciados; ação encerrada como `done` às `02:37:42 UTC` de
  17/10/2026;
- smoke externo aprovado pelo domínio gerado
  `https://papalino-aulas-ingles.aeuv6j.easypanel.host` para `/`, rota profunda,
  `/sw.js`, `/api/live` e `/api/health`;
- schema atual e requerido: `a42c7d1e9f20`; banco `up`, ambiente `prod`;
- CSP, HSTS, `nosniff`, política de referência e política de permissões presentes;
- `https://ingles.papalino.com.br` já está associado ao container `web:80` e é o
  domínio primário, mas não resolve publicamente enquanto faltar o registro DNS
  `A ingles -> 72.61.39.94`.

### Registro do segundo deploy — 21/10/2026 (Sprint 44)

- origem: `main` no squash `0ebb9be` (PR #25), CI verde nos cinco jobs antes do
  merge;
- sequência da Sprint 43 cumprida: backup anterior
  `aulas-20261021T123725650072Z-1e70…` (cifrado e copiado ao iCloud Drive);
  migration `a42c7d1e9f20 → d2b7e4c9a150` ensaiada no clone restaurado do backup
  público em `target-db` (idempotente, `alembic check` limpo, contagens iguais);
- execução: por SSH, reproduzindo o que o painel executa, porque não há token da
  API do EasyPanel e o painel só oferece deploy pela interface. O diretório
  `code/` do serviço não é um repositório Git (é uma exportação); ele foi
  atualizado com `git archive 0ebb9be | rsync --delete`, preservando
  `infra/easypanel/.env` e os `docker-compose.override.yml` gerados pelo painel,
  e a stack subiu com o mesmo comando do painel:
  `docker compose -p papalino_aulas-ingles --env-file .env -f compose.yml -f
  docker-compose.override.yml up -d --build --remove-orphans --wait`, em 3 min 08 s;
- gate: `migrate` aplicou a migration, `alembic check` sem operações, seed
  idempotente (82 aulas), `permissions` reaplicou os grants; API, worker e web
  saudáveis; `migrate` e `permissions` com saída 0;
- aceite: `/`, `/sw.js`, `/api/live`, `/api/health` e `/api/courses` em HTTP 200
  pelo domínio gerado; `schema_current` e `schema_required` iguais a
  `d2b7e4c9a150`, ambiente `prod`; CSP, HSTS, `nosniff`, COOP, `X-Frame-Options`,
  política de referência e de permissões presentes; gate operacional
  (`make operations-check` contra a origem pública) com status `ok` em todos os
  sinais;
- backup posterior `aulas-20261021T124227574247Z-7342…`, cifrado e copiado ao
  iCloud Drive;
- efeitos esperados: contadores de rate limit reiniciados uma vez (nova derivação
  da chave HMAC); `EASYPANEL_AUTH_BUCKET_SECRET` continua opcional e vazio;
- limitação registrada: o histórico de deploys do painel não mostra esta ação. O
  próximo deploy pela interface converge para a mesma `main`. Para deploys
  futuros sem interface, gerar um token da API do EasyPanel.

```text
Internet HTTPS
    │
    ▼
EasyPanel / Traefik (certificado e término TLS)
    │ HTTP interno + X-Forwarded-Proto=https
    ▼
web:80 (nginx + React)
    ├── /api/* ──► api:8000 (FastAPI, papel aulas_runtime)
    │                  │
    │                  └──► db:5432 (PostgreSQL 16, volume pgdata)
    └── arquivos estáticos

worker (papel aulas_worker) ──► db
migrate (papel aulas_migrator) ──► permissions ──► api ──► worker, web, seed
```

O gate de release é `migrate` (`alembic upgrade head && alembic check`) e
`permissions`; o `seed` editorial roda depois, com a API já saudável, pelo
papel do migrador, e uma falha dele não impede o site de subir. O nginx do `web`
resolve `api` a cada requisição (DNS embutido do Docker, TTL de 10 s), de modo
que recriar só o container da API não deixa o `web` em 502; o `worker` tem
healthcheck próprio pela batida em `worker_heartbeat`.

O serviço público é somente `web`, porta interna `80`. API e banco não têm
porta de host. Os volumes `pgdata` e `speaking_data` são persistentes. O perfil
público exige HTTPS, cookie `Secure`, HSTS e uma origem única.

## Arquivos

| Arquivo | Finalidade |
|---|---|
| `infra/easypanel/compose.yml` | stack pública e ordem segura do release |
| `infra/easypanel/Dockerfile.postgres` | PostgreSQL fixado e bootstrap dos papéis |
| `infra/easypanel/.env.example` | contrato sem credenciais reais |
| `.env.easypanel` | valores reais locais; ignorado pelo Git e Docker |
| `ops/easypanel_deploy.py` | geração exclusiva e validação sem imprimir segredos |

O `.env` da raiz contém valores de desenvolvimento e credenciais administrativas
locais; ele **não** é fonte para o EasyPanel. Credenciais da conta EasyPanel
também não pertencem às variáveis do serviço.

## 1. Preparar e validar localmente

Os segredos podem ser gerados antes da escolha do domínio. Se ele já existir,
informe-o agora; a origem não pode conter porta, caminho nem barra final.

```bash
make easypanel-env
# edite a origem quando ela existir e então valide:
make easypanel-check
```

Quando o domínio já for conhecido, use
`make easypanel-env origin=https://ingles.seudominio.com` no lugar do primeiro
comando.

O primeiro comando cria `.env.easypanel` uma única vez, com sete segredos
aleatórios e independentes e permissão `0600`. Ele recusa sobrescrever um arquivo
existente. Sem `origin`, mantém intencionalmente o marcador seguro
`https://configure-domain.invalid`; nesse estado, o check deve falhar até o
domínio ser editado. O segundo valida origem, força mínima, independência dos
segredos, feature flag e renderização do Compose sem exibir valores.

Para trocar o domínio antes do primeiro deploy, edite somente
`EASYPANEL_PUBLIC_ORIGIN` no arquivo privado e execute novamente o check. Não
copie o arquivo para `infra/`, não o adicione ao Git e não o envie em mensagens.

## 2. Gate de código

Antes da publicação:

```bash
git status --short
git diff --check
python3 -m unittest ops.tests.test_easypanel_deploy -v
make easypanel-check
```

Depois, faça commit da configuração versionável, revise o CI e integre a branch
na `main`. O serviço remoto deve usar um SHA aprovado da `main`, nunca o estado
não commitado da máquina.

## 3. Criar o serviço Compose

No projeto EasyPanel `papalino`:

1. crie um serviço do tipo **Compose**;
2. selecione fonte Git e informe
   `https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles.git`;
3. use a referência `main` e, se a tela oferecer deploy por SHA, prefira o SHA
   aprovado;
4. configure o Build Path como `/infra/easypanel`;
5. configure o arquivo Compose como `compose.yml`;
6. salve a definição do serviço sem iniciar o deploy;
7. obtenha o domínio na etapa seguinte antes de colar o ambiente privado.

## 4. Domínio e TLS

1. adicione um domínio gerado ou próprio ao serviço interno `web`, porta `80` e
   protocolo HTTP;
2. em domínio próprio, configure o DNS solicitado pelo painel;
3. habilite HTTPS, a emissão automática do certificado e marque a origem como
   primária;
4. edite `EASYPANEL_PUBLIC_ORIGIN` em `.env.easypanel` para a origem HTTPS exata;
5. execute `make easypanel-check`; não prossiga se ele recusar a configuração;
6. cole no campo de ambiente do Compose o conteúdo de `.env.easypanel` e ative a
   criação do arquivo `.env` quando a opção existir;
7. confirme que nenhuma variável `EASYPANEL_*` ficou vazia ou com marcador;
8. execute o primeiro deploy.

A cadeia esperada é:

1. `db` fica saudável;
2. `migrate` executa `alembic upgrade head && alembic check` (gate bloqueante,
   só schema);
3. `permissions` assume `aulas_owner` pelo migrador e reaplica os grants mínimos,
   sem receber a senha administrativa;
4. `api` passa no readiness;
5. `worker` e `web` iniciam; o `worker` passa a reportar saúde pela batida em
   `worker_heartbeat` (`python -m app.cli worker-health`, até 60 s de idade,
   verificado a cada 30 s após 40 s de carência);
6. `seed` roda uma vez (`python -m app.cli seed`, insert-only, papel do
   migrador) depois da API saudável e termina com saída 0.

Se `migrate` ou `permissions` falhar, API e web não devem iniciar. Não contorne o
gate com comandos manuais; leia o primeiro erro, corrija e refaça o deploy.

Se só o `seed` falhar, o site continua no ar com o conteúdo anterior: a falha
aparece no código de saída do `up --wait`, em `docker compose ps seed` e nos
logs desse container. Corrija o pacote editorial (`python -m app.cli seed
--dry-run` localmente) e refaça o deploy; não execute o seed à mão na stack.

Não publique `api` nem `db` separadamente. O Traefik encaminha o protocolo
externo no cabeçalho `X-Forwarded-Proto`; o nginx o preserva ao chamar a API.
Isso é necessário porque o backend público recusa tráfego não HTTPS.

## 5. Aceite pós-deploy

Substitua o domínio sem incluir segredos nos comandos:

```bash
export AULAS_PUBLIC_URL=https://ingles.papalino.com.br
curl --fail --silent --show-error "$AULAS_PUBLIC_URL/api/live"
curl --fail --silent --show-error "$AULAS_PUBLIC_URL/api/health"
curl --fail --silent --show-error --head "$AULAS_PUBLIC_URL/"
curl --fail --silent --show-error --head "$AULAS_PUBLIC_URL/sw.js"
```

Critérios obrigatórios:

- `/api/live` responde `200`;
- `/api/health` responde `200`, `status=ok`, banco `up` e schema `compatible`;
- `/` e uma rota profunda da SPA respondem `200`;
- HTTP redireciona para HTTPS;
- HTML e API apresentam HSTS em HTTPS;
- cadastro, login, refresh, logout e exclusão de conta funcionam;
- uma aula, um exercício, progresso, Caderno, Revisão e uma gravação curta
  persistem após redeploy;
- `db` e `api` não são acessíveis diretamente pela Internet;
- os logs não mostram credenciais, tokens, respostas de exercícios nem áudio.

Execute ainda o checklist humano de acessibilidade e listening já registrado na
Sprint 43; deploy aprovado não substitui essas homologações.

## 6. Backup inicial e rotina

No primeiro deploy o banco nasce vazio e é preenchido somente pelo seed. O
backup da stack pública é feito pela rotina do repositório, não pelo painel:

```bash
make backup-public-check                 # SSH, containers, papel aulas_backup, revisão
make backup source=public                # pacote aulas-recovery-v2 em backups/recovery/
make backup source=public recipient=secrets/backup-age-recipient.txt copy_to=/Volumes/externo
make backup-verify f=backups/recovery/aulas-IDENTIFICADOR
make backup-prune                        # plano 7 diários + 4 semanais; --apply só via backup-prune-apply
```

`ops/public_backup.py` conecta por SSH (`BatchMode`, `StrictHostKeyChecking=yes`,
host em `AULAS_PUBLIC_SSH_HOST` ou o documentado) e lê o banco **dentro do
container** com o papel `aulas_backup`, por socket local: nenhuma senha é lida ou
transmitida. O volume de voz sai pelo mesmo `voice_transfer.py` do fluxo local,
copiado de forma efêmera para a VM e executado em container sem rede e somente
leitura. Como a stack pública não entra em manutenção, o snapshot do banco é
conferido antes e depois da captura; divergência não publica o pacote (até três
tentativas). O recibo fica em `backups/recovery/public-receipts/` e não contém
segredos nem endereço da VM.

A cópia externa só sai cifrada: `recipient` aponta para um arquivo com a chave
pública `age1...` cuja chave privada **não** mora neste Mac. Sem `age` instalado
(`brew install age`) ou sem destinatário, o pacote fica só local.

Primeiro backup real registrado em 21/10/2026: pacote
`aulas-20261021T042626017843Z-bb04073b9b2947e69be89683970bda70`, revisão
`a42c7d1e9f20`, 82 aulas, 1 usuário, `database.dump` com 631.101 bytes
(sha256 `5c484686…415f0`), voz vazia, verificado por `make backup-verify`.
Esse pacote foi restaurado em 21/10/2026 no alvo `aulas-ingles-recovery/target-db`,
liberado com autorização de Jeferson (os volumes do ensaio da Sprint 37 foram
removidos para isso). Recibo em `backups/recovery/restore-receipts/`, `verified`
verdadeiro, 124 s; o clone respondeu revisão `a42c7d1e9f20`, 82 aulas e 1 usuário
pela mesma rotina de snapshot. Laboratório encerrado com volumes preservados.

Ainda em 21/10/2026, após autorização: `age` 1.3.2 instalado em `~/.local/bin` a
partir do release oficial (sha256 do tarball
`e2020b073c44f692685a24d6abc378817eb81ffaaf49fd0531ef8565f767f2f5`); par de
chaves gerado em `secrets/` (`backup-age-identity.txt` e `backup-age-recipient.txt`,
600); destino externo `~/Library/Mobile Documents/com~apple~CloudDocs/aulas-ingles-backups`
(iCloud Drive, só recebe `.tar.age`); agente launchd
`br.com.papalino.aulas-backup-public` instalado para 03:10 diário, com uma
execução de teste concluída com saída 0, recibo e cópia externa. Dois pacotes
cifrados já estão no destino externo; a decifra foi conferida listando o conteúdo.

Metas operacionais ainda a validar:

- RPO máximo de 24 horas: o agendamento está instalado; falta comprovar recibos
  em dias consecutivos (o Mac precisa estar ligado às 03:10);
- RTO de até 60 minutos: a janela medida foi de 124 s de restore mais a captura,
  sem incluir detecção e decisão;
- retenção de sete cópias diárias e quatro semanais: `make backup-prune-apply`
  executado em 21/10/2026 (10 pacotes e 1 parcial removidos, 4 mantidos);
- **custódia da chave privada**: `secrets/backup-age-identity.txt` ainda mora só
  neste Mac. Copie para um gerenciador de senhas ou outro dispositivo e, se
  decidir, apague a cópia local. Sem isso, perder o Mac perde também a chave das
  cópias externas.

Um arquivo de backup só vira evidência após verificação de checksum e restore
isolado. Antes de migrations futuras, gere nova cópia, restaure-a num alvo
descartável e execute a candidata sobre o clone.

## 7. Rollback

### Falha antes da migration

Interrompa o release e volte o serviço para o último SHA aprovado. Os volumes não
devem ser removidos.

### Falha de aplicação com schema compatível

Faça redeploy do SHA anterior e repita readiness e smokes. Registre o intervalo,
o motivo e os IDs das imagens.

### Migration incompatível ou dados alterados

1. ative manutenção e pare web, API e worker;
2. preserve o volume original; nunca restaure por cima dele;
3. restaure o backup pré-release em um volume/banco novo;
4. valide checksum, revisão, contagens, referências de voz e aplicação anterior;
5. troque o serviço para o alvo restaurado somente após aceite;
6. mantenha o volume falho isolado para diagnóstico.

Não use `docker compose down -v`, não apague volumes pelo painel e não execute
`alembic downgrade` como atalho operacional.

## 8. Encerramento

O deploy só pode ser chamado de concluído quando houver:

- projeto de destino e domínio registrados;
- SHA da `main` e CI aprovados;
- `make easypanel-check` aprovado;
- stack e certificado saudáveis;
- aceite funcional e de persistência;
- backup pós-deploy verificado;
- evidências sem segredos anexadas ao registro da mudança.

Estado atual: **implantado, com aceite remoto parcial**. O domínio gerado está
saudável; o encerramento integral ainda depende do DNS/certificado do domínio
próprio, do teste funcional autenticado, da persistência após redeploy e do
backup inicial verificado.

## Deploy automatizado — `make deploy-public` e o job `deploy` (Sprint 45)

A partir da Sprint 45 o procedimento do segundo deploy virou script:
`ops/deploy_public.sh` reproduz por SSH exatamente o que foi feito à mão em
21/10/2026, e o job `deploy` do CI o executa a cada push na `main` que passar
nos quatro jobs bloqueantes.

### O que o script faz

`make deploy-public sha=<sha>` (ou `bash ops/deploy_public.sh <sha>`) executa,
nesta ordem, parando no primeiro erro:

1. confere **localmente** que o SHA existe e é ancestral de `origin/main`
   (`git merge-base --is-ancestor`); branch, tag ou commit fora da `main` são
   recusados antes de qualquer contato com a VM (faça `git fetch origin main`
   se o seu clone estiver atrasado);
2. pré-voo por SSH: `code/`, `compose.yml`, o `.env` e o
   `docker-compose.override.yml` gerados pelo painel, `rsync` e `docker compose`
   precisam existir — nada é alterado se faltar algo;
3. `git archive --format=tar <sha> | ssh ... tar -x -C /tmp/aulas-deploy-<sha>`;
4. `rsync -a --delete` de `/tmp/aulas-deploy-<sha>/` para
   `/etc/easypanel/projects/papalino/aulas-ingles/code/`, preservando
   `/docker-compose.override.yml`, `/infra/easypanel/.env` e
   `/infra/easypanel/docker-compose.override.yml`; grava `code/.deployed-sha`
   (`<sha> <data UTC> <origem>`, o mesmo formato já usado na VM) e remove o
   diretório temporário;
5. em `code/infra/easypanel`: `docker compose -p papalino_aulas-ingles
   --env-file .env -f compose.yml -f docker-compose.override.yml up -d --build
   --remove-orphans --wait --wait-timeout 420` — o mesmo comando do painel;
6. imprime `docker compose ps -a` e os códigos de saída de `migrate`,
   `permissions` e `seed` (serviço próprio desde a Sprint 45, executado depois
   da API saudável); `up` reprovado ou qualquer one-shot diferente de 0 mostra
   os últimos logs de `migrate`/`permissions` e falha o deploy — a stack fica
   como o Compose a deixou, sem contorno manual. Um `seed` reprovado deixa o
   site no ar com o conteúdo anterior, mas o deploy sai vermelho para a falha
   editorial não passar despercebida;
7. smokes HTTPS em `AULAS_PUBLIC_URL` (padrão: domínio gerado pelo painel):
   `/`, `/sw.js`, `/api/live`, `/api/health` e `/api/courses` em 200 (até três
   tentativas cada) e `status=ok`, `db=up`, `schema=compatible` no JSON do health.
   A API compara as revisões internamente; o smoke público não recebe os seus nomes.

SSH sempre com `-o BatchMode=yes -o StrictHostKeyChecking=yes`: sem senha
interativa e sem aceitar host desconhecido. O script nunca lê nem imprime o
`.env` remoto; só o referencia por `--env-file`. `AULAS_PUBLIC_SSH_HOST` troca o
destino (padrão `root@72.61.39.94`, o mesmo de `ops/public_backup.py`).

`make deploy-public-dry-run sha=<sha>` imprime cada comando prefixado por
`[dry-run]` sem executar nada remoto — use antes de um deploy manual ou para
revisar o que o CI fará. `--skip-smoke` pula a etapa 7. Os testes em
`ops/tests/test_deploy_public.py` (rodam em `make test-recovery`) simulam `ssh`,
`git` e `curl` e cobrem recusa de SHA, dry-run sem chamadas remotas, sequência
dos comandos, one-shot com saída 1, `up` reprovado, smoke com 500 e schema
divergente.

### O job `deploy` do CI

`needs: [backend, frontend, e2e, recovery]`, só em `push` na `main`, environment
`production`, 20 minutos de limite e grupo de concorrência `deploy-public` sem
cancelamento (dois merges seguidos entram em fila). Na `main` o workflow também
deixou de cancelar a execução anterior, para um merge novo não derrubar um
`compose up` em andamento. Um CI vermelho não chega ao EasyPanel porque o job
nem inicia.

Sem o segredo `PUBLIC_DEPLOY_SSH_KEY`, o job emite um `::notice::` dizendo que
o deploy automatizado está desarmado e termina verde, sem tocar na VM — o deploy
continua manual (`make deploy-public`). Com o segredo, o job instala a chave em
`~/.ssh/id_deploy` (0600, `IdentitiesOnly yes`), grava `known_hosts` a partir de
`PUBLIC_DEPLOY_KNOWN_HOSTS` (recusa se vazio), exporta `AULAS_PUBLIC_SSH_HOST` de
`PUBLIC_DEPLOY_HOST` e roda `bash ops/deploy_public.sh "$GITHUB_SHA"`. Nenhum
segredo passa por `echo`.

### Secrets a criar (Settings → Secrets and variables → Actions)

| Secret | Conteúdo | Como obter |
|---|---|---|
| `PUBLIC_DEPLOY_SSH_KEY` | chave privada OpenSSH **exclusiva** para deploy | `ssh-keygen -t ed25519 -f deploy-aulas-ingles -C deploy-aulas-ingles -N ""`; cole a privada no segredo, acrescente a pública em `~/.ssh/authorized_keys` do usuário de deploy na VM e apague a privada da máquina |
| `PUBLIC_DEPLOY_KNOWN_HOSTS` | linha(s) de `known_hosts` da VM | `ssh-keyscan -t ed25519 72.61.39.94`; confira a impressão digital (`ssh-keygen -lf`) contra a já conhecida no Mac (`ssh-keygen -F 72.61.39.94`) antes de colar |
| `PUBLIC_DEPLOY_HOST` | `root@72.61.39.94` (ou outro usuário) | opcional; sem ele vale o padrão do script |

Recomendações: não reutilizar a chave pessoal do Mac; preferir um usuário da VM
dedicado ao deploy, com acesso ao Docker e ao diretório do serviço; revogar a
chave em `authorized_keys` se o segredo vazar. Para exigir aprovação humana
antes de cada deploy, configure *required reviewers* no environment
`production` do GitHub — o job já o declara.

Alternativa ao SSH: um token da API do EasyPanel disparando o deploy do serviço
`papalino/aulas-ingles` e deixando o build para o painel. É o caminho preferido
quando o token existir, porque o deploy passa a aparecer no histórico do painel;
o script por SSH continua valendo como contingência.

### Limitações

- O histórico de deploys do painel não registra deploys por SSH; a evidência é
  `code/.deployed-sha` na VM, o log do job no GitHub e este documento. Um deploy
  pela interface do painel depois converge para a mesma `main`.
- O script publica código: variáveis de ambiente continuam sendo editadas no
  painel (`.env` gerado), e o script as preserva.
- O backup anterior/posterior e o ensaio da migration no clone restaurado
  continuam sendo passos humanos da sequência da Sprint 43; o job não os faz.
  Antes de mergear uma migration na `main`, ensaie-a no clone primeiro.

## Vigilância agendada — probe externo e gate operacional (INFRA-46)

Atualização de 29/10/2026: `PUBLIC_PROBE_ORIGIN` configurada e probe público
aprovado no [run 40932540081](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/actions/runs/40932540081).
A etapa autenticada ficou ignorada por falta de `OPERATIONS_TOKEN` no GitHub;
o token existente na VM não foi transferido. Cron root/sistema sem entrada
reconhecida do monitor e `sendmail` ausente. A publicação do workflow não
equivale à comprovação de alerta; ver [matriz do piloto](matriz_aceite_sprint_48.md).

O monitor atualizado aceita limites `0` para operação sem gasto autorizado:
custo confirmado zero passa; valor positivo ou desconhecido é crítico.
Campos ausentes continuam gerando aviso. Isso é avaliação/alerta, não bloqueio
de chamadas nem comprovação da franquia disponível na conta. Publicar essa
versão antes de configurar zero; o release `9cc14fe` ainda exige valor positivo.

Duas coisas rodam fora da aplicação e precisam rodar em algum relógio: o
**probe externo**, que diz se o domínio público responde, e o **gate
operacional**, que compara worker, fila e custo do diálogo com limiares.

### Dois relógios, de propósito

| Onde | Comando | Resolução | Para que serve |
|---|---|---|---|
| Cron da VM | `make operations-alert` | o que você agendar (1–2 min é viável) | é o caminho principal; o aceite do INFRA-46 pede alerta para worker parado por 2 minutos, e só um cron curto vê isso |
| GitHub Actions | workflow `operações · vigilância da stack pública` | `*/30`, **melhor-esforço** | rede de segurança de fora: um probe no mesmo host não distingue "a aplicação caiu" de "o host caiu" |

O cron do GitHub para repositórios atrasa com frequência e pode pular
execuções em períodos de carga. Ele não substitui o cron da VM para a
resolução de minutos; serve para o caso em que a VM inteira está fora e,
portanto, nenhum cron dela vai reclamar.

### Alerta por e-mail, sem segredo de SMTP

- **GitHub**: o job **falha** (exit 1) quando um limiar estoura, e o GitHub
  envia a notificação nativa de falha de workflow agendado para quem mexeu no
  cron por último. Confira em Settings → Notifications que "Actions" está
  marcado para e-mail. Não há SMTP nem segredo de e-mail no repositório.
- **VM**: `make operations-alert` é silencioso quando está tudo bem e escreve
  o relatório em stdout quando não está, que é exatamente o contrato que o
  `cron` espera para mandar e-mail. Depende de um MTA funcionando na VM
  (`mailutils` ou equivalente); sem ele, o cron registra em
  `/var/log/syslog` e o e-mail não sai — confira antes de confiar.

Linha de crontab sugerida, de dois em dois minutos:

```cron
MAILTO=voce@exemplo.com
OPERATIONS_BASE_URL=http://127.0.0.1:8011
OPERATIONS_TOKEN=...
*/2 * * * * cd /caminho/para/aulas-ingles && make operations-alert
```

O token fica no crontab do usuário, com `chmod 600`; ele dá leitura de
`/api/operations/metrics` e `/api/operations/readiness`. As métricas são
agregadas; o diagnóstico inclui versão do banco, ambiente e revisões de schema.
Nenhuma dessas respostas carrega texto de aluno, mas o token continua sendo credencial.

### Saúde pública e diagnóstico autenticado (BE-49)

| Rota | Acesso | Verificação |
|---|---|---|
| `/api/live` | público | processo responde; não consulta banco |
| `/api/health` | público | banco acessível e revisões aplicadas iguais às da imagem; retorna apenas `status`, `db`, `schema` e `code` |
| `/api/operations/readiness` | `Authorization: Bearer <OPERATIONS_TOKEN>` | mesma verificação, com `version`, `env`, `schema_current` e `schema_required` |

Banco indisponível ou schema incompatível mantêm HTTP 503 nas duas rotas de
prontidão. Os diagnósticos têm `Cache-Control: private, no-store`. Sem token
operacional configurado, a rota privada retorna 404; credencial ausente ou
incorreta retorna 401 quando ele está configurado, antes de consultar o banco.
Enviar token ao health público não acrescenta detalhes à resposta.

`make operations-check` consulta a readiness privada e as métricas com o mesmo
token. O probe externo continua sem credencial e também reprova exposição de
versão, ambiente ou revisões no health público. Publique API e consumidores
operacionais juntos: a versão anterior da API não oferece a rota privada.

### Secrets do workflow

| Secret | Conteúdo | Sem ela |
|---|---|---|
| `PUBLIC_PROBE_ORIGIN` | `https://dominio-publico` | o workflow avisa que está desarmado e passa sem fazer nada |
| `OPERATIONS_TOKEN` | o mesmo `OPERATIONS_TOKEN` da aplicação | só o probe roda; o gate de métricas fica de fora |

O probe não usa credencial nenhuma: `/api/health` é público. É por isso que ele
roda primeiro e sozinho — disponibilidade é a pergunta que não deve depender de
um segredo estar configurado.

### O que cada limiar do diálogo significa

O INFRA-48 acrescenta `assist_costs.daily` e `assist_costs.monthly` ao endpoint
privado de métricas. Os totais abrangem escrita, transcrição e conversa,
contados uma vez por reserva consumida, pelo instante de despacho em UTC
(`created_at` nos registros legados sem despacho). São dia e mês de calendário,
até `sampled_at`; cada janela traz início, fim, quantidade consumida, custo em
microusd e quantidade de custos desconhecidos. Um USD corresponde a 1.000.000
microusd. O custo pode ser parcial enquanto houver valores desconhecidos.

Configure no ambiente do cron e nas **variables** do repositório do GitHub:

- `OPERATIONS_ASSIST_DAILY_BUDGET_MICROUSD`: orçamento diário aprovado, inteiro não negativo.
- `OPERATIONS_ASSIST_MONTHLY_BUDGET_MICROUSD`: orçamento mensal aprovado, inteiro não negativo.

Não há valor presumido para esses dois orçamentos. Ausência gera `warning`;
valor inválido encerra o comando com código 2 antes de qualquer requisição.
Com orçamento positivo, consumo >= 80% gera `warning` e >= 100% gera
`critical`. Com teto zero, somente custo confirmado zero passa; custo positivo
gera `critical`. Custo desconhecido ou métrica ausente/inválida gera `critical`.
Tanto `warning` quanto `critical` retornam código 1, permitindo que cron e
workflow sinalizem o problema. O resumo do workflow conserva o relatório
também quando há alerta. Nenhum envio foi disparado pela validação local.

O ledger permanece após excluir uma conversa ou expirar seu texto, evitando
que a exclusão reduza o custo observado. A exclusão da **conta** remove suas
reservas; por isso estes totais representam o ledger existente e precisam
ser conciliados com a fatura do provedor. Não são um livro contábil permanente.
O alerta não desliga flags automaticamente. Os checks legados abaixo continuam
ativos, inclusive o teto diário adicional de conversa.

| Check | Limiar | Responsável | Ação |
|---|---|---|---|
| `dialogue_cost_microusd_today` | ≤ 50.000 microusd | release manager | desligar a modalidade e conferir a fatura antes de religar |
| `dialogue_provider_failure_rate` | ≤ 0,2 com amostra ≥ 5 turnos | release manager | conferir o provedor; o Roteiro continua atendendo |
| `dialogue_quota_accounting` | seção `dialogue` presente | release manager | a API em uso é mais antiga que o gate: implantar antes de confiar no relatório |

O teto de custo é folga de uma ordem de grandeza sobre o uso esperado: a cota
são 24 turnos por dia, e o turno fica na casa de centenas de microusd. Passar
de 50.000 não é aluno conversando.

### O que isto não faz

- Não alerta por SMS, Telegram ou webhook. E-mail é o canal, e é o que existe
  sem segredo novo.
- Não mede latência de dentro da VM: o probe externo inclui a rede do runner
  até lá, e por isso o limiar dele é generoso (5 s).
- Não vigia o provedor de IA diretamente. O que ele vê é o efeito —
  `provider_failures` e `fallback` nas métricas do dia.

## Bundles de abas abertas durante um deploy

O PWA aguarda todas as abas fecharem antes de ativar uma atualização. Enquanto
isso, o shell antigo pode pedir pela primeira vez um chunk lazy, como Caderno.
Substituir a imagem removendo esse arquivo causava 404 e a tela de recuperação.
Em 29/10/2026, os logs confirmaram o problema nos arquivos
`study-tools-DYItHnjn.js` e `HistoricalContentDetails-zf8C-HIs.js`.

O serviço `web` agora monta `web_assets` em `/var/lib/aulas-web`. No boot,
`frontend/40-retain-assets.sh` arquiva os bundles públicos da imagem com troca
atômica por arquivo. O manifesto `.current-assets` renova a data da versão que
está saindo: mesmo uma versão ativa há meses tem mais de 30 dias de retenção
após a substituição. Arquivos fora dessa janela são removidos no próximo boot.
O nginx procura primeiro na imagem atual, depois nesse arquivo persistente;
um nome inexistente continua retornando 404, sem cache imutável nem HTML.
O volume não recebe HTML, service worker, banco, rascunhos ou gravações.

Na primeira implantação dessa correção, é necessário semear o volume com
os `/usr/share/nginx/html/assets` das imagens anteriores disponíveis, incluindo
a versão ativa, antes de substituí-la. Os arquivos do incidente foram
recuperados da imagem local `f2b0ba288981`, sem reconstruir ou renomear bundles:
um hash antigo deve sempre corresponder aos bytes originais. Sem esse artefato,
o aluno precisa salvar o trabalho pendente e fechar todas as abas/janelas do
aplicativo para ativar a versão atual; limpar dados do site não é necessário.
Nos próximos deploys o arquivamento é automático. Preserve `web_assets` também
em rollback e não use `compose down -v`.

Regressão: `npm run test:scripts --prefix frontend` cobre retenção/expiração e
`bash ops/test_web_assets.sh aulas-ingles-e2e-web:local` troca dois containers
nginx com dados sintéticos, pede o chunk antigo pela primeira vez só depois da
troca e verifica bytes, MIME, cache, shell atual e 404. Este último roda no CI.

## Referências do painel

- [Compose Service — documentação oficial do EasyPanel](https://easypanel.io/docs/services/compose)
- [API do EasyPanel](https://easypanel.io/docs/api)
- [CLI do EasyPanel](https://easypanel.io/docs/cli)
