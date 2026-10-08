# Aulas de Inglês

App de estudo construído sobre a série *Let's Learn English* (VOA, nível 1).
Catálogo de aulas, vocabulário com IPA, exercícios corrigidos no servidor,
progresso por usuário e revisão espaçada do que você errou.

**Estado: v1.4 — Sprints 6–14 concluídas no piloto.** O caderno, a conta, o progresso, o painel
Hoje, a revisão multimodal e o modo offline instalável funcionam. A Aula 31 também possui uma
jornada guiada com áudio, escrita, speaking e assistência opcional. Os recursos assistidos
ficam desligados por padrão até passarem pela avaliação humana.

---

## Stack

| Camada | Tecnologia |
|---|---|
| Frontend | React 19 + TypeScript + Vite |
| Backend | FastAPI + SQLAlchemy 2.0 async + asyncpg |
| Banco | PostgreSQL 16 (container, volume nomeado) |
| Testes | pytest · Vitest · Playwright (a partir da S5) |

## Subir o projeto

Pré-requisitos: Docker e `make`. Mais nada — Python e Node rodam dentro dos containers.

```bash
git clone git@github.com:jefersonpapalinosp-sys/Aulas-de-ingles.git
cd Aulas-de-ingles
cp .env.example .env
make up
```

| Serviço | URL |
|---|---|
| Frontend | <http://localhost:5180> |
| API | <http://localhost:8010/api/health> |
| Aulas | <http://localhost:8010/api/lessons> |
| OpenAPI | <http://localhost:8010/docs> |
| Postgres | `localhost:5433` |

As portas não são as padrão de propósito: `5432`, `5444`, `5456`, `8000`, `8001`,
`8005`, `5173` e `5174` já estão em uso por outros projetos na máquina de origem.
Para mudar, edite o `.env` — nada está fixo no código.

## Comandos

```bash
make help       # lista tudo

# desenvolvimento
make up         # sobe db + api + web, migra e semeia
make down       # derruba (mantém o banco)
make reset      # derruba e apaga o volume do banco
make logs       # acompanha os logs
make health     # bate no /api/health
make migrate    # aplica as migrations
make seed       # carrega seed/lessons.json (idempotente)
make openapi    # regrava o baseline do contrato

# testes
make test       # pytest + vitest
make cov        # pytest com relatório de cobertura
make test-e2e   # Playwright contra o compose de produção
make lint       # ruff + mypy + eslint + tsc

# produção local
make prod-up    # nginx + uvicorn + Postgres nas portas 5181/8011/5434
make prod-down
make prod-logs  # JSON, uma linha por requisição
make backup     # dump em backups/
make restore f=backups/aulas-....dump
```

### Rodar fora do container

Útil para debugar com breakpoint. O banco continua no Docker.

```bash
make up        # sobe pelo menos o db
make api       # uvicorn no host, porta 8010
make web       # vite no host, porta 5180
```

## Como as peças se falam

```
navegador → :5180 Vite ──proxy /api──→ :8000 FastAPI ──asyncpg──→ :5432 Postgres
```

O browser **nunca** chama a API direto: tudo passa por `/api` na mesma origem,
via proxy do Vite. Isso elimina CORS em dev e deixa o caminho pronto para o
cookie `httpOnly` da sprint 3.

## Health check

`/api/live` é *liveness*: responde 200 enquanto o processo estiver de pé, sem
tocar em dependência alguma.

`/api/health` é *readiness*: abre uma conexão e pergunta a versão ao Postgres.

```bash
$ make health
{"status":"ok","db":"up","version":"PostgreSQL 16.10","env":"dev"}
HTTP 200
```

Com o banco fora do ar vira `503` com `"db":"down"` — é isso que faz o endpoint
valer alguma coisa:

```bash
docker stop aulas-db && make health   # HTTP 503
docker start aulas-db
```

## Conteúdo das aulas

### Modelo

