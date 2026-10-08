# Homologação da assistência opcional por IA

Data: 8 de outubro de 2026  
Backlog: item 3 da fila de fechamento

## Situação atual

O produto está tecnicamente preparado para um piloto controlado, mas não está autorizado a
enviar dados reais a um provedor. As feature flags continuam desligadas porque faltam decisões
externas que não podem ser presumidas pelo código:

- fornecedor e endpoints dos gateways de escrita e transcrição;
- contrato de tratamento de dados e base legal;
- região de processamento e subprocessadores;
- retenção no fornecedor e garantia de não usar os dados para treinamento;
- orçamento do piloto;
- participantes e consentimento para gerar 30 avaliações humanas por modalidade;
- revisão humana de segurança e compreensão do aviso de automação.

Nenhum token deve ser registrado no manifesto ou no Git. Credenciais continuam restritas às
variáveis de ambiente.

## Manifesto de homologação

Copie o modelo e mantenha a cópia real somente no ambiente operacional:

```bash
cp config/assist-provider-review.example.json config/assist-provider-review.json
```

O arquivo real é ignorado pelo Git. Seus campos registram somente decisões e números:

| Campo | Condição para aprovação |
|---|---|
| `provider_name` | igual a `ASSIST_PROVIDER_NAME` |
| `data_processing_agreement` | contrato aprovado |
| `legal_basis_approved` | base legal aprovada |
| `region_approved` | região e subprocessadores aprovados |
| `provider_retention_days` | definido e não maior que `ASSIST_RETENTION_DAYS` |
| `provider_uses_data_for_training` | obrigatoriamente `false` |
| `privacy_incidents` | obrigatoriamente `0` |
| `budget_microusd` | definido e maior ou igual ao custo agregado |
| `safety_review_approved` | revisão manual concluída |
| `automation_notice_understood` | participantes compreenderam automação e baixa confiança |

## Execução do gate

Execute separadamente porque qualidade de escrita não autoriza transcrição, nem o inverso:

```bash
make assist-gate modality=writing review=../config/assist-provider-review.json
make assist-gate modality=transcription review=../config/assist-provider-review.json
```

O relatório JSON apresenta:

- total de solicitações, sucessos, falhas e resultados avaliados;
- quantidade marcada como útil;
- taxa de utilidade e taxa de falha técnica;
- custo agregado em microunidades de dólar;
- cada critério como `true` ou `false`;
- lista explícita dos bloqueios restantes.

Os limiares são os definidos na Sprint 14: pelo menos 30 avaliações, utilidade mínima de 80% e
falha técnica inferior a 5%. O gate também exige privacidade, orçamento, revisão de segurança e
compreensão da automação.

Saídas do processo:

- código `0`: modalidade aprovada, ainda sem alterar feature flag;
- código `1`: gate válido, mas requisitos pendentes;
- código `2`: manifesto ou argumentos inválidos.

## Sequência segura para o piloto

1. Escolher o fornecedor sem inserir credenciais no repositório.
2. Concluir avaliação jurídica e de privacidade.
3. Definir orçamento, cota, retenção e grupo pequeno de participantes.
4. Configurar somente o ambiente do piloto e ativar uma modalidade por vez.
5. Coletar no mínimo 30 avaliações humanas daquela modalidade.
6. Rodar o gate e revisar os bloqueios.
7. Desligar a flag ao primeiro incidente de privacidade ou desvio de custo.
8. Confirmar em homologação que o gateway respeita `Idempotency-Key` antes de ampliar o uso.

## Resultado nesta data

O provedor escolhido para o piloto local de escrita é Ollama `0.31.2`, usando `qwen2.5:7b` no
próprio Mac. A API local e uma inferência estruturada foram validadas. Não há provedor de
transcrição: essa modalidade continua desligada e exigirá Whisper ou serviço equivalente.

O primeiro ensaio expôs uma correção contraditória fora da decisão determinística. Como
contenção, o adaptador passou a enviar somente checks reprovados, restringir o schema aos códigos
desses checks e descartar critérios inventados na resposta. No novo ensaio, o modelo comentou
apenas `word_count` e `sentence_count`; comparação e uso de `should`, já aprovados, não receberam
sugestões. Essa contenção foi coberta por testes automatizados, mas não substitui a amostra humana.

Ollama local reduz a exposição externa, mas não substitui o gate: ainda faltam o manifesto
aprovado e 30 avaliações humanas da escrita. Portanto, para liberação além do ambiente de
desenvolvimento, o resultado esperado continua sendo `approved: false`.
