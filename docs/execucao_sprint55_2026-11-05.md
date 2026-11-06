# Sprint 55 — deploy seguro e cadeia de suprimentos

Implementação e validação local em 05/11/2026. Próxima implementação por
prioridade: **Sprint 56 — migrations, grants e integridade**. O aceite
operacional da 55 depende de instalação e ensaio na VM.

## Entregas

- **INF-02 / OPS-04:** cliente SSH envia somente SHA completo ou rollback;
  comando forçado valida novamente a main no servidor. Host explícito sem
  root, wrapper instalado fora do checkout, configuração root-owned, modelos
  de `authorized_keys` e instruções de instalação/revisores. Backup também
  deixa de usar destino root/IP embutido.
- **OPS-05 / OPS-06 / OPS-15:** imagens anteriores preservadas por ID e tag;
  build, Trivy e pré-voo de volume antes de parar worker/migrar. Lock não
  bloqueante, timeout total e limites por subprocesso. Recibos current,
  previous e pending tornam falhas visíveis. Rollback prova compatibilidade
  numa API temporária e reativa as imagens sem build, migration ou seed.
- **INF-05 / INF-07:** bases de produção e uv fixados por digest; Actions
  fixadas em SHAs verificados, preservando as majors existentes. Scripts de
  entrada nas imagens são normalizados para LF durante o build.
- **INF-06:** infra-lint e segurança passam a bloquear deploy. Relatórios
  Trivy ausentes/inválidos ou CRITICAL falham; SARIF e inventários auxiliares
  continuam disponíveis para triagem. O servidor repete o scan das imagens
  que efetivamente constrói, antes de alterar a aplicação.
- **INF-08:** ecossistema Docker no Dependabot e triagem dos 12 PRs abertos,
  com checks consultados e sequência proposta; sem merge automático.
- **INF-14 a INF-17:** nginx com UID/GID 101, zero capabilities e tmpfs
  próprios; exclusão de segredos/dados locais dos contextos Docker; ambiente
  da stack de desenvolvimento fixado como dev/local; revisão das 14 branches
  antigas, oito ancestrais da main e seis que exigem análise adicional.

Consultar o [runbook](deploy_seguro_2026-11-05.md) e a
[triagem de dependências/branches](triagem_dependencias_sprint55_2026-11-05.md).

## Evidências

- Builds de produção de API e frontend aprovados, incluindo TypeScript/Vite.
  O build mantém o aviso preexistente de chunk circular lesson-study/writing.
- Suíte operacional Linux: **378 testes descobertos, 371 aprovados e 7
  opcionais ignorados**. A cópia temporária usou scripts LF, como o checkout
  Linux. A suíte inclui build/scan recusados antes da interrupção, migration
  com falha preservando pending, rollback incompatível, concorrência do lock,
  arquivo inseguro, protocolo SSH e sanitização de erros.
- Ensaio opt-in com Docker/Compose reais: stack
  `aulas-dr-deploy55-6a05c62a1d1d`, API sintética e nginx de produção. Rollback
  em **8,773 s**, IDs anteriores confirmados, volume preservado, nginx
  UID 101 e `CapEff=0`. Recursos UUID removidos no finally. Esse teste também
  integra o job E2E usando as imagens descartáveis existentes.
- Ruff aprovado e mypy estrito em **50 módulos operacionais**. Shellcheck,
  hadolint e actionlint aprovados. Os quatro arquivos Compose foram validados
  com configuração sintética, sem iniciar stack de estudo.
- Trivy 0.76.0 nas imagens reais encontrou inicialmente uma CRITICAL:
  `brotli-libs 1.2.0-r1` no nginx. O gate recusou a imagem. Atualização fixa
  para `1.2.1-r0`, rebuild e novo scan resultaram em **zero CRITICAL** nas
  duas imagens. Persistem inventários não críticos: API 1 HIGH/5 MEDIUM/1 LOW;
  web 5 HIGH/2 MEDIUM/44 LOW/1 UNKNOWN. Isso não é declaração de ausência de
  vulnerabilidades; os achados seguem triagem e o gate atual é CRITICAL.
- A primeira tentativa de ensaio revelou CRLF no entrypoint antigo de assets;
  a normalização no build corrigiu a inicialização. Falhas ficaram restritas
  ao laboratório, antes da aplicação no projeto original.

## Pendências e limites

Não houve commit, push, merge, deploy, alteração em banco de estudo/produção,
instalação de usuário/chave/sshd, configuração de GitHub ou remoção de branches.
A pipeline remota e o Playwright completo não foram executados nesta sprint.

Required reviewers não são criados pelo YAML; configurar e demonstrar a
aprovação no environment `production`. A main consultada estava sem proteção.
Migrar o proprietário do volume antigo de assets antes de ativar nginx UID 101.
Não usar a chave restrita de deploy para o fluxo de backup remoto.

O laboratório mede orquestração local com resposta de saúde sintética, sem
banco real. Ainda é necessário ensaiar deploy com usuário/SSH restritos,
migration/seed reais, compatibilidade do schema, tráfego HTTPS e rollback na VM.
Build antecipado reduz a janela, mas não elimina 503 durante mudança de schema.
Rollback não reverte schema, segredos ou override do painel; schema incompatível
exige recuperação/correção conforme o runbook, sem downgrade automático.
