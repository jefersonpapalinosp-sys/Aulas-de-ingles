# ADR — Parceiro de conversa ancorado nas aulas (IA-45)

Estado: **proposto em 21/10/2026, aguardando aprovação de Jeferson**. Enquanto
não for aprovado, nenhum schema (DB-45) nem rota (BE-46) do assistente é criado.

Pacote de origem: [plano das Sprints 44–49](plano_sprints_44_49_frentes_e_assistente_de_fala_2026-10-21.md#ia-45-definição-contrato-e-spike-do-parceiro-de-conversa).

## Contexto

O aluno estuda a série *Let's Learn English* com 82 aulas publicadas, cada uma
com objetivos, vocabulário com IPA, frases, blocos de gramática, transcrição em
cues com falante e proposta de escrita. O app já grava voz localmente, faz
shadowing, transcreve por um gateway opcional (fila durável, cota, retenção) e
corrige escrita com rubrica determinística, deixando ao modelo só a explicação
dos critérios reprovados.

O [plano multimodal](plano_evolucao_estudo_ingles_multimodal.md#11-priorização)
veta "chat aberto genérico como tutor principal", "nota única de fluência" e
armazenar áudio no PostgreSQL. Este ADR respeita as três vedações.

## Decisão

### O que é

Um **parceiro de conversa roteirizado e ancorado na aula**, não um tutor. Ele
conversa em inglês, no nível da aula, sobre o tema da aula, usando o vocabulário
e os padrões gramaticais dela. Ele nunca dá nota, nunca corrige pronúncia, nunca
julga o aluno; explica, em português e em uma frase, apenas o que a camada
determinística reprovou.

### Três modos, liberados nesta ordem

| Modo | Mecânica | Precisa de | Libera quando |
|---|---|---|---|
| **Roteiro** (`script`) | Role-play do diálogo oficial: o app fala um personagem (voz sintetizada no navegador) e o aluno fala o outro; a fala do aluno é transcrita e comparada à esperada com `compare_transcript`. Sem IA generativa. | STT já existente. Sem STT, equivale ao shadowing atual com falas alternadas e autoavaliação. | BE-46 |
| **Guiado** (`guided`) | O parceiro faz uma pergunta curta ancorada nos objetivos, frases e vocabulário; a resposta passa pela camada determinística e só os códigos reprovados vão ao modelo, que devolve o próximo turno e uma dica por código. | STT + provedor de diálogo. | BE-46/FE-47, se o spike aprovar a latência |
| **Livre na unidade** (`free_unit`) | Conversa sobre os temas da unidade, com cerca de vocabulário e limite de turnos; o modelo redireciona ao tema quando o aluno sai. | Guiado aprovado no gate humano (IA-48). | depois de IA-48 |

### Pipeline de um turno do aluno

```
browser  VoiceRecorder → PUT áudio do turno (limites/consentimento atuais) → API 202 + job
worker   STT pelo gateway (Idempotency-Key)
         → domain/dialogue.py: cobertura de termos-alvo, padrão gramatical, comprimento (puro)
         → services/dialogue_prompts.py monta mensagens + JSON Schema restrito aos códigos reprovados
         → provedor (gateway HTTPS em produção; Ollama só em desenvolvimento)
         → saneamento: descarta códigos não permitidos, URLs, e-mails, excesso de texto
         → persiste turno; cliente faz polling do job
browser  mostra transcrição + confiança + checks; fala partner_text com speechSynthesis (en-US)
```

Entrada por texto é alternativa de primeira classe quando não há microfone; o
turno segue o mesmo caminho sem STT.

### O modelo nunca

- dá nota, "score", percentual ou qualquer juízo global sobre o aluno;
- corrige pronúncia ou fonema (a transcrição mede reconhecimento de palavras);
- recebe nome, e-mail, histórico de conta ou qualquer identificador: o payload
  tem só o texto do turno atual, os últimos turnos do diálogo (texto) e os
  códigos reprovados;
- altera progresso, evidência, revisão ou cota: isso é feito pela aplicação a
  partir dos checks determinísticos;
- sai do tema sem redirecionar, nem responde fora do JSON Schema.

### Camada determinística decide; o modelo explica

Códigos de check, fixos e versionados no módulo
`app/services/dialogue_prompts.py`:

| Código | Regra | Fonte |
|---|---|---|
| `target_terms_missing` | nenhum termo-alvo do turno apareceu na fala | `vocab_item.term` da aula, normalização de `domain/answers.py` |
| `grammar_pattern_missing` | o padrão do bloco de gramática pedido no turno não apareceu | exemplos das linhas de `grammar_block` |
| `too_short` | menos de 3 palavras reconhecidas | transcrição |
| `too_long` | mais de 60 palavras | transcrição |

O JSON Schema enviado ao provedor restringe `hints[].code` **exatamente** aos
códigos reprovados daquele turno. Sem código reprovado, o modelo recebe uma
lista vazia e só pode devolver o próximo turno.

### Contrato HTTP proposto (rascunho para BE-46)

| Método e rota | Função | Idempotência |
|---|---|---|
| `POST /api/speaking/dialogues` | cria diálogo: `lesson_id`, `mode`, `partner_speaker` opcional | `operation_key` |
| `GET /api/speaking/dialogues/{id}` | estado, turnos e limite | — |
| `PUT /api/speaking/dialogues/{id}/turns/{position}/audio` | áudio do turno; `202` com `job_id` | `(dialogue_id, position)` |
| `POST /api/speaking/dialogues/{id}/turns/{position}/text` | turno por texto; `202` com `job_id` | `(dialogue_id, position)` |
| `GET /api/speaking/dialogues/{id}/turns/{position}` | transcrição, checks, `partner_text`, `hints`, `confidence`, `fallback` | — |
| `PUT /api/speaking/dialogues/{id}/turns/{position}/rating` | "foi útil" / "não foi útil" | — |
| `DELETE /api/speaking/dialogues/{id}` | apaga diálogo e turnos; áudio segue a política de speaking | — |

Erros seguem o contrato atual (`request_id`, códigos estáveis): `409
assist_disabled` nos modos com IA quando a flag está desligada, `429` por cota,
`503` por provedor indisponível com o turno seguinte vindo do Roteiro marcado
como `fallback`.

### Cota, custo, retenção e privacidade

- Modalidade nova `conversation` em `assist_reservation`; cota diária própria
  `ASSIST_DIALOGUE_DAILY_TURNS` (padrão 20); cada turno Guiado custa STT + modelo
  e o custo é somado em microdólares como hoje.
- `transcript` e `partner_text` seguem `ASSIST_RETENTION_DAYS`; metadados
  agregados (checks, custo, avaliação) permanecem.
- Áudio só com o consentimento já exigido em speaking; excluir o diálogo apaga
  seus turnos; exclusão de conta e exportação pessoal (1.7) cobrem as tabelas.
- Nenhum texto de turno, transcrição ou resposta do provedor entra em log.
- Em produção o provedor é um gateway HTTPS com token, região e retenção
  revisadas (`avaliacao_sprint14_assistencia.md`); Ollama fica restrito a
  desenvolvimento, porque a VM pública é compartilhada e sem GPU.

### Voz do parceiro

`speechSynthesis` do navegador, voz `en-US`, velocidade ajustável, botão de
repetir, legenda sempre visível. Zero custo, nenhum dado sai do dispositivo,
funciona offline no modo Roteiro. Um gateway de TTS só entra se a voz for
reprovada no piloto (IA-48).

### Limites de produto

- Limite de 12 turnos do aluno por diálogo no Guiado; o parceiro encerra com
  uma frase de fechamento.
- Modo Roteiro usa o diálogo da aula como está; aulas com um só falante caem em
  "repita depois de mim" e são marcadas assim.
- Dicas em português, uma frase, sem repetir o texto completo do aluno.

## Alternativas consideradas

- **Chat aberto com o modelo como tutor.** Vetado pelo plano multimodal; sem
  cerca de tópico nem rastreabilidade pedagógica.
- **Modelo no dispositivo (WebLLM/WebGPU).** Latência e memória incompatíveis
  com os dispositivos reais do piloto; fica fora até existir medição.
- **TTS por gateway desde o início.** Custo e saída de dados sem necessidade
  comprovada; a síntese do navegador atende o piloto.
- **Correção fonética.** Fora do escopo pelo plano multimodal; a transcrição
  não mede pronúncia.

## Consequências

- Duas tabelas novas (`speaking_dialogue`, `dialogue_turn`), ampliação de
  `ck_assist_modality`, `skill_evidence.source_type` e origem de `review_item`
  (DB-45, migration aditiva).
- Um tipo novo de job na fila durável existente, sem worker novo.
- O gate humano `assist-gate modality=conversation` reaproveita os limiares das
  outras modalidades (30 avaliações, 80% úteis, falha técnica abaixo de 5%,
  custo no orçamento).

## Critérios de aceite do IA-45

1. Este ADR aprovado por Jeferson antes de DB-45 fechar o schema.
2. Spike com 30 turnos sintéticos no caminho escolhido para produção: p95 do
   turno completo abaixo de 8 s. Acima disso, só o Roteiro avança no ciclo 46.
3. Nenhum prompt contém dado pessoal além do texto do turno; teste automatizado
   em `backend/tests/test_dialogue_prompts.py`.

## Decisões em aberto, para Jeferson

- Provedor de diálogo e de STT em produção (qual gateway). Sem essa escolha, o
  spike só roda no modo simulado e no Ollama local, e o critério 2 fica em aberto.
- Confirmar o limite de 12 turnos e a cota diária de 20.
- Confirmar a voz do navegador como padrão do piloto.

Aprovado por: ____________________ em ____/____/2026.
