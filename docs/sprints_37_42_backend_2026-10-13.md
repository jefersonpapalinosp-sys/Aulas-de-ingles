# Sprints de backend para correção e confiabilidade do estudo

Atualização: 14 de outubro de 2026. **BE-38 implementada, validada em ambiente isolado e implantada em 5181 após autorização.** Jornadas legadas inconsistentes foram preservadas e estão documentadas abaixo. A homologação pedagógica humana da escrita permanece pendente e não foi declarada aprovada. BE-39 a BE-42 permanecem planejados.

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

### Entregas

- [ ] Substituir métrica semanal derivada do total histórico por soma de eventos/intervalos ativos dentro de uma janela temporal.
- [ ] Definir fuso do plano semanal e regra de início da semana; tratar tempo do cliente como entrada limitada, não como autoridade absoluta.
- [ ] Deduplicar eventos e impedir contagem duplicada em duas abas. Detectar ociosidade/visibilidade com contrato simples e minimização de telemetria.
- [ ] Harmonizar limite de voz na API, proxy e contrato; implementar leitura limitada sem acumular corpo arbitrário em memória.
- [ ] Verificar formato/duração reais de áudio com limites de CPU/tempo, transição de upload atômica e resposta idempotente ou conflito documentado.
- [ ] Implementar reconciliação segura de tentativas pendentes e arquivos sem referência, com dry-run e período de segurança.
- [ ] Reservar cota assistida atomicamente antes da chamada externa; consumo não desaparece ao apagar resultado.
- [ ] Definir reembolso de reserva por erro/timeout e semântica de custo em retries; preservar chave de provedor quando suportada.
- [ ] Não manter conexão/transação SQL aberta enquanto aguarda Ollama/gateway.
- [ ] Expirar transcrições por rotina independente do acesso do usuário; excluir jobs expirados da reivindicação/leitura/exportação.
- [ ] Proteger worker contra falha temporária de banco e oferecer sinal de atividade/atraso de fila.

### Critérios de aceite

1. Uma aula com 60 minutos antigos e dois novos informa dois minutos na semana corrente, não 62; dados legados não são retrodistribuídos sem evidência.
2. Retry, relógio deslocado e duas abas não duplicam tempo; retorno após um dia não registra automaticamente 30 minutos ativos.
3. Arquivos nos limites acordados têm mesmo comportamento no acesso direto e via Nginx, incluindo requisição sem Content-Length.
4. Duas tentativas de upload simultâneas não deixam arquivos órfãos ou duplicam evidência de competência.
5. Cota cinco suporta no máximo cinco reservas cobradas conforme política, mesmo com seis pedidos concorrentes ou exclusão de transcrição.
6. Job expirado não chama provedor. Limpeza não depende de o estudante voltar ao sistema.
7. Reiniciar worker recupera jobs válidos sem permitir que worker antigo sobrescreva resultado; testes preservam as proteções já existentes.

Fora do escopo: cobrança financeira ao usuário, avaliação automática de pronúncia como nota oficial e hospedagem pública do Ollama.

## Sprint 40 Histórico editorial e dados pessoais

Prioridade P1/P2. Achados B09, B11 e D04. Dependências: DB-40 antes de migrações de conteúdo; FE-40 para visualização.

### Entregas

- [ ] Criar inventário de dados pessoais e corrigir exportação para incluir checkpoints, sessões/itens de prática, feedbacks sem draft e metadados/versionamento.
- [ ] Versionar o formato de exportação e garantir snapshot coerente; definir estratégia assíncrona/streaming se tamanho exigir.
- [ ] Disponibilizar exportação autorizada de binários ou manifesto com downloads protegidos, distinguindo isso do JSON de metadados.
- [ ] Aplicar prazo/controle de acesso a exportações e expiração das transcrições nelas contidas.
- [ ] Definir procedimento de exclusão de conta/recursos, arquivos e tarefas associadas, com autenticação reforçada, confirmação e prazo operacional.
- [ ] Adotar versão editorial/snapshot suficiente para interpretar tentativas antigas e resultados de escrita sem gabarito mutável.
- [ ] Acrescentar prévia/diff ao seed e rejeitar remoção destrutiva de conteúdo referenciado sem plano explícito.
- [ ] Centralizar política de publicação/arquivamento em rotas por slug e por ID, preservando histórico permitido.
- [ ] Corrigir proveniência editorial: datas e versões vêm da revisão correspondente, não de constante global de 7 de outubro.

### Critérios de aceite

1. Conta sintética com todas as modalidades exporta todas as entidades previstas no inventário; feedback sem rascunho não desaparece.
2. Exportar conta A não inclui dados nem arquivos de B. Links de áudio continuam autenticados e não são publicados no cache.
3. Resultado de exercício antigo continua coerente após alteração de enunciado/gabarito; versão anterior permanece interpretável.
4. Seed que remove prompt com draft/cue com voz/exercício com prática exige arquivamento ou plano aprovado, não cascade silencioso.
5. Unidade arquivada tem comportamento consistente nas rotas diretas, laboratório, revisão e histórico, segundo contrato.
6. Exclusão de dados possui retry seguro e tratamento de falha parcial entre banco e filesystem; nenhum dado real é apagado nos testes.

