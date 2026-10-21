# Política operacional de exclusão e backups — ambiente de desenvolvimento

Data da decisão: 16/10/2026. Responsável: Jeferson.

## Escopo e limites

Esta política vale para o projeto local de estudo, com dados de teste, durante o
desenvolvimento. Ela descreve o comportamento técnico atual; não é parecer jurídico,
SLA nem certificação de conformidade. Antes de serviço público, é obrigatória uma
revisão de privacidade, segurança e operação.

Metas operacionais a validar:

- RPO de até 24 horas;
- RTO de até 60 minutos para recuperação completa;
- retenção manual de 7 backups diários e 4 semanais;
- cópias mantidas neste Mac enquanto o ambiente for somente de desenvolvimento.

Não há agendamento automático nem cópia externa. Portanto, as metas não são
consideradas atingidas sem execução diária e ensaio completo. FileVault protege o
disco em repouso, mas os pacotes não têm criptografia própria e uma falha ou perda do
Mac pode afetar origem e backup ao mesmo tempo.

### Atualização da Sprint 44 (21/10/2026)

- A janela de 7 diários + 4 semanais passou a ser executável: `make backup-prune`
  imprime o plano (nada é apagado) e `make backup-prune-apply` o executa. O pacote
  mais recente nunca é removido; `.partial-*` com menos de 24 h são preservados;
  recibos, pacotes de rollback nomeados por sprint e arquivos soltos ficam fora da
  política e são listados, não tocados.
- A stack pública passou a ter backup pela mesma rotina: `make backup source=public`
  lê o banco pelo papel `aulas_backup` dentro do container remoto e exporta a voz
  com o `voice_transfer.py` do fluxo local. Primeiro pacote verificado em 21/10/2026.
- Credenciais dos papéis (`roles-*.env`, `roles-*.json`) saíram de `backups/` para
  `secrets/` (perm 700/600, ignorado pelo Git). Chave e cofre não viajam juntos.
- Cópia externa só sai cifrada com `age` para um destinatário cuja chave privada não
  mora no Mac (`recipient=secrets/backup-age-recipient.txt`). Instalar `age`,
  gerar o par fora do Mac e agendar a execução diária continuam pendentes.

## Contrato da exclusão de conta

1. A pessoa precisa estar autenticada, informar a senha atual, digitar exatamente
   `EXCLUIR MINHA CONTA` e confirmar novamente no navegador.
2. A API revalida a senha antes de abrir a transação destrutiva e confirma que o hash
   não mudou após a autenticação.
3. Perfil, sessões e dados pessoais relacionais são removidos na mesma transação por
   FKs com `ON DELETE CASCADE` já inventariadas.
4. Chaves opacas dos arquivos de áudio são copiadas para uma fila sem `user_id`,
   e-mail, texto ou outro identificador da conta antes da exclusão relacional.
5. A resposta `202` distingue banco já excluído com áudio concluído de
   `cleanup_pending`. O cookie de refresh é invalidado e o frontend encerra a sessão.
6. O worker remove os arquivos de forma idempotente. Arquivo já ausente é sucesso.
   Falhas usam espera exponencial e, após 10 tentativas, o recibo passa para `failed`.
7. O heartbeat expõe somente totais de operações pendentes e falhas; caminhos e
   chaves de armazenamento não entram em métricas ou respostas públicas.

O recibo anônimo não permite recuperar a identidade apagada. A chave UUID devolvida
na resposta serve apenas para correlação operacional naquele momento e não deve ser
publicada em logs, tickets ou documentação versionada.

## Dados do navegador e downloads

A exclusão remota não apaga automaticamente outros dispositivos, abas abertas,
downloads já salvos ou armazenamento que o navegador não permitiu acessar. A tela
“Meus dados” oferece uma ação separada por conta para apagar rascunhos, fila offline,
posições, progresso local e gravação temporária. Um tombstone no IndexedDB impede
que fontes legadas compartilhadas restaurem a fila daquela conta; dados de outras
contas e o cache editorial público permanecem preservados.

Se qualquer armazenamento local estiver ilegível ou bloqueado, a interface não
declara limpeza completa. O usuário deve fechar outras abas, atualizar o inventário
e repetir a ação.

## Backups após uma exclusão

Backups são snapshots imutáveis: não serão editados registro a registro para apagar
uma conta. Eles podem conservar dados excluídos até saírem da janela de 7 diários e
4 semanais. Pacotes pré-migration podem ser mantidos além dessa janela enquanto o
rollout estiver em validação, sempre privados e identificados como não publicáveis.

Um restore é feito somente em ambiente isolado. Como o recibo atual é deliberadamente
anônimo, uma restauração pode reintroduzir dados que foram excluídos depois do
snapshot. Durante a fase de desenvolvimento:

- nunca promover diretamente o clone restaurado para o ambiente de uso;
- manter o clone isolado e sem acesso público;
- deixar o backup expirar pela retenção ou repetir a exclusão somente após o titular
  confirmar a conta restaurada;
- não tentar inferir a identidade a partir de arquivos, logs ou chaves opacas.

Antes de produção pública, implementar um mecanismo de reconciliação de exclusões
compatível com privacidade e restauração, além de cópia externa criptografada com
chave separada. Essa evolução não pode reintroduzir e-mail ou conteúdo pessoal no
recibo anônimo atual sem nova decisão de segurança.

## Monitoramento e tratamento de falha

O operador consulta somente agregados do heartbeat. Uma contagem `failed > 0`
mantida após a janela operacional exige investigação do filesystem e manutenção
controlada; não é aceitável apagar o recibo para esconder a falha.

Depois de corrigir a causa física, uma retomada manual só pode usar a UUID exata do
recibo entregue e previamente conferida. O owner/migrador pode, em transação, zerar
`attempt_count`, `next_attempt_at` e `last_error_code` das tarefas remanescentes e
voltar o job de `failed` para `cleanup_pending`. Nunca executar atualização sem
selecionar e bloquear primeiro uma única `operation_key` conhecida.

O prazo operacional inicial para áudio é de até 60 minutos, como alvo a validar. A
exclusão relacional é confirmada na resposta da API; um áudio pendente ou falho deve
ser comunicado separadamente, sem afirmar conclusão integral.

## Evidências mínimas por mudança

- migration upgrade/downgrade protegido em PostgreSQL descartável;
- senha inválida sem mutação; exclusão com e sem áudio; cascades e revogação de sessão;
- retry limitado, unlink idempotente e métrica agregada de falha;
- tombstone e isolamento entre contas no navegador;
- teste de privilégios com runtime, worker e backup separados;
- backup verificado e restore isolado antes de migration em qualquer ambiente de uso.

Os procedimentos gerais de backup, restore e papéis continuam em
[operacao_sprint_37.md](operacao_sprint_37.md). Esta política complementa o runbook;
não autoriza apagar backups, volumes ou dados fora do alvo confirmado.
