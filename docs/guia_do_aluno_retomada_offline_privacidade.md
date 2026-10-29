# Guia do aluno — retomada, offline, privacidade e recuperação

Atualizado em 26 de outubro de 2026 (SEC-46: a seção do parceiro de conversa).
Este guia descreve o comportamento atual da aplicação; “salvo neste
dispositivo” e “salvo na conta” não são sinônimos.

## Como retomar o estudo

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

Uma tentativa de exercício feita numa sessão já aberta pode entrar na fila local.
Ao voltar a ficar online, mantenha a aba aberta até o estado mudar para confirmado
ou bloqueado. Não limpe os dados do navegador antes de conferir as pendências.

## Sessão expirada ou serviço indisponível

- Sessão expirada: entre novamente na **mesma conta**. Escrita e fila local não
  são apagadas automaticamente.
- Rede/API temporariamente indisponível: use **Tentar novamente**; não crie outra
  conta nem repita cliques enquanto o envio estiver pendente.
- Conteúdo atualizado: inicie uma nova sessão. Resultados antigos continuam no
  histórico com a versão correspondente.
- Conflito de escrita: compare local e remoto; mantenha uma, use a outra ou copie
  ambas. Não há sobrescrita silenciosa.

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
arquivos pessoais; use somente depois de conferir ou baixar o que deseja guardar.

## O parceiro de conversa e o que sai desta aplicação

O parceiro de conversa tem três modos. O **Roteiro** não usa inteligência
artificial: ele segue o diálogo da aula, e nada do que você escreve nele sai
desta aplicação. O **Guiado** e o **Livre da unidade** mandam o texto do seu
turno a um provedor externo para que ele escreva a resposta do parceiro.

O que sai, quando você usa Guiado ou Livre:

- o conteúdo da aula (título, objetivos, vocabulário, frases e o roteiro);
- o texto do seu turno atual e até seis turnos anteriores da mesma conversa;
- a lista de códigos que a verificação automática reprovou neste turno.

O que **não** sai, em nenhum modo:

- seu nome, e-mail, identificador de conta ou token de sessão;
- seu histórico de estudo, progresso ou qualquer outra aula;
- o áudio da sua voz — o provedor de conversa é só de texto. Se você gravar um
  turno falando, o áudio é transcrito e o que segue para o provedor de conversa
  é o texto.

Se você escrever o seu e-mail, telefone ou documento dentro da própria frase, a
aplicação o substitui por `[email removido]` ou `[numero removido]` **antes** de
mandar o texto ao provedor. O que você escreveu continua inteiro na sua
conversa e no seu histórico: a troca é só no que sai. Números curtos — idade,
hora, número da aula — não são trocados.

O resultado que você vê — o que cumpriu e o que faltou — é calculado nesta
aplicação, por regra fixa, e nunca vem do provedor. Quando a resposta dele não
chega ou vem fora do formato esperado, a conversa continua pelo roteiro da aula
e a tela diz que foi o roteiro que respondeu.

O texto dos turnos de conversa é apagado no prazo de retenção exibido na tela.
O que fica depois disso é a evidência de que você praticou: quando praticou, o
que a verificação automática apontou e a sua própria avaliação do turno.

## Antes de trocar de navegador ou apagar dados

1. Abra o indicador de conectividade e confirme que não há respostas pendentes ou
   bloqueadas.
2. Confira rascunhos locais e conflitos de escrita.
3. Baixe gravações que ficaram somente na tela.
4. Exporte o que for necessário em **Meus dados**.
5. Só então limpe os dados deste dispositivo.