```
lesson ─┬─ lesson_goal
        ├─ content_source
        ├─ lesson_version
        ├─ grammar_block ── grammar_row
        ├─ phrase
        ├─ lesson_media ── transcript_cue
        ├─ writing_prompt
        ├─ vocab_item
        ├─ pronunciation_note
        └─ exercise ─┬─ exercise_answer
                     └─ exercise_hint

app_user ─┬─ study_session_progress ─┬─ lesson
          │                          └─ step_progress
          ├─ study_plan
          ├─ skill_evidence
          ├─ review_item ── lesson / origem da atividade
          ├─ media_progress ── lesson_media
          ├─ speaking_attempt ── transcription_job
          └─ writing_draft ─┬─ writing_revision
                            └─ writing_feedback
```

`exercise_answer` é tabela à parte porque um exercício aceita mais de uma
resposta certa (`should` e `ought to`, por exemplo) e todas valem igual.

O que está carregado hoje: **10 aulas**, 40 objetivos, 31 blocos de gramática
com 152 linhas, 76 frases, **115 itens de vocabulário**, 45 notas de pronúncia,
**10 áudios oficiais**, 48 trechos selecionados, 289 falas de transcrição integral,
**10 propostas de escrita** e **110 exercícios**
com 133 respostas aceitas e 107 dicas graduais nas Aulas 31–40. As Aulas 32–40 possuem
três práticas de listening e atividades de ditado, ordenação e transformação. As dez aulas também
possuem fonte oficial/autoral, estratégia, versão e status editorial explícitos.

### Formato do texto

Todo campo de texto exibível guarda um **subconjunto de Markdown** —
`**negrito**`, `*itálico*`, `` `código` `` e `~~riscado~~`. HTML cru não entra
no banco: elimina a superfície de XSS, deixa o seed editável à mão e mantém a
aparência sob controle do frontend. Há um teste que falha se HTML vazar no
payload.

### Seed

`seed/lessons.json` é a fonte do conteúdo. `make seed` é idempotente:

- `lesson`, `vocab_item`, `exercise` e `writing_prompt` são atualizados no lugar, pela chave
  natural. A partir da S3 as tentativas e as cartas de revisão apontam para
  esses ids, e eles não podem trocar a cada novo seed.
- O resto é descritivo: apaga e reinsere.

### Contrato

`backend/openapi.json` é o baseline versionado, e ele é a fonte dos tipos do
frontend — nenhuma interface de API é escrita à mão.

```bash
make openapi                  # regrava o baseline depois de mudar a API
cd frontend && npm run gen:api  # regenera src/api/schema.d.ts a partir dele
```

Dois gates no CI garantem que ninguém esquece:

- um teste do backend falha se o contrato gerado pelo código divergir do
  arquivo commitado;
- um passo do frontend falha se `src/api/schema.d.ts` estiver desatualizado.

## Autenticação

| O quê | Onde fica | Por quê |
|---|---|---|
| Senha | Argon2id no banco | nunca em claro, nunca em log |
| Access token | **memória** do frontend, 15 min | o que o JS lê, um XSS também lê |
| Refresh token | cookie `httpOnly`, `SameSite=Lax`, `Path=/api/auth` | o JS não enxerga, e só a rota de refresh o recebe |
| Sessão de refresh | tabela `refresh_session` | sem isso `logout` seria decorativo |

O refresh **roda**: usar um invalida o anterior. Reapresentar um refresh já
usado devolve 401 e pede login — é o que limita o estrago de um token vazado.

Recarregar a página perde o access token (ele é de memória) e a aplicação
pede um `/refresh` automaticamente. Se o cookie ainda valer, a sessão volta
sem passar pela tela de login.

## Instalação e modo offline

O build de produção é uma PWA. Depois da primeira visita, o navegador pode instalar o app e
reabrir o shell e aulas públicas já visitadas sem conexão. O aviso de conectividade mostra
quantas tentativas aguardam envio; ao voltar à rede, a sessão é renovada e a fila sincroniza
automaticamente com a chave idempotente original.

O access token continua apenas em memória. O navegador guarda somente o perfil mínimo do
último aluno para associar corretamente a fila. Dados privados, gabaritos, progresso, revisão,
escrita, speaking, áudio e vídeo não entram no cache. A política completa e a auditoria WCAG
estão em `docs/auditoria_sprint13_qualidade_offline.md`.

