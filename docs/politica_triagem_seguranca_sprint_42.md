# Sprint 42 — auditoria e triagem de segurança

Atualização: 16 de outubro de 2026. Esta política separa a descoberta
automática da decisão humana. Nenhum scanner aplica correção, aceita risco ou
interrompe uma release apenas por encontrar uma correspondência em uma base de
vulnerabilidades.

## Escopo e evidência

A CI gera, para cada commit:

- inventário `pip-audit` das dependências Python bloqueadas para produção;
- `npm audit --omit=dev` separado para frontend e testes E2E;
- imagens candidatas da API e do Nginx, sem publicação;
- relatórios JSON do Trivy para componentes da aplicação e do sistema
  operacional das duas imagens;
- artefato privado da execução, retido por 14 dias para triagem.

Os relatórios são inventário, não aprovação. A ação Trivy está fixada na
versão oficial `v0.36.0` e instala explicitamente o scanner `v0.76.0`, vigentes
na data desta decisão. As versões devem ser reavaliadas mensalmente, junto das
imagens-base e dos locks.

## Política de triagem

O release manager e o responsável técnico registram para cada achado novo:

1. identificador, pacote/camada, versão instalada e versão corrigida;
2. alcance no runtime real, exposição e controles compensatórios;
3. decisão: corrigir, mitigar, aceitar temporariamente ou falso positivo;
4. responsável, justificativa, prazo e evidência de reteste.

Prazos máximos iniciais:

| Severidade após analisar alcance | Prazo | Regra de release |
|---|---:|---|
| crítica explorável no runtime | 24 horas | bloqueia até corrigir/mitigar e retestar |
| alta explorável no runtime | 7 dias | bloqueia nova release sem decisão documentada |
| média | 30 dias | entra no backlog com responsável |
| baixa/unknown | próximo ciclo | revisar alcance; não ignorar automaticamente |

Aceite temporário nunca é permanente. Deve conter prazo, motivo, versão
afetada e condição de encerramento. Atualizações de dependência/imagem passam
pelas mesmas suítes funcionais, de migrations, recuperação e E2E da release.

## Estado da execução local

Em 16 de outubro de 2026:

- frontend: `npm audit --omit=dev` encontrou zero vulnerabilidades;
- E2E: `npm audit --omit=dev` encontrou zero vulnerabilidades;
- backend: `pip-audit` sobre o lock exportado de produção encontrou zero
  vulnerabilidades conhecidas;
- o Docker Scout foi autorizado, mas não executou sem autenticação no serviço;
  nenhuma credencial foi solicitada ou reaproveitada;
- a alternativa local exportou as imagens para arquivos temporários e executou
  Trivy `v0.76.0` sem montar o socket Docker no scanner;
- o primeiro scan rejeitou a imagem web antiga: Nginx 1.27/Alpine 3.21 tinha 2
  ocorrências críticas e 41 altas, todas corrigíveis;
- a imagem API Debian tinha zero críticas e 44 ocorrências altas correspondentes
  a 8 CVEs do sistema sem correção publicada. Ela foi substituída, não aceita
  por exceção;
- a candidata web passou a usar Nginx `1.30.6-alpine3.24`; a API passou a usar
  Python `3.12.15-alpine3.24`, `su-exec` e UID/GID 10001;
- o reteste final encontrou **zero críticas e zero altas nas duas imagens**;
- o smoke da API confirmou UID 10001, bibliotecas nativas e `/api/health` com
  schema compatível contra PostgreSQL descartável;
- o smoke web confirmou inicialização do Nginx e entrega do bundle quando o
  hostname interno `api` esperado pelo Compose está presente;
- a primeira execução do workflow atualizado ainda deve repetir e publicar o
  inventário privado do commit candidato. O aceite local não substitui a CI.

Falha do scanner, base desatualizada ou relatório ausente aparece como pendência
na matriz de release. Isso não vira aprovação silenciosa nem tentativa de usar
outro serviço externo sem autorização.

## Reteste de 26 de outubro de 2026 (SEC-45)

O aceite de 16/10 registrou **zero críticas e zero altas nas duas imagens**. O
reteste com o mesmo Trivy `v0.76.0`, dez dias depois, encontra três altas na
imagem web — nenhuma delas introduzida por mudança nossa: as mesmas três
aparecem na imagem construída a partir da `main`. É o efeito esperado de base
fixada por digest contra um banco de CVEs que avança.

