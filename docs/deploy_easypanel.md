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

Não publique `api` nem `db` separadamente. Antes do deploy da Sprint 51, configure
**`EASYPANEL_TRUSTED_PROXY_CIDRS`** com os IPs/CIDRs revisados do Traefik visto
pelo web. O Compose e o check recusam o perfil público sem essa configuração.
Acrescente a variável ao arquivo privado existente; não regenere os segredos.

Somente esse peer pode fornecer o endereço do aluno e `X-Forwarded-Proto`.
O nginx substitui a cadeia recebida por um único IP resolvido ao chamar a API.
Isso preserva HTTPS e separa os limites por origem sem confiar em headers do aluno.
Confira `forwardedHeaders.insecure` desligado e o acréscimo do endereço observado
à direita da cadeia. O procedimento e as pendências de aceite estão na
[execução da Sprint 51](execucao_sprint51_2026-11-05.md).

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

**Atualização de 05/11/2026:** a rotina substituta no servidor, holds, poda cifrada
e o restore em uma stack pública nova estão no
[runbook da Sprint 54](backup_recuperacao_publica_2026-11-05.md).
O registro do launchd abaixo é histórico; instalação na VM e custódia separada
continuam pendentes de comprovação operacional.

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
leitura. Dump e manifesto compartilham um snapshot exportado; revisão e referências
de voz são conferidas antes/depois, com até três tentativas. Eventos de estudo
não invalidam a captura. O recibo fica em `backups/recovery/public-receipts/` e não contém
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

## Deploy automatizado — Sprint 55

O cliente `make deploy-public sha=<sha>` agora chama um comando SSH restrito,
instalado separadamente no servidor. O procedimento da Sprint 45 foi substituído:
configuração, instalação, adoção da release atual, migração do volume do nginx e
rollback estão no [runbook de deploy seguro](deploy_seguro_2026-11-05.md).

São obrigatórios usuário sem root, host explícito, known_hosts verificado e origem
HTTPS. Não existe mais destino de produção embutido no script. O CI depende de
backend, frontend, E2E, recovery, infra-lint e segurança; CRITICAL ou relatório
inválido bloqueiam deploy. O environment `production` precisa de revisores
configurados no GitHub; declarar o nome no YAML não cria essa proteção.

O backup anterior/posterior e o ensaio de migration no clone continuam na sequência
da Sprint 43. A implementação local não comprova instalação ou deploy na VM.

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
  o relatório em stderr quando não está, que é exatamente o contrato que o
  `cron` espera para mandar e-mail. Depende de um MTA funcionando na VM
  (`mailutils` ou equivalente); sem ele, o cron registra em
  `/var/log/syslog` e o e-mail não sai — confira antes de confiar.

O modelo [infra/cron/aulas-operations.example](../infra/cron/aulas-operations.example)
executa de dois em dois minutos, com lock e timeout. É um crontab de usuário;
ajuste destinatário, permissões do lock e caminho do código antes de instalar.
O runner `python3 -m ops.operations_alert` usa biblioteca padrão (Python 3.12+),
dispensa `uv` no host e conserva saída 1 para alerta e 2 para erro de execução.
Sem incidente não escreve; falha inesperada usa diagnóstico fixo sanitizado.

Prepare `/etc/aulas/operations.env` a partir de
[config/operations-watch.env.example](../config/operations-watch.env.example),
com proprietário do processo operacional e modo 0600. Use a origem HTTPS pública
no EasyPanel; `http://127.0.0.1:8011` serve apenas ao ambiente de estudo local.
Esse arquivo é privado e não deve ser versionado. O token dá leitura de
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
| `OPERATIONS_TOKEN` | o mesmo `OPERATIONS_TOKEN` da aplicação | com origem configurada, o job falha por configuração incompleta |

O probe não usa credencial: `/api/health` é público. O workflow exige as duas
configurações para armar a vigilância completa. Com elas presentes, o gate privado
executa mesmo se o probe externo falhar. Os dois preservam seus códigos de saída
e o relatório no resumo do job, sem depender do resultado de um `tee`.

