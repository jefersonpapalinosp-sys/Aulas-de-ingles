# Operação local — Sprints 37 a 41

Escopo: desenvolvimento no Mac de Jeferson. A stack aulas-ingles-prod em
localhost:5181 é **produção local**, não serviço público. Desenvolvimento em
5180 tem manutenção independente. Nunca executar pytest/E2E nessas bases.

Estado vigente: Sprint 40 fechada tecnicamente em branch em 16/10/2026, com head
`a42c7d1e9f20` aprovado somente no PostgreSQL descartável e no laboratório de
papéis. Este incremento não inspecionou nem alterou DEV 5180 ou estudo 5181.
Aceites físicos/pedagógicos e rollout continuam separados. Comandos antigos são
históricos e não devem ser repetidos como atualização genérica para sprints posteriores.

## Decisões autorizadas em 13/10/2026

Jeferson autorizou manutenção temporária em 5181 **depois do ensaio isolado**,
com backup real anterior às migrations e mudanças de papéis, preservando dados.
Também aprovou:

- RPO alvo: no máximo **24 horas** de alterações perdidas.
- RTO alvo: **60 minutos**, a validar para recuperação completa.
- Retenção desejada: **7 diários + 4 semanais**; responsável: **Jeferson**.
- Manter os backups **neste Mac** enquanto o projeto está em desenvolvimento.
- Fechar a entrega **técnica** e manter a homologação pedagógica humana dos
  82 exemplos como pendência, sem declará-la aprovada.

Metas não são SLA. Não há agendamento automático instalado; enquanto não
houver execução/verificação diária, não se afirma cumprimento do RPO.
Tempo de restore isolado não inclui detecção, provisionamento, recuperação
das credenciais e retorno de toda a aplicação.

## Proteção e retenção

Pacotes, recibos e credenciais: backups/recovery/, ignorado pelo Git/builds.
Diretórios privados 0700; arquivos privados 0600. FileVault observado
**ativo** no Mac. Isso protege o disco em repouso; dumps/voz **não têm
criptografia independente** e são acessíveis à conta desbloqueada/administrador.

Não há cópia externa. Perda, roubo ou falha do Mac pode eliminar dados e
backups juntos; limitação aceita apenas no estágio local. Antes de publicar,
escolher destino independente e criptografia dos pacotes com chave separada.

Retenção manual: preservar o último pacote verificado de cada um dos 7 dias
recentes e um de cada uma das 4 semanas recentes; o mesmo pacote pode atender
às duas janelas. Preservar adicionalmente o pré-migration até aceite do rollout.
Só considerar remoção de excedentes após verificar pacote substituto/restore.
Nenhuma rotação de senhas ou limpeza automática de backups foi instalada.
Na Sprint 39G/H, somente TTL de transcrições/reservas ganhou execução independente;
refresh/pending adicionais e expurgo de arquivos continuam sem ativação automática.
Pacotes parciais, volumes de ensaio e recibos não são descartados silenciosamente.

roles-prod.json e roles-prod.env são segredos. Não imprimir arquivos, Compose
resolvido ou inspect completo; não anexar ao CI. O dump não inclui roles
globais; recuperação completa precisa dessas credenciais e do provisionamento.
Hashes detectam corrupção, não autenticam o dump. Restaurar apenas pacotes próprios.

## Papéis

| Papel | Permissão |
|---|---|
| aulas_runtime / API | Leitura de catálogo e DML explícito de tabelas pessoais; sem DDL, TRUNCATE ou escrita editorial |
| aulas_worker | Leitura de jobs/tentativas/cues; atualização de jobs; volume de voz somente leitura |
| aulas_owner | Proprietário do schema/objetos; NOLOGIN |
| aulas_migrator | Login limitado, assume owner pelo driver para migrations/editorial explícito |
| aulas_backup | Leitura de tabelas e sequências; sem DML/DDL |
| Administrador anterior | Mantido para recuperação; não usado pela API/worker após rollout |

Guardas validam identidade SQL real e ausência de poderes globais. Novas tabelas
não ganham escrita automaticamente: migrations futuras precisam declarar grants.
Runtime não faz seed/migrations. Com papéis separados, make prod-up/prod-seed
recusam o fluxo antigo de iniciar código antes de atualizar schema.

## Ensaio e rollout

Primeiro, em ambientes sintéticos isolados:

    make roles-lab-up
    make roles-lab-prepare
    make test-roles
    make test-recovery
    make e2e-up
    make test-e2e

Operações proibidas são testadas apenas no laboratório de papéis, sem portas.
E2E usa somente 5198 e banco/voz próprios. Nenhum teste mutável toca contas reais.

Foi acrescentado um segundo destino vazio de restore:
aulas-ingles-recovery/study-check-db, volumes study_check_db/study_check_voice.
Não reutilizar/resetar destino ocupado. Prepará-lo com perfil study-check de
infra/compose.recovery.yml e verificar antes da janela.

> **Procedimento histórico, não executar para um rollout novo.** O comando
> `writing-rubrics` citado abaixo foi desativado na 40B.2c porque 63 das 82
> divergências mudam a avaliação. `ops.study_rollout` continua preservado como
> evidência da Sprint 37, mas não é o runbook vigente da Sprint 40. Use a seção
> 40B.2c e não tente contornar a recusa com SQL manual.

Construir imagens antes da manutenção e preservar IDs/imagens anteriores.
Na janela autorizada, parar apenas API/worker de produção local; banco fica ativo.
O backup recusa outros clientes SQL ou consumidores do volume de voz.

    docker stop aulas-prod-api aulas-prod-worker
    make backup source=prod
    make backup-verify f=PACOTE
    make restore f=PACOTE confirm=aulas-ingles-recovery/study-check-db
    uv run --project backend python -m ops.study_rollout capture --backup PACOTE
    uv run --project backend python -m ops.study_rollout rehearse --backup PACOTE

Substituir PACOTE pelo diretório exato retornado. O ensaio compara hashes de
todas as tabelas, preservando IDs, textos, checks e resultados antigos.
Exclui somente alembic_version, novos metadados de feedback e requirements de
writing_prompt — as alterações planejadas. Compara também inventário/checksums
de voz. Nenhum conteúdo privado é impresso. Migration e duas aplicações de
writing-rubrics rodam primeiro no clone sem provedor ou volume original.

Só depois do ensaio:

    uv run --project backend python -m ops.roles provision --scope prod --confirm aulas-ingles-prod --backup PACOTE
    uv run --project backend python -m ops.roles grants --scope prod --confirm aulas-ingles-prod --backup PACOTE

Ambos exigem manutenção, pacote verificado, recibo ligado ao hash do manifesto
e snapshot original inalterado. Grants vêm **antes** da migration; não relaxar
essa guarda para reaplicar sobre schema já alterado.

Usar o migrador com ambos os env-files e arquivos Compose:

    docker compose --env-file .env.prod --env-file backups/recovery/roles-prod.env -f infra/compose.prod.yml -f infra/compose.roles.prod.yml --profile tools run --rm --no-deps migrator alembic upgrade head
    docker compose --env-file .env.prod --env-file backups/recovery/roles-prod.env -f infra/compose.prod.yml -f infra/compose.roles.prod.yml --profile tools run --rm --no-deps migrator python -m app.cli writing-rubrics
    uv run --project backend python -m ops.study_rollout verify --backup PACOTE

Não rodar seed completo. A atualização dirigida valida todas as propostas antes
de alterar qualquer uma e recusa divergência editorial. Após a prova, subir as
imagens construídas usando o overlay, verificar health, catálogo, identidade real
SQL e worker. Não criar contas/tentativas artificiais no estudo para validar.

Com as imagens e migrations já conferidas:

    docker compose --env-file .env.prod --env-file backups/recovery/roles-prod.env -f infra/compose.prod.yml -f infra/compose.roles.prod.yml up -d --no-build --no-deps --wait --wait-timeout 90 api worker web

Para apenas retomar containers existentes depois de uma pausa de backup, sem
trocar imagem/configuração, usar docker start aulas-prod-api aulas-prod-worker.
Não executar esses comandos antes das verificações anteriores em um novo deploy.

Se falhar antes de alterações, iniciar containers anteriores. Depois da migration
aditiva, preservar banco e usar rollback de **aplicação**, nunca downgrade
destrutivo ou restore sobre origem. Imagens pré-rollout preservadas em tags
aulas-sprint37-rollback-{api,worker,web}:local; confirmar IDs antes de reutilizar.
Retornar ao aplicativo anterior exige configuração anterior controlada, sem
remover roles ou credenciais novas.

## Registro de execução

Em 13/10/2026, aproximadamente 23:25–23:28 BRT:
backup real pré-migration restaurado em study-check-db; fase de restore e
conferência em 3,939 s (não é RTO completo). Migration c95f3d8ba042 e 82
rubricas ensaiadas no clone e aplicadas na origem; 39 tabelas preservadas
nas provas privadas. Origem sem arquivos de voz pessoais; o teste de áudio
foi realizado com WAV sintético no ensaio anterior.

Pacote pré-migration:
aulas-20261014T022517321471Z-7eca236ddbbe4147b9593b518ec9eb10.
Pacote pós-migration, feito com aulas_backup:
aulas-20261014T022759607484Z-78514719cc3e48d8a2c4a4a1530ccf71.
Ambos íntegros; apenas o primeiro restaurado, seguido do ensaio de upgrade.
Recibos/provas e credenciais privadas permanecem em backups/recovery/.

API, health, catálogo e Aula 31 responderam 200 após reabertura; identidade
real limitada de API/worker conferida, worker sem root e voz somente leitura.
Desenvolvimento não foi reiniciado/migrado. Laboratórios encerrados sem
remover volumes. Não houve commit/push nem execução remota do CI.

## Limites residuais no fechamento da Sprint 37

- Homologação por professor pendente, separada do aceite técnico.
- Leitores de tela/dispositivos reais: FE-41.
- Refresh concorrente, revisões atômicas e conflitos de escrita: BE/FE/DB-38.
- Recuperação integral cronometrada, alertas, agendamento e gate: BE/DB-42.
  Aprovação técnica atual não declara RTO integral atingido.
- Clone de estudo contém dados reais; não é fixture para pytest/E2E. Manter
  sem portas e parar após o ensaio, preservando volumes protegidos.

## Sprint 38 — implantação autorizada em 14/10/2026

Jeferson autorizou alterar o ambiente de estudo e informou que seus dados são
apenas testes. A manutenção foi limitada a aulas-ingles-prod/localhost:5181.
Mesmo assim, dados, credenciais, backups anteriores e clones anteriores foram
preservados; não houve reset, seed completo, limpeza de contas nem alteração
do desenvolvimento em 5180. Pytest e E2E continuam proibidos nessas bases:
essa autorização não remove as guardas de isolamento da suíte.

### Preparação e execução

- Imagens anteriores de API/worker/web preservadas em
  aulas-sprint38-rollback-{api,worker,web}:local antes do build.
- Imagens novas construídas antes da interrupção. O helper de recuperação deve
  ser construído diretamente com backend/Dockerfile.prod, não retagado de uma
  imagem Compose: os rótulos herdados causam ambiguidade de serviço. A primeira
  tentativa foi recusada por essa guarda antes de capturar dados; o parcial foi
  preservado e o backup foi refeito com helper sem rótulos Compose.
- Novo destino autorizado de restore: aulas-ingles-recovery/concurrency-check-db,
  com concurrency_check_db/concurrency_check_voice próprios e rede interna sem
  portas. Os clones antigos não foram reutilizados nem apagados.
- API/worker pausados; backup consistente de banco + voz com aulas_backup,
  checksums e manifesto. Restauração no destino vazio comprovou referências e
  inventário; fase de restore/conferência levou 4,418 segundos. Não é RTO integral.
- ops/concurrency_rollout.py capturou hashes privados das 39 tabelas históricas,
  ensaiou a migration d06a4e9cb153 duas vezes no clone e conferiu preservação.
  Não exclui requirements/rubricas/textos das comparações: ignora somente colunas
  realmente novas da Sprint 38. Também exige recibos/contadores novos vazios,
  revisões iniciais zero e famílias iniciais iguais ao jti conhecido.
- Migration aplicada na origem com aulas_migrator assumindo aulas_owner; grants
  das tabelas novas fornecidos pela migration. Papéis/senhas não foram recriados.
  Prova posterior confirmou os mesmos hashes e inventário de voz na origem.
- Backup pós-migration criado ainda em manutenção, antes da troca dos containers.
  Seu manifesto registra corretamente as imagens antigas então paradas; o schema
  já é d06a4e9cb153. Para reabrir esse schema é necessário código da Sprint 38.
- API/worker/web reabertos com as imagens novas. Página, live, health, catálogo
  e Aula 31 responderam 200; HTML servido conferido com o container.
  Conexões SQL reais confirmaram aulas_runtime/aulas_worker, sem poderes globais.
  Runtime pode inserir/ler recibos, mas não atualizá-los/excluí-los diretamente;
  worker não pode ler os contadores de autenticação.

### Preservação do legado, sem aceite fictício

A auditoria anterior à manutenção passou em 20 de 22 regras. Encontrou:

- 20 jornadas com 86 etapas declaradas sem linha detalhada em StepProgress;
- 15 jornadas com as cinco etapas declaradas, mas sem completed_at;
- nenhuma referência cruzada de proprietário, origem polimórfica órfã ou demais
  violações verificadas pela auditoria.

Foi apresentada a escolha de preservar ou reconciliar. Sem decisão específica
para reescrever o histórico, adotou-se a opção conservadora anunciada: preservá-lo.
**Não foram inventadas datas nem alteradas conclusões.** Reconciliação permanece
pendente; essas duas regras não são declaradas aprovadas.

A flag explícita --preserve-legacy-journeys documenta a exceção no recibo privado;
permite somente aquelas duas regras e exige contagens idênticas antes/depois,
além dos hashes de todas as linhas históricas. Não é uma liberação genérica
para ignorar a auditoria. Sem a flag, qualquer contagem não zero é recusada.
Outras violações, mudança nas contagens ou no conteúdo bloqueiam a verificação.

### Pacotes e evidências

Pré-migration, restaurado e ensaiado:
aulas-20261014T035315064416Z-b2e4d5ccf76f4b528d9b2932fb216bc2.

Pós-migration, integridade verificada, sem segundo restore:
aulas-20261014T035519894349Z-37b1cceddc3f4378850e7b3f1159f8f7.

Ambos em backups/recovery/ privado, ignorado pelo Git. Voz pessoal: zero arquivos
nessa captura; não se apresenta esse restore como novo ensaio de áudio não vazio.
Recibos: restore-receipts/ e sprint38-{capture,rehearse,verify}-<bundle>.json.
Foram aprovados 47 testes operacionais e Ruff; configurações Compose e sintaxe YAML
validadas. Regressões de produto anteriores à implantação: 789 backend, 270 frontend,
106 E2E em ambientes isolados. Não se repetiu a suíte na base de estudo.

### Limites e próxima manutenção

O clone ficou preservado e parado, sem portas; não é destino vazio para um novo
restore. Uma manutenção futura precisa de destino novo explicitamente validado,
não de apagar esse volume ou relaxar a guarda. study_rollout.py permanece preso
à revisão da Sprint 37; concurrency_rollout.py aceita somente c95f3d8ba042 como
origem e d06a4e9cb153 como destino. Não usar esses scripts como migração genérica.

Após a migration, **não basta voltar à API da Sprint 37**: ela não preenche o novo
family_id obrigatório de refresh. As imagens antigas estão preservadas para
recuperação controlada, não são um rollback de aplicação já homologado nesse schema.
Se necessário, manter origem intacta, restaurar o backup pré-migration em outra
base vazia e planejar a troca de configuração/imagens; nunca downgrade destrutivo
nem restore por cima da origem. Essa troca completa não foi ensaiada como RTO.

Continuam pendentes: reconciliação das jornadas legadas, homologações humanas de
escrita/leitores de tela, CI remoto e cópia externa/agendamento de backup. Não houve
commit ou push nesta manutenção.

## Sprint 39A — alinhamento autorizado do desenvolvimento em 14/10/2026

### Escopo e resultado

Autorização: resposta “pode seguir” à proposta de alinhar o banco dev após backup.
Alvo exclusivo: projeto Docker `aulas-ingles`, web 5180, API 8010 e PostgreSQL 5433.
O ambiente `aulas-ingles-prod`/5181/5434 não foi parado, migrado ou recriado; os IDs
e horários de início dos quatro containers foram conferidos antes/depois e permaneceram
iguais. Estudo continua em `d06a4e9cb153` (Sprint 38).

Desenvolvimento passou de `b84e2c7a9d31` para `e17b5fad0264`, com as migrations aditivas
37, 38 e 39A. Pausa explícita somente de `aulas-web`, `aulas-api` e `aulas-worker`;
o primeiro pedido de backup foi corretamente recusado enquanto o worker terminava.
Backup só foi publicado após ausência de clientes SQL e consumidores do volume de voz.
Os três serviços foram reabertos depois da prova de preservação. Não houve seed,
backfill editorial, reparo automático, alteração de papéis ou remoção de volume.

### Backup e ensaio

Pacote pré-migration, privado no Mac, ignorado pelo Git/builds:

    backups/recovery/aulas-20261014T214342395633Z-315840e6900a4d1caf6c6dc3a20a494c

Contém dump custom PostgreSQL, arquivo de voz e manifesto com checksums. Diretório
700, arquivos 600; isso é controle de acesso local, **não criptografia nem cópia externa**.
Nenhum texto pessoal, token, hash de senha ou credencial foi exposto nos logs/MD.

Novo destino: `aulas-ingles-recovery/dev-check-db`, sem portas publicadas, rede interna,
volumes novos `aulas-ingles-recovery_dev_check_db` e `aulas-ingles-recovery_dev_check_voice`.
Restore recusaria um destino não vazio. O clone não recebeu rede ou mounts da origem.

`ops/recovery.py` agora aceita `--source dev`; valida projeto, banco, porta loopback
5433, volumes, redes, `APP_ENV=dev` e quiescência. Os destinos de restore continuam
exclusivamente descartáveis; não existe restore autorizado sobre dev ou estudo.

