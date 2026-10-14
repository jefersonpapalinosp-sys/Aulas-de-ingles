# Sprints de banco de dados para integridade e recuperação

Atualização: 14 de outubro de 2026. **DB-38 implementada, ensaiada e aplicada na base de estudo após autorização, backup e restore isolado.** Divergências antigas de jornada foram preservadas e estão documentadas, sem reconciliação automática. DB-39 a DB-42 permanecem planejados. As metas RPO/RTO não são SLA.

Referência: [auditoria técnica](auditoria_tecnica_frontend_backend_banco_2026-10-13.md). Este plano abrange PostgreSQL, migrations, seed, papel da aplicação e consistência com o armazenamento privado de voz. O primeiro incremento cria apenas um ambiente de teste separado; não modifica o banco de estudo nem seus papéis atuais.

Na fotografia inicial da auditoria, o banco observado estava no head `b84e2c7a9d31`, com 40 tabelas no schema público e 82 aulas. O segundo incremento levou **somente a base descartável** a `c95f3d8ba042`. Os problemas tratados são preservação operacional, concorrência, rastreabilidade e escala, não falta de conteúdo curricular.

## Sequência e dependências

| Pacote | Resultado | Prioridade | Integração |
|---|---|---|---|
| DB-37 | Bases isoladas, backup verificável e papéis mínimos | P0/P1 | Precede testes integrados das demais frentes |
| DB-38 | Estado concorrente e eventos idempotentes | P1 | BE-38 e FE-38 |
| DB-39 | Tempo por período, cota e ciclo de vida da voz | P1 | BE-39 e FE-39 |
| DB-40 | Versões editoriais e exportação íntegra | P1/P2 | BE-40 e FE-40 |
| DB-41 | Índices comprovados e invariantes validadas | P2 | BE-41 e FE-41 |
| DB-42 | Upgrade e recuperação ensaiados | P1/P2 | Gate final de release |

As propostas de novas tabelas abaixo descrevem responsabilidades. Os nomes e colunas finais dependem do contrato refinado, não são autorização para executar DDL.

## Sprint 37 Isolamento proteção e backup

Achados D01, D02 e D03. Esta é a primeira entrega obrigatória antes de rodar a suíte backend sobre qualquer base com dados de estudo.

### Entregas

- [x] Criar banco, role e volume exclusivos de teste, sem compartilhar `aulas_ingles` de desenvolvimento nem produção local.
- [x] Implementar guardas cruzadas para pytest/seed/Alembic de teste: ambiente, nome/marcador de base descartável e papel limitado; nenhum fallback automático para banco real.
- [x] Revisar `make test-api`, `make cov`, CI backend e instruções de README para selecionar e preparar o alvo descartável.
- [x] Isolar a stack E2E local e revisar seu alvo padrão; Compose próprio e guardas antes da suíte impedem uso acidental de dev/prod.
- [x] Restringir o papel de teste ao próprio banco. Guardar privilégio de criação/remoção de bases na etapa de provisionamento, não no processo normal de testes.
- [x] Separar papel runtime, worker, proprietário/migrador e backup; verificar qual usuário API/worker realmente usam antes de alterar grants.
- [x] Implementar inventário do PostgreSQL e volume de voz, com manifesto ligando dump, binários, checksums, schema e identidade de imagens/worktree; validar pacote sintético e backup real da produção local.
- [x] Corrigir receita de backup para abortar por exit code, escrever pacote temporário, validar e publicar somente backup completo; nome único evita colisão no mesmo minuto.
- [x] Definir armazenamento protegido, retenção, criptografia e política de cópia externa: responsável aprovou permanecer no Mac nesta fase de desenvolvimento; risco explicitado no runbook.
- [x] Criar comando de restore com alvo explícito e confirmação, validação do manifesto e recusa de destino ocupado; nesta entrega, somente ambiente vazio separado é permitido, sem restore destrutivo de produção.

### Critérios de aceite

1. Configuração apontando para desenvolvimento/produção é recusada antes de DELETE/TRUNCATE/migration de teste.
2. Um conjunto sentinela criado em base de demonstração permanece inalterado após a suíte rodar em outra base descartável; nunca usar a base real para esse teste.
3. Falha simulada do `pg_dump` retorna erro ao shell/CI e não deixa arquivo anunciado como backup válido.
4. Dois backups no mesmo minuto produzem artefatos diferentes e verificáveis.
5. Restaurar em ambiente isolado recupera um áudio sintético cujo checksum e referência no banco conferem.
6. Runtime consegue DML necessário, mas não criar role, banco, tabela ou alterar schema; migrador continua apto a executar migrations.
7. RPO e RTO têm valor acordado e responsável; metas não são inventadas como SLA já existente.

### Cuidados de rollout

Não revogar o papel atual antes de ensaiar grants e credenciais novas. Preservar um caminho administrativo de recuperação e não publicar segredos em documentação. Não executar receitas antigas de restore sobre produção como “teste de backup”; o novo `make restore` só permite laboratório vazio.

Fora do escopo: rotação imediata não coordenada de credenciais, apagar dados de teste existentes em produção ou migrar para banco gerenciado.

### Registro de execução — primeira entrega, 13/10/2026

- Novo projeto `aulas-ingles-test`, porta `127.0.0.1:55435` e volume próprio.
- Base `aulas_ingles_test` marcada como descartável; migrations/seed/pytest usam
  `aulas_test`, proprietário dessa base, sem poderes administrativos globais.
