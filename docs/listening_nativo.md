# Piloto nativo de listening — Sprints 60–61

Implementação iniciada em 05/11/2026. O piloto está **desativado por padrão**.
Há três atividades próprias em rascunho, com áudio sintético e dez questões.
O aceite editorial da Sprint 60 continua pendente: testes de software não
atestam o nível A2, a naturalidade da voz ou os direitos de publicação.

## Material para revisão

| Atividade | Questões | Áudio medido | Prévia |
|---|---:|---:|---|
| A room at the Riverside Hotel | 4, escolha única | 77,11 s | [MP3](../seed/listening-native/audio/hotel-riverside-v1.mp3) |
| Find the museum | 3, mapa e diálogo | 77,34 s | [MP3](../seed/listening-native/audio/caminho-ao-museu-v1.mp3) |
| A Saturday with friends | 3, incluindo selecione duas | 77,80 s | [MP3](../seed/listening-native/audio/sabado-com-amigos-v1.mp3) |

O [pacote editorial](../seed/listening-native/activities.json) contém os roteiros,
opções, gabaritos, explicações, mapa textual, procedência e SHA-256 de cada MP3.
Esses arquivos pertencem ao backend; não são distribuídos no bundle do frontend.
Os roteiros foram preparados com assistência de IA para este projeto. Nenhum
áudio, imagem, questão ou transcrição do Test-English foi incorporado ao piloto.

As prévias usam eSpeak NG 1.51.1, voz `en-us`, 135 palavras/minuto, codificação
MP3 a 64 kbps. Uma única voz lê os nomes dos participantes; a revisão deve
avaliar especialmente inteligibilidade, pausas e distinção entre interlocutores.
As durações acima são dos arquivos de áudio. **5–10 minutos por atividade é uma
meta pedagógica ainda não medida com alunos.**

Para o aceite, um responsável deve ouvir cada MP3 e conferir nível A2, ritmo,
gabarito, explicações e alternativa textual do mapa. Deve também registrar a
base de direitos para texto e áudio e decidir a licença/atribuição da publicação.
`reviewed_by`, `reviewed_on` e `rights_approved` permanecem vazios/falsos nos
rascunhos entregues. Nenhuma aprovação humana foi simulada.

## Experiência e pontuação

Na página **Listening rápido**, o bloco **Pratique aqui** aparece quando o
recurso está habilitado e há versões disponíveis. A rota `/listening/:slug`
abre a atividade; **Iniciar prática** cria uma sessão com a versão fixada.
O endereço passa a incluir `?sessao=ID`, permitindo voltar à sessão confirmada.

O player não inicia automaticamente e oferece velocidade, avanço/retorno de
cinco segundos e repetição A/B. Os controles de reprodução e seleção são
compartilhados com as aulas VOA. A Sprint 61 acrescenta posição de áudio,
rascunhos por conta/versão e histórico com acesso às sessões anteriores.

A correção vem da API. Cada questão conta somente na primeira resposta da
sessão. Revelar o gabarito antes de responder conta zero; repetir não altera
essa nota. A transcrição pode ser revelada a qualquer momento e deixa o registro
**prática com apoio textual**. Não há nota importada de sites externos nem
alteração do progresso VOA. Uma nova sessão é uma nova prática, com sua própria nota.

Para seleção dupla, é necessário enviar exatamente dois IDs válidos, distintos.
A ordem não interfere. Cada resposta exige revisão e UUID de operação. Uma
repetição da mesma operação não cria outro evento; reutilizar a chave com outro
conteúdo ou enviar uma revisão antiga retorna 409. O reenvio de uma operação
antiga devolve o estado atual, preservando respostas posteriores.

Em uma sessão já aberta, escolhas são salvas no dispositivo e respostas podem
ficar **pendentes de envio** sem conexão. A confirmação depende da API. A fila
preserva chave, seleção, versão e revisão entre recargas; só envia depois que
a mesma conta for confirmada online. Abrir a prática ou o histórico e reconectar
retoma o envio. Não há envio em segundo plano com o aplicativo fechado.
Revelar gabarito/transcrição e iniciar sessões novas exigem conexão.

No catálogo, **Meu histórico no aplicativo** mostra primeira e última tentativa,
nota inicial e resultado mais recente, com páginas de dez sessões e filtro por
atividade. **Continuar de onde parei** abre a primeira sessão incompleta disponível
na página; **Revisar erros** filtra erros/revelações da primeira tentativa.
As marcações dos links externos continuam autodeclaradas e separadas.

Duas abas preservam rascunhos de editores diferentes. A lista permite escolher
uma variante sem apagar as demais. Respostas são reservadas atomicamente em
IndexedDB; Web Locks serializa envio e a API assegura idempotência. Um conflito
409 preserva a escolha e exige **Enviar como nova tentativa** ou descarte explícito.
A nota inicial não muda. Posição de áudio usa uma revisão independente; conflito
entre posições oferece manter a posição local ou usar a da conta.

O áudio só funciona online e não é baixado para uso offline. Pausas, saltos e
avanço de aproximadamente cinco segundos atualizam a posição; concluir o áudio
registra zero e impede que uma escrita atrasada restaure o ponto antigo. Não há
garantia de salvar os últimos segundos se o navegador for encerrado abruptamente.

## Contrato, dados e privacidade

- `native_listening_version`: pacote privado, identificado por slug e versão;
  guarda o conteúdo completo e seu hash. Seed e trigger impedem alteração de
  versão existente. Questões pertencem ao JSON versionado, com IDs estáveis.
- `native_listening_session`: conta, versão fixada, chave de início e revisão.
- `native_listening_position`: posição por conta/sessão, revisão própria e chave
  idempotente; FK composta, índice de sessão e exclusão por cascata.