`ops/dev_alignment.py` implementa `capture`, `rehearse` e `apply`, limitado à origem
dev em `b84e2c7a9d31` e ao destino `e17b5fad0264`. Aplicação exige recibo do restore
no clone dedicado e do ensaio da mesma imagem por ID e mesmo manifesto. Mudança de
conteúdo, backup, imagem, origem ou revisão bloqueia a operação. O migrador usa somente
a rede do alvo, sem montar dados/voz, com providers desabilitados e sem seed.

Sequência executada: backup → capture → restore no clone → rehearse → apply em dev.
No clone e no dev, `alembic upgrade e17b5fad0264` foi executado duas vezes; a segunda
não aplicou alterações. `alembic check` passou nos dois destinos. Comparação de hashes
de todas as colunas históricas demonstrou preservação das **39 tabelas e 6.766 registros**.
Somente colunas/tabelas adicionadas pelas três migrations ficaram fora desse hash;
seus defaults e ausência de histórico fabricado foram conferidos separadamente.

Recibos privados:

- `restore-receipts/<bundle>.json`: restore do par banco/voz.
- `dev39-<bundle>-capture.json`: hashes/contagens, imagem e auditoria inicial.
- `dev39-<bundle>-rehearse.json`: ensaio aprovado no clone.
- `dev39-<bundle>-apply.json`: aplicação e preservação aprovadas no desenvolvimento.

A base dev tinha **82 aulas, zero usuários e zero arquivos de voz**. Auditoria das
22 regras não encontrou violações antes/depois. Esse restore não prova restauração de
áudio não vazio, e não elimina as divergências legadas existentes no ambiente de estudo.

### Verificação após reabertura

Via HTTP real pelo proxy de `http://127.0.0.1:5180`, passaram **23 verificações**:
readiness, cadastro/login/refresh/logout, catálogo, aula 31, CAS/idempotência de posição,
rejeição 409 de escrita atrasada, conclusão/tombstone, âncora e evento ativo idempotente,
plano em `America/Sao_Paulo`, painel Hoje e exportação 1.6. O deep link da jornada
também entregou o HTML do frontend. Não houve chamada ao MP3 da VOA ou provider assistido.

Foi criada uma única conta sintética com identidade aleatória, removida ao final por
filtro exato; suas sessões, posição e eventos foram removidos por cascade. Após isso,
as 39 tabelas históricas voltaram a corresponder integralmente ao backup, com zero
usuários. Buckets novos de rate limit gerados pelo smoke não foram apagados em massa.
Contas de estudo não foram copiadas para o desenvolvimento.

Nesta manutenção: **63 testes operacionais** aprovados, Ruff com configuração do
backend, sintaxe Compose e `git diff --check`. As regressões de produto aprovadas no
incremento anterior continuam como evidência (802 backend, 289 frontend, 112 E2E,
50 guardas E2E); não foram reaplicadas à base dev nem à de estudo. O smoke HTTP não
substitui homologação visual, leitores de tela, dispositivos ou microfone reais.

### Estado final e limites

Dev 5180/8010 ativo no head `e17b5fad0264`. Clone dev-check parado, volumes preservados;
não pode ser reutilizado como destino vazio. Backup e provas permanecem no Mac.
Não houve commit/push/merge. Sprint 39 continua aberta para upload/microfone,
PWA/cache, cotas assistidas, liberação de conexões durante provider, resiliência/expiração
de jobs e retenção/reconciliação de arquivos.

O script não é um migrador genérico: uma nova manutenção ou implantação em 5181 exige
origem/destino/ensaio próprios. Não fazer downgrade destrutivo ou restore por cima da
origem. A recuperação completa com troca de configuração não foi medida como RTO;
esta execução não declara atingidas as metas operacionais nem fecha a Sprint 39.

## Sprint 39C — atualização da API dev sem alteração de dados em 14/10/2026

Adicionada dependência PyAV 19.0.1 no projeto, fixada em `pyproject.toml`/`uv.lock`.
Foi reconstruído **somente** o serviço `api` de `infra/compose.yml`, com
`--no-deps --build --wait`, após ensaio na stack E2E. Não foi executado `make up`,
migration, seed, limpeza, restore ou reprovisionamento de papéis nesta entrega.
Worker/web/banco de desenvolvimento não foram recriados por esse comando.
Ambiente de estudo em 5181 não foi alterado; seu schema continua na Sprint 38.

Readiness e política pelo proxy 5180 confirmaram dev saudável e
`content_validation=decoded_audio_v1`. No Linux, usando UID sem privilégios,
cinco amostras de silêncio em memória passaram: WAV, WebM/Opus, Ogg/Opus,
MP4/AAC e MP3 (1.000–1.001 ms medidos). Nenhuma conta ou arquivo de voz foi criado
por essa verificação. No Mac, a dependência ficou restrita ao ambiente virtual
do projeto; nenhum FFmpeg global foi instalado.

Inventário seguro:

```bash
docker compose --env-file .env -f infra/compose.yml exec -T api python -m app.audio_audit --dry-run
```

Execução dev: `complete=true`, zero referências e zero arquivos, sem achados.
Ensaio E2E: 42 referências/26 arquivos, todos os arquivos protegidos como recentes.
Esses números são snapshots dessas execuções, não uma promessa de estado futuro.
O comando não possui apply/delete e nunca exclui/move arquivos ou muda registros.
Relatório contém chaves de storage e IDs: mantê-lo privado, não publicar em CI.
Snapshot SQL é read-only; hashing ocorre após devolver a conexão.

O prazo mínimo de 24 h só protege candidatos recentes; não define retenção. Relatório
não autoriza remoção posterior sem revalidar banco/storage/uploads ativos. Não houve
quarentena ou expurgo. Hash observado não substitui baseline persistente nem prova de
restauração. Os procedimentos de rollout 37/38 não foram ampliados para instalar 39.
Não houve commit/push/merge; recuperação após crash, PWA, cotas e manutenção de jobs
continuam abertas na Sprint 39.

Regressão final: 850 testes backend (93,62% de cobertura), 308 frontend e
120 E2E em 6,4 min; também passaram 63 testes operacionais e 50 guardas E2E.
Ao terminar, `make e2e-down` validou o isolamento e removeu somente os containers
e a rede do laboratório; seus volumes sintéticos foram preservados. Desenvolvimento
e ambiente de estudo permaneceram em execução.

## Sprint 39D — quarentena reversível e backup v2 em 14/10/2026

Entrega de código operacional, sem ação sobre áudios reais. Não foi feita migration,
seed, modificação de papéis ou SQL mutável em dev/estudo. O código backend está no
bind mount do desenvolvimento; **5181 continua na Sprint 38**. Não houve commit/push/merge.

Antes de qualquer movimentação futura, conferir o par banco/volume configurado e
guardar backup verificável na janela de manutenção apropriada. Os nomes confirmados
não comprovam identidade de cluster ou montagem: não trocar `DATABASE_URL`/storage
para contornar recusas. Configuração `APP_ENV=prod` é recusada; não trocar para dev
como atalho de implantação. Operação requer dono do diretório/arquivos e privilégios
para lock da tabela; nenhum grant novo foi concedido.

Fluxo manual para **desenvolvimento confirmado**, no mesmo ambiente da API:

1. Rodar `python -m app.audio_audit --dry-run` e revisar o relatório. Ele não move nada.
2. Escolher uma chave candidata conhecida, conferir checksum, origem e idade. Registrar
   um ID de operação novo com 32 caracteres hexadecimais antes da chamada; se a resposta
   se perder, usar esse mesmo ID para retomar, não gerar outro.
3. Substituir os placeholders abaixo por valores realmente verificados. O comando não
   aceita curingas, vários arquivos, idade forçada ou exclusão definitiva.

```bash
python -m app.audio_quarantine quarantine \
  --operation '<id-de-operacao-32-hex>' \
  --key '<chave-validada-do-audio>' \
  --sha256 '<checksum-validado-64-hex>' \
  --confirm-storage /app/data/speaking \
  --confirm-database aulas_ingles
```

Para retomar uma operação interrompida ou devolver seus bytes, respectivamente:

```bash
python -m app.audio_quarantine resume \
  --operation '<mesmo-id-de-operacao>' \
  --confirm-storage /app/data/speaking --confirm-database aulas_ingles

python -m app.audio_quarantine restore \
  --operation '<mesmo-id-de-operacao>' \
  --confirm-storage /app/data/speaking --confirm-database aulas_ingles
```

Resultados/recusas:

- `quarantined`: bytes preservados em `.quarantine/<operação>/audio`; o nome original
  foi retirado, **sem eliminar a cópia**. `restored`: bytes devolvidos à chave original.
  O journal é conservado, com tamanho/checksum/identidade, sem transcrição ou usuário.
- `referenced_file_protected`: qualquer referência atual protege o arquivo; não
  alterar SQL para contornar. `recent_file_protected`: aguardar a janela de segurança
  real, sem retrodatá-la. Temp/links/conteúdo alterado também não são recolhidos.
- Conflito de lock ou `operation_unavailable`: saída 2, sem promessa de conclusão.
  Verificar o journal privado e repetir `resume` com o ID conhecido. Não publicar
  stdout do inventário/journal em CI público: IDs/chaves continuam metadados privados.
- Journal parcial, checksum diferente, destino ocupado, inode divergente ou ausência
  de ambas as cópias exigem revisão manual. Preservar artefatos; não tentar "reparar"
  apagando journal ou sobrescrevendo destino. Sem journal válido não há movimento de
  áudio autorizado; um diretório de operação vazio pode restar antes dessa etapa.
- A restauração só devolve arquivos conhecidos; não associa órfão a `pending`, recria
  tentativa ou evidência nem recupera gravação perdida da memória do navegador.

O lock SQL `EXCLUSIVE NOWAIT` conflita com `FOR UPDATE`/DML e permite SELECT comum.
Mantém-se durante uma única operação de até 2.000.000 bytes, com orçamento cooperativo
de filesystem de 5 s e statement timeout SQL de 5 s. Isso não limita rigidamente um
disco travado. `flock` serializa operadores no diretório. A implementação pressupõe
filesystem local com link/fsync/flock; não homologa NFS, múltiplos hosts nem escritores
externos privilegiados. Falha de conexão/transação não desfaz arquivo: journal e cópias
determinam retomada segura. Não há transação distribuída ou expurgo automático.

Backup conjunto **v2** inclui os três caminhos reservados por operação (`audio`,
`record.json`, `restore.json`). Novas ferramentas leem v1; ferramentas antigas não
devem receber pacotes v2. Pacote conserva bytes mesmo no intervalo com dois hardlinks,
exportando cada nome como arquivo regular. Contagem de entradas de quarentena é
separada de órfãos. Não interpreta journal de backup como autorização de ação.
Restore para volume novo altera inodes/device: retomar mutação exige revisão manual,
mesmo quando checksums estão íntegros. Pacotes/volumes antigos não foram regravados.

Ensaios usam arquivos sintéticos e PostgreSQL descartável 55435. Seis interrupções
de processo reais cobrem journal/link/unlink tanto na ida quanto na restauração.
Transportador de voz exportado/importado em diretórios temporários, com preservação
de bytes/journals e recusa de traversal/links inesperados. **Não** foi feito novo
dump/restore real do banco de estudo, teste de queda de energia ou medição RPO/RTO.
PWA, cotas/reservas, jobs, retenção e rollout continuam pendentes na Sprint 39.

Validação final 39D: **893 testes backend em 115,21 s**, cobertura **93,69%**
(piso de 90% preservado), Ruff/mypy aprovados; **72 testes operacionais**;
**8 E2E de upload em 19,9 s** em desktop/mobile simulados. Container Linux
descartável sem rede/volumes de dados, raiz somente leitura e UID 10001 aprovou
**33 testes puros de quarentena**, incluindo as seis interrupções de processo.
Uma fixture de ctime foi tornada determinística após diferença de resolução temporal
no Linux; as verificações de proteção do produto não foram relaxadas.

`make e2e-down` encerrou apenas os containers/rede E2E após validar isolamento;
volumes sintéticos preservados. Nenhum áudio real foi movido/excluído. As suítes
frontend completa e 120 E2E não foram repetidas em 39D; não confundir com 39C.

## Sprint 39E — PWA e cache público em 14/10/2026

Escopo: continuidade offline e atualização segura em build. Sem rollout em 5181,
sem migration/seed nas bases de desenvolvimento/estudo e sem commit/push/merge.
O Vite 5180 não registra `/sw.js`; validação do worker exige build servido em
origem segura (localhost é permitido). Não desativar o overlay ou limpar dados
do navegador para esconder falhas de instalação/armazenamento.

### Operação pelo aluno

1. Abra a aula com conexão. Expanda **Offline e atualizações**; verifique se o
   **texto desta aula** está armazenado e sua validade. Se necessário, use
   **Verificar disponibilidade e versão**. Essa leitura é uma fotografia do cache,
   não garantia permanente contra desalojamento pelo navegador.
2. Texto e telas já carregadas podem funcionar offline; áudio/vídeo continuam
   online. Dados privados da API não são cacheados. A fila de exercícios continua
   separada e não recebe gravações de voz automaticamente.
3. Ao aparecer **Atualização disponível**, salve/copie textos e envie ou baixe
   gravações ainda locais. Feche **todas** as abas/janelas do aplicativo, inclusive
   PWA instalado, e abra novamente. Atualizar uma aba mantendo outra aberta não
   força a ativação. A interface não recarrega nem apaga rascunhos/fila.
4. Após ativar a nova versão, abra novamente as aulas com conexão para popular o
   cache editorial dessa release. Não use a troca de versão como backup offline.
5. **Limpar somente textos públicos** requer confirmação e remove somente o cache
   editorial atual. Consultas online podem preenchê-lo novamente. Não toca em
   shell/assets, localStorage, IndexedDB, gravações, sessão ou dados remotos.

### Contrato técnico e limites

- Build gera release determinística por SHA-256 e lista fechada de assets. Apenas
  entrada/imports estáticos/CSS são pré-carregados; aula/laboratório continuam lazy.
  Instalação valida SHA-256 do HTML e tem abort de rede após 30 s; não aceita shell
  misturado com outro build. O prazo não é garantia contra filesystem travado.
- `sw.js` recebe `no-cache, must-revalidate`, registro usa `updateViaCache: none`.
  Não há `skipWaiting`, reload automático nem comando para forçar troca sobre abas
  abertas. Ativação apaga apenas caches de versões reconhecidas deste aplicativo.
- TTL/poda executados no acesso: shell 3 itens/1 MiB/30 dias; assets 64/8 MiB/30 dias;
  texto 120/8 MiB/7 dias. Por item: shell/texto 512 KiB, assets 2 MiB. Bytes medidos
  são os corpos, sem overhead do navegador. Escritas/podas são serializadas e
  corpo é lido com limite, mesmo sem Content-Length. Limites são **por release**;
  caches antigos/candidatos podem coexistir até a ativação segura, sem cota global.
- Só GET editorial allowlisted com JSON 200, marcador `X-Aulas-Offline: public-text-v1`
  e sem `private/no-store` ou `Vary` privado entra no cache. Fetch editorial é anônimo
  e cache usa chaves novas sem headers de autenticação. API privada, mídia, mutações
  e origens externas não são interceptadas. Erros de quota preservam resposta online.
- Consulta editorial tem abort após 6 s e fallback somente a texto não expirado;
  5xx admite fallback, mas 4xx e resposta sem autorização de cache removem a cópia
  antiga. Sem cópia, erro 503 explicável. Navegações compartilham um único shell;
  nenhum histórico de URLs individuais é guardado em CacheStorage.
- Workers antigos não são reescritos no navegador. Rollout futuro exige informar
  o fechamento das abas antigas; alterações de frontend/backend devem ser entregues
  juntas. Não remover CacheStorage/localStorage/IndexedDB globalmente para atualizar.
  O servidor atual não retém assets de todos os builds antigos: uma tela lazy nunca
  visitada por uma aba antiga pode exigir atualização após deploy. Não confundir
  preservação da aba/rascunho com garantia de carregar qualquer rota antiga.

### Ensaios isolados

```bash
make test-api-prepare
cd backend && uv run pytest -q --cov --cov-report=term
cd ../frontend && npm run lint && npm run typecheck && npm test
npm run build && npm run check:budget
cd ../e2e && npm run test:pwa
cd .. && make e2e-up
cd e2e && npm test
cd .. && make e2e-down
```

`test:pwa` inicia servidor sintético exclusivo em 127.0.0.1:5196, sem proxy, conta,
banco ou `.env` de estudo. Exercita duas releases/duas abas, armazenamento sintético
preservado e instalação divergente recusada com versão anterior offline. Relatórios
em `e2e/pwa-test-results/`, separados do E2E principal em `e2e/test-results/`.
O job frontend do CI inclui esse ensaio após a fila isolada; configuração alterada
localmente, **sem execução do GitHub Actions nesta entrega**.

Validação de unidade/build: **912 testes backend / 93,70% de cobertura** (188,32 s),
Ruff e mypy aprovados; **334 testes frontend**, ESLint, TypeScript e build aprovados.
Budget original de assets JS/CSS preservado: **174.304 bytes gzip (170,2 KiB)**,
abaixo de 176.128 bytes. Worker é medido separadamente: 9.649 bytes de arquivo,
3.464 bytes gzip; não está incluído no orçamento histórico de assets. Release
`8bcb9637cf1697dd`, hash do HTML conferido e sem placeholders no worker gerado.

Os **2 ensaios de ciclo PWA** passaram (2,6 s) e os **4 novos E2E** de interface
passaram (13,7 s) no build final. Capturas desktop/mobile foram inspecionadas. A
primeira regressão integrada teve 119 aprovações e uma falha de infraestrutura
`ENOENT` ao fechar trace: dois runners usavam o mesmo diretório. O ensaio PWA agora
tem saída própria; esse resultado inicial não é tratado como suíte integral aprovada.
Repetição integral no build final: **124 E2E aprovados em 6,2 minutos**, Chromium
desktop e mobile simulado, sem falhas. Inclui os quatro cenários novos, teclado,
reflow, axe, fila entre abas, escrita, áudio/upload e tempo ativo. Os dois ensaios
de lifecycle PWA são adicionais, não estão somados nesses 124. Nenhuma dessas
emulações substitui homologação de dispositivo/leitor de tela real.

