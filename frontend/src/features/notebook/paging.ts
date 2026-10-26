import { useRef } from 'react'

/**
 * "Carregar mais" que termina anunciando o total e levando o foco até ele.
 *
 * Sem isso, quem navega por teclado ou leitor de tela clica no botão e não
 * recebe retorno: os itens novos entram abaixo do ponto de foco e o botão
 * continua ali. O foco no `role="status"` dá o retorno e deixa o leitor na
 * borda da lista recém-crescida.
 */
export function useAnnouncedPaging(fetchNext: () => Promise<unknown>) {
  const statusRef = useRef<HTMLParagraphElement>(null)
  async function loadMore(): Promise<void> {
    await fetchNext()
    requestAnimationFrame(() => statusRef.current?.focus())
  }
  return { statusRef, loadMore }
}
