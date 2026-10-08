"""Modelo de domínio do conteúdo das aulas.

Convenção de texto: todo campo de texto exibível guarda um **subconjunto de
Markdown** — `**negrito**`, `*itálico*`, `` `código` `` e `~~riscado~~`. HTML
cru não entra no banco, o que elimina a superfície de XSS e deixa o seed
editável à mão. Quem decide a aparência é o frontend.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Lesson(Base):
    """Uma aula da série Let's Learn English."""

    __tablename__ = "lesson"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    title_pt: Mapped[str] = mapped_column(String(200))
    voa_url: Mapped[str] = mapped_column(String(500))
    grammar_tag: Mapped[str] = mapped_column(String(200))
    # Rótulos curtos de foco, usados na navegação. Lista de strings.
    focus_points: Mapped[list[str]] = mapped_column(JSONB, default=list)
    story_note: Mapped[str | None] = mapped_column(String(200), default=None)
    lead: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    goals: Mapped[list["LessonGoal"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LessonGoal.position",
        lazy="selectin",
    )
    grammar_blocks: Mapped[list["GrammarBlock"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="GrammarBlock.position",
        lazy="selectin",
    )
    phrases: Mapped[list["Phrase"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="Phrase.position",
        lazy="selectin",
    )
    vocab: Mapped[list["VocabItem"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="VocabItem.position",
        lazy="selectin",
    )
    pronunciation: Mapped[list["PronunciationNote"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="PronunciationNote.position",
        lazy="selectin",
    )
    exercises: Mapped[list["Exercise"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="Exercise.position",
        lazy="selectin",
    )
    media: Mapped[list["LessonMedia"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LessonMedia.position",
        lazy="selectin",
    )
    writing_prompts: Mapped[list["WritingPrompt"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="WritingPrompt.position",
        lazy="selectin",
    )


class LessonMedia(Base):
    """Mídia oficial ou autoral associada a uma aula.

    O banco guarda somente metadados e a URL de origem. Arquivos grandes não
    pertencem ao PostgreSQL e, para a VOA, continuam hospedados na fonte.
    """

    __tablename__ = "lesson_media"
    __table_args__ = (UniqueConstraint("lesson_id", "position", name="uq_media_lesson_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(1000))
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    listening_exercise_position: Mapped[int | None] = mapped_column(Integer, default=None)

    lesson: Mapped[Lesson] = relationship(back_populates="media")
    cues: Mapped[list["TranscriptCue"]] = relationship(
        back_populates="media",
        cascade="all, delete-orphan",
        order_by="TranscriptCue.position",
        lazy="selectin",
    )


class TranscriptCue(Base):
    """Trecho curto sincronizado com uma mídia da aula."""

    __tablename__ = "transcript_cue"
    __table_args__ = (
        UniqueConstraint("media_id", "position", name="uq_transcript_media_position"),
        CheckConstraint("start_seconds >= 0", name="ck_transcript_start_nonnegative"),
        CheckConstraint("end_seconds > start_seconds", name="ck_transcript_end_after_start"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_media.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    speaker: Mapped[str] = mapped_column(String(80))
    text_en: Mapped[str] = mapped_column(Text)
    text_pt: Mapped[str] = mapped_column(Text)

    media: Mapped[LessonMedia] = relationship(back_populates="cues")


class SpeakingAttempt(Base):
    """Gravação de shadowing salva com consentimento explícito.

    O áudio não entra no banco: ``storage_key`` aponta para o armazenamento
    privado, e nunca recebe um nome fornecido pelo usuário.
    """

    __tablename__ = "speaking_attempt"
    __table_args__ = (
        CheckConstraint("duration_ms > 0", name="ck_speaking_duration_positive"),
        CheckConstraint("duration_ms <= 30000", name="ck_speaking_duration_limit"),
        CheckConstraint(
            "file_size IS NULL OR file_size > 0", name="ck_speaking_file_size_positive"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    transcript_cue_id: Mapped[int] = mapped_column(
        ForeignKey("transcript_cue.id", ondelete="CASCADE"), index=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer)
    self_rating: Mapped[str | None] = mapped_column(String(20), default=None)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    mime_type: Mapped[str | None] = mapped_column(String(100), default=None)
    file_size: Mapped[int | None] = mapped_column(Integer, default=None)
    storage_key: Mapped[str | None] = mapped_column(String(80), unique=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cue: Mapped[TranscriptCue] = relationship(lazy="selectin")


class TranscriptionJob(Base):
    """Resultado descartável de um provedor de speech-to-text opcional."""

    __tablename__ = "transcription_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_transcription_job_status",
        ),
        CheckConstraint(
            "mean_confidence IS NULL OR (mean_confidence >= 0 AND mean_confidence <= 1)",
            name="ck_transcription_confidence",
        ),
        CheckConstraint(
            "similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 1)",
            name="ck_transcription_similarity",
        ),
        CheckConstraint("cost_microusd >= 0", name="ck_transcription_cost_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    speaking_attempt_id: Mapped[int] = mapped_column(
        ForeignKey("speaking_attempt.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    provider: Mapped[str] = mapped_column(String(80))
    transcript_text: Mapped[str | None] = mapped_column(Text, default=None)
    words: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, default=None)
    mean_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    similarity_score: Mapped[float | None] = mapped_column(Float, default=None)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    human_rating: Mapped[str | None] = mapped_column(String(20), default=None)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LessonGoal(Base):
    """Objetivo de aprendizagem da aula."""

    __tablename__ = "lesson_goal"
    __table_args__ = (UniqueConstraint("lesson_id", "position", name="uq_goal_lesson_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    lesson: Mapped[Lesson] = relationship(back_populates="goals")


class GrammarBlock(Base):
    """Um tópico gramatical, com explicação e tabela opcional."""

    __tablename__ = "grammar_block"
    __table_args__ = (UniqueConstraint("lesson_id", "position", name="uq_block_lesson_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(300))
    why: Mapped[str] = mapped_column(Text)
    warning: Mapped[str | None] = mapped_column(Text, default=None)
    # Cabeçalho da tabela. Null quando o bloco não tem tabela.
    table_head: Mapped[list[str] | None] = mapped_column(JSONB, default=None)

    lesson: Mapped[Lesson] = relationship(back_populates="grammar_blocks")
    rows: Mapped[list["GrammarRow"]] = relationship(
        back_populates="block",
        cascade="all, delete-orphan",
        order_by="GrammarRow.position",
        lazy="selectin",
    )


class GrammarRow(Base):
    """Uma linha da tabela de um bloco gramatical.

    As células ficam em JSONB porque o número de colunas varia por bloco e
    uma tabela de células seria peso sem ganho: nada consulta célula isolada.
    """

    __tablename__ = "grammar_row"
    __table_args__ = (UniqueConstraint("block_id", "position", name="uq_row_block_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_id: Mapped[int] = mapped_column(
        ForeignKey("grammar_block.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    cells: Mapped[list[str]] = mapped_column(JSONB)

    block: Mapped[GrammarBlock] = relationship(back_populates="rows")


class Phrase(Base):
    """Fala real do episódio, com tradução e nota."""

    __tablename__ = "phrase"
    __table_args__ = (UniqueConstraint("lesson_id", "position", name="uq_phrase_lesson_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text_en: Mapped[str] = mapped_column(Text)
    text_pt: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text)

    lesson: Mapped[Lesson] = relationship(back_populates="phrases")


class VocabItem(Base):
    """Item de vocabulário.

    A chave natural é (lesson_id, term), e não a posição: a partir da S4 as
    cartas de revisão apontam para cá, e reordenar o seed não pode trocar o
    item por baixo de uma carta existente.
    """

    __tablename__ = "vocab_item"
    __table_args__ = (UniqueConstraint("lesson_id", "term", name="uq_vocab_lesson_term"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    term: Mapped[str] = mapped_column(String(120))
    ipa: Mapped[str] = mapped_column(String(160))
    translation_pt: Mapped[str] = mapped_column(Text)
    example_en: Mapped[str] = mapped_column(Text)

    lesson: Mapped[Lesson] = relationship(back_populates="vocab")


class PronunciationNote(Base):
    """Nota de pronúncia, escolhida pelos erros típicos de quem fala português."""

    __tablename__ = "pronunciation_note"
    __table_args__ = (UniqueConstraint("lesson_id", "position", name="uq_pron_lesson_position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String(200))
    explanation: Mapped[str] = mapped_column(Text)

    lesson: Mapped[Lesson] = relationship(back_populates="pronunciation")


class Exercise(Base):
    """Exercício de completar.

    Chave natural (lesson_id, position) porque na S3 as tentativas do usuário
    apontam para cá e não podem perder a referência a cada novo seed.
    """

    __tablename__ = "exercise"
    __table_args__ = (
        UniqueConstraint("lesson_id", "position", name="uq_exercise_lesson_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    activity_type: Mapped[str] = mapped_column(String(40), default="gap_fill")
    skill: Mapped[str] = mapped_column(String(40), default="grammar")
    options: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    prompt: Mapped[str] = mapped_column(Text)
    hint: Mapped[str | None] = mapped_column(String(200), default=None)
    explanation: Mapped[str] = mapped_column(Text)

    lesson: Mapped[Lesson] = relationship(back_populates="exercises")
    answers: Mapped[list["ExerciseAnswer"]] = relationship(
        back_populates="exercise",
        cascade="all, delete-orphan",
        order_by="ExerciseAnswer.position",
        lazy="selectin",
    )
    hints: Mapped[list["ExerciseHint"]] = relationship(
        back_populates="exercise",
        cascade="all, delete-orphan",
        order_by="ExerciseHint.level",
        lazy="selectin",
    )

    @property
    def hint_count(self) -> int:
        """Expõe a quantidade sem publicar o conteúdo das dicas."""
        return len(self.hints)


class ExerciseAnswer(Base):
    """Uma resposta aceita.

    Tabela à parte porque um exercício aceita mais de uma resposta certa
    (`should` e `ought to`, por exemplo) e todas precisam valer igual.
    """

    __tablename__ = "exercise_answer"
    __table_args__ = (
        UniqueConstraint("exercise_id", "position", name="uq_answer_exercise_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercise.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    value: Mapped[str] = mapped_column(String(200))

    exercise: Mapped[Exercise] = relationship(back_populates="answers")


class ExerciseHint(Base):
    """Dica progressiva, liberada explicitamente pelo aluno."""

    __tablename__ = "exercise_hint"
    __table_args__ = (
        UniqueConstraint("exercise_id", "level", name="uq_exercise_hint_level"),
        CheckConstraint("level > 0", name="ck_exercise_hint_level_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercise.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)

    exercise: Mapped[Exercise] = relationship(back_populates="hints")


class WritingPrompt(Base):
    """Proposta autoral de escrita associada ao objetivo de uma aula."""

    __tablename__ = "writing_prompt"
    __table_args__ = (
        UniqueConstraint("lesson_id", "position", name="uq_writing_prompt_lesson_position"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text)
    min_words: Mapped[int] = mapped_column(Integer)
    min_sentences: Mapped[int] = mapped_column(Integer)
    requirements: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)

    lesson: Mapped[Lesson] = relationship(back_populates="writing_prompts")


class WritingDraft(Base):
    """Rascunho atual do usuário; versões explícitas ficam em tabela própria."""

    __tablename__ = "writing_draft"
    __table_args__ = (
        UniqueConstraint("user_id", "prompt_id", name="uq_writing_draft_user_prompt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    prompt_id: Mapped[int] = mapped_column(
        ForeignKey("writing_prompt.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    revisions: Mapped[list["WritingRevision"]] = relationship(
        back_populates="draft",
        cascade="all, delete-orphan",
        order_by="WritingRevision.version.desc()",
        lazy="selectin",
    )


class WritingRevision(Base):
    """Fotografia imutável criada quando o aluno decide versionar o texto."""

    __tablename__ = "writing_revision"
    __table_args__ = (
        UniqueConstraint("draft_id", "version", name="uq_writing_revision_draft_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    draft_id: Mapped[int] = mapped_column(
        ForeignKey("writing_draft.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    draft: Mapped[WritingDraft] = relationship(back_populates="revisions")


class WritingFeedbackRecord(Base):
    """Resultado estruturado de uma análise de escrita feita pelo aluno."""

    __tablename__ = "writing_feedback"
    __table_args__ = (
        CheckConstraint(
            "analysis_mode IN ('deterministic', 'assisted', 'fallback')",
            name="ck_writing_feedback_analysis_mode",
        ),
        CheckConstraint(
            "assisted_confidence IS NULL OR "
            "(assisted_confidence >= 0 AND assisted_confidence <= 1)",
            name="ck_writing_feedback_confidence",
        ),
        CheckConstraint("assisted_cost_microusd >= 0", name="ck_writing_feedback_cost_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    prompt_id: Mapped[int] = mapped_column(
        ForeignKey("writing_prompt.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    sentence_count: Mapped[int] = mapped_column(Integer)
    ready: Mapped[bool] = mapped_column(Boolean)
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    analysis_mode: Mapped[str] = mapped_column(String(20), default="deterministic")
    provider: Mapped[str | None] = mapped_column(String(80), default=None)
    assisted_summary: Mapped[str | None] = mapped_column(Text, default=None)
    assisted_suggestions: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, default=None
    )
    assisted_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    assisted_cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    assisted_error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    human_rating: Mapped[str | None] = mapped_column(String(20), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotebookEntry(Base):
    """Anotação pessoal que nunca modifica o conteúdo curricular."""

    __tablename__ = "notebook_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lesson: Mapped[Lesson] = relationship(lazy="selectin")


class User(Base):
    """Quem estuda.

    O e-mail é guardado em minúsculas: duas contas que diferem só pela caixa
    seriam a mesma pessoa tentando entrar e não conseguindo.
    """

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sessions: Mapped[list["RefreshSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshSession(Base):
    """Uma sessão de refresh viva.

    O refresh é um JWT, mas o `jti` dele fica aqui — sem isso `logout` seria
    decorativo: o token continuaria válido até expirar.
    """

    __tablename__ = "refresh_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="sessions")


class LessonProgress(Base):
    """Marcação de aula estudada, por usuário."""

    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_progress_user_lesson"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    studied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lesson: Mapped[Lesson] = relationship(lazy="selectin")


class StudySessionProgress(Base):
    """Ponto de retomada da jornada guiada, por usuário e aula."""

    __tablename__ = "study_session_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_study_session_user_lesson"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    current_step: Mapped[str] = mapped_column(String(20))
    completed_steps: Mapped[list[str]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    total_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lesson: Mapped[Lesson] = relationship(lazy="selectin")
    steps: Mapped[list["StepProgress"]] = relationship(
        back_populates="study_session",
        cascade="all, delete-orphan",
        order_by="StepProgress.id",
        lazy="selectin",
    )


class StepProgress(Base):
    """Tempo aproximado e conclusão de cada etapa da jornada guiada."""

    __tablename__ = "step_progress"
    __table_args__ = (
        UniqueConstraint("study_session_id", "step", name="uq_step_progress_session_step"),
        CheckConstraint("seconds_spent >= 0", name="ck_step_progress_seconds_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    study_session_id: Mapped[int] = mapped_column(
        ForeignKey("study_session_progress.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(20))
    seconds_spent: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    study_session: Mapped[StudySessionProgress] = relationship(back_populates="steps")


class StudyPlan(Base):
    """Meta semanal leve; orienta o aluno sem bloquear estudos fora da agenda."""

    __tablename__ = "study_plan"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_study_plan_user"),
        CheckConstraint(
            "weekly_minutes >= 30 AND weekly_minutes <= 600",
            name="ck_study_plan_weekly_minutes",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    weekly_minutes: Mapped[int] = mapped_column(Integer, default=90)
    preferred_days: Mapped[list[str]] = mapped_column(JSONB, default=list)
    goal: Mapped[str] = mapped_column(String(200), default="Criar constância no inglês")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SkillEvidence(Base):
    """Uma observação normalizada usada no painel de competências."""

    __tablename__ = "skill_evidence"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_skill_evidence_source"),
        CheckConstraint("score >= 0 AND score <= 1", name="ck_skill_evidence_score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    skill: Mapped[str] = mapped_column(String(40), index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExerciseAttempt(Base):
    """Cada tentativa, certa ou errada, com o que foi digitado.

    Guardar o texto exato é o que permite, na S4, descobrir *qual* item de
    vocabulário a pessoa erra — e não só que ela errou.
    """

    __tablename__ = "exercise_attempt"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_attempt_user_idempotency"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercise.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(36), default=None)
    answer: Mapped[str] = mapped_column(String(200))
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exercise: Mapped[Exercise] = relationship(lazy="selectin")


class ReviewCardLegacy(Base):
    """Deck de vocabulário anterior à fila multimodal.

    Mantido durante a migração expand/contract para que o histórico original
    continue disponível e o rollback da Sprint 12 não dependa de reconstrução.

    `due_at` é `timestamptz` e sempre guardado em UTC. Conversão para o fuso
    de quem lê acontece na borda — guardar hora local no banco é como se
    perde uma semana inteira de revisões no horário de verão.
    """

    __tablename__ = "review_card"
    __table_args__ = (UniqueConstraint("user_id", "vocab_item_id", name="uq_card_user_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    vocab_item_id: Mapped[int] = mapped_column(
        ForeignKey("vocab_item.id", ondelete="CASCADE"), index=True
    )

    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)

    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vocab_item: Mapped[VocabItem] = relationship(lazy="selectin")


class ReviewItem(Base):
    """Item multimodal com agendamento SM-2 e origem idempotente."""

    __tablename__ = "review_item"
    __table_args__ = (
        UniqueConstraint("user_id", "source_key", name="uq_review_item_user_source"),
        UniqueConstraint("legacy_card_id", name="uq_review_item_legacy_card"),
        CheckConstraint(
            "item_type IN ('vocabulary', 'grammar_error', 'phrase', 'listening', "
            "'writing_prompt', 'speaking_prompt')",
            name="ck_review_item_type",
        ),
        CheckConstraint("status IN ('active', 'suspended')", name="ck_review_item_status"),
        CheckConstraint("estimated_seconds > 0", name="ck_review_item_duration_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    vocab_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("vocab_item.id", ondelete="CASCADE"), index=True, default=None
    )
    legacy_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("review_card.id", ondelete="CASCADE"), default=None
    )
    item_type: Mapped[str] = mapped_column(String(30), index=True)
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(100))
    skill: Mapped[str] = mapped_column(String(40), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    prompt_note: Mapped[str | None] = mapped_column(String(200), default=None)
    answer: Mapped[str] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text, default=None)
    origin_reason: Mapped[str] = mapped_column(String(300))
    media_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    cue_start_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    cue_end_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    estimated_seconds: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lesson: Mapped[Lesson] = relationship(lazy="selectin")
    vocab_item: Mapped[VocabItem | None] = relationship(lazy="selectin")