O browser fala com a API pelo proxy do Vite, na mesma origem. Isso não é
detalhe de conforto: cookie `httpOnly` com `credentials` **não funciona** com
`allow_origins=["*"]`, então a saída certa é a mesma origem, não CORS aberto.

## Assistência opcional

Speech-to-text e feedback aberto de escrita são experimentos por opt-in e ficam desativados por
padrão. Sem eles, a autoavaliação oral e a rubrica determinística continuam funcionando. Quando
ativados, a interface identifica o conteúdo automatizado, destaca confiança inferior a 75%,
mostra a cota restante e permite avaliar ou excluir a transcrição sem apagar o áudio.

A API controla feature flags, cota diária, custo e retenção. Em produção, gateways precisam usar
HTTPS e token; texto e áudio não entram nos logs. Configuração, contrato HTTP, política de
privacidade, fallback e gate de avaliação humana estão em
`docs/avaliacao_sprint14_assistencia.md`.

O gate é executável e falha fechado. Copie
`config/assist-provider-review.example.json` para o arquivo local ignorado
`config/assist-provider-review.json`, preencha a homologação e rode uma modalidade por vez:

```bash
make assist-gate modality=writing review=../config/assist-provider-review.json
make assist-gate modality=transcription review=../config/assist-provider-review.json
```

O comando só produz métricas agregadas e retorna código `0` quando todos os critérios passam,
`1` quando a liberação continua bloqueada e `2` para configuração inválida. Ele não altera a
feature flag.

### Correção de exercício

A resposta certa **não** faz parte do contrato de leitura. Mandá-la ao
navegador para o JavaScript comparar seria publicar o gabarito. Então:

| Ação | Endpoint |
|---|---|
| Responder (confere e **grava**) | `POST /api/exercises/{id}/attempt` |
| Pedir dica gradual | `GET /api/exercises/{id}/hints/{level}` |
| Ver o gabarito (o usuário pede) | `GET /api/exercises/{id}/answer` |
| Marcar / desmarcar aula | `PUT` / `DELETE /api/lessons/{n}/studied` |
| Ler / salvar retomada | `GET` / `PUT /api/lessons/{n}/study-session` |
| Ler / salvar rascunho | `GET` / `PUT /api/writing/prompts/{id}/draft` |
| Criar versão do texto | `POST /api/writing/prompts/{id}/versions` |
| Analisar critérios | `POST /api/writing/prompts/{id}/feedback` |
| Meu progresso | `GET /api/me/progress` |

Ler o conteúdo das aulas é público; responder e marcar exigem conta.
Cada tentativa guarda **o texto exato digitado** — é isso que vai permitir,
na S4, descobrir *qual* item a pessoa erra, e não só que ela errou.

A comparação vive em `app/domain/answers.py`, isolada de banco e de HTTP:
ignora caixa, pontuação, espaço sobrando e tipo de apóstrofo — digitar
`Won't`, `wont` ou `won’t` não pode ser a diferença entre acerto e erro.
Quando há erro, o mesmo domínio o classifica como palavra faltando, palavra
extra, ordem, ortografia ou escolha de palavra. O cliente recebe marcações
somente sobre o que digitou; a resposta esperada continua protegida. Cada
requisição também leva uma chave de idempotência, evitando duplicar tentativas
quando a conexão oscila.

Na Aula 31, o motor já renderiza lacuna, múltipla escolha, transformação, ditado e ordenação.
A primeira dica
pode ser aberta diretamente; a segunda exige uma tentativa errada. O gabarito
continua em uma ação separada e explícita.

### Markdown no frontend

`src/components/Markdown.tsx` renderiza o subconjunto para nós do React. Não
existe `dangerouslySetInnerHTML` em lugar nenhum do projeto, então texto vindo
do banco nunca vira markup.

## Repetição espaçada

O algoritmo é o **SM-2**, o mesmo do Anki, em `app/domain/sm2.py` — função
pura, sem banco e sem relógio global: o `agora` entra como argumento, para o
teste simular trinta dias sem esperar trinta dias.

