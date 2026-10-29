"""BE-46: turno do Guiado sem cue e job de diálogo sem áudio

Duas colunas NOT NULL impediam o modo Guiado, e nenhuma das duas podia
simplesmente virar opcional sem perder a garantia que carregava.

`speaking_attempt.transcript_cue_id` existia porque todo áudio vinha do
shadowing, onde a fala tem uma linha de transcrição esperada. No Guiado o aluno
responde uma pergunta do parceiro: não há cue. A coluna passa a opcional e
`origin` assume a garantia — ela diz de onde o áudio veio e a constraint amarra
as duas colunas, de modo que um áudio de shadowing sem cue continua impossível.

`transcription_job.speaking_attempt_id` existia porque todo job transcrevia um
áudio. O turno por texto também precisa de job (a chamada ao modelo acontece no
worker), e aí não há áudio. A coluna passa a opcional e `kind` diz o que o
worker deve fazer; a constraint garante que um job de transcrição sem áudio
continua impossível.

Os valores das linhas existentes são preenchidos antes de cada constraint
entrar, então a migration vale para uma base com histórico: em produção, hoje,
todo áudio tem cue e todo job transcreve.

Revision ID: f4c2e8a71b30
Revises: e3a1c7d9b250
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4c2e8a71b30"
down_revision: str | None = "e3a1c7d9b250"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ATTEMPT_ORIGIN = (
    "(origin = 'cue') = (transcript_cue_id IS NOT NULL) AND origin IN ('cue','dialogue')"
)
# Job de transcrição precisa de áudio; job de diálogo pode ser de texto.
JOB_KIND = (
    "kind IN ('transcription','dialogue') "
    "AND (kind <> 'transcription' OR speaking_attempt_id IS NOT NULL)"
)

# Sem bloco de GRANT, de propósito: `ops/roles_policy.sql` concede
# INSERT/UPDATE/DELETE **na tabela** `speaking_attempt` e `transcription_job`
# ao runtime, e SELECT ao worker. Privilégio de tabela no PostgreSQL vale para
# coluna adicionada depois, então `origin` e `kind` já estão cobertos. Grant por
# coluna aqui sugeriria uma restrição que não existe — diferente do DB-45, onde
# `dialogue_turn` é restrito coluna a coluna de propósito.


def upgrade() -> None:
    # (1) Áudio do Guiado: cue opcional, com `origin` assumindo a garantia.
    op.add_column(
        "speaking_attempt",
        sa.Column("origin", sa.String(length=20), nullable=True),
    )
    # Toda linha existente é shadowing: é o único caminho que existia.
    op.execute("UPDATE speaking_attempt SET origin = 'cue' WHERE origin IS NULL")
    op.alter_column("speaking_attempt", "origin", nullable=False, server_default="cue")
    op.alter_column(
        "speaking_attempt",
        "transcript_cue_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_check_constraint("ck_speaking_origin", "speaking_attempt", ATTEMPT_ORIGIN)

    # (2) Job de diálogo por texto: áudio opcional, com `kind` dizendo o que o
    # worker faz. O índice composto é o que mantém a varredura da fila barata
    # depois de ela passar a ter dois tipos de job na mesma tabela.
    op.add_column(
        "transcription_job",
        sa.Column("kind", sa.String(length=20), nullable=True),
    )
    op.execute("UPDATE transcription_job SET kind = 'transcription' WHERE kind IS NULL")
    op.alter_column("transcription_job", "kind", nullable=False, server_default="transcription")
    op.alter_column(
        "transcription_job",
        "speaking_attempt_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_check_constraint("ck_transcription_job_kind", "transcription_job", JOB_KIND)
    op.create_index(
        "ix_transcription_job_kind_status",
        "transcription_job",
        ["kind", "status", "next_attempt_at"],
    )


def downgrade() -> None:
    """Reverte apenas enquanto nada usou os caminhos novos.

    Um áudio sem cue ou um job sem áudio não cabe no schema antigo: apagá-los
    para caber apagaria evidência do aluno. Nesse caso o downgrade recusa e diz
    quantos são, como no DB-45.
    """

    bind = op.get_bind()
    counts = {
        name: int(bind.execute(sa.text(sql)).scalar_one())
        for name, sql in (
            (
                "audios_de_dialogo",
                "SELECT count(*) FROM speaking_attempt WHERE transcript_cue_id IS NULL",
            ),
            (
                "jobs_sem_audio",
                "SELECT count(*) FROM transcription_job WHERE speaking_attempt_id IS NULL",
            ),
        )
    }
    if any(counts.values()):
        raise RuntimeError(
            "BE-46: downgrade bloqueado; o schema antigo não cabe o que já existe "
            f"({counts['audios_de_dialogo']} áudios de diálogo, "
            f"{counts['jobs_sem_audio']} jobs sem áudio). Restaure em base isolada."
        )
    op.drop_index("ix_transcription_job_kind_status", table_name="transcription_job")
    op.drop_constraint("ck_transcription_job_kind", "transcription_job", type_="check")
    op.alter_column(
        "transcription_job",
        "speaking_attempt_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_column("transcription_job", "kind")
    op.drop_constraint("ck_speaking_origin", "speaking_attempt", type_="check")
    op.alter_column(
        "speaking_attempt",
        "transcript_cue_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_column("speaking_attempt", "origin")
