"""BE-47: leitura editorial e inserção de evidências pelo worker de diálogo.

Sem escrita no conteúdo, UPDATE/DELETE de evidências ou acesso a contas.
Revision ID: a18d7e4c2b91
Revises: b7e5f1c38a42
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a18d7e4c2b91"
down_revision: str | None = "b7e5f1c38a42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EDITORIAL = "course, lesson, lesson_goal, grammar_block, grammar_row, phrase, vocab_item, lesson_media"
DERIVED = "skill_evidence, review_item"
SEQUENCES = "skill_evidence_id_seq, review_item_id_seq"


def upgrade() -> None:
    op.execute(f"""DO $$ BEGIN
        IF current_user = 'aulas_owner'
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_worker') THEN
            GRANT SELECT ON {EDITORIAL} TO aulas_worker;
            GRANT INSERT ON {DERIVED} TO aulas_worker;
            GRANT SELECT (id, user_id, source_type, source_id) ON skill_evidence TO aulas_worker;
            GRANT SELECT (id, user_id, source_key, origin_reason) ON review_item TO aulas_worker;
            GRANT USAGE ON SEQUENCE {SEQUENCES} TO aulas_worker;
        END IF;
    END $$""")


def downgrade() -> None:
    # Reverte apenas permissões; nenhuma evidência ou revisão é apagada.
    op.execute(f"""DO $$ BEGIN
        IF current_user = 'aulas_owner'
           AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aulas_worker') THEN
            REVOKE SELECT ON {EDITORIAL} FROM aulas_worker;
            REVOKE INSERT ON {DERIVED} FROM aulas_worker;
            REVOKE SELECT (id, user_id, source_type, source_id) ON skill_evidence FROM aulas_worker;
            REVOKE SELECT (id, user_id, source_key, origin_reason) ON review_item FROM aulas_worker;
            REVOKE USAGE ON SEQUENCE {SEQUENCES} FROM aulas_worker;
        END IF;
    END $$""")
