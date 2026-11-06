# Triagem de dependências e branches — Sprint 55

Consulta somente leitura ao GitHub em 05/11/2026. Base da main:
`012e54a8f0e02e0c63f88cc896563c134c9fd5b0`. Nenhum PR foi mesclado/fechado e
nenhuma branch foi removida. Check verde no head antigo não valida a composição
com as Sprints 50–55 ainda locais; atualizar a base e repetir o CI antes de merge.

## Doze PRs abertos do Dependabot

| PR | Mudança | Checks consultados | Decisão e ordem |
|---|---|---|---|
| [44](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/44) | Grupo backend, 8 atualizações | Sucesso | Prioridade 1: av 19.0.2 corrige double-free; revisar também mudanças de FastAPI em defaults de formulários e extras; repetir backend/E2E/segurança na base atual |
| [43](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/43) | Grupo frontend, 7 minor/patch | Sucesso | Prioridade 2: validar sessão, cache/PWA e router antes do merge |
| [27](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/27) | Grupo E2E, 2 atualizações | Sucesso | Prioridade 2: validar navegadores e guardas da stack isolada |
| [37](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/37) | buildx v3 → v4 | Sucesso | Prioridade 3: atualizar SHA e revisar runtime/permissões; não substituir pin por tag |
| [36](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/36) | codeql-action v3 → v4 | Sucesso | Prioridade 3: confirmar SARIF e permissão Security; preservar pin |
| [34](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/34) | upload-artifact v4 → v7 | Sucesso | Prioridade 3: validar artefatos, retenção e runtime; preservar pin |
| [38](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/38) | setup-node v4 → v7 | Recovery falhou | Investigar log e repetir recovery; não aprovar por checks parciais |
| [35](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/35) | setup-uv v5 → v7 | E2E cancelado | Reexecutar E2E completo; cancelado não é aprovação |
| [30](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/30) | Vitest 4.1.11 → 5.0.5 | Sucesso | Lote de tooling: conferir cobertura/ambiente e compatibilidade com Vite antes de combinar |
| [33](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/33) | Vite 6.4.4 → 8.3.5 | Frontend/E2E/recovery/segurança falharam | Tratar como migração com plugin React; validar build, PWA e orçamento de bundle |
| [31](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/31) | plugin-react 4.7 → 6.1.2 | Frontend/E2E/segurança falharam | Coordenar com Vite; resolver incompatibilidade antes do merge |
| [29](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/29) | ESLint 9.39.5 → 10.13 | Frontend/E2E/segurança falharam | Migrar configuração/plugins em lote próprio; não desabilitar lint |

Nesta sprint as Actions permanecem nas majors existentes, agora fixadas pelo
SHA do commit verificado. O Dependabot passa a acompanhar Docker em backend,
frontend e infraestrutura EasyPanel. As dependências da aplicação não foram
atualizadas em massa junto da mudança de deploy.

O scan local identificou `CVE-2026-111497` em `brotli-libs 1.2.0-r1` no nginx.
O Dockerfile instala explicitamente `1.2.1-r0`, versão corrigida indicada pelo
[Alpine Security Tracker](https://security.alpinelinux.org/vuln/CVE-2026-111497).
Não foi criada exceção para o achado; a imagem deve passar pelo scan novamente.

## Correção da imagem PostgreSQL em 06/11/2026

O scan da candidata PostgreSQL identificou `CVE-2025-68121` na biblioteca Go
1.24.6 embutida em `/usr/local/bin/gosu`. O [aviso oficial do Go](https://pkg.go.dev/vuln/GO-2026-4337)
descreve uma falha de retomada de sessões TLS e as versões corrigidas.
O achado de componente não comprova que esse caminho TLS é usado pelo gosu;
o gate CRITICAL continua bloqueando a imagem, sem exceção de scanner.

A imagem mantém PostgreSQL **16.15** e o digest da base. Instala
`su-exec=0.3-r0` do Alpine 3.24, já utilizado pelo backend, e substitui somente
as duas chamadas fixas para o usuário `postgres` nos helpers oficiais.
O build verifica as chamadas esperadas e o alias upstream antes de remover
o binário Go e redirecionar o alias para `/sbin/su-exec`.
O [código do su-exec 0.3](https://github.com/ncopa/su-exec/blob/v0.3/su-exec.c)
aplica usuário/grupos e executa diretamente o processo; o
[pacote Alpine](https://github.com/alpinelinux/aports/blob/3.24-stable/main/su-exec/APKBUILD)
fornece o executável usado pela imagem.

O CI agora constrói e varre também a imagem compartilhada por `db` e
`permissions`, exige seu relatório no mesmo gate de API/web e publica JSON/SARIF.
Essa correção da candidata não recria nem atualiza automaticamente o banco
produtivo: o controlador mantém a troca do serviço PostgreSQL separada do deploy
da aplicação.

Validação local em 06/11: Trivy 0.76.0 detectou zero vulnerabilidades na imagem
final Alpine 3.24.3. Dois laboratórios isolados comprovaram inicialização de
volume vazio e troca da imagem anterior para a candidata em volume existente:
PostgreSQL 16.15, UID/GID 70, migrations até `f61a1b8c9009`, aplicação de grants,
preservação de registro sentinela e hashes dos papéis/senhas. Reinício como
`postgres`, helpers `ensure`/`enforce` e encerramento limpo também passaram.
Nenhum banco produtivo participou desses testes.

## Branches antigas

As pontas consultadas pela API foram comparadas às referências locais de mesmo
SHA com `git merge-base --is-ancestor <head> origin/main`.

Oito branches têm o head integralmente ancestral da main: `sprint/6-experiencia-estudo`,
`sprint/15-validacao-acessibilidade`, `sprint/19-acabamento-operacional`,
`sprint/25-level-2-piloto`, `sprint/39-audio-tempo-ativo`,
`sprint/40-fechamento-dados-historico`, `sprint/43-implantacao-estudo`,
`sprint/46-operational-readiness`.
São candidatas à remoção após confirmar ausência de trabalho ativo e política
de retenção; não foram apagadas nesta execução.

Seis não são ancestrais: `fix/pwa-assets-between-deploys`,
`sprint/37-38-confiabilidade-estudo`, `sprint/44-producao-publica`,
`sprint/45-deploy-e-fundacao`, `sprint/46-assistente-backend` e
`sprint/49-frontend-quality`. Isso pode ocorrer por squash ou trabalho exclusivo;
revisar PRs e equivalência de patches antes de decidir. Data antiga por si só
não autoriza exclusão. As doze branches Dependabot permanecem ligadas aos PRs.
