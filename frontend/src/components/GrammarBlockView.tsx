import type { GrammarBlock } from '../api/client'
import { Markdown } from './Markdown'

export function GrammarBlockView({ bloco }: { bloco: GrammarBlock }) {
  return (
    <article className="gram">
      <h3>
        <Markdown>{bloco.heading}</Markdown>
      </h3>
      <p className="why">
        <Markdown>{bloco.why}</Markdown>
      </p>

      {bloco.table_head && bloco.rows.length > 0 && (
        <div className="tw" role="region" aria-label="Tabela de gramática" tabIndex={0}>
          <table>
            <thead>
              <tr>
                {bloco.table_head.map((h) => (
                  <th key={h} scope="col">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bloco.rows.map((linha, i) => (
                <tr key={i}>
                  {linha.cells.map((celula, j) => (
                    <td key={j}>
                      <Markdown>{celula}</Markdown>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {bloco.warning && (
        <p className="warn">
          <Markdown>{bloco.warning}</Markdown>
        </p>
      )}
    </article>
  )
}
