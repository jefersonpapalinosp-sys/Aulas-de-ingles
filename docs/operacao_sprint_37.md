# Operação local — Sprints 37 e 38

Escopo: desenvolvimento no Mac de Jeferson. A stack aulas-ingles-prod em
localhost:5181 é **produção local**, não serviço público. Desenvolvimento em
5180 não faz parte da manutenção. Nunca executar pytest/E2E nessas bases.

Estado vigente: Sprint 38 em 5181, schema d06a4e9cb153. O registro da Sprint 38
está no final deste documento. Os comandos da seção Sprint 37 são históricos;
não devem ser repetidos como atualização genérica para sprints posteriores.

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
**Nenhuma exclusão, rotação de senhas ou limpeza automática foi instalada.**
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
