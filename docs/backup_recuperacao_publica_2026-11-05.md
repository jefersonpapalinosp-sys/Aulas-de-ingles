# Backup e recuperação pública — Sprint 54

Código preparado em 05/11/2026. A instalação do timer, a custódia da chave, o
recebimento do alerta e o ensaio em uma VM nova ainda precisam de aceite operacional.
O histórico do Mac em `deploy_easypanel.md` não comprova essas novas etapas.

## Rotina no servidor

Usar Linux com Docker local, Python 3.12+, `age`, `tar` e `git`. O checkout aprovado
fica em `/opt/aulas-ingles`, legível pelo usuário `aulas-ops`, que precisa operar o
Docker. Preparar `/var/lib/aulas-ops` privado (0700), o diretório de backups do
checkout gravável por esse usuário e um destino externo montado em
`/mnt/aulas-backups`. Um segundo diretório no mesmo disco não atende à custódia
externa; conferir o mount e seu domínio de falha antes de ativar a rotina.

Guardar somente o destinatário público `age1...` em
`/etc/aulas-ops/backup-recipient.txt`. A chave privada deve ter duas cópias em
custódias independentes da VM e da máquina usada para operar: registrar responsáveis,
acesso de emergência e prova de decifragem. A rotina nunca precisa da chave privada.
Não remover a chave histórica antes de testar as cópias e abrir um backup antigo.

Revisar e instalar `infra/systemd/aulas-backup.service` e `.timer` em
`/etc/systemd/system/`. Os caminhos são modelos; adaptar o checkout ao host real.
Executar primeiro o serviço manualmente e conferir o recibo/cópia externa; depois
habilitar o timer. A agenda é 06:10 e 18:10 UTC, com até cinco minutos de variação
e compensação após desligamento (`Persistent=true`). Não desativar o launchd antigo
até comprovar duas execuções consecutivas e a recuperação pela nova rotina.

```sh
sudo systemctl daemon-reload
sudo systemctl start aulas-backup.service
sudo systemctl status aulas-backup.service
sudo systemctl enable --now aulas-backup.timer
sudo systemctl list-timers aulas-backup.timer
```

O modo `--host local` lê os containers da stack pública no daemon da própria VM.
Para um runner separado, usar `--host usuario@host` com a chave SSH e o host já
conferido no `known_hosts`. O modo SSH conserva a validação estrita de identidade.

`backup_watch` grava o início da tentativa como pendente/falha antes da captura.
Só atualiza `last_success_at` depois de criar, verificar, cifrar e copiar o pacote.
Falha ou interrupção não renova o sucesso anterior. O lock do agendador usa `flock`
e é liberado pelo kernel; duas execuções não devem compartilhar a rotina simultaneamente.

Configurar o cron operacional com `config/operations-watch.env.example` e
`infra/cron/aulas-operations.example`. O usuário do cron deve ler o status privado.
`OPERATIONS_BACKUP_STATUS_FILE=/var/lib/aulas-ops/backup-status.json` e
`--require-backup` tornam ausência, arquivo inválido, data futura, tentativa falha
ou idade maior que 24 horas um check crítico `last_backup_age_hours`.
Esse check é calculado pelo gate do host; não é um novo endpoint da API.
Validar a entrega do MTA/MAILTO com uma falha sintética de status antes de depender
do alerta em até cinco minutos. O workflow remoto sem acesso ao arquivo não atesta
a idade do backup; o cron da VM é o monitor dessa evidência.

## Consistência e retenção

