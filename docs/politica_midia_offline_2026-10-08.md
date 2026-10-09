# Política de licença e mídia offline

Data da revisão: 8 de outubro de 2026  
Backlog: item 5 da fila de fechamento

## Decisão

As 22 mídias das Aulas 31–52 pertencem ao recorte publicado do curso *Let's Learn English —
Level 1* e são identificadas nas páginas oficiais como produção da VOA Learning English. Os termos
oficiais informam que material
produzido exclusivamente pela VOA é domínio público e deve receber crédito; conteúdo de terceiros
permanece protegido e não pode ser redistribuído sem autorização.

O projeto registra essas 22 mídias como `public_domain`, atribui “Voice of America (VOA Learning
English)” e mantém `offline_policy=network_only`. A licença compatível é condição necessária, mas
não suficiente, para armazenamento offline.

Fontes revisadas:

- curso oficial: https://learningenglish.voanews.com/p/5644.html
- termos da VOA Learning English: https://learningenglish.voanews.com/p/6021.html

## Modelo fail-closed

Cada `lesson_media` precisa declarar:

| Campo | Valores/uso |
|---|---|
| `license_status` | `public_domain`, `permission_granted`, `restricted` ou `review_required` |
| `license_url` | página oficial que sustenta a decisão |
| `license_note` | resumo da autorização e das exceções |
| `attribution` | crédito mostrado ao aluno |
| `license_reviewed_at` | data da última verificação |
| `offline_policy` | `network_only` ou `cache_allowed` |

O banco impede `cache_allowed` para licença `restricted` ou `review_required`. Conteúdo novo deve
entrar como `review_required` e `network_only`; ausência de metadados faz o seed falhar.

## Regra de cache

O service worker exclui áudio e vídeo independentemente do domínio ou do status de licença. Uma
mídia só poderá migrar para `cache_allowed` quando todos estes controles existirem:

1. revisão documental por arquivo, incluindo ausência de material de terceiros;
2. ação explícita “Baixar para uso offline”, nunca download silencioso;
3. tamanho informado antes da confirmação e limite global de armazenamento;
4. tela para listar e remover downloads;
5. tratamento de expiração, mudança de licença e nova versão editorial;
6. origem técnica aprovada, sem depender de hotlink instável ou resposta opaca não verificável;
7. testes de quota, interrupção, integridade e limpeza do cache.

Gravações privadas do aluno, transcrições assistidas e qualquer mídia `restricted` nunca entram
nesse cache de conteúdo.

## Experiência na interface

O player possui uma seção nativa expansível “Fonte, licença e uso offline”. Ela mostra atribuição,
nota da licença, link para os termos e informa que o arquivo atual é reproduzido somente online.
Isso evita que a capacidade jurídica seja confundida com uma promessa técnica de disponibilidade.

## Decisão sobre Storybook

Storybook não foi adotado nesta etapa. O frontend possui cinco componentes compartilhados
(`ExerciseCard`, `GrammarBlockView`, `LessonRail`, `LessonSections` e `Markdown`) e cinco
componentes de feature. Os estados interativos críticos já estão cobertos por Vitest e pelos E2E;
introduzir outro build, dependências e manutenção não reduz risco suficiente agora.

Reavaliar a decisão quando ocorrer pelo menos uma destas condições:

- mais de 12 componentes reutilizáveis com variantes visuais;
- segundo tema ou marca;
- colaboração frequente com design fora do repositório;
- necessidade de regressão visual automatizada por componente;
- duplicação comprovada de estados de loading, vazio, erro ou acessibilidade.

## Evidência de fechamento

- migration com constraints de licença e política offline;
- seed das 22 mídias com fonte, crédito e data de revisão;
- contrato OpenAPI e tipos frontend atualizados;
- player torna origem e política visíveis;
- teste impede remoção acidental da exclusão de áudio/vídeo do service worker;
- documentação de PWA, plano evolutivo e README reconciliados.
