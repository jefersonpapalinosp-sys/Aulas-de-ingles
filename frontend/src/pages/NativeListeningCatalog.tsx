import { Link } from 'react-router-dom'
import { useNativeCatalog } from '../api/nativeListening'
import { NativeListeningHistory } from './NativeListeningHistory'
import { useOnline } from '../features/offline/useOnline'

export function NativeListeningCatalog({ userId }: { userId: number }) {
  const catalog = useNativeCatalog(userId)
  const online = useOnline()
  if (!online) return <NativeListeningHistory userId={userId} />
  if (catalog.isError) return <p role="status">Práticas dentro do aplicativo indisponíveis no momento.</p>
  if (!catalog.data) return null
  return <section aria-label="Práticas dentro do aplicativo">
    <h2>Pratique aqui</h2>
    <ul className="listening-grid">{catalog.data.map(item => <li key={item.slug} className="listening-card">
      <h3><Link to={`/listening/${item.slug}`}>{item.title}</Link></h3>
      <p>{item.topic} · {item.questions.length} questões{item.preview && ' · Prévia local para revisão'}</p>
    </li>)}</ul>
    <NativeListeningHistory userId={userId} />
  </section>
}
