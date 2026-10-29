# Operação vigente — ambientes, testes e recuperação

Atualização: 29/10/2026 (INFRA/SEC-49). Este runbook reúne os caminhos operacionais;
resultados datados ficam no [histórico](historico_operacao_sprints_37_44.md) e
no [plano das Sprints 44–49](plano_sprints_44_49_frentes_e_assistente_de_fala_2026-10-21.md).

## Escolha o ambiente antes de executar

| Ambiente | Configuração | Destino |
|---|---|---|
| Desenvolvimento | `infra/compose.yml`, `.env` | Web 5180, API 8010, PostgreSQL 5433 |
| Estudo local, com dados do aluno | `infra/compose.prod.yml` + `infra/compose.roles.prod.yml`, `.env.prod` + `secrets/roles-prod.env` | Web 5181, API 8011, PostgreSQL 5434 |
| Produção pública | `infra/easypanel/compose.yml` e configuração privada da VM | EasyPanel `papalino/aulas-ingles` |
| Backend de teste | `infra/compose.test.yml` | PostgreSQL descartável em 55435 |
| E2E | `infra/compose.e2e.yml`, `infra/e2e.env` | Web descartável em 5198 |
| Recuperação, upgrade e papéis | `infra/compose.recovery.yml`, `compose.upgrade.yml`, `compose.roles.yml` | Redes internas; sem portas públicas |
| Rotação de segredos | `infra/compose.rotation.yml` | Banco sintético exclusivo; rede interna sem portas públicas |

O nome legado `prod` dos arquivos/volumes locais foi **mantido**. A stack
`aulas-ingles-prod` continua sendo estudo local, não a VM. Renomeá-la criaria
outro projeto/volume e poderia ocultar os dados existentes. Nenhum desses
arquivos é candidato a remoção enquanto essa instalação existir.

Nunca usar pytest ou E2E nos bancos de desenvolvimento, estudo ou produção.
Não imprimir `.env`, credenciais, Compose resolvido nem inspect completo.
Segredos de papéis ficam em `secrets/`; dumps e voz ficam em pacotes privados.

## Desenvolvimento e verificações locais

Em clone novo: `cp .env.example .env`, depois `make up`. O comando sobe o
desenvolvimento, migra e carrega o seed. Use `make logs`, `make health` e
`make down` para essa stack. `make reset` apaga seu volume e só cabe em uma
base de desenvolvimento explicitamente descartável.

`make help` lista os comandos principais; `make help-all` inclui ferramentas
avançadas e laboratórios. Ambos somente mostram comandos.

```bash
make test-api       # prepara banco descartável, migra, semeia e roda pytest
make test-db-down   # encerra somente esse banco, preservando o volume
make test-web
make lint
make test-recovery # testes puros de ops; sem Docker/banco
```

A [política DB-49](politica_migrations_downgrade_2026-10-29.md) descreve o
isolamento: identidade real do banco/papel, limpeza somente das tabelas fora
do seed e rollback do catálogo temporário. Não rodar dois pytest sobre a mesma
base. Variáveis de outro ambiente fazem a guarda recusar a operação.

Para E2E, instalar as dependências de `e2e` e os browsers Playwright; executar
`make e2e-up`, `make test-e2e` e `make e2e-down`. As guardas conferem projeto,
volumes, origem, papéis e identidade do banco. O encerramento preserva volumes.
As suítes isoladas `npm --prefix e2e run test:queue` e `test:pwa` têm seus
próprios servidores e não usam o banco do aluno.

## Estudo local e produção pública

`make prod-up` e `make prod-seed` continuam bloqueados: o fluxo antigo iniciava
código antes do gate de migration e permitia seed editorial genérico.
`make prod-logs` e `make prod-down` referem-se **somente ao estudo em 5181**;
o segundo interrompe a disponibilidade desse ambiente.

