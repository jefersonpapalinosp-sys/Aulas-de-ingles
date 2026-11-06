# Listening rápido — catálogo externo A2

A Sprint 59 acrescenta `/listening`, independente dos cursos VOA. O menu abre
o catálogo; no celular, abra a trilha e escolha **Listening rápido**. Busque um
assunto ou filtre **Não iniciada**, **Em andamento** e **Concluída por mim**.

**Abrir no Test-English** abre uma nova aba. Abrir o link não muda o progresso.
Depois da prática, escolha sua marcação e aguarde **Marcação confirmada**.
Ela pode ser desfeita. Não há importação de nota ou tempo, crédito de estudo,
alteração de competências, revisão espaçada ou certificado VOA.

Sem rede, as marcações ficam bloqueadas. O catálogo visto nesta sessão pode
continuar na memória; não há promessa de acesso após fechar/recarregar offline.
Em falha de envio, **Tentar salvar novamente** repete a mesma operação enquanto
a tela estiver aberta. Após recarregar, consulte o estado confirmado da conta.
Um conflito entre abas exige conferir o estado atualizado e escolher novamente.

## Conteúdo e conferência

O [catálogo A2 do Test-English](https://test-english.com/listening/a2/) e as
31 páginas de destino foram consultados em 05/11/2026. O inventário versionado
está em [seed/listening-a2.json](../seed/listening-a2.json): 31 identificadores e
URLs distintos, títulos e descrições autorais, tema, nível atribuído pela fonte,
data da conferência e disponibilidade. A consulta verifica a página de destino;
não equivale a ouvir/validar todos os vídeos, gabaritos ou a duração pedagógica.
Não exibimos durações estimadas como se tivessem sido medidas.

São compartilhados links. Nenhum vídeo, imagem, questão, transcrição ou resposta
do Test-English é copiado, incorporado por iframe, espelhado ou armazenado em
cache. A CSP não recebe novas permissões. A disponibilidade é editorial, da
última conferência; o aplicativo não rastreia o site a cada acesso do aluno.

Para sinalizar uma página indisponível, altere `availability` para `unavailable`,
atualize `checked_on` e incremente `version` no seed. Aplique pelo procedimento
editorial de release. O card preserva o histórico e oculta o link. Manter o slug
preserva a identidade; omitir uma linha do seed não a exclui automaticamente.
Reaplicar a mesma versão não gera DML; mudar conteúdo exige versão maior.

## Dados e contrato

- `listening_resource`: metadados do catálogo, chave textual estável.
- `listening_progress`: estado atual, único por aluno/recurso, revisão e data.
- `listening_operation`: recibo imutável por aluno/chave UUID, para reenvio seguro.

`GET /api/listening/config` informa a ativação. Catálogo e detalhe ficam em
`GET /api/listening/resources` e `GET /api/listening/resources/{slug}`.
`GET /api/me/listening/progress` lê somente o estado da conta autenticada.
`PUT /api/me/listening/progress/{slug}` exige `state`, `expected_revision` e
`operation_key`. A primeira escrita usa revisão zero; conflito retorna 409.
O mesmo recibo pode ser repetido após alterações posteriores sem desfazê-las.
O cliente relê o estado atual após cada tentativa. Todos esses GETs são
autenticados e `private, no-store`; dados pessoais não entram no cache da PWA.

A exportação completa em **Meus dados** inclui `listening_progress` e
`listening_operations`, também com o módulo desativado. A versão de catálogo
e o URL exportados são referências editoriais atuais, não uma nota histórica.
Os recibos permanecem até a exclusão da conta; entram no limite já existente
da exportação síncrona. As duas tabelas pessoais usam FK com `ON DELETE CASCADE`;
excluir a conta não remove o catálogo compartilhado.

## Ativação e desativação

O padrão é **desativado**. O menu continua acessível e explica a indisponibilidade.
Esta entrega de código não executou migration nem ativou o módulo no ambiente
de estudo ou na produção pública.

1. Faça backup e ensaie a release em clone, conforme a sequência operacional
   existente. A migration expansiva é `d59a1b8c9007`, após `c56b1c8d9006`.
2. Execute migration e `alembic check` com o papel migrador. O seed padrão
   (`python -m app.cli seed`, sem `--file`) carrega também `listening-a2.json`.
   O `seed --dry-run` existente continua sendo a prévia do currículo VOA;
   não apresenta um plano do catálogo de listening.
3. Confira as 31 entradas e os privilégios: runtime lê o catálogo, escreve
   progresso e insere recibos; worker não acessa os dados de listening;
   backup tem leitura. O runtime não edita o catálogo nem recibos existentes.
4. Após o aceite, use `LISTENING_ENABLED=true` em desenvolvimento/estudo ou
   `EASYPANEL_LISTENING_ENABLED=true` no EasyPanel, recriando a API pela release.
   A stack E2E já usa a flag ativa com banco exclusivo e contas sintéticas.

Desative pela mesma flag com valor `false`. Isso preserva os dados e os fluxos
de exportação/exclusão. Não faça downgrade do schema para desligar a funcionalidade:
a migration recusa downgrade quando existem marcações ou recibos pessoais.
O backup PostgreSQL existente inclui automaticamente as três tabelas; não há
novos arquivos de mídia para copiar. A recuperação operacional permanece sujeita
ao ensaio de restore da release antes da publicação.

## Verificação

Na base exclusiva de testes, após `make test-api-prepare`:

```sh
cd backend
uv run pytest tests/test_sprint59.py tests/test_personal_export.py tests/test_database_isolation.py
```

Frontend: `npm run test:coverage`, `npm run lint`, `npm run build`,
`npm run check:api` e `npm run check:budget`. No PowerShell use `npm.cmd`.
E2E Linux/WSL: prepare a stack com `make e2e-up` e execute
`cd e2e && npx playwright test testes/sprint59-listening.spec.ts`.
Os testes usam uma página externa sintética e não dependem de vídeos de terceiros.

Listening é carregado sob demanda, com teto próprio de **3 KiB gzip**.
Entrada permanece em **132 KiB**, base em **184 KiB** e diálogo em **8 KiB**;
o conjunto passa a **195 KiB**. A reserva do listening não pode pagar crescimento
da base, e carregá-lo na entrada reprova o gate.

## Piloto dentro do aplicativo (Sprint 60)

O [piloto nativo](listening_nativo.md) é independente deste catálogo externo.
Ele oferece três atividades próprias em prévia local, com áudio e correção no
servidor. Seus rascunhos aguardam revisão humana; as flags são separadas e
continuam desativadas por padrão. O catálogo da Sprint 59 pode ser utilizado
enquanto o aceite editorial do piloto permanece pendente.
