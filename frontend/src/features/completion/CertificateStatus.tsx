import { Link } from 'react-router-dom'
import type { CourseCompletion } from '../../api/client'

export function CertificateStatus({ data }: { data: CourseCompletion }) {
  const certificate = data.certificate
  const externalCertificate = /^https?:\/\//i.test(certificate.cta_href)
  return (
    <section
      className={`completion-certificate ${certificate.status}`}
      id="certificado"
      aria-labelledby="certificate-title"
      tabIndex={-1}
    >
      <p className="eyebrow">Elegibilidade</p>
      <h2 id="certificate-title">
        Certificado do recorte: {certificate.eligible ? 'elegível' : 'ainda não elegível'}
      </h2>
      <p>{certificate.reason}</p>
      <p className="completion-certificate-rule">
        Regra deste recorte: {certificate.required_lessons} aulas e{' '}
        {certificate.required_checkpoints} checkpoints atuais.
      </p>
      <p className="completion-no-download">
        Versão da regra: {certificate.rule_version}. Esta tela recalcula a elegibilidade atual;
        ela não altera resultados históricos nem representa um certificado já emitido.
      </p>
      <p className="completion-no-download">
        Esta tela informa a elegibilidade. Nenhum certificado é baixado automaticamente.
      </p>
      {externalCertificate && (
        <p className="completion-no-download">
          Esta regra vale para o escopo “{certificate.scope_label}” dentro do aplicativo.
          A página externa da VOA considera o curso oficial completo e possui critérios
          próprios.
        </p>
      )}
      {externalCertificate ? (
        <a
          className="btn"
          href={certificate.cta_href}
          target="_blank"
          rel="noreferrer"
        >
          {certificate.cta_label}
        </a>
      ) : (
        <Link className="btn" to={certificate.cta_href}>
          {certificate.cta_label}
        </Link>
      )}
    </section>
  )
}
