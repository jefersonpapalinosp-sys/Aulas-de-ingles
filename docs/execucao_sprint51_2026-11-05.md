# Execução — Sprint 51: borda, sessão e autenticação

**05/11/2026. Código implementado e validado localmente.** Publicação e aceite no
Traefik real permanecem pendentes. Base: `012e54a` com as alterações locais da
Sprint 50 e FE-01 preservadas. Próxima implementação: **Sprint 52**.

## Entregas

| Item | Comportamento implementado |
|---|---|
| SEC-01 / BE-06 | nginx substitui `X-Forwarded-For` pelo endereço resolvido; a cadeia enviada pelo cliente não chega à API |
| INF-09 | IP do aluno só é extraído de um proxy explicitamente confiável; limite de borda passa a separar as origens |
| SEC-02 | replay fora da janela revoga toda a família de refresh, persistindo a revogação antes do 401; outro login permanece válido |
| SEC-02, prazo absoluto | descendentes herdam o vencimento da sessão raiz, em vez de ganhar mais 30 dias por rotação; famílias legadas também são limitadas pela raiz |
| SEC-04 / BE-01 | exclusão de conta consome os limites por identidade/origem antes do hash; senha incorreta retorna 403 com `code=password_mismatch`, sem renovar nem encerrar o login |
| SEC-05 | gateway não segue redirects; token e corpo não são reenviados ao destino de 301/302/303/307/308 |
| SEC-06 | `/docs`, `/redoc` e `/openapi.json` desabilitados quando `APP_ENV=prod` ou perfil público; geração programática do contrato preservada |
| INF-13 | timeouts explícitos, buffering de pedido/resposta desligado e nenhuma repetição automática do pedido pelo proxy |

OpenAPI e tipos do frontend foram regenerados. O formulário distingue senha
incorreta de excesso de tentativas e preserva a sessão nos dois casos.
Não foi necessária migration nem alteração de dados existentes.

A janela de concorrência de refresh continua em 10 segundos. Uma família sem
raiz disponível exige novo login. A revogação trata refresh tokens; access tokens
já emitidos continuam sujeitos ao prazo curto existente (15 minutos por padrão).
Os opcionais SEC-07/SEC-08 continuam fora desta entrega.

## Configuração obrigatória antes da publicação

O Compose público exige **`EASYPANEL_TRUSTED_PROXY_CIDRS`**. O nginx usa a lista
para confiar no peer de entrada e em seu `X-Forwarded-Proto`. Sem configuração,
o perfil público recusa a inicialização; rede universal e entradas inválidas
também são recusadas. Em uso direto/local, a lista vazia ignora headers de proxy.

1. Identificar os IPs do Traefik **como observados pelo container web**. Preferir
   endereços `/32` ou `/128`, ou uma rede dedicada que contenha somente proxies
   autorizados. Não presumir que toda a rede privada/Docker é confiável.
2. Preencher a variável no arquivo privado existente e no ambiente do painel.
   O gerador aceita `--trusted-proxy-cidrs` e `make easypanel-env proxy_cidrs=...`;
   sem esse argumento gera um arquivo incompleto, que o check recusa. Nunca
   recriar o arquivo existente para acrescentar a variável nem rotacionar os
   segredos por causa deste ajuste.
3. Conferir no Traefik que `forwardedHeaders.insecure` está desligado e que ele
   acrescenta o endereço observado à direita de `X-Forwarded-For`
   (`notAppendXForwardedFor` deve permanecer desligado, quando disponível).
   Se houver outro balanceador antes dele, revisar a cadeia explicitamente.
4. Executar `make easypanel-check`, publicar API/web juntos e validar HTTPS,
   login, refresh concorrente, upload e exclusão recusada em ensaio.
5. Variar `X-Forwarded-For` de uma mesma origem e confirmar que isso não renova
   sua quota. Confirmar que outra origem legítima continua atendida. Registrar
   a versão/configuração do Traefik e a evidência; isso não foi feito remotamente.

A estratégia assume um único proxy de entrada confiável: `real_ip_recursive off`
seleciona o último endereço enviado por ele. Esse comportamento está definido na
[documentação do nginx](https://nginx.org/en/docs/http/ngx_http_realip_module.html).
As opções a conferir no primeiro proxy estão na
[referência de entrypoints do Traefik](https://doc.traefik.io/traefik/reference/install-configuration/entrypoints/#forwarded-headers).

A API pública continua sem porta de host: somente o nginx deve receber tráfego
externo. A confiança interna do Uvicorn foi mantida, necessária também aos probes
internos; a correção de SEC-01 usa a alternativa de sobrescrever o cabeçalho no
nginx. Expor a API diretamente exigiria rever essa fronteira.

## Evidências locais

- **73 testes de backend em Linux:** autenticação, famílias de refresh, exclusão,
  gateway/redirects, concorrência, saúde e contrato OpenAPI (72 na seleção inicial
  e um cenário adicional de isolamento entre famílias após revisão).
- **10 testes focados de autenticação também passaram no Windows.** Testes de
  upload com verificação de áudio foram validados no Linux, onde roda o produto.
- **47 testes de frontend:** transporte autenticado e página Meus dados.
- **2 Playwright/Chromium:** formulário, provider de sessão e transporte reais;
  API sintética responde 403/429. A sessão continua ativa, com um único DELETE e
  nenhum refresh adicional. O harness bloqueia acesso à API real.
- **4 ensaios Docker de borda:** nginx + Uvicorn reais, rede interna isolada e
  nenhuma porta de host. Headers de peer não confiável são ignorados; prefixo
  forjado da cadeia é descartado; HTTPS confiável preservado; saturar uma origem
  não bloqueia a outra; configuração ausente/universal é recusada.
- **39 testes operacionais** e **4 testes de configuração Compose** aprovados.
- Ruff, mypy (107 módulos backend e 41 operacionais, alvo Linux), ESLint,
  TypeScript, sincronismo OpenAPI e build aprovados.
- Bundle gzip: inicial **129,0/132,0 KiB**, base **183,5/184,0 KiB**, conjunto
  **190,5/192,0 KiB**. Tetos mantidos. Aviso preexistente de chunk circular
  `lesson-study → writing → lesson-study` permanece.

O ensaio local da borda usou `nginx:1.28.0-alpine` e imagem Python local. O CI
passou a executar o mesmo teste com as imagens web/API construídas pelo projeto;
essa execução remota e a imagem completa de produção não foram comprovadas aqui.
O servidor HTTP local dos testes de redirect confirmou que somente o destino
original recebeu o token sintético; o bloqueio usa `HTTPRedirectHandler`, conforme
a [API do Python 3.12](https://docs.python.org/3.12/library/urllib.request.html#urllib.request.HTTPRedirectHandler).

Banco descartável: projeto `aulas-ingles-sprint51-test`, porta 55435, papel
limitado `aulas_test`, migrations/seed sob `app.testing`. Nenhum banco de estudo
ou de produção recebeu migrations, limpeza ou alteração de dados nesta entrega.
Os containers e redes dos ensaios foram encerrados; o volume sintético do banco
foi preservado. Publicação, commit/push e alteração de secrets remotos não foram
executados.
