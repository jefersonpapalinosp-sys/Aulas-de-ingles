# Sprints de banco de dados para integridade e recuperação

Atualização: 16 de outubro de 2026. **DB-39G/H, DB-40, DB-41 e o escopo técnico de DB-42 estão concluídos e o estudo foi migrado para `a42c7d1e9f20`.** A promoção preservou contagens, referências e volume de voz, com backup real anterior, restore isolado, ensaio da mesma cadeia, zero locks aguardando e backup posterior. A janela planejada ficou abaixo de sete minutos, mas o RTO de desastre e a cadência RPO de 24 h continuam metas a validar, não SLA. Consulte a [Sprint 43](sprint_43_implantacao_estudo_2026-10-16.md) e a [matriz da Sprint 42](matriz_aceite_sprint_42_2026-10-16.md).

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
RPO continuamente cumprido. Política e comandos em [operação local](historico_operacao_sprints_37_44.md).

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
Pacotes e procedimento: [registro operacional](historico_operacao_sprints_37_44.md#sprint-38--implantação-autorizada-em-14102026).

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

### Incremento 39A — migration `e17b5fad0264` (14/10/2026)

Expand sobre `d06a4e9cb153`, sem reescrever nem redistribuir histórico:

- `media_progress`: revisão não negativa, conclusão com posição zero, UUID/fingerprint
  da última operação e data declarada de alteração. Linha preservada após conclusão.
- `study_plan.timezone`: IANA, UTC por padrão, validado pela API.
- `study_activity_session`: âncora por usuário/aula e UUID transitório de sessão.
- `study_activity_event`: recibo com chave única `(user_id, operation_key)`, fingerprint,
  duração 1–30.000 ms, crédito entre zero e duração e recebimento no servidor.
- `study_active_interval`: trechos creditados de até 30 s; índice `(user_id, ends_at)`
  para sobreposição/janela semanal. Não sobreposição é garantida na transação API sob
  lock do usuário, não por uma exclusion constraint do PostgreSQL.
- Runtime recebe somente SELECT/INSERT nas três tabelas; worker não as acessa.
  Exclusão de conta por procedimento futuro poderá usar cascades; esses eventos não
  são ledger de cota e não devem ser reutilizados como tal.

Ensaio transacional em schema sintético preservou posição/plano antigos, comprovou
defaults e recusas de constraints. Alembic check não detectou drift. PostgreSQL de testes
55435, E2E 5198 e laboratório de papéis receberam o head; base de estudo não recebeu.
Laboratório aprovou 36 recusas de privilégios, escrita/leitura HTTP runtime e dump
read-only incluindo as novas tabelas. 63 testes operacionais puros aprovados.

Alinhamento posterior autorizado do dev 5433: sequência `b84e2c7a9d31` → `c95f3d8ba042`
→ `d06a4e9cb153` → `e17b5fad0264`, primeiro em clone do backup real e depois na origem.
39 tabelas/6.766 registros históricos preservados por hashes, 82 aulas, zero usuários
originais e zero áudios; sem seed, reparos ou alterações de papéis. Auditadas 22 regras,
sem violações no dev; não confundir com divergências legadas do estudo. Segunda execução
das migrations sem alterações e Alembic check aprovado nos dois bancos. Após smoke
HTTP e remoção da conta temporária, hashes históricos novamente idênticos. Banco de
estudo 5434 continua em `d06a4e9cb153`. [Evidências e limites](historico_operacao_sprints_37_44.md#sprint-39a--alinhamento-autorizado-do-desenvolvimento-em-14102026).

Não há purge automático novo: 7 dias é janela de aceitação de replay, **não retenção
do banco**. Retenção/compactação e exclusão auditável seguem pendentes; não apagar
recibos enquanto puderem autorizar replay duplicado. Downgrade destrutivo bloqueado.
Rollout futuro em 5181 exige backup/restore ensaiado e atualização coordenada API/frontend;
os scripts de rollout 37/38 não foram ampliados para 39A e não devem ser usados como
atalho. `ops/dev_alignment.py` é exclusivo da origem dev em `b84e2c7a9d31`, não aceita
estudo nem uma base já migrada. Orçamento frontend e 112 cenários Playwright do build
otimizado aprovados.

### Incremento 39B — concorrência de voz, sem migration (14/10/2026)

O head continua em `e17b5fad0264` no desenvolvimento e nos testes; estudo 5434/5181
permanece em `d06a4e9cb153`. Não houve alteração de papéis, seed ou SQL operacional.
O upload libera a transação de leitura antes de receber o corpo e só depois bloqueia
a linha de `speaking_attempt` para serializar PUT/DELETE. Recarrega o estado após o lock:
retry idêntico não duplica `skill_evidence` nem revisão; outro conteúdo recebe conflito.

A criação do arquivo e o commit SQL continuam em sistemas separados. Em falha ambígua
de commit, a API consulta a referência antes de excluir seu arquivo novo; se a consulta
falhar, preserva o candidato. Os testes cobrem commit efetivado/não efetivado com resposta
perdida, além de upload/exclusão concorrentes em PostgreSQL. **820 testes backend**
passaram na base isolada 55435 e **63 operacionais puros** passaram, sem usar dados do aluno.

Não existe coluna de checksum nova: comparação SHA-256 com leitura limitada serve
somente ao retry de PUT. Não substitui inventário/checksum durável, reconciliação
dry-run nem retenção de `pending`. Crash/cancelamento podem deixar órfãos; os itens
de reconciliação abaixo permanecem abertos. Não executar limpeza automática por
idade do arquivo nem apagar candidatos sem conferir referências e uploads ativos.

### Incremento 39C — inventário read-only e duração medida (14/10/2026)

Nenhuma migration, seed, papel ou limpeza automática foi acrescentado. Head de dev
continua `e17b5fad0264`, estudo permanece `d06a4e9cb153`. Somente uploads novos,
na primeira publicação, recebem duração medida pelo decoder na coluna existente
`duration_ms`; registros prontos antigos conservam o valor histórico. Não existe
baseline persistente de checksum ou marcador de validação retroativo por tentativa.

`app.audio_audit` usa `REPEATABLE READ, READ ONLY`, `statement_timeout=5s` e projeção
de ID/status/chave/tamanho/criação, limitada a 10.001 linhas para detectar truncamento.
Processa no máximo 10 mil referências; libera a transação antes de ler arquivos.
Não consulta textos de fala, email ou conteúdo pessoal para o relatório.

Inventário: máximo de 10 mil entradas, 100 MiB de hashing e orçamento **cooperativo**
de 30 s entre leituras; não é timeout rígido de filesystem/disco travado. Hash SHA-256
em blocos de 64 KiB, comparação de inode/tamanho/mtime/ctime antes/depois e recusa
de links/hardlinks. Referências de qualquer status protegem arquivos. Temporários,
desconhecidos, recentes (mtime **ou** ctime < 24 h) e mutáveis não viram candidatos.
Metadado inválido, referência faltante, tamanho divergente e `pending` antigo são
achados, não ordens de exclusão. Snapshot incompleto não classifica órfãos;
orçamento esgotado/erro de leitura marca `complete=false` e saída 2.

Hashes são observações por execução, não prova de integridade histórica. Relatório
não move/exclui/repara nada e não possui opção apply. O prazo de segurança não define
retenção. Futuro fluxo de quarentena precisa revalidar referências e uploads ativos
no momento da ação; reaproveitar um relatório antigo é inseguro.

Teste com PostgreSQL real confirma SQL somente leitura e conexão devolvida antes
do hashing. Ensaio no laboratório Linux leu 42 referências/26 arquivos recentes,
todos preservados; não confundir com certificação da base de estudo. Checklists
de retenção, consumo assistido e reconciliação mutante continuam abertos.

Regressão final backend: **850 testes / 93,62% de cobertura**. Inventário de dev
executado apenas para leitura: zero referências/arquivos, sem alterações. Nenhuma
base de estudo foi usada pelos testes. [Registro operacional](historico_operacao_sprints_37_44.md#sprint-39c--atualização-da-api-dev-sem-alteração-de-dados-em-14102026).

### Incremento 39D — exclusão mútua e journal privado (14/10/2026)

Nenhuma tabela/coluna/papel/migration foi acrescentado. O operador abre transação
READ COMMITTED, confere `current_database()`, toma `LOCK TABLE speaking_attempt IN
EXCLUSIVE MODE NOWAIT` e consulta referências atuais. Isso recusa intervenção durante
`FOR UPDATE`/DML concorrente; SELECT comum continua possível. Statement timeout 5 s.
Após a ação de filesystem, rollback apenas libera o lock: **não desfaz arquivo**.

Journal no volume, não no PostgreSQL: chave opaca, operação, checksum, tamanho,
inodes/device, timestamps e nome do banco; sem texto de fala/email/token. É recibo
de seleção/movimentação, não baseline retroativo de todas as gravações. Fica privado
e participa do backup v2, separado da contagem de áudios sem referência. Inventário
39C identifica a pasta protegida sem recursar ou afirmar que a reconciliou.

Quarentena/restore não mudam tentativas, evidências ou progresso. Referência nova
protege contra movimentação; arquivo recente, modificado, linkado externamente ou
fora dos limites não é recolhido. Um processo interrompido pode deixar dois nomes
do mesmo inode: a retomada reconhece apenas esse par, não qualquer hardlink externo.

Backup v2 aceita exclusivamente caminhos reservados de journal/áudio, sem traversal,
links de tar, arquivos especiais ou extração genérica. Backups v1 seguem suportados.
Exportação de dois nomes após interrupção conserva ambos como arquivos regulares.
Restore em volume novo conserva bytes, mas invalida identidade de inode do journal:
requer revisão, não retoma mutação automaticamente. Sem nova medição de RPO/RTO.

Ensaio limitado à base descartável e arquivos sintéticos; não foi aplicada quarentena
em dev 5433 nem estudo 5434. Retenção de `pending`, checksum durável de todo áudio
publicado e expurgo aprovado seguem abertos; estes comandos não substituem esse trabalho.

Evidência: **893 testes backend / 93,69% de cobertura**, incluindo lock concorrente,
referência nova após seleção e ausência de DML no operador. **72 testes operacionais**
cobrem v1/v2, checksum, transporte real em diretórios temporários e destinos inseguros.

### Integração 39E — limites do cache no navegador (14/10/2026)

Nenhuma migration, índice, papel, exclusão ou mudança de seed no desenvolvimento/estudo.
CacheStorage guarda apenas respostas editoriais públicas, com limite e expiração por
release. Não é substituto de backup, tabela de tentativas ou arquivo privado de voz.

Atualizar o PWA/limpar seus textos não executa DML nem apaga localStorage/IndexedDB.
Fila e rascunhos conservam os contratos anteriores; a ativação aguarda fechamento
das abas para não descartar dados ainda em memória por reload automático. Testes
de duas abas preservam rascunho/fila sintéticos entre versões. Retenção de dados
pessoais não é confundida com TTL do conteúdo público.

Regressão backend: **912 testes**, cobertura **93,70%**, em PostgreSQL descartável
55435. Somente essa base foi preparada/migrada/semeada nesta entrega. Sem nova
medição de RPO/RTO, dump/restore ou alteração da base de estudo em 5434.
[Registro operacional 39E](historico_operacao_sprints_37_44.md#sprint-39e--pwa-e-cache-público-em-14102026).

### Entregas

- [x] Criar armazenamento de intervalos/eventos ativos com usuário, aula, sessão/dispositivo lógico, timestamps, duração validada e chave de deduplicação (39A isolada e dev).
- [x] Definir agregação semanal e fuso; manter totais históricos antigos rotulados como legado sem distribuição temporal fictícia (39A isolada e dev; sem painel diário novo).
- [x] Modelar reserva/consumo assistido independente de `TranscriptionJob` e feedback apagáveis, com transições e unicidade idempotente (39F, incluída no rollout 39G/H).
- [x] Definir operação atômica para respeitar cota diária e prazo para reservas abandonadas; documentar política de reembolso (39F, expiração lógica de reserva; purge em lotes separado).
- [x] Índices de expiração de refresh e estado/data de pending; lotes de até 500 com `SKIP LOCKED`, timeouts e cancelamento entre transações.
- [x] SHA-256 durável, estado/instante de integridade de voz, inventário e reparação explícita por cópia conferida. Legado `unknown`, sem baseline retroativo fictício.
- [x] Reconciliação com dry-run e quarentena reversível; estudo exige migrador e alvo confirmado, sem expurgo automático.
- [x] Rotinas separadas e auditáveis de jobs, reservas, refresh e pending; as duas últimas ficam opt-in desligadas até aprovação da política de 7 dias. Ledger não é expurgado.

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

### Incremento 39F — ledger de assistência (14/10/2026)

`assist_reservation` armazena conta, chave da operação, fingerprint, modalidade,
chave estável do provedor, estado, motivo, datas e custo reportado. Não conserva
texto, áudio ou token. Unicidade `(user_id, request_key)` e `provider_key`; checks
de modalidade, estado, custo não negativo e vencimento posterior à criação.
Índices `(user_id, created_at)` para o saldo e `(state, expires_at)` para a futura
rotina limitada; não representam benchmark de volume ou aceite de DB-41.

Feedback/job têm FK nullable e única para a reserva. Apagar resultado não apaga
ledger. A cascata da conta foi mantida explicitamente: encerrar a identidade apaga
seu consumo; não é uma operação de reembolso nem proteção contra criar outra conta.
Runtime recebe SELECT/INSERT/UPDATE e uso da sequence, worker SELECT/UPDATE; ambos
sem DELETE direto. Somente operador owner pode executar futura retenção controlada.

`f28c6abe1375` expande `e17b5fad0264` sem remover registros históricos. Backfill de
feedback com provedor e jobs existentes marca `consumed/legacy_observed`, sem
inventar instante de despacho. Zero legado fica com custo desconhecido, pois o
contrato antigo confundia zero e ausência. Jobs legados pendentes também são
conservadoramente consumidos; sua exclusão não devolve unidade. Consumo apagado
antes da migration não pode ser reconstruído. Downgrade destrutivo é recusado.

Reserva nova vence logicamente após `ASSIST_RESERVATION_SECONDS` (900 por padrão;
60–3600): deixa de ocupar o saldo sem depender de leitura da listagem. Antes de
despachar o worker confere e libera a vencida. Consumo confirmado não expira por
esse TTL. Na entrega 39F, retenção histórica do ledger e limpeza em lotes ficaram para 39G;
neste incremento ele permanece até exclusão da conta/decisão operacional explícita.
Não há prazo jurídico presumido, nem uso de `ASSIST_RETENTION_DAYS` como purge
do ledger. Chaves não devem ser removidas enquanto sustentam deduplicação.

Upgrade/backfill/constraints/exclusão e concorrência foram ensaiados no PostgreSQL
descartável. A corrida expiração × commit de despacho possui regressão própria.
Em 15/10, somente DEV 5433 foi migrado: `e17b5fad0264` → `f28c6abe1375`, após
manutenção, backup/restore e ensaio com imagem imutável. As 44 tabelas históricas e
6.768 linhas conservaram seus fingerprints; nenhum seed, reconciliação ou mudança
de papéis foi feito. O backfill real tinha zero resultados assistidos; os casos
não vazios permanecem cobertos na base sintética 55435. Estudo 5434 não migrado.
[Alinhamento e recibos](historico_operacao_sprints_37_44.md#sprint-39f--alinhamento-do-desenvolvimento-em-15102026).
[Registro 39F](historico_operacao_sprints_37_44.md#sprint-39f--reservas-e-cotas-assistidas-em-14102026).

### Incremento 39G/H — aplicado em 15/10/2026

`a39d7bc02486` acrescenta três colunas de integridade em `speaking_attempt`, índices,
`worker_heartbeat` e função de limpeza `SECURITY DEFINER` com escopos estáticos,
search_path fixo e execução restrita. Runtime/backup não recebem execução da função;
worker não recebe DELETE amplo. Upgrade repetido e `alembic check` aprovados.

Clones exclusivos `dev39-check-db` e `study39-check-db`: backup/restore com hash,
fingerprints por tabela e smoke autenticado antes da origem. DEV preservou 45
tabelas históricas e estudo 41; exclusões da comparação limitadas às estruturas
novas de cada base. Backfill de ledger conferido; 15/20 divergências históricas de
jornada preservadas. Zero arquivos reais nas origens; casos não vazios de áudio e
restauração cobertos por fixtures sintéticas, sem declarar evidência física.

Detalhes, recibos, retenção ainda opt-in e limites de recuperação no [runbook](historico_operacao_sprints_37_44.md#sprint-39gh--retenção-integridade-e-implantação-em-15102026).

## Sprint 40 Versionamento editorial e portabilidade

Achados D04, B09 e B11.

### Entregas

- [x] Separar identidade estável de conteúdo e ordenação visual para exercício/prompt/cue, mídia, vocabulário e questão de checkpoint (40B.2b.2; migration ensaiada em bases isoladas, rollout DEV/estudo pendente).
- [x] Substituir os vínculos posicionais mídia→exercício e checkpoint→mídia por FKs compostas estáveis, com backfill estrito e downgrade protegido (40B.2e; somente banco descartável).
- [x] Definir snapshots mínimos imutáveis de enunciado, correção, rubrica e origem para novas evidências, com ausência legada explícita e consumo posterior seguro pelo STT (40B.2a/40B.2d; sem backfill).
- [x] Criar e ensaiar tabela de snapshots das novas evidências, com FKs, unicidade, dono e proteção contra UPDATE (40B.2a; sem backfill ou rollout).
- [x] Adotar arquivamento para conteúdo usado por alunos em vez de cascade destrutivo por desaparecimento do seed (40B.2b.3).
- [x] Acrescentar diff/dry-run de seed com itens novos, diferentes, omitidos e bloqueios, sem DML nem avanço de sequência (40B.1).
- [x] Completar o diff com arquivamento e contagens de impacto em dados pessoais após definir identidade/snapshots (40B.2b.1/40B.2b.3).
- [x] Implementar prévia independente por unidade com contagens agregadas de referências e dependências entre checkpoints (40B.2b.1; não é aplicação nem diff semântico do seed).
- [x] Criar recibo append-only e ensaiar arquivamento transacional por unidade, com digest, exclusão mútua e integração de impacto para pedidos explícitos no dry-run do seed (40B.2b.3; sem rollout ou remoção de conteúdo).
- [x] Corrigir datas de revisão/publicação por versão editorial e preservar origem/licença auditadas (40B.2c; revisão humana permanece pendente).
- [x] Implementar inventário de exportação cobrindo toda entidade pessoal atual, inclusive prática/checkpoint e feedback sem draft (40A; exclusões operacionais explícitas).
- [x] Garantir snapshot consistente da exportação (40A); grandes volumes recusados integralmente acima dos limites documentados.
- [x] Implementar exclusão de conta/recursos com tarefa de remoção de binários rastreável e retries seguros, sem transação distribuída implícita (40C).
- [x] Definir preservação e expiração de backups após pedidos de exclusão segundo política aprovada para o ambiente DEV (40C).

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

### Incremento 40A — snapshot pessoal consistente, 15/10/2026

Sem migration ou mudança de permissão: mantém `a39d7bc02486`. Exportação usa uma
transação somente leitura `REPEATABLE READ`, depois da autenticação, com releitura
do perfil. As três entidades filhas sem `user_id` — `writing_revision`,
`step_progress`, `practice_session_item` — são delimitadas pelo proprietário do pai.
Transcrições são incluídas apenas quando válidas no timestamp do snapshot.
Teste com escrita concorrente confirmada em outra conexão comprovou a preservação
do estado anterior no arquivo; escrita posterior ao export também funciona,
verificando que a opção read-only não permaneceu no checkout seguinte.

Inventário cobre 21 tabelas com `user_id`, as três filhas e `app_user`; dados de
segurança não pessoais/agregados e backups operacionais são exclusões declaradas.
Cada tabela tem contagem no arquivo; a mesma entidade pode aparecer também numa
projeção compatível antiga, por isso não somar seções JSON para contar registros.
Campos secretos/operacionais não fazem parte da portabilidade.

**Sprint em andamento:** 40B preservação editorial/seed, 40C exclusão com retry e
política de backups, 40D histórico/aceite integrado. Nenhum expurgo ou alteração
de seed foi executado. [Contrato e verificação](historico_operacao_sprints_37_44.md#sprint-40a--exportação-e-meus-dados-em-15102026).

### Incremento 40B.1 — proteção antes de migrations editoriais, 15/10/2026

Mantida migration `a39d7bc02486`; nenhum schema/usuário/permissão alterado.
Prévia lê somente as 19 tabelas editoriais em snapshot consistente. Aplicação
recusa qualquer alteração ou omissão de conteúdo existente, mesmo não referenciado,
e extensão de aula/checkpoint existente. Omissão **não é exclusão nem arquivamento**.
Metadados de versões inferiores à versão solicitada ficam preservados literalmente
e aparecem como `retained`, sem bloquear reaplicação idêntica. Uma versão superior
omitida caracteriza tentativa de downgrade e continua bloqueada. Não apagar versões
para liberar o seed nem interpretar esses metadados como snapshots completos.

Foram eliminados os deletes/reinserts de objetivos, gramática, frases, respostas,
dicas, vocabulário, prompts, mídia/cues e questões. Reaplicação idêntica preserva
IDs, timestamps e sequências de todas as tabelas editoriais. Conteúdo genuinamente
novo é inserido em ordem de dependências, com rollback da transação inteira em
falha. Sequências podem avançar em uma aplicação que falhe, como no PostgreSQL
normal; a garantia de não avançar é da prévia e da reaplicação idêntica.

Locks `NOWAIT` serializam a carga frente a outros escritores editoriais sem
espera indefinida. Dados pessoais não precisam ser bloqueados: nenhum registro
editorial existente pode ser modificado por esse caminho. Ainda **não** há
snapshot imutável novo, identidade estável independente de posição, política
central de arquivamento ou correção das datas legadas de 07/10. 40B.2 permanece
necessário antes de editar/publicar novas versões em conteúdo existente.

Prévia DEV: 82 diferenças de `writing_prompt.requirements` e 3 registros
`lesson_version` antigos mantidos. Somente leitura; preservação integral.
Diferença de representação de rubrica ainda precisa ser distinguida de mudança
semântica antes de propor migração, sem sobrescrever o estado local automaticamente.
[Contrato e testes](historico_operacao_sprints_37_44.md#sprint-40b1--prévia-e-barreira-editorial-do-seed-em-15102026).

### Incremento 40B.2a — tabela de evidências imutáveis, 15/10/2026

Migration aditiva `b40e8cd13597`, depois de `a39d7bc02486`, cria
`evidence_content_snapshot`: proprietário, exatamente uma FK real para tentativa
de exercício/item de prática/feedback de escrita/fala/checkpoint, conteúdo JSONB,
schema 1.0, fingerprint SHA-256 e timestamp. Unicidade por evento e trigger de
validação da conta, incluindo proprietário da sessão pai dos itens de prática.
Trigger rejeita UPDATE; runtime tem SELECT/INSERT, sem UPDATE/DELETE; worker não
recebe acesso. Exclusão do evento/conta remove seu snapshot por cascade, mantendo
o contrato futuro de exclusão pessoal. Não equivale a habilitar cascade editorial.

Nenhum backfill: tabela nasce vazia. Ausência de snapshot antigo é declarada, não
substituída por conteúdo atual. Limites: 200 mil bytes na serialização canônica do
serviço e 256 KiB na representação textual JSONB. Fingerprint não é assinatura
digital nem defesa contra administrador que altere o schema.

Upgrade/downgrade/upgrade ensaiados em schema isolado: downgrade só permite tabela
vazia e recusa apagar snapshots já gravados. Alembic check sem divergência entre
modelo e migration. Migration aplicada somente nos laboratórios de teste/papéis;
DEV e estudo permanecem em `a39d7bc02486`. Permissões reais ensaiadas no laboratório,
não alteradas nos ambientes de uso.

**Pendentes de 40B.2:** UUID/chave editorial estável, arquivamento, proveniência real,
impacto no diff e rollout após backup/restore. As 82 rubricas divergentes do DEV
não foram normalizadas/sobrescritas. [Contrato e verificação](historico_operacao_sprints_37_44.md#sprint-40b2a--snapshots-privados-de-evidências-em-15102026).

### Incremento 40B.2b.1 — diagnóstico de impacto, 15/10/2026

Prévia `editorial-plan` usa uma transação `REPEATABLE READ, READ ONLY`, teto total
de 30 s e 20 s por statement. Conta linhas das 19 tabelas editoriais e referências
pessoais diretas/indiretas, incluindo versões de rascunho, itens de prática,
checkpoint, eventos de tempo, competências resolvíveis e snapshots quando a tabela
existe. Detecta referências de checkpoints de outras unidades por números de aula
e questões JSONB, restringindo sempre ao mesmo curso. Não conta usuários únicos.

Não expõe IDs de alunos, textos, e-mails ou caminhos de áudio. Ausência da tabela
de snapshots é explícita, não convertida em zero; recibos órfãos, origens não
resolvíveis, backups e dados somente locais são limites declarados. Nada é escrito,
arquivado ou apagado; sequências e timestamps editoriais permanecem inalterados.
Teste concorrente comprova o mesmo instante de leitura em todas as contagens.

No DEV, prévia do bloco 31–40 encontrou 10 aulas, 111 exercícios, 10 prompts,
48 cues e 1 checkpoint externo dependente; sem dados pessoais atribuíveis ao bloco
naquele corte. Isso não é inventário de todas as contas/ambientes. Não houve
migration nem concessão de privilégios. Identidade estável, aplicação auditada e
integração desse plano ao seed ainda pendentes.
[Contrato e evidências](historico_operacao_sprints_37_44.md#sprint-40b2b1--disponibilidade-e-prévia-de-arquivamento-em-15102026).

### Incremento 40B.2b.2 — chaves imutáveis e compatibilidade, 15/10/2026

Migration `c51f9de246a8`, após `b40e8cd13597`, acrescenta UUID `NOT NULL` com unicidade
por tabela em `exercise`, `writing_prompt`, `transcript_cue`, `lesson_media`,
`vocab_item` e `course_review_question`. Trigger recusa mudança de chave mesmo pelo
owner. IDs numéricos, FKs, posições, textos, datas e resultados não são reescritos.

O mapeamento inicial UUIDv5 usa namespace/receita congelados com coordenadas da
baseline legada; fica persistido no banco e nos dois JSONs do seed. Essa receita
**não é executada novamente para identificar entidades já migradas**. Editar ou
reordenar deve carregar a chave original; entidade nova/clonada usa nova chave
explícita. Inserções SQL sem chave têm default UUIDv4, mas o importador exige chave
no pacote. Não há backfill de snapshots nem alegação de identidade histórica anterior.

Downgrade recusa tabelas com entidades: remover chaves após reordenação permitiria
reidentificação incorreta. Reversão vazia/re-upgrade ensaiados em schema temporário.
Para rollback operacional, preferir código anterior mantendo colunas; eventual
restore exige plano/backup compatível, não apagar conteúdo para habilitar downgrade.

Ensaio: constraints, imutabilidade, relações e resultados preservados, chave mantida
após mudança de posição, seed idempotente e `alembic check` sem drift. Papéis runtime,
worker e backup não podem alterar chaves; runtime lê/captura via HTTP no laboratório.
Laboratório encerrado com volume preservado. DEV/estudo não receberam migration;
somente teste descartável e laboratório de papéis estão em c51.

Reordenação continua bloqueada: referências posicionais de listening/checkpoints
e fingerprints da prática ainda precisam de tratamento no plano editorial futuro.
Proveniência, 82 rubricas DEV, integração de impacto/arquivamento e rollout pendentes.
[Contrato e evidências](historico_operacao_sprints_37_44.md#sprint-40b2b2--identidade-editorial-estável-em-15102026).

### Incremento 40B.2b.3 — recibo e transação de arquivamento, 15/10/2026

Migration `d62a0ef357b9` após c51 cria `editorial_archive_event`, sem arquivar dados
ou preencher auditoria legada. PK UUID da operação, FK RESTRICT para unidade,
constraints de transição/motivo/hash, operador declarado e identidades SQL reais,
timestamp do banco e impacto agregado. Trigger recusa UPDATE/DELETE; downgrade
recusa recibos existentes. Não é proteção contra DDL privilegiado do owner.

Runtime/worker não leem nem escrevem a auditoria; backup tem somente leitura.
O proprietário/migrador aplica por serviço/CLI auditado, sem conceder UPDATE de
catálogo ao runtime. Status e recibo são atômicos. Retry verifica todos os campos
do pedido antes de devolver o recibo, sem nova mutação.

Advisory lock global transacional compartilhado nas admissões/exclusivo no seed
e apply; aquisição não bloqueante evita ciclos com locks pessoais. As 19 tabelas
editoriais recebem SHARE ROW EXCLUSIVE NOWAIT durante aplicação, congelando
conteúdo e referências entre unidades. Nenhuma tabela pessoal é bloqueada para
arquivar. Digest inclui catálogo normalizado completo, IDs, alvo e nome do banco;
alteração editorial em outra unidade também exige nova prévia, por prudência.

Prévia usa REPEATABLE READ READ ONLY; apply exige READ COMMITTED e tem teto de
30 s/20 s por statement. Contagens pessoais durante apply são observações, não um
snapshot global imóvel: jobs admitidos e gestão privada podem continuar. Essas
contagens não autorizam remoção ou reprocessamento; dependências editoriais estão
congeladas e checkpoints externos bloqueiam a aplicação.

Migration/constraints/rollback ensaiados no banco descartável e em laboratório de
papéis. Ensaios de arquivamento foram revertidos integralmente por rollback, sem
desabilitar triggers para apagar recibos. DEV/estudo não migrados nem arquivados;
prod/public bloqueados. [Contrato e evidências](historico_operacao_sprints_37_44.md#sprint-40b2b3--arquivamento-auditado-local-em-15102026).

### Incremento DB-40B.2c — ausência explícita de data e auditoria read-only

Migration `e73c1a9b40d2` torna `lesson_version.reviewed_at` anulável e corrige o
timestamp técnico 07/10 para `NULL`; não usa acesso à fonte, migration ou relógio
atual como substituto de revisão. Datas diferentes são preservadas e downgrade
com valor desconhecido é recusado. A nota default legada passa a declarar que a
homologação continua pendente.

O auditor usa snapshot `REPEATABLE READ, READ ONLY`, sem tabelas pessoais. No DEV,
85 versões tinham a data gerada e 83 antecediam o último acesso da aula à fonte.
A consulta não fez DML. Upgrade/reseed e migration unitária foram ensaiados apenas
no banco 55435; `alembic check` ficou limpo. **1.088 backend e 88 testes operacionais**
passaram. DEV/estudo continuam no schema anterior, sem correção ou rubrica aplicada.
[Contrato completo](historico_operacao_sprints_37_44.md#sprint-40b2c--auditoria-de-rubricas-e-proveniência-15102026).

### Incremento DB-40B.2d — projeção mínima do worker

Migration `f84d1b6c2a90`, depois de e73, cria somente a função fixa
`aulas_speaking_expected_text(attempt_id,user_id)`. Ela lê o snapshot privado como
definer e retorna apenas a cue inglesa quando tentativa, dono e modalidade
coincidem. `PUBLIC`, runtime e backup não recebem execução; o worker recebe apenas
`EXECUTE` e continua proibido de executar `SELECT` na tabela de snapshots.

Não há coluna nova, backfill ou alteração de evidência. A função devolve `NULL`
para legado ausente, e o worker encerra o job antes do provedor. Migration ensaiada
somente no PostgreSQL descartável; DEV e estudo permanecem no schema anterior.

### Incremento DB-40B.2e — referências por identidade, não por posição

Migration `a06f2ce1487b`, depois de f84, acrescenta os vínculos canônicos
`lesson_media.listening_exercise_id` e
`course_review.listening_course_id/listening_lesson_id/listening_media_id`.
O backfill resolve o catálogo legado dentro da aula/curso e aborta a transação se
qualquer referência ficar sem alvo. As colunas antigas de número/posição permanecem
na janela expand, mas não decidem mais a leitura da API.

FKs compostas garantem que a mídia use exercício da mesma aula e que o checkpoint
use aula/mídia do mesmo curso. A unidade não é exigida porque checkpoints podem
retomar legitimamente a aula limítrofe do bloco anterior, como 40–44 → Aula 40.
Índices cobrem os novos FKs e o modelo/Alembic ficaram sem drift.

Downgrade foi ensaiado antes de reordenar. Após mudar temporariamente a posição de
um alvo no banco descartável, a reversão foi recusada e a transação preservou o
head; a posição foi restaurada. A migration não altera snapshots, tentativas,
textos ou IDs existentes. `alembic check` e **1.097 testes backend** passaram;
DEV/estudo permaneceram intocados.

### Incremento DB-40B.2f — prévia de permutação sem DML

Nenhuma migration ou alteração de schema foi necessária. A prévia abre snapshot
`REPEATABLE READ, READ ONLY`, relê as 19 tabelas editoriais e verifica que cada
grupo afetado conserva o mesmo conjunto de UUIDs, os mesmos pais e exatamente o
mesmo conjunto de posições. Cues são validadas dentro da própria mídia, não apenas
no conjunto da aula.

O catálogo atual e o proposto recebem hashes separados. O relatório conta FKs
diretas de tabelas não editoriais para as identidades afetadas, mas não seleciona
valores pessoais. Identidade projetada de schema legado bloqueia aceite; somente
UUID persistido pode sustentar a operação futura.

O ensaio no PostgreSQL descartável confirmou apenas `SELECT`/`SET`, sem avanço de
sequências ou alteração de linhas. Não existe DML nesta etapa. O apply futuro ainda
precisa de advisory lock exclusivo, locks editoriais NOWAIT, comparação do digest,
atualização atômica sem colisão de UNIQUE e recibo append-only. DEV/estudo não foram
consultados nem migrados.

### Incremento DB-40B.2g — recibo e permutação atômica

Migration `b71d4f9e20c3`, depois de a06, cria `editorial_reorder_event`. A tabela
guarda chave UUID da operação, operador/motivo, `current_user`/`session_user`, hashes
do plano/catálogo, mudanças posicionais e impacto agregado. Trigger recusa UPDATE e
DELETE; downgrade é permitido somente sem recibos. Não há backfill ou alteração de
conteúdo nessa migration.

Durante o apply todas as tabelas editoriais ficam congeladas. Cada linha afetada
recebe primeiro uma posição temporária positiva acima do máximo da tabela e depois
a posição planejada; isso mantém as constraints imediatas válidas durante swaps.
Versão e auditoria são atômicas com a permutação. O hash do catálogo relido após DML
precisa coincidir com o estado projetado, que preserva versões históricas omitidas do
pacote atual.

Upgrade, downgrade vazio, re-upgrade, `alembic check` e seed idempotente passaram no
banco descartável. O laboratório de papéis confirmou owner/migrador para aplicação,
backup com SELECT e runtime/worker sem acesso ao recibo. Ensaios com dados sintéticos
foram revertidos; DEV/estudo não receberam migration nem mudança de posição.

### Incremento DB-40C — recibo anônimo e fila de arquivos, 16/10/2026

Migration `f40c2d9a1b73`, depois de `e41f6c2a8d90`, cria
`account_deletion_job` e `account_deletion_file`. O primeiro usa UUID informado pelo
cliente, estados restritos e contagens coerentes; deliberadamente não referencia a
conta excluída. O segundo contém somente a chave opaca temporária, retry e próxima
tentativa, com FK cascade para o recibo e unicidade da chave física.

A transação grava recibo/tarefas antes de apagar `app_user`; todas as entidades
pessoais continuam saindo pelas FKs inventariadas. A exclusão física ocorre depois,
fora da transação relacional, e pode ser repetida com segurança. Um recibo só é
`completed` quando todas as tarefas foram removidas; após dez falhas fica `failed`
para intervenção explícita. Não há sucesso parcial invisível.

Permissões foram declaradas tanto na migration quanto na política reaplicável. O
runtime não apaga recibos e o worker não cria operações. Laboratório de papéis real
aprovou os acessos mínimos; testes de migration cobriram constraints, cascade e
downgrade bloqueado quando há recibo.

Backups seguem snapshots imutáveis e podem reter uma conta excluída até a expiração
de 7 diários + 4 semanais. Restore ocorre isolado e não pode ser promovido diretamente,
pois o recibo anônimo não identifica exclusões posteriores ao snapshot. RPO 24 h e
RTO 60 min são metas a validar, não SLA; em desenvolvimento as cópias ficam somente
neste Mac. Detalhes em
[política de exclusão e backups](politica_exclusao_e_backups_dev_2026-10-16.md).

## Sprint 41 Desempenho de consultas e validação de invariantes

Achados D05, D06 e B10.

### Entregas

- [x] Gerar massa sintética isolada para usuários, eventos, escrita, revisão e jobs, em pelo menos dois volumes documentados.
- [x] Capturar planos de consultas reais de fila, histórico, painel, currículo e expiração; registrar cardinalidade, buffers e tempo.
- [x] Ensaiar índices compostos/parciais candidatos e manter somente os que tragam benefício mensurável na carga definida.
- [x] Revisar índices redundantes, custo de escrita, espaço e manutenção; não remover índice de unicidade por parecer sobreposto.
- [x] Alinhar índices aos cursores e filtros de BE-41, incluindo desempate por ID.
- [x] Validar as constraints adicionadas com verificação de dados e testes de SQL direto em base descartável.
- [x] Criar relatório agregado de referências polimórficas órfãs e incoerências de estado, com prazo e ação para cada caso.
- [x] Avaliar pool total de API/workers, timeout de statement/lock e orçamento de conexões; não apenas aumentar `max_connections`.

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

### Incremento DB-41A — medir antes de indexar

A sonda do backend conta comandos executados e aquisições do pool sem registrar
texto SQL ou bind parameters. No PostgreSQL descartável, a lista de aulas fez 1
comando e o detalhe fez 18. A causa inicial não era ausência de índice: o mapeamento
carregava automaticamente o checkpoint, suas perguntas e respostas corretas que
não pertencem ao contrato público.

Depois de delimitar a projeção, o detalhe passou a 15 comandos e manteve um único
checkout. Nenhuma migration ou índice foi criado, pois ainda não existe plano de
execução nem massa suficiente que justifique custo de escrita adicional. Os testes
fixam os orçamentos iniciais, mas os cenários 1k/10k, `EXPLAIN (ANALYZE, BUFFERS)` e
avaliação de pool concorrente permanecem pendentes.

### Incremento DB-41B — eliminar N+1 antes de criar índice

O painel Hoje executava 38 comandos para uma conta nova. Dez deles eram contagens
sequenciais de aulas faltantes por checkpoint; outros vinham da hidratação de
grafos editoriais inteiros para produzir poucos campos de recomendação.

A regra foi expressa como anti-join correlacionado (`NOT EXISTS`) sobre aulas sem
progresso e tentativa da versão atual. O banco agora escolhe o primeiro checkpoint
elegível na própria consulta. Projeções de coluna impediram carregamentos laterais e
o caso medido caiu para 8 comandos e um checkout. Nenhuma migration ou índice foi
adicionado: planos com massa 1k/10k ainda precisam demonstrar se algum índice traz
benefício real.

### Incremento DB-41C — keyset composto antes de indexar

A primeira paginação de histórico usa a ordenação total
`notebook_entry.updated_at DESC, notebook_entry.id DESC` e a fronteira equivalente
`updated_at < ts OR (updated_at = ts AND id < id_cursor)`. Assim, datas iguais não
dependem da ordem acidental do banco e não se usa `OFFSET` progressivamente mais
caro. `user_id` e filtros editoriais são condições da mesma consulta; o cursor não
substitui nenhuma autorização.

Não houve migration nem índice neste incremento. A página pequena mediu um único
comando de dados, além da autenticação, e um checkout; isso ainda não demonstra o
plano para 1 mil/10 mil linhas. Antes de propor um índice composto como
`(user_id, updated_at DESC, id DESC)`, faltam massa sintética, filtros seletivos,
`EXPLAIN (ANALYZE, BUFFERS)` e comparação do custo de escrita. A rota ilimitada
legada continua somente para compatibilidade e deve ter retirada planejada após a
migração de todos os consumidores.

### Incremento DB-41D — índice composto aprovado por evidência

O laboratório isolado materializou 1 mil e 10 mil notas, com cinco registros por
timestamp para também pressionar o desempate por `id`. A travessia integral de 10
mil itens retornou exatamente os ids esperados em 200 páginas. O plano profundo,
em 90% da massa, caiu de 2,047 ms e 706 blocos de cache para 0,124 ms e 40 blocos
com o candidato `(user_id, updated_at, id)`: reduções aproximadas de 93,9% no
tempo do plano e 94,3% nos blocos somados.

O custo foi medido antes da decisão: inserir 10 mil linhas passou de 118,74 ms
para 135,81 ms (+14,4%); o índice ocupou 456 KiB após 11 mil linhas e 840 KiB
após 21 mil. A massa é sintética e a latência HTTP apresentou variação, portanto
os valores não são SLO. O ganho no plano profundo e a contenção do trabalho do
banco justificam o índice; capacidade e write amplification devem continuar
monitoradas com volume real anonimizado.

A migration `c82f4a9d117e` usa `CREATE INDEX CONCURRENTLY`, fora da transação
Alembic, para reduzir bloqueio de escrita. Antes e depois da criação ela consulta
`pg_index`/`pg_get_indexdef`; um índice homônimo inválido, incompleto ou divergente
interrompe a migration com instrução de inspeção, sem exclusão automática. O
downgrade também exige definição válida e usa `DROP INDEX CONCURRENTLY`.
Upgrade, downgrade, re-upgrade e `alembic check` passaram no PostgreSQL descartável.
Uma execução posterior reconheceu o índice definitivo, percorreu novamente as 200
páginas de 10 mil itens e mediu o plano profundo em 0,067 ms e 45 blocos de cache,
sem criar candidato temporário.

### Incremento DB-41E — escrita keyset sem índice especulativo

Versões e análises usam a fronteira de tupla
`(created_at, id) < (timestamp_cursor, id_cursor)` na mesma ordem decrescente. O
resumo do Caderno usa `(writing_draft.updated_at, writing_draft.id)` e mantém
`user_id`, curso e unidade na consulta. Empates foram exercitados nos testes; o ID
é o desempate obrigatório e o cursor não carrega autorização.

Não houve migration neste incremento. Nas páginas pequenas, os orçamentos ficaram
em 2 SQLs para versões, 4 para feedback com snapshots buscados em lote e 2 para o
resumo, todos já contando autenticação e limitados a um checkout. Isso comprova o
formato da consulta, mas não custo profundo: índice novo só poderá ser proposto
depois de massas isoladas de 1 mil/10 mil registros, filtros seletivos, plano com
buffers e medição do custo de escrita. A migration vigente continua sendo
`c82f4a9d117e`; nenhum dado do ambiente de estudo foi alterado.

### Incremento DB-41F — speaking keyset e projeção medida

A página de speaking usa a fronteira
`(speaking_attempt.created_at, speaking_attempt.id) < (timestamp, id)` e mantém
`user_id`, estado `ready`, curso, unidade e aula na mesma consulta. Tentativas
pendentes não entram. Transcrição vigente e snapshot histórico são buscados em
lote somente para os IDs da página.

A abordagem ORM inicial executou 22 SQLs por causa do carregamento indireto das
coleções da aula. A projeção explícita reduziu o contrato para 5 SQLs fixos por
página, incluindo autenticação, e um checkout. Datas empatadas foram percorridas em
2/2/1 sem lacunas ou repetição, mas essa massa de cinco itens não justifica índice.

Não houve migration. Antes de considerar um composto como
`(user_id, status, created_at DESC, id DESC)`, faltam massa descartável de 1 mil/10
mil gravações, seletividade dos filtros, `EXPLAIN (ANALYZE, BUFFERS)`, custo de
inserção e impacto das rotinas de retenção. O ambiente de estudo não foi consultado
nem alterado.

### Incremento DB-41G — fronteira keyset da revisão sem índice especulativo

A página de itens de revisão usa a fronteira
`(review_item.created_at, review_item.id) < (timestamp, id)` em ordem decrescente.
`user_id`, `status`, curso e unidade permanecem na mesma consulta projetada; o
cursor não carrega nem substitui autorização. Empates foram exercitados em 2/2/1 e
a rota executou 2 SQLs por página, incluindo autenticação, com um checkout.

Não houve migration. Cinco registros comprovam o contrato, não o custo profundo.
Antes de considerar um índice como
`(user_id, status, created_at DESC, id DESC)`, faltam massas descartáveis de 1 mil
e 10 mil itens, seletividade por curso/unidade, `EXPLAIN (ANALYZE, BUFFERS)` e
medição do custo de escrita. O banco de estudo não foi consultado nem alterado.

### Incremento DB-41H — índice da revisão aprovado por medição

O laboratório `make review-benchmark` foi executado no banco marcado
`aulas_ingles_test`, com papel não administrativo `aulas_test`. Ele criou contas
sintéticas isoladas, inseriu massas de 1 mil/10 mil itens suspensos e validou a
ordem total `(created_at DESC, id DESC)` durante 20/200 páginas. A ferramenta usa
advisory lock, confere identidade real antes da conexão útil, remove as contas por
chave e e-mail e elimina o índice candidato mesmo em falha.

Com 10 mil itens, o plano profundo sem candidato executou em 2,299 ms e somou
1.795 blocos de cache. O composto `(user_id, status, created_at, id)` reduziu esses
valores para 0,305 ms e 56 blocos. O índice temporário ocupou 565.248 bytes após
11 mil linhas e 1.056.768 bytes após 21 mil. A inserção única de 10 mil linhas
mediu 234,78 ms sem candidato e 191,28 ms com ele; como ordem, cache e aquecimento
não foram neutralizados, o resultado apenas mostra ausência de regressão grosseira
nesse ensaio e não demonstra escrita mais barata.

A migration `d41e7ac905b2`, sucessora de `c82f4a9d117e`, cria
`ix_review_item_user_status_created_id` por `CREATE INDEX CONCURRENTLY`. Preflight
e pós-verificação exigem índice válido, pronto e definição exata; artefato homônimo
inválido ou divergente bloqueia a execução para inspeção, sem remoção automática.
O downgrade também valida a definição e usa `DROP INDEX CONCURRENTLY`.

Upgrade, downgrade, re-upgrade, teste do índice e gate de drift passaram. Com o
índice final, novo percurso de 10 mil itens fechou 200 páginas; o plano profundo
mediu 0,722 ms/283 blocos e uma rajada de 10 requisições respondeu integralmente.
A variação entre execuções confirma que tempos HTTP locais não são SLO. Nenhuma
migration foi aplicada ao banco de estudo; promoção futura exige backup verificado,
checagem de locks/capacidade e janela operacional.

### Incremento DB-41I — escrita e speaking medidos antes de indexar

O laboratório de escrita materializou 1 mil/10 mil versões, análises e rascunhos
resumidos, sempre com timestamps empatados. O composto de feedback
`(user_id,prompt_id,created_at,id)` reduziu o plano profundo de 1,607 ms e 1.575
blocos para 0,062 ms e 10 blocos por `Index Only Scan`. Após a migration definitiva,
o plano repetido ficou em 0,061 ms/8 blocos. Os candidatos de versões e rascunhos
não foram escolhidos; não foram promovidos.

Speaking percorreu as mesmas escalas. Seu candidato composto não apareceu no plano,
que continuou usando `ix_speaking_status_created`, e houve regressão no p95 da
primeira página. Ele foi removido ao fim do ensaio. A decisão deixa explícito que
mais índices não são automaticamente melhores.

`e41f6c2a8d90` cria somente
`ix_writing_feedback_user_prompt_created_id` com `CONCURRENTLY`, preflight e
pós-verificação de validade/prontidão/definição. O ciclo reversível e o gate de
drift passaram no banco descartável; nenhuma migration foi aplicada ao estudo.

### Incremento DB-41J — volumes restantes, invariantes e orçamento de pool

`make database-benchmark` completou massas isoladas de 1 mil/10 mil usuários,
eventos/intervalos e jobs. Em 10 mil, os inserts mediram 41,26 ms, 316,60 ms e
320,70 ms. Os planos reais registraram: lookup de usuário 0,022 ms/4 blocos;
painel semanal 1,478 ms/178 blocos; fila 0,070 ms/15 blocos; expiração 1,324
ms/705 blocos; currículo 0,579 ms/45 blocos. Scans sequenciais de painel,
expiração e currículo foram mantidos porque as massas/seleções medidas não
justificaram outro índice.

O candidato parcial de fila `(next_attempt_at,id) WHERE status='queued'` foi usado,
mas reduziu apenas 0,070 para 0,064 ms. Seu build levou 25,67 ms, ocupou 360 KiB
antes do probe/1.240 KiB depois e elevou o insert de 10 mil jobs de 320,70 para
362,36 ms (+13,0%). O ganho marginal não justificou manutenção; o índice temporário
foi removido. A limpeza final confirmou zero usuários sintéticos e índice ausente.
Durante o desenvolvimento, uma falha do fixture deixou 1.002 contas exclusivamente
sintéticas; elas foram identificadas pelo prefixo único, removidas do banco de teste
e a rotina passou a executar rollback defensivo antes da limpeza.

A auditoria read-only existente executou 22 regras agregadas de ownership,
referências polimórficas e estados, todas com contagem zero e sem expor conteúdo ou
identidade. Constraints continuam cobertas por SQL direto. O runtime agora aplica
pool 5 + overflow 5, espera 10 s, statement 30 s e lock 5 s; no compose atual, API
e worker declaram no máximo 20 conexões diante das 100 do PostgreSQL, preservando
reserva operacional. Assim, DB-41 fica tecnicamente concluída sem aumentar
`max_connections` nem promover índice sem benefício material. A cadeia Alembic foi
confirmada com head único `e41f6c2a8d90`; a regressão integrada aprovou **1.151
testes backend** e **94 testes operacionais**.

## Sprint 42 Recuperação e evolução segura do banco

Achados D02, D08 e B12; fechamento de D03/D07.

### Entregas

- [x] Criar cenário de upgrade a partir de versão anterior com massa sintética contendo todas as modalidades, inclusive sessões em curso e arquivos de voz.
- [x] Verificar divergência entre modelo SQLAlchemy, Alembic e schema aplicado; falhar gate em divergência não aprovada.
- [x] Ensaiar upgrade com duração/locks medidos e rollback de aplicação sem assumir downgrade destrutivo como solução padrão.
- [ ] Restaurar backup completo de banco e voz em ambiente separado, medindo RTO e perda potencial segundo RPO acordado.
- [x] Validar permissões pós-restore, checksums de áudio, integridade referencial e leitura pela aplicação.
- [x] Integrar revisão compatível de schema ao readiness do backend e à sequência de implantação.
- [x] Monitorar capacidade do banco/arquivos, crescimento de tabelas, conexões, locks, idade de jobs e execução das rotinas de retenção.
- [x] Decidir permanência/retirada de `review_card` legado com reconciliação, janela de compatibilidade e recuperação aprovadas.
- [x] Consolidar runbook com nomes de ambientes, papéis, backups, processo de incidente e comandos que exigem confirmação.

### Critérios de aceite

1. Upgrade preserva usuários, tentativas, revisão, voz, rascunhos, versões, eventos e checkpoints da massa de ensaio.
2. Schema incompatível impede liberação de tráfego; banco acessível não basta para estar pronto.
3. Restore valida banco e arquivos, não apenas saída zero do `pg_restore`.
4. Restore ensaiado não se conecta ao banco real por fallback e não inicia worker que envie áudio a um provedor externo.
5. RPO/RTO medidos atendem à meta combinada, ou impedem o aceite operacional até ajuste.
6. Remoção de legado só ocorre após comprovar ausência de consumidores e preservar o histórico necessário; a escolha de mantê-lo é documentada se ainda houver dependência.

### Evidência executada em 16/10/2026

A origem foi construída diretamente em `e41f6c2a8d90`, com 18 modalidades de
dado pessoal, sessão ativa e WAV sintético. O pacote conjunto foi restaurado em
banco/volume novos e migrado ao head. A migration levou **7,475 s** e as
amostras observaram zero locks aguardando. `alembic check` aprovou e a imagem
anterior `d0b1f8c` leu o schema expandido, comprovando rollback de aplicação.

As contagens, a referência de voz, 16.044 bytes e seu SHA-256 foram preservados.
A leitura pós-restore ocorreu como `aulas_restore`, dono apenas do destino, com
`NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOBYPASSRLS` e
`NOREPLICATION`. As **80 FKs** do schema público estão validadas e nenhuma ficou
`NOT VALID`.

O endpoint operacional agora limita as cinco maiores relações e expõe tamanho,
pool/conexões, locks, idade da manutenção, jobs, retenção, capacidade de voz e
reconciliação do legado. `review_card` permanece durante a exportação 2.x e
a janela de rollback; qualquer vínculo ausente ou divergente bloqueia o gate.

O item de restore/RPO/RTO permanece aberto: pacote até recibo consumiu cerca de
25 s e a migration 7,475 s, mas isso é somente o caminho automatizado. Uma
execução pontual não comprova a cadência diária necessária ao RPO de 24 horas,
nem inclui detecção, decisão e liberação do RTO operacional completo. As
próximas execuções gravam também `technical_recovery_seconds` no recibo.

## Regras para toda mudança de banco

1. Identificar alvo com consulta read-only antes de qualquer operação destrutiva.
2. Nunca usar a base de estudo do usuário como fixture de teste ou massa de benchmark.
3. Planejar evolução compatível, pré-verificação, índices, locks, rollback e backup antes de aplicar migration.
4. Não corrigir automaticamente dados fora da regra sem conhecer origem e decisão do responsável.
5. Nenhum dump, áudio, token, senha ou conteúdo pessoal deve entrar no Git, log de CI ou relatório técnico.
6. Toda tabela nova define chave, propriedade, integridade, índice de acesso e retenção; JSONB não elimina contrato.
7. Índices e checks não substituem transações, idempotência ou autorização da API.
8. A auditoria documental não conclui caixas; cada atualização de status depende de implementação e evidências registradas na sprint correspondente.
