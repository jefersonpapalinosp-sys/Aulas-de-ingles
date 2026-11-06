"""Sprint 60: versões e sessões independentes do listening nativo."""
from alembic import op

revision = "e60a1b8c9008"
down_revision = "d59a1b8c9007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""CREATE TABLE native_listening_version (
        id SERIAL NOT NULL,
        slug VARCHAR(100) NOT NULL,
        version INTEGER NOT NULL,
        content JSONB NOT NULL,
        content_sha256 VARCHAR(64) NOT NULL,
        CONSTRAINT native_listening_version_pkey PRIMARY KEY (id),
        CONSTRAINT native_listening_version_slug_version_key UNIQUE (slug, version),
        CONSTRAINT ck_native_version_positive CHECK (version > 0)
)""")
    op.execute("""CREATE TABLE native_listening_session (
        id SERIAL NOT NULL,
        user_id INTEGER NOT NULL,
        version_id INTEGER NOT NULL,
        operation_key UUID NOT NULL,
        revision INTEGER NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        CONSTRAINT native_listening_session_pkey PRIMARY KEY (id),
        CONSTRAINT native_listening_session_user_id_operation_key_key UNIQUE (user_id, operation_key),
        CONSTRAINT native_listening_session_id_user_id_key UNIQUE (id, user_id),
        CONSTRAINT ck_native_session_revision CHECK (revision BETWEEN 0 AND 100),
        CONSTRAINT native_listening_session_user_id_fkey FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE CASCADE,
        CONSTRAINT native_listening_session_version_id_fkey FOREIGN KEY(version_id) REFERENCES native_listening_version (id) ON DELETE RESTRICT
)""")
    op.execute("""CREATE INDEX ix_native_listening_session_version_id ON native_listening_session (version_id)""")
    op.execute("""CREATE TABLE native_listening_response (
        id SERIAL NOT NULL,
        user_id INTEGER NOT NULL,
        session_id INTEGER NOT NULL,
        operation_key UUID NOT NULL,
        expected_revision INTEGER NOT NULL,
        revision INTEGER NOT NULL,
        payload JSONB NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        CONSTRAINT native_listening_response_pkey PRIMARY KEY (id),
        CONSTRAINT native_listening_response_user_id_operation_key_key UNIQUE (user_id, operation_key),
        CONSTRAINT native_listening_response_session_id_revision_key UNIQUE (session_id, revision),
        CONSTRAINT native_listening_response_session_id_user_id_fkey FOREIGN KEY(session_id, user_id) REFERENCES native_listening_session (id, user_id) ON DELETE CASCADE,
        CONSTRAINT ck_native_response_revision CHECK (expected_revision >= 0 AND revision = expected_revision + 1),
        CONSTRAINT native_listening_response_user_id_fkey FOREIGN KEY(user_id) REFERENCES app_user (id) ON DELETE CASCADE
)""")
    op.execute("""
    CREATE FUNCTION native_listening_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Native listening records are immutable; insert a new version/event'; END $$;
    """)
    op.execute("""CREATE TRIGGER native_version_immutable BEFORE UPDATE ON native_listening_version
      FOR EACH ROW EXECUTE FUNCTION native_listening_immutable();
    """)
    op.execute("""CREATE TRIGGER native_response_immutable BEFORE UPDATE ON native_listening_response
      FOR EACH ROW EXECUTE FUNCTION native_listening_immutable();
    """)
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_runtime') THEN
        GRANT SELECT ON native_listening_version, native_listening_session, native_listening_response TO aulas_runtime;
        GRANT INSERT, UPDATE ON native_listening_session TO aulas_runtime;
        GRANT INSERT ON native_listening_response TO aulas_runtime;
        GRANT USAGE ON SEQUENCE native_listening_session_id_seq, native_listening_response_id_seq TO aulas_runtime;
      END IF;
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aulas_backup') THEN
        GRANT SELECT ON native_listening_version, native_listening_session, native_listening_response TO aulas_backup;
        GRANT SELECT ON SEQUENCE native_listening_version_id_seq, native_listening_session_id_seq, native_listening_response_id_seq TO aulas_backup;
      END IF;
    END $$;""")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM native_listening_session) THEN
        RAISE EXCEPTION 'Native listening has personal data; preserve the schema';
      END IF;
    END $$;""")
    op.drop_table("native_listening_response")
    op.drop_table("native_listening_session")
    op.drop_table("native_listening_version")
    op.execute("DROP FUNCTION native_listening_immutable()")