- `native_listening_response`: eventos imutáveis de resposta, revelação ou apoio,
  com chave por conta e sequência única por sessão. FK composta impede associar
  um evento à sessão de outro usuário.

As rotas autenticadas são `/api/listening/native-config`, `/native`,
`/native/{slug}`, `/native/{slug}/sessions`, `/sessions/{id}`,
`/sessions/{id}/responses`, GET/PUT `/sessions/{id}/position`, GET `/history`
(`limit` até 50, `before` por ID e `slug`) e `/native/{slug}/versions/{version}/audio`, todas
sob `/api/listening`. A projeção pública de cada questão contém apenas enunciado,
opções e quantidade exigida. Gabarito e explicação aparecem após resposta ou
revelação daquela questão; a transcrição depende de revelação explícita.

Os GETs são privados e `no-store`. O áudio passa pelo cliente autenticado e
vira um Blob temporário, revogado ao sair da atividade/conta. API e mídia não
entram no Cache Storage da PWA. Se o cache público da página for removido, uma
visita online o reconstrói somente após verificar o hash da versão instalada.
A CSP e os limites/TTL existentes foram preservados. O IndexedDB
privado `aulas:listening:v1` guarda apenas a projeção de sessões já abertas,
rascunhos e comandos da conta, sem chaves de correção ainda não reveladas.
Posições usam namespaces `native-position:v1`/`native-pending:v1` separados de VOA.
Limites locais: mil registros por conta, cem comandos por sessão e cem eventos
na API. Falha/quota bloqueia o salvamento com aviso; nada é descartado para abrir espaço.

Em **Meus dados**, o inventário inclui rascunhos/respostas nativas e posições.
Limpar dados privados remove somente a conta escolhida e avança a geração do
IndexedDB para rejeitar callbacks anteriores. A exportação da conta contém só
o que chegou ao servidor; rascunhos e respostas pendentes locais não fazem parte
desse JSON. Confirme a sincronização antes de limpar. Não há importação local.

A exportação completa inclui `native_listening_sessions` e
`native_listening_responses`, além de `native_listening_positions`: versão/hash, nota inicial, estado de apoio,
respostas enviadas, identificação de repetições e explicações já liberadas.
Não inclui gabaritos de questões ainda não respondidas. A transcrição entra
somente se já foi revelada. Exportação e exclusão continuam funcionando com
o recurso desligado; a exclusão da conta remove as sessões/eventos por cascata
e preserva o catálogo editorial.

## Prévia local e release

1. Use um clone/banco de desenvolvimento destinado a ensaio, com backup e
   processo de release do projeto. A migration atual é `f61a1b8c9009`, sucessora de
   `e60a1b8c9008` (piloto) e `d59a1b8c9007` (catálogo externo). Execute migration, `alembic check` e seed com o migrador.
   O seed padrão passa a verificar também o pacote e os hashes dos três MP3s.
   `seed --dry-run` continua sendo a prévia do currículo VOA; não cobre este pacote.
2. Reconcile os grants: runtime lê versões e grava sessões/eventos; não pode
   editar versões nem eventos existentes. A posição permite SELECT/INSERT/UPDATE,
   sem DELETE direto. Worker não recebe acesso; backup lê.
3. Somente para revisão local, use `LISTENING_NATIVE_ENABLED=true` e
   `LISTENING_NATIVE_PREVIEW=true`, com `APP_ENV=dev` ou `test` e
   `DEPLOYMENT_PROFILE=local`. `prod` e perfil `public` recusam rascunhos,
   mesmo que alguém ligue a flag de prévia.
4. Após revisão humana, publique **nova versão** com registro editorial e
   direitos aprovados; preserve versões/áudios usados por sessões anteriores.
   Produção usa `LISTENING_NATIVE_ENABLED` ou
   `EASYPANEL_LISTENING_NATIVE_ENABLED`; a prévia fica desligada.

Os defaults permanecem `false` em desenvolvimento, produção e EasyPanel.
Somente a stack E2E sintética habilita ambos. Desligar a flag bloqueia as rotas
de prática sem apagar os dados. Downgrade é recusado quando existem sessões ou posições;
prefira rollback da aplicação preservando o schema.

O backup PostgreSQL inclui versões, sessões, respostas e posições. Os MP3s didáticos
pertencem à pasta `seed/listening-native/audio` da **imagem versionada da API**,
não ao volume de gravações pessoais. Preserve a imagem/digest e os ativos de
todas as versões referenciadas junto da release; um dump sozinho não recupera
os MP3s. O ensaio operacional compara o conteúdo restaurado do banco e verifica
os três hashes de áudio em um container novo da imagem.

## Release e limites atuais

A Sprint 61 foi implementada para ensaio; não houve deploy nem migração do banco
de estudo. Flags continuam falsas. Desativar bloqueia novos acessos/envios na API,
sem eliminar o histórico remoto ou os dados locais já salvos. Cópias locais podem
ser consultadas offline pela mesma conta; pendências recusadas ficam preservadas
para resolução quando o recurso voltar. Nunca limpe storage como procedimento de rollback.

O orçamento específico passa a 13 KiB gzip, incluindo histórico, fila e o
sincronizador neutro de posição compartilhado com VOA (antes contabilizado na
base). Entrada permanece em 132 KiB, base em 184 KiB, diálogo em 8 KiB e catálogo
externo em 3 KiB; conjunto máximo 208 KiB. Todos os módulos de listening são lazy.

Próxima prioridade: avaliação humana dos três roteiros/MP3s, registro de direitos
e nova versão aprovada; depois ensaio e release controlada. Atalho no painel Hoje
é opcional e não foi acrescentado. O [relatório da Sprint 61](execucao_sprint61_2026-11-06.md)
registra os testes e as limitações da validação técnica.
