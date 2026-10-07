import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useAvaliar, useDueCards } from '../api/review'
import { Carregando, Erro } from '../components/States'

/**
 * Tela de revisão.
 *
 * As notas visíveis são quatro, não seis: pedir ao estudante que escolha
 * entre 0, 1 e 2 para "errei" não melhora o agendamento e atrasa a revisão.
 * O que vai para o SM-2 é a nota da direita.
 */
const NOTAS = [
  { tecla: '1', rotulo: 'Errei', quality: 1, classe: 'errei' },
  { tecla: '2', rotulo: 'Difícil', quality: 3, classe: 'dificil' },
  { tecla: '3', rotulo: 'Bom', quality: 4, classe: 'bom' },
  { tecla: '4', rotulo: 'Fácil', quality: 5, classe: 'facil' },
] as const

function emQuantoTempo(dias: number): string {
  if (dias === 1) return 'amanhã'
  if (dias < 30) return `em ${dias} dias`
  if (dias < 365) return `em ${Math.round(dias / 30)} meses`
  return `em ${(dias / 365).toFixed(1)} anos`
}

export function ReviewPage() {
  const { data: cartas, isPending, error, refetch } = useDueCards()
  const avaliar = useAvaliar()
  const [virada, setVirada] = useState(false)
  const [ultima, setUltima] = useState<string | null>(null)

  const carta = cartas?.[0]

  const responder = useCallback(
    (quality: number) => {
      if (!carta) return
      avaliar.mutate(
        { cardId: carta.id, quality },
        {
          onSuccess: (d) => {
            setUltima(`${carta.term} volta ${emQuantoTempo(d.interval_days)}`)
            setVirada(false)
          },
        },
      )
    },
    [carta, avaliar],
  )

  useEffect(() => {
    function aoTeclar(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement) return
      if (!virada && (e.key === ' ' || e.key === 'Enter')) {
        e.preventDefault()
        setVirada(true)
        return
      }
      if (virada) {
        const nota = NOTAS.find((n) => n.tecla === e.key)
        if (nota) {
          e.preventDefault()
          responder(nota.quality)
        }
      }
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [virada, responder])

  if (isPending) return <Carregando oque="as cartas de hoje" />
  if (error) return <Erro erro={error} aoTentarDeNovo={() => void refetch()} />

  if (!carta) {
    return (
      <>
        <p className="eyebrow">Revisão espaçada</p>
        <h1>Nada para revisar agora</h1>
        <p className="lead">
          {ultima
            ? `Deck zerado. ${ultima}.`
            : 'Marque uma aula como estudada na barra lateral — o vocabulário dela entra no deck.'}
        </p>
        <p className="navbtns">
          <Link className="btn ghost" to="/">
            ← Mapa do bloco
          </Link>
        </p>
      </>
    )
  }

  return (
    <>
      <p className="eyebrow">
        Revisão espaçada · {cartas.length} {cartas.length === 1 ? 'carta' : 'cartas'} hoje
      </p>
      <h1>Revisar</h1>
      {ultima && <p className="ultima">{ultima}</p>}

      <div className="carta">
        <p className="carta-origem">Aula {carta.lesson_number}</p>
        <p className="carta-termo">{carta.term}</p>
        <p className="carta-ipa">{carta.ipa}</p>

        {virada ? (
          <div className="carta-verso">
            <p className="carta-traducao">{carta.translation_pt}</p>
            <p className="carta-exemplo">“{carta.example_en}”</p>
          </div>
        ) : (
          <button className="btn virar" onClick={() => setVirada(true)}>
            Mostrar resposta
          </button>
        )}
      </div>

      {virada && (
        <div className="notas">
          {NOTAS.map((n) => (
            <button
              key={n.quality}
              className={`nota ${n.classe}`}
              onClick={() => responder(n.quality)}
              disabled={avaliar.isPending}
            >
              <span className="nota-rotulo">{n.rotulo}</span>
              <span className="nota-tecla">{n.tecla}</span>
            </button>
          ))}
        </div>
      )}

      <p className="atalhos">
        {virada ? '1–4 para avaliar' : 'espaço ou enter para virar a carta'}
        {' · '}
        <span>
          {carta.repetitions === 0
            ? 'primeira vez'
            : `${carta.repetitions} acertos, ${carta.lapses} tropeços`}
        </span>
      </p>
    </>
  )
}