### A curva

Acertando sempre com nota máxima, uma carta volta em:

| revisão | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| **dias** | 1 | 6 | 16 | 45 | 130 | 390 |

Errar zera a sequência e conta um lapso, mas **não** zera o fator de
facilidade: a dificuldade que a carta já demonstrou é informação acumulada.

Dois detalhes que mudam o resultado e por isso estão fixados em teste:

- o intervalo usa o fator de facilidade **anterior** à revisão, como no SM-2
  original — inverter a ordem adianta o efeito em um passo;
- o fator é arredondado a duas casas em cada passo. Somar `0.1` em float
  acumula erro (`2.8 + 0.1 = 2.9000000000000004`), e esse erro chega ao
  intervalo: `45 × 2.9000000000000004` dá `130.50000000000003`, que arredonda
  para 131 em vez de 130.

### Como as cartas entram no deck

| Gatilho | O que entra |
|---|---|
| Marcar uma aula como estudada | todo o vocabulário da aula |
| Botão **+ revisar** na tabela de vocabulário | aquele item |
| Errar um exercício cuja resposta é um termo do vocabulário | aquele item |

O terceiro gatilho estava no plano como a fonte principal, mas vale para
**4 dos 63 exercícios** do bloco: eles treinam gramática, não palavra. O
grosso do deck vem de marcar a aula como estudada.

Adicionar é idempotente: um item que já está no deck não tem o agendamento
reiniciado — isso apagaria o histórico de quem já estuda.

### Fuso

`due_at` é `timestamptz` e sempre em UTC; a conversão acontece na borda.
A suíte roda idêntica sob `TZ=UTC`, `America/Sao_Paulo`, `Pacific/Kiritimati`
(UTC+14) e `Pacific/Midway` (UTC−11).

## Produção local

O compose de produção é diferente do de dev de propósito: bundle buildado
servido por **nginx**, API sob uvicorn com workers e **sem reload**, imagem
sem pytest/ruff/mypy dentro, processo rodando como usuário sem root.

```bash
cp .env.prod.example .env.prod
openssl rand -hex 32          # para o JWT_SECRET
make prod-up                  # http://localhost:5181
```

Diferente do `.env` de dev, aqui **não há default para segredo**: a stack
recusa subir sem `POSTGRES_PASSWORD`, `DATABASE_URL` e `JWT_SECRET` próprios,
e a aplicação valida que o segredo tem pelo menos 32 bytes.

`COOKIE_SECURE=false` em localhost é intencional: com `Secure` ligado o
navegador simplesmente não envia o cookie por HTTP, e o login para de
funcionar. Ligue junto com HTTPS, não antes.

### Observabilidade

Uma linha de log em JSON por requisição, com `request_id` que também volta no
cabeçalho `X-Request-ID`. Um id vindo de fora é respeitado, para um proxy na
frente conseguir amarrar o rastro de ponta a ponta.

```json
{"ts":"2026-10-07T19:43:50.752Z","level":"INFO","logger":"app.request",
 "msg":"GET /api/health 200","request_id":"3bb1c073923e4001",
 "method":"GET","path":"/api/health","status":200,"duration_ms":27.6}
```

`/api/live` é *liveness* e não toca em dependência; `/api/health` é
*readiness* e abre conexão no banco.

### Backup e restore

```bash
make backup                              # backups/aulas-AAAAMMDD-HHMM.dump
make restore f=backups/aulas-....dump    # --clean --if-exists
```

Testado derrubando o schema inteiro (`drop schema public cascade`) e
restaurando: usuários, cartas de revisão e tentativas voltam intactos.

## Testes

| Suíte | O que cobre | Como rodar |
|---|---|---|
| pytest | 129 testes contra o Postgres do compose | `make test-api` |
| vitest | 65 testes de componente, fluxo e parser | `make test-web` |
| Playwright | 15 cenários em desktop e mobile (30 execuções), contra **produção** | `make prod-up && make test-e2e` |

