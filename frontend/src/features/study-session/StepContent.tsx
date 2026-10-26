import type { LessonDetail } from '../../api/client'
import { AssistirStep } from './steps/AssistirStep'
import { EstudarStep } from './steps/EstudarStep'
import { PraticarStep } from './steps/PraticarStep'
import { PrepararStep } from './steps/PrepararStep'
import { RevisarStep } from './steps/RevisarStep'
import type { StudyStepSlug } from './studyProgress'

/** Um componente por passo do estudo.
 *
 * Antes era uma função de 240 linhas com cinco `if (step === ...)`, e cada
 * passo novo engordava a mesma. O despachante é a única parte que conhece a
 * lista de passos.
 */
export function StepContent({
  lesson,
  step,
  userId,
}: {
  lesson: LessonDetail
  step: StudyStepSlug
  userId: number
}) {
  if (step === 'preparar') return <PrepararStep lesson={lesson} />
  if (step === 'assistir') return <AssistirStep lesson={lesson} userId={userId} />
  if (step === 'estudar') return <EstudarStep lesson={lesson} />
  if (step === 'praticar') return <PraticarStep lesson={lesson} userId={userId} />
  return <RevisarStep lesson={lesson} userId={userId} />
}
