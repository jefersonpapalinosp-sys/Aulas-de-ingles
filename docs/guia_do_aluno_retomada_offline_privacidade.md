# Guia do aluno — retomada, offline, privacidade e recuperação

Atualizado em 5 de novembro de 2026 (Sprint 59: catálogo externo de listening).
Este guia descreve o comportamento atual da aplicação; “salvo neste
dispositivo” e “salvo na conta” não são sinônimos.

## Como retomar o estudo

Para a prática complementar de listening, consulte o
[guia do catálogo A2](listening_rapido.md). A conclusão é marcada por você e
confirmada pela API; esse módulo ainda não mantém uma fila de marcações offline.

- Entre na mesma conta e abra **Hoje**. A recomendação ou a última sessão leva à
  etapa confirmada mais recente.
- Etapas e posição do áudio sincronizadas aparecem em outro dispositivo depois
  que o servidor confirma a gravação. Uma alteração ainda pendente continua
  somente no dispositivo que a criou.
- Em uma sessão de exercícios, **Retomar sessão** usa a posição confirmada. Se o
  conteúdo mudou, o histórico antigo é preservado e a tela pede uma nova sessão.
- Escrita identifica separadamente o rascunho deste dispositivo, a revisão salva
  na conta e um possível conflito. Escolher uma versão é sempre uma ação explícita.

## O que cada estado significa

- **Confirmado/salvo na conta:** o servidor respondeu e o item pode ser retomado
  em outro dispositivo.
- **Pendente neste dispositivo:** a alteração está guardada localmente e será
  reenviada com a mesma chave idempotente. Ainda não conte com ela em outra tela.
- **Bloqueado:** sessão, conteúdo ou conta mudou. A aplicação mantém a cópia e
  explica se é necessário entrar novamente, iniciar uma sessão nova ou comparar
  versões.
- **Somente nesta tela:** gravação de voz sem consentimento não é persistida. Faça
  o download ou envie antes de fechar a aba.

A fila offline comporta até 100 respostas por conta neste navegador. Ao atingir
o limite, a resposta nova permanece no formulário e não é anunciada como salva.

## Estudo offline

Depois de uma visita online, o texto público de uma aula pode permanecer
disponível por tempo limitado. Áudio oficial da VOA continua dependente da rede e
da política da fonte; a interface nunca promete que ele foi baixado. Login,
sincronização, novas sessões e recursos assistidos exigem conexão.

**Hoje** oferece acesso ao mapa offline quando o currículo já foi consultado.
Sem confirmação online, o mapa não apresenta aulas como pendentes ou concluídas:
o progresso fica identificado como não confirmado. Recomendações e metas voltam
quando a conexão permite consultar a conta.

Posições intermediárias do áudio ainda não enviadas pela mesma aba são combinadas
na posição mais recente. A conclusão e os envios que aguardam confirmação são
preservados separadamente. Se o navegador avisar que não conseguiu salvar, mantenha
a página aberta; a retomada em outra aba não está garantida.

Uma tentativa de exercício feita numa sessão já aberta pode entrar na fila local.
Ao voltar a ficar online, mantenha a aba aberta até o estado mudar para confirmado
ou bloqueado. Não limpe os dados do navegador antes de conferir as pendências.

Após três falhas do serviço para a mesma resposta, o envio fica pausado e a fila
pode seguir com as próximas respostas. Em **Consultar respostas preservadas**,
**Pular por enquanto** pausa uma resposta que já falhou; **Retomar envio** permite
tentar novamente com o mesmo texto. Pausar não exclui nem confirma a resposta.
Falhas de sessão, limite de solicitações ou atualização obrigatória continuam
interrompendo a sincronização até serem resolvidas.

## Sessão expirada ou serviço indisponível

- Sessão expirada: entre novamente na **mesma conta**. Escrita e fila local não
  são apagadas automaticamente.
- Rede/API temporariamente indisponível: use **Tentar novamente**; não crie outra
  conta nem repita cliques enquanto o envio estiver pendente.
- Conteúdo atualizado: inicie uma nova sessão. Resultados antigos continuam no
  histórico com a versão correspondente.
- Conflito de escrita: compare local e remoto; mantenha uma, use a outra ou copie
  ambas. Não há sobrescrita silenciosa.

## Atualizar o aplicativo

Para receber esta correção pela primeira vez, salve o que estiver pendente,
feche todas as abas/janelas do aplicativo e reabra. Uma aba que ainda está na
versão antiga continua usando o botão antigo até essa primeira atualização.

Quando aparecer um aviso de versão nova ou de recuperação, escolha
**Recarregar aplicativo…**. Antes de confirmar, copie textos e salve gravações
que ainda estejam apenas na tela. A atualização preserva rascunhos já salvos
neste dispositivo e a fila de respostas pendentes.

Após a confirmação, aguarde a atualização terminar. Só a aba em que você
confirmou será recarregada; outras abas continuam abertas. Se a conexão falhar,
a tela permanece aberta e permite tentar novamente. Não é necessário limpar
os dados do navegador.

## Como interpretar avaliações

- **Correção objetiva:** compara uma resposta com o gabarito autoral daquele
  exercício. Não é avaliação geral do seu inglês.
- **Rubrica automática de escrita:** verifica critérios observáveis da proposta.
  Não garante gramática, coerência ou proficiência.
- **Assistência automática:** acrescenta sugestões experimentais e pode errar;
  não substitui professor ou revisão humana.
- **Autoavaliação oral:** é a percepção do próprio aluno após ouvir e comparar.
  Transcrição converte fala em texto, mas não dá nota de pronúncia.