O shell Bash explícito usa `pipefail`, conforme a
[referência oficial do GitHub Actions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
O teste `ops/tests/test_operations_workflow.py` executa os blocos reais com probes
sintéticos que retornam 0, 1 e 2, incluindo origem configurada sem token.

**Aceite operacional da Sprint 50:** depois de publicar, configurar as secrets,
instalar o cron e comprovar entrega do MTA, interromper apenas o worker de uma
stack de ensaio e registrar alerta recebido em até cinco minutos. Restaurar o
worker e verificar recuperação. O cron do GitHub a cada 30 minutos não comprova
esse prazo. Testes locais de saída não comprovam configuração remota, recebimento
de e-mail nem publicação; esses itens permanecem pendentes até evidência do ensaio.

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

Por padrão, a PWA aguarda todas as abas fecharem antes de ativar uma atualização.
O aluno também pode confirmar **Recarregar aplicativo…**: o aplicativo busca a
atualização, ativa o worker novo e só então recarrega a aba solicitante. As outras
abas continuam abertas; salvar textos ou gravações ainda apenas na memória
continua necessário. Falha de rede ou de ativação mantém a tela aberta para nova
tentativa. Essa ação preserva rascunhos e fila local; caches de conteúdo público
podem ser renovados pela ativação.

**Primeira publicação da FE-01:** abas que ainda executam o bundle anterior
continuam com o botão antigo de recarga. Depois de salvar o trabalho pendente,
feche todas as abas/janelas instaladas do aplicativo uma vez e reabra para
receber esta correção. O botão novo passa a conduzir as atualizações seguintes;
publicar JavaScript novo não substitui o código já carregado nas abas antigas.
Esse passo inicial precisa ocorrer antes do corte dos clientes legados.

Enquanto uma aba permanece na versão anterior, o shell antigo pode pedir pela
primeira vez um chunk lazy, como Caderno.
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


### Restrição do piloto de conversa por conta

Antes de ativar o piloto, configurar `EASYPANEL_DIALOGUE_PILOT_USER_IDS`
como lista JSON de IDs internos positivos na configuração privada. O Compose
repassa o mesmo valor à API e ao worker. O padrão `[]` bloqueia todas as modalidades
assistidas em produção/public, mesmo com gateway e flags configurados.
Não publicar IDs reais em Git, logs de deploy ou documentação.

Para alterar/revogar participantes, desligar a assistência, atualizar a lista
nos dois processos e reiniciá-los antes de eventual reativação. Configuração
é lida no início do processo; editar somente o arquivo não revoga workers já
em execução. Chamadas já enviadas não podem ser canceladas retroativamente.
Histórico/exportação/exclusão e modo Roteiro permanecem disponíveis.
Os pré-requisitos e o estado de publicação estão na
[matriz da Sprint 48](matriz_aceite_sprint_48.md).


### Workers AI — configuração do piloto de áudio (29/10/2026)

O gateway é a API HTTPS oficial da Cloudflare, consumida pelo adaptador
`cloudflare_provider.py`. Não há novo Worker, proxy, storage, AI Gateway com
logs/cache, créditos pagos ou serviço extra na VM.

Na configuração privada do EasyPanel, usar `EASYPANEL_ASSIST_PROVIDER_KIND=cloudflare`,
`EASYPANEL_ASSIST_PROVIDER_NAME=cloudflare-workers-ai` e
`EASYPANEL_ASSIST_JOB_MAX_ATTEMPTS=1`. As URLs de diálogo/STT seguem o formato
`https://api.cloudflare.com/client/v4/accounts/<conta>/ai/run/<modelo>` com
modelos fixos `@cf/meta/llama-3.3-70b-instruct-fp8-fast` e
`@cf/openai/whisper-tiny-en`. Escrita permanece sem URL. Token somente em
`EASYPANEL_ASSIST_PROVIDER_TOKEN`, nunca em argumento de shell ou Git.

`EASYPANEL_ASSIST_CLOUDFLARE_FREE_PLAN_CONFIRMED=true` exige confirmação
operacional de Workers Free; não verifica faturamento automaticamente. As
consultas de faturamento retornaram 403 com a credencial disponível. Mudança de
plano deve desligar assistência e invalidar essa confirmação. O adaptador só
registra custo conhecido zero sob essa condição; não estima cobrança por tokens.

A lista `EASYPANEL_DIALOGUE_PILOT_USER_IDS` também protege STT compartilhada e
escrita assistida. Manter lista idêntica na API e worker. A troca/revogação só é
efetiva após recriar ambos. Chamadas já enviadas não são recolhidas. Uma tentativa
por job evita retries de inferência que poderiam repetir consumo; jobs antigos
com limites maiores devem ser avaliados antes de ativar o piloto.

Preparação privada recebida na VM após autorização expressa do responsável:
`/root/aulas-release/sprint48/assist-config-candidate.json` (0600), com lista de
uma conta e flags desligadas. Aplicar somente junto do código que conhece o
adaptador; preservar cópia 0600 do ambiente anterior. Não anunciar áudio liberado
até os gates de publicação, revisão informada e saúde operacional passarem.
