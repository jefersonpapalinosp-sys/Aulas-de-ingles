# Expansão pedagógica das Aulas 32–40

Data de implementação: 8 de outubro de 2026  
Backlog: item 2 da fila de fechamento

## Resultado da etapa

Cada Aula 32–40 passou a oferecer:

- três atividades de listening: compreensão existente, ditado e uma nova questão contextual;
- uma atividade de ordenação de palavras;
- uma atividade de transformação gramatical;
- uma proposta de escrita de 5 a 7 frases, com mínimo de 40 a 50 palavras;
- requisitos verificáveis ligados ao objetivo gramatical da aula;
- duas dicas graduais em cada atividade adicionada;
- prática de speaking e shadowing a partir dos trechos de áudio cronometrados já associados à aula.
- transcrição integral em inglês, recolhível no player e creditada à página oficial.

| Aula | Foco da escrita | Listening | Exercícios | Escrita |
|---:|---|---:|---:|---:|
| 32 | pergunta, resposta e objetos direto/indireto | 3 | 11 | 1 |
| 33 | explicar um jogo em sequência | 3 | 11 | 1 |
| 34 | planos certos e possibilidades | 3 | 11 | 1 |
| 35 | lista de compras e quantidades | 3 | 11 | 1 |
| 36 | localização e oferta imediata | 3 | 11 | 1 |
| 37 | opinião sobre cidade e interior | 3 | 11 | 1 |
| 38 | descrição com superlativos | 3 | 11 | 1 |
| 39 | avaliação de compra online | 3 | 12 | 1 |
| 40 | direções de atuação com advérbios | 3 | 12 | 1 |

No bloco completo das Aulas 31–40, o seed agora contém 110 exercícios, 133 respostas aceitas,
107 dicas graduais, 29 atividades marcadas como listening, 10 propostas de escrita e 289 falas
de transcrição integral nas Aulas 32–40.

## Funcionamento no frontend

Não foi necessário criar uma nova tela. O contrato existente renderiza automaticamente:

- múltipla escolha com opções nativas;
- ordenação por botões acessíveis;
- ditado e transformação com campo de resposta e correção no servidor;
- escrita guiada com contagem de palavras, frases, requisitos, rascunho e versões;
- player com trechos selecionados e área de shadowing/gravação.
- transcrição integral recolhível, com identificação de falante, rolagem própria e crédito.

Assim, o conteúdo novo fica disponível nas rotas de estudo das respectivas aulas após executar o
seed. Os estados de carregamento, erro, resposta, dicas e progresso continuam sendo os mesmos já
cobertos pelo frontend.

## Política e procedência das transcrições

As transcrições foram extraídas da seção “Conversation” das páginas oficiais e mantêm a ordem dos
turnos. O produto preserva também 48 trechos curtos e cronometrados para navegação, tradução,
speaking e shadowing.

A página [Request Our Content — VOA Learning English](https://learningenglish.voanews.com/p/6861.html)
informa que textos, MP3s, fotos e vídeos da VOA Learning English estão em domínio público e podem
ser republicados para fins educacionais ou comerciais com crédito. A mesma política exclui
materiais de AP, Reuters, AFP e outros terceiros. Estas lições são conversas produzidas pela série
*Let's Learn English* e são apresentadas com crédito e link para a origem.

Regras editoriais adotadas:

1. não importar fotos, vídeos ou matérias de agência terceirizada;
2. creditar a VOA Learning English no frontend e nos metadados da API;
3. manter URL da página, data de acesso e nota de licença;
4. conservar os exercícios, traduções e explicações autorais separados da transcrição oficial;
5. revisar ou retirar uma transcrição se sua página de origem ou condição de uso mudar.

## Critérios automatizados

Os testes devem garantir que:

- as Aulas 32–40 tenham exatamente uma proposta de escrita;
- cada uma tenha três exercícios de listening;
- ditado, ordenação, transformação e múltipla escolha estejam presentes;
- cada Aula 32–40 exponha ao menos 20 falas de transcrição em ordem;
- a escrita exija ao menos 40 palavras, 5 frases e 2 requisitos;
- o seed preserve os identificadores ao ser executado novamente;
- respostas corretas não sejam expostas pelos endpoints de leitura.
