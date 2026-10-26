/**
 * Política de leitura, uma só para todas as consultas do app.
 *
 * `networkMode: 'always'` — a consulta roda mesmo com o navegador se dizendo
 * offline: há o cache do service worker atrás dela, e uma leitura que o SW
 * pode responder não deve ficar pausada esperando a rede voltar.
 *
 * `retry: false` — a interface mostra o erro com o `request_id` e oferece
 * "tentar novamente" explícito. Repetir sozinho esconde a falha do aluno e
 * multiplica requisições numa rede ruim; as escritas idempotentes já têm a
 * retomada da fila offline.
 *
 * O `QueryClient` em `main.tsx` guarda só o que é de cache (`staleTime`,
 * `refetchOnWindowFocus`); quem precisa de dado sempre fresco declara
 * `staleTime: 0` no próprio hook.
 *
 * Vive num módulo sem dependências, e não em `queries.ts`, porque vários
 * testes substituem `queries.ts` inteiro por mock: uma constante de política
 * não pode desaparecer junto com os hooks.
 */
export const READ_POLICY = { networkMode: 'always', retry: false } as const
