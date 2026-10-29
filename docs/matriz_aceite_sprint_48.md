# Matriz de aceite — piloto de conversa da Sprint 48

Preparação em 29/10/2026, após publicação do PR #41 (`9cc14fe`).
**Estado: piloto não iniciado; assistência permanece desligada.**
Esta matriz registra evidências e decisões; não substitui o manifesto privado
nem constitui autorização de envio de dados ao provedor.

## Pré-requisitos para iniciar o piloto

| Item | Estado e evidência | Próxima ação |
|---|---|---|
| Código e ensaios | PR #41 integrado; CI/deploy aprovados; upgrade e SEC-49 aprovados | Preservar vínculo entre release e evidências |
| Provedor/modelos | Decisão de 21/10 no [ADR](adr_assistente_de_conversa.md): Cloudflare Workers AI, `llama-3.1-8b-instruct` e `whisper-tiny-en`; atualização 29/10 para Llama 3.3 70B fp8 fast, compatível com schema | Modelos atuais verificados em ensaio sintético; aceite pedagógico depende de turnos reais |
| Gateway e credencial | Adaptador HTTPS Workers AI implementado; conversa e STT sintéticas passaram; credencial preparada na VM em arquivo privado 0600 após autorização expressa | Publicar código, aplicar configuração com flags desligadas, validar e só então ativar após aceite |
| Revisão SEC-46 | Revisão técnica concluída no [modelo de ameaças](modelo_ameacas_assistente_2026-10-26.md); fluxo corrigido para explicitar áudio bruto | Aceite informado do responsável solicitado em conversa |
| Contrato e privacidade | Sem manifesto real validado | Registrar contrato, base legal, região/subprocessadores, retenção e não treinamento com evidências do provedor escolhido |
| Orçamento | Responsável informou uso do plano gratuito em 29/10; limite adotado de gasto autorizado: USD 0/dia, USD 0/mês e USD 0 no piloto | Confirmar modalidade Workers AI da conta e monitorar franquia; não habilitar cobrança |
| Participante | Uma única conta correspondente ao responsável identificada na VM; ID somente na configuração privada | Aplicar lista à API e worker após publicação |
| Restrição por conta | Lista cobre conversa, STT compartilhada e escrita; despacho revalida antes de consumo/rede | Publicar e configurar a mesma lista privada na API e worker |
| Isolamento de STT compartilhada | Implementado e testado: admissão/status/fila/dispatch respeitam a lista | Manter escrita sem URL e uma tentativa por job no piloto Cloudflare |
| Vigilância pública | Probe executado com sucesso no run 40932540081; schedule existente a cada 30 minutos | Acompanhar execuções agendadas; não inferir entrega de notificação |
| Métricas e alerta | Leitura pontual antes da definição gratuita: 14 checks `ok`, dois avisos de orçamento; gate GitHub ignorado sem secret | Publicar suporte a teto zero, preparar agendamento autenticado/canal de alerta e provar detecção do worker em 2 minutos |

O inventário da VM verificou root e crontabs de sistema, sem encontrar entrada
reconhecida do monitor; `sendmail` ausente. Não houve inventário de outros
agendadores. API e worker tinham ambas as flags desligadas, sem URL de diálogo
ou token do provedor. Nenhuma configuração de assistência foi alterada.

O token operacional existe na VM, mas não foi transferido ao GitHub. Ativar o
probe público não ativa o gate autenticado nem o alerta de custo. O snapshot
pontual com avisos de orçamento não comprova monitoramento contínuo.

## Restrição por conta — implementação local de 29/10

`DIALOGUE_PILOT_USER_IDS` recebe uma lista JSON de IDs internos positivos.
Em `APP_ENV=prod` ou `DEPLOYMENT_PROFILE=public`, lista vazia bloqueia todos
os diálogos assistidos. Dev/test locais permitem ensaios com lista vazia;
quando preenchida, a lista restringe qualquer ambiente. No EasyPanel,
`EASYPANEL_DIALOGUE_PILOT_USER_IDS` alimenta API e worker pelo mesmo bloco.
Identificadores reais ficam somente na configuração privada.

Contas excluídas não podem criar Guiado/Livre nem enviar novos turnos de
texto/áudio em conversas existentes. Áudio é recusado antes de armazenamento.
Roteiro, consulta, exportação e exclusão continuam disponíveis ao titular.
A lista agora protege **todas as modalidades assistidas**, incluindo STT
compartilhada e escrita. Escrita não é suportada pelo adaptador Cloudflare deste
piloto e sua URL permanece vazia. A lista não impede salvar/baixar áudio próprio
sem transcrição nem usar o feedback determinístico de escrita.

Jobs de contas excluídas permanecem na fila sem consumir tentativas ou cota,
até expiração/limpeza normal; não impedem o processamento de contas permitidas.
Se a autorização mudar após a reivindicação, o despacho falha com
`assist_disabled` antes de STT e libera apenas reservas ainda não consumidas.
A chamada de diálogo também verifica a lista antes de usar o provedor.

Configuração é carregada por processo: aplicar/revogar exige atualizar e
reiniciar API e worker, mantendo assistência desligada durante a transição.
Uma requisição externa já enviada não pode ser desfeita pela lista.
A conta real já foi vinculada ao arquivo candidato privado na VM. O ambiente
ativo não foi alterado; publicação e aceite ainda antecedem a ativação.

Validação da etapa anterior (`1c9ea6a`): **1.399 testes backend aprovados**, incluindo 18 novos casos,
com **94,31% de cobertura**; **345 testes operacionais** aprovados. Ruff,
mypy (106 módulos backend e 40 operacionais), ESLint e TypeScript sem erros.
Composes de produção/EasyPanel conferidos com lista vazia e lista explícita
iguais na API e no worker. Baseline OpenAPI preservado. Provedores simulados,
sem envio real de áudio/texto e sem alteração em produção.

