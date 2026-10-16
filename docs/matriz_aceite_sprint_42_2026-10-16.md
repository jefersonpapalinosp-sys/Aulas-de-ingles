# Sprint 42 — matriz de aceite e pendências residuais

Atualização: 16 de outubro de 2026. “Implementado” não significa homologação
humana. Evidências privadas de backup permanecem em `backups/recovery/`, ignorado
pelo Git; este documento registra apenas resultados agregados.

| Frente | Critério | Estado | Evidência / ação restante |
|---|---|---|---|
| FE | textos distinguem correção, rubrica, assistência e autoavaliação | implementado e automatizado | testes dos componentes de prática, escrita e fala |
| FE | competência mostra origem, período e amostra mínima | implementado e automatizado | API e telas Hoje/conclusão; percentual só com 3 amostras |
| FE | sessão rápida separa referência por item e orçamento total | implementado e automatizado | ~2 min/item, até 10 min no modo rápido, sem cronômetro obrigatório |
| FE | retomada, fila/offline, conflito e privacidade explicados | implementado | `guia_do_aluno_retomada_offline_privacidade.md` |
| FE | jornada estável, lenta, offline, sessão expirada e atualização | aprovada automaticamente no Chromium | 6 cenários: fluxo completo, rede lenta, expiração, offline e dois ciclos PWA |
| conteúdo | inventário individual de cues associado à aula/versão | registrado | 408 de 408 estão `pending_human_listening`; `make cue-audit` |
| conteúdo | conferência auditiva dos cues | homologação humana pendente | professor/Jeferson deve ouvir e registrar decisão/revisor/data |
| BE | liveness separado de readiness de DB/schema | aprovado automaticamente | schema antigo retorna 503; head exato retorna 200 |
| BE | métricas/gate agregados | implementado | limiares incluem erro, locks, fila, worker, retenção e espaço de voz |
| BE | correlação API/worker sem conteúdo pessoal | aprovado automaticamente | request-id + job-id opaco em testes |
| BE | ordem segura de release | ensaiada no laboratório | fluxo legado bloqueado; ensaio DB-42 parte de `e41f6c2a8d90` |
| BE | dependências e imagens | aprovado na candidata local | locks sem vulnerabilidade conhecida; Trivy 0.76: API/web com 0 críticas e 0 altas após troca das bases; CI deve repetir por commit |
| BE | HTTPS público e headers | parcial | headers/CSP locais automatizados; certificado/proxy público pendente |
| BE | falhas de provedor, banco e restart do worker | aprovado em simulação isolada | 5 testes: falha DB, fallback/provedor, retry idempotente e retomada de job |
| DB | upgrade representativo anterior → head | aprovado no laboratório | 18 modalidades + sessão ativa + voz; migration 7,475 s, zero locks aguardando |
| DB | drift SQLAlchemy/Alembic/schema | aprovado no laboratório | `alembic check` após restore/migration |
| DB | restore de banco + voz e leitura pela aplicação | aprovado no laboratório | 1 usuário sintético, 16.044 bytes, checksum, papel limitado e 80 FKs validadas |
| DB | RPO 24 h / RTO 60 min | meta ainda a validar | ensaio prova mecanismo; falta medir recuperação operacional completa e rotina diária |
| DB | capacidade/conexões/locks/jobs/retenção | implementado | snapshot limitado e gate operacional; coletor deve reter amostras para tendência |
| DB | destino de `review_card` legado | permanência aprovada | mantido durante exportação 2.x; gate exige zero vínculos ausentes/divergentes |
| acessibilidade | teclado estrutural e zoom | aprovado na validação anterior | sem reflow horizontal |
| acessibilidade | VoiceOver/TalkBack/contraste forçado | homologação física pendente | macOS/iOS, Android e Windows reais |
| pedagogia | exemplos de escrita | homologação humana pendente | fechamento técnico foi autorizado sem declarar aceite pedagógico |

## Resultado do ensaio DB-42

- origem criada diretamente na revisão anterior, sem downgrade de dados atuais;
- backup conjunto restaurado em banco e volume de voz separados, sem portas;
- contagens idênticas antes/depois para usuário, exercício, prática, escrita,
  revisão, jornada, atividade, progresso, caderno, transcrição e voz;
- aplicação atual leu o clone e o arquivo restaurado com checksum válido;
- `alembic check` não encontrou operação de schema pendente;
- locks aguardando antes, durante e depois: zero.

O intervalo entre a criação do pacote e o recibo final foi aproximadamente 25 s;
dentro dele, 7,475 s correspondem à migration. Isso mede o caminho técnico
automatizado, não o RTO operacional total. A meta RTO de 60 minutos e RPO de 24
horas continua “operacional a validar” até incluir detecção, decisão, troca de
configuração, liberação e uma rotina de backup executada na frequência acordada.

## Regressão técnica desta rodada

- 1.161 testes backend aprovados no PostgreSQL descartável;
- 360 testes frontend, ESLint, TypeScript, build e orçamento aprovados;
- 101 testes operacionais puros aprovados;
- 5 ensaios dirigidos de falha aprovados;
- 6 cenários E2E da matriz de experiência aprovados;
- OpenAPI e tipos do frontend regenerados e sincronizados;
- Ruff e mypy aprovados nos 92 módulos do backend.

## Regra de fechamento

A Sprint 42 pode ter fechamento técnico parcial, mas não recebe aceite integral
enquanto as linhas “pendente” acima permanecerem abertas. Nenhuma automação
substitui escuta humana, leitor de tela/dispositivo real, revisão pedagógica ou
homologação HTTPS com certificado real.
