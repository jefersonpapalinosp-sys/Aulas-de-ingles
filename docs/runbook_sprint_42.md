# Sprint 42 — operação, incidentes e release seguro

Atualização: 16 de outubro de 2026. Este documento descreve o mecanismo já
implementado e separa evidência automática de homologação humana. Não autoriza
uma manutenção nem declara HTTPS público, RPO ou RTO aprovados.

## Estado e responsáveis

| Área | Responsável operacional | Evidência atual |
|---|---|---|
| decisão de liberar/reverter aplicação | release manager | readiness + checklist deste documento |
| API e taxa de erro | backend on-call | `/api/operations/metrics` |
| fila/provedor/heartbeat | worker on-call | métricas agregadas e `job_id` opaco nos logs |
| schema, locks, restore | database operator | readiness, Alembic, recibo de restore |
| arquivos de voz/capacidade | storage operator | contagem/bytes agregados e inventário do backup |
| exclusão de conta | privacy owner | recibo anônimo e contadores do worker |
| conteúdo e exemplos | responsável pedagógico | homologação humana ainda pendente |
| leitores de tela/dispositivos | responsável por acessibilidade | homologação física ainda pendente |

No ambiente pessoal atual, Jeferson acumula os papéis operacionais. Os nomes de
papel permanecem no relatório para uma futura equipe não depender de uma pessoa.

## Contratos de saúde

- `GET /api/live`: somente processo vivo; nunca consulta dependências.
- `GET /api/health`: banco acessível **e** conjunto de revisões da tabela
  `alembic_version` exatamente igual aos heads embarcados na imagem.
- banco fora: HTTP 503, `db=down`, `schema=unknown`;
- banco acessível com migration ausente, excedente, ilegível ou sem permissão:
  HTTP 503, `db=up`, `schema=incompatible`;
- Compose usa `/api/health` para considerar a API saudável. O frontend de
  produção depende dessa saúde e não é liberado apenas porque `/live` responde.

O endpoint informa somente versões operacionais. Não inclui DSN, SQL, parâmetros,
usuários ou conteúdo. Readiness incompatível não é autorização para downgrade.

## Métricas e gate

`GET /api/operations/metrics` fica oculto com 404 enquanto `OPERATIONS_TOKEN`
estiver vazio. Quando habilitado, exige `Authorization: Bearer ...`; o token deve
ter ao menos 32 bytes e nunca entra no Git, linha de comando, URL ou log.

O snapshot tem cardinalidade fixa:

- requests/5xx, soma/máximo e buckets de latência por processo;
- tamanho, conexões, locks aguardando e estado do pool;
- fila, processando, falhas, retries, expirados, idade da fila e heartbeat;
- exclusões pendentes/falhas;
- arquivos/bytes referenciados e capacidade livre do filesystem de voz.

Não há rota, e-mail, texto, transcrição, chave de storage, áudio ou token nas
métricas. Em uma API com múltiplos workers, contadores HTTP têm `scope=process`;
banco/fila/storage continuam agregados. Um coletor futuro deve consultar cada
processo ou substituir os contadores locais antes de prometer visão global.

Executar o gate sem imprimir a credencial:

```bash
export OPERATIONS_TOKEN='valor-local-com-32-bytes-ou-mais'
export OPERATIONS_BASE_URL='http://127.0.0.1:8011'
make operations-check
```

Limites iniciais, operacionais a validar:

| Sinal | Limiar | Ação |
|---|---:|---|
| schema | exatamente `compatible` | manter tráfego bloqueado; alinhar imagem/migration |
| HTTP 5xx | até 5% após 20 requests | correlacionar request-id e considerar rollback só da aplicação |
| job mais antigo | até 300 s | conferir worker/provedor sem reenviar manualmente |
| heartbeat | até 60 s | reiniciar worker; a fila durável retoma jobs |
| locks aguardando | zero | pausar deploy e identificar bloqueio sem registrar SQL |
| exclusões falhas | zero | preservar recibo anônimo e reprocessar pelo worker |
| `review_card` sem vínculo ou divergente | zero | manter legado e reconciliar somente no clone |
| espaço livre de voz | ao menos 1 GiB | bloquear upload e ampliar/limpar somente por política |

