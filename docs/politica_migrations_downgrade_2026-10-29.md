# DB-49 — política de migrations, downgrade e isolamento de testes

Registro: 29/10/2026. Aplica-se ao backend e ao job `backend` do CI.
O plano de execução continua sendo o das Sprints 44–49; esta política não
autoriza alterações de dados em estudo ou produção.

## Evolução do schema

Migrations publicadas são histórico imutável. Mudanças novas recebem uma nova
revisão e seguem expansão compatível: adicionar estruturas, preencher apenas
valores dedutíveis, validar constraints e manter contratos antigos durante a
janela documentada. IDs, recibos, revisões e snapshots históricos são evidências;
não podem ser recriados ou descartados para fazer um upgrade passar.

Pré-condições inválidas interrompem a migration e apresentam somente contagens,
sem textos, áudios ou credenciais. Correção de dados exige decisão própria.
Remoções e mudanças incompatíveis pertencem a uma etapa posterior de contração,
com consumidores migrados, backup validado, ensaio em clone isolado e estratégia
de retorno compatível. Uma migration aditiva também precisa de ensaio de locks,
duração e leitura pelo release anterior quando essa compatibilidade for exigida.

## Limite de downgrade

| Revisão/situação | Política |
|---|---|
| Até `c95f3d8ba042`, antes da Sprint 38 | O CI percorre upgrade até essa revisão e downgrade até `base` **apenas em banco vazio e descartável**. Isso não comprova preservação de dados de aluno. |
| `d06a4e9cb153`, filha de `c95f3d8ba042` | Marco irreversível: o `downgrade()` recusa incondicionalmente a remoção de revisões e recibos. Não se atravessa esse marco por downgrade. |
| Revisões posteriores | Reversão depende das pré-condições da revisão e da compatibilidade da aplicação. Algumas recusam downgrade com evidências existentes. Não há permissão geral para voltar de `head` a uma revisão arbitrária. |

O teste `test_concurrency_migration.py` exerce o preflight, a preservação dos
textos sintéticos, as constraints e a recusa explícita do marco. Outras suites
de migration verificam suas condições específicas, incluindo snapshots,
identidades editoriais e evidências de diálogo. Não se removem guardas nem se
usa `alembic stamp` para simular uma reversão que não ocorreu.

Retorno operacional prioriza a imagem anterior **com compatibilidade comprovada
com o schema atual**. Se isso não for possível, restaura-se o backup em outra
base, verificam-se schema, contagens e leitura pela aplicação, e só então se
executa a troca controlada conforme o runbook da Sprint 43. Uma restauração
também exige tratar as gravações posteriores ao backup; não se presume que
elas possam ser perdidas. Nunca executar `downgrade base` na base de estudo
ou produção como procedimento de recuperação.

## O que o CI verifica

O job usa PostgreSQL exclusivo de testes, papel limitado e marcador de banco
descartável. Antes das migrations, `python -m app.testing check` confirma a
identidade. Em runner novo, a sequência é:

1. Ciclo legado vazio: upgrade até `c95f3d8ba042`, depois downgrade até `base`.
2. Upgrade até `head`, repetido para verificar o no-op, seguido de `alembic check`.
3. Seed executado duas vezes para verificar idempotência.
4. Suíte backend com testes de migration/isolamento e cobertura mínima de 90%.
5. Ensaios de falhas, fuso alternativo e contrato depois da janela de writes legados.

Esses checks não homologam um downgrade de produção nem substituem backup,
restore e ensaio com o release anterior. O ciclo legado só pode começar em
base vazia: não deve ser copiado para uma base que já chegou a `head`.

## Isolamento por teste

`backend/tests/db_isolation.py` classifica explicitamente as 53 tabelas dos
modelos: 19 de conteúdo/seed e 34 de dados transitórios do cenário. Uma tabela
nova sem classificação ou uma classificação sobreposta interrompe a limpeza.
`alembic_version` é metadado do migrador e fica fora dessa limpeza.

A fixture `banco_por_teste` confirma ambiente, URL e identidade real da conexão,
incluindo marcador e privilégios do papel; executa um único `TRUNCATE ...
RESTART IDENTITY RESTRICT` nas 34 tabelas antes e depois do cenário; confirma
a transação e descarta o pool ao terminar. Não usa `CASCADE`: uma FK nova de
uma tabela externa à lista impede a operação em vez de ampliar seu alcance.
Nenhuma sequência de seed é reiniciada. A limpeza também alcança jobs de
exclusão, buckets de autenticação e heartbeats, sem depender de FK para usuário.

Commits reais e conexões independentes continuam disponíveis para testar
concorrência, locks, API e worker. Testes puros não solicitam essa fixture e
não conectam ao banco. A suíte deve rodar em série por banco; múltiplos processos
pytest precisam de bases isoladas, nunca de `xdist` sobre a mesma base.

Para conteúdo curricular temporário, `catalog_lab` fornece sessão e cliente
HTTP presos a uma transação externa. Cada sessão usa savepoints; o `commit()`
do cenário torna o conteúdo visível à API desse cliente, mas a saída da fixture
sempre desfaz a transação externa, inclusive após falha. Não usar essa fixture
para provar concorrência entre conexões. Sequências PostgreSQL podem avançar
mesmo após rollback; lacunas de IDs são normais e não justificam reset do seed.

O cenário da unidade planejada `31-35` foi convertido para essa fixture. Saiu
o `DELETE` global por slug, que dependia de um detalhe curricular para limpar
o banco. Os laboratórios editoriais que já usam rollback externo continuam
com seu próprio isolamento.

## Verificação local reproduzível

`make test-api-prepare` prepara somente a base descartável da porta 55435.
Na pasta `backend`, executar `uv run ruff check .`, `uv run mypy app` e
`uv run pytest -q --cov --cov-report=term-missing:skip-covered --cov-fail-under=90`.
Ao terminar, `make test-db-down` na raiz para somente essa stack e preserva
o volume sintético. Não usar a URL de desenvolvimento ou produção no pytest.

Os testes novos verificam preservação de todos os registros das 19 tabelas de
seed e da sequência de aulas, limpeza idempotente de dados confirmados,
recusa de dependência fora do inventário, recusa de ambiente não descartável,
inventário incompleto e rollback de conteúdo visível à API após commit e falha.
Os resultados datados e o estado de publicação ficam no plano das Sprints 44–49.
