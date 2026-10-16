"""Benchmark DB-41 de usuários, eventos, fila, painel, currículo e expiração."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from uuid import uuid4

from ops.review_performance import summarize_plan

LOCK_KEY = "aulas-ingles:database-performance:v1"
SIZES = (1_000, 10_000)
CANDIDATE = "ix_transcription_queue_ready_bench"


async def run() -> dict[str, object]:
    from app.db.session import dispose_engine, get_engine
    from sqlalchemy import text

    engine = get_engine()
    prefix = f"benchmark41-db-{uuid4().hex}"
    users_created = 0
    candidate_created = False
    lock_acquired = False
    event_users: dict[int, int] = {}
    job_users: dict[int, int] = {}
    report: dict[str, object] = {
        "contract": "database-performance-v1",
        "volumes": list(SIZES),
        "datasets": {},
    }

    async with engine.connect() as connection:
        try:
            identity = (
                await connection.execute(
                    text(
                        "SELECT current_database(),current_user,"
                        "shobj_description(oid,'pg_database') "
                        "FROM pg_database WHERE datname=current_database()"
                    )
                )
            ).one()
            report["environment"] = {
                "database": identity[0],
                "role": identity[1],
                "marker": identity[2],
                "postgres": await connection.scalar(text("SHOW server_version")),
            }
            lock_acquired = bool(
                await connection.scalar(
                    text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                    {"key": LOCK_KEY},
                )
            )
            if not lock_acquired:
                raise RuntimeError("Outro benchmark DB-41 já está em execução.")

            lesson_id = await connection.scalar(
                text("SELECT id FROM lesson WHERE number=31 ORDER BY id LIMIT 1")
            )
            cue_id = await connection.scalar(
                text(
                    "SELECT tc.id FROM transcript_cue tc "
                    "JOIN lesson_media lm ON lm.id=tc.media_id "
                    "JOIN lesson l ON l.id=lm.lesson_id "
                    "WHERE l.number=31 ORDER BY tc.id LIMIT 1"
                )
            )
            if lesson_id is None or cue_id is None:
                raise RuntimeError(
                    "Aula/cue 31 ausente; execute make test-api-prepare."
                )

            async def create_user(label: str) -> int:
                nonlocal users_created
                user_id = await connection.scalar(
                    text(
                        "INSERT INTO app_user(email,password_hash,display_name) "
                        "VALUES (:email,'!disabled-benchmark!','Benchmark DB-41') "
                        "RETURNING id"
                    ),
                    {"email": f"{prefix}-{label}@example.invalid"},
                )
                users_created += 1
                await connection.commit()
                return int(user_id)

            async def seed_users(size: int) -> float:
                nonlocal users_created
                started = time.perf_counter()
                result = await connection.execute(
                    text(
                        "INSERT INTO app_user(email,password_hash,display_name) "
                        "SELECT :prefix || g || '@example.invalid',"
                        "'!disabled-benchmark!','Benchmark DB-41' "
                        "FROM generate_series(1,:size) g"
                    ),
                    {"prefix": f"{prefix}-users-{size}-", "size": size},
                )
                users_created += int(result.rowcount)
                await connection.commit()
                return round((time.perf_counter() - started) * 1000, 2)

            async def seed_events(user_id: int, size: int) -> float:
                session_id = str(uuid4())
                await connection.execute(
                    text(
                        "INSERT INTO study_activity_session(id,user_id,lesson_id,started_at) "
                        "VALUES (:session_id,:user_id,:lesson_id,"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00')"
                    ),
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "lesson_id": lesson_id,
                    },
                )
                started = time.perf_counter()
                await connection.execute(
                    text(
                        "INSERT INTO study_activity_event("
                        "user_id,session_id,operation_key,fingerprint,duration_ms,"
                        "credited_ms,received_at) "
                        "SELECT :user_id,:session_id,"
                        "'00000000-0000-4000-8000-' || lpad(g::text,12,'0'),"
                        "repeat('a',64),1000,1000,TIMESTAMPTZ '2026-01-01 00:00:00+00' "
                        "+ g * INTERVAL '2 seconds' FROM generate_series(1,:size) g"
                    ),
                    {"user_id": user_id, "session_id": session_id, "size": size},
                )
                await connection.execute(
                    text(
                        "INSERT INTO study_active_interval("
                        "event_id,user_id,lesson_id,starts_at,ends_at) "
                        "SELECT id,:user_id,:lesson_id,received_at - INTERVAL '1 second',"
                        "received_at FROM study_activity_event "
                        "WHERE user_id=:user_id"
                    ),
                    {"user_id": user_id, "lesson_id": lesson_id},
                )
                await connection.commit()
                return round((time.perf_counter() - started) * 1000, 2)

            async def seed_jobs(user_id: int, size: int) -> float:
                started = time.perf_counter()
                await connection.execute(
                    text(
                        "INSERT INTO speaking_attempt("
                        "user_id,transcript_cue_id,duration_ms,status,consented_at,created_at) "
                        "SELECT :user_id,:cue_id,1000,'pending',"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00',"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00' + g * INTERVAL '1 second' "
                        "FROM generate_series(1,:size) g"
                    ),
                    {"user_id": user_id, "cue_id": cue_id, "size": size},
                )
                await connection.execute(
                    text(
                        "INSERT INTO transcription_job("
                        "user_id,speaking_attempt_id,status,provider,idempotency_key,"
                        "attempt_count,max_attempts,low_confidence,cost_microusd,"
                        "next_attempt_at,requested_at,expires_at) "
                        "SELECT :user_id,id,'queued','benchmark',"
                        ":key || '-' || id,0,3,false,0,"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00' "
                        "+ (row_number() OVER (ORDER BY id) / 5) * INTERVAL '1 second',"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00',"
                        "TIMESTAMPTZ '2030-01-01 00:00:00+00' "
                        "FROM speaking_attempt WHERE user_id=:user_id"
                    ),
                    {"user_id": user_id, "key": f"{prefix}-job"},
                )
                await connection.commit()
                return round((time.perf_counter() - started) * 1000, 2)

            datasets: dict[str, object] = {}
            report["datasets"] = datasets
            for size in SIZES:
                event_user = await create_user(f"events-{size}")
                job_user = await create_user(f"jobs-{size}")
                event_users[size] = event_user
                job_users[size] = job_user
                datasets[str(size)] = {
                    "users_insert_ms": await seed_users(size),
                    "events_insert_ms": await seed_events(event_user, size),
                    "jobs_insert_ms": await seed_jobs(job_user, size),
                }

            for table_name in (
                "app_user",
                "study_activity_event",
                "study_active_interval",
                "transcription_job",
            ):
                await connection.execute(text(f"ANALYZE {table_name}"))
            await connection.commit()

            async def explain(
                sql: str, parameters: dict[str, object]
            ) -> dict[str, object]:
                document = await connection.scalar(
                    text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"), parameters
                )
                return summarize_plan(document)

            queue_sql = (
                "SELECT id FROM transcription_job WHERE status='queued' "
                "AND next_attempt_at <= TIMESTAMPTZ '2027-01-01 00:00:00+00' "
                "AND attempt_count < max_attempts "
                "AND expires_at > TIMESTAMPTZ '2027-01-01 00:00:00+00' "
                "ORDER BY next_attempt_at,id LIMIT 1"
            )
            plans = {
                "auth_user_10k": await explain(
                    "SELECT id FROM app_user WHERE email=:email",
                    {"email": f"{prefix}-users-10000-10000@example.invalid"},
                ),
                "weekly_panel_10k": await explain(
                    "SELECT coalesce(sum(extract(epoch FROM ends_at-starts_at)),0) "
                    "FROM study_active_interval WHERE user_id=:user_id "
                    "AND ends_at > TIMESTAMPTZ '2025-12-31 00:00:00+00' "
                    "AND starts_at < TIMESTAMPTZ '2027-01-01 00:00:00+00'",
                    {"user_id": event_users[10_000]},
                ),
                "transcription_queue_10k": await explain(queue_sql, {}),
                "transcription_expiry_10k": await explain(
                    "SELECT id FROM transcription_job "
                    "WHERE expires_at < TIMESTAMPTZ '2031-01-01 00:00:00+00' "
                    "ORDER BY expires_at,id LIMIT 100",
                    {},
                ),
                "curriculum": await explain(
                    "SELECT l.id,l.number,l.position FROM lesson l "
                    "JOIN course c ON c.id=l.course_id "
                    "JOIN course_unit cu ON cu.id=l.unit_id "
                    "WHERE c.slug='voa-level-1' AND cu.status='published' "
                    "ORDER BY cu.position,l.position",
                    {},
                ),
            }
            report["baseline_plans"] = plans

            started = time.perf_counter()
            await connection.execute(
                text(
                    f"CREATE INDEX {CANDIDATE} ON transcription_job "
                    "(next_attempt_at,id) WHERE status='queued'"
                )
            )
            await connection.commit()
            candidate_created = True
            await connection.execute(text("ANALYZE transcription_job"))
            await connection.commit()
            candidate_build_ms = round((time.perf_counter() - started) * 1000, 2)
            candidate_plan = await explain(queue_sql, {})
            candidate_size_before = int(
                await connection.scalar(
                    text("SELECT pg_relation_size(to_regclass(:name))"),
                    {"name": CANDIDATE},
                )
                or 0
            )
            write_user = await create_user("jobs-write-probe")
            indexed_write_ms = await seed_jobs(write_user, 10_000)
            report["queue_candidate"] = {
                "definition": "(next_attempt_at,id) WHERE status='queued'",
                "build_ms": candidate_build_ms,
                "plan": candidate_plan,
                "size_bytes_before_write_probe": candidate_size_before,
                "size_bytes_after_write_probe": int(
                    await connection.scalar(
                        text("SELECT pg_relation_size(to_regclass(:name))"),
                        {"name": CANDIDATE},
                    )
                    or 0
                ),
                "insert_10k_without_candidate_ms": (
                    report["datasets"]["10000"]["jobs_insert_ms"]  # type: ignore[index]
                ),
                "insert_10k_with_candidate_ms": indexed_write_ms,
            }
        finally:
            try:
                # Qualquer erro SQL aborta a transação PostgreSQL; a limpeza precisa
                # começar fora desse estado para não esconder a causa original.
                await connection.rollback()
                if candidate_created:
                    await connection.execute(text(f"DROP INDEX IF EXISTS {CANDIDATE}"))
                    await connection.commit()
                result = await connection.execute(
                    text("DELETE FROM app_user WHERE email LIKE :prefix"),
                    {"prefix": f"{prefix}%"},
                )
                await connection.commit()
                if int(result.rowcount) != users_created:
                    raise RuntimeError(
                        "Limpeza não removeu exatamente os usuários sintéticos."
                    )
            finally:
                if lock_acquired:
                    await connection.execute(
                        text("SELECT pg_advisory_unlock(hashtext(:key))"),
                        {"key": LOCK_KEY},
                    )
                    await connection.commit()
                await dispose_engine()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    from app.db.test_safety import UnsafeTestDatabase, configure_test_environment

    try:
        configure_test_environment(os.environ)
        result = asyncio.run(run())
    except UnsafeTestDatabase as error:
        print(f"Benchmark bloqueado: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