Cada alerta emitido inclui nome, observado, limiar, ação e responsável. Alterar
limiares exige teste e registro; não silenciar um alerta apenas para liberar release.

## Correlação segura

A linha `transcription_queued` herda o `request_id` da API e registra apenas o
`job_id`. O worker usa o mesmo `job_id` em `transcription_claimed`,
`transcription_failed` e `transcription_completed`, com número da tentativa e
código de erro controlado. Assim, o caminho é:

```text
request_id da API -> job_id opaco -> tentativa do worker
```

Não registrar corpo, texto esperado, transcrição, nome de arquivo, e-mail,
Authorization, cookie, DSN ou resposta bruta do provedor.

## Checklist obrigatório de release

`make prod-up` e `make prod-seed` estão bloqueados: os fluxos antigos podiam
iniciar código novo antes de atualizar o banco e aplicar seed editorial amplo.

1. Confirmar branch/commit, worktree limpo e imagem anterior identificada.
2. Registrar defeitos, riscos aceitos e homologações humanas separadamente.
3. Rodar CI em banco/voz descartáveis: lint, tipagem, contratos, concorrência,
   migrations, frontend, E2E, recovery e papéis.
4. Construir imagens antes da manutenção; não trocar containers ainda.
5. Abrir manutenção autorizada e parar web/API/worker. Não parar nem apagar o banco.
6. Criar pacote conjunto de banco + voz; executar `backup-verify`.
7. Restaurar em destino novo, vazio, interno e explicitamente confirmado.
8. No clone, ensaiar a migration a partir da revisão realmente capturada; medir
   duração/locks e conferir hashes/contagens/voz/permissões/leitura pela aplicação.
9. Se o ensaio falhar, manter origem e imagens anteriores; não “corrigir” o
   pacote nem executar SQL manual sem novo plano.
10. Aplicar migration com `aulas_migrator`, nunca com runtime/worker.
11. Executar `seed --dry-run`. Qualquer diff editorial exige plano/homologação
    próprio; não usar o seed completo genérico para contornar o bloqueio.
12. Confirmar `alembic current`, `alembic check`, grants e auditorias da release.
13. Subir API/worker novos ainda sem liberar web; exigir `/api/health` 200.
14. Executar `make operations-check`, smoke autenticado e teste de acesso aos
    áudios autorizados. Falha mantém tráfego fechado.
15. Subir/liberar web somente após os gates; conferir hash/release servido.
16. Criar backup pós-migration e registrar tempos, IDs das imagens e pendências.

Depois de migration aditiva, o retorno preferencial é a imagem anterior que seja
compatível com o schema expandido. Restore é recuperação em destino isolado, não
atalho para sobrescrever a origem. Downgrade destrutivo não é rollback padrão.

## Decisão sobre `review_card`

`review_card` permanece no schema durante toda a linha de exportação 2.x. O
runtime atual cria e consulta somente `review_item`; a tabela legada ainda é
necessária para preservar o histórico exportável, a FK `legacy_card_id` e a
janela de rollback. Não há migration de remoção autorizada na Sprint 42.

O endpoint operacional conta cartões sem `review_item` correspondente e vínculos
com usuário/vocabulário divergentes; qualquer ocorrência bloqueia o gate. Uma
retirada só pode ser reconsiderada numa versão maior do formato de exportação,
depois de: zero divergências no banco e num restore separado, ausência de imagem
suportada que consuma a tabela, snapshot histórico equivalente, backup verificado
e nova homologação de rollback. Até lá, backup/restore inclui as duas tabelas e
nenhum dado legado é apagado.

## Incidentes

### Banco indisponível