Consultas somente leitura a health em 5180/5181 retornaram HTTP 200; worker em 5198
retornou `Cache-Control: no-cache, must-revalidate`. Nenhum serviço de estudo foi
recriado e nenhum dado pessoal foi excluído. `make e2e-down` encerrou somente os
containers/rede descartáveis, preservando volumes sintéticos. Nova conferência de
health em 5180/5181 após esse encerramento retornou HTTP 200. Leitores de
tela, Safari/iOS e dispositivos reais não foram homologados. Reservas/cotas de
assistência, jobs/retenção, checksum durável de voz e rollout seguem pendentes;
**não marcar a Sprint 39 inteira como concluída**.

## Sprint 39F — reservas e cotas assistidas em 14/10/2026

Escopo: admissão concorrente de escrita/transcrição, reenvio idempotente da escrita,
registro de consumo independente do resultado e interface de saldo. Não encerra
BE/FE/DB-39, não habilita provedores e não inclui rollout em dev/estudo.

### Política operacional

| Situação | Unidade local | Custo |
| --- | --- | --- |
| Pedido admitido, ainda não despachado | Reservada | Não inferido |
| Reserva não iniciada vencida (padrão 900 s) | Deixa de ocupar o saldo | Não inferido |
| Cancelamento/exclusão antes de despachar | Liberada | Nenhum custo confirmado |
| Despacho autorizado e confirmado no banco | Consumida no dia UTC da reserva | Pode permanecer desconhecido |
| Timeout, falha ou crash após esse marco | Continua consumida | Não pressupor gratuidade |
| Retry do mesmo job / replay da mesma escrita | Mesma unidade | Chave estável; fornecedor precisa honrar idempotência |
| Exclusão do resultado depois do despacho | Continua consumida | Ledger preservado |

Não há atomicidade entre commit SQL e serviço externo: crash entre autorização e
chamada pode consumir uma unidade sem enviar. A escolha é conservadora e evita
reembolso por timeout que permitiria ultrapassar a cota. Cota local não é cobrança
financeira. Para Ollama, custo reportado zero significa taxa de provedor, não custo
de energia/hardware. Gateway sem inteiro não negativo válido em `cost_microusd`
mantém custo desconhecido; `cost_incomplete` evita apresentar o total como completo.
Custos referem-se às operações reservadas naquele dia, não à data do retorno da rede.

API não segura conexão enquanto espera o provedor. Admissão usa lock na conta e
nas reservas relevantes, inclusive para aguardar despacho que ainda esteja em
transação ao vencer o TTL. Worker não recebe acesso a `app_user`; usa lock no job
e na reserva. Cancelamento respeita essa ordem e nunca reabre consumo confirmado.

Escrita assistida admitida: `operation_key` UUID opcional, conta/chave única e fingerprint do texto,
proposta e versão da rubrica/algoritmo. Replay devolve feedback persistido; se ainda
não houver resultado (inclusive crash), 409 sem novo despacho. Chave com conteúdo
diferente é conflito. Frontend conserva a chave após falha de rede na mesma tela;
não a persiste após reload. Cliente antigo sem chave cria nova operação. Não há
retry automático de uma escrita com resultado incerto nem promessa de exactly-once
num fornecedor que ignore o header. Correção local continua disponível.
Análises puramente locais e recusas antes da admissão não recebem essa deduplicação.

Transcrição: pedidos simultâneos da mesma tentativa retornam o mesmo job. Retry
mantém reserva e chave do gateway. Áudio/reserva ausente ou expirada barra o despacho.
Job vencido não chama provedor; neste incremento ainda pode ser reivindicado antes
de ser marcado como falha. Expiração em lote, leituras/exportações e recuperação de
indisponibilidade do banco continuam em 39G. Nenhum transcript apagado é recriado
por resposta tardia; seu custo reportado pode ser registrado na reserva sobrevivente.

### Migration, dados e permissões

`f28c6abe1375` sucede `e17b5fad0264`. Expansão aditiva: `assist_reservation` e FKs
nullable/únicas de job/feedback. Sem texto/áudio/token no ledger. Backfill conserva
resultados legados observáveis como `consumed/legacy_observed`, mantendo datas e
chave já usada por jobs. Não inventa despacho, nem recupera resultados anteriormente
apagados. Zero legado não distingue gratuidade de custo ausente e fica desconhecido.
Jobs legados ainda na fila são conservadoramente consumidos, sem reembolso ao apagar.

Apagar job/feedback não apaga reserva. Excluir a conta apaga seu ledger por cascata;
isso é decisão explícita de encerramento da identidade, não defesa contra múltiplas
contas. Sem purge histórico neste bloco: permanece até exclusão da conta ou operação
owner aprovada. Definir retenção e tombstones de deduplicação em 39G, sem presumir
prazo jurídico. `ASSIST_RETENTION_DAYS` não governa este ledger.

Runtime: SELECT/INSERT/UPDATE + sequence; worker: SELECT/UPDATE; ambos sem DELETE
direto. Migration concede privilégios no perfil owner e `roles_policy.sql` pode
reaplicá-los no laboratório. O smoke executa reserva/consumo real com os dois papéis
e **39 recusas de privilégio**, além de HTTP runtime e dump com papel de backup.

### Situação da implantação em 14/10/2026

