import { useState } from 'react'
import type { Phrase, PronunciationNote, VocabItem } from '../api/client'
import { useAdicionarItem } from '../api/review'
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
  const adicionar = useAdicionarItem()
  const [postos, setPostos] = useState<Set<number>>(new Set())

  return (
    <div className="tw" role="region" aria-label="Vocabulário da aula" tabIndex={0}>
      <table className="vocab">
        <thead>
          <tr>
            <th scope="col">Termo</th>
            <th scope="col">Tradução</th>
            <th scope="col">Na aula</th>
            <th scope="col">Deck</th>
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
              <td>
                <button
                  type="button"
                  className="add-deck"
                  disabled={adicionar.isPending || postos.has(v.id)}
                  aria-label={`Adicionar "${v.term}" ao deck de revisão`}
                  onClick={() =>
                    adicionar.mutate(v.id, {
                      onSuccess: () => setPostos((p) => new Set(p).add(v.id)),
                    })
                  }
                >
                  {postos.has(v.id) ? 'no deck' : '+ revisar'}
                </button>
              </td>
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
