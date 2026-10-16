# Sprints de backend para correção e confiabilidade do estudo

Atualização: 16 de outubro de 2026. **BE-39G/H implementada; BE-40, BE-41 e o escopo técnico de BE-42 concluídos.** O novo head BE-40 `f40c2d9a1b73` foi aplicado apenas no banco descartável e nos laboratórios, não em DEV/estudo. Consulte o [registro operacional 40C/40D](operacao_sprint_37.md#sprint-40c40d--exclusão-histórico-e-fechamento-técnico-em-16102026) e a [matriz da Sprint 42](matriz_aceite_sprint_42_2026-10-16.md). A triagem Trivy local das imagens foi concluída após substituir as bases vulneráveis; o aceite integral de BE-42 continua bloqueado por HTTPS público real e pela confirmação do inventário no próximo commit da CI.

Referência: [auditoria técnica e achados](auditoria_tecnica_frontend_backend_banco_2026-10-13.md). Este plano mantém FastAPI, SQLAlchemy e o monólito atual. A prioridade é corrigir regras de estudo e transações, não introduzir microserviços.

## Sequência e contratos

| Pacote | Resultado | Contrato principal |
|---|---|---|
| BE-37 | Correção de escrita e testes seguros | Rubrica tipada e mensagens de correção |
| BE-38 | Concorrência controlada e autenticação protegida | Refresh atômico, revisão/idempotência e conflitos |
| BE-39 | Tempo, áudio e assistência consistentes | Eventos ativos, limites de mídia e reserva de cota |
| BE-40 | Histórico preservado e exportação completa | Versão editorial, política de publicação e export v2 |
| BE-41 | Consultas previsíveis e paginação | Cursores, projeções e limites |
| BE-42 | Operação verificável e release seguro | Readiness, métricas, recuperação e gates |

Contratos sugeridos devem ser refinados com frontend e banco antes da implementação. Não alterar rotas/formatos antigos sem migração compatível e atualização do baseline OpenAPI.

## Sprint 37 Correção de escrita e isolamento dos testes

Prioridade P0/P1. Achados D01 e B01; suporte a F01/F02/F10.

### Entregas

- [x] Com DB-37, separar configuração da suíte pytest e bloquear seu teardown/migrations/seed se banco/role/ambiente não forem explicitamente descartáveis. Isolamento Playwright local entregue no sexto incremento DB-37.
- [x] Remover a necessidade de conexão/teardown de banco em testes de funções puras; manter fixtures de integração restritas às suítes que precisam delas.
- [x] Definir contrato de rubrica para palavras/expressões literais, quantidade, alternativa `any/all` e fala entre aspas; aplicar às 82 propostas.
- [x] Corrigir matching multiword e espaços periféricos, com limites de palavra e tratamento consistente de apóstrofos/capitalização.
- [x] Inventariar os 236 requisitos originais e testar alcançabilidade/negativos das 82 propostas, inclusive os requisitos incompatíveis: 247 critérios após 11 desdobramentos.
- [x] Completar exemplos de redações naturais por proposta, com positivos e negativos discriminantes.
- [ ] Homologação pedagógica humana dos 82 exemplos — pendência de Jeferson/professor, separada do fechamento técnico por autorização explícita em 13/10/2026. Testes não substituem esse aceite.
- [x] Revisar quantidades, obrigatoriedade e alternativas observáveis: ocorrências, termos distintos e todos os marcadores; explicitar limites de critérios que dependem de interpretação gramatical.
- [x] Versionar o algoritmo/rubrica usado em novos feedbacks. Explicar resultados antigos, sem reavaliá-los silenciosamente.
- [x] Uniformizar códigos de erro necessários ao frontend para sessão inválida, indisponibilidade e conflito, preservando mensagens seguras.

### Critérios de aceite

1. Guardas abortam antes de abrir transação mutável quando apontados para a base de desenvolvimento ou produção. O teste da guarda não exclui dados para provar proteção.
2. Teste de domínio puro não executa limpeza de usuários nem depende de PostgreSQL.
3. `Are you Anna?` satisfaz a expressão `are you`; `he` não é encontrado dentro de `the`; espaço final em termo é normalizado ou rejeitado no carregamento editorial.
4. Cada proposta possui pelo menos um texto compatível e casos negativos discriminantes; nem repetição vazia de termos nem textos fora da tarefa recebem garantia de gramática correta.
5. Ollama continua opcional e não é usado para encobrir falha determinística.
6. Evidências antigas permanecem intactas; novos resultados indicam a versão da regra.

### Testes e entrega técnica

Unitários de matching/tokenização, contrato de rubrica e parametrização sobre todo o seed; integração de feedback/evidência/revisão em DB descartável; OpenAPI baseline e tipos frontend. Tratar normalização como regra explícita e não como regex genérica que “aprova mais textos”.

Fora do escopo: NLP avançado, substituição do corretor por LLM e alteração global de notas históricas.

### Registro de execução — primeira entrega, 13/10/2026

Implementados `app/db/test_safety.py`, preflight `python -m app.testing`,
guardas de conexão no engine/Alembic, fixtures restritas a `client`/`session`,
Compose exclusivo e ajuste dos comandos Make/CI backend. A verificação real
da conexão valida `current_database`, `current_user`, comentário de descarte e
ausência de `SUPERUSER`/`CREATEDB`/`CREATEROLE`, antes de liberar a conexão para
operações da suíte. Configuração divergente não é corrigida silenciosamente.

A rubrica de escrita e os códigos de erro ainda não foram alterados. Esta
entrega não conclui BE-37, FE-37 ou DB-37.

Evidências locais desta entrega:

- `pytest -q --cov --cov-report=term-missing:skip-covered --cov-fail-under=90`:
  **279 testes aprovados**, cobertura **93,65%**, exclusivamente na base nova.
- `TZ=Pacific/Kiritimati make test-api`: **279 testes aprovados** novamente,
  validando também a receita completa de preparação e execução pelo Make.
- 55 testes de guardas/regras puras aprovados com o alvo de banco na porta
  indisponível `127.0.0.1:1`, demonstrando ausência de dependência de conexão.
- `ruff check .` e `mypy app`: aprovados (56 arquivos na análise de tipos).
- Seed de 82 aulas aplicado e reaplicado sem erro; OpenAPI baseline incluído
  na suíte backend, sem mudança de contrato de produto.
- Registro da base sentinela igual antes/depois da suíte; conexão negada ao
  papel `aulas_test`.
- Um downgrade até `base` sobre o catálogo já semeado foi recusado pela
  proteção histórica de `c1d4e8f6a290` contra números de aula repetidos entre
  cursos. A transação foi revertida, o head continuou `b84e2c7a9d31` e a nova
  preparação passou. Não se declara esse downgrade aprovado nem se removeu
  conteúdo para contornar a guarda; o CI mantém seu ciclo em base ainda vazia,
  antes do seed. O workflow remoto ainda não foi executado nesta entrega.

O contrato/matching/versionamento inicialmente apontado como próximo passo foi
implementado no segundo incremento abaixo.

### Registro de execução — segunda entrega, escrita v2, 13/10/2026

Implementados `domain/writing_rubric.py`, novo matching em `domain/writing.py`,
validação anterior a qualquer escrita do seed e versão/snapshot no feedback.
Os 236 critérios originais foram normalizados e revisados; exigências compostas
foram desdobradas em 247 critérios nas mesmas 82 propostas. Não houve alteração
de títulos, instruções, IDs/posições das propostas ou conteúdo externo às rubricas.

Contrato editorial:

| Campo | Regra |
|---|---|
| `kind=markers` | Palavras e expressões literais em `terms`; não aceita regex editorial |
| `kind=quoted_speech` | Par de aspas retas ou curvas fechado, contendo palavras; `terms=[]` |
| `match_mode=any` | Alternativas contribuem para a quantidade mínima |
| `match_mode=all` | Cada marcador precisa aparecer `min_count` vezes |
| `count_mode=occurrences` | Conta ocorrências não sobrepostas; `want to` não conta também como `want` no mesmo critério |
| `count_mode=distinct_terms` | Conta marcadores diferentes, apenas com `any`; repetições não aumentam diversidade |
| `min_count` | Inteiro entre 1 e 20, validado; defaults permitem ler o contrato legado |

Caixa, espaços e apóstrofos tipográficos são normalizados. `he` não coincide
com `the` nem `he's`; `are you` não atravessa um ponto entre palavras.
`woo-hoo` aceita o hífen tipográfico equivalente, mas não se inventam sinônimos.
Sufixos explícitos como `'ll be` reconhecem `I'll be`; `'d` não é expandido
ambiguamente para had/would. A pontuação interna de expressões é literal.

Exemplos de revisão editorial: Level 1 Aula 1 exige três usos de `I am`/`I'm`;
Aula 2 exige `he`, `she` **e** `they`; Aula 31 exige `ought to`, não `ought`
sozinho; Aula 33 exige dois marcadores diferentes de sequência; Aula 35 passa
a exigir três unidades/embalagens, alinhadas à instrução de três itens;
Level 2 Aula 17 exige três reflexivos diferentes; Aula 20 verifica aspas
fechadas e exige tanto `said` quanto `told`.

Preservação e interface:

- Migration aditiva `c95f3d8ba042`: `algorithm_version`, `rubric_version` e
  `rubric_snapshot` em `writing_feedback`, sem recalcular checks, ready ou evidências.
- Registros anteriores recebem `legacy-v1`, sem inventar snapshot histórico.
  Novos registros da API recebem `writing-rules-v2`, hash SHA-256 da rubrica
  normalizada e cópia de título, instrução, mínimos e requisitos efetivamente usados.
- Histórico e exportação preservam o snapshot mesmo se a proposta for editada.
  Downgrade é recusado se houver feedback versionado, para não descartar a evidência.
- Frontend identifica a regra, diferencia legado, avisa que resultado anterior
  não foi recalculado e troca “Texto pronto” por “Critérios automáticos atendidos”.
  No Caderno, “Regras das análises salvas” permite consultar essa identificação.
- A assistência continua opcional, sem mudar o resultado determinístico.
  Nenhuma chamada real ao Ollama foi necessária para validar o corretor.

Limites que continuam explícitos: presença de `if`/`will`, auxiliares ou adjetivos
não demonstra sintaxe, concordância, pertinência ou coerência. O avaliador não
garante gramática correta nem proficiência. As sondas de 82 propostas e 247
critérios são testes técnicos, não redações exemplares ou homologação por professor.

Rollout: migration e seed desta entrega foram aplicados **somente** ao PostgreSQL
descartável em 55435. Nenhuma credencial ou dado da base de estudo foi alterado.
Antes de ativar o código no ambiente de estudo, é necessário preparar backup
verificável, aplicar a migration antes de servir o backend novo e carregar as
rubricas revisadas. Não servir o código novo sobre o schema antigo; não usar
downgrade destrutivo nem reexecutar avaliações para “corrigir” o histórico.
O isolamento E2E e a correção do backup permanecem em DB-37.

Pendências BE-37: exemplos pedagógicos completos e códigos de erro para
sessão/indisponibilidade/conflito. A recomendação de implementar refresh/reenvio
foi atendida no [terceiro incremento FE-37](sprints_37_42_frontend_2026-10-13.md).
O quarto incremento frontend entrega fila sem descarte silencioso e com
coordenação entre abas. Seus testes Chromium usam API simulada e não substituem
validação integrada de concorrência/idempotência no backend. Permanecem no
frontend, após o quinto incremento de armazenamento/barreiras/mensagens, o aceite
integrado e a revisão dos alertas de dependências de teste.
O tratamento de 503 local no cliente não substitui os códigos de erro pendentes
no backend; Web Locks da fila não resolve atomicidade do refresh em BE-38.

Validação final do segundo incremento:

- **668 testes backend aprovados**, cobertura **93,79%**, na base exclusiva.
- **169 testes frontend aprovados**, incluindo regra atual/legada e histórico no Caderno.
- Ruff, mypy (57 arquivos), ESLint, TypeScript, baseline OpenAPI e tipos gerados aprovados.
- Build e orçamento do frontend aprovados: **163,9 KiB gzip** de JS/CSS total.
- Ensaio transacional da migration preserva texto/checks/ready anteriores;
  editar uma rubrica mantém o snapshot dos feedbacks já salvos e exportados.
- Sem nova execução de E2E, homologação visual em navegador ou leitor de tela,
  teste com provedor real, execução remota do CI, commit ou push.

### Apoio ao sexto incremento — E2E integrado isolado

O Compose E2E reutiliza `app.testing prepare/check` e a guarda de conexão,
com banco/volume próprios, distintos inclusive do pytest em 55435. A API
aguarda migrations/seed com sucesso antes de servir o nginx. Não foi criado
endpoint de teste no contrato público e não houve alteração de schema ou
lógica backend adicional nesta etapa. Worker/provedor assistido ficam fora
dessa stack; o status de BE-37 permanece em andamento pelas pendências acima.

### Apoio ao sétimo incremento — recuperação de banco e voz

DB-37 entregou comandos de backup conjunto e restore restrito ao laboratório
vazio, sem endpoint novo nem alteração da lógica de produto. O ensaio real
recuperou schema `c95f3d8ba042`, 82 aulas e uma gravação sintética; 29 testes
operacionais passaram. A produção continua em `b84e2c7a9d31`, API/worker
ativos, sem dump ou migration de estudo neste incremento. A rotina recusa
backup real sem manutenção autorizada; o rollout da escrita v2 continua
pendente desse backup e da verificação correspondente. A suíte backend de
668 testes é evidência anterior, não foi repetida aqui. Detalhes, limitações
e próximo passo de papéis mínimos no
[registro DB-37](sprints_37_42_banco_de_dados_2026-10-13.md#sétimo-incremento--backup-conjunto-e-restore-isolado-13102026).
Evidências operacionais e limites estão no
[sexto incremento DB-37](sprints_37_42_banco_de_dados_2026-10-13.md#sexto-incremento--stack-e2e-isolada-13102026).

### Oitavo incremento — fechamento técnico, 13/10/2026

Entregas finais:

- Corpus autoral com **82 exemplos completos** nos arquivos
  seed/writing_examples_level_1.json e seed/writing_examples_level_2.json.
  Os 83 testes do corpus validam cobertura, mínimos, requisitos e negativos
  por remoção dos marcadores/aspas. Não são apenas listas de palavras; também
  não são respostas homologadas por professor nem material exposto como gabarito.
- Erros 401/409/503 com code, detail e request_id, cabeçalho X-Error-Code e
  no-store. Login inválido usa invalid_credentials; demais 401 session_invalid;
  409 conflict; indisponibilidade service_unavailable. Detalhes legados
  estruturados e headers de autenticação/retry preservados.
- Falhas de conexão/pool viram 503 sem SQL, parâmetros ou segredos na resposta.
  Readiness indisponível mantém seu formato próprio, com code e header comuns.
  Request-id externo limitado a ASCII seguro e 128 caracteres.
- OpenAPI baseline e tipos TypeScript atualizados; novos testes de erro
  não dependem de PostgreSQL.
- Comando writing-rubrics valida o catálogo inteiro antes de qualquer alteração,
  atualiza somente requirements e preserva IDs/evidências; testado duas vezes
  no clone real. Não se executou seed completo no ambiente de estudo.
- Migration aditiva c95f3d8ba042 aplicada pelo migrador limitado em 5181:
  feedbacks anteriores não foram recalculados. Hashes de 39 tabelas, excluídos
  somente os campos planejados, conferiram antes/depois.

Validação: **765 testes backend**, **93,57% de cobertura**, Ruff e mypy
(60 arquivos) aprovados. Frontend: 263 testes; E2E: 98 cenários isolados.
API/worker passaram a usar aulas_runtime/aulas_worker. Ensaios DML/HTTP,
worker, migrador e recusas de permissões executados no laboratório; produção
recebeu apenas rollout e verificações de leitura, sem usuários sintéticos.

Fechamento **técnico autorizado** por Jeferson, com revisão humana dos exemplos
explicitamente pendente. Os avisos de limitação do corretor permanecem;
não se substituiu validação linguística por presença lexical ou Ollama.
Próxima implementação: BE-38 em conjunto com FE/DB-38.
Procedimento, backup e limitações: [operação local](operacao_sprint_37.md).
Os registros anteriores retratam suas respectivas etapas, não o status vigente.

## Sprint 38 Autenticação e mutações concorrentes

Prioridade P1. Achados B02, B03, B04, B05 e D05/D07. Dependência: DB-38 para eventos/revisões e FE-38 para conflitos.

### Entrega técnica e implantação em 14/10/2026

Implementação validada em bases descartáveis e posteriormente aplicada ao estudo,
com backup e ensaio em clone. Contrato escolhido: revision na leitura,
expected_revision na escrita e HTTP 409 com detail.code/current recuperável.
O cliente novo sempre envia revisão. Clientes antigos têm compatibilidade somente
até 13/11/2026 00:00 UTC (LEGACY_WRITES_UNTIL); após essa data recebem 428 e devem
recarregar. O endpoint de feedback analisa um snapshot independente do autosave e
devolve source_text_hash SHA-256, sem reavaliar resultados antigos.

Revisão SM-2 exige UUID por operação no cliente novo. Fingerprint inclui item,
nota e revisão esperada. Recibo e estado são confirmados na mesma transação;
replay retorna o mesmo resultado, inclusive após exclusão do item. Recibos ficam
até exclusão da conta; essa retenção cobre retries sem uma janela curta de perda.
Não foram criados eventos fictícios para o histórico anterior.

Refresh usa lock transacional por conta, família e sucessor determinístico,
sem token bruto no banco. Janela de 10 segundos aceita repetição legítima do
refresh anterior e devolve o mesmo sucessor. Durante a janela o sucessor não
rotaciona novamente. Logout revoga toda a família; replay fora da janela recebe
401 sem revogar outras famílias. Revogados serão mantidos até expiração; a rotina
de expurgo em lotes continua em DB-39, sem limpeza automática de sessões neste ciclo.

Login/registro compartilham limites por identidade (20) e origem (200) a cada
300 segundos. Contadores usam HMAC, nunca e-mail/IP em claro, e retornam 429 com
Retry-After. X-Forwarded-For não é confiado pela aplicação. A configuração de um
proxy público deve restringir os IPs confiáveis do servidor ASGI; não usar curinga.
Buckets antigos são removidos após 24 horas quando há nova autenticação.
Argon2 usa pool limitado a dois hashes simultâneos por processo e libera a conexão
SQL antes de verificar senha. Perfil público exige COOKIE_SECURE e PUBLIC_ORIGIN
HTTPS; tráfego HTTP público recebe 426 (exceto /api/live para a sonda interna),
respostas da API não entram em cache. Proxy/TLS público não foi implantado.
O perfil local permanece HTTP e deve continuar restrito a loopback.

Ensaios específicos incluem cadastro concorrente, cinco refreshes, seis repetições
da mesma nota, rollback de recibo/estado, rascunho/versões e merge de jornada.
SQLSTATE de deadlock/serialização/lock indisponível retorna 503, colisão de
unicidade retorna 409; SQL, parâmetros e texto pessoal não entram na resposta.
Não há retry ilimitado nem repetição automática de mutação não idempotente.

Ensaio controlado de oito logins reais concorrentes, pool de dois hashes:
/live teve máximo de 9,54 ms; high-water RSS do processo passou de 161,56 para
225,09 MiB. Cada hash usa 65.536 KiB de memória configurada. São medidas locais
de um processo de teste, não um SLA nem dimensionamento homologado de produção.
O limitador é por processo; somar os limites ao aumentar o número de workers.

Regressão final: **789 testes backend, 93,54% de cobertura**, Ruff/mypy (63 arquivos),
contrato OpenAPI e tipos TypeScript aprovados. Integração: 270 testes frontend,
106 E2E desktop/mobile e ensaio adicional de navegação SPA aprovado nos dois.

Implantação autorizada em 14/10: backup conjunto restaurado, 39 tabelas históricas
preservadas, migration aplicada pelo migrador e API/worker/web atualizados em 5181.
Readiness, catálogo e Aula 31 responderam 200; conexões reais confirmaram runtime
e worker limitados. Não houve alteração editorial nem seed completo.
As duas divergências históricas de jornada detectadas na auditoria foram mantidas
idênticas, não declaradas corrigidas: 20 jornadas sem detalhamento completo e 15
sem data final. Nova inconsistência não é aceita pela prova de rollout.
Procedimento específico: ops/concurrency_rollout.py. study_rollout.py continua
fixo na Sprint 37. Detalhes no [registro operacional](operacao_sprint_37.md#sprint-38--implantação-autorizada-em-14102026).

Referências técnicas: [locks PostgreSQL 16](https://www.postgresql.org/docs/16/explicit-locking.html)
e [pool limitado do AnyIO](https://anyio.readthedocs.io/en/stable/threads.html).

### Entregas

- [x] Consumir refresh de forma atômica, com lock ou atualização condicional e política de sucessor/reutilização definida.
- [x] Tratar corretamente refresh concorrente legítimo entre abas; não devolver dois sucessores independentes nem encerrar a conta por uma corrida esperada.
- [x] Introduzir limitação de autenticação/cadastro por identidade e origem, com janela, resposta 429 e observabilidade sem PII.
- [x] Executar Argon2 fora do event loop com limite de concorrência; verificar impacto em latência e memória.
- [x] Transformar colisão concorrente de cadastro em resposta controlada, sem traceback ou IntegrityError exposto.
- [x] Definir perfil público HTTPS com cookie Secure e headers privados; manter perfil local HTTP explicitamente separado.
- [x] Criar evento idempotente de avaliação SM-2, com payload comparado, versão esperada e escrita atômica do estado e do histórico.
- [x] Aplicar controle otimista ao rascunho e alocar revisões sob proteção transacional.
- [x] Definir merge de etapas concluídas e upsert idempotente para marcação de aula/itens de revisão; não alterar a semântica de desmarcação sem decisão explícita.
- [x] Padronizar resposta de conflito com código, revisão corrente e instrução de recuperação; não devolver texto de outro usuário em nenhuma hipótese.

### Critérios de aceite

1. Duas conexões reais disputam o mesmo refresh: há somente uma transição válida conforme a política, sem 500 e sem sucessores inconsistentes.
2. Mesmo evento de revisão repetido retorna o resultado anterior; mesma chave com outra nota retorna conflito; contador SM-2 muda uma vez.
3. Duas notas com revisões conflitantes têm resultado determinístico; ordem de locks não produz deadlock recorrente.
4. Duas versões de escrita concorrentes não sobrescrevem texto nem colidem silenciosamente em `MAX+1`.
5. Duas conclusões de etapas compatíveis são preservadas; operação incompatível responde conflito.
6. Pico controlado de hashes não bloqueia `/live` ou leituras simples; os limites são medidos em ambiente isolado, não contra contas reais.
7. Perfis públicos recusam configuração insegura; desenvolvimento em loopback permanece utilizável sem hacks na segurança.

### Contratos e migração

Escolher convenção única para `idempotency_key`, fingerprint do pedido, `revision/If-Match`, códigos 409/412 e tempo de retenção da idempotência. Aplicar expand/contract quando cliente antigo não envia revisão. Não aceitar ausência indefinidamente sem um plano de retirada.

Fora do escopo: adoção obrigatória de OAuth/MFA externo. Recuperação de senha e gestão de sessões devem ter decisão de produto/provedor antes de ampliar escopo.

## Sprint 39 Tempo de estudo áudio e assistência

Prioridade P1. Achados B06, B07, B08 e F07. Dependência: DB-39 e frontend de mídia/atividade.

### Incremento 39A — contrato e evidência (14/10/2026)

- `POST /api/me/activity/sessions`: UUID de sessão e aula publicada; resposta com
  âncora e hora atual do servidor, limite de 24 horas de offsets e replay de 7 dias.
  Repetir início não muda a âncora; resposta perdida não força uso do relógio civil local.
- `POST /api/me/activity/events`: UUID por operação, offset monotônico final e duração
  de 1–30.000 ms. Rejeita intervalo anterior à âncora/futuro além de 2 s, sessão
  alheia, chave reutilizada com outro conteúdo e evento novo após expiração.
- Lock por usuário serializa recibo e subtração de intervalos sobrepostos, inclusive
  entre cursos. Primeiro intervalo aceito recebe crédito; posteriores recebem somente
  os trechos livres. Retry retorna recibo original, sem duplicar contagem.
- `/api/me/today`: recorta intervalos na semana atual (segunda 00:00 no fuso IANA do
  plano), no instante atual e no curso publicado. `legacy_minutes` conserva estimativa
  antiga à parte; mudar etapa não transforma espera/abandono em tempo ativo.
- Mídia usa CAS obrigatório em PUT/DELETE, UUID, `changed_at` e revisão. Conclusão
  conserva tombstone. Só a última operação possui recibo na linha; replay de operação
  superada retorna conflito, nunca restaura posição antiga. Cliente antigo sem contrato
  recebe 422: API e frontend precisam ser atualizados juntos antes de uso no estudo.
- Exportação JSON passa a 1.6 e inclui sessões/eventos/intervalos da própria conta,
  fuso e metadados de retomada. Isso não fecha o inventário completo previsto na Sprint 40.

802 testes backend aprovados, incluindo concorrência real em PostgreSQL, sessão alheia,
60 minutos legados + 2 ativos = 2 na semana, corte na segunda-feira de São Paulo,
replay/expiração, tombstone e migração transacional. Ruff/mypy/OpenAPI e Alembic check
aprovados. API exercitada também sob papel runtime no laboratório (36 recusas de
privilégio). Após autorização separada, desenvolvimento 5180/8010 alinhado ao head
`e17b5fad0264`: backup real restaurado e ensaiado, 39 tabelas/6.766 registros históricos
preservados, 23 verificações HTTP aprovadas e conta de teste removida. 5181 permanece
intacto na Sprint 38. [Registro operacional](operacao_sprint_37.md#sprint-39a--alinhamento-autorizado-do-desenvolvimento-em-14102026).
Orçamento frontend e os 112 cenários Playwright do build otimizado aprovados.
O incremento de upload 39B e as pendências de cotas, reconciliação e jobs estão abaixo.

### Incremento 39B — recepção limitada e retry de upload (14/10/2026)

- `GET /api/speaking/policy` público e `no-store` expõe teto efetivo (padrão
  **2.000.000 bytes**, configurável apenas para baixo), 30.000 ms declarados,
  whitelist MIME e timeout de recepção da API de 30 s. `content_validation` informa
  `declared_mime_only`: ainda não existe validação do codec/duração decodificados.
- `read_audio` consome `Request.stream()` e verifica o acumulado **antes** de copiar
  cada bloco; não usa `request.body()`. Recusa excedente mesmo sem Content-Length
  ou com valor menor que o recebido. Cabeçalho inválido/divergente, corpo vazio,
  desconexão e timeout têm resposta explícita. Há buffer limitado; não é streaming
  de tamanho ilimitado para disco nem limite global de memória/conexões simultâneas.
- O Nginx usa `client_max_body_size 2000000` e timeout de 30 s **entre leituras**.
  A API limita o **total** de tempo de recepção; não são temporizadores equivalentes.
  O proxy pode responder 413 antes da API, inclusive HTML; cliente usa o status.
- A propriedade da tentativa é validada antes de ler o corpo. A transação somente
  de leitura é encerrada, devolvendo a conexão ao pool durante o recebimento.
  Depois, `FOR UPDATE` e refresh do estado serializam PUT/DELETE da mesma tentativa.
- Mesmo ID + MIME normalizado + mesmos bytes: 200 sem novo arquivo/evidência.
  Mesmo ID com outro conteúdo: 409 sem sobrescrever. Hash é comparado em blocos ao
  arquivo existente, não armazenado em coluna nova. Arquivo temporário privado
  (0600) é renomeado antes de confirmar `ready`, evidência e revisão na transação SQL.
- Se o commit falhar com resultado incerto, rollback/consulta verificam referência
  antes de apagar o arquivo recém-criado. Se não for possível verificar, ele é
  preservado para reconciliação futura. Não há atomicidade distribuída entre SQL e
  filesystem: crash/cancelamento ainda podem deixar órfão; nenhum purge foi adicionado.

**820 testes backend aprovados**, incluindo concorrência real, DELETE durante recepção,
pool liberado durante stream, arquivo alheio sem leitura do corpo, resultado de commit
perdido antes/depois da confirmação e retry sem evidência duplicada. Ruff/mypy aprovados;
OpenAPI e tipos frontend regenerados deterministicamente. Seis novos E2E passaram pelo
Nginx isolado; WAV sintético no limite verifica transporte, não inspeção de codec.
Regressão completa: **118 E2E aprovados**; os seis cenários específicos passaram
novamente após o último ajuste de frontend. Laboratório encerrado preservando volumes.

Sem migration nova, sem rollout em 5181 e sem commit/push/merge. O POST de criação não
ganhou chave idempotente; resposta perdida antes de conhecer o ID ainda pode deixar uma
tentativa pendente. Próximo bloco: inspeção real de mídia com limites de recursos e
reconciliação dry-run, antes de declarar o aceite completo de arquivos.
Referência do proxy: [limite de corpo do Nginx](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size).

### Incremento 39C — inspeção e reconciliação observacional (14/10/2026)

`audio_inspection.py` executa `audio_probe_worker.py` com Python `-I`, ambiente mínimo
sem credenciais e PyAV **19.0.1** fixado no lockfile. Dois filhos simultâneos por API,
prazo de 8 s, CPU de 5 s, uma thread de codec, 32 descritores e saída limitada a
4 KiB; Linux limita espaço virtual a 512 MiB, macOS não recebe essa garantia.
Cancelamento/timeout/overflow matam, drenam e recolhem o filho, sem ocupar o pool SQL.
Entrada é somente bytes já limitados; allowlists de demuxer/codec, protocolo restrito
e callback que nega aberturas externas impedem usar URLs/arquivos referenciados pelo
container. Não é sandbox de segurança do SO nem atestado contra vulnerabilidade nativa.

Aceita uma faixa de áudio mono/estéreo, 8–48 kHz. Famílias/codec permitidos estão em
`audio_probe_worker.py`; o [README](../README.md#sprint-39c--inspeção-real-de-áudio-e-inventário-somente-leitura-14102026)
registra o contrato e seus limites. Mede amostras e extensão temporal dos frames;
recusa tipo falso/vídeo/múltiplas faixas e mais de 30 s reais, inclusive em arquivo
com poucos bytes. WAV RIFF truncado é recusado. Decodificação não é análise forense
de toda corrupção possível; containers tolerantes podem omitir um final incompleto.

A primeira transição `pending` → `ready` grava a duração medida em `duration_ms`.
Retry válido mantém o contrato 39B. Não reescreve gravação histórica nem a apresenta
como inspecionada; não há marcador de validação retroativo por registro.
`GET /speaking/policy` passa a `decoded_audio_v1` e fornece alvo local de 29 s.
422 preserva áudio no cliente; ocupação/timeout/falha operacional retornam 503.

`python -m app.audio_audit --dry-run` lê snapshot SQL read-only com statement timeout
e solta a conexão antes de inventariar o storage. Janela de segurança de 24 h,
mtime/ctime, temporários e links protegidos; hashes em blocos com limites explícitos.
Não existe apply/delete, movimentação ou alteração de status. Checksum do relatório
não é baseline histórico. Referência pode mudar após o snapshot: um relatório nunca
autoriza limpeza futura sem nova verificação. Detalhes de orçamento e estados em DB-39C.

Sem migration nova. API dev reconstruída para incluir a dependência; estudo 5181,
seus dados e papéis não foram alterados. Oito E2E de upload passaram na imagem Linux;
amostras são silêncio sintético e não homologam microfone real.

Regressão backend: **850 testes**, **93,62% de cobertura**, Ruff/mypy aprovados.
Cinco codecs também passaram no Linux com UID sem privilégios e sem escrita em disco.
Contrato OpenAPI/tipos regenerado sem divergência; 63 testes operacionais e 50 guardas
E2E aprovados. Inventário dev read-only: zero referências/arquivos, nenhuma alteração.
Regressão completa de integração: **120 E2E aprovados em 6,4 min** na stack isolada,
em desktop e mobile simulados.

### Incremento 39D — persistência e quarentena retomável (14/10/2026)

`AudioStorage.save` executa flush/fsync dos bytes e fsync do diretório após publicar
o nome, antes do commit SQL. Falha de sincronização não retorna sucesso; um arquivo
publicado sem referência continua candidato protegido para reconciliação posterior.

Operador `app.audio_quarantine`, separado da API/worker, processa **uma chave explícita**:
confirma banco/storage, exige checksum e operação previamente escolhida, obtém lock
SQL `EXCLUSIVE NOWAIT` e verifica referência atual antes de agir. Conflita com o
`FOR UPDATE` do upload/exclusão. Não escreve SQL nem muda `pending` para `ready`.
Um flock local impede operadores concorrentes; limites de tamanho, idade, orçamento
cooperativo, permissões e symlinks são verificados novamente, não herdados do dry-run.

Journal durável precede link exclusivo → fsync → remoção do nome anterior → fsync.
`resume` verifica bytes/identidade e retoma movimento interrompido; `restore` grava
intenção durável e devolve os mesmos bytes sem sobrescrever outro arquivo. Uma
referência surgida depois da seleção bloqueia quarantine/resume; restauração explícita
não publica nem repara registros. Sem expurgo, cron ou timeout rígido para disco travado.

Testes interrompem processos reais após journal, link e retirada do nome original,
tanto na quarentena quanto na restauração. Casos ambíguos/corrupção/manifesto parcial
permanecem protegidos para revisão, não são "corrigidos" descartando dados. Os seis
pontos de interrupção também foram exercitados em Linux sem rede e UID não privilegiado.
Backup v2 conserva journals/bytes; v1 segue aceito. Não foi homologado restore do
journal como identidade operacional de um volume novo nem queda física de energia.

Sem migration, mudança de papéis ou rollout em 5181. Ver [runbook 39D](operacao_sprint_37.md#sprint-39d--quarentena-reversível-e-backup-v2-em-14102026).

### Incremento 39E — opt-in de conteúdo público para o PWA (14/10/2026)

O middleware passa a distinguir exclusivamente GET 200 JSON de uma lista fechada:
catálogo, currículo, aula, exercícios editoriais e vocabulário públicos. Essas
respostas recebem `Cache-Control: public, max-age=0, must-revalidate` e
`X-Aulas-Offline: public-text-v1`. Elas já eram anônimas; não foi removida autenticação
de endpoint privado nem publicado gabarito adicional.

Demais respostas `/api/`, incluindo conta, progresso, sessão de estudo, voz,
mutações e erros, continuam `private, no-store`. Testes com e sem Authorization
confirmam que os endpoints permitidos não personalizam o payload. O worker exige
também marcador, tipo e política corretos antes de gravar; não basta parecer JSON.

Sem nova migration, seed do ambiente de estudo ou alteração de contrato JSON/OpenAPI.
PostgreSQL descartável usado para regressão; detalhes e contagens em
[runbook 39E](operacao_sprint_37.md#sprint-39e--pwa-e-cache-público-em-14102026).
Reservas/cotas concorrentes de assistência, estados de jobs, retenção e rollout de
BE-39 permanecem abertos; este incremento não encerra a sprint.

Validação final: **893 testes backend / 93,69% de cobertura**, Ruff/mypy aprovados;
**72 testes operacionais**, **33 testes puros Linux** e **8 E2E de upload** em 19,9 s.
Laboratório E2E encerrado com volumes preservados. Sem commit/push/merge.

### Entregas

- [x] Substituir métrica semanal derivada do total histórico por soma de eventos/intervalos ativos dentro de uma janela temporal (39A local).
- [x] Definir fuso do plano semanal e regra de início da semana; tratar tempo do cliente como entrada limitada, não como autoridade absoluta (39A local).
- [x] Deduplicar eventos e impedir contagem duplicada em duas abas. Detectar ociosidade/visibilidade com contrato simples e minimização de telemetria (39A local).
- [x] Harmonizar limite de voz na API, proxy e contrato; implementar leitura limitada sem acumular corpo arbitrário em memória (39B).
- [x] Verificar formato/duração reais com limites, upload atômico/idempotente e recuperação de referência ausente por cópia conferida, preservando identidade; 39G/H adiciona checksum durável e restauração sem journal. Homologação física é aceite separado.
- [x] Implementar reconciliação com dry-run, período de segurança e quarentena reversível; lote de pending vazio com mais de 7 dias implementado, mas ativação automática depende de aprovação da política. Sem expurgo automático de arquivos.
- [x] Reservar cota assistida atomicamente antes da chamada externa; consumo não desaparece ao apagar resultado (39F, incluída no rollout 39G/H).
- [x] Definir reembolso de reserva por erro/timeout e semântica de custo em retries; preservar chave de provedor quando suportada (39F, unidade local não é garantia de cobrança externa única).
- [x] Não manter conexão/transação SQL aberta enquanto aguarda Ollama/gateway (39F; testes verificam o pool durante o provedor simulado).
- [x] Expirar transcrições em lotes independentemente do acesso; filtrar reivindicação/leitura/exportação e preservar ledger consumido.
- [x] Retomar worker após falha temporária do banco com backoff; heartbeat persistido e estado/idade da fila da própria conta.

### Critérios de aceite

1. Uma aula com 60 minutos antigos e dois novos informa dois minutos na semana corrente, não 62; dados legados não são retrodistribuídos sem evidência.
2. Retry, relógio deslocado e duas abas não duplicam tempo; retorno após um dia não registra automaticamente 30 minutos ativos.
3. Arquivos nos limites acordados têm mesmo comportamento no acesso direto e via Nginx, incluindo requisição sem Content-Length.
4. Duas tentativas de upload simultâneas não deixam arquivos órfãos ou duplicam evidência de competência.
5. Cota cinco suporta no máximo cinco reservas cobradas conforme política, mesmo com seis pedidos concorrentes ou exclusão de transcrição.
6. Job expirado não chama provedor. Limpeza não depende de o estudante voltar ao sistema.
7. Reiniciar worker recupera jobs válidos sem permitir que worker antigo sobrescreva resultado; testes preservam as proteções já existentes.

Fora do escopo: cobrança financeira ao usuário, avaliação automática de pronúncia como nota oficial e hospedagem pública do Ollama.

### Incremento 39F — admissão atômica de assistência (14/10/2026)

- Cota compartilhada por conta/dia UTC, contada pelo dia da reserva. `FOR UPDATE`
  na conta serializa novas admissões; locks nas reservas do dia aguardam despachos
  ainda sem commit, inclusive quando a reserva vence durante essa transação.
- Antes de iniciar o processamento, a reserva é convertida em consumo e confirmada.
  A conexão volta ao pool antes de aguardar o provedor. Cancelamento antes desse
  marco libera a unidade; timeout/falha/crash posterior não prova ausência de
  processamento e não devolve a unidade automaticamente.
- Escrita aceita `operation_key` UUID opcional. Mesmo conteúdo/chave devolve o
  feedback já salvo, sem duplicar evidência. Em processamento/resultado ausente:
  409, sem chamada adicional. Chave com conteúdo/rubrica diferente: 409.
  Clientes antigos sem chave continuam aceitos, mas não têm deduplicação de retry.
- Transcrição serializa criação por conta/tentativa. Retry do worker mantém a
  reserva e `Idempotency-Key`; excluir job/voz depois do despacho não reabre cota.
  Resposta após excluir job pode registrar custo no ledger, nunca recria o texto.
- Sem áudio ou reserva válida não há despacho. Job vencido é barrado antes do
  provedor; exclusão em lotes, filtro de reivindicação e proteção do worker contra
  indisponibilidade do banco ainda pertencem ao próximo incremento.
- Status distingue reservado/consumido, próxima renovação e custo parcial. Campo
  de custo ausente/inválido no gateway não é tratado como gratuidade. Ollama local
  informa taxa do provedor zero, sem contabilizar hardware/energia. Nenhum provedor
  externo foi habilitado ou chamado nos ensaios.

Migration `f28c6abe1375`, contrato OpenAPI e consumidor tipado atualizados juntos.
Não habilitar código novo sobre schema anterior nem manter worker antigo admitindo
jobs sem reserva. Backfill não recupera consumo de resultados já apagados.
[Política, ensaios e limites operacionais 39F](operacao_sprint_37.md#sprint-39f--reservas-e-cotas-assistidas-em-14102026).
**Estado histórico ao concluir 39F:** próximo bloco era 39G, jobs/retenção, além do
rollout de estudo, checksum durável e homologações reais restantes. O alinhamento
do DEV foi concluído em 15/10: API/worker recriados juntos, configuração existente
preservada e 11 verificações HTTP autenticadas aprovadas, sem chamar provedores.
[Registro operacional](operacao_sprint_37.md#sprint-39f--alinhamento-do-desenvolvimento-em-15102026).

### Incremento 39G/H — execução técnica e limites de aceite (15/10/2026)

Entregues lotes SQL limitados/canceláveis, função restrita ao worker, filtros de TTL,
retry de indisponibilidade do banco, heartbeat e estado privado de fila. SHA-256
persistido em upload, leitura limitada com verificação, estados de integridade e
CLI de baseline/recuperação explícitos. Legado não ganha hash fictício e arquivo
existente não é sobrescrito. Backup, clone, smoke e aplicação sem seed em DEV/estudo.

**955 testes backend / 93,27%**, **338 frontend**, **126 E2E**, **2 PWA**, **88 ops**;
43 recusas de privilégio. O mesmo worker recuperou-se da queda real do PostgreSQL
do laboratório em 3,26 s após reinício, sem provedor. Primeiro E2E teve timeout
transitório registrado; repetição tripla e segunda suíte completa passaram.

A limpeza automática de refresh/pending antigos fica desligada, com rotinas
prontas e dry-run disponível, até decidir política. Homologação física Safari/iOS
continua pendente; não declarar aceite integral. [Procedimentos e evidências](operacao_sprint_37.md#sprint-39gh--retenção-integridade-e-implantação-em-15102026).

## Sprint 40 Histórico editorial e dados pessoais

Prioridade P1/P2. Achados B09, B11 e D04. Dependências: DB-40 antes de migrações de conteúdo; FE-40 para visualização.

### Entregas

- [x] Criar inventário de dados pessoais e corrigir exportação para incluir checkpoints, sessões/itens de prática, feedbacks sem draft e metadados/versionamento (40A; versões já persistidas, sem inventar snapshots legados).
- [x] Versionar o formato de exportação e garantir snapshot coerente (40A); teto síncrono explícito, jobs/streaming condicionados a ensaio de volume futuro.
- [x] Disponibilizar exportação autorizada de binários ou manifesto com downloads protegidos, distinguindo isso do JSON de metadados (40A).
- [x] Aplicar controle de acesso e expiração das transcrições (40A); não há artefato retido no servidor nem link público temporário.
- [x] Definir procedimento de exclusão de conta/recursos, arquivos e tarefas associadas, com autenticação reforçada, confirmação e prazo operacional (40C).
- [x] Adotar snapshot suficiente para interpretar novas tentativas e resultados sem reler gabarito/cue mutável; ausência legada permanece explícita (40B.2d; sem backfill e sem rollout DEV/estudo).
- [x] Implementar captura imutável e leitura privada de novas evidências nas cinco modalidades, ensaiadas com captura opt-in (40B.2a; sem ativação nos ambientes de uso).
- [x] Acrescentar prévia/diff ao seed e rejeitar remoção destrutiva de conteúdo referenciado sem plano explícito (40B.1; bloqueio conservador inclusive sem referências, sem arquivamento ainda).
- [x] Centralizar política de publicação/arquivamento em rotas por slug e por ID, preservando histórico permitido (40B.2b/40D).
- [x] Unificar disponibilidade nas rotas curriculares por slug/ID e preservar leitura pessoal; acrescentar prévia agregada de arquivamento por unidade (40B.2b.1; sem aplicar arquivamento).
- [x] Separar identidade editorial de posição para exercício, prompt, cue, mídia, vocabulário e questão de checkpoint; exigir chave explícita no seed e registrá-la nos novos snapshots quando disponível (40B.2b.2; ensaio isolado, sem rollout).
- [x] Implementar aplicação local de arquivamento por unidade com recibo imutável, confirmação, prévia revalidada, retry e serialização das admissões; integrar impacto ao diff de pedidos explícitos (40B.2b.3; prod/public bloqueados e rollout pendente).
- [x] Corrigir proveniência editorial: datas e versões vêm da revisão correspondente, não de constante global de 7 de outubro (40B.2c; homologação humana continua pendente).

### Critérios de aceite

1. Conta sintética com todas as modalidades exporta todas as entidades previstas no inventário; feedback sem rascunho não desaparece.
2. Exportar conta A não inclui dados nem arquivos de B. Links de áudio continuam autenticados e não são publicados no cache.
3. Resultado de exercício antigo continua coerente após alteração de enunciado/gabarito; versão anterior permanece interpretável.
4. Seed que remove prompt com draft/cue com voz/exercício com prática exige arquivamento ou plano aprovado, não cascade silencioso.
5. Unidade arquivada tem comportamento consistente nas rotas diretas, laboratório, revisão e histórico, segundo contrato.
6. Exclusão de dados possui retry seguro e tratamento de falha parcial entre banco e filesystem; nenhum dado real é apagado nos testes.

Fora do escopo: prometer conformidade legal automática, redefinir certificado interno ou reprocessar histórico pedagógico em massa.

### Incremento 40A — exportação 2.0, 15/10/2026

`GET /api/me/export` mantém nome do arquivo, rota e seções anteriores; adiciona
IDs correlacionáveis, inventário, checkpoints, prática/itens, feedback independente
de draft, recibos de revisão inclusive com item removido, cartões legados,
metadados de sessões de acesso e consumo/reservas de assistência. Não exporta
credenciais, chaves de fornecedor, caminhos físicos ou bytes de áudio.

Serviço `personal_export.py`: autenticação anterior é encerrada sem escrita;
perfil e entidades são relidos na mesma transação `REPEATABLE READ, READ ONLY`,
uma conexão, timestamp único para corte/expiração. Conta removida antes do snapshot
é recusada. Limites de 10 mil registros, 20 MiB e 20 s (10 s por statement), sem
arquivo parcial em erro. Campos pessoais são listados explicitamente; teste de
inventário exige revisão se surgir uma nova tabela com `user_id`.

Metadados históricos preservam os resultados gravados, rubrica/snapshot existentes,
versão/fingerprint da prática e versão do checkpoint. Referências editoriais atuais
não são declaradas históricas; enunciado original indisponível é indicado.
Arquivamento/seed/versionamento imutável e exclusão com retries **continuam pendentes**.
Estratégia de grandes volumes: a exportação atual falha de forma explícita acima
do teto; não existe exportação assíncrona implantada nem promessa de capacidade
em produção derivada destes testes. Ensaio e evolução ficam para BE-41 se necessário.

Sequência registrada: **40B** editorial/seed, **40C** exclusão/backups, **40D** histórico
e fechamento integrado. [Inventário e evidências](operacao_sprint_37.md#sprint-40a--exportação-e-meus-dados-em-15102026).

### Incremento 40B.1 — barreira do seed, 15/10/2026

CLI `seed --dry-run` e `make seed-plan`: snapshot `REPEATABLE READ, READ ONLY`,
diff por identidade editorial, campos alterados, hashes, contagens e bloqueios.
Não consulta dados pessoais, não calcula quantos alunos seriam afetados e não
declara conteúdo arquivado. Lista limitada a 500 diferenças, mantendo contagens
completas e sinalização de truncamento. Não executa escrita seguida de rollback
para simular a prévia, portanto não avança sequências.

O caminho destrutivo anterior foi removido. Aplicação **insert-only**: qualquer
alteração/omissão de registro existente ou acréscimo dentro de aula/checkpoint
existente é recusado, mesmo com versão incrementada e mesmo sem referências de
alunos. Um pacote idêntico não executa DML. Curso/unidade/aula novos só entram se
o pacote completo não alterar o conteúdo existente. Não há `--force`.

Aplicação relê o catálogo sob locks editoriais `SHARE ROW EXCLUSIVE NOWAIT` em
ordem fixa, exige `READ COMMITTED`, recusa ORM pendente e faz rollback integral
em erro/cancelamento. O relatório anterior não serve como autorização de escrita
posterior. Argumentos CLI desconhecidos falham antes de abrir o banco. Mudança
de privilégios não foi necessária nem executada; aplicação precisa do papel
editorial/migrador autorizado, não de novas permissões concedidas à API.

Prévia DEV encontrou **82 rubricas diferentes + 3 versões antigas mantidas**,
com 6.681 registros iguais. Recusou a carga pelas rubricas; nenhum dado DEV foi atualizado.
O diff compara a representação persistida; não conclui sozinho se cada diferença
de rubrica é semântica ou apenas de formato/defaults. Versões inferiores à versão
solicitada são mantidas literalmente, sem bloquear uma reaplicação idêntica;
downgrade e modificação do registro de versão existente continuam proibidos.
Não usar esse resultado para apagar versões ou reaplicar rubricas automaticamente.

**40B continua em andamento:** 40B.2 deve substituir a barreira conservadora por
identidade estável, snapshots, arquivamento e proveniência real, com migração
ensaiada; tratar o drift DEV sem reconstruir histórico a partir do gabarito atual.
O comando direcionado `writing-rubrics` é anterior a esta entrega e não faz parte
da proteção do seed; não foi executado. [Evidências e operação](operacao_sprint_37.md#sprint-40b1--prévia-e-barreira-editorial-do-seed-em-15102026).

### Incremento 40B.2a — snapshots privados de novas evidências, 15/10/2026

Implementados snapshots 1.0 para nova tentativa de exercício, item de prática,
feedback de escrita, tentativa de fala e checkpoint. Captura os objetos usados
na operação, antes do commit do evento, sem buscar o seed para reconstruir o
passado. Escrita utiliza a rubrica efetivamente avaliada, inclusive se houve uma
chamada assistida entre leitura e resultado. Falha do snapshot impede o commit
do evento; reservas/custos de assistência previamente admitidos continuam seguindo
seu ledger próprio, não são desfeitos como se o provedor não tivesse sido chamado.

`GET /api/me/history/{kind}/{evidence_id}/content` verifica propriedade e devolve
snapshot ou ausência explícita; tipos `exercise/practice/writing/speaking/checkpoint`.
Resposta `private, no-store`, 404 entre contas, sem recurso público de gabarito.
Item de prática pendente oculta gabarito/dicas/explicação e hash; exportação explícita
da conta inclui o snapshot completo. Retry de exercício com snapshot devolve o
feedback capturado; registros legados não recebem backfill durante retry.

Exportação 2.0 recebeu seção aditiva `content_snapshots`, inventário e referência
de snapshot nas tentativas; o schema interno do snapshot é 1.0. OpenAPI e tipos
TypeScript foram regenerados. Não há nova tela histórica neste incremento.

**Entrega ensaiada, não ativada no DEV/estudo:** captura depende de
`EDITORIAL_SNAPSHOTS_ENABLED=true`, padrão false, após migration
`b40e8cd13597` e permissões. Ativar sem tabela responde 503 e não conclui o evento.
Desligar a captura não oculta snapshots que já existam na leitura/exportação.

**40B.2 ainda parcial:** falta identidade editorial independente de posição,
arquivamento/publicação centralizados, proveniência por revisão, integração das
demais projeções históricas/UI e do consumo posterior de cues pelo STT, além do
rollout com backup/restore ensaiado. Não habilita edição destrutiva: a barreira
40B.1 continua integralmente ativa. [Evidências](operacao_sprint_37.md#sprint-40b2a--snapshots-privados-de-evidências-em-15102026).

### Incremento 40B.2b.1 — disponibilidade e prévia de arquivamento, 15/10/2026

Durante a preparação de identidade/arquivamento foi encontrada uma inconsistência:
listas filtravam publicação, mas IDs de exercício, prompt, mídia, cue e vocabulário
permitiam novas operações sem conferir o estado dos pais. Corrigido com a política
compartilhada `publication.py`: curso **e** unidade publicados para novas atividades.
Rotas legadas e por curso seguem a mesma regra. Curso/unidade arquivados saem do
catálogo; curso planejado preserva prévia sem aulas/checkpoints ou contagem publicada.

Leitura do próprio rascunho/posição existente, prática por ID, gravações, snapshots,
exportação, cartões pessoais já copiados e cancelamento de gravação são preservados.
Limpar posição existente mantém CAS/tombstone. Novos feedbacks, gravações, respostas,
dicas/revelações e mutações da prática ficam bloqueados. Nova transcrição é recusada
antes da reserva de cota; job já admitido mantém seu tratamento anterior. Isso não
resolve ainda a integração de snapshots ao worker/STT nem versões em todas as telas.

`python -m app.cli editorial-plan --course voa-level-1 --unit 31-40` gera prévia
somente leitura: contagens editoriais/pessoais, práticas ativas e checkpoints de
outras unidades que referenciam essas aulas. Não existe `--apply`/`--force`; não há
rota administrativa pública. O hash identifica o relatório agregado, não o conteúdo
editorial nem autorização de execução. A barreira insert-only do seed permanece.

**40B.2 continua parcial:** identidade editorial estável/mapeamento do seed,
proveniência por revisão, aplicação auditada/serializada de arquivamento,
invalidação do cache público, interfaces históricas e rollout ainda faltam.
Sem migration, alteração de status no DEV/estudo, ativação de snapshots ou merge.
[Contrato e evidências](operacao_sprint_37.md#sprint-40b2b1--disponibilidade-e-prévia-de-arquivamento-em-15102026).

### Incremento 40B.2b.2 — identidade editorial estável, 15/10/2026

Seis tipos referenciáveis passam a usar `editorial_key` UUID explícito no seed e
imutável no banco. IDs numéricos/FKs permanecem; posição/termo são atributos, não
identidade. O bootstrap da baseline adicionou **2.194 chaves** sem modificar valores
pedagógicos. Não é versão de conteúdo nem reconstrução do passado.

O diff 1.1 reconhece a mesma entidade após mudança de posição, inclusive preservando
as referências normalizadas de respostas/dicas/cues. **Continua bloqueando** qualquer
alteração/omissão ou extensão de conteúdo existente: não libera reordenação ou
arquivamento. Seed novo/clone precisa de nova chave; chave ausente, inválida ou
duplicada é recusada antes de escrita. Reaplicação idêntica preserva IDs/datas/sequências.

Snapshots novos recebem metadados opcionais `editorial_identity_contract=explicit_uuid_v1`
e chaves dos objetos envolvidos, sem alterar o envelope 1.0. Snapshots anteriores
permanecem intactos; schema apenas b40 continua capturando sem esses metadados.
As chaves não substituem o texto/gabarito/rubrica capturados e não certificam revisão.

Leituras ORM comuns continuam compatíveis com DEV não migrado. A prévia identifica
`legacy_projection` e bloqueia a aplicação até c51; não apresenta UUID projetado
como identidade já persistida. DEV continua com 82 diferenças de rubrica bloqueadas.
**1.066 testes backend**, 94% de cobertura; contrato OpenAPI inalterado.

Próximo passo: aplicação auditada/serializada de arquivamento e integração do impacto
ao seed, seguidas de proveniência, rubricas, histórico/STT, cache e rollout.
Sprint 40 continua parcial. [Contrato e evidências](operacao_sprint_37.md#sprint-40b2b2--identidade-editorial-estável-em-15102026).

### Incremento 40B.2b.3 — arquivamento auditado local, 15/10/2026

`editorial-archive` implementa somente a transição de uma unidade publicada para
arquivada, pelo owner/migrador. Exige flag opt-in, `--apply`, banco confirmado,
operador, motivo enumerado, UUIDv4 da operação e `catalog_sha256` da prévia atual.
Flag desligada por padrão; ambientes `prod` e perfil `public` são recusados mesmo
com flag ligada. Não há endpoint administrativo HTTP ou autorização via token de aluno.

Admissões curriculares tomam advisory lock compartilhado transacional antes da
checagem de publicação; seed/arquivamento tomam exclusivo. Concorrência é recusada
imediatamente (503 para admissão, bloqueio operacional para apply), sem esperar
por locks pessoais. Arquivamento também congela as tabelas editoriais com NOWAIT,
revalida hash/status/dependências e grava status + recibo na mesma transação.
Processos antigos sem esse protocolo não estão cobertos; rollout requer alinhamento.

Nova tabela append-only registra operador declarado, identidades SQL reais, alvo,
motivo, digest e impacto agregado. Repetir a mesma operação devolve o recibo;
reutilizar chave com outro pedido é recusado. Nenhum texto pessoal, resultado ou
arquivo é modificado. Operações assistidas já admitidas antes do commit podem
terminar; não são novas admissões nem são canceladas retroativamente.

Prévia 1.1 mantém `report_sha256` diagnóstico e acrescenta `catalog_sha256`, sem
dados pessoais nesse digest. Checkpoints externos dependentes bloqueiam o apply.
Pedidos explícitos de `status=archived` no seed recebem impacto na prévia (até cinco),
mas seguem bloqueados para aplicação pelo seed; omissões nunca viram exclusões.

**1.082 testes backend**, 94% de cobertura; ensaio com papéis reais aprovado.
Ainda faltam proveniência/rubricas, histórico/STT, interfaces/cache, regra de
conclusão e implantação. [Contrato e evidências](operacao_sprint_37.md#sprint-40b2b3--arquivamento-auditado-local-em-15102026).

### Incremento 40B.2c — rubricas e proveniência auditáveis, 15/10/2026

Novo `editorial-audit` compara as 82 propostas num snapshot read-only e separa
representação, apresentação e efeito real no avaliador. No DEV foram encontradas
18 diferenças de representação, 1 visual e **63 semânticas**. O relatório expõe
somente localizadores, contagens e hashes; não lê dados pessoais e nunca oferece
apply. O atalho anterior `writing-rubrics` foi desativado antes de abrir sessão.

O seed deixou de fabricar revisão/publicação em 07/10 e agora valida acesso,
status, nota e timestamps com fuso/ordem coerente. `reviewed_at` é anulável para
representar data desconhecida; o contrato OpenAPI/tipos foi atualizado. Sete
notas ausentes passaram a declarar registro legado e homologação pendente, sem
afirmar revisão humana.

Migration e73 corrige somente o default legado, preserva datas reais e recusa
downgrade que inventaria informação. Ensaiada apenas na base descartável; DEV e
estudo permaneceram sem migration ou escrita. **1.088 testes backend**, 94% de
cobertura; 347 frontend e 88 operacionais aprovados. As 63 mudanças dependem de
nova versão/snapshots e homologação antes de rollout.
[Runbook e resultado DEV](operacao_sprint_37.md#sprint-40b2c--auditoria-de-rubricas-e-proveniência-15102026).

### Incremento 40B.2d — projeções históricas e STT imutável, 15/10/2026

As respostas de prática, escrita e fala agora informam
`historical_content_status`. Itens da prática expõem seu ID de evidência; o
histórico de escrita marca cada feedback; fala devolve o texto capturado no
snapshot e nunca substitui ausência legada pela cue atual. O frontend mostra
essa ausência no histórico oral e não oferece nova comparação automática.

Nova transcrição exige snapshot da tentativa antes de reservar cota. O worker
calcula semelhança usando somente a cue capturada, mesmo que a legenda editorial
mude entre fila e processamento. Job legado sem captura falha com
`historical_content_unavailable` antes do provedor e libera reserva ainda não
consumida. Jobs existentes continuam legíveis, com `expected_text=null` quando
o passado não pode ser provado.

O worker não ganhou `SELECT` em `evidence_content_snapshot`. Migration f84 cria
uma função `SECURITY DEFINER` fixa, limitada por tentativa e proprietário, que
projeta apenas `text_en`; runtime e backup não podem executá-la e o worker segue
sem acesso aos snapshots de escrita, exercício, prática ou checkpoint.

Captura continua opt-in e desligada em DEV/estudo. Não houve backfill, chamada a
provedor, migration nesses ambientes ou mudança pedagógica. Sprint 40 permanece
parcial: interfaces completas de prática/checkpoint, cache/arquivados, exclusão
pessoal e rollout ainda faltam.

### Incremento 40B.2e — vínculos editoriais estáveis, 15/10/2026

Mídia → exercício e checkpoint → mídia deixaram de ser resolvidos pela posição.
O seed normaliza a coordenada legada congelada para o UUID editorial persistido;
pacotes novos podem declarar `listening_exercise_key` e `listening_media_key`.
Posição continua sendo somente ordem visual. Referência ausente, exercício de
outra aula ou mídia de outro curso/aula falha antes de qualquer escrita.

A API de checkpoint consulta os IDs canônicos. `LessonMediaOut` acrescenta
`listening_exercise_id`; `listening_exercise_position` permanece temporariamente
compatível e marcado como obsoleto. O caso curricular do checkpoint 40–44, que
retoma a Aula 40 do bloco anterior, continua válido porque pertence ao mesmo curso.

A migration `a06f2ce1487b`, após f84, faz backfill somente quando cada vínculo
legado resolve exatamente, cria FKs compostas de aula/curso e recusa catálogo
ambíguo. Downgrade funciona antes de reordenação e é recusado se as posições já
divergirem dos vínculos estáveis. Ensaios ocorreram apenas no PostgreSQL descartável;
DEV/estudo não receberam migration, seed ou reordenação.

Validação: **1.097 testes backend**, Ruff, mypy, Alembic sem drift, OpenAPI e
tipos gerados aprovados; 348 testes frontend e 88 operacionais também passaram.

Isso remove o bloqueio estrutural das referências, mas **não autoriza reordenar**:
o diff 40B ainda bloqueia mudanças em conteúdo existente até concluir regras de
versão/publicação, impacto e interfaces históricas.

### Incremento 40B.2f — contrato read-only de reordenação, 15/10/2026

O novo `editorial-reorder-plan` compara um pacote completo com o catálogo em
`REPEATABLE READ, READ ONLY`. Apenas seis entidades com UUID editorial estável
podem trocar posição: exercício, mídia, cue, vocabulário, proposta de escrita e
questão de checkpoint. O conjunto de irmãos precisa ser uma permutação; identidade,
pai e todos os campos semânticos permanecem iguais.

Cada aula afetada exige `lesson_version` nova, exatamente N+1, em estado revisado
ou publicado e com revisão datada. Checkpoint exige `content_version` N+1. Mudança
semântica misturada, inclusão/omissão, troca de pai, salto de versão e tabelas cuja
identidade ainda depende da posição são bloqueadas com motivo estruturado.

O relatório 1.2 contém hashes antes/depois, digest do plano, transições, posições
e contagens agregadas de FKs pessoais diretas preservadas. Não lê nem devolve texto,
resposta, e-mail ou áudio do aluno. Não existe apply/force/delete; uma execução
idêntica sem reordenação também não é apresentada como plano válido.

Validação focal: **13 testes**, incluindo PostgreSQL descartável, provaram somente
SELECT/SET, sequências e catálogo intactos, sessão suja recusada e flags mutáveis
inexistentes. A regressão completa fechou com **1.110 testes backend**, Ruff e mypy.
O seed comum permanece insert-only. DEV/estudo e os JSONs reais não foram alterados.
Próximo passo: aplicação transacional auditada com revalidação sob lock e recibo
imutável; este incremento não autoriza reordenação em ambiente real.

### Incremento 40B.2g — apply transacional e auditado, 15/10/2026

`editorial-reorder` recebe o pacote completo e o `plan_sha256` produzido pela
prévia. Exige `--apply`, banco confirmado, UUIDv4 de operação, operador e motivo
enumerado. A feature flag fica desligada por padrão e o serviço recusa `prod/public`.
Não existe endpoint HTTP ou autorização por conta de aluno.

O apply usa READ COMMITTED, advisory lock editorial exclusivo e locks das 19 tabelas
com NOWAIT. Sob essas travas, refaz o plano. Trocas passam por posições temporárias
positivas e globalmente livres, evitando colisão imediata das constraints UNIQUE;
depois recebem a posição final. A nova `lesson_version` ou o `content_version` do
checkpoint é gravado na mesma transação e o catálogo final precisa corresponder ao
hash projetado antes do recibo.

O recibo append-only registra identidade SQL real, operador, motivo, hashes, UUIDs/
posições, versões e contagens agregadas de FKs pessoais — nunca respostas, textos,
e-mails ou áudio. Retry idêntico é leitura idempotente; chave reutilizada com outro
pedido é recusada. Falha do recibo, plano obsoleto ou lock ocupado desfaz toda DML.

Testes cobriram exercício e questões de checkpoint, preservação dos IDs/FKs pessoais,
concorrência com admissão de estudo, rollback injetado, imutabilidade e CLI sem apply
implícito. O laboratório confirmou migrador como executor, runtime/worker sem acesso
e backup somente leitura. A regressão terminou com **1.124 testes backend**, Ruff e
mypy; 88 testes operacionais e 80 subtestes também passaram. Nenhum pacote real foi
aplicado em DEV/estudo.

### Incrementos 40C/40D — exclusão retomável e histórico paginado, 16/10/2026

`DELETE /api/me/account` exige sessão, senha atual, UUID da operação e confirmação
exata. Argon2 roda sem conexão/lock; a transação depois serializa por usuário,
revalida existência e hash, captura apenas chaves opacas dos áudios e apaga o perfil.
As cascades revogam sessões e removem os dados pessoais. O recibo restante não tem
`user_id`, e-mail ou conteúdo. A resposta 202 sempre confirma que o banco já foi
excluído e distingue áudio concluído de limpeza pendente.

O worker processa `account_deletion_file` antes da transcrição, faz unlink
idempotente, usa `SKIP LOCKED`, backoff e no máximo dez tentativas. Falha final fica
visível apenas como contagem agregada no heartbeat. Runtime pode criar/atualizar o
recibo e a fila; worker só lê/atualiza e remove tarefas; nenhum deles ganha DELETE
do recibo. O downgrade recusa apagar tabelas com recibos.

`GET /api/me/history/page` lista snapshots privados com cursor estável
`(created_at,id)`, limite 1–100 e `private, no-store`. A página informa modalidade,
ID da evidência, captura e schema, sem retornar o JSON pesado. O conteúdo só é
buscado sob demanda na rota por evidência. Outra conta vê lista vazia e não consegue
abrir o registro. Schema ainda não instalado produz lista vazia, sem erro 500 nem
reconstrução a partir do conteúdo atual.

`CertificateEligibilityOut.rule_version=course-certificate-v1` torna explícita a
regra atualmente calculada. Não cria emissão, download ou reprocessamento histórico.

Ruff e mypy passaram; 39 testes dirigidos de API/migration passaram em PostgreSQL
descartável. O laboratório com papéis reais aprovou recusas, DML mínimo, API,
worker, snapshots, cotas/retenção e dump limitado. Evidência completa e rollout
permanecem no runbook; homologação pedagógica humana não foi declarada.

## Sprint 41 Performance e contratos paginados

Prioridade P2. Achados B10, F11 e D06.

### Entregas

- [x] Instrumentar contagem SQL e tamanho de payload nos principais endpoints, usando a amostra de 17 SQLs do detalhe apenas como ponto de investigação.
- [x] Separar projeção pública, detalhe editorial, histórico e comando de escrita; evitar carga automática de relações desnecessárias.
- [x] Remover consultas por checkpoint dentro do loop de recomendação quando a medição confirmar custo relevante.
- [x] Paginar escrita, speaking, notebook e revisão suspensa com cursor estável composto por data e ID, limites máximos e filtros consistentes.
- [x] Tornar resposta de autosave pequena; obter histórico de versões por chamada paginada separada.
- [x] Definir limites de exportação/processamento e streaming/jobs quando justificado pelo ensaio de volume.
- [x] Cooperar com DB-41 na análise dos planos de execução, sem prescrever índices indiscriminados.
- [x] Padronizar invalidadores/ETags de conteúdo público, preservando `no-store` privado.

### Critérios de aceite

1. Cenários com 1 mil e 10 mil itens sintéticos por histórico mantêm paginação estável, sem lacunas/duplicatas quando datas empatam.
2. Identidade de usuário e escopo de curso/unidade permanecem corretos em todas as páginas e cursores inválidos são recusados.
3. SQL count não cresce linearmente com itens de uma página por N+1; limites de consultas são documentados por rota.
4. Registrar p50/p95, payload e uso de pool num ambiente declarado. Metas sugeridas para negociação: p95 de leituras usuais abaixo de 500 ms em carga de ensaio e sem regressão superior a 20% sobre baseline estável.
5. Resultado funcional, idempotência, privacidade e acessibilidade não são sacrificados para atingir a meta de latência.
6. Não usar resultados locais de amostra única como promessa de produção nem exigir Redis sem comprovar necessidade.

Fora do escopo: fragmentar o monólito, particionar tudo ou reescrever SQLAlchemy.

### Incremento 41A — sonda agregada e primeira projeção, 15/10/2026

Foi criada uma sonda opt-in por request, desligada por padrão e recusada por
configuração em `prod/public`. Ela conta comandos SQL pelo evento do engine, bytes
de `Content-Length`, duração e checkouts do pool. Log e headers carregam somente
essas agregações, método, path e status: não guardam SQL, parâmetros, query string,
corpo de resposta ou identidade do aluno.

No banco descartável, a lista pública usou 1 SQL. O detalhe da aula confirmou que
a estimativa anterior estava baixa: eram 18, não 17. Dois carregamentos pertenciam
ao checkpoint da unidade e um buscava gabaritos que o contrato público oculta. A
projeção passou a recusar essas relações e adiar também as colunas privadas de
dica/explicação, reduzindo o mesmo detalhe para 15 SQLs e 1 checkout sem mudar o
payload de 14.435 bytes da Aula 31.

Cinco testes da sonda, 118 testes das rotas afetadas e a regressão completa com
1.129 testes backend passaram; Ruff e mypy também foram aprovados. A amostra de
cerca de 60 ms foi uma execução local isolada e não é p50/p95. Instrumentar as rotas
autenticadas, gerar massas 1k/10k e medir distribuições continuam pendentes; por
isso as duas primeiras entregas da Sprint 41 estão apenas parcialmente atendidas.

### Incremento 41B — recomendação sem N+1, 15/10/2026

A primeira medição autenticada confirmou 38 comandos SQL em `/api/me/today` para
uma conta nova. A recomendação carregava todos os checkpoints candidatos e fazia
uma contagem de aulas faltantes para cada um. Selecionar `Lesson` e entidades de
checkpoint completas também acionava relações `selectin` sem uso no painel.

A elegibilidade passou para um `NOT EXISTS` correlacionado que exige todas as aulas
necessárias estudadas e nenhuma tentativa na versão corrente, ordena os candidatos
e retorna somente o primeiro. Sessão recente, checkpoint e próxima aula retornam
somente as colunas do contrato. A consulta da sessão recente alimenta a recomendação;
uma segunda leitura pequena ocorre apenas quando a sessão mais recente está completa
e é preciso procurar uma retomada anterior incompleta.

O caso de conta nova ficou em 8 SQLs, 493 bytes e um checkout. Dezoito testes focais
preservaram prioridade de revisão, retomada, conclusão, checkpoints/versionamento,
tempo ativo e isolamento entre cursos; a regressão completa passou com 1.130 testes,
Ruff e mypy. Ainda faltam baselines com dados para caderno,
escrita, speaking e revisão, seguidas de paginação por cursor.

### Incremento 41C — primeira paginação keyset, 15/10/2026

O Caderno ganhou `GET /api/me/notebook/page`, sem remover imediatamente o contrato
legado. A rota aceita os mesmos filtros de curso, unidade, aula e tipo, limita a
página entre 1 e 100 itens e usa a chave total `(updated_at DESC, id DESC)`. O cursor
é base64url opaco, contém versão, data com fuso e id, tem tamanho máximo e validação
estrita; conteúdo malformado recebe 422 com `invalid_cursor`.

A consulta projeta apenas os campos do contrato e faz os joins de aula, unidade e
curso na mesma operação. Autenticação mais página ficaram em 2 comandos SQL e no
máximo um checkout, independentemente de 1, 2 ou 5 itens retornados no teste. Datas
empatadas foram percorridas em páginas 2/2/1 sem repetição ou lacuna; outra conta e
outro tipo permaneceram fora do resultado.

O OpenAPI e o consumidor TypeScript foram regenerados. A regressão passou com
1.137 testes backend, Ruff e mypy. Ainda não foram executadas as massas sintéticas
de 1 mil/10 mil itens, concorrência, p50/p95 ou os históricos de escrita, speaking e
revisão; portanto este incremento não encerra toda a Sprint 41.

### Incremento 41D — carga representativa e plano do Caderno, 15/10/2026

O comando `make notebook-benchmark` prepara exclusivamente o PostgreSQL marcado
como teste, adquire advisory lock e cria contas sintéticas isoladas com 1 mil e 10
mil notas. Ele percorre todas as páginas e compara a sequência recebida com a
ordem do banco. O conjunto de 10 mil completou 200 páginas de 50 itens em
1.437,17 ms, sem lacunas ou duplicatas; cada chamada preservou 2 comandos SQL,
payload conferido e no máximo um checkout.

Na página situada em 90% da massa de 10 mil, o plano sem índice consumiu 2,047 ms
e somou 706 blocos de cache. O candidato `(user_id, updated_at, id)` passou a ser
usado e reduziu o plano para 0,124 ms e 40 blocos, aproximadamente 93,9% e 94,3%
de redução. O custo observado foi +14,4% para inserir 10 mil linhas e 840 KiB de
índice em 21 mil linhas. O p95 da aplicação local variou e não melhorou em todas
as páginas; portanto a decisão se apoia no plano e na escala, sem converter a
amostra local em promessa de latência.

A fronteira da consulta usa comparação de tupla compatível com o índice. A
migration `c82f4a9d117e` cria o índice concorrentemente e recusa índice parcial,
inválido ou com definição diferente. O ciclo upgrade/downgrade/re-upgrade e o gate
de drift passaram no banco descartável. A regressão final teve 1.138 testes backend
e 91 testes operacionais aprovados. Escrita, speaking e revisão continuam como os
próximos históricos a medir/paginar na Sprint 41.

### Incremento 41E — contratos paginados de escrita, 15/10/2026

O contrato de rascunho/autosave passou a responder somente revisão, prompt, texto
atual e data. Versões deixaram de ser um relacionamento aninhado nessa resposta e
são lidas em `GET /api/writing/prompts/{prompt_id}/versions`; análises usam
`GET /api/writing/prompts/{prompt_id}/feedback`. Ambas ordenam por
`(created_at DESC, id DESC)`, limitam a página a 100 itens e validam cursor opaco.

`GET /api/writing/history/page` projeta apenas o contexto necessário ao Caderno e
contagens correlacionadas de versões/análises. Não devolve o rascunho, snapshots ou
listas aninhadas. Curso/unidade e identidade entram na consulta, não em filtragem
posterior. A rota `/api/writing/history` permanece temporariamente para exportação
e consumidores antigos.

O teste de contrato força timestamps empatados, percorre páginas pequenas na ordem
exata, rejeita cursor inválido e confirma isolamento entre contas. Os orçamentos
observados, incluindo autenticação, foram 2 SQLs para versões, 4 para feedback com
snapshots em lote e 2 para o resumo, com até um checkout. O rascunho medido ficou
abaixo de 1.000 bytes sem histórico acidental. A regressão completa passou com
1.139 testes backend, Ruff, formatação e mypy. Speaking, revisão e o laboratório
1k/10k de escrita continuam abertos; este incremento não encerra toda a Sprint 41.

### Incremento 41F — speaking paginado com projeção, 15/10/2026

`GET /api/speaking/attempts/page` acrescenta paginação keyset por
`(created_at DESC, id DESC)`, limite de 1 a 100 e os mesmos filtros de aula, curso e
unidade da rota legada. Cursor malformado retorna 422 e a identidade continua na
consulta. A rota ilimitada `/api/speaking/attempts` foi preservada para o workspace
de shadowing e clientes ainda não migrados.

A primeira versão reutilizou o carregamento ORM completo e a sonda encontrou 22
SQLs para apenas dois itens, causado pelas coleções `selectin` da aula. A rota
paginada foi substituída por projeção explícita dos campos do contrato; jobs de
transcrição ativos e snapshots são buscados em lote. O resultado passou a usar
exatamente 5 SQLs por página, já incluindo autenticação, e um checkout.

O teste empata cinco datas, percorre 2/2/1 itens em ordem de ID, exclui tentativas
pendentes, rejeita cursor inválido e confirma isolamento por conta. A regressão
completa passou com 1.140 testes backend, Ruff, formatação e mypy. Não houve
migration: escala 1k/10k e plano profundo ainda são necessários antes de avaliar
índice composto. O histórico de revisão continua como próxima paginação da Sprint
41.

### Incremento 41G — revisão suspensa paginada, 15/10/2026

`GET /api/review/items/page` pagina itens por `(created_at DESC, id DESC)`, aceita
limite de 1 a 100 e conserva os filtros de status, curso e unidade da rota legada.
O cursor é opaco, limitado e estritamente validado; formato inválido responde 422
com `invalid_cursor`. A rota `/api/review/items` não foi removida.

A rota nova usa projeção explícita dos campos de `CardOut`, aula, unidade e curso,
sem instanciar relacionamentos `selectin`. Autenticação e página totalizaram
exatamente 2 SQLs e até um checkout. Cinco itens com o mesmo timestamp foram
percorridos em páginas 2/2/1 na ordem total dos IDs; outra conta, outro status e
outros escopos não entram no resultado.

A regressão final passou com 1.141 testes backend, Ruff, formatação e mypy. O
teste de retenção que criava consumo uma hora antes de 00:00 UTC também passou a
consultar explicitamente a mesma janela do registro, eliminando dependência da
virada do dia sem mudar produção. Não houve migration; os ensaios 1k/10k ainda
precedem qualquer índice novo.

### Incremento 41H — benchmark 1k/10k da revisão e índice promovido, 15/10/2026

`ops.review_performance` exercita a rota real `/api/review/items/page`, incluindo
autenticação, serialização e filtros de curso/unidade. A ferramenta recusa qualquer
banco sem nome, papel e marcador exclusivos de teste; mantém advisory lock, usa
contas sintéticas `.invalid`, não registra tokens/conteúdo e verifica a limpeza
exata ao terminar. O percurso completo confirmou 1 mil itens em 20 páginas e 10
mil em 200 páginas, sem lacuna, repetição ou cursor cíclico.

Cada página conservou o contrato de 2 SQLs, no máximo um checkout e header de bytes
igual ao corpo. Na massa de 10 mil, o candidato
`(user_id, status, created_at, id)` reduziu `EXPLAIN ANALYZE` profundo de 2,299 ms
para 0,305 ms e os blocos somados de 1.795 para 56. O p50 interno da página
profunda caiu de 5,68 ms para 5,20 ms e o p95 de 12,41 ms para 8,39 ms. Uma única
medição de inserção ficou sujeita a cache/ruído e não foi interpretada como ganho
de escrita.

A migration `d41e7ac905b2` cria o índice definitivo com `CONCURRENTLY`, valida
`indisvalid`, `indisready` e `pg_get_indexdef` e recusa um homônimo divergente sem
apagá-lo. Downgrade e re-upgrade passaram, assim como o teste do contrato e
`alembic check`. Uma repetição reconheceu o índice final e completou rajada de 10
requisições com HTTP 200. A regressão final aprovou 1.142 testes backend, 94 testes
operacionais, Ruff em todo o backend e nos arquivos novos, além de mypy. O
ambiente de estudo não foi consultado ou migrado.

### Incremento 41I — benchmarks de escrita e speaking, 16/10/2026

`make writing-benchmark` percorre, pelas rotas reais, versões, feedback e resumo de
textos em massas separadas de 1 mil/10 mil. Em 10 mil foram 200 páginas por
histórico, sem lacuna, duplicata ou cursor cíclico; os tetos permaneceram 2 SQLs
para versões, 4 para feedback e 2 para resumo, sempre com um checkout por chamada.
As rajadas de dez requisições responderam integralmente e ficaram abaixo da meta
negociada de 500 ms neste laboratório local.

Somente o candidato de feedback foi escolhido pelo planejador: o plano profundo
caiu de 1,607 ms/1.575 blocos para 0,062 ms/10 blocos. Candidatos de versões e
resumo não foram usados e não viraram migrations. A migration `e41f6c2a8d90` cria
o índice definitivo concorrentemente, valida definição/estado e passou por
downgrade, re-upgrade e `alembic check`. Com o índice final, o feedback mediu
0,061 ms/8 blocos, p50 3,50 ms e p95 4,65 ms na página profunda.

`make speaking-benchmark` também percorreu 20/200 páginas com 5 SQLs e um checkout.
O candidato composto não foi escolhido — o plano preferiu o índice existente — e
a primeira página regrediu no ensaio; portanto nenhum índice de speaking foi
promovido. Os tempos são evidência local para decisão, não SLO de produção.

### Incremento 41J — ETag público e política privada, 16/10/2026

Conteúdo editorial JSON público recebe ETag SHA-256 forte e estável. `If-None-Match`
aceita lista, wildcard e comparação fraca de GET, respondendo 304 sem corpo. O
validador e `X-Aulas-Offline` estão expostos pelo CORS. Erros, autenticação,
progresso, escrita, voz e demais respostas privadas nunca recebem ETag e preservam
`private, no-store`.

O runtime passou a declarar pool, overflow, espera e timeouts SQL por ambiente. Os
defaults mantêm 5 conexões + 5 de overflow por processo, espera de 10 s,
`statement_timeout=30s` e `lock_timeout=5s`; API + worker somam teto declarado de
20 conexões, sem alterar `max_connections`. Testes conferem os valores efetivos na
sessão PostgreSQL. Com esses incrementos, todas as entregas técnicas de BE-41 estão
implementadas; valores locais continuam sem promessa de produção. A validação final
aprovou **1.151 testes backend**, **94 testes operacionais**, Ruff, formatação dos
arquivos deste incremento, mypy e `alembic heads` em `e41f6c2a8d90`.

## Sprint 42 Observabilidade e implantação segura

Prioridade P1/P2 operacional. Achados B12 e D08; fechamento transversal.

### Entregas

- [x] Definir readiness que valide dependências/schema compatíveis, mantendo liveness separado.
- [x] Ordenar deploy: backup verificado, migration compatível, verificação de schema/seed e liberação de tráfego. Evitar servir código novo sobre banco antigo.
- [x] Expor métricas agregadas de latência/erro, pool, fila, retries, expirados e capacidade de mídia; limitar cardinalidade.
- [x] Padronizar request-id validado e correlação de API/worker sem incluir textos, e-mails, tokens ou áudio nos logs.
- [x] Acrescentar auditoria de dependências/imagens com triagem e política de atualização, sem falhar release por resultado não analisado.
- [ ] Homologar headers de segurança e HTTPS no perfil público; avaliar CSP com fontes/mídias legítimas e manter ambiente local funcional.
- [x] Executar ensaio de recuperação, falha de provedor, banco indisponível e reinício de worker em ambiente isolado.
- [x] Publicar runbooks operacionais de incidentes e checklist de release, incluindo bloqueios humanos ainda abertos.

### Critérios de aceite

1. Versão incompatível de schema mantém readiness negativa e impede publicação; não basta `/live` responder 200.
2. Alertas são testados e indicam ação/limiar/responsável, não apenas gráficos.
3. Falha de gateway não derruba correção local; indisponibilidade de banco não gera perda silenciosa de evento.
4. Ensaio restaura banco e voz e valida acesso autorizado aos arquivos, conforme DB-42.
5. CI cobre contratos, tipagem, isolamento, concorrência e migração representativa; exceções de segurança têm prazo e justificativa.
6. Backlog residual diferencia defeito, risco aceito, melhoria futura e homologação humana pendente.

### Evidência executada em 16/10/2026

O fluxo legado que iniciava aplicação antes da migration foi bloqueado. O
laboratório executou backup, restore, migration, `alembic check`, leitura com a
imagem atual e leitura com a imagem anterior sobre o schema expandido, sem
downgrade destrutivo.

O alvo `test-failure-rehearsal` aprovou **5 cenários** na base descartável:
falha transitória de acesso ao banco com backoff/cancelamento, fallback de
escrita quando o provedor falha, preservação do áudio na falha de transcrição,
retry com a mesma chave idempotente e retomada de job que ficou `processing`
após interrupção. O ensaio representa falhas controladas no processo; não é
alegação de desastre físico real.

A CI agora inventaria locks Python/npm e as imagens candidatas API/web e guarda
relatórios privados para triagem. A política, prazos e decisões permitidas estão
em `politica_triagem_seguranca_sprint_42.md`. As dependências locais tiveram
zero vulnerabilidades conhecidas. O Trivy `v0.76.0` rejeitou as bases anteriores,
que somavam 2 ocorrências críticas/41 altas na web e 44 altas na API. Após mover
a web para Nginx `1.30.6-alpine3.24` e a API para Python
`3.12.15-alpine3.24`, o reteste encontrou zero críticas/altas nas duas imagens.
O smoke da API confirmou UID 10001, bibliotecas nativas e health compatível no
banco descartável. O próximo commit ainda deve produzir o artefato equivalente
na CI; não se declara essa execução remota antes de ela ocorrer.

## Definição de pronto

- Aceites funcionais e de concorrência verificados em banco descartável, com evidências e sem dados pessoais reais.
- Testes backend, OpenAPI e consumidores frontend consistentes; migrações têm plano e reversão segura.
- Queries respeitam usuário, curso, política editorial e limites operacionais.
- Modificações do algoritmo de estudo são versionadas e explicadas, sem recalcular histórico automaticamente.
- Logs e observabilidade não expõem conteúdo pessoal.
- Toda alteração de contrato tem dono de implementação por frente; um mock frontend não encerra entrega backend.