Fora do escopo: prometer conformidade legal automática, redefinir certificado interno ou reprocessar histórico pedagógico em massa.

## Sprint 41 Performance e contratos paginados

Prioridade P2. Achados B10, F11 e D06.

### Entregas

- [ ] Instrumentar contagem SQL e tamanho de payload nos principais endpoints, usando a amostra de 17 SQLs do detalhe apenas como ponto de investigação.
- [ ] Separar projeção pública, detalhe editorial, histórico e comando de escrita; evitar carga automática de relações desnecessárias.
- [ ] Remover consultas por checkpoint dentro do loop de recomendação quando a medição confirmar custo relevante.
- [ ] Paginar escrita, speaking, notebook e revisão suspensa com cursor estável composto por data e ID, limites máximos e filtros consistentes.
- [ ] Tornar resposta de autosave pequena; obter histórico de versões por chamada paginada separada.
- [ ] Definir limites de exportação/processamento e streaming/jobs quando justificado pelo ensaio de volume.
- [ ] Cooperar com DB-41 na análise dos planos de execução, sem prescrever índices indiscriminados.
- [ ] Padronizar invalidadores/ETags de conteúdo público, preservando `no-store` privado.

### Critérios de aceite

1. Cenários com 1 mil e 10 mil itens sintéticos por histórico mantêm paginação estável, sem lacunas/duplicatas quando datas empatam.
2. Identidade de usuário e escopo de curso/unidade permanecem corretos em todas as páginas e cursores inválidos são recusados.
3. SQL count não cresce linearmente com itens de uma página por N+1; limites de consultas são documentados por rota.
4. Registrar p50/p95, payload e uso de pool num ambiente declarado. Metas sugeridas para negociação: p95 de leituras usuais abaixo de 500 ms em carga de ensaio e sem regressão superior a 20% sobre baseline estável.
5. Resultado funcional, idempotência, privacidade e acessibilidade não são sacrificados para atingir a meta de latência.
6. Não usar resultados locais de amostra única como promessa de produção nem exigir Redis sem comprovar necessidade.

Fora do escopo: fragmentar o monólito, particionar tudo ou reescrever SQLAlchemy.

## Sprint 42 Observabilidade e implantação segura

Prioridade P1/P2 operacional. Achados B12 e D08; fechamento transversal.

### Entregas

- [ ] Definir readiness que valide dependências/schema compatíveis, mantendo liveness separado.
- [ ] Ordenar deploy: backup verificado, migration compatível, verificação de schema/seed e liberação de tráfego. Evitar servir código novo sobre banco antigo.
- [ ] Expor métricas agregadas de latência/erro, pool, fila, retries, expirados e capacidade de mídia; limitar cardinalidade.
- [ ] Padronizar request-id validado e correlação de API/worker sem incluir textos, e-mails, tokens ou áudio nos logs.
- [ ] Acrescentar auditoria de dependências/imagens com triagem e política de atualização, sem falhar release por resultado não analisado.
- [ ] Homologar headers de segurança e HTTPS no perfil público; avaliar CSP com fontes/mídias legítimas e manter ambiente local funcional.
- [ ] Executar ensaio de recuperação, falha de provedor, banco indisponível e reinício de worker em ambiente isolado.
- [ ] Publicar runbooks operacionais de incidentes e checklist de release, incluindo bloqueios humanos ainda abertos.

### Critérios de aceite

1. Versão incompatível de schema mantém readiness negativa e impede publicação; não basta `/live` responder 200.
2. Alertas são testados e indicam ação/limiar/responsável, não apenas gráficos.
3. Falha de gateway não derruba correção local; indisponibilidade de banco não gera perda silenciosa de evento.
4. Ensaio restaura banco e voz e valida acesso autorizado aos arquivos, conforme DB-42.
5. CI cobre contratos, tipagem, isolamento, concorrência e migração representativa; exceções de segurança têm prazo e justificativa.
6. Backlog residual diferencia defeito, risco aceito, melhoria futura e homologação humana pendente.

## Definição de pronto

- Aceites funcionais e de concorrência verificados em banco descartável, com evidências e sem dados pessoais reais.
- Testes backend, OpenAPI e consumidores frontend consistentes; migrações têm plano e reversão segura.
- Queries respeitam usuário, curso, política editorial e limites operacionais.
- Modificações do algoritmo de estudo são versionadas e explicadas, sem recalcular histórico automaticamente.
- Logs e observabilidade não expõem conteúdo pessoal.
- Toda alteração de contrato tem dono de implementação por frente; um mock frontend não encerra entrega backend.
