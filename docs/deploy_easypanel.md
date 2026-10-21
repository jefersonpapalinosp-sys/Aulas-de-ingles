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

## Arquitetura publicada

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
migrate (papel aulas_migrator) ──► permissions ──► api ──► web
```

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
2. `migrate` executa `upgrade`, `check` e seed insert-only;
3. `permissions` assume `aulas_owner` pelo migrador e reaplica os grants mínimos,
   sem receber a senha administrativa;
4. `api` passa no readiness;
5. `worker` e `web` iniciam.

Se `migrate` ou `permissions` falhar, API e web não devem iniciar. Não contorne o
gate com comandos manuais; leia o primeiro erro, corrija e refaça o deploy.

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

## Referências do painel

- [Compose Service — documentação oficial do EasyPanel](https://easypanel.io/docs/services/compose)
- [API do EasyPanel](https://easypanel.io/docs/api)
- [CLI do EasyPanel](https://easypanel.io/docs/cli)
