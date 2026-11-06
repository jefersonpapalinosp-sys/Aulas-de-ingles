# Deploy seguro e rollback — Sprint 55

Código preparado em 05/11/2026. **Instalação e aceite na VM ainda pendentes.**
Este procedimento substitui o deploy SSH livre da Sprint 45. Execute primeiro
em ambiente de ensaio; não misture este controlador com redeploy automático
do painel, que alteraria os containers fora dos recibos.

## Preparação do servidor

O host precisa de Linux, Python 3.12+, Git, Docker Engine/Compose v2 e Trivy
0.76.0 instalado por fonte verificada. O usuário operacional `aulas-deploy`
deve ter acesso ao grupo `docker`, ao clone de leitura de `origin/main`, ao
estado de releases e à configuração do painel. Acesso ao Docker equivale a
privilégio administrativo no host: o comando SSH reduz o uso da chave, mas
não é isolamento contra código malicioso aprovado na main.

Com administração local do host, criar o usuário sem senha de login, adicionar
ao grupo Docker e preparar `/var/lib/aulas-deploy/{repository,state}` com dono
`aulas-deploy`, modo 0700. O clone deve apontar para o repositório oficial,
com credencial somente de leitura; nunca aceitar URL/branch vindos do cliente.
Manter Python, Git, Docker e Trivy em diretórios graváveis apenas por root.

Instalar uma cópia revisada do pacote `ops/` em `/opt/aulas-deploy/ops`, com
arquivos root:root 0644 e diretórios 0755. Não usar symlink para o checkout
gravável. Instalar `infra/ssh/aulas-deploy-command` em
`/usr/local/libexec/aulas-deploy-command`, root:root 0755, com finais LF.
Atualizar essa instalação separadamente quando o protocolo mudar.

Copiar `config/deploy-server.example.json` para `/etc/aulas-deploy.json`,
root:root 0644. Conferir os seis caminhos/projeto com a instalação real.
O arquivo de ambiente referenciado deve ser regular, modo 0600 e legível
por `aulas-deploy`; o override precisa ser legível. Pais desses caminhos não
podem ser graváveis por usuários não confiáveis. O arquivo `.env` pode
continuar no diretório do painel, mas nunca entra no Git nem na release.

Usar chave exclusiva de deploy. Instalar a pública em `authorized_keys`
conforme `infra/ssh/authorized_keys.example`, com `restrict,command=...`.
Preferir `AuthorizedKeysFile` em caminho administrado por root para este
usuário; não habilitar login por senha, forwarding ou outras chaves livres.
A chave aceita somente `deploy <SHA completo>` e `rollback`; shell, SCP,
upload de arquivo, comandos concatenados e `adopt` remoto são recusados.
Validar a configuração de sshd antes de recarregá-la, mantendo acesso
administrativo separado até concluir o ensaio.

## Adoção e migração do nginx

Antes de armar o CI, conferir uma stack saudável e adotar suas imagens atuais
pelo console administrativo, executando como usuário operacional:

```sh
sudo -u aulas-deploy /usr/bin/python3 -I -c 'import sys; sys.path.insert(0,"/opt/aulas-deploy"); from ops.deploy_server import main; sys.argv=["deploy_server","adopt"]; raise SystemExit(main())'
```

A adoção preserva os IDs das imagens de API, worker e web com tags locais,
copia o Compose vigente e escreve `state/current.json`. Não reconstrói imagens.
O comando recusa uma segunda adoção. Conferir nomes `${project}-{service}-1`
e volumes gerados pelo Compose antes da instalação.

O nginx passa a executar com UID/GID **101:101**, sem capabilities, raiz
somente leitura e tmpfs próprios. Volumes novos recebem o dono da imagem;
o volume `web_assets` antigo precisa de migração única de proprietário pelo
operador. Primeiro conferir o nome e labels do volume, backup e janela; parar
apenas o web, ajustar para 101:101 somente esse volume público e reiniciar.
Não aplicar chown em `pgdata`, gravações ou diretórios do host. O pré-voo do
deploy verifica a escrita nesse volume antes de parar o worker/migrar.

Preservar a versão anterior e o volume de assets. Não executar prune de imagens
com `-a` nem remover tags `aulas-preserved/*` enquanto forem necessárias ao
rollback. Limpeza de releases exige conferir `current`, `previous` e `pending`.