O frontend possui uma **jornada guiada** em todas as Aulas 31–40. Ela divide o estudo em
preparar, assistir, estudar, praticar e revisar. A etapa atual é salva localmente e na conta,
permitindo continuar em outro navegador. Em “Assistir”, o player usa o áudio oficial da VOA,
sincroniza a posição na conta e oferece velocidade, saltos de cinco segundos, repetição A–B e
48 trechos selecionados com tradução opcional. As atividades de compreensão são corrigidas pela
API sem enviar o gabarito antes da
resposta. Na revisão, o aluno pode praticar *shadowing*, gravar a voz localmente, comparar com
o modelo e salvar uma autoavaliação. O áudio permanece local por padrão; somente após
consentimento explícito pode ser salvo no volume privado da conta, ouvido no histórico e
excluído junto com seus metadados. Essa etapa também oferece produção escrita com autosave,
backup local em caso de falha, checklist de critérios e histórico de versões privado por
conta, incluindo comparação visual entre versões. O **Caderno** centraliza notas por aula,
frases favoritas, exemplos, erros, perguntas, textos e gravações; o aluno também pode exportar
seus dados em JSON. A página completa da aula continua disponível durante a evolução do novo
fluxo.

Na entrada, o painel **Hoje** sugere deterministicamente revisar itens vencidos, retomar a
sessão mais recente ou começar a próxima aula — e sempre explica o motivo. O plano semanal é
editável e não bloqueia a navegação livre. Gramática, listening, escrita e fala acumulam
evidências separadas; para evitar falsa precisão, o percentual de uma competência só aparece
depois de três evidências. Tempo aproximado, conclusão e retomada são registrados por etapa.

A revisão usa uma fila única para vocabulário, erros gramaticais, listening, frases favoritas,
prompts de escrita e trechos de speaking. O aluno pode filtrar por tipo, competência e duração,
entender por que cada item voltou e suspender, reativar ou excluir uma revisão. O intervalo SM-2
continua orientado pelo desempenho, com ajuste por tipo de atividade. A migração copia IDs,
intervalos, facilidade, repetições, lapsos e vencimentos do deck antigo sem recalculá-los.

O CI roda os três, mais: `ruff`, `mypy --strict`, `eslint`, `tsc`, o build de
produção, migrations para frente e para trás, seed rodado duas vezes, piso de
**90% de cobertura**, orçamento de bundle e a suíte inteira de novo sob
`TZ=Pacific/Kiritimati`.

## Como adicionar uma aula nova

1. Acrescente o objeto em `seed/lessons.json` seguindo o formato das outras
   (texto em Markdown, nunca HTML).
2. `make seed` — é idempotente, as aulas existentes não são tocadas.
3. Se o modelo mudou: `make migration m="o que mudou"`, confira o arquivo
   gerado, e `make migrate`.
4. Se a API mudou: `make openapi` e, no frontend, `npm run gen:api`. Os dois
   arquivos entram no mesmo commit que a mudança.

## Estrutura

```
backend/   app/{api,core,db,domain,schemas}  — FastAPI, uv, pytest
           alembic/                    — migrations
           openapi.json                — baseline do contrato
frontend/  src/api/                    — cliente tipado + schema GERADO
           src/components/             — Markdown, gramática, exercício
           src/features/               — jornada guiada, mídia, speaking e writing
           src/pages/                  — mapa, aula, estudo, revisão, prova
infra/     compose.yml                 — dev: db + api + web
           compose.prod.yml            — prod local: nginx + uvicorn + db
e2e/       testes/                     — Playwright, fluxo completo
seed/      lessons.json                — conteúdo das 10 aulas
```

## Convenções

- Trabalho em `sprint/N-slug`, entregue por PR com squash merge em `main`.
- *Conventional commits*.
- Toda migration precisa aplicar **e** reverter num banco limpo antes do merge.
- Teste que toca banco roda contra o Postgres do compose — mock de banco não
  conta como teste de integração.
- Tag `sN` a cada sprint fechada.

O plano completo das Sprints 6–14 está no roadmap do projeto.