Imagem da API (`python:3.12.15-alpine3.24`): **zero críticas e zero altas**,
sem mudança.

Primeiro a correção que estava disponível: o upstream republicou o tag
`nginx:1.30.6-alpine3.24` sobre o Alpine 3.24.3, com digest novo. Como
`ops/ci_pull_bases.sh` pré-carrega as bases **por digest**, o tag sozinho não
traria os pacotes corrigidos; re-ancorar o digest (`sha256:970364…` →
`sha256:47928b…`, idêntico nas duas origens) baixou as altas de cinco para
três, encerrando:

| Identificador | Pacote | Instalada | Corrigida | Estado |
|---|---|---|---|---|
| CVE-2026-77214 | `libexpat` | 2.8.5-r0 | 2.9.0-r0 | corrigida pela re-âncora |
| CVE-2026-88806 | `libx11` | 1.8.13-r0 | 1.8.14-r0 | corrigida pela re-âncora |

### Achados em aberto, para decisão humana

| Identificador | Pacote/camada | Instalada | Corrigida | Alcance no runtime real | Controles compensatórios | Decisão proposta |
|---|---|---|---|---|---|---|
| CVE-2026-111497 | `brotli-libs` (SO da imagem web) | 1.2.0-r1 | 1.2.1-r0 | **nenhum caminho de execução**: `frontend/nginx.conf` comprime com `gzip`; o módulo brotli não é carregado nem referenciado | borda sem upload para o nginx (o corpo vai à API); `cap_drop: [ALL]` e FS read-only no container web | aceitar temporariamente até o upstream publicar imagem com 1.2.1-r0 |
| CVE-2026-92392 | `curl` e `libcurl` (SO da imagem web) | 8.22.0-r0 | 8.23.0-r0 | o nginx não invoca `curl`; o binário vem como dependência da imagem e nenhuma rota o executa | idem; nada no container parte de entrada do usuário para um processo externo | aceitar temporariamente até o upstream publicar imagem com 8.23.0-r0 |

Condição de encerramento, não prazo em aberto: **nenhuma imagem nginx alpine3.24
publicada hoje contém essas correções** — a mais recente (`1.30-alpine3.24`,
mesmo digest que a re-ancorada) ainda traz `brotli-libs-1.2.0-r1` e
`curl-8.22.0-r0`, conferido em 26/10/2026. A alternativa seria `apk upgrade` no
estágio de runtime, recusada aqui porque trocaria reprodutibilidade por
atualidade sem o digest dizer o que mudou — e o hadolint do job `infra-lint`
reprova (DL3017). A re-âncora do digest deve ser reconferida junto das imagens-base
na revisão mensal que esta política já prevê; é ela que encerra os dois achados.

### Decisão (item 3 da política)

**Aceite temporário dos dois achados, por Jeferson Papalino, em 26/10/2026.**

| Campo exigido pela política | Registro |
|---|---|
| Decisão | aceitar temporariamente CVE-2026-111497 (`brotli-libs`) e CVE-2026-92392 (`curl`/`libcurl`) na imagem web |
| Responsável | Jeferson Papalino, acumulando release manager e responsável técnico |
| Justificativa | nenhum dos dois tem caminho de execução no runtime: a borda comprime com `gzip` e não carrega o módulo brotli; o nginx não invoca `curl`, que entra como dependência da imagem-base. Some-se o container web com `cap_drop: [ALL]`, FS read-only e `no-new-privileges` (SEC-45) |
| Condição de encerramento | publicação de imagem `nginx:*-alpine3.24` com `brotli-libs ≥ 1.2.1-r0` e `curl ≥ 8.23.0-r0`. Em 26/10/2026 **nenhuma existe**: a mais recente ainda traz 1.2.0-r1 e 8.22.0-r0 |
| Prazo | reconferir na revisão mensal que esta política já prevê, junto das imagens-base e dos locks; a próxima re-âncora de digest em `ops/ci_pull_bases.sh` é o gatilho natural |
| Evidência de reteste | Trivy v0.76.0 local, imagem web construída do SEC-45: 5 altas antes da re-âncora do digest, 3 depois; imagem da API em zero críticas e zero altas |

Não é aceite permanente nem silencioso: a condição de encerramento é objetiva e
não depende de alguém lembrar — ela aparece na primeira reconferência de digest
que encontrar os pacotes corrigidos.
