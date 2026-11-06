# Migrations, grants e rotação JWT — Sprint 56

Procedimento preparado em 05/11/2026. Nenhuma migration ou rotação foi aplicada
ao banco de estudo ou à produção. Usar backup com hold e clone restaurado antes
de promover as revisões desta sprint, conforme a política de migrations existente.

## Migrations e integridade

Alembic usa limites próprios: `MIGRATION_LOCK_TIMEOUT_MS=5000` e
`MIGRATION_STATEMENT_TIMEOUT_MS=300000`. O primeiro deve ser menor que o segundo;
valores são validados. São configurações da conexão, preservadas inclusive nos
blocos autocommit de índices concorrentes. O SQL offline também declara os limites.
O timeout de requests da API continua separado.

Cada revisão tem sua própria transação. Uma falha pode deixar revisões anteriores
confirmadas: conferir `alembic current` antes de retomar, nunca presumir rollback
de toda a cadeia. Não aumentar o timeout para contornar lock sem localizar o
processo bloqueador e ensaiar a mudança com volume representativo.

Para CHECK/FK adicionadas a tabelas existentes, a revisão deve criar com
`NOT VALID`; outra revisão/transação executa `VALIDATE CONSTRAINT`. Criar e
validar na mesma transação mantém o lock forte de criação até o final. Tabelas
novas e vazias podem declarar constraints no CREATE TABLE; registrar essa
exceção na revisão. UNIQUE/PK seguem estratégia própria de índice concorrente
quando a tabela já tem volume. Ver [ALTER TABLE no PostgreSQL 16](https://www.postgresql.org/docs/16/sql-altertable.html).

As revisões são:

| Revisão | Operação | Recuperação |
|---|---|---|
| `a56b1c8d9004` | CHECKs NOT VALID para respostas persistidas do provedor | Bloqueia novas violações; não apaga nem encurta dados existentes |
| `b56b1c8d9005` | Validação dos CHECKs | Uma violação histórica impede avançar; diagnosticar por contagem/ID em canal privado, sem texto do aluno em logs |
| `c56b1c8d9006` | IDs/sequências de review_event, study_activity_event e study_active_interval em bigint, incluindo event_id | Exige janela: alteração de tipo pode reescrever tabelas/índices; downgrade recusa IDs ou sequência fora de integer |

Limites: transcrição 5.000 caracteres; parceiro 280; resumo de escrita 1.000;
até 300 palavras temporizadas, 3 dicas de diálogo e 12 sugestões de escrita,
com limites adicionais de tamanho JSON. São compatíveis com os contratos atuais
do gateway. A migration valida o que já existe; não inventa substituições.

O downgrade antigo `b84e2c7a9d31` agora bloqueia escritas enquanto conta respostas
acima de 200 caracteres e recusa a execução se houver qualquer uma. Foi removido
o truncamento `left(...,200)`. A política de backup/ensaio continua obrigatória;
esse guard não transforma downgrade editorial em operação livre de risco.

Metadata define convenção para PK, FK, UNIQUE, CHECK e índice. Nomes explícitos
históricos foram preservados, incluindo as reservas de assistência, para evitar
recriação desnecessária. Novos CHECKs precisam de nome explícito descritivo para
evitar colisões de expressões textuais. Conferir `alembic check` e o SQL gerado;
ver [convenções do SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/constraints.html#configuring-constraint-naming-conventions).

## Fonte canônica dos grants

`ops/roles_policy.sql` é a política operacional vigente: o comando de papéis,
o serviço permissions do EasyPanel e o restore a usam. Os grants embutidos nas
migrations antigas são snapshots históricos e não devem ser editados para
acompanhar permissões novas. Alterar a política vigente, aplicar após migration
e rodar o laboratório antes de liberar a aplicação.

O reset agora remove também ACLs de coluna, de funções e grants de PUBLIC em
tabelas/sequências. Revogar na tabela não remove uma concessão separada por
coluna. A aplicação pelo EasyPanel passa a ser uma única transação: falha não
deixa metade da política aplicada.

O lab de papéis compara privilégios efetivos de tabela, coluna, sequência e
função para runtime, worker e backup. Obtém o estado esperado reaplicando a
política dentro de uma transação revertida; divergência reprova o lab sem
corrigir silenciosamente o estado. Os testes de operações proibidas existentes
continuam necessários, pois igualdade de ACL não substitui o contrato funcional.

## Rotação JWT sem invalidar todas as sessões

Novos tokens incluem `kid`. A assinatura permanece exclusivamente HS256;
o header seleciona uma chave configurada, nunca algoritmo, URL, arquivo ou
conjunto externo. Ver [API do PyJWT](https://pyjwt.readthedocs.io/en/stable/api.html).

`JWT_KEY_ID=legacy` é o padrão de transição: tokens antigos sem kid apontam
somente para essa identidade. A chave anterior só é aceita até o prazo UTC
absoluto configurado; não há tentativa de todas as chaves nem fallback para kid
desconhecido. Novos tokens sempre usam a chave ativa. Refresh continua validando
a sessão/família no banco e preserva seu prazo original.

Configurações: `JWT_KEY_ID`, `JWT_SECRET`, `JWT_PREVIOUS_KEY_ID`,
`JWT_PREVIOUS_SECRET`, `JWT_PREVIOUS_VALID_UNTIL`. No EasyPanel, usar o prefixo
`EASYPANEL_` nos cinco nomes. Os três campos da chave anterior devem estar
juntos; kid/segredo precisam ser distintos dos ativos e o prazo deve ter fuso.
Campos vazios de Compose significam ausência da chave anterior.

1. Implantar primeiro o código com a chave atual intacta e kid `legacy`.
   Confirmar refresh de sessão existente. Separar `AUTH_BUCKET_SECRET` antes
   da rotação se os contadores de login precisarem manter a mesma derivação.
2. Gerar uma chave nova por canal privado, com pelo menos 32 bytes aleatórios,
   e um kid novo. Nunca incluir segredo no comando, log ou evidência.
3. Em múltiplas réplicas, distribuir primeiro a nova chave no slot secundário
   com prazo futuro, mantendo a antiga ativa. Só depois inverter: nova ativa,
   antiga anterior. O slot secundário funciona como chave de verificação;
   nenhuma réplica pode emitir a nova antes de todas conseguirem verificá-la.
4. Definir prazo absoluto da antiga que cubra o restante das famílias de
   refresh ainda válidas (até 30 dias com a configuração padrão), mais a margem
   operacional necessária. Não recomeçar a janela em cada reinício.
5. Conferir login, access antigo durante a janela, refresh emitindo kid novo,
   logout/revogação e rejeição do kid antigo após o prazo. Então remover os
   três campos anteriores e destruir a cópia antiga conforme a custódia.

Se houver comprometimento, a conveniência da janela não se aplica: retirar a
chave comprometida imediatamente e revogar sessões afetadas. Para desfazer uma
rotação operacional, manter ambos os kids durante a janela; retornar ao binário
anterior à Sprint 56 não oferece a validação de duas chaves. O rollback de imagens
não restaura configuração ou segredos automaticamente.

## Catálogo e credenciais sintéticas

O validador recusa faixas inválidas e sobreposições não declaradas. A unidade
40–44 inclui revisão intencional da Aula 40, pertencente à 31–40; o seed declara
`review_overlap_lesson_numbers: [40]`. Essa lista precisa corresponder exatamente
à interseção, referenciar aulas de outra unidade e aparecer no checkpoint.
Não é uma autorização genérica para duplicar aulas. Essa anotação de validação
não altera os registros editoriais, IDs, títulos ou resultados já publicados.

**DB-14 — decisão técnica limitada aos laboratórios:** senhas literais dos
Compose/fixtures descartáveis são credenciais públicas de teste, não segredos
de produção. O risco residual é aceito somente com isolamento de rede, ausência
de volumes/dados de estudo, validação de identidade do banco e portas ausentes
ou em loopback. Nunca reutilizar essas senhas, expor o lab à rede externa ou
copiar configurações de teste para produção. Mudança dessas condições exige
revisar a decisão; a declaração não atesta controles do servidor público.