## Configuração no GitHub e no cliente

Em `production`, configurar required reviewers, impedir autoaprovação e
restringir publicação à main. Configurar também proteção da main com os seis
jobs obrigatórios. Esses controles são configurações do GitHub, não efeitos
do YAML; na consulta de 05/11 a main ainda estava sem proteção. Ver
[proteções de environment](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments).

Secrets: `PUBLIC_DEPLOY_SSH_KEY`, `PUBLIC_DEPLOY_KNOWN_HOSTS`,
`PUBLIC_DEPLOY_HOST` (`aulas-deploy@host`) e `PUBLIC_PROBE_ORIGIN` (origem HTTPS).
Conferir a impressão digital do host por canal independente antes de cadastrar
known_hosts. Sem chave, CI informa deploy desarmado; com chave e configuração
incompleta, falha. O host não tem valor padrão e `root@...` é recusado.

No cliente Linux/macOS, configurar chave/known_hosts e exportar
`AULAS_PUBLIC_SSH_HOST` e `AULAS_PUBLIC_URL`. Atualizar `origin/main` e usar:

```sh
make deploy-public-dry-run sha=<sha>
make deploy-public sha=<sha>
make deploy-public-rollback
# equivalente: bash ops/deploy_public.sh --rollback
```

O dry-run valida o SHA e mostra o comando permitido sem contatar a VM.
`--skip-smoke` existe para diagnóstico explícito; não constitui aceite público.
O backup remoto também exige host explícito sem root. A chave restrita de
deploy não serve para os comandos de backup; preferir o timer local da Sprint
54 e seu destino cifrado separado.

## Sequência e recuperação

O servidor usa lock não bloqueante liberado pelo kernel e limite total de
30 minutos. Busca a main e verifica novamente a ancestralidade do SHA,
extrai o Git archive sem links/segredos e constrói imagens com tags exclusivas.
Antes de alterar serviços, exige sucesso do Trivy CRITICAL em todas as imagens
candidatas e da permissão do volume do nginx. Falha de build/scanner mantém
a release atual em execução.

Depois registra `previous.json` e `pending.json`, para o worker com grace
period, executa migration e grants, sobe apenas API/worker/web por IDs imutáveis,
confere saúde, executa seed e verifica os IDs efetivos. Só então substitui
`current.json` e remove o pending. Banco não é recriado pelo deploy; atualização
da imagem do PostgreSQL requer procedimento próprio. A janela de schema
incompatível ainda pode produzir 503 durante migration; o build já ocorreu.

Os comandos [Compose up](https://docs.docker.com/reference/cli/docker/compose/up/)
usam `--no-build --no-deps --pull never --wait`. Os one-shots usam
[Compose run](https://docs.docker.com/reference/cli/docker/compose/run/) sem
dependências. Não há downgrade de banco, remoção de volumes ou rollback
automático após falha de migration.

Se a fase posterior ao build falhar, manter os recibos e diagnosticar pelo
console administrativo; `state/phase.json` registra a última fase mesmo quando
o SSH falha. O worker pode estar parado. `--rollback` inicia uma
API temporária da imagem anterior, sem publicar portas, e exige
`status=ok`, `db=up`, `schema=compatible` no banco atual. Só depois substitui
os três serviços, confere saúde/IDs e registra a versão restaurada. Se o schema
não for compatível, recusa a troca: seguir recuperação da Sprint 54 ou publicar
correção após ensaio. Não apagar `pending.json` para contornar esse estado.

Segredos e override atuais continuam sendo usados no rollback; não são
versionados nem restaurados pelo controlador. Evitar edição no painel durante
a operação. Um redeploy do painel invalida os recibos e requer reconciliação
administrativa antes de voltar a usar o controlador.

## Aceite operacional pendente

Em uma VM de ensaio, provar acesso com usuário sem root, recusa de shell/SCP,
lock em duas sessões, timeout, build que falha sem interrupção, deploy aceito
com os gates e rollback compatível abaixo de cinco minutos. Conferir volumes,
grants, seed, autenticação e smokes HTTPS, além da aprovação pelo environment.
O laboratório local usa API sintética: comprova a orquestração e o nginx,
mas não substitui esse ensaio com banco/aplicação reais e SSH restrito.
