# SEC-49 — ensaio e ordem de rotação de segredos

Registro de 29/10/2026. Ensaio aprovado em laboratório exclusivo, com API real,
PostgreSQL e gateway HTTP sintético. Nenhum segredo de estudo ou produção foi
alterado. Publicado pelo [PR #41](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/pull/41),
com ensaio aprovado no [CI remoto](https://github.com/jefersonpapalinosp-sys/Aulas-de-ingles/actions/runs/40926233714)
e deploy concluído em `9cc14fe`.

## Resultado observado

| Prova | Resultado |
|---|---|
| Senhas de backup, migrador, worker e runtime | Quatro senhas antigas recusadas em conexões novas; quatro novas aceitas |
| Conexões abertas antes da troca | As quatro continuaram funcionando |
| Runtime reiniciado com senha antiga | `/api/health` respondeu 503 |
| Runtime reiniciado com senha nova | Health 200; sessão autenticada anterior continuou válida |
| JWT antigo depois da troca | Access e refresh recusados com 401 |
| Novo login e novo refresh | Ambos responderam 200; novo access aceito |
| Duas APIs com JWTs diferentes | Mesmo access antigo: 200 na instância antiga e 401 na nova |
| Token do gateway | Sobreposição aceita; token revogado recebeu 401; token novo continuou aceito |
| Preservação | Nota sintética, atributos/membros dos papéis, grants de tabelas e chaves do limitador preservados |
| Encerramento do cenário | Conta sintética removida; zero usuários restantes |

A execução final levou **9.772 ms**: etapa de senhas e reinício do runtime
**3.513 ms**, JWT **1.376 ms**, gateway **505 ms**. O total inclui preparação,
migrations, seed, inicialização e limpeza; as etapas não somam o total.
São medições locais, não estimativas de indisponibilidade ou SLA de produção.

## Ordem operacional

Antes da janela, identificar os consumidores de cada segredo: API, workers,
migrador, backup e configuração de deploy. Conferir recuperação e acesso
administrativo independente, guardar segredos em configuração privada e
combinar a janela com os usuários. Salvar textos e enviar ou baixar gravações
pendentes antes de encerrar sessões do navegador.

Executar uma classe de segredo por vez, validando antes de avançar:

1. **Banco: backup → migrador → worker → runtime.** Para cada papel, alterar
   a senha no PostgreSQL, atualizar a configuração de todos os consumidores
   e renovar seus processos/pools de forma controlada. Verificar uma conexão
   nova, identidade/privilégios e funcionamento do consumidor. O migrador
   precisa continuar podendo assumir o papel proprietário; o backup deve
   manter leitura. Respeitar o término dos jobs antes de reiniciar workers.
2. **JWT:** distribuir a nova configuração a todas as instâncias e coordenar
   a substituição dos processos da API na mesma janela. A implementação usa
   uma chave por processo; manter instâncias antigas e novas no tráfego
   produz respostas inconsistentes. Validar rejeição do access e refresh
   antigos, novo login e novo refresh. Comunicar que será necessário entrar
   novamente.
3. **Provedor:** quando o provedor permitir duas credenciais simultâneas,
   criar a nova, instalar em todos os consumidores, validar uma chamada,
   revogar a anterior e validar novamente. Se não houver sobreposição,
   coordenar a pausa dos consumidores conforme o contrato do provedor.

PostgreSQL mantém uma senha por papel: não há sobreposição de duas senhas
no mesmo login. Alterar a senha **não encerra conexões abertas**. Em resposta
a comprometimento, o procedimento deve também tratar as sessões existentes,
identificadas por banco e papel; reiniciar apenas o consumidor legítimo não
revoga outras conexões. Não encerrar indiscriminadamente outros projetos.

O proprietário `aulas_owner` é `NOLOGIN`; não recebeu senha. A senha do
administrador do banco não faz parte do ensaio dos quatro consumidores.
Não restaurar uma senha comprometida para desfazer uma implantação.

O ensaio fixa explicitamente `AUTH_BUCKET_SECRET`, preservando as chaves do
limitador durante a troca do JWT. Tratar esse segredo separadamente: a prova
não cobre a configuração que deriva o segredo do limitador de outra chave.
A troca de assinatura não equivale à revogação persistente de todas as
sessões: restaurar a chave JWT antiga pode tornar tokens antigos válidos
novamente, se ainda não expirados/revogados. Manter a chave nova ao reverter
somente a versão da aplicação.

O gateway recebeu cinco chamadas: `200, 200, 200, 401, 200`. O cliente real
`call_writing_provider` converteu a recusa do token revogado em
`provider_unavailable`, sem revelar a resposta sensível. Capacidade de manter
duas chaves, custo e comportamento de chamadas em andamento precisam ser
confirmados no provedor efetivamente escolhido.

## Reproduzir o laboratório

Na raiz do repositório, com Docker local e dependências do backend instaladas:

```bash
uv run --project backend python -m ops.rotation_rehearsal up
uv run --project backend python -m ops.rotation_rehearsal check
uv run --project backend python -m ops.rotation_rehearsal down
```

`up` constrói a imagem auxiliar atual e inicia somente o projeto
`aulas-ingles-rotation49`. O banco `aulas_rotation_lab` fica em rede interna,
sem portas publicadas. Volume, rede, imagem e mounts são conferidos; banco
e papéis têm marcadores próprios. A sonda tem raiz somente leitura, usuário
sem privilégios, capabilities removidas e nenhum mount de dados do aluno.

As quatro senhas, os JWTs e os tokens de gateway são aleatórios e existem
apenas nos processos do ensaio. A senha administrativa publicada no Compose
é uma fixture exclusiva desse banco descartável. A ferramenta não aceita
alvo, URL ou segredo externo. APIs e gateway escutam no loopback da sonda.

`check` aplica migrations/seed reais, cria a conta e nota sintéticas, realiza
as verificações e remove somente a conta criada. Se já existir usuário no
banco, a preparação é recusada; não esvaziar a base para forçar aprovação.
O nome fixo da sonda impede duas execuções simultâneas. Uma sonda preexistente
é recusada; a limpeza remove somente o ID criado pela execução atual.

O recibo privado `backups/recovery/rotation49-*.json` contém resultados
agregados, durações e SHA-256 dos três scripts, sem tokens, senhas ou textos.
Diretório e arquivo exigem permissões privadas; campos inesperados ou provas
incompletas impedem o recibo. Falhas mostram somente fase e tipo de erro.
Não publicar os diretórios de backup como artifacts do CI.

`down` encerra apenas o laboratório e preserva seu volume sintético e recibos.
Não usa `down -v` nem limpeza global de Docker. O CI contém o ensaio e seu
encerramento com `if: always()`.

## Validação e limites

- Ensaio integrado executado três vezes, incluindo a versão final dos scripts.
- Laboratório encerrado; ausência de containers do projeto confirmada, com volume preservado.
- Sete testes novos de isolamento, recusa, limpeza e recibo; **343 testes
  operacionais aprovados** na suíte completa.
- Ruff com a configuração do projeto, mypy estrito dos **40 módulos**, Compose
  e actionlint do workflow aprovados.
- APIs exercitadas por HTTP, incluindo login/refresh e readiness; conexões
  reais com os quatro papéis; gateway sintético usando o cliente da aplicação.

Não foram exercitados jobs longos de worker, provedor externo, cobrança,
gravações/rascunhos no navegador nem uma base real de alunos. A preservação
de conteúdo verificada é a nota sintética, não uma auditoria integral de dados.
O aceite de SEC-46 e o piloto do ciclo 48 continuam separados desta entrega.
