import type { Phrase, PronunciationNote, VocabItem } from '../api/client'
import { Markdown } from './Markdown'

export function PhraseList({ frases }: { frases: Phrase[] }) {
  return (
    <div className="stack">
      {frases.map((f, i) => (
        <div className="line" key={i}>
          <p className="en">
            <Markdown>{f.text_en}</Markdown>
          </p>
          <p className="pt">{f.text_pt}</p>
          <p className="nt">
            <Markdown>{f.note}</Markdown>
          </p>
        </div>
      ))}
    </div>
  )
}

export function VocabTable({ itens }: { itens: VocabItem[] }) {
  return (
    <div className="tw">
      <table className="vocab">
        <thead>
          <tr>
            <th scope="col">Termo</th>
            <th scope="col">Tradução</th>
            <th scope="col">Na aula</th>
          </tr>
        </thead>
        <tbody>
          {itens.map((v) => (
            <tr key={v.id}>
              <td>
                <span className="termo">{v.term}</span>
                <span className="ipa">{v.ipa}</span>
              </td>
              <td>
                <Markdown>{v.translation_pt}</Markdown>
              </td>
              <td className="exemplo">“{v.example_en}”</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function PronunciationList({ notas }: { notas: PronunciationNote[] }) {
  return (
    <ul className="pron">
      {notas.map((n, i) => (
        <li key={i}>
          <span className="say">
            <Markdown>{n.label}</Markdown>
          </span>
          <span className="exp">
            <Markdown>{n.explanation}</Markdown>
          </span>
        </li>
      ))}
    </ul>
  )
}
