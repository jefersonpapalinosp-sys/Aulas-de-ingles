"""Sprint 61: retomada de áudio sem alterar a revisão das respostas."""
from alembic import op

revision = "f61a1b8c9009"
down_revision = "e60a1b8c9008"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""CREATE TABLE native_listening_position (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	session_id INTEGER NOT NULL,
	position_seconds FLOAT DEFAULT '0' NOT NULL,
	revision INTEGER DEFAULT '0' NOT NULL,
	completed BOOLEAN DEFAULT 'false' NOT NULL,
	operation_key UUID,
	fingerprint VARCHAR(64),
	changed_at TIMESTAMP WITH TIME ZONE,
	updated_at TIMESTAMP WITH TIME ZONE,
	CONSTRAINT native_listening_position_pkey PRIMARY KEY (id),
	CONSTRAINT native_listening_position_user_id_session_id_key UNIQUE (user_id, session_id),
	CONSTRAINT native_listening_position_session_id_user_id_fkey FOREIGN KEY(session_id, user_id) REFERENCES native_listening_session (id, user_id) ON DELETE CASCADE,
	CONSTRAINT ck_native_position_bounds CHECK (revision >= 0 AND position_seconds >= 0),
	CONSTRAINT ck_native_position_end CHECK (NOT completed OR position_seconds = 0),
	CONSTRAINT native_listening_position_user_id_fkey FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE CASCADE
)""")
    op.execute('CREATE INDEX ix_native_listening_position_session ON native_listening_position (session_id)')
    op.create_index("ix_native_session_user_id", "native_listening_session", ["user_id", "id"])
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime') THEN
        GRANT SELECT, INSERT, UPDATE ON native_listening_position TO aulas_runtime;
        GRANT USAGE ON SEQUENCE native_listening_position_id_seq TO aulas_runtime;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_backup') THEN
        GRANT SELECT ON native_listening_position TO aulas_backup;
        GRANT SELECT ON SEQUENCE native_listening_position_id_seq TO aulas_backup;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM native_listening_position) THEN
        RAISE EXCEPTION 'Listening has saved positions; preserve the schema';
      END IF;
    END $$;""")
    op.drop_table("native_listening_position")
    op.drop_index("ix_native_session_user_id", table_name="native_listening_session")
