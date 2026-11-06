# Sprint 54 — continuidade, backup e recuperação

Implementação e validação local em 05/11/2026. O aceite operacional continua
pendente de instalação na VM, custódia separada, entrega do alerta e ensaio de DR
com tráfego. Próxima implementação por prioridade: Sprint 55.

## Entregas

- **OPS-02 / INF-03:** serviço/timer Linux a cada 12 horas, modo de captura local
  na VM e wrapper com lock liberado pelo kernel. Status só confirma sucesso após
  cópia cifrada externa verificada. Gate do cron expõe `last_backup_age_hours`;
  ausência, falha recente, data inválida/futura ou idade acima de 24 h bloqueiam.
  Runbook define custódia independente da chave privada, que não entra no timer.
- **OPS-03:** `public_restore unseal/restore` abre um pacote com `age`, recusa
  conteúdo inseguro e restaura somente stack nova `aulas-dr-*`, aplicação parada,
  banco e voz vazios. Confere imagem, labels e conexões; aplica grants, compara
  snapshot e hashes e grava recibo cronometrado. Não promove tráfego.
- **OPS-07:** `--hold`/`hold=true` protege o backup pré-migration e suas cópias
  cifradas. A poda verifica holds novamente antes de remover. Liberação exige
  confirmar o identificador em cada raiz protegida.
- **OPS-10:** snapshot exportado compartilhado com `pg_dump --snapshot` mantém
  manifesto e dump consistentes sem exigir igualdade das contagens antes/depois.
  Mudança de voz, revisão ou containers continua recusando publicação.
- **OPS-11:** `lease-break` exige ID completo, label, container parado, idade
  mínima de uma hora e declaração explícita de que o proprietário terminou.
  Remove pelo ID imutável, preservando dados e volumes.
- **OPS-12:** retenção cifrada de sete diários e quatro semanais, mantendo o mais
  recente e holds, com prévia obrigatória por padrão. Só arquivos com recibo
  `.verified` e hash correspondente entram na seleção; parciais/legados são
  preservados. Cópia local e externa ganham recibos após a conferência.
- **OPS-08:** 13 fronteiras operacionais existentes passaram a emitir operação e
  categoria fixa de falha, sem mensagens arbitrárias, SQL, segredos ou traceback.
  Novas CLIs seguem a mesma sanitização.

Procedimentos e comandos estão em
[backup e recuperação pública](backup_recuperacao_publica_2026-11-05.md).

## Evidências locais

- Suíte operacional completa: **377 testes descobertos, 371 aprovados e 6
  opcionais ignorados** (contratos que exigem Docker/imagem explicitamente
  habilitados). Os testes cobrem falha de backup e gate crítico, hold criado após
  prévia, retenção cifrada, lease, snapshots e recusas de restore inseguro.
- Ruff de `ops/` aprovado. Mypy estrito aprovado nos **46 módulos operacionais**,
  com plataforma Linux, correspondente ao host de execução desses scripts.
- A primeira execução ampla identificou CRLF em dois scripts antigos de CI:
  oito falhas e dois erros de shell. A repetição usou cópia temporária com scripts
  em LF, como no checkout Linux. Os arquivos originais desses scripts não foram
  alterados; a portabilidade permanece no escopo da Sprint 58.
- Ensaio real local, sem rede externa: PostgreSQL 16.15, papéis separados,
  migration até `f53a1b8c9003`, uma conta e um WAV de silêncio. O ensaio inseriu
  uma segunda conta enquanto o snapshot estava aberto: origem terminou com duas,
  dump e destino restaurado continham exatamente uma. O áudio teve hash conferido.
- `age` real cifrou o pacote e decifrou sua cópia externa sintética. Dois ensaios
  completos aprovados mediram **6,285 s** e **11,506 s** para decifragem + restore.
  Na execução final, o restore do par banco/voz levou **10,921 s**; o laboratório
  inteiro, incluindo preparo e captura, levou **32,233 s**. Variação local impede
  tratar essa amostra como previsão de produção.
- Pacote sintético final: `aulas-20261105T211217831326Z-016e004c23d1418d910fdefabdcc4282`;
  manifesto SHA-256 `be58ce8e58b7874293f913ccef8610d421b1607dc3be5948f7229cb517a6dcd7`.
  Stack descartável `aulas-dr-target-decfdee7809c`; `verified=true`, tráfego parado.

O controlador do laboratório adaptou somente os binds de `/tmp` para o Docker
Desktop e a localização dos containers sintéticos. O caminho de captura,
snapshot exportado, dump, `age`, restauração, grants e conferência foi o código
operacional. A fixture grava com UID 10001, como o armazenamento da aplicação.
Falhas iniciais de preparação ficaram restritas a recursos UUID do laboratório.

## Limites e próximo aceite

Não houve commit, push, deploy, instalação de timer/cron, envio de mensagem,
manipulação de chave real nem alteração em banco de estudo/produção. A pipeline
remota não foi executada. Não se alterou schema da aplicação nesta sprint.

O laboratório não inicia a stack pública completa nem mede obtenção da chave,
provisionamento de VM, recuperação de imagens, conexão SSH, DNS, autenticação ou
tráfego real. Confirmar esses itens com o runbook, medir RTO completo e demonstrar
alerta recebido antes de encerrar o aceite operacional. O timer e o cron são
modelos prontos para instalação, ainda não evidência de agendamento ativo.

O pacote é banco + voz. Configuração, segredos e imagens precisam de custódia
separada. Backups cifrados antigos, sem recibos novos, não são apagados pela nova
poda. A retenção só é aplicada por comando explícito após revisar a lista.