Manter a aplicação em readiness 503 e preservar filas/rascunhos. Confirmar
container, volume e conectividade sem imprimir DSN. Não apontar para outro banco
por fallback. Após retorno, conferir schema antes de liberar tráfego.

### Schema incompatível

Manter web bloqueado. Comparar `schema_current` e `schema_required`, imagem e
recibo da migration. Se a migration não começou, retomar imagem anterior. Se foi
aplicada, concluir verificação ou usar rollback de aplicação compatível; não
executar downgrade/refazer restore sobre a origem.

### Provedor assistido indisponível

Correção objetiva/local e autoavaliação devem continuar funcionando. O worker usa
retry limitado e idempotência. Não reenviar em massa. Se fila/heartbeat excederem
limiar, pausar assistência, preservar jobs e investigar por `job_id`.

### Worker reiniciado

Jobs `processing` antigos voltam à fila pelo timeout e `SKIP LOCKED`; retries têm
limite. Confirmar heartbeat e contadores depois do reinício. Não alterar status à mão.

### Capacidade de voz baixa

Bloquear novas gravações antes de encher o volume. Verificar arquivos referenciados,
quarentena, exclusões pendentes e backup. Nunca remover por `find`/idade sem reconciliar
com o banco e a política de retenção.

## Segurança HTTP

O Nginx aplica CSP, bloqueio de framing, `nosniff`, `no-referrer`, política de
permissões e COOP. A CSP permite somente bundle local, estilos React por atributo,
`blob:` para gravações e os hosts oficiais de mídia VOA. Não força
`upgrade-insecure-requests` no localhost HTTP.

O perfil público da API exige `PUBLIC_ORIGIN=https://...`, cookie seguro e HTTPS,
e adiciona HSTS. **HTTPS público completo continua não homologado** enquanto não
houver proxy/certificado real e teste da página estática + API nesse ambiente.

## Auditoria de dependências e imagens

A CI produz inventários JSON de `pip-audit`, `npm audit` e Trivy e os conserva
por 14 dias. O scanner não corrige automaticamente nem falha a release por uma
correspondência ainda não analisada; a decisão de release consulta a triagem e
seus prazos. Consulte `politica_triagem_seguranca_sprint_42.md`.

Na execução local de 16/10/2026, os três inventários de dependências retornaram
zero vulnerabilidades conhecidas. O Docker Scout não prosseguiu sem login; a
triagem seguiu com Trivy `v0.76.0` sobre arquivos temporários das imagens, sem
socket Docker montado. A base web antiga foi rejeitada após 2 ocorrências
críticas e 41 altas; a base Debian da API foi substituída após 44 ocorrências
altas sem correção. As candidatas finais, Nginx `1.30.6-alpine3.24` e Python
`3.12.15-alpine3.24`, ficaram com zero críticas/altas. A API também respondeu
`/api/health` como UID 10001 contra o banco descartável, e a web entregou o
bundle pelo Nginx com o DNS interno esperado. A CI deve repetir a varredura e
conservar o artefato do commit candidato.

## Ensaio controlado de falhas

`make test-failure-rehearsal` usa somente o banco marcado como descartável.
Ele cobre falha transitória de acesso ao banco, provedor de escrita/transcrição,
retry idempotente e retomada de job abandonado por um worker interrompido. A
rodada de 16/10/2026 aprovou 5 de 5 cenários. Esse teste não toca o banco de
estudo e não substitui um exercício futuro de indisponibilidade física.

## Pendências que impedem o aceite integral

- medir o RTO operacional completo e comprovar a rotina/cadência do RPO de 24 h;
- confirmar na CI o inventário Trivy já aprovado localmente para as candidatas;
- conferência auditiva, pedagógica, leitores de tela e dispositivos reais;
- HTTPS público com certificado/proxy reais.

Esses itens devem aparecer individualmente na matriz final. O pacote inteiro não
recebe “aprovado” enquanto algum aceite obrigatório estiver aberto.
