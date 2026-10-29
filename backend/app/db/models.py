"""Modelo de domínio do conteúdo das aulas.

Convenção de texto: todo campo de texto exibível guarda um **subconjunto de
Markdown** — `**negrito**`, `*itálico*`, `` `código` `` e `~~riscado~~`. HTML
cru não entra no banco, o que elimina a superfície de XSS e deixa o seed
editável à mão. Quem decide a aparência é o frontend.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import (
    AnalysisMode,
    AudioOrigin,
    DeletionJobState,
    DialogueMode,
    DialogueState,
    ExerciseObjective,
    HumanRating,
    IntegrityState,
    JobKind,
    NotebookKind,
    PracticeMode,
    PracticeStatus,
    SelfRating,
    SpeakingStatus,
    TranscriptionStatus,
    TurnInputKind,
    TurnRole,
    TurnState,
)


class EditorialArchiveEvent(Base):
    """Operational receipt, append-only; contains no student content or identifiers."""

    __tablename__ = "editorial_archive_event"
    __table_args__ = (
        CheckConstraint(
            "before_status = 'published' AND after_status = 'archived'",
            name="ck_archive_transition",
        ),
        CheckConstraint(
            "reason_code IN ('editorial_review', 'source_unavailable', "
            "'curriculum_reorganization')",
            name="ck_archive_reason",
        ),
        CheckConstraint("catalog_sha256 ~ '^[0-9a-f]{64}$'", name="ck_archive_hash"),
    )
    operation_key: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("course_unit.id", ondelete="RESTRICT"))
    course_slug: Mapped[str] = mapped_column(String(100))
    unit_slug: Mapped[str] = mapped_column(String(100))
    operator_label: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(40))
    db_actor: Mapped[str] = mapped_column(String(128), server_default=text("current_user"))
    db_login: Mapped[str] = mapped_column(String(128), server_default=text("session_user"))
    before_status: Mapped[str] = mapped_column(String(20))
    after_status: Mapped[str] = mapped_column(String(20))
    catalog_sha256: Mapped[str] = mapped_column(String(64))
    impact: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EditorialReorderEvent(Base):
    """Immutable receipt for one explicitly approved position permutation."""

    __tablename__ = "editorial_reorder_event"
    __table_args__ = (
        CheckConstraint(
            "reason_code IN ('pedagogical_sequence', 'accessibility_sequence', "
            "'curriculum_reorganization')",
            name="ck_reorder_reason",
        ),
        CheckConstraint("plan_sha256 ~ '^[0-9a-f]{64}$'", name="ck_reorder_plan_hash"),
        CheckConstraint(
            "catalog_before_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_reorder_before_hash",
        ),
        CheckConstraint(
            "catalog_candidate_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_reorder_candidate_hash",
        ),
        CheckConstraint(
            "catalog_after_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_reorder_after_hash",
        ),
    )
    operation_key: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    operator_label: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(40))
    db_actor: Mapped[str] = mapped_column(String(128), server_default=text("current_user"))
    db_login: Mapped[str] = mapped_column(String(128), server_default=text("session_user"))
    plan_sha256: Mapped[str] = mapped_column(String(64))
    catalog_before_sha256: Mapped[str] = mapped_column(String(64))
    catalog_candidate_sha256: Mapped[str] = mapped_column(String(64))
    catalog_after_sha256: Mapped[str] = mapped_column(String(64))
    changes: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    impact: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Course(Base):
    """Curso independente, com numeração de aulas própria."""

    __tablename__ = "course"
    __table_args__ = (
        CheckConstraint("position > 0", name="ck_course_position_positive"),
        CheckConstraint("total_lessons > 0", name="ck_course_total_lessons_positive"),
        CheckConstraint("status IN ('planned', 'published', 'archived')", name="ck_course_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    level: Mapped[str] = mapped_column(String(40))
    proficiency_label: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer, unique=True)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    total_lessons: Mapped[int] = mapped_column(Integer)

    units: Mapped[list["CourseUnit"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="CourseUnit.position",
        lazy="raise",
    )
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="course",
        order_by="Lesson.position",
        lazy="raise",
        overlaps="lessons,unit",
    )


class CourseUnit(Base):
    """Unidade navegável de um curso, publicada ou ainda planejada."""

    __tablename__ = "course_unit"
    __table_args__ = (
        UniqueConstraint("id", "course_id", name="uq_course_unit_id_course"),
        UniqueConstraint("course_id", "slug", name="uq_course_unit_course_slug"),
        UniqueConstraint("course_id", "position", name="uq_course_unit_course_position"),
        CheckConstraint("position > 0", name="ck_course_unit_position_positive"),
        CheckConstraint("lesson_start > 0", name="ck_course_unit_lesson_start_positive"),
        CheckConstraint("lesson_end >= lesson_start", name="ck_course_unit_lesson_range"),
        CheckConstraint("total_lessons > 0", name="ck_course_unit_total_lessons_positive"),
        CheckConstraint(
            "status IN ('planned', 'published', 'archived')", name="ck_course_unit_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    lesson_start: Mapped[int] = mapped_column(Integer)
    lesson_end: Mapped[int] = mapped_column(Integer)
    total_lessons: Mapped[int] = mapped_column(Integer)

    course: Mapped[Course] = relationship(back_populates="units")
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="unit",
        order_by="Lesson.position",
        lazy="raise",
        overlaps="course,lessons",
    )
    review: Mapped["CourseReview | None"] = relationship(
        back_populates="unit",
        foreign_keys="CourseReview.unit_id",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )


class CourseReview(Base):
    """Checkpoint curricular de uma unidade — não é uma aula artificial."""

    __tablename__ = "course_review"
    __table_args__ = (
        UniqueConstraint("unit_id", name="uq_course_review_unit"),
        UniqueConstraint("unit_id", "slug", name="uq_course_review_unit_slug"),
        CheckConstraint("position > 0", name="ck_course_review_position_positive"),
        CheckConstraint("estimated_minutes > 0", name="ck_course_review_minutes_positive"),
        CheckConstraint("content_version > 0", name="ck_course_review_version_positive"),
        CheckConstraint("review_lesson_number > 0", name="ck_course_review_lesson_positive"),
        CheckConstraint(
            "listening_lesson_number IS NULL OR listening_lesson_number > 0",
            name="ck_course_review_listening_lesson_positive",
        ),
        CheckConstraint(
            "listening_media_position IS NULL OR listening_media_position >= 0",
            name="ck_course_review_listening_position_nonnegative",
        ),
        CheckConstraint(
            "(listening_lesson_number IS NULL) = (listening_media_position IS NULL) AND "
            "(listening_media_position IS NULL) = (listening_course_id IS NULL) AND "
            "(listening_course_id IS NULL) = (listening_lesson_id IS NULL) AND "
            "(listening_lesson_id IS NULL) = (listening_media_id IS NULL)",
            name="ck_course_review_listening_pair",
        ),
        ForeignKeyConstraint(
            ["unit_id", "listening_course_id"],
            ["course_unit.id", "course_unit.course_id"],
            name="fk_course_review_unit_course",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["listening_lesson_id", "listening_course_id"],
            ["lesson.id", "lesson.course_id"],
            name="fk_course_review_listening_lesson_course",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["listening_lesson_id", "listening_media_id"],
            ["lesson_media.lesson_id", "lesson_media.id"],
            name="fk_course_review_listening_media_lesson",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('planned', 'published', 'archived')", name="ck_course_review_status"
        ),
        CheckConstraint(
            "source_kind IN ('official', 'authorial', 'mixed')",
            name="ck_course_review_source_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    unit_id: Mapped[int] = mapped_column(
        ForeignKey("course_unit.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    source_kind: Mapped[str] = mapped_column(String(20))
    source_title: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    source_note: Mapped[str] = mapped_column(String(500))
    intro: Mapped[str] = mapped_column(Text)
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    content_version: Mapped[int] = mapped_column(Integer, default=1)
    review_lesson_number: Mapped[int] = mapped_column(Integer)
    listening_lesson_number: Mapped[int | None] = mapped_column(Integer, default=None)
    listening_media_position: Mapped[int | None] = mapped_column(Integer, default=None)
    # Vínculo canônico. Número/posição permanecem somente para compatibilidade
    # com o pacote editorial legado e não são usados para resolver a mídia.
    listening_course_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    listening_lesson_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    listening_media_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)

    unit: Mapped[CourseUnit] = relationship(
        back_populates="review", foreign_keys=[unit_id], lazy="joined"
    )
    questions: Mapped[list["CourseReviewQuestion"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
        order_by="CourseReviewQuestion.position",
        lazy="selectin",
    )


class CourseReviewQuestion(Base):
    """Questão autoral de checkpoint; o gabarito nunca sai na leitura inicial."""

    __tablename__ = "course_review_question"
    editorial_key: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        server_default=text("gen_random_uuid()"),
        deferred=True,
        deferred_raiseload=True,
    )
    __table_args__ = (
        UniqueConstraint("editorial_key", name="uq_course_review_question_editorial_key"),
        UniqueConstraint("review_id", "position", name="uq_course_review_question_position"),
        CheckConstraint("position > 0", name="ck_course_review_question_position_positive"),
        CheckConstraint(
            "activity_type IN ('multiple_choice', 'short_answer')",
            name="ck_course_review_question_activity_type",
        ),
        CheckConstraint(
            "skill IN ('grammar', 'listening', 'vocabulary')",
            name="ck_course_review_question_skill",
        ),
        CheckConstraint(
            "jsonb_array_length(accepted_answers) > 0",
            name="ck_course_review_question_answers_nonempty",
        ),
        CheckConstraint(
            "jsonb_array_length(lesson_numbers) > 0",
            name="ck_course_review_question_lessons_nonempty",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("course_review.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    activity_type: Mapped[str] = mapped_column(String(30))
    skill: Mapped[str] = mapped_column(String(30))
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    accepted_answers: Mapped[list[str]] = mapped_column(JSONB)
    explanation: Mapped[str] = mapped_column(Text)
    lesson_numbers: Mapped[list[int]] = mapped_column(JSONB, default=list)

    review: Mapped[CourseReview] = relationship(back_populates="questions")


class CourseReviewAttempt(Base):
    """Resultado imutável de uma execução completa do checkpoint."""

    __tablename__ = "course_review_attempt"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="uq_course_review_attempt_user_idempotency"
        ),
        CheckConstraint("content_version > 0", name="ck_course_review_attempt_version_positive"),
        CheckConstraint("score >= 0", name="ck_course_review_attempt_score_nonnegative"),
        CheckConstraint("total > 0", name="ck_course_review_attempt_total_positive"),
        CheckConstraint("score <= total", name="ck_course_review_attempt_score_within_total"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("course_review.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    content_version: Mapped[int] = mapped_column(Integer)
    answers: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    result: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    score: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Lesson(Base):
    """Uma aula da série Let's Learn English."""

    __tablename__ = "lesson"

    __table_args__ = (
        ForeignKeyConstraint(
            ["unit_id", "course_id"],
            ["course_unit.id", "course_unit.course_id"],
            name="fk_lesson_unit_course",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("course_id", "number", name="uq_lesson_course_number"),
        UniqueConstraint("course_id", "slug", name="uq_lesson_course_slug"),
        UniqueConstraint("unit_id", "position", name="uq_lesson_unit_position"),
        UniqueConstraint("id", "course_id", name="uq_lesson_id_course"),
        CheckConstraint("number > 0", name="ck_lesson_number_positive"),
        CheckConstraint("position > 0", name="ck_lesson_position_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("course.id", ondelete="RESTRICT"), index=True)
    unit_id: Mapped[int] = mapped_column(Integer, index=True)
    number: Mapped[int] = mapped_column(Integer, index=True)
    slug: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    title_pt: Mapped[str] = mapped_column(String(200))
    voa_url: Mapped[str] = mapped_column(String(500))
    grammar_tag: Mapped[str] = mapped_column(String(200))
    # Rótulos curtos de foco, usados na navegação. Lista de strings.
    focus_points: Mapped[list[str]] = mapped_column(JSONB, default=list)
    story_note: Mapped[str | None] = mapped_column(String(200), default=None)
    lead: Mapped[str] = mapped_column(Text)
    warmup_prompt: Mapped[str] = mapped_column(Text)
    listening_focus: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    course: Mapped[Course] = relationship(
        back_populates="lessons", lazy="joined", overlaps="lessons,unit"
    )
    unit: Mapped[CourseUnit] = relationship(
        back_populates="lessons", lazy="joined", overlaps="course,lessons"
    )

    @property
    def course_slug(self) -> str:
        return self.course.slug

    @property
    def unit_slug(self) -> str:
        return self.unit.slug

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
    content_sources: Mapped[list["ContentSource"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="ContentSource.kind",
        lazy="selectin",
    )
    versions: Mapped[list["LessonVersion"]] = relationship(
        back_populates="lesson",
        cascade="all, delete-orphan",
        order_by="LessonVersion.version.desc()",
        lazy="selectin",
    )


class ContentSource(Base):
    """Origem editorial de conteúdo oficial ou explicação autoral."""

    __tablename__ = "content_source"
    __table_args__ = (
        UniqueConstraint("lesson_id", "kind", name="uq_content_source_lesson_kind"),
        CheckConstraint("kind IN ('official', 'authorial')", name="ck_content_source_kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    publisher: Mapped[str] = mapped_column(String(120))
    url: Mapped[str | None] = mapped_column(String(1000), default=None)
    license_note: Mapped[str] = mapped_column(String(500))
    accessed_at: Mapped[date] = mapped_column()

    lesson: Mapped[Lesson] = relationship(back_populates="content_sources")


class LessonVersion(Base):
    """Fotografia editorial identificável do conteúdo de uma aula."""

    __tablename__ = "lesson_version"
    __table_args__ = (
        UniqueConstraint("lesson_id", "version", name="uq_lesson_version_lesson_version"),
        CheckConstraint(
            "status IN ('draft', 'reviewed', 'published')", name="ck_lesson_version_status"
        ),
        CheckConstraint("version > 0", name="ck_lesson_version_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    learning_strategy: Mapped[str] = mapped_column(String(100))
    review_note: Mapped[str] = mapped_column(String(500))
    # NULL significa que a revisão legada existe, mas sua data não foi
    # comprovada. Nunca preencher com a data de acesso ou de execução.
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    lesson: Mapped[Lesson] = relationship(back_populates="versions")


class LessonMedia(Base):
    """Mídia oficial ou autoral associada a uma aula.

    O banco guarda somente metadados e a URL de origem. Arquivos grandes não
    pertencem ao PostgreSQL e, para a VOA, continuam hospedados na fonte.
    """

    __tablename__ = "lesson_media"
    editorial_key: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        server_default=text("gen_random_uuid()"),
        deferred=True,
        deferred_raiseload=True,
    )
    __table_args__ = (
        UniqueConstraint("editorial_key", name="uq_lesson_media_editorial_key"),
        UniqueConstraint("lesson_id", "position", name="uq_media_lesson_position"),
        UniqueConstraint("lesson_id", "id", name="uq_lesson_media_lesson_id"),
        ForeignKeyConstraint(
            ["lesson_id", "listening_exercise_id"],
            ["exercise.lesson_id", "exercise.id"],
            name="fk_lesson_media_listening_exercise_lesson",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "license_status IN ('public_domain', 'permission_granted', "
            "'restricted', 'review_required')",
            name="ck_media_license_status",
        ),
        CheckConstraint(
            "offline_policy IN ('network_only', 'cache_allowed')",
            name="ck_media_offline_policy",
        ),
        CheckConstraint(
            "offline_policy != 'cache_allowed' OR "
            "license_status IN ('public_domain', 'permission_granted')",
            name="ck_media_offline_requires_license",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    source_url: Mapped[str] = mapped_column(String(1000))
    license_status: Mapped[str] = mapped_column(String(30), default="review_required")
    license_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    license_note: Mapped[str] = mapped_column(String(500))
    attribution: Mapped[str] = mapped_column(String(200))
    offline_policy: Mapped[str] = mapped_column(String(20), default="network_only")
    license_reviewed_at: Mapped[date | None] = mapped_column(default=None)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    # Campo legado: preserva o contrato do seed/API durante a expansão, mas
    # a referência canônica é o FK abaixo e sobrevive a reordenações.
    listening_exercise_position: Mapped[int | None] = mapped_column(Integer, default=None)
    listening_exercise_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    transcript: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)

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
    editorial_key: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        server_default=text("gen_random_uuid()"),
        deferred=True,
        deferred_raiseload=True,
    )
    __table_args__ = (
        UniqueConstraint("editorial_key", name="uq_transcript_cue_editorial_key"),
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


class MediaProgress(Base):
    """Última posição de mídia sincronizada entre dispositivos."""

    __tablename__ = "media_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "media_id", name="uq_media_progress_user_media"),
        CheckConstraint("position_seconds >= 0", name="ck_media_progress_nonnegative"),
        CheckConstraint("revision >= 0", name="ck_media_progress_revision"),
        CheckConstraint("NOT completed OR position_seconds = 0", name="ck_media_completed_zero"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    media_id: Mapped[int] = mapped_column(
        ForeignKey("lesson_media.id", ondelete="CASCADE"), index=True
    )
    position_seconds: Mapped[float] = mapped_column(Float, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    operation_key: Mapped[str | None] = mapped_column(String(36))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SpeakingAttempt(Base):
    """Gravação de shadowing salva com consentimento explícito.

    O áudio não entra no banco: ``storage_key`` aponta para o armazenamento
    privado, e nunca recebe um nome fornecido pelo usuário.
    """

    __tablename__ = "speaking_attempt"
    __table_args__ = (
        CheckConstraint("status IN ('pending','ready')", name="ck_speaking_status"),
        CheckConstraint(
            "audio_sha256 IS NULL OR audio_sha256 ~ '^[0-9a-f]{64}$'", name="ck_speaking_sha256"
        ),
        CheckConstraint(
            "integrity_state IN ('unknown','verified','missing','changed')",
            name="ck_speaking_integrity",
        ),
        Index("ix_speaking_status_created", "status", "created_at"),
        CheckConstraint(
            "(origin = 'cue') = (transcript_cue_id IS NOT NULL) "
            "AND origin IN ('cue','dialogue')",
            name="ck_speaking_origin",
        ),
        CheckConstraint("duration_ms > 0", name="ck_speaking_duration_positive"),
        CheckConstraint("duration_ms <= 30000", name="ck_speaking_duration_limit"),
        CheckConstraint(
            "file_size IS NULL OR file_size > 0", name="ck_speaking_file_size_positive"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    # Opcional desde o BE-46: o áudio do Guiado responde uma pergunta do
    # parceiro, não uma linha de transcrição. `origin` carrega a garantia.
    transcript_cue_id: Mapped[int | None] = mapped_column(
        ForeignKey("transcript_cue.id", ondelete="CASCADE"), index=True, default=None
    )
    origin: Mapped[AudioOrigin] = mapped_column(
        String(20), default="cue", server_default="cue"
    )
    duration_ms: Mapped[int] = mapped_column(Integer)
    self_rating: Mapped[SelfRating | None] = mapped_column(String(20), default=None)
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[SpeakingStatus] = mapped_column(String(20), default="pending")
    mime_type: Mapped[str | None] = mapped_column(String(100), default=None)
    file_size: Mapped[int | None] = mapped_column(Integer, default=None)
    storage_key: Mapped[str | None] = mapped_column(String(80), unique=True, default=None)
    audio_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    integrity_state: Mapped[IntegrityState] = mapped_column(
        String(20), default="unknown", server_default="unknown"
    )
    integrity_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    cue: Mapped[TranscriptCue] = relationship(lazy="selectin")


class AssistReservation(Base):
    """Ledger mínimo de cota, independente dos resultados descartáveis."""

    __tablename__ = "assist_reservation"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_assist_user_request"),
        CheckConstraint(
            "modality IN ('writing','transcription','conversation')", name="ck_assist_modality"
        ),
        CheckConstraint("state IN ('reserved','consumed','released')", name="ck_assist_state"),
        CheckConstraint("cost_microusd >= 0", name="ck_assist_cost"),
        CheckConstraint("expires_at > created_at", name="ck_assist_expiry"),
        Index("ix_assist_user_created", "user_id", "created_at"),
        Index("ix_assist_state_expiry", "state", "expires_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    request_key: Mapped[str] = mapped_column(String(80))
    fingerprint: Mapped[str] = mapped_column(String(64))
    modality: Mapped[str] = mapped_column(String(20))
    provider_key: Mapped[str] = mapped_column(String(64), unique=True)
    state: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str | None] = mapped_column(String(50), default=None)
    cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    cost_known: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class WorkerHeartbeat(Base):
    """Estado agregado de operação, sem conteúdo ou identidade de alunos."""

    __tablename__ = "worker_heartbeat"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    maintenance_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    maintenance_counts: Mapped[dict[str, int] | None] = mapped_column(JSONB, default=None)


class AccountDeletionJob(Base):
    """Recibo sem identidade pessoal para a limpeza assíncrona de arquivos."""

    __tablename__ = "account_deletion_job"
    __table_args__ = (
        CheckConstraint(
            "state IN ('cleanup_pending','completed','failed')",
            name="ck_account_deletion_state",
        ),
        CheckConstraint(
            "file_count >= 0 AND deleted_file_count >= 0 AND deleted_file_count <= file_count",
            name="ck_account_deletion_counts",
        ),
    )
    operation_key: Mapped[str] = mapped_column(Uuid(as_uuid=False), primary_key=True)
    state: Mapped[DeletionJobState] = mapped_column(String(20))
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    deleted_file_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    database_deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AccountDeletionFile(Base):
    """Chave opaca temporária; a linha é removida após o unlink idempotente."""

    __tablename__ = "account_deletion_file"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="ck_account_deletion_file_attempts"),
        UniqueConstraint("storage_key", name="uq_account_deletion_file_storage_key"),
        Index("ix_account_deletion_file_next", "next_attempt_at", "id"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_operation_key: Mapped[str] = mapped_column(
        ForeignKey("account_deletion_job.operation_key", ondelete="CASCADE")
    )
    storage_key: Mapped[str] = mapped_column(String(80))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_error_code: Mapped[str | None] = mapped_column(String(50), default=None)


class TranscriptionJob(Base):
    """Resultado descartável de um provedor de speech-to-text opcional."""

    __tablename__ = "transcription_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'failed')",
            name="ck_transcription_job_status",
        ),
        CheckConstraint(
            "kind IN ('transcription','dialogue') "
            "AND (kind <> 'transcription' OR speaking_attempt_id IS NOT NULL)",
            name="ck_transcription_job_kind",
        ),
        Index("ix_transcription_job_kind_status", "kind", "status", "next_attempt_at"),
        CheckConstraint(
            "mean_confidence IS NULL OR (mean_confidence >= 0 AND mean_confidence <= 1)",
            name="ck_transcription_confidence",
        ),
        CheckConstraint(
            "similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 1)",
            name="ck_transcription_similarity",
        ),
        CheckConstraint("cost_microusd >= 0", name="ck_transcription_cost_nonnegative"),
        CheckConstraint("attempt_count >= 0", name="ck_transcription_attempt_count"),
        CheckConstraint("max_attempts > 0", name="ck_transcription_max_attempts"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assist_reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("assist_reservation.id", ondelete="SET NULL"), unique=True, default=None
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    # Opcional desde o BE-46: o turno por texto também vira job (a chamada ao
    # modelo acontece no worker) e não tem áudio. `kind` diz o que fazer.
    speaking_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("speaking_attempt.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        default=None,
    )
    kind: Mapped[JobKind] = mapped_column(
        String(20), default="transcription", server_default="transcription"
    )
    status: Mapped[TranscriptionStatus] = mapped_column(String(20), default="queued", index=True)
    provider: Mapped[str] = mapped_column(String(80))
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    transcript_text: Mapped[str | None] = mapped_column(Text, default=None)
    words: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB, default=None)
    mean_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    similarity_score: Mapped[float | None] = mapped_column(Float, default=None)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    human_rating: Mapped[HumanRating | None] = mapped_column(String(20), default=None)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SpeakingDialogue(Base):
    """Diálogo do parceiro de conversa, ancorado em uma aula (ADR IA-45).

    Guarda metadados e o recorte da aula (versão e fingerprint). O texto dos
    turnos fica em ``dialogue_turn`` e segue a retenção da assistência.
    """

    __tablename__ = "speaking_dialogue"
    __table_args__ = (
        UniqueConstraint("user_id", "operation_key", name="uq_dialogue_user_operation"),
        CheckConstraint("mode IN ('script','guided','free_unit')", name="ck_dialogue_mode"),
        CheckConstraint("state IN ('active','completed','abandoned')", name="ck_dialogue_state"),
        CheckConstraint("turn_limit > 0 AND turn_limit <= 50", name="ck_dialogue_turn_limit"),
        CheckConstraint("ended_at IS NULL OR ended_at >= started_at", name="ck_dialogue_ended"),
        Index("ix_dialogue_user_started", "user_id", "started_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    operation_key: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    mode: Mapped[DialogueMode] = mapped_column(String(20))
    state: Mapped[DialogueState] = mapped_column(String(20), default="active")
    partner_speaker: Mapped[str | None] = mapped_column(String(80), default=None)
    content_version: Mapped[int] = mapped_column(Integer)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    provider_name: Mapped[str | None] = mapped_column(String(80), default=None)
    rubric_version: Mapped[str] = mapped_column(String(40))
    turn_limit: Mapped[int] = mapped_column(Integer, default=12)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class DialogueTurn(Base):
    """Um turno do diálogo: fala do aluno ou resposta do parceiro.

    ``checks`` guarda só códigos e booleanos; ``hints`` só códigos permitidos,
    com uma frase cada. O áudio continua em ``speaking_attempt``. ``transcript``,
    ``partner_text`` e ``hints`` expiram em ``expires_at``; os metadados ficam.
    """

    __tablename__ = "dialogue_turn"
    __table_args__ = (
        UniqueConstraint("dialogue_id", "position", name="uq_dialogue_turn_position"),
        UniqueConstraint("speaking_attempt_id", name="uq_dialogue_turn_speaking_attempt"),
        UniqueConstraint("transcription_job_id", name="uq_dialogue_turn_transcription_job"),
        CheckConstraint("position > 0", name="ck_dialogue_turn_position"),
        CheckConstraint("role IN ('student','partner')", name="ck_dialogue_turn_role"),
        CheckConstraint(
            "(role = 'student') = (input_kind IS NOT NULL) "
            "AND (input_kind IS NULL OR input_kind IN ('audio','text'))",
            name="ck_dialogue_turn_input",
        ),
        CheckConstraint("state IN ('pending','completed','failed')", name="ck_dialogue_turn_state"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_dialogue_turn_confidence",
        ),
        CheckConstraint("cost_microusd >= 0", name="ck_dialogue_turn_cost"),
        CheckConstraint(
            "jsonb_typeof(checks) = 'object' AND jsonb_typeof(hints) = 'array'",
            name="ck_dialogue_turn_json",
        ),
        CheckConstraint("expires_at > created_at", name="ck_dialogue_turn_expiry"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dialogue_id: Mapped[int] = mapped_column(ForeignKey("speaking_dialogue.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    role: Mapped[TurnRole] = mapped_column(String(20))
    input_kind: Mapped[TurnInputKind | None] = mapped_column(String(20), default=None)
    speaking_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("speaking_attempt.id", ondelete="SET NULL"), default=None
    )
    transcription_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("transcription_job.id", ondelete="SET NULL"), default=None
    )
    state: Mapped[TurnState] = mapped_column(String(20), default="pending")
    transcript: Mapped[str | None] = mapped_column(Text, default=None)
    checks: Mapped[dict[str, bool]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    check_details: Mapped[dict[str, list[dict[str, str | bool]]] | None] = mapped_column(
        JSONB(none_as_null=True), default=None
    )
    partner_text: Mapped[str | None] = mapped_column(Text, default=None)
    hints: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    fallback: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    cost_microusd: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    human_rating: Mapped[HumanRating | None] = mapped_column(String(20), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
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

    (lesson_id, term) continua único. A chave editorial imutável identifica
    a entidade mesmo se o termo/ordem mudar; cartas existentes mantêm a FK
    numérica. O seed ainda bloqueia alterações de conteúdo existente.
    """

    __tablename__ = "vocab_item"
    editorial_key: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        server_default=text("gen_random_uuid()"),
        deferred=True,
        deferred_raiseload=True,
    )
    __table_args__ = (
        UniqueConstraint("lesson_id", "term", name="uq_vocab_lesson_term"),
        UniqueConstraint("editorial_key", name="uq_vocab_item_editorial_key"),
    )

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

    O ID numérico mantém FKs pessoais. editorial_key é imutável; posição é
    somente ordenação, nunca identidade de uma edição subsequente do seed.
    """

    __tablename__ = "exercise"
    editorial_key: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        server_default=text("gen_random_uuid()"),
        deferred=True,
        deferred_raiseload=True,
    )
    __table_args__ = (
        UniqueConstraint("editorial_key", name="uq_exercise_editorial_key"),
        UniqueConstraint("lesson_id", "position", name="uq_exercise_lesson_position"),
        UniqueConstraint("lesson_id", "id", name="uq_exercise_lesson_id"),
        CheckConstraint(
            "objective IN ('recognize', 'apply', 'correct', 'produce', 'listen')",
            name="ck_exercise_objective",
        ),
        CheckConstraint(
            "activity_type != 'classification' OR "
            "(classification_items IS NOT NULL AND "
            "jsonb_typeof(classification_items) = 'array' AND "
            "jsonb_array_length(classification_items) > 0 AND "
            "classification_categories IS NOT NULL AND "
            "jsonb_typeof(classification_categories) = 'array' AND "
            "jsonb_array_length(classification_categories) >= 2)",
            name="ck_exercise_classification_contract",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    activity_type: Mapped[str] = mapped_column(String(40), default="gap_fill")
    skill: Mapped[str] = mapped_column(String(40), default="grammar")
    objective: Mapped[str] = mapped_column(String(20), default="apply")
    options: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    classification_items: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    classification_categories: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
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
    value: Mapped[str] = mapped_column(Text)

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
    editorial_key: Mapped[str] = mapped_column(
        Uuid(as_uuid=False),
        server_default=text("gen_random_uuid()"),
        deferred=True,
        deferred_raiseload=True,
    )
    __table_args__ = (
        UniqueConstraint("editorial_key", name="uq_writing_prompt_editorial_key"),
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
        CheckConstraint("revision >= 0", name="ck_writing_draft_revision"),
        UniqueConstraint("user_id", "prompt_id", name="uq_writing_draft_user_prompt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    prompt_id: Mapped[int] = mapped_column(
        ForeignKey("writing_prompt.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
        CheckConstraint(
            "algorithm_version != 'writing-rules-v2' OR "
            "(rubric_version IS NOT NULL AND rubric_snapshot IS NOT NULL)",
            name="ck_writing_feedback_v2_snapshot",
        ),
        Index(
            "ix_writing_feedback_user_prompt_created_id",
            "user_id",
            "prompt_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assist_reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("assist_reservation.id", ondelete="SET NULL"), unique=True, default=None
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    prompt_id: Mapped[int] = mapped_column(
        ForeignKey("writing_prompt.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    word_count: Mapped[int] = mapped_column(Integer)
    sentence_count: Mapped[int] = mapped_column(Integer)
    ready: Mapped[bool] = mapped_column(Boolean)
    checks: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    algorithm_version: Mapped[str] = mapped_column(
        String(50), default="legacy-v1", server_default="legacy-v1"
    )
    rubric_version: Mapped[str | None] = mapped_column(String(71), default=None)
    rubric_snapshot: Mapped[dict[str, object] | None] = mapped_column(
        JSONB(none_as_null=True), default=None
    )
    analysis_mode: Mapped[AnalysisMode] = mapped_column(String(20), default="deterministic")
    provider: Mapped[str | None] = mapped_column(String(80), default=None)
    assisted_summary: Mapped[str | None] = mapped_column(Text, default=None)
    assisted_suggestions: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB, default=None
    )
    assisted_confidence: Mapped[float | None] = mapped_column(Float, default=None)
    assisted_cost_microusd: Mapped[int] = mapped_column(Integer, default=0)
    assisted_error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    human_rating: Mapped[HumanRating | None] = mapped_column(String(20), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotebookEntry(Base):
    """Anotação pessoal que nunca modifica o conteúdo curricular."""

    __tablename__ = "notebook_entry"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('note','favorite_phrase','personal_example',"
            "'recurring_error','teacher_question')",
            name="ck_notebook_kind",
        ),
        Index("ix_notebook_entry_user_updated_id", "user_id", "updated_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    kind: Mapped[NotebookKind] = mapped_column(String(30))
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
    __table_args__ = (Index("ix_refresh_expiry", "expires_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    family_id: Mapped[str] = mapped_column(String(32), index=True)
    successor_jti: Mapped[str | None] = mapped_column(String(32), default=None)
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
        CheckConstraint("revision >= 0", name="ck_study_session_progress_revision"),
        CheckConstraint("total_seconds >= 0", name="ck_study_seconds"),
        CheckConstraint(
            "current_step IN ('preparar','assistir','estudar','praticar','revisar')",
            name="ck_study_step",
        ),
        CheckConstraint(
            "jsonb_typeof(completed_steps) = 'array' AND completed_steps <@ "
            """'["preparar","assistir","estudar","praticar","revisar"]'::jsonb""",
            name="ck_study_completed_steps",
        ),
        UniqueConstraint("user_id", "lesson_id", name="uq_study_session_user_lesson"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    current_step: Mapped[str] = mapped_column(String(20))
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
        CheckConstraint(
            "step IN ('preparar','assistir','estudar','praticar','revisar')", name="ck_step_name"
        ),
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
    timezone: Mapped[str] = mapped_column(String(80), default="UTC", server_default="UTC")
    preferred_days: Mapped[list[str]] = mapped_column(JSONB, default=list)
    goal: Mapped[str] = mapped_column(String(200), default="Criar constância no inglês")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class StudyActivitySession(Base):
    """Âncora de tempo do servidor, sem identificador permanente de dispositivo."""

    __tablename__ = "study_activity_session"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StudyActivityEvent(Base):
    """Recibo imutável. Retry não cria intervalos novos."""

    __tablename__ = "study_activity_event"
    __table_args__ = (
        UniqueConstraint("user_id", "operation_key", name="uq_activity_event_key"),
        CheckConstraint("duration_ms BETWEEN 1 AND 30000", name="ck_activity_duration"),
        CheckConstraint("credited_ms BETWEEN 0 AND duration_ms", name="ck_activity_credit"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("study_activity_session.id", ondelete="CASCADE"), index=True
    )
    operation_key: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer)
    credited_ms: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class StudyActiveInterval(Base):
    """Intervalos disjuntos por conta, inclusive entre aulas/abas diferentes."""

    __tablename__ = "study_active_interval"
    __table_args__ = (
        CheckConstraint(
            "ends_at > starts_at AND ends_at <= starts_at + interval '30 seconds'",
            name="ck_active_interval_duration",
        ),
        Index("ix_active_interval_user_end", "user_id", "ends_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("study_activity_event.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class PracticeSession(Base):
    """Seleção imutável de exercícios que pode ser retomada entre dispositivos."""

    __tablename__ = "practice_session"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_practice_session_user_idempotency"),
        Index(
            "uq_practice_session_active_user_lesson",
            "user_id",
            "lesson_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        CheckConstraint("mode IN ('guided', 'quick', 'mistakes')", name="ck_practice_session_mode"),
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_practice_session_status",
        ),
        CheckConstraint("current_position >= 0", name="ck_practice_session_position_nonnegative"),
        CheckConstraint("total_items > 0", name="ck_practice_session_total_positive"),
        CheckConstraint("state_revision > 0", name="ck_practice_session_revision_positive"),
        CheckConstraint(
            "objective IS NULL OR objective IN "
            "('recognize', 'apply', 'correct', 'produce', 'listen')",
            name="ck_practice_session_objective",
        ),
        CheckConstraint(
            "(mode = 'mistakes' AND source_session_id IS NOT NULL) OR "
            "(mode != 'mistakes' AND source_session_id IS NULL)",
            name="ck_practice_session_source_by_mode",
        ),
        CheckConstraint(
            "current_position < total_items",
            name="ck_practice_session_position_in_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lesson.id", ondelete="CASCADE"), index=True)
    source_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"), default=None
    )
    idempotency_key: Mapped[str] = mapped_column(String(36))
    mode: Mapped[PracticeMode] = mapped_column(String(20))
    activity_type: Mapped[str | None] = mapped_column(String(40), default=None)
    skill: Mapped[str | None] = mapped_column(String(40), default=None)
    objective: Mapped[ExerciseObjective | None] = mapped_column(String(20), default=None)
    lesson_version: Mapped[int] = mapped_column(Integer)
    content_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[PracticeStatus] = mapped_column(String(20), default="active")
    current_position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_items: Mapped[int] = mapped_column(Integer)
    state_revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_state_key: Mapped[str | None] = mapped_column(String(36), default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    lesson: Mapped[Lesson] = relationship(lazy="joined")
    items: Mapped[list["PracticeSessionItem"]] = relationship(
        back_populates="practice_session",
        cascade="all, delete-orphan",
        order_by="PracticeSessionItem.position",
        lazy="selectin",
    )


class PracticeSessionItem(Base):
    """Estado permitido de um exercício dentro de uma sessão específica."""

    __tablename__ = "practice_session_item"
    __table_args__ = (
        UniqueConstraint(
            "practice_session_id", "exercise_id", name="uq_practice_item_session_exercise"
        ),
        UniqueConstraint(
            "practice_session_id", "position", name="uq_practice_item_session_position"
        ),
        CheckConstraint("position >= 0", name="ck_practice_item_position_nonnegative"),
        CheckConstraint("attempt_count >= 0", name="ck_practice_item_attempts_nonnegative"),
        CheckConstraint("highest_hint_level >= 0", name="ck_practice_item_hint_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    practice_session_id: Mapped[int] = mapped_column(
        ForeignKey("practice_session.id", ondelete="CASCADE"), index=True
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercise.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_try_correct: Mapped[bool | None] = mapped_column(Boolean, default=None)
    highest_hint_level: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    answer_revealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    practice_session: Mapped[PracticeSession] = relationship(back_populates="items")
    exercise: Mapped[Exercise] = relationship(lazy="selectin")
    attempts: Mapped[list["ExerciseAttempt"]] = relationship(
        back_populates="practice_session_item",
        order_by="ExerciseAttempt.id",
        lazy="selectin",
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
    practice_session_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_session_item.id", ondelete="SET NULL"),
        index=True,
        default=None,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(36), default=None)
    answer: Mapped[str] = mapped_column(Text)
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exercise: Mapped[Exercise] = relationship(lazy="selectin")
    practice_session_item: Mapped[PracticeSessionItem | None] = relationship(
        back_populates="attempts"
    )


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
        Index(
            "ix_review_item_user_status_created_id",
            "user_id",
            "status",
            "created_at",
            "id",
        ),
        CheckConstraint("revision >= 0", name="ck_review_item_revision"),
        CheckConstraint(
            "interval_days >= 0 AND repetitions >= 0 AND lapses >= 0 AND ease_factor >= 1.3",
            name="ck_review_counters",
        ),
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
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    ease_factor: Mapped[float] = mapped_column(Float, default=2.5)
    interval_days: Mapped[int] = mapped_column(Integer, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lesson: Mapped[Lesson] = relationship(lazy="selectin")
    vocab_item: Mapped[VocabItem | None] = relationship(lazy="selectin")


class ReviewEvent(Base):
    """Recibo imutável: sobrevive à exclusão do item, não à exclusão da conta."""

    __tablename__ = "review_event"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_review_event_key"),
        CheckConstraint("quality BETWEEN 0 AND 5", name="ck_review_event_quality"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("review_item.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(String(36))
    fingerprint: Mapped[str] = mapped_column(String(64))
    quality: Mapped[int] = mapped_column(Integer)
    algorithm_version: Mapped[str] = mapped_column(String(30))
    before_state: Mapped[dict[str, object]] = mapped_column(JSONB)
    after_state: Mapped[dict[str, object]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceContentSnapshot(Base):
    """Private, immutable content actually used by a new learning event.

    Exactly one real FK, not an unverifiable polymorphic source_id. Deleting
    the event/account cascades its snapshot; editing it is forbidden by trigger.
    No backfill of unknown historical content.
    """

    __tablename__ = "evidence_content_snapshot"
    __table_args__ = (
        CheckConstraint("schema_version = '1.0'", name="ck_snapshot_schema"),
        CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_snapshot_hash"),
        CheckConstraint(
            "jsonb_typeof(content) = 'object' AND octet_length(content::text) <= 262144",
            name="ck_snapshot_content",
        ),
        CheckConstraint(
            "num_nonnulls(exercise_attempt_id, practice_item_id, writing_feedback_id, "
            "speaking_attempt_id, checkpoint_attempt_id) = 1",
            name="ck_snapshot_one_parent",
        ),
        Index("ix_snapshot_user_created", "user_id", "created_at", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    exercise_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercise_attempt.id", ondelete="CASCADE"), unique=True
    )
    practice_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("practice_session_item.id", ondelete="CASCADE"), unique=True
    )
    writing_feedback_id: Mapped[int | None] = mapped_column(
        ForeignKey("writing_feedback.id", ondelete="CASCADE"), unique=True
    )
    speaking_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("speaking_attempt.id", ondelete="CASCADE"), unique=True
    )
    checkpoint_attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("course_review_attempt.id", ondelete="CASCADE"), unique=True
    )
    schema_version: Mapped[str] = mapped_column(String(10), default="1.0")
    content: Mapped[dict[str, object]] = mapped_column(JSONB)
    content_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthRateBucket(Base):
    """Contadores por janela; identidade e origem são HMAC, nunca e-mail/IP em claro."""

    __tablename__ = "auth_rate_bucket"
    __table_args__ = (
        CheckConstraint("count > 0", name="ck_auth_rate_count"),
        # A limpeza de janelas antigas roda em todo login/registro e filtra por
        # window_start, segunda coluna da PK: sem índice próprio é seq scan.
        Index("ix_auth_rate_bucket_window_start", "window_start"),
    )
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