O dump e as contagens do manifesto compartilham um snapshot PostgreSQL exportado.
Novos eventos de estudo podem ocorrer durante a captura; mudanças na revisão,
nas referências de voz ou nos containers interrompem a publicação. A checagem de
inventário/checksum continua obrigatória. Uma mudança de voz pode exigir nova
tentativa; o processo não para a aplicação automaticamente.
Referência: [snapshot sincronizado do PostgreSQL 16](https://www.postgresql.org/docs/16/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION)
e [pg_dump --snapshot](https://www.postgresql.org/docs/16/app-pgdump.html).

Antes de migration, criar a cópia com `hold=true` (ou `--hold` na CLI):

```sh
make backup source=public hold=true recipient=/etc/aulas-ops/backup-recipient.txt copy_to=/mnt/aulas-backups
```

O hold fica em `.holds/IDENTIFICADOR`, fora do pacote, e protege tanto a cópia local
quanto as cifradas produzidas nessa execução. A política mantém o mais recente,
sete diários e quatro semanais, além dos holds. Um segundo backup no mesmo dia não
libera o pré-migration. Não remover hold enquanto o plano de retorno depender dele.

```sh
python3 -m ops.recovery prune --json
python3 -m ops.backup_policy prune-encrypted /mnt/aulas-backups
# Após revisar a lista concreta:
python3 -m ops.backup_policy prune-encrypted /mnt/aulas-backups --apply
# Liberação explícita, repetir em cada raiz que contém o hold:
python3 -m ops.backup_policy hold /mnt/aulas-backups IDENTIFICADOR --release --confirm IDENTIFICADOR
```

A poda cifrada só considera arquivos de nome reconhecido com recibo `.verified/`
e checksum correspondente. Cópias anteriores a esta versão e parciais sem recibo
ficam fora da política, preservadas para revisão. Recibos e arquivos desconhecidos
não são removidos. Aplicar também a política no diretório cifrado local; não instalar
poda automática antes de revisar sua primeira prévia.

Se uma operação antiga deixar um container de lock após crash, interromper o
processo proprietário e seus subprocessos, conferir o ID completo e a idade do
lock. A ferramenta exige ao menos uma hora, o rótulo correto e confirmação explícita;
idade sozinha não prova que o dono terminou. No daemon onde o lock está:

```sh
python3 -m ops.recovery lease-break restore --confirm-id ID_COMPLETO --confirm-owner-stopped
# Para restore público, o nome do lease é o nome aulas-dr-... da stack.
```

## Recuperação em uma VM nova

1. Declarar o incidente, bloquear novas escritas e preservar a origem. Selecionar
   a cópia externa e seu recibo confiável; registrar o horário da decisão e o
   ponto de recuperação. Confirmar o impacto dos dados posteriores ao backup.
2. Recuperar o checkout e as imagens correspondentes ao manifesto. Guardar as
   imagens aprovadas em registro/arquivo externo: IDs no manifesto não são uma
   cópia das imagens. Restaurar configuração e segredos da custódia separada;
   o pacote contém banco e voz, não esses segredos.
3. Provisionar a VM e a stack a partir de `infra/easypanel/compose.yml`, usando
   **nome novo `aulas-dr-IDENTIFICADOR`**, sem apontar DNS/Traefik para ela. Usar
   PostgreSQL 16 compatível e as imagens registradas; não executar migrations,
   seed, worker ou aplicação sobre o destino antes do restore. Criar os containers
   `api`, `worker` e `web` parados, e subir somente `db`. O entrypoint do banco
   prepara os papéis; os volumes `pgdata` e `speaking_data` devem ser novos e ter
   os rótulos desse projeto. Não reaproveitar nomes/volumes de produção.
4. Na estação de recuperação, com disco privado e chave obtida da custódia,
   decifrar para um diretório novo. O `unseal` recusa links, traversal, duplicatas,
   conteúdo extra e checksums divergentes. Não usar `tar -xf` genérico.

   ```sh
   python3 -m ops.public_restore unseal /externo/IDENTIFICADOR.tar.age --identity /custodia/identity.txt --output /privado/aberto
   python3 -m ops.public_restore restore /privado/aberto/IDENTIFICADOR --host operador@VM-NOVA --project aulas-dr-IDENTIFICADOR --confirm operador@VM-NOVA/aulas-dr-IDENTIFICADOR --receipts /privado/recibos
   ```

5. O restore verifica a identidade dos containers/volumes, a imagem da API,
   ausência de clientes SQL, banco vazio e voz vazia. Carrega com `aulas_migrator`
   assumindo `aulas_owner`, reaplica os grants e verifica snapshot e hashes de voz.
   O recibo mede a recuperação do par banco/voz. Em falha, preservar o destino
   parcial para diagnóstico; não tentar sobrepor nem executar limpeza destrutiva.
6. Com o recibo aprovado, validar privilégios efetivos, iniciar API/worker e
   conferir health, readiness, autenticação, leitura do áudio e retomada da fila
   com conta de ensaio autorizada. Se precisar atualizar schema, usar o processo
   de migration em clone. Só então promover o tráfego/DNS e testar o acesso HTTPS.
   Registrar tempo total até serviço disponível, incluindo obtenção da chave,
   provisionamento, imagens, decisão e propagação do tráfego.
7. Rotacionar credenciais quando indicado pelo incidente, ativar backup/alertas
   na nova VM e manter a origem protegida até encerrar a investigação.

O ensaio local provou a carga e a integridade de dados sintéticos. Ele não mede
provisionamento de VM, recuperação de imagens, SSH, custódia, DNS ou tráfego real.
A meta de RTO de 60 minutos e o aceite operacional da Sprint 54 permanecem pendentes
desse exercício completo; não extrapolar os segundos do laboratório para produção.

## Repetir o ensaio de código

Em um host Linux de desenvolvimento, construir a imagem de desenvolvimento
`aulas-ingles-api:latest` do backend e depois as ferramentas. O controlador precisa
do socket Docker local e cria somente recursos UUID com dados sintéticos. Não
executá-lo no daemon de produção. Os arquivos do repositório entram somente leitura.

```sh
docker build -t aulas-ingles-api:latest backend
docker build -f infra/Dockerfile.recovery54 -t aulas-ingles-recovery54-tools:local .
mkdir -p /tmp/aulas-recovery54-lab
docker run --rm --network none \
  -e AULAS_PUBLIC_RECOVERY_LAB=synthetic-only \
  --mount type=bind,src="$PWD",dst=/work,readonly \
  --mount type=bind,src=/tmp/aulas-recovery54-lab,dst=/tmp \
  --mount type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock \
  aulas-ingles-recovery54-tools:local -m ops.tests.public_recovery_lab
```

O ensaio cifra/decifra com `age` real, grava uma segunda conta durante o snapshot
e confirma que o dump contém somente a primeira. Usa os papéis reais, restaura
WAV sintético e compara hashes. Remove containers que criou; em sucesso, remove
seus volumes após conferir rótulos. Em falha preserva volumes. Dumps e chaves
gerados são sintéticos e ficam no diretório temporário para diagnóstico.
