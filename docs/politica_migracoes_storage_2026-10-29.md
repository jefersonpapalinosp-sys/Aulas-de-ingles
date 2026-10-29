# Retirada dos adaptadores de storage — FE-49

Responsável técnico: frente FE; validação de preservação de dados: FE/SEC.

**Data-alvo de remoção: 29/01/2027**, sujeita aos critérios abaixo. A data é
um marco de revisão e publicação de código, não uma expiração dos dados.
Nenhum relógio, limpeza automática ou alteração de formato foi introduzido
pela FE-49. Se os critérios não forem atendidos, registrar uma nova data
neste documento e manter o adaptador.

| Origem legada | Destino atual | Adaptador | Condição específica para retirada |
| --- | --- | --- | --- |
| `aulas-ingles:study-progress:v1:<usuário>:<aula>` | `study-progress:v2:<usuário>:<curso>:<aula>` | `features/study-session/studyProgress.ts` | Preservar associação exclusiva ao curso `voa-level-1`; validar cópia sem sobrescrever progresso atual |
| `aulas-ingles:shadowing-rating:v1:<usuário>:<aula>:<trecho>` | `shadowing-rating:v2:<usuário>:<curso>:<aula>:<trecho>` | `features/speaking/selfRating.ts` | Preservar autoavaliação do Level 1 e isolamento por usuário/curso |
| `aulas-ingles:media-position:v1:<usuário>:<mídia>` | cache `media-position:v2` e comandos `media-pending:v2` | `features/media/positionSync.ts` | Confirmar que retomada e sincronização da posição foram feitas sem perder comandos pendentes |
| `aulas:offline-attempts:v1` e `aulas:offline-attempts:v2` | IndexedDB, schema v3 | `features/offline/attemptQueueStore.ts` | Migração transacional, recibos contra reenvio e caminho de recuperação para clientes que voltam após longo período offline |

Antes da remoção:

1. Publicar uma versão com os adaptadores e orientação de atualização; registrar
   a versão e o período de convivência. Não forçar reload nem apagar cache privado.
2. Testar retorno de cliente antigo, múltiplas contas, escrita interrompida,
   quota esgotada, dados inválidos e repetição da migração. Manter a fonte
   legada quando a gravação do destino não estiver confirmada.
3. Para a fila de exercícios, disponibilizar e testar um importador de
   recuperação explícito antes de remover a importação automática. Ausência de
   uso recente não prova ausência de respostas em dispositivos offline.
4. Validar atualização e rollback na stack descartável, com fixtures legadas.
   Registrar evidências na PR de remoção e atualizar inventário/limpeza privada.
5. Remover a leitura legada em uma entrega separada. Apagar dados antigos exige
   ação explícita do usuário ou política específica posterior; não faz parte
   desta data-alvo.

Chaves v1/v2 que ainda são formatos ativos — rascunho de escrita, eventos de
tempo, posição de prática, perfil da sessão e comandos pendentes de mídia —
**não são legadas apenas por conterem v1/v2** e não entram nesta retirada.

A leitura do storage continua tolerante a indisponibilidade. Falhas devem
informar o aluno e preservar texto, gravações e respostas recuperáveis; não
devem ser tratadas como autorização para recriar o banco ou limpar o navegador.
