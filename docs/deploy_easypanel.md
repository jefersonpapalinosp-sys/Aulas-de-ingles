# Deploy público no EasyPanel

Atualização: 16 de outubro de 2026.

Este runbook prepara o primeiro deploy público sem reutilizar dados, volumes ou
segredos dos ambientes locais. O destino escolhido é o projeto `papalino` e a
origem pública é `https://ingles.papalino.com.br`. Este documento só passa a ser
registro de publicação depois que o aceite pós-deploy for anexado.

## Estado da preparação

- capacidade observada no servidor: 2 CPUs, 7,76 GiB de RAM e 51,2 GB livres;
- estimativa local da aplicação: aproximadamente 0,33 GiB de RAM em repouso e
  0,32 GB entre imagens exclusivas e banco inicial;
- assistência por IA permanece desligada; o Ollama `qwen2.5:7b` não deve dividir
  este servidor com a aplicação;
- a conta permite listar os três projetos existentes, mas
  `canCreateProject=false`: não há cota para criar um quarto projeto;
- o serviço Compose usará o nome `aulas-ingles` no projeto existente `papalino`;
- a origem pública definida é `https://ingles.papalino.com.br`;
- branch preparada localmente: `sprint/43-implantacao-estudo`; publicar somente
  depois de commit, revisão e merge na `main`.

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
4. configure o diretório raiz como `/`;
5. configure o arquivo Compose como `infra/easypanel/compose.yml`;
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

No primeiro deploy o banco nasce vazio e é preenchido somente pelo seed. Depois
do aceite, crie o primeiro backup de banco e do volume `speaking_data` pelo
mecanismo de backup do host/painel. Registre data, SHA do código, revisão Alembic,
checksum e resultado de restauração em alvo isolado.

Metas operacionais ainda a validar:

- RPO máximo de 24 horas;
- RTO de até 60 minutos;
- retenção de sete cópias diárias e quatro semanais;
- cópias mantidas neste Mac apenas durante o estágio de desenvolvimento.

Um arquivo de backup só vira evidência após verificação de checksum e restore
isolado. Antes de migrations futuras, coloque o serviço em manutenção, gere nova
cópia, restaure-a num alvo descartável e execute a candidata sobre o clone.

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

Até esses itens existirem, o estado correto é **preparado, não publicado**.

## Referências do painel

- [Compose Service — documentação oficial do EasyPanel](https://easypanel.io/docs/services/compose)
- [API do EasyPanel](https://easypanel.io/docs/api)
- [CLI do EasyPanel](https://easypanel.io/docs/cli)