## Manifesto privado e separação dos dois momentos de aceite

### Decisão: somente plano gratuito

O responsável informou em conversa: “estou utlizando plano gratuito”. Isso
foi incorporado como restrição de **nenhum gasto autorizado**, sem assinar
automaticamente a revisão SEC-46 nem habilitar assistência ou cobrança.
A modalidade efetiva da conta ainda não foi conferida no painel Cloudflare.

Conforme a [documentação oficial consultada em 29/10/2026](https://developers.cloudflare.com/workers-ai/platform/pricing/),
Workers AI oferece 10.000 Neurons/dia; no Workers Free, operações excedentes
falham, e os limites reiniciam às 00:00 UTC. Alguns modelos exigem modalidade
paga/créditos: a compatibilidade do modelo com a conta faz parte da preparação.
Não comprar créditos nem migrar de plano como tratamento automático de falha.

Franquia usada não equivale a cobrança. No gateway genérico, custo ausente permanece desconhecido. No adaptador
Workers AI, zero é conhecido somente com a confirmação operacional explícita
`ASSIST_CLOUDFLARE_FREE_PLAN_CONFIRMED`; sem ela, o boot assistido é recusado.
Essa confirmação depende do responsável pela conta e deve ser revogada se
houver mudança de plano; não equivale a conciliação automática de fatura. O consumo da conta pode incluir
outros aplicativos, portanto a cota de 24 turnos não substitui a franquia.

O monitor local agora aceita teto `0`: custo confirmado zero fica `ok`, custo
positivo ou desconhecido fica crítico. O alerta não bloqueia sozinho novas
chamadas; a modalidade gratuita no provedor e a contenção da aplicação são
controles separados. Orçamento ausente continua sendo aviso, e tetos positivos
mantêm os limiares anteriores. Publicação desse ajuste e agendamento autenticado
ainda pendentes; não aplicar `0` ao binário antigo, que o recusa.

### Preparação do manifesto

Usar `config/assist-provider-review.example.json` como modelo, com
`modality=conversation`, e manter o arquivo real em
`config/assist-provider-review.json`, ignorado pelo Git. `provider_name` deve
coincidir com a configuração da aplicação. O nome comercial do fornecedor e
as evidências contratuais devem ser registrados na revisão, sem credenciais.

A cópia privada local foi preparada com `budget_microusd=0`, permissão `0600`
e os demais aceites ainda não aprovados. Não foi instalada na VM e não autoriza
o piloto por si só.

Preencher os campos somente com decisões e medições reais; valores `false`
ou `null` não devem ser alterados apenas para o gate passar. A escolha histórica
do fornecedor não substitui a revisão das condições aplicáveis à conta.

O **aceite para iniciar o piloto** exige pré-requisitos, revisão responsável,
restrição de participantes e orçamento. O **aceite para ampliar o uso** depende
das avaliações abaixo. Exigir 30 avaliações antes de iniciar o piloto seria
circular; ignorá-las para ampliar o uso também não atende ao plano.

## Evidências durante e após o piloto

| Critério | Evidência necessária | Estado |
|---|---|---|
| Avaliações | Pelo menos 30 turnos avaliados em cinco aulas distintas | Pendente |
| Utilidade | Pelo menos 80% dos turnos avaliados considerados úteis | Pendente |
| Falha técnica | Menos de 5% entre turnos terminais | Pendente |
| Custo | Custos confirmados, sem turnos com custo desconhecido e dentro do orçamento | Pendente |
| Revisão pedagógica | Prompts e dez diálogos reais revisados; tema, vocabulário e feedback adequados, sem nota de fluência/pronúncia | Pendente |
| Acessibilidade | VoiceOver em macOS e iOS; responsável, data, problemas e reteste registrados | Pendente |
| Privacidade | Amostragem controlada de logs de API/worker e evidência de ausência de texto/token; registrar apenas resultado agregado | Pendente |
| Incidente real | Procedimento validado no ambiente escolhido; ensaios sintéticos SEC-48/49 já existem | Pendente de aceite operacional |
| Banco DB-46 | Comparação das 39 tabelas históricas e exclusão de conta sintética com cascatas; nunca usar a conta real como fixture | Pendente de evidência específica |
| Recuperação INFRA-48 | Recibo de restauração do pacote público com tabelas de conversa e leitura pela aplicação; vincular evidência existente quando suficiente | Pendente de reconciliação do aceite |
| Gate final | `assist-gate modality=conversation` com manifesto real, métricas e release identificados | Pendente |

Na raiz do repositório, o comando existente para o gate é:

```bash
make assist-gate modality=conversation review=../config/assist-provider-review.json
```

Executá-lo somente no ambiente operacional previamente identificado. Um
comando no Mac não comprova métricas de produção. Não copiar textos, gravações,
credenciais ou avaliações identificáveis para documentos públicos. As provas
publicáveis são contagens, resultados agregados e referências aos recibos.

## Decisão do responsável

| Campo | Registro |
|---|---|
| Responsável | Jeferson Papalino |
| Data da revisão SEC-46 | Pendente |
| Decisão para iniciar piloto restrito | Pendente |
| Orçamento diário / mensal / total do piloto | USD 0 / USD 0 / USD 0; plano gratuito informado em 29/10/2026; sem autorização de cobrança |
| Data da avaliação final | Pendente |
| Decisão final | Pendente: ampliar Guiado / manter somente Roteiro / desligar |
| Condições e correções exigidas | Pendente |
| Referências dos recibos | Pendente |

Não há assinatura ou aprovação implícita nesta matriz. O modo Livre só entra
em pauta depois do aceite do Guiado, conforme o plano.