- **Competências:** são tendências de evidências registradas. A tela mostra origem,
  período e tamanho da amostra e só calcula percentual a partir de três evidências;
  isso não certifica nível nem equivale a certificado oficial da VOA.

## Privacidade e voz

Gravações só são enviadas após consentimento explícito. A área **Meus dados**
permite baixar metadados, baixar áudios autorizados separadamente e pedir exclusão
da conta. O JSON exportado não é um backup restaurável e não inclui pendências
locais. A transcrição assistida é opcional, expira segundo o prazo exibido e pode
ser excluída sem apagar a gravação.

**Limpar este dispositivo** remove cópias locais e pendências, mas não apaga a
conta. **Excluir minha conta** remove dados do servidor e agenda a limpeza dos
arquivos pessoais. Também remove rascunhos, respostas pendentes, posições e a
gravação temporária dessa conta neste navegador, preservando outras contas.
Se alguma limpeza local falhar, a tela informa como remover os dados do site.
Feche outras abas antes da exclusão para que elas não mantenham rascunhos em
memória. Cópias baixadas e dados de outros dispositivos precisam ser removidos
nesses locais. Use somente depois de conferir ou baixar o que deseja guardar.

## O parceiro de conversa e o que sai desta aplicação

O parceiro de conversa tem três modos. O **Roteiro** não usa inteligência
artificial: ele segue o diálogo da aula, e nada do que você escreve nele sai
desta aplicação. O **Guiado** e o **Livre da unidade** mandam o texto do seu
turno a um provedor externo para que ele escreva a resposta do parceiro.

O que sai, quando você usa Guiado ou Livre:

- o conteúdo da aula (título, objetivos, vocabulário, frases e o roteiro);
- o texto do seu turno atual e até seis turnos anteriores da mesma conversa;
- a lista de códigos que a verificação automática reprovou neste turno.

O que a aplicação **não acrescenta** ao envio:

- seu nome, e-mail, identificador de conta ou token de sessão;
- seu histórico de estudo, progresso ou qualquer outra aula;

**Se você autorizar uma transcrição, o áudio bruto vai para o Workers AI da
Cloudflare.** Isso vale tanto para a conversa quanto para a prática oral.
Depois, o modelo de conversa recebe somente o texto. A voz e o que você disser
podem identificar você; não há anonimização de áudio. Evite dados pessoais,
conteúdo sensível e gravações de terceiros. Sem confiança informada pelo
provedor, a tela avisa que a confiança é desconhecida; não é uma nota de pronúncia.

O piloto é restrito à conta autorizada. A Cloudflare declara não usar o conteúdo
para treinamento e não reter conteúdo de inferência comum após processamento,
com exceções legais/de segurança e retenção de metadados operacionais. Não há
garantia de processamento exclusivamente no Brasil. Consulte a
[política Workers AI](https://developers.cloudflare.com/workers-ai/platform/data-usage/).
Respostas podem conter erros ou conteúdo inadequado: não há moderação de saída.

Se você escrever o seu e-mail, telefone ou documento dentro da própria frase, a
aplicação o substitui por `[email removido]` ou `[numero removido]` **antes** de
mandar o texto ao provedor. O que você escreveu continua inteiro na sua
conversa e no seu histórico: a troca é só no que sai. Números curtos — idade,
hora, número da aula — não são trocados.

O resultado que você vê — o que cumpriu e o que faltou — é calculado nesta
aplicação, por regra fixa, e nunca vem do provedor. Quando a resposta dele não
chega ou vem fora do formato esperado, a conversa continua pelo roteiro da aula
e a tela diz que foi o roteiro que respondeu.

O texto e as gravações dos turnos de conversa seguem o prazo de retenção exibido
na tela (30 dias por padrão). A limpeza dos arquivos ocorre pelo serviço de
manutenção, com novas tentativas se o armazenamento estiver indisponível.
Excluir um diálogo inteiro também remove suas gravações; não existe exclusão
individual de turno.
O que fica depois disso é a evidência de que você praticou: quando praticou, o
que a verificação automática apontou e a sua própria avaliação do turno.

## Antes de trocar de navegador ou apagar dados

1. Abra o indicador de conectividade e confirme que não há respostas pendentes ou
   bloqueadas.
2. Confira rascunhos locais e conflitos de escrita.
3. Baixe gravações que ficaram somente na tela.
4. Exporte o que for necessário em **Meus dados**.
5. Só então limpe os dados deste dispositivo.

## Listening rápido: histórico e retomada do piloto

O piloto de três atividades próprias ainda depende de revisão humana e ativação;
o catálogo de links externos continua separado. Quando habilitado, **Meu histórico
no aplicativo** permite continuar uma sessão e revisar os erros. A nota das primeiras
respostas é preservada, mesmo quando você acerta numa repetição.

Uma sessão já aberta guarda escolhas e respostas pendentes neste dispositivo.
Sem conexão, **Pendente de envio** não significa resposta corrigida ou confirmada.
Volte à prática ou ao histórico com internet e confirme a mesma conta para sincronizar.
Recarregar mantém as pendências; trocar de conta não as envia como outro aluno.
O áudio, o início de uma nova prática e a revelação de respostas exigem conexão.

Se duas abas produzirem rascunhos diferentes, escolha na lista qual usar. Se a
sessão mudou em outro dispositivo, confira a seleção preservada antes de enviá-la
como nova tentativa. Conflitos de áudio permitem escolher entre a posição local
e a da conta. A reprodução não começa automaticamente ao retomar.

**Meus dados** conta esses rascunhos, respostas pendentes e posições. A exportação
JSON contém os dados confirmados no servidor; não contém pendências do navegador.
Sincronize antes de limpar os dados privados ou trocar de dispositivo. Não limpe
storage para corrigir um erro de sincronização.
