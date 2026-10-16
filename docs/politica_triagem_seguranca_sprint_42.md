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