Registro histórico: a pendência de DEV descrita abaixo foi resolvida em
[15/10/2026](#sprint-39f--alinhamento-do-desenvolvimento-em-15102026). O estudo
continua sem rollout da Sprint 39.

Não foi aplicado `f28c6abe1375` em 5433/5434. O Vite/API de 5180 têm bind mounts e
hot reload: código local novo **não significa schema compatível**. Escrita, voz,
histórico/exportação que selecionam esses modelos e assistência precisam da nova
migration. Health 200 confirma conectividade, não essas tabelas. 5181 mantém imagem
da Sprint 38 e não foi recriado. Não anunciar 39F disponível nesses ambientes.

Próximo passo operacional, antes de testar 39F em 5180:

1. Conferir alvo dev e revisão; pausar API/worker para não admitir chamadas durante
   backfill. Nenhum writer antigo pode continuar contornando a reserva.
2. Backup local privado de banco/voz, verificar e restaurar em clone isolado.
3. Ensaiar upgrade, comparando IDs/contagens/fingerprints históricos e backfill;
   smoke com a mesma imagem e papéis. Não rodar seed como correção de schema.
4. Aplicar somente após ensaio e atualizar API/worker juntos; conferir schema e
   chamadas autenticadas, não apenas health. Se falhar, manter manutenção e backup;
   não apagar ledger/downgrade nem restaurar in-place por impulso.
5. Ferramentas antigas de rollout têm revisão alvo fixa: não usar
   `ops.dev_alignment` (b84 → e17) para pular diretamente a 39F. Preparar fluxo
   equivalente específico e testado. Implantação em estudo permanece separada.

### Ensaios e limites

Testes de integração usam PostgreSQL descartável 55435. Migration/backfill também
rodam numa transação/schema sintético com rollback e teste de recusa de downgrade.
`alembic check` sob a guarda de teste não detectou divergências entre modelos e DB.
Não há fixture de dados reais nem gateway/Ollama real nesses testes.

Os testes novos cobrem oito pedidos simultâneos com cotas três/cinco, concorrência
de modalidade, cancelamento, replay/409, exclusão durante e após provedor, falha
com consumo, reserva vencida, áudio ausente, virada UTC e custo desconhecido.
Um teste mantém despacho sem commit e avança o relógio além do TTL: nova admissão
precisa esperar o lock e depois recusar cota, não observar estado MVCC vencido.

Interface em Chromium desktop/mobile simulado verifica Enter, mesma chave no
retry, preservação do texto e saldo/custo parcial com respostas interceptadas;
isso não substitui os testes reais de concorrência. Sem homologação adicional em
VoiceOver/TalkBack, Safari/iOS, contraste Windows real ou revisão pedagógica humana.

Referências: [locks PostgreSQL](https://www.postgresql.org/docs/current/explicit-locking.html)
e [limites transacionais/commit da Session](https://docs.sqlalchemy.org/en/20/orm/session_basics.html).

Validação frontend: **336 testes**, ESLint/TypeScript/build aprovados, orçamento
original preservado (**175.067 bytes gzip de JS/CSS**, teto 176.128). **126 E2E**
aprovados em **7,6 min**, incluindo dois cenários novos de assistência com mock;
os **2 ensaios de lifecycle PWA** também passaram (2,7 s) com saída independente.
**72 testes operacionais / 50 subtestes** passaram. Ruff/mypy/OpenAPI alinhados.

Houve uma falha intermediária no smoke operacional de papéis após rebuild; não
foi atribuída uma causa sem evidência. A repetição instrumentada por fase passou
com a imagem final: migrator, HTTP runtime, reserva/consumo runtime, consumo worker,
claim e dump limitado, além das 39 recusas. A primeira tentativa de build E2E
também não é evidência de aprovação; a execução acima usa rebuild posterior válido.
Não foi executado GitHub Actions nem foi feito commit/push/merge.

Consulta read-only confirmou dev em `e17b5fad0264`, sem `assist_reservation`.
Health 5180/5181 retornou 200; isso **não valida escrita/voz do dev com código 39F**.

Regressão final do código backend: **937 testes aprovados em 356,29 s**, cobertura
**93,79%** (piso 90%), Ruff e mypy aprovados. OpenAPI confere exatamente com o
schema gerado da aplicação. O backfill final é ensaiado transacionalmente pelo
teste de migration; não se tentou reaplicar migration já carimbada nos laboratórios.

Comandos principais usados nesta validação:

```bash
make test-api-prepare
cd backend && uv run pytest -q --cov --cov-report=term --cov-fail-under=90
uv run ruff check . && uv run mypy app
cd ../frontend && npm run lint && npm run typecheck && npm test
npm run build && npm run check:budget
cd .. && make roles-lab-up && make roles-lab-prepare && make test-roles
make e2e-up
cd e2e && npm test
npm run test:pwa
cd .. && make e2e-down && make roles-lab-down
```

Os containers/redes E2E e de papéis foram encerrados, **preservando os volumes
sintéticos**. A base 55435 usada pelo pytest foi mantida. Nenhum serviço de estudo
foi recriado, nenhum banco real migrado/semeado e nenhum arquivo de voz real apagado.
Próxima prioridade: preparar alinhamento seguro de 5180 para a nova migration;
em seguida continuar 39G (jobs/retenção), sem declarar a Sprint 39 inteira encerrada.

## Sprint 39F — alinhamento do desenvolvimento em 15/10/2026

Concluído o alinhamento de **DEV 5180/8010/5433** após a autorização de continuidade.
Revisão `e17b5fad0264` → `f28c6abe1375`. API e worker foram reconstruídos/recriados
juntos e o frontend foi reaberto somente depois da conferência final. Não houve
seed, downgrade, restauração sobre a origem nem alteração de usuários/permissões
existentes. Configuração preservada; o parâmetro de reserva usa 900 segundos.

### Backup, ensaio e preservação

- Backup local privado: `backups/recovery/aulas-20261015T134601180520Z-3957a7e1392641f182b58bf17d258fb8`.
- Pacote completo de banco/voz, manifesto e checksums verificados; restore no
  **novo** `aulas-ingles-recovery/assist-check-db`, vazio e sem portas publicadas.
  Os clones e volumes antigos não foram sobrescritos.
- A imagem do migrador foi fixada pelo ID imutável nos recibos. Upgrade repetido
  e `alembic check` aprovados no clone e no DEV; sem drift.
- **44 tabelas históricas, 6.768 linhas, 82 aulas** preservadas por contagens e
  fingerprints por tabela. Somente `assist_reservation` e as duas novas FKs são
  excluídas dessa comparação; eventos/colunas da 39A–39E também foram comparados.
- A origem tinha zero usuários, feedbacks de escrita, jobs e arquivos de voz.
  Backfill real com zero reservas aprovado; não representa teste com legado
  não vazio. Esse caso foi revalidado no PostgreSQL sintético 55435.
- Backfill conferido por comparação bidirecional entre legado e ledger, incluindo
  vínculos, datas, custos conhecidos/desconhecidos e ausência de despacho inventado.
- Contas sintéticas dos smokes excluídas por **ID e e-mail exatos** com suas cascatas;
  nenhum DELETE amplo. Depois, a origem foi novamente parada e todos os
  fingerprints/voz reconferidos. Sequências podem avançar por essas inserções;
  preservação de dados não significa igualdade byte a byte do arquivo PostgreSQL.

Recibos privados em `backups/recovery/`: `dev39f-<bundle>-capture.json`,
`-rehearse.json`, `-smoke.json`, `-apply.json`, além de
`dev39f-http-dev-20261015.json` e `dev39f-preservation-final-20261015.json`.
Não versionar dumps, manifestos ou recibos privados. A cópia permanece somente no
Mac, conforme decisão anterior; não é proteção contra perda do equipamento nem
nova aprovação de RPO/RTO/backup externo.

### Verificações desta entrega

- **83 testes operacionais** e lint de `ops` aprovados.
  Formatação dos arquivos desta entrega aprovada; a verificação global de formato
  ainda sinaliza seis arquivos preexistentes de `ops`, mantidos sem alteração
  para não misturar mudanças alheias ao alinhamento.
- **16 testes focados de cota/migration** aprovados em 55435, incluindo backfill
  não vazio, constraints, preservação de consumo e recusa de downgrade.
- **11 verificações HTTP no clone e 11 no DEV**: bloqueio sem token, consultas
  privadas, aula, rascunho, feedback determinístico, histórico, saldo vazio,
  reserva e consumo/custo conhecido. JWT válido para uma conta sintética; não
  substitui teste completo de login/refresh nem homologação por teclado/leitor.
- Zero chamadas a Ollama/gateway: escrita enviada com `assisted=false`; estados
  de reserva/consumo produzidos diretamente pelo serviço apenas para a conta do
  smoke. Não houve upload/download de áudio real nem validação auditiva humana.
- O primeiro roteiro de smoke não salvava rascunho antes de exigir histórico:
  falhou no clone e foi corrigido antes da aplicação. Os dados foram preservados.
  Recibos têm publicação exclusiva; tentativa de republicar recibo existente foi
  recusada. O comando agora reconfere recibo válido sem repetir HTTP; mudança do
  script/imagem invalida esse reaproveitamento.

Ferramentas: `ops.assist_alignment` oferece `capture`, `rehearse`, `smoke`, `apply`.
`apply` exige recibo de restore/ensaio e smoke vinculados ao backup, imagem,
clone, revisão e hash do script. Recusa origem de estudo, alteração de conteúdo
histórico, escritores ativos ou revisão não prevista. O migrador antigo mantém
seu padrão b84 → e17; a CLI antiga não deve ser usada para executar 39F.

Sequência usada, **não executar novamente no DEV já atualizado**:

```bash
# Após conferir alvo, preparar imagens, parar somente DEV e capturar backup:
uv run --project backend python -m ops.assist_alignment capture --backup "$backup_39f"
# Clone dedicado vazio preparado com perfil assist-check do compose.recovery.yml:
uv run --project backend python -m ops.recovery restore "$backup_39f" --confirm aulas-ingles-recovery/assist-check-db
uv run --project backend python -m ops.assist_alignment rehearse --backup "$backup_39f"
uv run --project backend python -m ops.assist_alignment smoke --backup "$backup_39f"
uv run --project backend python -m ops.assist_alignment apply --backup "$backup_39f"
# Recriar API/worker, smoke HTTP real, conferir preservação em quiescência e reabrir web.
```

O clone foi parado; seus volumes e o backup foram preservados. **5181/5434 continuam
na Sprint 38 (`d06a4e9cb153`)**: IDs, imagens e horários de início dos quatro
containers de estudo, além da revisão do banco, conferidos sem alteração.
Sem commit, push ou merge. Próxima implementação: **39G — jobs e retenção**;
checksum durável de voz, rollout de estudo e homologações continuam pendentes.
**A Sprint 39 inteira ainda não está encerrada.**

## Sprint 39G/H — retenção, integridade e implantação em 15/10/2026

### Implementação e limites de retenção

Migration `a39d7bc02486`, posterior a `f28c6abe1375`:

- `worker_heartbeat` mantém o último sinal do processador e contagens da última
  limpeza, sem conteúdo de aluno. A API mostra estado/idade e somente a fila da
  própria conta; indisponibilidade não significa perda do job.
- Worker executa manutenção mesmo com assistência desligada. Transações limitadas
  a 100 candidatos por escopo, máximo configurável de 500, `SKIP LOCKED`, timeout
  de statement de 5 s e de lock de 1 s. Execução a cada 60 s por padrão; cancelável
  entre transações. Não se trata de limpeza ilimitada de toda a tabela.
- Transcrições vencidas são omitidas da reivindicação, leitura, avaliação humana e
  exportação imediatamente, além da exclusão física em lotes pelo worker. O TTL
  existente continua `ASSIST_RETENTION_DAYS` (padrão 30). Reservas não despachadas
  vencidas são liberadas; consumo/custo já confirmado permanece no ledger.
- Índices de expiração de refresh e de estado/data de tentativas apoiam os lotes.
  A função SQL `aulas_retention_batch` usa `SECURITY DEFINER`, SQL estático,
  `search_path` fixo e EXECUTE revogado de PUBLIC. Worker ganha apenas execução
  desse contrato e escrita do heartbeat, não DELETE geral. Runtime e backup não
  podem executar a limpeza nem escrever no heartbeat.
- **Política adicional proposta, ainda não ativada:** refresh expirado há mais de
  7 dias e tentativa `pending` vazia há mais de 7 dias. `MAINTENANCE_CLEANUP_ENABLED`
  permanece **false** nos dois ambientes até decisão do responsável. Tentativa
  pronta, recente ou com metadados de arquivo é preservada. Ledger permanece até
  exclusão da conta/decisão futura; isso não representa prazo jurídico aprovado.
- Quarentena de arquivo órfão continua explícita, reversível, com janela mínima
  de 24 h, checksum e confirmação do alvo. Não existe expurgo automático de voz,
  journals, backups ou ledger. A janela de observação de 24 h do inventário não é
  autorização para apagar tentativas após 24 h; o lote opcional exige 7 dias.

Comandos abaixo são executados **dentro do container worker correto**, após
conferir ambiente e banco; o primeiro não altera dados:

```bash
python -m app.cli retention --scope refresh --limit 100
# Somente após aprovar a política e conferir o nome real do banco:
python -m app.cli retention --scope refresh --limit 100 --apply --confirm-database NOME_CONFERIDO
```

Escopos separados: `transcriptions`, `reservations`, `refresh`, `pending`. Resultado
JSON informa escopo, limite, dry-run e quantidade; logs do loop são agregados e
não contêm textos, áudio, e-mails ou credenciais. Desligar worker suspende a limpeza
física; filtros lógicos de expiração continuam valendo na API.

### Áudio: checksum durável e reparação sem journal

Upload novo grava SHA-256 e estado `verified`. Download/worker leem tamanho
limitado, sem seguir symlinks, e recusam bytes divergentes do checksum. O inventário
compara baseline persistido com hash observado. A interface preserva o histórico
e informa indisponibilidade quando o operador registra `missing`/`changed`.
Uma falha de download por si só não grava automaticamente o estado de auditoria.

Legado permanece `unknown`, sem hash inventado pela migration. `--baseline` registra
o estado dos bytes atuais explicitamente; **não comprova integridade retroativa**.
Para referência ausente sem journal, `app.audio_integrity` exige cópia de backup,
SHA conferido, metadados/decodificação/duração compatíveis, ID e chave esperados,
banco e diretório confirmados. Mantém ID/histórico e publica nova chave privada;
recusa sobrescrever arquivo existente. Sem cópia íntegra, bytes perdidos não podem
ser reconstruídos: preservar histórico e gravar nova tentativa.

```bash
# No ambiente correto; não há mutação sem --apply.
python -m app.audio_audit --dry-run
python -m app.audio_integrity --attempt-id ID_CONFERIDO
# Operação explícita em manutenção; estudo exige DATABASE_PURPOSE=migrator.
python -m app.audio_integrity --attempt-id ID_CONFERIDO --apply \
  --confirm-database NOME_CONFERIDO --confirm-storage /app/data/speaking \
  --expected-key CHAVE_CONFERIDA --restore-file /backup/ARQUIVO_CONFERIDO \
  --sha256 SHA256_DO_MANIFESTO_CONFERIDO
```

O Compose migrator comum não monta voz nem backup. Uma reparação requer execução
operacional específica: backup montado somente leitura, volume de voz exato,
usuário de sistema 10001 e credencial do migrador por env-file privado. Não elevar
API/worker, montar diretórios amplos ou colar senhas na linha de comando. Quarentena
em APP_ENV=prod também exige migrador. Nenhuma reparação/quarentena real foi
necessária neste rollout: ambas as origens tinham zero arquivos de voz.

### Evidências técnicas

- Backend: **955 testes**, **93,27% de cobertura**, Ruff e mypy aprovados.
- Frontend: **338 testes**, ESLint/TypeScript, build e orçamento aprovados;
  JS/CSS total **171,2 KiB gzip**.
- E2E: **126 aprovados** em Chromium desktop e viewport móvel; PWA: **2 aprovados**.
  A primeira execução teve timeout da jornada ao aguardar sincronização (125/126);
  três repetições isoladas e a segunda suíte completa passaram sem alteração de
  código. Não apagar esse registro nem confundir viewport móvel com Android físico.
- **88 testes operacionais**, lint de ops com configuração do CI e `diff --check`.
- Ensaio de papéis: **43 recusas de privilégio** e operações permitidas; worker
  limitado executou manutenção/heartbeat. Queda real do PostgreSQL **somente no
  laboratório de papéis**: o mesmo processo retomou em **3,26 s** após reinício do
  banco, sem restart do worker nem chamada externa. Não é RTO de recuperação total.
- Áudio sintético cobriu arquivo alterado, symlink, limite, baseline legado,
  ausência, restauração de cópia conferida e preservação da identidade/histórico.
  Não equivale a teste auditivo ou uso de microfone físico.

### Backup, ensaio e migrations

Backups privados preservados:

- DEV: `aulas-20261015T143111514147Z-db63464dcdcb4566b8d8696f826ab983`.
- Estudo: `aulas-20261015T152802903375Z-dc4b07120bf0483ea5c6240799aa7ea2`.

Clones **novos**, sem portas: `dev39-check-db` e `study39-check-db`, no projeto
`aulas-ingles-recovery`. Clones/volumes anteriores não foram sobrescritos.
`ops.sprint39_rollout` vincula captura/ensaio/aplicação a backup, imagem imutável,
scripts, origem, revisão, fingerprints e smoke HTTP. Restore aceita só destino
isolado vazio. Não executa seed nem abre serviços automaticamente.

- DEV: `f28c6abe1375` → `a39d7bc02486`; **45 tabelas / 6.768 linhas** históricas
  preservadas; migration/repetição/check em 19,73 s no clone e 10,90 s na origem.
- Estudo: `d06a4e9cb153` → `a39d7bc02486`; **41 tabelas / 46.192 linhas** históricas
  preservadas; migration/repetição/check em 8,00 s no clone e 7,18 s na origem.
  Inclui todas as colunas antigas, sem excluir rubricas, versões ou progresso
  existente da comparação. Backfill assistido conferido nos dois sentidos.
- As 15 divergências antigas de timestamp de conclusão e 20 de consistência da
  jornada foram preservadas; as demais regras auditadas permaneceram sem violações.
- Migração do estudo feita por `aulas_migrator` assumindo owner; API continua
  runtime e worker separado. Sem rotação de senha, seed ou correção histórica.
- Recibos `sprint39-{dev|prod}-<bundle>-{capture|rehearse|apply|live}.json` ficam
  privados em `backups/recovery/`, não no Git. Smokes criam/removem somente sua conta
  sintética por ID/e-mail exatos; sequências podem avançar. Zero provedores chamados.
- O armazenamento OCI local recusou retag das imagens antigas pelos IDs/digests
  informados pelos containers. Antes da troca, seus filesystems foram exportados
  para `sprint39-application-before-20261015T152736/`, com checksums privados. Esses
  arquivos não incluem volumes nem configuração completa e **não são uma imagem
  de rollback ensaiada**. A recuperação comprovada é dump+voz em clone; não realizar
  downgrade destrutivo ou restore sobre origem. Tags antigas das Sprints 37/38
  foram preservadas, sem afirmar que correspondem à aplicação pré-39.

**Reabertura concluída:** DEV `http://localhost:5180/` e estudo
`http://localhost:5181/`, API/web com HTTP 200, workers ativos e heartbeat recente.
As 11 verificações HTTP autenticadas passaram no clone e no ambiente real de cada
origem. Conta sintética removida por ID/e-mail exatos; fingerprints e voz conferidos
novamente sob manutenção antes da reabertura final. Configuração existente do
Ollama no DEV preservada; o processo de smoke teve assistência desabilitada e
enviou apenas escrita determinística. Estudo continua com assistência desligada.

Auditoria final de áudio completa, sem achados nos dois ambientes. Dry-run de todos
os quatro escopos retornou zero candidatos. Heartbeat mostrou zero transcrições e
reservas removidas/liberadas; nenhum dado histórico foi expurgado nesta entrega.
`MAINTENANCE_CLEANUP_ENABLED=false` conferido em ambos os workers. PWA do estudo
servido com identificador de release preenchido. Recibo privado:
`sprint39-final-health-20261015.json`.

Se a aba antiga continuar aberta, salvar o que estiver em edição e fechar todas
as abas do aplicativo antes de reabrir; não limpar armazenamento ou rascunhos para
forçar a atualização. O ciclo de duas abas/atualização segura foi testado no PWA
sintético, não por interação visual real no estudo. Laboratórios E2E, papéis e
clones 39G/H encerrados, com seus volumes e todos os backups preservados.

### Aceite humano ainda necessário

Implementação não equivale a homologação física. Continua pendente validar gravação,
reprodução, cancelamento/permissão tardia, mudança de aba/suspensão e alternativa
sem suporte em Safari/macOS/iPhone e em dispositivo móvel real. O navegador
interativo desta sessão não estava disponível; não houve contorno dessa limitação
nem declaração de inspeção visual humana. VoiceOver/TalkBack/Windows reais também
não foram homologados por estes testes (escopo da matriz de acessibilidade).

A ativação da limpeza adicional de refresh/pending aguarda a decisão de retenção
do responsável. A pergunta sobre separar aceite físico do fechamento técnico da
Sprint 39 ainda não recebeu resposta registrada. **Não declarar aceite integral
da Sprint 39 enquanto essas decisões/homologações estiverem pendentes.** Sem
commit, push ou merge nesta entrega.

## Sprint 40A — exportação e Meus dados em 15/10/2026

Primeiro incremento da Sprint 40, **não fechamento da sprint**. Código aditivo,
sem migration, seed, alteração de papéis, exclusão de dados ou política de retenção.
DEV usa os fontes locais; estudo 5181 permanece no build 39G/H. Não foi feito
commit, push ou merge. Pendências humanas/operacionais da Sprint 39 permanecem.

### Contrato de portabilidade

`GET /api/me/export`, autenticado, `private, no-store`, arquivo
`aulas-ingles-dados.json`, `schema_version=2.0`. Projeções anteriores preservadas;
novas seções independentes e IDs permitem correlação. Seções repetidas por
compatibilidade não devem ser contadas duas vezes.

| Entidades persistidas | Seção no JSON |
|---|---|
| `app_user` (sem credenciais) | `profile` |
| `lesson_progress`, `study_session_progress`, `step_progress` | `lesson_progress`, `study_sessions`, `step_progress` |
| `study_plan`, `media_progress` | `study_plan`, `media_progress` |
| `study_activity_session`, `study_activity_event`, `study_active_interval` | `activity_sessions`, `activity_events`, `active_intervals` |
| `skill_evidence`, `exercise_attempt` | `skill_evidence`, `exercise_attempts` |
| `review_item`, `review_event`, `review_card` | `review_items`, `review_events`, `legacy_review_cards` |
| `writing_draft`, `writing_revision` | `writing`, com `revisions` |
| `writing_feedback` | `writing_feedback` (canônica, inclusive sem draft); projeção também em `writing[].feedbacks` |
| `speaking_attempt`, `transcription_job` não expirado | `speaking`, com `transcription` |
| `notebook_entry` | `notebook` |
| `course_review_attempt` | `checkpoint_attempts` |
| `practice_session`, `practice_session_item` | `practice_sessions`, `practice_items` |
| `assist_reservation` | `assistance_usage`, sem chaves de fornecedor |
| `refresh_session` | `login_sessions`, somente ID e datas |

`scope` informa corte, contagens por tabela, limites e exclusões. Exporta dados
do proprietário, não autenticação, hashes de senha, chaves de fornecedor,
armazenamento físico, logs, backups ou conteúdo ainda somente local.
`audio_manifest` traz ID da tentativa, MIME, tamanho, hash quando conhecido,
estado de integridade e caminho relativo autenticado para download. Pending ou
integridade missing/changed não ganham botão de download; arquivo removido depois
do snapshot continua sujeito a 404/409. O JSON não transporta o binário.

Não há arquivo temporário/URL pública ou job de exportação. O JSON baixado não
expira e não é revogável; transcrições expiradas **antes do corte** não são incluídas.
As cópias baixadas anteriormente são responsabilidade do usuário. Caminhos de áudio
dependem da autenticação e do estado atual do arquivo; não garantem retenção futura.

Transação do endpoint é `REPEATABLE READ, READ ONLY`; o perfil é relido após
encerrar a leitura de autenticação. Uma conexão, sem transação distribuída com
filesystem. Limites preventivos: **10.000 registros pessoais**, **20 MiB JSON**,
**20 segundos** totais de serviço e **10 segundos** por statement. Exceder limite
retorna 413/503, não arquivo truncado. Jobs/streaming não foram implementados;
benchmark de grandes volumes e eventual ampliação pertencem ao refinamento BE-41.

`historical_content_status=unavailable` em tentativas sem snapshot original.
Enunciados/títulos/cues atuais não são apresentados como uma versão histórica.
Resultados de checkpoint, rubricas e fingerprints já gravados são mantidos.
A solução editorial imutável ainda pertence ao próximo incremento.

### Interface e proteção local

Rota `/meus-dados`, link no menu e caderno. JSON e áudio só são requisitados por
ação explícita; sair da página cancela a leitura/download em curso. Manifesto em
memória da tela, sem armazenamento privado no service worker/localStorage/Query.
Botões nativos, status/erro anunciados, nova tentativa e indisponibilidade offline.

Inventário é por conta e distingue rascunhos, fila bloqueada/pendente, comandos de
posição e eventos de tempo. Cópias de progresso/autoavaliação não são chamadas de
"pendentes confirmadas". Falha de leitura gera "não confirmado". Áudio temporário
na memória desta aba não é consumido pelo inventário; outras abas não são inspecionadas.
Limpeza pede confirmação e só envia `PWA_CLEAR_TEXT`; não apaga rascunhos,
gravações, fila, conta ou dados remotos. Não há botão de exclusão integral ainda.

### Validação deste incremento

- Backend: **962 testes aprovados**, incluindo snapshot concorrente read-only,
  conta A/B, feedback sem draft, recibo após remoção do item, limites/timeout e
  áudio autorizado/expiração. Nenhum provedor externo acionado. Ruff/mypy aprovados.
- Frontend: **347 testes aprovados**, lint/tipagem/build; os testes novos cobrem
  download por Enter, cancelamento ao desmontar, falha/nova tentativa, manifesto,
  limpeza cancelada/confirmada, isolamento do inventário e storage indisponível.
- Quatro E2E novos passaram em Chromium desktop/mobile emulado: JSON real,
  WAV sintético autenticado por Enter/Espaço, axe da nova página, viewport 640×360,
  ausência de cache privado e preservação de rascunhos próprios/de outra conta.
  Não equivale a zoom nativo ou dispositivo físico.
- Regressão completa no build final: **128/130** na primeira execução. As duas
  falhas foram o mesmo teste de ordem de Tab ainda com a lista anterior ao link
  “Meus dados”. Expectativa atualizada sem remover verificações; reexecução em
  ambos os projetos, duas vezes cada, **4/4 aprovada**. Não se declara uma segunda
  execução integral 130/130. Os **2 testes de lifecycle PWA** também passaram.
  Artefatos em `e2e/test-results/`, repetição em `sprint40-keyboard-recheck/`.
- Build inicial atingiu 175,2 KiB e reprovou no teto de 172 KiB. Agrupamento tardio
  de ferramentas/históricos (`study-tools`) resultou em **171,9 KiB**, sem aumentar
  limites (**176.017 bytes**, teto 176.128). Compromisso: primeira visita a uma dessas rotas carrega o grupo de
  ~14,3 KiB gzip; login/Hoje não o antecipam. A margem total restante é pequena.
- Erros iniciais foram corrigidos nos testes: expectativas de nome de tabela,
  status 201 e perfil separado no cadastro; compatibilidade Blob do ambiente de
  teste e uma anotação de tipagem. Não mascarados como testes aprovados.
- Navegador interativo indisponível (lista vazia); screenshot mobile produzido
  pelo E2E foi inspecionado como artefato. Não houve homologação física/VoiceOver.

Conferência somente leitura: DEV `/meus-dados` e fonte da página retornam 200;
OpenAPI em `localhost:8010/openapi.json` contém `ExportScope`; estudo 5181 responde
200 sem ter sido reconstruído. Laboratório E2E encerrado ao final, volumes
preservados. Banco de teste 55435 e os dois ambientes existentes foram mantidos.

### Continuidade registrada

1. **40B:** identidade estável, snapshots editoriais honestos, arquivamento,
   preview/diff do seed e proveniência por versão.
2. **40C:** exclusão de conta/recursos com reautenticação, confirmação e tarefa
   rastreável de binários; política de backups depende de decisão do responsável.
3. **40D:** histórico/arquivados na interface, versão da regra de conclusão,
   regressão integrada e implantação no estudo com procedimento seguro.

Não ativar a retenção opcional da Sprint 39 por inferência desta continuidade.

## Sprint 40B.1 — prévia e barreira editorial do seed em 15/10/2026

Escopo entregue: proteção do carregamento editorial, **não** conclusão da Sprint
40B nem da Sprint 40. Sem migration (permanece `a39d7bc02486`), sem alteração de
papéis/permissões, sem mudança de frontend/OpenAPI e sem reconstruir o estudo 5181.

### Contrato operacional

```sh
# No DEV, somente leitura; não precisa parar API/worker.
make seed-plan

# Com o ambiente/conexão já configurados para o destino correto:
python -m app.cli seed --dry-run
python -m app.cli seed --dry-run --file /caminho/lessons.json
```

`--file` procura `courses.json` no mesmo diretório. O pacote deve ser completo,
não um patch parcial. Código CLI 0 = plano permitido; 1 = bloqueado ou falha
operacional; 2 = argumentos/pacote inválidos. Flags desconhecidas são recusadas,
inclusive `--force`/`--apply`; a aplicação mantém o comando legado `seed` sem
`--dry-run`, sempre com a guarda nova. Não executar a aplicação apenas porque uma
prévia antiga foi permitida: a aplicação relê e compara dentro da própria transação.

JSON 1.0 tem política `insert_only_40B1`, fingerprint do pacote normalizado,
timestamp do snapshot, contagens `create/change/omitted/retained/unchanged/blocked`
e até 500 detalhes de identidade/campos/hashes. `changes_truncated` informa corte
da lista; totais continuam completos. Não contém texto de aluno, e-mail, caminhos
de gravação, tokens ou contagem de dados pessoais: as consultas são limitadas a
19 tabelas editoriais. Limite de 100 mil linhas por tabela, 20 s por statement;
não é promessa de capacidade nem orçamento global de 20 s.

Prévia é `REPEATABLE READ, READ ONLY`; não executa o seed para depois desfazer.
Não avança sequências. Aplicação usa `READ COMMITTED`, locks editoriais
`SHARE ROW EXCLUSIVE NOWAIT` em ordem estável, e rollback integral em erro ou
cancelamento. Banco ocupado exige nova tentativa em janela adequada; não há
retry infinito nem concessão automática de privilégios.

O caminho antigo de update/delete/reinsert foi removido. Aplicação só insere
conteúdo novo em ordem de dependências. Registro existente diferente/omitido,
novo filho de aula/checkpoint existente, incremento de versão para reinterpretar
conteúdo e downgrade são recusados **antes do DML**, mesmo sem aluno associado.
Metadados de versões inferiores já persistidas são mantidos literalmente
(`retained`), não apagados nem inventados como snapshots completos. Reaplicação
idêntica preserva todos os IDs, timestamps e sequências. Em aplicação com inserções
que falhe, a transação desfaz os registros, mas sequências PostgreSQL podem avançar.

### Conferência no ambiente existente

DEV foi consultado em **15/10/2026, 16:40:46 UTC** (13:40:46 em São Paulo), sem
aplicar carga: **6.681 iguais, 82 diferentes, 3 versões antigas mantidas, zero
novos/omitidos**. As 82 diferenças estão em `writing_prompt.requirements` e
permanecem bloqueadas. As versões antigas são das Aulas 31, 38 e 40 do Level 1.
Fingerprint do pacote: `18804444b25f5085f874d034ab236df883db525553b860ac68046adb17731460`.

A primeira prévia tratou as três versões antigas como omissões bloqueadas;
o refinamento passou a reconhecê-las como histórico mantido, com teste de
preservação literal e recusa de downgrade. Diferença de rubrica persistida não
prova por si só uma mudança pedagógica: auditar formato/defaults versus semântica
antes de qualquer migração. Não apagar versões nem reaplicar rubricas como
atalho. Nenhum `seed` de aplicação, `writing-rubrics` ou expurgo rodou no DEV/estudo.
Ao final, `GET http://127.0.0.1:8010/api/health` confirmou `status=ok`, `db=up`
e PostgreSQL 16.15. A primeira checagem usou `/health`, sem o prefixo `/api`,
e recebeu 404; a rota correta foi conferida no registro de rotas antes da repetição.

**Atenção a `make up`/`make seed`:** o seed passa a falhar de forma explícita se
encontrar essas diferenças, em vez de sobrescrevê-las. O aplicativo que já está
rodando não é desligado pela prévia. A imagem do estudo ainda não inclui esta
proteção; implantação será feita pelo fluxo seguro de fechamento, não por inferência.

### Verificação

Regressão final: **1.009 testes backend aprovados** em 111,56 s, **94% de cobertura
total** e **98% em `seed_plan.py`**. São 47 testes adicionais sobre a base de 962
da entrega 40A. Ruff aprovado para `app/tests`, mypy aprovado em 78 módulos.
`git diff --check` sem erros. Uma primeira execução das novas fixtures teve dois
erros de campo (`name` em vez de `display_name`); corrigidos e cobertos pelas
execuções completas posteriores, não registrados como aprovação inicial.

Testes em PostgreSQL descartável **55435**: reaplicação sem alteração de qualquer
linha editorial/ID/data/sequência; SQL exclusivamente read-only na prévia;
bloqueio das 19 tabelas editoriais; mudanças de gabarito/cue/rubrica/checkpoint;
chaves naturais/alternativas duplicadas; criação de curso sintético completo;
rollback de inserção parcialmente executada; conflito real entre escritores;
recusa de snapshot antigo no apply; banco alterado após a prévia; preservação de
draft/revisão, voz, resposta, revisão de vocabulário, prática com FK RESTRICT e
checkpoint real; manutenção de metadados antigos sem permitir downgrade.

Nenhum provedor de IA/STT acionado. Fixtures criadas/removidas apenas na base
marcada como descartável, com limpeza restrita ao curso/versão sintéticos. Nenhum
teste declara uma gravação física ou homologação humana. Frontend/E2E não foram
reexecutados neste incremento sem mudança de UI; evidências 40A continuam acima.

### Próximo incremento — 40B.2

1. Ensaiar migrations de identidade editorial independente de posição e snapshots
   imutáveis de exercício/prompt/cue/checkpoint, sem reconstruir passado ausente.
2. Definir publicação/arquivamento consistente em rotas por ID/slug e histórico.
3. Corrigir proveniência por revisão real, sem conservar a constante global como
   data certificada. Esta etapa apenas preserva/compara os metadados legados.
4. Refinar o diff com arquivamento e impacto agregado em dados pessoais; substituir
   o bloqueio conservador somente após esse contrato, incluindo o drift DEV.
5. Depois: 40C exclusão/backups; 40D histórico na interface e fechamento integrado.

O comando anterior `writing-rubrics` e SQL operacional direto não são protegidos
por esta guarda do seed; permanecem sujeitos ao procedimento específico de
manutenção/backup. Não houve commit, push ou merge nesta entrega.

## Sprint 40B.2a — snapshots privados de evidências em 15/10/2026

Primeira entrega do bloco 40B.2: captura de conteúdo histórico **nova e opt-in**.
Não conclui identidade editorial/arquivamento nem a Sprint 40. Snapshot não é
certificação pedagógica, cópia do arquivo de áudio ou backup restaurável.

### O que fica preservado

| Evidência | Conteúdo capturado com o novo registro |
| --- | --- |
| Exercício | Enunciado, tipo/classificação, alternativas, gabarito, dicas, explicação, resposta e feedback efetivamente calculado. |
| Item de prática | Conteúdo do exercício, posição no momento e versão da aula declarada pela sessão. |
| Escrita | Rubrica utilizada, versão da rubrica/algoritmo, critérios/resultados e modalidade da análise; não relê o prompt após a chamada assistida. |
| Fala | Cue usado no registro, tempos, falante, textos e metadados de mídia/licença/origem disponíveis naquele momento. Não inclui binário/transcrição futura. |
| Checkpoint | Questões, enunciados, alternativas/gabaritos, origem, versão, respostas corrigidas e resultado gravado. |

Conteúdo vem dos objetos usados pelo servidor na operação, não de nova leitura do
seed. Enunciado exibido no navegador antes de uma edição concorrente não é provado
por esse snapshot; ainda falta o contrato editorial ponta a ponta. Tentativas
legadas continuam sem snapshot e não são preenchidas durante retries. `correct`,
competências e resultados antigos não são recalculados pela migration.

### Persistência, privacidade e contrato

Migration **`b40e8cd13597`**, depois de `a39d7bc02486`, apenas adiciona
`evidence_content_snapshot`. Tem proprietário e exatamente uma FK real para
evento, unicidade por evento, schema 1.0, SHA-256 da serialização JSON canônica,
timestamp e conteúdo JSONB. Trigger recusa UPDATE e valida o dono do evento
(incluindo sessão pai da prática). Runtime: SELECT/INSERT e sequência; sem
UPDATE/DELETE direto. Worker: nenhum acesso. Cascade pessoal por exclusão de
evento/conta continua permitido, sem liberar remoção editorial por seed.

Limite de 200.000 bytes na serialização canônica do serviço e 262.144 bytes no
JSONB textual do banco. Snapshot e evento são gravados na mesma transação; falha
impede seu commit. Reservas/custos externos já admitidos no ledger de assistência
não são revertidos como se o provedor nunca tivesse sido acionado.
Hash é identificador de conteúdo, não assinatura contra administrador privilegiado.

`GET /api/me/history/{kind}/{evidence_id}/content`, com tipos
`exercise`, `practice`, `writing`, `speaking`, `checkpoint`, exige a conta dona.
Retorna `available` ou `unavailable`, sem reconstruir ausência com conteúdo atual.
Outra conta recebe 404; sem autenticação, 401; tipo/ID inválido, 422.
`private, no-store`, sem opt-in ao cache público. Item pendente da prática oculta
gabarito/dicas/explicação **e hash**, evitando expor um identificador enumerável de
resposta curta. Snapshot completo está na exportação explícita da própria conta.

Exportação **2.0** mantém compatibilidade e acrescenta `content_snapshots` opcional,
contagem no inventário e vínculo da tentativa com seu snapshot. Snapshot tem schema
interno 1.0; OpenAPI/tipos TypeScript regenerados. A consulta/exportação continua
funcionando com captura desligada e mantém os snapshots já existentes acessíveis.
Teto de registros/bytes da exportação continua válido e inclui a nova tabela.

### Ativação e ambientes

`EDITORIAL_SNAPSHOTS_ENABLED=false` é o padrão; a variável é encaminhada à API
pelos compose DEV/estudo. Ativar sem tabela falha com 503 e não conclui o evento.
Schema é detectado na leitura, permitindo código expand conviver com banco antigo
sem consultar uma tabela ausente. Não existe cache negativo permanente dessa detecção.

**Aplicado somente aos laboratórios** PostgreSQL descartável 55435 e papéis
`aulas-ingles-roles` (rede interna, sem portas publicadas). Captura habilitada nas
fixtures e no processo HTTP sintético do teste de papéis. Não foi alterado `.env`
real, nem executada migration/seed/rubricas ou reconstrução no DEV/estudo. Os dois
ambientes de uso continuam em `a39d7bc02486`, captura desligada; as 82 diferenças
de rubrica do DEV permanecem protegidas pela barreira 40B.1.

Conferência final em leitura no DEV: revisão `a39d7bc02486`, flag `false`, tabela
de snapshots ausente e `/api/health` com `status=ok`/`db=up`. O laboratório de
papéis foi encerrado após os testes; nenhum container desse projeto ficou ativo.

Para rollout: backup real e restauração ensaiada com a mesma imagem, aplicar
migration como migrador, verificar grants, só então habilitar captura e testar
conta sintética. Não executar `make up` como atalho para sobrescrever o drift do
seed. Downgrade recusa tabela com snapshots; em tabela vazia, foi ensaiado
upgrade/downgrade/upgrade. Nenhum dado histórico é descartado para forçar downgrade.

### Verificação deste incremento

- **1.021 testes backend aprovados**, 94% de cobertura total; serviço
  `editorial_history.py` com 100% nesta execução. São 12 testes adicionais sobre
  a entrega 40B.1. Regressão completa em 133,54 s, sem uso de provedor externo.
- Testes reais de captura nas cinco modalidades, propriedade A/B, exportação,
  snapshot após mudança de gabarito, retry sem reinterpretar feedback capturado,
  concorrência com quatro retries produzindo um evento/snapshot, ausência legada,
  falha/rollback, flags/schema e limites. Exercícios antigos sem snapshot ainda
  têm limitações nos endpoints legados; a rota histórica nova é explícita.
- Migration ensaiada em schema isolado: sem backfill, validação de dono,
  imutabilidade, cascade pessoal, recusa de downgrade destrutivo e reversão vazia.
  `alembic check`: nenhuma operação de atualização pendente.
- Laboratório de papéis: captura/leitura HTTP de exercício e escrita pelo runtime,
  recusa de UPDATE/DELETE direto e de leitura pelo worker, além do smoke anterior
  de permissões/cotas/retenção e backup com papel limitado. Isso não substitui
  restauração do backup real do ambiente de uso para o rollout.
- **347 testes frontend**, lint, tipagem, build e orçamento aprovados;
  bundle **171,9 KiB gzip** com teto inalterado de 172 KiB. Nenhuma tela histórica
  nova; sem nova execução E2E/avaliação física de acessibilidade neste incremento.
- Ruff e mypy (80 módulos) aprovados; `git diff --check` limpo. As falhas iniciais
  das fixtures — ID de prática não exposto na resposta atual e contexto de
  transação assíncrona — foram corrigidas antes da regressão completa.

### Continuidade exata

1. **40B.2b:** identidade editorial independente de posição, arquivamento/publicação
   consistente por ID/slug e origem/datas de revisão reais; estender o diff para
   impacto/arquivamento. Não liberar alteração de conteúdo via seed antes disso.
2. Integrar snapshots às projeções existentes de prática/escrita/fala/histórico e
   ao consumo posterior de cue pelo STT; não declarar todas as telas históricas
   corrigidas apenas pela nova API. Retry de prática ainda recusa conteúdo alterado.
3. Auditar diferença de formato versus semântica das 82 rubricas DEV, sem backfill
   fabricado, e preparar rollout com backup/restore; captura ainda não está ativa.
4. **40C:** exclusão pessoal e decisão sobre backups; **40D:** interfaces históricas,
   regra de conclusão, regressão/aceite integrado e implantação no estudo.

Sem commit, push ou merge. Nenhuma política de retenção opcional ativada.

## Sprint 40B.2b.1 — disponibilidade e prévia de arquivamento em 15/10/2026

**Incremento parcial da 40B.2b, não fechamento de 40B ou da Sprint 40.** Ao conferir
o caminho para identidade/arquivamento, foram encontrados acessos por ID que não
validavam publicação dos pais. Priorizada essa correção antes de oferecer um comando
de arquivamento. Identidade editorial independente de posição **não foi implementada
nesta etapa**; não se deve interpretar o ID numérico atual ou hash do relatório
como substituto desse contrato.

### Política de disponibilidade online

`services/publication.py` compartilha filtros de curso **e** unidade publicados
entre resolução da aula e operações por ID. Conteúdo não publicado retorna 404
para novas atividades. Listagens ocultam cursos/unidades arquivados; curso planejado
mantém só prévia, sem aulas/checkpoints disponíveis ou contagem publicada.
Checkpoint publicado não incorpora mídia de listening de outra unidade não publicada.

| Operação | Curso/unidade não publicado |
| --- | --- |
| Aula, exercícios/vocabulário atuais, tentativa, dica/revelação, nova prática e suas mutações | Indisponíveis; leitura da prática já pertencente à conta por ID permanece. |
| Novo rascunho/versão/feedback de escrita | Indisponíveis; rascunho já existente continua legível somente pelo dono. |
| Nova gravação e nova solicitação de transcrição | Indisponíveis; nova transcrição é recusada antes de consumir/reservar cota. |
| Áudio pessoal e job já admitido | Leitura/gestão autenticada anterior preservada; upload já admitido pode terminar ou ser cancelado. |
| Posição de mídia | Posição pessoal existente é legível; limpeza mantém CAS e tombstone. Não admite criar posição em mídia indisponível. |
| Revisão pessoal já copiada, caderno existente, snapshots e exportação | Mantidos sob controle de propriedade; não são catálogo público. Adicionar novo vocabulário do catálogo indisponível é recusado. |
| Tempo ativo | Nova sessão exige publicação; retries/eventos de sessão previamente admitida seguem o contrato anterior. |

Arquivamento editorial não é exclusão pessoal nem retirada retroativa de licença.
Não altera `correct`, notas, rubricas, gabaritos ou competências gravadas. Snapshots
legados ausentes continuam ausentes. Integração de conteúdo capturado ao worker/STT
e às demais projeções históricas permanece pendente.

Não existe aplicação de arquivamento nesta entrega. Os testes de estados fazem
alterações reversíveis **somente no PostgreSQL descartável** e restauram o status
em `finally`. Um futuro comando precisa serializar publicação com admissões,
registrar auditoria e tratar cache/conclusão; não executar UPDATE manual como atalho.

### Prévia operacional somente leitura

```sh
docker compose --env-file .env -f infra/compose.yml exec -T api \
  python -m app.cli editorial-plan --course voa-level-1 --unit 31-40
```

O comando exige curso/unidade explícitos; não tem `--apply`, `--force`, `--delete`
ou `--archive`. Não cria arquivo nem expõe rota administrativa HTTP. O relatório
JSON 1.0 informa `dry_run=true`, `apply_available=false`, estado/IDs editoriais do
alvo, contagens, limitações e bloqueios. IDs de alunos, respostas, rascunhos,
credenciais e caminhos de áudio não são selecionados para saída.

Uma transação nova `REPEATABLE READ, READ ONLY`; limite total de **30 s**, por
statement **20 s**. Sessão com transação/ORM pendente é recusada antes de consultar.
Erro/timeout não imprime relatório parcial. Não há DML, avanço de sequências ou
atualização de timestamps editoriais.

Contagens abrangem as 19 tabelas editoriais e 21 tabelas pessoais atribuíveis ao
alvo, mais `evidence_content_snapshot` quando disponível. Contagens de curso/unidade
são contexto, não solicitação de arquivar o curso inteiro. Incluem filhos de prática,
rascunho, tempo ativo e checkpoints; competências usam suas três origens conhecidas.
Recibos sem item, origens sem vínculo resolvível, sessões de acesso, cotas/plano,
backups e dados apenas locais não são atribuídos a uma unidade; isso não significa
que sejam inexistentes ou removíveis. Não somar linhas como se fossem alunos únicos.

`external_checkpoint_dependencies` conta checkpoints de **outras unidades do mesmo
curso**, em qualquer status, que referenciam aulas-alvo pelo fechamento, listening
ou questões JSONB. São referências sem FK; não inferir independência entre unidades
só pelo relacionamento `unit_id`. `report_sha256` identifica apenas o relatório
agregado, excluindo o horário: não prova identidade/versão de conteúdo, não reserva
o banco e não autoriza uma escrita futura. O seed continua insert-only (40B.1).

### Conferência de ambientes

No DEV, prévia executada em leitura retornou para 31–40: **10 aulas, 111 exercícios,
10 prompts, 48 cues, 13 registros de versão e 1 checkpoint externo dependente**.
As contagens pessoais atribuíveis estavam zeradas naquele corte; isso não comprova
ausência de dados em outras unidades, contas, dispositivos ou no estudo.
Tabela de snapshots ausente explicitamente sinalizada; não há backfill.
`/api/health`: `status=ok`, `db=up`.

Sem nova migration, seed, alteração de `.env`, status de conteúdo ou privilégios no
DEV/estudo. DEV utiliza fontes locais atualizadas; estudo não foi reconstruído.
Captura de snapshots permanece desligada nos ambientes de uso. Nenhuma retenção
opcional ativada, commit, push ou merge realizado.

### Validação deste incremento

- **1.044 testes backend aprovados**, 94% de cobertura, regressão final em 117,06 s.
  São 23 testes adicionais sobre a 40B.2a; `publication.py` e `editorial_plan.py`
  ficaram com 100% de cobertura nesta execução. Sem provedor externo acionado.
- Matriz curso/unidade × planejado/arquivado cobre 21 rotas de conteúdo/atividade,
  além das listas. Preservação/isolamento de histórico A/B, rascunho, posição,
  snapshots, prática, exportação, revisão pessoal e cancelamento de gravação.
  Nova transcrição recusada sem job/reserva; limpeza de posição mantém CAS.
- Prévia: ausência de DML/avanço de sequência, mesmas contagens após reaplicação,
  snapshot consistente com gravação concorrente, escopo entre cursos/unidades,
  origem indireta dos dados, ausência de textos pessoais na saída, limite total,
  rollback de timeout, schema legado sem snapshots e recusa de flags de escrita.
- Fixture inicial de tentativa omitira `idempotency_key` obrigatório e recebeu
  422; corrigida antes das execuções aprovadas, sem enfraquecer o contrato.
- **347 testes frontend**, lint, tipagem, build e orçamento aprovados: **171,9 KiB
  gzip**, teto inalterado de 172 KiB. Não houve mudança de interface nem nova
  execução E2E/validação física de acessibilidade neste incremento.
- Ruff, mypy (82 módulos), igualdade do OpenAPI com contrato versionado e
  `git diff --check` aprovados. Não há mudança de schema HTTP ou tipos frontend.
- Não foi necessário novo ensaio de migration/grants: nenhum schema/papel mudou.
  A validação operacional feita no DEV foi exclusivamente leitura.

### Continuidade

1. Identidade editorial estável e mapeamento explícito no pacote do seed, sem derivar
   identidade permanente da posição. Preservar IDs/FKs existentes e ensaiar migration.
2. Aplicação auditada/serializada de arquivamento e integração do impacto ao diff do
   seed; incluir dependências entre unidades. A prévia atual não executa o plano.
3. Proveniência por revisão, auditoria das 82 diferenças de rubrica DEV e integração
   dos snapshots ao histórico/STT; não inventar datas, versões ou conteúdo anterior.
4. Mensagens/links de arquivados, política de cache público/offline, regra versionada
   de conclusão e rollout seguro; seguir com 40C e 40D conforme o planejamento.

API online recusar conteúdo não revoga cópias já baixadas. Não declarar interfaces
históricas ou política offline completas com base nestes testes de API.

## Sprint 40B.2b.2 — identidade editorial estável em 15/10/2026

**Incremento técnico concluído em laboratório; Sprint 40 ainda parcial.**
Este bloco atende a identidade independente de posição. Não implementa alteração
de conteúdo, aplicação de arquivamento ou rollout nos ambientes de uso.

### Contrato e baseline

Migration `c51f9de246a8`, após b40, acrescenta `editorial_key` UUID `NOT NULL`,
único por tabela, em seis entidades. IDs numéricos e FKs continuam iguais.
Trigger impede substituir/anular a chave, inclusive em UPDATE pelo owner.
Ordenação e conteúdo continuam atributos distintos; a chave não é uma versão,
hash de texto, evidência de homologação ou reconstrução da identidade no passado.

| Entidade | Chaves explícitas na baseline do seed |
| --- | ---: |
| Exercício | 687 |
| Proposta de escrita | 82 |
| Trecho de transcrição (cue) | 408 |
| Mídia da aula | 82 |
| Vocabulário | 835 |
| Questão de checkpoint | 100 |
| **Total** | **2.194** |

O bootstrap inicial usa UUIDv5 com namespace e receita congelados. Coordenadas
legadas (curso/aula/posição, termo para vocabulário, unidade para questão) servem
**somente para associar a baseline atual**. As chaves ficam literais em
`seed/courses.json` e `seed/lessons.json`, e persistidas pela migration. Depois
disso, alterações/reordenações carregam a chave original; não recalculá-la com
nova posição, texto ou pai. Novo item/clone precisa de nova chave explícita
(UUIDv4 recomendado). Importação valida UUID canônico v4/v5 e duplicidade.

`ops/bootstrap_editorial_keys.py` é utilitário de execução única, fora do fluxo
normal de seed. Foi executado explicitamente para essa baseline e recusa uma
baseline já parcialmente/totalmente identificada. Antes da gravação, a comparação
removendo apenas as novas chaves confirmou igualdade de todos os demais valores.
SHA-256 dos dois documentos normalizados, sem as chaves:
`8113970438150dc3a9c4e989f0354392c84ff2db0fff796c8b0cb7065e8cbf9f`.
Não usar esse bootstrap novamente para corrigir um diff ou reordenar conteúdo.

### Seed, snapshots e compatibilidade

- Diff 1.1 usa as chaves para esses seis tipos e para suas referências normalizadas.
  Reordenação aparece como mudança do campo `position` da mesma entidade, sem
  reassociar respostas/dicas/cues. Substituir a chave aparece como omissão/criação.
- **Barreira insert-only mantida:** mudanças, omissões e filhos novos de conteúdo
  existente continuam bloqueados, independentemente de terem referências pessoais.
  Não há `--force`, aplicação de reordenação ou arquivamento neste incremento.
- No schema antigo, prévia continua somente leitura e marca `identity_storage`
  como `legacy_projection`; projeção não é chave persistida. `allowed=false` e
  `schema_blocker` exigem c51. Aplicação recusa antes de qualquer DML de seed.
- Colunas ORM são deferred/raiseload; a leitura normal não exige a nova coluna.
  Leitura de mídia para snapshot também seleciona apenas colunas compatíveis.
  Não houve alteração de rotas/IDs públicos, OpenAPI ou tipos frontend.
- Com schema migrado e captura habilitada, snapshots **novos** recebem metadados
  `editorial_identity_contract=explicit_uuid_v1`: chave de exercício/prática,
  prompt, cue/mídia ou de cada questão do checkpoint. Envelope permanece 1.0;
  são campos opcionais do conteúdo e o hash inclui esses metadados. Apenas a
  identidade imutável é consultada novamente, não o texto/gabarito/rubrica.
- Com apenas b40, captura permanece compatível sem as chaves. Snapshots já
  existentes e retries não são enriquecidos retroativamente. Ausência histórica
  continua explícita; nenhum conteúdo/resultados antigos foram inventados.

UUID não corrige referências posicionais de listening/checkpoints nem fingerprints
de prática. Isso precisa ser tratado antes de liberar reordenação. Os outros tipos
editoriais mantêm suas chaves anteriores; não afirmar que todas as 19 tabelas
ganharam UUID ou versionamento semântico nesta etapa.

### Segurança da migration e ambientes

Migration não remove/recria entidades ou filhos, não mexe em sequências e não
reescreve conteúdo, rubricas, versões, datas ou resultados. Ensaio em schema
temporário conferiu valores/IDs/FKs e resultado anterior, além de manter a chave
após mudar posição. UNIQUE/NOT NULL e trigger foram exercitados por SQL direto.

Downgrade **recusa tabelas povoadas**: retirar chaves após reordenação permitiria
reidentificar conteúdo incorretamente. Downgrade/re-upgrade vazios foram ensaiados
apenas no schema sintético revertido por rollback. Em operação, voltar o código
sem remover as colunas é a opção não destrutiva; restore exige plano/backup válido.

Aplicação de migrations/seed limitada ao PostgreSQL descartável protegido (55435)
e ao laboratório de papéis sem portas. Este último foi encerrado, preservando
seu volume. Runtime lê chaves e captura via HTTP, mas não pode atualizá-las; worker
e backup também não podem alterá-las. Nenhuma permissão editorial adicional foi
concedida aos papéis da aplicação.

DEV e estudo não receberam migration, seed, mudança de privilégios ou `.env`;
captura permanece desligada. DEV usa fontes locais atualizadas e sua prévia
read-only retornou `legacy_projection`, 82 mudanças bloqueadas de rubrica,
3 versões retidas e 6.681 itens iguais. A migration não resolveria essas rubricas
automaticamente: auditar formato versus semântica continua pendente. Estudo não
foi reconstruído. Sem commit, push, merge ou política de retenção nova.

Conferência HTTP read-only no DEV após as alterações: `/api/health` retornou 200
(`status=ok`, `db=up`), assim como `/api/courses` e
`/api/courses/voa-level-1/lessons/31`. O utilitário de bootstrap foi executado
novamente sem `--apply` e recusou corretamente a baseline já identificada.

### Validação

- **1.066 testes backend aprovados**, 94% de cobertura, 140,61 s; 22 testes novos
  sobre o incremento anterior. Identidade 97% e seed planner 99% de cobertura.
- Cobertura inclui rejeição de chave ausente/inválida/duplicada, clone com identidade
  indevida, preservação de filhos no diff, leitura legada sem coluna, projeção
  explicitamente bloqueada, seed idempotente, migration e snapshots nas cinco
  modalidades, sem atualização retroativa. As falhas iniciais de fixture SQL e de
  tentativa de mudar o envelope do snapshot foram corrigidas antes da regressão.
- `alembic check`: nenhuma operação nova pendente. Laboratório com papéis reais:
  leitura das seis chaves, recusa de UPDATE por runtime/worker/backup, captura HTTP,
  demais recusas anteriores, cotas/retenção e dump com papel limitado aprovados.
- **88 testes operacionais** e **347 testes frontend** aprovados. Lint, tipagem,
  build e orçamento frontend aprovados: **171,9 KiB gzip**, teto 172 KiB inalterado.
- Ruff, mypy (83 módulos), igualdade do OpenAPI e `git diff --check` aprovados.
  Sem nova execução E2E, teste de acessibilidade física ou tela histórica nova.

### Próxima etapa

1. Aplicação de arquivamento com auditoria e serialização das admissões; integrar
   impacto/dependências entre unidades ao plano do seed. Não executar UPDATE manual.
2. Proveniência por revisão, análise das 82 rubricas DEV e integração de snapshots
   às projeções históricas e ao worker/STT, sem inventar revisão ou conteúdo passado.
3. Interface de arquivados, invalidação do cache/offline, conclusão versionada e
   rollout com backup/restore. Prosseguir com 40C (exclusão/backups) e 40D (aceite).

## Sprint 40B.2b.3 — arquivamento auditado local em 15/10/2026

**Incremento técnico concluído em bases isoladas, não fechamento da Sprint 40
nem liberação de arquivamento no ambiente de uso.** Implementada a transição de
uma unidade publicada para arquivada com registro atômico, sem apagar conteúdo,
dados pessoais ou arquivos. Cursos inteiros, republicação/desarquivamento e
edição/reordenação semântica não são operações deste comando.

### Prévia, aplicação e repetição segura

`editorial-plan --course ... --unit ...` permanece exclusivamente leitura. Formato
1.1 acrescenta `catalog_sha256`, disponibilidade de identidade/auditoria, bloqueios
dinâmicos e limitações do rollout. `report_sha256` continua identificando somente
o relatório agregado, não uma autorização. `apply_available` descreve elegibilidade
local, não concede privilégios nem reserva conteúdo.

`catalog_sha256` considera o catálogo normalizado das 19 tabelas, IDs, alvo/estados
e nome do banco. Não inclui dados pessoais. Alterações editoriais até em outra
unidade invalidam a prévia conservadoramente; mudanças de contagens pessoais não
mudam o digest. Nenhuma data/hash prova homologação pedagógica ou conteúdo anterior.

Novo comando `editorial-archive` exige todos os parâmetros abaixo:

| Parâmetro | Contrato |
| --- | --- |
| `--course`, `--unit` | Alvo único existente; curso e unidade precisam estar publicados. |
| `--catalog-sha256` | Digest da prévia atual, rechecado com as tabelas editoriais bloqueadas. |
| `--operation-key` | UUIDv4 canônico; guardar a mesma chave para retries. |
| `--operator` | Identificador operacional de 1–64 caracteres, sem texto livre. Não é autenticação. |
| `--reason` | `editorial_review`, `source_unavailable` ou `curriculum_reorganization`. |
| `--confirm-database` | Nome exato do banco conectado. Não transportar comando entre ambientes. |
| `--apply` | Confirmação explícita; sua ausência é erro antes da execução. |

Pré-condições adicionais: `EDITORIAL_ARCHIVE_ENABLED=true`, schema d62 e migrations
anteriores, sessão nova READ COMMITTED e identidade SQL com os privilégios do owner.
Flag **false por padrão**, documentada no exemplo de ambiente e não propagada ao
runtime pelos composes. `APP_ENV=prod` ou `DEPLOYMENT_PROFILE=public` são recusados
**mesmo com flag true**. Não mudar a classificação de ambiente para contornar isso.
Não há rota HTTP administrativa, `--force`, cascata de dependências ou exclusão.

Após adquirir os locks, o serviço refaz a análise. Um checkpoint de outra unidade
que referencie aulas-alvo (fechamento, listening ou questões JSONB), em qualquer
status, bloqueia a operação. Não é arquivado ou reescrito automaticamente.
No DEV, 31–40 continua tendo uma dependência externa e portanto não é elegível.

Status e recibo são gravados na mesma transação. Falha no recibo reverte o status.
Retry com mesma chave e mesmos campos retorna o recibo persistido (`replayed=true`);
chave reutilizada com outro pedido é recusada. Nova chave não permite reexecutar
uma unidade já arquivada. Em falha de conexão/commit, repetir a mesma chave/pedido
para descobrir se houve confirmação; não executar SQL manual ou gerar outra chave.

### Auditoria e preservação

Migration `d62a0ef357b9` cria `editorial_archive_event`, sem backfill ou mudança
de status. PK da operação, FK RESTRICT à unidade, constraints de transição/motivo/
digest, alvo, operador declarado, `current_user`/`session_user` reais, data do banco
e impacto agregado observado na aplicação. Não registra texto de aluno, ID de
usuário, respostas ou caminhos de áudio. Não aparece na exportação pessoal.

Trigger recusa UPDATE/DELETE do recibo; downgrade recusa auditoria não vazia.
Não promete resistência a DDL/superusuário: owner é responsável pela operação.
Runtime/worker não têm SELECT nem DML nessa tabela, backup tem SELECT e não escreve.
Permissões foram verificadas em conexões reais; nenhum privilégio editorial foi
concedido ao runtime. Migração vazia/downgrade/re-upgrade e FK RESTRICT ensaiados.

Dados curriculares, chaves estáveis, rascunhos, resultados, snapshots e áudios não
são alterados pelo apply. Leitura privada existente continua regida pela propriedade;
novas atividades online deixam de estar disponíveis pela política da 40B.2b.1.
Isso não apaga dados pessoais nem revoga cópias já existentes em cache/offline.

### Concorrência e integração com o seed

Admissões curriculares usam o advisory lock transacional compartilhado `(74040, 1)`
antes de consultar publicação, mantido até commit/rollback. Seed/arquivamento
exigem o exclusivo; aquisição é não bloqueante. Se estudo estiver em transação,
apply recusa imediatamente. Se apply estiver ativo, nova admissão recebe 503
transitório, sem persistir atividade. Locks não ficam presos à conexão após a transação.

O lock é global ao catálogo neste primeiro contrato, não por unidade. Alguns GETs
que usam os mesmos resolvedores também podem receber 503 breve. Decisão conservadora
para impedir ciclos entre unidades/checkpoints; medir antes de granularizar.
Todos os processos de admissão precisam executar o protocolo: versões antigas ou
SQL manual não são considerados seguros para rollout concorrente.

Apply usa também SHARE ROW EXCLUSIVE NOWAIT nas 19 tabelas editoriais, impedindo
seed/edição concorrente durante revalidação e escrita. Não adquire lock em tabelas
pessoais. Prazo total 30 s, statement 20 s. Locks de aluno/prática existentes não
formam espera circular porque a aquisição editorial falha imediatamente.

Reserva de escrita assistida/job já admitido pode terminar após o arquivamento;
upload já admitido e gestão privada mantêm seus contratos. Não cancelar ou consumir
cota novamente por causa do arquivamento. Contagens pessoais do recibo são observações
sob READ COMMITTED, não snapshot global estático: esses fluxos podem continuar.
Somente as dependências/editorial que autorizam a transição ficam congeladas.

Dry-run do seed inclui `archive_requests` com impacto/dependências/digest quando
uma unidade existente tem pedido **explícito** de `published` para `archived`.
Até cinco prévias agregadas, com sinalização de truncamento; mesma transação read-only
da prévia original. `archive_apply_via_seed=false`: barreira insert-only permanece,
inclusive para mudanças de status. Omissão não vira pedido de arquivamento/exclusão.
Após arquivamento futuro, reconciliação do pacote precisa conservar o estado arquivado;
seed antigo não republica automaticamente, apenas apresenta divergência e bloqueia.

### Evidências e ambientes

- **1.082 testes backend aprovados**, 94% de cobertura, 143,99 s; 16 testes novos.
  Arquivamento 92%, plano 99%, publicação 100% nessa execução. Reexecução dos
  16 testes específicos após reforçar a verificação de mudanças pessoais no digest.
- Ensaios cobrem atomicidade/rollback, recibo/retry, imutabilidade/FK, digest obsoleto,
  dependências, confirmação/flag/perfil, impacto no seed e concorrência nas duas
  direções. Matriz de 12 rotas de admissão recusada durante lock exclusivo; fluxo
  normal volta após rollback. Fixture inicial do checkpoint corrigida antes do aceite.
- Testes de arquivamento usam transação externa com savepoints e rollback final:
  nenhum recibo precisou ser apagado ou trigger desativado. Fluxos de rascunho e
  snapshot continuam legíveis e seus valores foram comparados antes/depois.
- Laboratório de papéis: migrador arquiva/reexecuta e confere identidades SQL reais;
  ensaio inteiro revertido por rollback. Runtime/worker recusados na auditoria,
  backup só lê, demais smokes HTTP/cotas/retenção/dump aprovados. Laboratório
  encerrado com seu volume preservado. Não foi restauração de backup do estudo.
- **88 testes operacionais**, **347 testes frontend**, lint, tipagem, build e
  orçamento frontend aprovados: **171,9 KiB gzip**, teto 172 KiB inalterado.
- Ruff, mypy (84 módulos), OpenAPI inalterado, `alembic check` sem drift e
  `git diff --check` aprovados. Sem novo E2E ou validação física de acessibilidade.

Somente banco descartável protegido (55435) e laboratório de papéis receberam d62.
DEV/estudo não receberam migration, alteração de `.env`, privilégios ou status.
Na prévia DEV: `dry_run=true`, `apply_available=false`, `legacy_projection`,
auditoria ausente, bloqueios de migration/flag/dependência externa. Saúde, catálogo
e Aula 31 retornaram HTTP 200. Estudo não foi reconstruído. Captura de snapshots
segue desligada nos ambientes de uso. Sem commit/push/merge.

### Próxima etapa

1. Auditar as 82 divergências de rubrica DEV e corrigir proveniência/datas por revisão,
   distinguindo normalização de formato de mudança pedagógica. Não fabricar revisão.
2. Integrar snapshots ao histórico/prática/escrita/fala e worker/STT; resolver
   referências posicionais antes de admitir mudanças de conteúdo/reordenação.
3. Interface de arquivados, cache/offline, regra de conclusão versionada e rollout
   com backup/restore, incluindo todos os processos no protocolo de admissão.
4. Continuar 40C (exclusão pessoal/backups) e 40D (aceite integrado); não avançar
   a Sprint 41 como se a Sprint 40 estivesse fechada.

## Sprint 40B.2c — auditoria de rubricas e proveniência, 15/10/2026

### Comando e contrato

`make editorial-audit` (ou `python -m app.cli editorial-audit` dentro da API)
abre uma sessão nova em `REPEATABLE READ, READ ONLY`, limita cada statement a
20 segundos e consulta somente catálogo editorial. A saída JSON contém contagens,
localizador curso/aula/posição e hashes; não contém termos das rubricas, textos de
alunos, e-mail, respostas ou caminhos de áudio. `apply_available=false` é fixo:
o relatório não é autorização para escrita.

| Classe | Significado operacional |
| --- | --- |
| `exact` | Representação persistida e pacote são iguais. |
| `representation_only` | Defaults/normalização produzem a mesma rubrica canônica. |
| `display_only` | Muda rótulo/ordem, mas não o resultado booleano do avaliador atual. |
| `evaluation_change` | Termos, modo, contagem ou quantidade podem mudar aprovação. |
| `prompt_metadata_change` | Título, instruções ou mínimos da proposta mudaram. |
| `invalid/missing/extra` | Catálogo inconsistente; não publicar nem corrigir automaticamente. |

O antigo `writing-rubrics` agora termina com código 2 **antes de criar sessão**.
A função Python de compatibilidade também recusa a chamada. Preservar IDs e
evidências não torna uma sobrescrita segura; cada mudança semântica exige nova
versão editorial, snapshots para novas evidências e homologação pedagógica.

### Resultado somente leitura no DEV

- 82 propostas no seed e 82 persistidas; nenhuma ausente ou extra.
- **18** diferenças apenas de representação, **1** apenas de apresentação e
  **63** que alteram o resultado possível da avaliação.
- Level 1: 14 de representação, 1 de apresentação e 37 semânticas; Level 2:
  4 de representação e 26 semânticas.
- Campos afetados por proposta semântica: `min_count` 51, `match_mode` 18,
  `count_mode` 17, `terms` 16 e quantidade de critérios 10. Uma proposta pode
  aparecer em mais de um grupo.
- Digest do relatório agregado observado:
  `7501b836113b73d3d55069fba632c9919fe9c94ce5910f62b37150164b68c92e`.
- Nenhuma rubrica, versão, resultado ou dado pessoal foi alterado no DEV.

O DEV possui 85 `lesson_version` com `reviewed_at=07/10/2026`; 83 aparecem antes
do último acesso registrado à fonte. Todas as 82 aulas do pacote têm acesso à
fonte explícito, mas nenhuma tem timestamp de revisão comprovado. Portanto,
07/10 era um default técnico, não evidência de revisão humana.

A prévia geral do seed continua bloqueada e agora explicita as duas famílias:
164 mudanças (`lesson_version` 82 + `writing_prompt` 82), 3 versões históricas
retidas e 6.599 registros iguais. O schema DEV ainda aparece como
`legacy_projection` e exige c51; isso não autoriza aplicar c51/e73 ou o seed.

### Correção de proveniência e rollout

Migration `e73c1a9b40d2`, após d62, torna `lesson_version.reviewed_at` anulável,
converte somente o timestamp legado gerado de 07/10 em `NULL`, remove eventual
`published_at` gerado no mesmo instante e troca a nota default genérica por uma
declaração explícita de validação pedagógica pendente. Datas reais diferentes
são preservadas. O downgrade recusa fabricar datas para linhas desconhecidas.

O seed não usa mais defaults de 07/10: exige `source_accessed_at`, status e nota
explícitos; timestamps opcionais precisam ter fuso, não podem anteceder a fonte
e publicação datada exige revisão datada. As sete aulas sem nota receberam apenas
a marcação honesta de registro legado/QA pendente, não uma homologação inventada.
Na API, `reviewed_at` passa a aceitar `null`; não houve tela nova.

Ensaiar migration + auditoria + seed idempotente no restore isolado antes de
qualquer janela real. Esta entrega **não aplicou e73 nem rubricas no DEV/estudo**.
Não executar o runbook histórico da Sprint 37, `writing-rubrics`, seed completo
ou SQL direto. Um rollout das 63 mudanças depende primeiro do modelo de nova
versão e da decisão pedagógica por proposta.

### Evidências

- PostgreSQL descartável 55435: upgrade d62→e73 e seed idempotente aprovados;
  migration ensaiada com data gerada, data real preservada e downgrade recusado.
- **1.088 testes backend**, 94% de cobertura; auditor editorial 88%.
- Ruff, mypy (85 módulos), `alembic check` e `git diff --check` aprovados.
- **347 testes frontend**, lint, TypeScript, build e orçamento de 171,9 KiB gzip.
- **88 testes operacionais** aprovados; OpenAPI/tipos regenerados apenas pela
  nulabilidade verdadeira de `reviewed_at`.

Sprint 40 continua parcial. Próximos itens: publicar versões das rubricas após
homologação, integrar snapshots aos históricos/prática/escrita/fala e worker/STT,
resolver referências posicionais, interface/cache, exclusão pessoal e rollout.

## Sprint 40B.2d — histórico integrado e STT imutável em 15/10/2026

### Contrato de leitura

- `PracticeSessionItemOut` expõe `id` e `historical_content_status`; o ID abre a
  rota privada já existente sem procurar o exercício atual por posição.
- Cada `WritingFeedbackOut` declara se o snapshot completo foi capturado. A
  rubrica persistida continua sendo a fonte do resultado, sem recálculo.
- `SpeakingAttemptOut.cue_text` vem exclusivamente do snapshot da tentativa e
  passa a aceitar `null`. Ausência legada não é preenchida com `transcript_cue`
  atual. A interface preserva ouvir/excluir o áudio e oculta nova transcrição.
- `TranscriptionJobOut.expected_text` também aceita `null` e traz o mesmo estado.
  Resultado legado já salvo não é recalculado nem apagado.

Consultas em lista carregam snapshots em lote; não acrescentam uma consulta por
registro. Captura continua controlada por `EDITORIAL_SNAPSHOTS_ENABLED`; desligar
a flag não apaga nem torna ilegíveis snapshots existentes.

### Admissão e execução do STT

Para job novo, a API verifica a captura antes da reserva. Sem ela responde 409
com `historical_content_unavailable`; não chama provedor e não consome cota. Job
já existente continua consultável. No worker, a cue é relida da captura imutável
somente depois de reivindicar o job. Se um job legado já estava na fila sem essa
captura, termina como falha antes do dispatch e libera a reserva ainda pendente.

Migration `f84d1b6c2a90` cria
`public.aulas_speaking_expected_text(integer,integer)` como projeção fixa
`SECURITY DEFINER`, `search_path` fechado e `PUBLIC` revogado. O worker recebe
apenas `EXECUTE`; permanece sem `SELECT` em `evidence_content_snapshot`. Runtime
e backup não executam a função. A função devolve apenas `text_en` quando dono,
tentativa e `kind=speaking` coincidem, nunca rubrica, resposta ou texto pessoal.

### Falhas que este incremento impede

1. Editar uma cue depois do pedido não altera a semelhança calculada pelo worker.
2. Abrir histórico antigo não exibe a legenda atual como evidência do passado.
3. Tentativa sem captura não envia voz a um provedor sob critério editorial
   desconhecido.
4. A integração não amplia o acesso do papel de worker à tabela privada inteira.

### Validação e ambientes

- PostgreSQL descartável 55435: upgrade e73→f84, seed e **1.092 testes backend**
  aprovados; regressão específica cobriu mudança da cue após fila, ausência
  legada na API e job legado no worker sem chamada ao provedor.
- **348 testes frontend**, lint, TypeScript, build e orçamento aprovados; bundle
  permaneceu dentro do teto de 172 KiB gzip.
- **88 testes operacionais**, Ruff e mypy aprovados; OpenAPI e tipos TypeScript
  regenerados. O smoke de papéis mantém `SELECT` direto do worker proibido e
  acrescenta somente a projeção autorizada.
- Nenhum provedor foi chamado. DEV e estudo não receberam migration, flag,
  backfill, seed ou escrita. A migration foi aplicada apenas ao banco descartável.

### Pendências reais

Na conclusão de 40B.2d, a Sprint 40 permanecia parcial e as referências
posicionais ainda bloqueavam reordenações; o incremento 40B.2e abaixo resolve os
vínculos, mas não autoriza a mutação editorial. Interfaces completas de
prática/checkpoint e arquivados, cache/offline, exclusão pessoal/backups e rollout
ensaiado continuam pendentes. As 63 rubricas semanticamente diferentes seguem
dependentes de versão e homologação pedagógica.

## Sprint 40B.2e — vínculos editoriais estáveis em 15/10/2026

### Escopo executado

- migration `a06f2ce1487b` no PostgreSQL descartável `aulas_ingles_test`, porta
  55435; nenhum comando de migration/seed foi dirigido a DEV ou estudo;
- backfill de 82 vínculos mídia→exercício e 16 vínculos checkpoint→mídia;
- FKs compostas validam mesma aula para exercício e mesmo curso/aula para
  checkpoint, preservando a dependência legítima 40–44 → Aula 40;
- API de checkpoint lê os IDs novos; mídia expõe `listening_exercise_id` e mantém
  a posição legada somente como campo obsoleto;
- seed transforma a coordenada congelada da baseline no UUID editorial antes do
  diff e aceita chaves explícitas para pacotes futuros.

### Ensaios de migration e segurança

1. A primeira tentativa recusou um vínculo que a regra inicial restringia à mesma
   unidade. A transação foi revertida sem schema parcial. A inspeção agregada mostrou
   somente o checkpoint 40–44 → Aula 40; a constraint foi corrigida para mesmo curso.
2. Upgrade e seed idempotente passaram. Downgrade imediato para f84 e re-upgrade
   passaram sem perda.
3. A posição do exercício ID 5 foi alterada temporariamente de 4 para 999999 no
   banco descartável. O downgrade foi recusado com a mensagem de vínculo divergente,
   Alembic permaneceu em `a06f2ce1487b` e a posição foi restaurada para 4.
4. `alembic check` não encontrou operações novas. Testes SQL/ORM rejeitaram mídia
   apontando para exercício de outra aula e checkpoint apontando para outro curso.

### Validação

- regressão completa: **1.097 testes backend** aprovados; a repetição integral
  ficou verde após tornar explícita a junção checkpoint→unidade na exportação;
- testes focais: 49 de seed/vínculos e 46 de aulas/checkpoints aprovados;
- regressão frontend: 348 testes, lint, TypeScript, build e orçamento total de
  172,0 KiB gzip aprovados;
- operações: 88 testes e 80 subtestes aprovados;
- Ruff e mypy aprovados; OpenAPI e tipos TypeScript regenerados.

### Limites e próximos passos

Nenhuma aula/exercício foi reordenado. As colunas legadas não devem ser usadas por
novas integrações, mas ainda não podem ser removidas. O seed continua `insert_only`
e bloqueia alterações existentes: ainda faltam contrato de nova versão/reordenação,
diff de impacto completo, interfaces históricas/arquivados, cache/offline, exclusão
pessoal e rollout com backup/restore. DEV e estudo permanecem no schema anterior.

## Sprint 40B.2f — prévia controlada de reordenação em 15/10/2026

### Contrato implementado

O comando abaixo é exclusivamente de leitura:

```sh
make editorial-reorder-plan
# pacote alternativo montado ao lado de courses.json:
make editorial-reorder-plan file=/app/seed-candidate/lessons.json
```

Ele compara o pacote completo com um snapshot consistente do banco. São elegíveis
somente `exercise`, `lesson_media`, `transcript_cue`, `vocab_item`,
`writing_prompt` e `course_review_question`, pois possuem UUID editorial persistido.
Para cada coleção, os mesmos UUIDs devem ocupar uma permutação das posições antigas.
Conteúdo, vínculo e pai não podem mudar. Cue é agrupada pela mídia; questão, pelo
checkpoint; os demais tipos, pela aula.

Reordenação de aula exige uma `lesson_version` N+1, revisada/publicada e com
`reviewed_at` comprovado. Reordenação de questões exige `content_version` N+1 no
checkpoint. Versão isolada, salto de versão, criação, omissão, edição semântica,
movimento entre pais e tipos posicionais sem UUID são recusados.

### Saída e privacidade

O JSON 1.2 informa posições anterior/nova, UUIDs, versões, bloqueios, hashes dos
catálogos e `plan_sha256`. Também conta referências diretas por FK para as entidades
afetadas. Apenas nomes de tabela/coluna e totais são retornados; texto pessoal,
respostas, e-mail, áudio e storage key nunca entram no relatório. `snapshot_at` é
informativo e não faz reserva.

### Barreiras e validação

- não há `--apply`, `--force`, `--delete`, endpoint HTTP ou configuração para
  habilitar escrita;
- sessão com transação/estado pendente é recusada;
- schema sem UUID persistido é marcado `legacy_projection` e bloqueado;
- execução usa `REPEATABLE READ, READ ONLY` e timeout;
- 13 testes focais passaram, incluindo inspeção das instruções SQL, preservação das
  sequências/linhas e recusas semânticas/versionais; a regressão completa terminou
  com 1.110 testes backend, Ruff e mypy aprovados;
- somente o PostgreSQL descartável na porta 55435 foi consultado. DEV/estudo,
  seeds reais e frontend permaneceram intactos.

### Limite ao final do 40B.2f (resolvido no 40B.2g)

O plano não autoriza SQL manual. Um apply futuro deverá receber o digest esperado,
confirmar o banco/operador/chave idempotente, reler o catálogo sob advisory lock
exclusivo e locks editoriais NOWAIT, resolver colisões de posição atomicamente,
gravar versão + recibo append-only e revalidar histórico/cache. Até isso existir,
o seed comum continua recusando toda alteração de conteúdo existente.

## Sprint 40B.2g — aplicação auditada de reordenação em 15/10/2026

### Barreiras de entrada

O apply não é continuação automática da prévia. Ele exige explicitamente:

```sh
EDITORIAL_REORDER_ENABLED=true python -m app.cli editorial-reorder \
  --file /caminho/isolado/lessons.json \
  --plan-sha256 HASH_DA_PREVIA \
  --operation-key UUID_V4_NOVO \
  --operator IDENTIFICADOR_DO_OPERADOR \
  --reason pedagogical_sequence \
  --confirm-database NOME_EXATO_DO_BANCO \
  --apply
```

Motivos aceitos: `pedagogical_sequence`, `accessibility_sequence` e
`curriculum_reorganization`. A flag é false por padrão. `prod` e perfil `public`
são recusados por código, e o papel conectado precisa ser proprietário/migrador.
Runtime, worker e tokens de aluno não executam a operação.

### Transação

1. Confirma isolamento READ COMMITTED, banco, migration e owner.
2. Adquire o mesmo advisory lock exclusivo usado por seed/arquivamento.
3. Congela as 19 tabelas editoriais com `SHARE ROW EXCLUSIVE NOWAIT`.
4. Relê o catálogo e exige o mesmo `plan_sha256` ainda permitido.
5. Move no máximo 500 entidades para posições temporárias acima do máximo da tabela.
6. Grava posições finais e a versão N+1 da aula/checkpoint.
7. Relê todo o grafo e compara o hash do estado aplicado com a projeção da prévia.
8. Insere `editorial_reorder_event`; commit publica posição, versão e recibo juntos.

Qualquer erro reverte tudo. A operação não atualiza IDs, respostas pessoais,
snapshots, tentativas ou resultados. Referências pessoais diretas são somente
contadas e registradas de forma agregada.

### Idempotência e auditoria

`operation_key` identifica uma única solicitação. Repetir chave, hash, pacote,
operador e motivo devolve o recibo já persistido. Reutilizar a chave com qualquer
divergência é recusado. O recibo registra os três hashes (catálogo anterior, pacote
candidato e catálogo efetivamente projetado), identidades SQL, mudanças e versões.
Trigger impede UPDATE/DELETE; downgrade recusa auditoria não vazia.

### Evidências

- 27 testes focais e **1.124 testes backend** aprovados, incluindo exercício e
  checkpoint; Ruff e mypy também passaram;
- tentativa pessoal continuou ligada ao mesmo exercício após a troca;
- falha injetada no recibo restaurou posições/versão e não deixou evento parcial;
- admissão de estudo concorrente bloqueou o apply até liberar o lock;
- Alembic sem drift; downgrade vazio, re-upgrade e seed idempotente aprovados;
- laboratório de papéis aprovado: migrador aplicou/repetiu dentro de rollback,
  runtime/worker não acessaram auditoria e backup permaneceu somente leitura;
- 88 testes operacionais e 80 subtestes aprovados;
- laboratório encerrado preservando apenas volume sintético.

Nenhum seed candidato real foi produzido ou aplicado. DEV e ambiente de estudo não
receberam migration, flag ou reordenação. Antes de qualquer rollout ainda são
obrigatórios pacote pedagógico homologado, prévia atual, backup/restore, ensaio de
interface/cache e janela de manutenção.

## Sprint 41A — sonda local de performance em 15/10/2026

A sonda é desligada por padrão. Para uma execução local deliberada, defina
`PERFORMANCE_PROBE_ENABLED=true` no `.env` e recrie somente a API. Não habilite a
flag no perfil público nem em produção; a validação de configuração recusa ambos.

```sh
docker compose --env-file .env -f infra/compose.yml up -d --force-recreate api
curl -sS -D - -o /dev/null \
  http://localhost:8010/api/courses/voa-level-1/lessons/31
```

Headers esperados: `X-Perf-SQL-Queries`, `X-Perf-Response-Bytes`,
`X-Perf-Duration-Ms`, `X-Perf-Pool-Checkouts` e `Server-Timing`. O evento
`app.performance` repete as mesmas agregações no log JSON, correlacionado por
request-id. Ele não inclui SQL, parâmetros, query string ou corpo.

Baseline do teste descartável: lista de aulas com 1 SQL; detalhe da Aula 31 com 15
SQLs, 14.435 bytes e 1 checkout depois da correção (18 SQLs antes). A duração de
uma chamada fria/isolada não deve ser usada como p50/p95. Desabilite a flag e
recrie a API ao terminar a coleta.

## Sprint 41B — baseline autenticada do painel Hoje em 15/10/2026

Com uma conta sintética nova e Level 1 publicado, a rota `/api/me/today` executou
38 SQLs, respondeu 493 bytes e usou um checkout. A causa comprovada foi o loop por
checkpoint combinado a entidades ORM completas. Depois do anti-join e das projeções,
o mesmo cenário executou 8 SQLs e manteve payload/checkouts.

O teste `test_today_baseline_does_not_query_each_checkpoint_or_full_lesson` fixa o
teto de 8. Testes funcionais cobrem retomada, revisão vencida, checkpoint, mudança
de versão e cursos diferentes. A duração isolada variou de aproximadamente 98 ms
antes para 37 ms depois, mas não constitui distribuição, benchmark concorrente ou
SLO. Não comparar esses números entre máquinas como se fossem p95.

## Sprint 41C — paginação do Caderno em 15/10/2026

A interface usa `/api/me/notebook/page?limit=20`. Para inspecionar manualmente sem
expor o token em histórico de shell, autentique-se pelo navegador, abra **Caderno**,
aplique curso/unidade/aula/tipo e use **Carregar mais anotações**. Confirme que os
itens anteriores continuam visíveis e que trocar qualquer filtro reinicia a lista.

O teste automatizado cria cinco notas com o mesmo `updated_at`, uma entrada de outro
tipo e uma nota de outra conta. As páginas 2/2/1 retornam os cinco ids em ordem
decrescente, sem vazamento, repetição ou lacuna. Cada resposta mede 2 SQLs no total
(autenticação + página), no máximo um checkout e confere o header de bytes. Cursor
malformado deve responder 422 com código `invalid_cursor`.

Comandos de validação:

```sh
cd backend
uv run pytest -q tests/test_pagination.py tests/test_notebook.py tests/test_performance.py
uv run pytest -q

cd ../frontend
npm test
npm run typecheck
npm run lint
npm run build
npm run check:budget
```

Resultado: 1.137 testes backend, 349 frontend, verificações estáticas e build
aprovados; bundle de 176.122 bytes gzip no limite de 176.128. Nenhum dado de DEV ou
do ambiente de estudo foi usado. Não adicionar índice com base nesta amostra: rode
primeiro o laboratório 1k/10k e registre planos, p50/p95, payload e concorrência.

## Sprint 41D — benchmark e índice do Caderno em 15/10/2026

O laboratório recusa DEV/produção e exige o marcador da base descartável. Ele usa
um advisory lock, cria contas com e-mails `.invalid`, não imprime conteúdo, SQL ou
tokens e remove exatamente as contas que criou. Execute:

```sh
make notebook-benchmark
```

O comando prepara migration/seed na base de teste e mede 30 amostras por cenário.
No ensaio de referência, 1 mil notas foram percorridas em 20 páginas e 10 mil em
200 páginas, sempre na ordem esperada e sem repetição ou lacuna. Cada resposta
usou 2 SQLs e no máximo um checkout. Uma rajada de 10 páginas profundas respondeu
10/10 com HTTP 200, em 48,63 ms de parede, p95 interno de 39,28 ms e pico de 10
conexões retiradas do pool.

Comparação da página profunda em 90% da massa de 10 mil:

| Medida local | Sem candidato | Com candidato |
| --- | ---: | ---: |
| Execução do plano | 2,047 ms | 0,124 ms |
| Blocos de cache somados | 706 | 40 |
| API p50 | 3,72 ms | 3,95 ms |
| API p95 | 5,44 ms | 7,64 ms |

O plano melhorou cerca de 93,9% e os blocos 94,3%. O p95 HTTP oscilou para cima,
mostrando que este ensaio local não deve virar SLO. Na primeira página de 10 mil,
o p50 interno caiu de 4,96 ms para 2,93 ms; o p95 ficou praticamente estável
(9,66 ms para 9,78 ms). Inserir 10 mil linhas custou 118,74 ms sem o índice e
135,81 ms com ele (+14,4%). O índice mediu 456 KiB em 11 mil linhas e 840 KiB em
21 mil.

A migration aprovada é `c82f4a9d117e`. Ela cria
`ix_notebook_entry_user_updated_id` com `CONCURRENTLY`. Se uma tentativa for
interrompida, não repita cegamente: consulte `pg_index` e `pg_get_indexdef`. A
migration recusa um índice homônimo inválido ou divergente. Remova somente esse
artefato com `DROP INDEX CONCURRENTLY` depois de confirmar alvo e definição; então
repita o upgrade. No banco descartável, foram aprovados:

```sh
cd backend
uv run alembic check
uv run alembic downgrade b71d4f9e20c3
uv run alembic upgrade c82f4a9d117e
uv run alembic check
uv run pytest -q tests/test_notebook_index_migration.py tests/test_notebook.py
```

DEV e ambiente de estudo não receberam essa migration durante o ensaio. Antes de
aplicá-la fora do teste ainda cabem backup verificado, inspeção de locks/capacidade
e janela operacional compatível com o runbook.

Na confirmação posterior à migration, a ferramenta detectou o índice definitivo e
não criou candidato. Ela percorreu novamente 10 mil itens em 200 páginas, mediu o
plano profundo em 0,067 ms e 45 blocos e concluiu uma rajada 10/10 em 46,37 ms,
com p95 interno de 28,77 ms. A regressão terminou com 1.138 testes backend e 91
testes operacionais; Ruff, mypy e `alembic check` também passaram.

## Sprint 41E — escrita paginada em 15/10/2026

O rascunho/autosave não contém mais versões aninhadas. Para inspeção autenticada,
abra uma atividade de escrita, crie mais de uma versão e use **Carregar mais
versões**. No **Caderno**, use **Carregar mais textos**; abra **Regras das análises
salvas** para consultar feedback somente sob demanda. Em cada ação, confirme que os
itens anteriores permanecem e que o status com a quantidade carregada recebe foco.

Contratos incrementais:

```text
GET /api/writing/prompts/{prompt_id}/versions?limit=20&cursor=...
GET /api/writing/prompts/{prompt_id}/feedback?limit=20&cursor=...
GET /api/writing/history/page?course=...&unit=...&limit=20&cursor=...
```

O teste automatizado empata timestamps e valida ordem `(created_at DESC, id DESC)`,
cursor 422, privacidade por conta e resumo sem `draft_text`. Orçamentos totais:
2 SQLs para versões, 4 para feedback/snapshots e 2 para resumo, com até um checkout.
O rascunho de prova fica abaixo de 1.000 bytes e não inclui `revisions`.

Comandos executados:

```sh
cd backend
uv run pytest -q
uv run ruff check app/api/writing.py app/schemas/writing.py tests/test_writing.py
uv run ruff format --check app/api/writing.py app/schemas/writing.py tests/test_writing.py
uv run mypy app

cd ../frontend
npm test
npm run typecheck
npm run lint
npm run build
npm run check:budget
```

Resultado: 1.139 testes backend e 351 frontend aprovados; bundle de 176.000
bytes gzip no teto preservado de 176.128. O ensaio usou apenas a base PostgreSQL
descartável. Não há migration de escrita: execute laboratório 1k/10k e compare
planos/custo de escrita antes de propor índice. Speaking e revisão são os próximos
históricos da Sprint 41.

## Sprint 41F — speaking paginado em 15/10/2026

No **Caderno**, a seção **Gravações mantidas** consulta:

```text
GET /api/speaking/attempts/page?course=...&unit=...&limit=20&cursor=...
```

Use **Carregar mais gravações** e confirme que os itens anteriores continuam
visíveis, o total carregado recebe foco e curso/unidade não se misturam. Reprodução
e exclusão continuam privadas; depois de excluir, somente o item removido sai do
acumulado. A rota `/api/speaking/attempts` continua disponível para compatibilidade.

A sonda registrou 22 SQLs na implementação ORM inicial. A projeção final usa 5
SQLs por página: autenticação, metadados projetados, jobs ativos, detecção da tabela
de snapshots e snapshots em lote. Todas as chamadas usaram um checkout. O teste
percorre cinco registros empatados em páginas 2/2/1, exclui `pending`, valida 422
para cursor inválido e compara os IDs de duas contas.

Comandos executados:

```sh
cd backend
uv run pytest -q
uv run ruff check app/api/speaking.py app/schemas/speaking.py tests/test_speaking.py
uv run ruff format --check app/api/speaking.py app/schemas/speaking.py tests/test_speaking.py
uv run mypy app

cd ../frontend
npm test
npm run typecheck
npm run lint
npm run build
npm run check:budget
```

Resultado: 1.140 testes backend, 352 frontend e contrato OpenAPI regenerado.
Bundle: 176.092 bytes gzip de 176.128 permitidos. O PostgreSQL descartável foi o
único banco usado; DEV e ambiente de estudo não foram consultados. Não criar índice
de speaking antes do laboratório 1k/10k com plano e custo de escrita.

## Sprint 41G — revisão suspensa paginada em 15/10/2026

Na página **Revisar**, a lista **Itens suspensos** consulta:

```text
GET /api/review/items/page?course=...&unit=...&limit=20&cursor=...
```

Use **Carregar mais** e confirme que a página anterior continua visível e o total
carregado recebe foco. Troque curso/unidade e confirme que itens e cursor não se
misturam. Reativar ou excluir deve remover somente o item escolhido. A rota antiga
`/api/review/items` permanece para compatibilidade.

A sonda deve registrar 2 SQLs por página, já incluindo autenticação, e no máximo
um checkout. O teste percorre cinco timestamps empatados em 2/2/1, valida filtros,
422 para cursor inválido e isolamento entre duas contas.

Comandos executados:

```sh
cd backend
uv run pytest -q
uv run ruff check app/api/review.py app/schemas/review.py tests/test_review.py tests/test_maintenance.py
uv run ruff format --check app/api/review.py app/schemas/review.py tests/test_review.py tests/test_maintenance.py
uv run mypy app

cd ../frontend
npm test
npm run typecheck
npm run lint
npm run build
npm run check:budget
```

Resultado: 1.141 testes backend, 353 frontend e contrato OpenAPI regenerado.
Bundle: 176.118 bytes gzip de 176.128 permitidos. Apenas o PostgreSQL descartável
foi usado. Não criar índice de revisão antes do laboratório 1k/10k com plano e
custo de escrita.

## Sprint 41H — benchmark e índice da revisão em 15/10/2026

O laboratório só aceita `aulas_ingles_test` com papel `aulas_test` e marcador
`aulas-ingles:disposable-test:v1`. Ele mantém advisory lock, cria contas `.invalid`,
não imprime tokens ou conteúdo e remove exatamente os usuários sintéticos. Execute:

```sh
make review-benchmark
```

O ensaio de referência percorreu 1 mil itens em 20 páginas e 10 mil em 200, sem
lacunas, duplicações ou ordem instável. Todas as páginas usaram 2 SQLs e até um
checkout. Para a página em 90% da massa de 10 mil:

| Medida local | Sem candidato | Com candidato |
| --- | ---: | ---: |
| Execução do plano | 2,299 ms | 0,305 ms |
| Blocos de cache somados | 1.795 | 56 |
| API p50 | 5,68 ms | 5,20 ms |
| API p95 | 12,41 ms | 8,39 ms |

O índice mediu 565.248 bytes com 11 mil linhas e 1.056.768 bytes com 21 mil. A
inserção única de 10 mil itens oscilou de 234,78 ms para 191,28 ms; esse valor não
é prova de escrita mais rápida porque cache e ordem do ensaio não foram
neutralizados. Os tempos HTTP também são diagnóstico local, não SLO.

A migration aprovada é `d41e7ac905b2`, que cria
`ix_review_item_user_status_created_id` com `CONCURRENTLY`. Se a criação for
interrompida, consulte `pg_index` e `pg_get_indexdef`; a migration recusa índice
homônimo inválido/incompleto/divergente em vez de removê-lo. Depois de confirmar
alvo e definição, remova somente esse artefato com `DROP INDEX CONCURRENTLY` e
repita o upgrade.

No banco descartável foram aprovados upgrade, downgrade para `c82f4a9d117e`,
re-upgrade, teste de definição e `alembic check`. A repetição reconheceu o índice
final, não criou candidato, percorreu outra vez as 200 páginas e respondeu 10/10
requisições concorrentes. DEV e ambiente de estudo não receberam a migration.
Antes de aplicá-la fora do teste: faça backup verificado, inspecione locks/espaço e
use janela operacional compatível com este runbook.

Fechamento automatizado: 1.142 testes backend e 94 testes operacionais aprovados;
Ruff dos arquivos em escopo, mypy e `alembic check` também passaram.

## Sprint 40C/40D — exclusão, histórico e fechamento técnico em 16/10/2026

### Exclusão da conta

Contrato HTTP:

```text
DELETE /api/me/account
202 { operation_key, state, database_deleted=true, audio_files_pending }
```

O pedido requer sessão, senha atual, UUID e a frase exata de confirmação. Argon2
roda antes da transação; dentro dela a API usa advisory lock por usuário, bloqueia
o perfil, revalida o hash, bloqueia as tentativas de fala e registra as chaves
opacas antes de apagar a conta. Cascades removem sessões e dados relacionais. A
resposta só ocorre depois do commit e apaga o cookie de refresh.

`account_deletion_job` é um recibo anônimo; `account_deletion_file` é a fila
temporária. O worker a processa antes das transcrições com `SKIP LOCKED`, unlink
idempotente, espera exponencial e dez tentativas. `failed` permanece observável no
heartbeat agregado. Não há e-mail, texto, `user_id` ou caminho completo nesses
registros. Downgrade é recusado enquanto houver recibos.

No navegador, a limpeza privada é outra ação. Ela remove somente o namespace da
conta atual e grava tombstone no IndexedDB antes de reescrever fontes legadas. Cache
editorial público, servidor e outras contas permanecem. A exclusão remota não alega
apagar downloads, outros dispositivos ou abas inacessíveis.

Política aprovada: [exclusão e backups em DEV](politica_exclusao_e_backups_dev_2026-10-16.md).
RPO 24 h, RTO 60 min e retenção 7 diários + 4 semanais são metas a validar. Backups
ficam neste Mac durante desenvolvimento e podem reter a conta até expirar; restore
fica isolado e nunca é promovido diretamente.

### Histórico e conclusão

`GET /api/me/history/page` pagina apenas metadados dos snapshots da conta, em ordem
`created_at DESC, id DESC`, cursor opaco e limite 1–100. O JSON pesado só sai em
`/api/me/history/{kind}/{evidence_id}/content`, sob demanda. A central no Caderno
abrange exercício, prática, escrita, fala e checkpoint, não depende do catálogo
publicado e não cria link para aula arquivada. Legado sem snapshot permanece
indisponível; conteúdo atual nunca o substitui.

A regra de elegibilidade passou a declarar `course-certificate-v1`. O frontend
explica que a tela calcula o estado atual, não altera histórico, não emite arquivo
e não redefine os critérios externos da VOA.

### Evidências executadas

- 1.156 testes backend aprovados na segunda suíte completa;
- a primeira suíte completa encontrou sete falhas de tempo após salto observado de
  aproximadamente 15 minutos no mesmo teste; os nove casos parametrizados afetados
  passaram isoladamente e a repetição completa passou sem falhas;
- 360 testes frontend, ESLint, TypeScript e build de produção aprovados;
- bundle final de 175,7 KiB gzip, com teto explícito de 178 KiB e limites
  individuais de 140 KiB JS/15 KiB CSS preservados;
- 94 testes operacionais puros aprovados;
- laboratório de papéis real aprovou recusas, DML runtime, worker, API, snapshots,
  cotas/retenção e dump limitado; containers encerrados, volume sintético preservado;
- Ruff completo, mypy dos 90 módulos, `alembic check` e head
  `a42c7d1e9f20` aprovados no banco descartável;
- OpenAPI e tipos TypeScript foram regenerados; `git diff --check` passou.

Não houve seed, arquivamento, exclusão real, chamada a provedor, alteração de `.env`,
migration em DEV/estudo, commit, push ou merge. O fechamento é técnico no código e
nos laboratórios. Homologação pedagógica das rubricas e testes físicos da Sprint 41
continuam pendentes e não foram marcados como aprovados.
