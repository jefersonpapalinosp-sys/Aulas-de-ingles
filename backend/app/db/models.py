"""Modelo de domínio do conteúdo das aulas.

Convenção de texto: todo campo de texto exibível guarda um **subconjunto de
Markdown** — `**negrito**`, `*itálico*`, `` `código` `` e `~~riscado~~`. HTML
cru não entra no banco, o que elimina a superfície de XSS e deixa o seed
editável à mão. Quem decide a aparência é o frontend.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class ExerciseAttempt(Base):
    """Cada tentativa, certa ou errada, com o que foi digitado.

    Guardar o texto exato é o que permite, na S4, descobrir *qual* item de
    vocabulário a pessoa erra — e não só que ela errou.
    """

    __tablename__ = "exercise_attempt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercise.id", ondelete="CASCADE"), index=True
    )
    answer: Mapped[str] = mapped_column(String(200))
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exercise: Mapped[Exercise] = relationship(lazy="selectin")


class ReviewCard(Base):
    """Uma carta de revisão espaçada: um item de vocabulário, para um usuário.

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