Para atualizar o estudo, seguir a sequência da
[Sprint 43](sprint_43_implantacao_estudo_2026-10-16.md) e o
[checklist de release](runbook_sprint_42.md#checklist-obrigatório-de-release):

1. Identificar release, banco, papéis, volumes e imagens anteriores.
2. Construir imagens e capturar backup anterior na janela prevista.
3. Restaurar em clone vazio isolado e ensaiar migration, leitura e preservação.
4. Migrar pelo papel migrador, conferir grants/schema/health e só então liberar web.
5. Conferir worker e funcionamento, capturar backup posterior e guardar recibos.

Para a VM, usar o [runbook EasyPanel](deploy_easypanel.md) e o pipeline
versionado. `make deploy-public sha=<SHA>` exige release de `origin/main` e
as guardas do script; `make deploy-public-dry-run sha=<SHA>` mostra o plano
sem contatar a VM. O Git local não é evidência de atualização da VM.

`/api/live` verifica o processo. `/api/health` verifica banco e schema, com
resposta pública sem versões internas; detalhes operacionais exigem a rota
protegida. `make operations-check` usa `OPERATIONS_BASE_URL` e token privado
do ambiente escolhido. Falha de readiness mantém o release bloqueado.

## Backup e restauração

`make backup source=lab|dev|prod|public` exige uma origem explícita. `prod`
é o estudo local; `public` usa o procedimento da VM. Capturas locais de dados
reais exigem quiescência conforme as guardas. Não mover pacotes privados para
repositório, logs, artifacts públicos nem ambientes sem a proteção prevista.

`make backup-verify f=<pacote>` verifica manifesto e checksums.
`make restore f=<pacote> confirm=aulas-ingles-recovery/target-db` aceita
somente destino vazio e identificado; não sobrescreve estudo ou produção.
O manifesto e os recibos vinculam banco, voz e provas. Hash não autentica a
origem: restaurar apenas pacotes confiáveis.

`make backup-prune` apresenta o plano de retenção; `backup-prune-apply`
executa a política implementada. Não apagar backups ou volumes para fazer um
ensaio passar. RPO/RTO e guarda externa de chave só estão comprovados quando
houver execução e recibo, conforme as pendências no plano.

A revisão `d06a4e9cb153` bloqueia downgrade destrutivo. Retorno deve usar uma
imagem anterior comprovadamente compatível ou restauração em outra base com
troca controlada; ver a [política de downgrade](politica_migrations_downgrade_2026-10-29.md).

## Laboratórios sob demanda

O [ensaio SEC-49](rotacao_segredos_2026-10-29.md) verifica senhas dos quatro
papéis, sessões JWT e tokens de um gateway sintético. Use
`uv run --project backend python -m ops.rotation_rehearsal up|check|down`,
selecionando uma ação por chamada. O runbook registra a ordem de rotação,
o impacto nas sessões e os limites da prova; nenhuma ação altera produção.

Os trios `recovery-lab-up/prepare/down`, `upgrade-lab-up/prepare/down` e
`roles-lab-up/prepare/down` aparecem em `make help-all`. Usar somente recursos
descartáveis marcados, sem portas nem volumes de estudo. `down` não usa `-v`.
Um destino já preenchido é preservado e recusado; não limpar para repetir.

O upgrade DB-42 ainda prova leitura pela aplicação anterior. Antes de
`make upgrade-lab-up`, preparar a imagem fixa:

```bash
uv run --project backend python -m ops.rollback_image
make upgrade-lab-up
make upgrade-lab-prepare
make test-upgrade-integration
make upgrade-lab-down
```

No CI, checkout do commit completo `d0b1f8cf7b02ca8b06ea75876153d2b1079ea83d`
e build da imagem anterior são etapas explícitas. O Makefile apenas exige
que a imagem exista; não reconstrói silenciosamente um checkout histórico.
`ops.rollback_image` permanece ferramenta local sob demanda. O teste de
compatibilidade após upgrade continua obrigatório.

`ops.rollout --profile study|concurrency` reúne os ensaios históricos 37/38,
com ações `capture`, `rehearse` e `verify`, revisões fixas e recibos preservados.
Não é um migrador genérico. O perfil study inclui `writing-rubrics`, desativado
para execução indiscriminada desde 40B.2c; a recusa continua valendo. As guardas
não podem ser relaxadas para aplicar esses perfis ao release atual.

Os perfis `dev-check` e `assist-check`, usados pelos alinhamentos históricos
39A/39F, ficam no overlay explícito `infra/compose.legacy-rehearsal.yml`.
Quando um ensaio histórico exigir esses recursos, combinar o Compose recovery
com esse overlay e selecionar somente o serviço do perfil, após o preflight
`ops.recovery lab-resources`. Não entram no CI ou na stack padrão. Os recursos
`final39-check` e o script `ops.sprint39_rollout` foram retirados; seu código
continua no histórico Git, junto dos registros datados.

## Encerramento e manutenção da topologia

Conferir containers por labels `com.docker.compose.project` e `service`, não
por busca genérica no nome. Encerrar somente o laboratório identificado, sem
`docker system prune`, `volume prune` ou `down -v`. Preservar outros projetos.
Branches locais podem ser retiradas após provar que são ancestrais de `main`
e não estão em worktrees; usar `git branch -d`, sem forçar e sem apagar remotas.