- Base sentinela apenas sintética, com conexão negada ao papel de teste. Nenhuma
  base do estudante foi usada como sentinela ou como fixture.
- PostgreSQL 16.15, mesma versão das stacks existentes; sem nova migration de
  produto nem mudança nas credenciais de desenvolvimento/produção.
- Backup com voz, restore seguro, papéis runtime/worker/migrador/backup e
  isolamento de E2E permanecem abertos; DB-37 não está concluída.

Validação desta primeira entrega: 279 testes backend aprovados (93,65% de
cobertura), repetidos com sucesso via `make test-api` em `Pacific/Kiritimati`;
migrations de instalação até `b84e2c7a9d31`; seed de 82 aulas
reaplicado sem erro; metadados confirmam papel limitado e marcador; sentinela
preservada após execução. O downgrade de catálogo semeado foi recusado pela
guarda histórica de ambiguidade entre cursos, mantendo o head por rollback;
isso não é ensaio de recuperação de backup nem aprovação de downgrade.
Detalhes e limites estão no [registro BE-37](sprints_37_42_backend_2026-10-13.md#registro-de-execução--primeira-entrega-13102026).

### Apoio à escrita v2 — segundo incremento, 13/10/2026

Migration aditiva `c95f3d8ba042` acrescenta versão do algoritmo, hash da rubrica
e snapshot do contrato utilizado a `writing_feedback`. Dados antigos recebem
`legacy-v1` e snapshot nulo; checks, texto e evidências não são recalculados.
Um ensaio em schema transacional sintético confirma preservação dos registros
anteriores, roundtrip só com legado e recusa de downgrade quando há resultado v2.
A API explicita as três informações no histórico e na exportação; edição
posterior da proposta não muda o snapshot já guardado.

Aplicação limitada ao banco de teste, sem mudanças nas bases de estudo. Não
confundir esse snapshot de escrita com a entrega editorial geral DB-40: exercícios,
checkpoints, áudio e exclusões pelo seed continuam exigindo trabalho próprio.
Backup/voz, papéis de produção e isolamento E2E da DB-37 seguem pendentes.

Atualização do quarto incremento frontend: a fila offline agora usa IndexedDB
no navegador. Os 3 testes Chromium de duas abas (`cd e2e && npm run test:queue`)
usam servidor exclusivo e API simulada, sem conexão ao PostgreSQL. Essa suíte
não fecha o isolamento da stack E2E integrada acima. Nenhum schema, seed,
serviço ou dado da base de estudo foi alterado nessa etapa. Retenção de recibos
locais e cópias legadas da fila deve acompanhar a política FE-40/DB-40.

Regressão final: 668 testes backend aprovados, cobertura de 93,79%; 82 propostas
e 247 critérios carregados na base descartável. Nenhuma reavaliação ou atualização
de evidência histórica foi executada nas bases do estudante.

### Sexto incremento — stack E2E isolada, 13/10/2026

`infra/compose.e2e.yml` cria projeto `aulas-ingles-e2e`, web em
`127.0.0.1:5198`, banco sem porta publicada e dois volumes exclusivos:
`aulas-ingles-e2e_pgdata` e `aulas-ingles-e2e_speaking_data`. Nenhum volume
global de `compose.prod.yml` é herdado. O arquivo `infra/e2e.env` é
intencionalmente vazio de segredos; não são lidos `.env` ou `.env.prod`.

O backend usa a mesma identidade restrita e o marcador descartável da suíte
pytest, mas em **outro servidor e outro volume**, não na base de 55435.
Migrations e seed passam por `app.testing prepare`; a API aguarda a conclusão
com sucesso, e o nginx aguarda a saúde real da API. As imagens usam os
Dockerfiles de produção com tags E2E próprias; `APP_ENV=test` habilita as
guardas e a assistência externa fica desligada, sem worker neste escopo.

`make e2e-up` verifica volumes preexistentes antes de iniciar a stack;
subida/parada e testes exigem daemon local via socket Unix (macOS/Linux),
recusando contextos/`DOCKER_HOST` TCP ou SSH antes de acessar recursos.
`make e2e-check`, `make test-e2e` e o setup global do Playwright verificam
projeto, rede, portas, mounts, origem do init SQL, labels/driver/opções dos
volumes e configurações da API. `app.testing check` confirma a identidade e
os privilégios reais da conexão, e um GET sem redirecionamento confirma o
readiness na origem exclusiva. A base sentinela **sintética** é lida antes e
depois da suíte, sem consultar dados pessoais do estudante.

Não basta apontar `E2E_BASE_URL` para outro lugar: qualquer valor diferente
de `http://127.0.0.1:5198` é recusado antes dos testes. Falha de Docker,
metadados ou readiness também bloqueia a execução, sem fallback. O CI E2E
passa a usar os mesmos comandos e encerra apenas a stack descartável.
`make e2e-down` preserva os volumes; não existe reset automático com `down -v`.

As guardas evitam erros operacionais; não protegem contra administrador que
modifique o daemon/recursos durante a suíte. O resultado não homologa a
configuração de produção, o worker assistido ou leitores de tela reais.

Validação local deste incremento:

- **48 testes de segurança aprovados**, sem banco: recusas de origem,
  endpoint Docker remoto, projeto, rede, portas, mounts, volumes sem marcador,
  storage redirecionado e configuração inadequada da API.
- `make e2e-up`: imagens próprias construídas, preparação concluída, API/web
  saudáveis e preflight aprovado. Identidade SQL: `aulas_ingles_test`, papel
  `aulas_test`, revisão `c95f3d8ba042`, exclusivamente no servidor E2E.
- **96 execuções Playwright aprovadas (48 cenários × desktop/mobile)** em
  uma rodada final completa de `make test-e2e`, sem retries locais, em 6 min.
  A sentinela sintética foi conferida no setup/teardown e permaneceu intacta.
  A rodada exploratória anterior teve 93 aprovações e três falhas dos testes
  antigos (espera de cadastro e leitura do corpo do envio); os ajustes e seus
  limites estão documentados em FE-37.
- Override real `E2E_BASE_URL=http://localhost:5181 npm test -- --list`
  recusado com exit code 1 antes da suíte; nenhum pedido ao ambiente real.
- `make e2e-down` encerrou somente os quatro containers E2E e sua rede,
  preservando os dois volumes. Depois disso, `make e2e-check` foi recusado
  conforme esperado (exit code 2 do Make), sem fallback nem início de testes.
  Dev, produção local e o banco pytest continuaram ativos nas portas originais.
- Compose validado, workflow aprovado pelo `actionlint` local e
  `git diff --check` sem erros. CI remoto não executado; não houve commit/push.
- O build repetiu o alerta de dependências de teste já registrado (um moderado
  e dois críticos). Nenhuma atualização major foi aplicada neste incremento.

Próximo incremento identificado naquela etapa: backup conjunto de PostgreSQL + voz, publicação
atômica/manifesto/checksums, falhas simuladas e restore em destino vazio
isolado. Papéis de produção e política de retenção/criptografia/RPO/RTO também
continuam abertos. Não executar o restore legado na base do aluno; o rollout
da escrita v2 nessa base continua dependendo do backup verificado.

Referências técnicas consultadas: [ordem de inicialização no Docker Compose](https://docs.docker.com/compose/how-tos/startup-order/),
[escopo e nomes de volumes](https://docs.docker.com/reference/compose-file/volumes/)
e [setup/teardown global do Playwright](https://playwright.dev/docs/test-global-setup-teardown).
O bloqueio de daemons remotos considera os [contextos Docker](https://docs.docker.com/engine/manage-resources/contexts/).

### Sétimo incremento — backup conjunto e restore isolado, 13/10/2026

#### Entrega operacional

`ops/recovery.py` e `ops/recovery_archive.py`, acionados pelo Make, substituem
as receitas antigas que copiavam só PostgreSQL e permitiam restore destrutivo.
Não há endpoint novo na API nem mudança em schema, seed ou componentes de estudo.

- Origem obrigatória `lab` ou `prod`, daemon Docker local Unix, projeto,
  imagem PostgreSQL 16.15, rede, mounts e volumes conferidos. No macOS, o
  alias exato `/host_mnt` do Docker Desktop é reconhecido; caminhos diferentes
  continuam recusados. Nenhuma configuração `.env.prod` é impressa.
- `prod` resolve banco/role dos metadados do container real. Exige API/worker
  parados, mounts coerentes, ausência de consumidores do volume e de outras
  conexões SQL, antes e depois da captura. **Não** para serviços nem encerra
  conexões automaticamente. Outros terminais/processos devem permanecer sem
  escrever durante a janela: as verificações não bloqueiam um administrador
  que modifique o ambiente entre elas.
- Dump custom via socket Unix interno, `pg_dump -Fc`, exit code e stderr
  verificados; aviso do dump também impede aprovação. `pg_restore --list`
  valida o índice do arquivo, não equivale a restaurar todos os blocos.
  Um snapshot de revisão, seis contagens de tabelas e referências de voz é
  comparado antes/depois; não é checksum de cada linha de todas as tabelas.
- Voz exportada em helper sem rede e com volume **somente leitura**. Arquivos
  planos, sem links, travessia de diretórios, especiais, nomes duplicados ou
  uploads `.tmp`; limites de 64 MiB/arquivo, 100 mil arquivos e 20 GiB de voz.
  Áudio referenciado ausente ou com tamanho divergente bloqueia publicação.
  Órfãos são conservados e contabilizados, nunca apagados por esta rotina.
- Diretório `.partial-*` privado, arquivos sincronizados, manifesto JSON,
  SHA-256 de dump/tar e de cada áudio, UUID + timestamp UTC com microssegundos
  e publicação por rename no mesmo filesystem. Falha deixa o parcial privado
  para investigação, retorna erro e não anuncia sucesso.
- Manifesto registra revisão Alembic, IDs de imagens, origem e `HEAD`/estado
  sujo do worktree. O `HEAD` local não é tratado como versão implantada;
  imagens/credenciais não são copiadas dentro do pacote. Banco lógico não
  inclui papéis globais, configuração do cluster ou arquivos externos à voz.

O backup usa o contrato de **manutenção sem escritores**, não snapshot online
atômico de PostgreSQL + filesystem. A consistência própria de `pg_dump`
não se estende a arquivos de áudio externos. Referência: [pg_dump 16](https://www.postgresql.org/docs/16/app-pgdump.html).

#### Laboratório, restore e falhas

`infra/compose.recovery.yml` cria projeto `aulas-ingles-recovery`, rede interna
sem portas publicadas e quatro volumes próprios (`source_db`, `source_voice`,
`target_db`, `target_voice`, prefixados pelo projeto). Origem usa o marcador
de teste e papel limitado `aulas_test`; destino `aulas_ingles_restore` usa
`aulas_restore`, sem superusuário, criação de banco/role, replicação ou bypass
de RLS. Seu marcador é `aulas-ingles:recovery-target:v1`.

O preparo aplica migrations/seed somente à origem inicialmente vazia e cria
um usuário sintético, uma tentativa de speaking e um WAV mono de **1 segundo
de silêncio**, sem voz humana. Não se conecta aos serviços de estudo.

O restore exige exatamente `confirm=aulas-ingles-recovery/target-db`, valida
o pacote antes de acessar Docker e confere identidade/limitação do papel.
Recusa objetos SQL existentes e qualquer arquivo no volume de destino. Usa
`--single-transaction --exit-on-error --no-owner --no-privileges`, sem `--clean`
ou criação/remoção de banco. Depois importa os áudios com criação exclusiva,
permissão 600 e UID 10001, sem `extractall`, e compara snapshot e hashes
restaurados. [Referência das opções de pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html).

Um recibo privado separado em `backups/recovery/restore-receipts/` registra o
hash do manifesto, alvo, quantidade de áudios e duração, sem modificar o
pacote original. A transação SQL **não** torna banco e filesystem uma única
transação: falha posterior à carga SQL pode deixar destino parcial, que deve
ser preservado e não recebe novo restore automaticamente. A rotina não limpa
destinos para contornar erros. O tratamento de arquivos não confia em nomes,
permissões ou links do tar: [riscos de extração](https://docs.python.org/3/library/tarfile.html#extraction-filters).

Locks por nome de container Docker serializam backups por origem e restores
no alvo fixo, inclusive entre clones. A liberação remove apenas o ID criado
pela operação, sem força. Interrupção abrupta pode deixar lock: primeiro
confira que a operação terminou e identifique o lock específico; não remova
containers/volumes por padrão ou por glob. Um destino parcial exige análise
e autorização para qualquer descarte; não existe comando de reset nesta entrega.

#### Evidência local e limites

- **29 testes unitários operacionais aprovados**, com subcasos para identidade,
  mounts, privilégio, daemon remoto, arquivos corrompidos/incompletos,
  caminhos/links inseguros, falta de áudio, permissões, falha/aviso do dump,
  colisão com relógio congelado, locks e destino ocupado. Falha simulada do
  comando de dump chega ao shell como erro, sem pacote publicado.
- Ensaio real com PostgreSQL 16.15: **2 backups distintos no mesmo minuto**
  (13/10/2026 às 22:38 BRT; IDs em UTC `20261014T013833...` e
  `20261014T013835...`), íntegros. Restore recuperou **82 aulas, 1 usuário,
  1 tentativa e 1 WAV sintéticos**, revisão `c95f3d8ba042`; seis contagens,
  referências, tamanho e SHA-256 do áudio iguais aos da origem.
- WAV com 16.044 bytes; SHA-256
  `56d4af65701c26df20bd4021eda95b6e830348ce3a746086079fe89285548dc9`.
  Recibo mediu **10,332 s** para a fase de restore/conferência, excluindo
  provisionamento e verificação inicial do pacote. Isso **não define RTO**.
- Nova tentativa de restore recusada pelo destino não vazio, sem apagar
  schema ou áudios. Origem e destino permaneceram com os snapshots esperados.
- Preflight de produção executado **somente até a recusa de manutenção**:
  API/worker seguem ativos. Consulta de metadados confirmou schema real
  `b84e2c7a9d31`; não houve dump, migration ou restore nessa base.
- Ruff, YAML do workflow e `git diff --check` aprovados. Job `recovery` no
  CI reproduz testes e ensaio sintético, sem publicar dumps/áudios como
  artifacts. **CI remoto não executado**; não houve commit ou push.
- As suítes backend, frontend e E2E dos incrementos anteriores não foram
  repetidas: esta etapa não modifica código de produto.
- `make recovery-lab-down` encerrou somente os três containers e a rede do
  laboratório. Os quatro volumes e os pacotes foram preservados, não incluídos
  no Git ou no contexto de build. Não há exclusão automática de backups ou
  dados parciais; containers/rede podem ser recriados sem apagar os volumes.

Os hashes detectam corrupção, não autenticam nem criptografam backups. Só
restaurar pacotes próprios/confiáveis: SQL em dump pode executar código no
servidor; este laboratório não é sandbox para dumps maliciosos.
Permissões 700/600 são proteção local, não cópia externa ou plano de retenção.
O teste sintético não comprova recuperação da conta real nem homologa todas
as funções da aplicação após desastre. Dumps legados sem manifesto/voz não
são convertidos automaticamente em backups completos.

**DB-37 permanece em andamento.** Próximo incremento: separar e ensaiar
papéis runtime/worker/migrador/backup em ambiente sintético, preservando o
acesso administrativo. Ainda dependem de decisão/autorização: política de
retenção/criptografia/cópia externa e seus responsáveis, RPO/RTO, janela de
manutenção para backup real e ensaio correspondente. O rollout da escrita v2
no banco do aluno permanece bloqueado pelo backup real ainda não realizado.

### Oitavo incremento — papéis e rollout preservando estudo, 13/10/2026

Decisões do responsável: manutenção local autorizada após ensaio; **RPO 24h**,
**RTO 60min a validar**, retenção **7 diários + 4 semanais**, Jeferson responsável.
Backup permanece no Mac por escolha explícita para o estágio de desenvolvimento.
Permissões 0700/0600 e FileVault ativo; sem criptografia independente dos pacotes
ou cópia fora do equipamento. Sem agendamento/limpeza automática; não se afirma
RPO continuamente cumprido. Política e comandos em [operação local](operacao_sprint_37.md).

Ensaio de papéis:

- Novo PostgreSQL sintético sem portas, projeto aulas-ingles-roles.
- Owner NOLOGIN; migrador limitado assume owner; runtime faz DML pessoal;
  worker lê tentativas/cues e atualiza jobs; backup só lê tabelas/sequências.
- **24 operações indevidas recusadas por SQLSTATE 42501**: DDL, TRUNCATE,
  criação de banco/role, assumir owner, alterações de catálogo e acessos
  indevidos do worker/backup. DML runtime, HTTP escrita, claim do worker,
  migrations e pg_dump limitado aprovados.
- Guarda do engine valida usuário/papel real e poderes em cada conexão nova.
  Worker roda como UID 10001, voz read-only; credenciais não entram no Git/build.
- Administrador antigo preservado para recuperação. Nenhum teste destrutivo
  de privilégios foi feito sobre dados reais.

Rollout real:

1. Confirmados API/worker antigos usando aulas e revisão b84e2c7a9d31.
   Imagens anteriores preservadas para rollback de aplicação.
2. Manutenção iniciou às **23:25 BRT** (02:25 UTC de 14/10). Paradas somente
   API/worker de 5181; nenhuma interrupção dos containers de desenvolvimento.
3. Backup pré-migration publicado em backups/recovery/, identificado por
   aulas-20261014T022517321471Z-7eca236ddbbe4147b9593b518ec9eb10.
   Restore verificado no segundo destino vazio study-check-db.
4. Recibo mediu **3,939 s** para restore/conferência, sem provisionamento.
   **Zero arquivos de voz pessoais** na origem; não se afirma recuperação de
   gravação real. A recuperação de áudio está comprovada pelo WAV sintético
   de 16.044 bytes do sétimo incremento.
5. Prova SHA-256 das **39 tabelas** de conteúdo/dados pessoais igual no clone
   restaurado e depois da migration/rubricas. Desconsiderados apenas o controle
   Alembic e os campos deliberadamente atualizados; textos, IDs e resultados
   históricos preservados. Nenhum conteúdo privado publicado.
6. Provisionamento/grants reais exigiram pacote, recibo ligado ao hash do
   manifesto e manutenção. Aplicados owner/runtime/worker/migrador/backup;
   migration c95f3d8ba042 e 82 rubricas atualizadas, sem seed completo.
7. Mesma prova de preservação aprovada na origem antes de reabrir tráfego.
8. Segundo pacote pós-migration criado usando **aulas_backup**:
   aulas-20261014T022759607484Z-78514719cc3e48d8a2c4a4a1530ccf71.
   Integridade verificada; este segundo pacote não foi restaurado em novo
   destino. O primeiro foi restaurado e migrado com sucesso.
9. Serviços saudáveis novamente às **23:28 BRT**; health, catálogo e Aula 31
   responderam 200. Conexões reais confirmaram aulas_runtime/aulas_worker,
   sem CREATE no schema nem UPDATE no catálogo; worker read-only para voz,
   sem root e sem reinícios observados.

Evidências finais: **38 testes operacionais puros**, 50 guardas E2E, 765
backend/93,57% cobertura, 263 frontend e 98 E2E integrados aprovados.
YAML, Ruff, mypy, ESLint, TypeScript e diff-check aprovados. Job CI ampliado
para ensaio de papéis; execução remota não realizada.

DB-37 tecnicamente encerrada. Cerca de três minutos de manutenção bem-sucedida
não provam RTO completo de desastre. Backups, recibos, credenciais e volumes
foram preservados; laboratórios foram encerrados sem remover volumes.
Não houve restore destrutivo, downgrade, remoção de usuários ou reavaliação
retroativa da escrita na base real. Pendência pedagógica externa foi aceita
separadamente pelo responsável para fechamento técnico da Sprint 37 conjunta.

## Sprint 38 Integridade transacional e eventos de revisão

Achados B02, B04, B05, D05 e D07.

### Entrega técnica e implantação em 14/10/2026

Migration aditiva d06a4e9cb153, após c95f3d8ba042: revisão zero para rascunhos,
jornadas e itens de revisão existentes; família inicial igual ao jti já conhecido;
sem sucessores ou eventos SM-2 históricos inventados. Constraints conferem etapas,
tempo/contadores, notebook, estado de voz, revisão não negativa e qualidade da nota.
Preflight retorna contagens por constraint e recusa dados incompatíveis sem corrigi-los.
Downgrade destrutivo é bloqueado: recuperação exige backup validado em base separada.

Unicidade de rascunho/versão permanece. Insert-on-conflict e lock de linha protegem
rascunho e alocação de versões. Lock da jornada precede seus StepProgress; conclusões
são monotônicas. Nova navegação incompatível com revisão antiga recebe 409.
Desmarcar aula continua removendo apenas LessonProgress, sem apagar jornada/histórico.
Recibos de revisão usam unicidade conta/chave; lock advisory por conta precede
lock do item. A exclusão do item apenas remove a FK do recibo; a conta possui cascade.
Runtime recebe INSERT/SELECT de recibos, nunca UPDATE/DELETE diretos; worker não
ganha novas permissões. Política SQL e migration foram atualizadas para o papel limitado.

Inventário/reconciliação: app.db.concurrency_audit executa somente SELECT em transação
READ ONLY e emite contagens. Origens editoriais de ReviewItem: vocab_item, exercise,
writing_prompt e transcript_cue; origem pessoal: notebook_entry (confere proprietário).
SkillEvidence admite exercise_attempt, writing_feedback e speaking_attempt; todas
essas origens devem existir e pertencer à mesma conta. Também verifica proprietário
da transcrição versus gravação, tentativa versus sessão de prática/exercício e
consistência da jornada versus etapas/timestamp de conclusão. São 22 regras.
Não há FK genérica possível para source_type/source_id; a API deriva IDs de entidades
autorizadas, e o relatório identifica órfãos para decisão editorial, sem apagá-los.
FKs compostas adicionais de proprietário ficam condicionadas a esse inventário e a
uma migration específica, não são introduzidas por limpeza silenciosa neste ciclo.

PostgreSQL descartável e laboratório de papéis aprovados. A base de estudo em 5181
foi atualizada de c95f3d8ba042 para d06a4e9cb153 após autorização. Alembic check não detectou divergência
entre models e schema d06a4e9cb153 de teste. O ensaio de migration parte de um schema
legado sintético, recusa dado incompatível sem expor o conteúdo, preserva texto/jti,
valida constraints e confirma a recusa de downgrade destrutivo.
O relatório também foi testado com origem inexistente e referência de outra conta,
sem apagar ou reparar os registros. Depois, a auditoria somente leitura foi
executada na base de estudo: as 20 regras de tipos/origens/proprietários passaram;
duas regras de jornada apontaram divergências preexistentes (detalhes abaixo).

O laboratório confirmou 27 recusas de operações não autorizadas, além do fluxo HTTP
de rascunho/revisão com runtime, worker e dump limitado. Corrigida a geração da
configuração de papéis para manter ordem estável mesmo após reler JSON ordenado,
sem regenerar credenciais existentes. A migration do ambiente real exige manutenção
autorizada, backup novo, relatório das 22 regras e ensaio de restauração antes da
aplicação; não executar seed completo nem reutilizar o rollout fixo da Sprint 37.

Regressão final: **789 testes backend (93,54%), 39 testes operacionais e 50 guardas
E2E aprovados**. Três testes de auditoria/migration cobrem inventário vazio, origens
inválidas/proprietário cruzado e expansão compatível. Integração: 106 E2E em bases
isoladas. Nenhum desses números corresponde a testes mutáveis na conta de estudo.

CI preserva o ciclo de downgrade legado somente até c95f3d8ba042, em base vazia,
depois sobe ao head e executa Alembic check. A recusa de downgrade da Sprint 38 é
verificada por teste específico; não foi removida a proteção para fazer o CI passar.
Sintaxe YAML do workflow validada localmente; execução remota ainda não realizada.
Laboratórios E2E/papéis encerrados após os testes, com volumes preservados e sem
reiniciar os serviços de estudo.

Atualização operacional posterior: Jeferson autorizou mexer no ambiente e esclareceu
que os dados são de teste. Backup pré-migration restaurado em concurrency-check-db,
destino novo sem portas; fase de restore/conferência em 4,418 s, não RTO integral.
Hashes das 39 tabelas históricas e inventário de voz conferiram antes/depois, no
clone e na origem. Migração repetida no clone sem efeitos adicionais, aplicada
na origem pelo migrador limitado; recibos/contadores novos vazios antes da reabertura.

Pendência preservada: 20 jornadas com 86 etapas declaradas sem StepProgress
correspondente; 15 jornadas com cinco etapas declaradas e completed_at ausente.
Não foram criadas datas retrospectivas nem apagadas conclusões. A política explícita
--preserve-legacy-journeys permite somente essas duas regras já presentes, exigindo
mesmas contagens e hashes de todas as linhas históricas; qualquer outra regra
ou mudança bloqueia a liberação. Isso é preservação de legado, não aprovação
da integridade dessas jornadas. Reconciliação segue pendente.

47 testes operacionais aprovados. API e worker reabertos com papéis anteriores;
INSERT/SELECT de review_event permitidos ao runtime, UPDATE/DELETE recusados;
worker sem leitura de auth_rate_bucket. Novo backup pós-migration verificado.
Pacotes e procedimento: [registro operacional](operacao_sprint_37.md#sprint-38--implantação-autorizada-em-14102026).

### Entregas

- [x] Modelar revisão/versão de rascunho e operações concorrentes sem remover a unicidade usuário/proposta.
- [x] Garantir alocação atômica da versão de escrita, com ordenação determinística de locks e resposta tratável na API.
- [x] Criar histórico de eventos SM-2 com usuário, item, chave idempotente, qualidade, versão do algoritmo, estado anterior/posterior mínimo e momento do evento.
- [x] Definir unicidade da chave e fingerprint para impedir reutilização com payload diferente. Escolher retenção capaz de cobrir a janela de retry/offline.
- [x] Dar suporte ao consumo atômico de refresh; avaliar família/sucessor e retenção de revogados conforme política BE-38.
- [x] Modelar revisão de jornada e regra de merge das etapas, mantendo consistência entre `completed_steps`, `StepProgress` e `completed_at`.
- [x] Reforçar checks selecionados: etapas válidas, contadores/tempo não negativos, tipos do notebook e invariantes de estado de speaking.
- [x] Inventariar origens polimórficas e associações cruzadas de proprietário; definir validação/reconciliação ou FKs compostas onde tecnicamente apropriado.

### Critérios de aceite

1. Mesma chave de revisão aparece uma única vez e atualiza SM-2 na mesma transação; rollback não deixa evento sem estado correspondente.
2. Duas conexões concorrentes não alocam a mesma versão nem aceitam o mesmo refresh indevidamente.
3. Deadlocks/violação de unicidade esperados têm tratamento na API, não retry ilimitado.
4. Invariantes inválidas são rejeitadas no banco; dados válidos existentes continuam aceitos.
5. Consulta de pré-migration reporta quantidade de violações por regra, sem expor conteúdo pessoal nem corrigi-lo automaticamente.
6. Histórico novo permite explicar mudança de agendamento; não inventa eventos detalhados para revisões anteriores que só possuem estado agregado.

### Estratégia de migration

Expandir com colunas/tabelas novas compatíveis; preencher apenas valores dedutíveis; validar constraints em etapa própria quando aplicável; trocar consumidores; remover compatibilidade antiga somente depois da janela combinada. A API participa da atomicidade: constraint sozinha não implementa fluxo de conflito.

Fora do escopo: trocar SM-2 por outro algoritmo e apagar `review_card` legado neste ciclo.

## Sprint 39 Eventos de estudo cota e mídia

Achados B06, B07, B08, D02 e D07.

### Entregas

- [ ] Criar armazenamento de intervalos/eventos ativos com usuário, aula, sessão/dispositivo lógico, timestamps, duração validada e chave de deduplicação.
- [ ] Definir agregação por dia/semana e fuso; manter totais históricos antigos rotulados como legado sem distribuição temporal fictícia.
- [ ] Modelar reserva/consumo assistido independente de `TranscriptionJob` e feedback apagáveis, com transições e unicidade idempotente.
- [ ] Definir operação atômica para respeitar cota diária e prazo para reservas abandonadas; documentar política de reembolso.
- [ ] Acrescentar índices e estados mínimos para expiração em lotes, evitando transações de limpeza ilimitadas.
- [ ] Inventariar metadados de voz e relacionamento com arquivos; manter checksums quando úteis à restauração/reconciliação.
- [ ] Definir reconciliação entre referências e storage com dry-run, período de segurança e isolamento de arquivos candidatos à remoção.
- [ ] Retenção de refresh expirado, jobs expirados e tentativas pendentes com rotinas separadas e resultado auditável.

### Critérios de aceite

1. Tempo de semanas anteriores não entra na semana corrente só por atualizar uma aula; virada de semana e fuso têm testes.
2. Reenvio offline de evento não soma duas vezes; eventos sobrepostos de duas abas respeitam regra explícita.
3. Excluir transcrição não apaga o consumo mínimo necessário para a cota do dia, respeitando a retenção definida para esse registro.
4. Seis transações concorrentes contra cota cinco não autorizam seis consumos cobrados; exceções/reembolsos são demonstráveis.
5. Expiração funciona com usuário ausente e não reivindica job vencido.
6. Reconciliação identifica arquivos faltantes/órfãos sem apagar arquivo recente, em upload ou referenciado. Produção começa com relatório, não exclusão automática.
7. Limpeza em lotes tem limite, observabilidade, cancelamento e comportamento idempotente.

### Segurança e limites

Não conservar áudio/texto no ledger de consumo. Não escolher retenção jurídica por suposição. Não usar `ON DELETE CASCADE` sobre tabelas de medição sem avaliar se isso reabre cota, destrói explicabilidade ou contraria exclusão solicitada.

Fora do escopo: data warehouse, rastreamento de navegação detalhado e telemetria de conteúdo digitado.

## Sprint 40 Versionamento editorial e portabilidade

Achados D04, B09 e B11.

### Entregas

- [ ] Separar identidade estável de conteúdo e ordenação visual; posição não deve ser a única identidade de exercício/prompt/cue referenciado.
- [ ] Definir versões imutáveis ou snapshots mínimos de enunciado, correção, rubrica e origem suficientes para interpretar tentativa histórica.
- [ ] Adotar arquivamento para conteúdo usado por alunos em vez de cascade destrutivo por desaparecimento do seed.
- [ ] Acrescentar diff/dry-run de seed com itens criados, alterados, arquivados e impacto em dados pessoais.
- [ ] Corrigir datas de revisão/publicação por versão editorial e preservar origem/licença auditadas.
- [ ] Implementar inventário de exportação cobrindo toda entidade pessoal atual, inclusive prática/checkpoint e feedback sem draft.
- [ ] Garantir snapshot consistente da exportação ou mecanismo de corte/versionamento equivalente para grandes volumes.
- [ ] Planejar exclusão de conta/recursos com tarefa de remoção de binários rastreável e retries seguros, sem transação distribuída implícita.
- [ ] Definir preservação e expiração de backups após pedidos de exclusão segundo política aprovada.

### Critérios de aceite

1. Atualizar gabarito não muda o significado do registro histórico; versão referenciada continua consultável.
2. Seed que retire prompt com escrita, cue com voz e vocábulo com revisão conserva os dados segundo política de arquivamento.
3. Exercício referenciado por prática não gera falha surpresa de RESTRICT no meio de deploy; o diff já identifica o caso.
4. Rodar seed idêntico duas vezes não altera IDs históricos, datas de revisão sem motivo ou contagens de dados pessoais.
5. Exportação sintética contém todas as entidades do inventário e não omite feedback sem draft.
6. Exclusão parcial de arquivo pode ser retomada e auditada sem reexpor referência privada nem deixar pendência invisível.

### Migração dos dados antigos

Snapshots antigos só podem usar informação efetivamente disponível. Quando a versão histórica exata não for reconstruível, marcar essa limitação em vez de atribuir o gabarito atual como se fosse original. Não reescrever `correct` nem recalcular competências silenciosamente.

Fora do escopo: CMS completo de autoria, copiar materiais externos sem licença e renumerar a cobertura deliberada da unidade 40–44.

## Sprint 41 Desempenho de consultas e validação de invariantes

Achados D05, D06 e B10.

### Entregas

- [ ] Gerar massa sintética isolada para usuários, eventos, escrita, revisão e jobs, em pelo menos dois volumes documentados.
- [ ] Capturar planos de consultas reais de fila, histórico, painel, currículo e expiração; registrar cardinalidade, buffers e tempo.
- [ ] Ensaiar índices compostos/parciais candidatos e manter somente os que tragam benefício mensurável na carga definida.
- [ ] Revisar índices redundantes, custo de escrita, espaço e manutenção; não remover índice de unicidade por parecer sobreposto.
- [ ] Alinhar índices aos cursores e filtros de BE-41, incluindo desempate por ID.
- [ ] Validar as constraints adicionadas com verificação de dados e testes de SQL direto em base descartável.
- [ ] Criar relatório agregado de referências polimórficas órfãs e incoerências de estado, com prazo e ação para cada caso.
- [ ] Avaliar pool total de API/workers, timeout de statement/lock e orçamento de conexões; não apenas aumentar `max_connections`.

### Candidatos sujeitos a medição

| Carga | Índice a ensaiar | Condição |
|---|---|---|
| Revisões vencidas de uma conta | `(user_id, due_at, id)` parcial ativo | Comparar filtros adicionais e distribuição real |
| Histórico de escrita/voz | `(user_id, created_at DESC, id DESC)` | Ajustar para prompt/aula se predominante |
| Job pronto para execução | `(next_attempt_at, id)` parcial queued | Testar disputa de vários workers |
| Retenção de refresh | `expires_at` | Só se volume/rotina justificarem |
| Eventos de estudo | `(user_id, occurred_at)` ou equivalente | Depende do modelo de evento aprovado |

### Critérios de aceite

1. Cada índice novo possui plano antes/depois, volume, melhoria e custo de escrita documentados.
2. Nenhum pressuposto de “index scan sempre melhor”: scan sequencial pequeno pode permanecer.
3. Paginação estável não degrada progressivamente como OFFSET profundo nos cenários alvo.
4. Migrações de índice indicam estratégia de concorrência/locks e falha parcial; `CREATE INDEX CONCURRENTLY` não é colocado cegamente em transação Alembic.
5. Invariantes verificadas não apresentam regressão; dados incorretos encontrados têm decisão antes de ajuste.
6. Não se utiliza dado pessoal real para gerar relatório ou benchmark.

Fora do escopo: particionamento/replicação/cache externo sem evidência de necessidade.

## Sprint 42 Recuperação e evolução segura do banco

Achados D02, D08 e B12; fechamento de D03/D07.

### Entregas

- [ ] Criar cenário de upgrade a partir de versão anterior com massa sintética contendo todas as modalidades, inclusive sessões em curso e arquivos de voz.
- [ ] Verificar divergência entre modelo SQLAlchemy, Alembic e schema aplicado; falhar gate em divergência não aprovada.
- [ ] Ensaiar upgrade com duração/locks medidos e rollback de aplicação sem assumir downgrade destrutivo como solução padrão.
- [ ] Restaurar backup completo de banco e voz em ambiente separado, medindo RTO e perda potencial segundo RPO acordado.
- [ ] Validar permissões pós-restore, checksums de áudio, integridade referencial e leitura pela aplicação.
- [ ] Integrar revisão compatível de schema ao readiness do backend e à sequência de implantação.
- [ ] Monitorar capacidade do banco/arquivos, crescimento de tabelas, conexões, locks, idade de jobs e execução das rotinas de retenção.
- [ ] Decidir permanência/retirada de `review_card` legado com reconciliação, janela de compatibilidade e recuperação aprovadas.
- [ ] Consolidar runbook com nomes de ambientes, papéis, backups, processo de incidente e comandos que exigem confirmação.

### Critérios de aceite

1. Upgrade preserva usuários, tentativas, revisão, voz, rascunhos, versões, eventos e checkpoints da massa de ensaio.
2. Schema incompatível impede liberação de tráfego; banco acessível não basta para estar pronto.
3. Restore valida banco e arquivos, não apenas saída zero do `pg_restore`.
4. Restore ensaiado não se conecta ao banco real por fallback e não inicia worker que envie áudio a um provedor externo.
5. RPO/RTO medidos atendem à meta combinada, ou impedem o aceite operacional até ajuste.
6. Remoção de legado só ocorre após comprovar ausência de consumidores e preservar o histórico necessário; a escolha de mantê-lo é documentada se ainda houver dependência.

## Regras para toda mudança de banco

1. Identificar alvo com consulta read-only antes de qualquer operação destrutiva.
2. Nunca usar a base de estudo do usuário como fixture de teste ou massa de benchmark.
3. Planejar evolução compatível, pré-verificação, índices, locks, rollback e backup antes de aplicar migration.
4. Não corrigir automaticamente dados fora da regra sem conhecer origem e decisão do responsável.
5. Nenhum dump, áudio, token, senha ou conteúdo pessoal deve entrar no Git, log de CI ou relatório técnico.
6. Toda tabela nova define chave, propriedade, integridade, índice de acesso e retenção; JSONB não elimina contrato.
7. Índices e checks não substituem transações, idempotência ou autorização da API.
8. A auditoria documental não conclui caixas; cada atualização de status depende de implementação e evidências registradas na sprint correspondente.
