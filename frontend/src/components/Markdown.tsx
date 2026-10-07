import { Fragment, type ReactNode } from 'react'

/**
 * Renderiza o subconjunto de Markdown que o banco guarda:
 * `**negrito**`, `*itálico*`, `` `código` `` e `~~riscado~~`.
 *
 * Produz nós do React, nunca HTML — não existe `dangerouslySetInnerHTML` em
 * lugar nenhum deste projeto, então texto vindo do banco não vira markup.
 */

type Regra = {
  re: RegExp
  tag: 'strong' | 'em' | 'code' | 'del'
  classe?: string
  /** `code` é literal: nada dentro dele é interpretado. */
  recursivo: boolean
}

const REGRAS: Regra[] = [
  { re: /\*\*(.+?)\*\*/, tag: 'strong', classe: 'md-hl', recursivo: true },
  { re: /`([^`]+)`/, tag: 'code', recursivo: false },
  { re: /~~(.+?)~~/, tag: 'del', recursivo: true },
  // Um asterisco só, sem outro grudado de nenhum lado — senão come o negrito.
  { re: /(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/, tag: 'em', recursivo: true },
]

function parse(texto: string): ReactNode[] {
  let melhor: { regra: Regra; m: RegExpMatchArray; at: number } | null = null
  for (const regra of REGRAS) {
    const m = texto.match(regra.re)
    if (m?.index === undefined) continue
    if (melhor === null || m.index < melhor.at) melhor = { regra, m, at: m.index }
  }
  if (!melhor) return texto ? [texto] : []

  const { regra, m, at } = melhor
  const Tag = regra.tag
  const dentro = m[1] ?? ''
  return [
    ...parse(texto.slice(0, at)),
    <Tag key={`${Tag}-${at}`} className={regra.classe}>
      {regra.recursivo ? parse(dentro) : dentro}
    </Tag>,
    ...parse(texto.slice(at + m[0].length)),
  ]
}

export function Markdown({ children }: { children: string | null | undefined }) {
  if (!children) return null
  return (
    <>
      {parse(children).map((n, i) => (
        <Fragment key={i}>{n}</Fragment>
      ))}
    </>
  )
}
