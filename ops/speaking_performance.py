"""Benchmark 1k/10k da paginação de speaking no PostgreSQL descartável."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any, cast
from uuid import uuid4

from ops.review_performance import distribution, summarize_plan

LOCK_KEY = "aulas-ingles:speaking-performance:v1"
CANDIDATE_INDEX = "ix_speaking_attempt_user_status_created_id_bench"
FINAL_INDEX = "ix_speaking_attempt_user_status_created_id"
SIZES = (1_000, 10_000)
PAGE_SIZE = 50


async def run(samples: int, concurrency: int) -> dict[str, object]:
    # A guarda configura/valida o alvo antes destes imports criarem a engine.
    from app.core.config import get_settings
    from app.core.security import criar_token
    from app.db.models import Lesson, LessonMedia, TranscriptCue, User
    from app.db.session import dispose_engine, get_engine
    from app.main import create_app
    from app.pagination import decode_time_id_cursor, encode_time_id_cursor
    from app.performance import BYTES_HEADER, DURATION_HEADER, POOL_HEADER, SQL_HEADER
    from httpx import ASGITransport, AsyncClient, Response
    from sqlalchemy import delete, select, text

    settings = get_settings()
    settings.performance_probe_enabled = True
    settings.log_level = "warning"
    engine = get_engine()
    created_users: dict[int, str] = {}
    candidate_created = False
    lock_acquired = False
    datasets: dict[str, object] = {}
    report: dict[str, object] = {
        "contract": "speaking-performance-v1",
        "samples_per_route": samples,
        "page_size": PAGE_SIZE,
        "datasets": datasets,
    }

    async with engine.connect() as control:
        try:
            identity = (
                await control.execute(
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
                "postgres": await control.scalar(text("SHOW server_version")),
            }
            lock_acquired = bool(
                await control.scalar(
                    text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                    {"key": LOCK_KEY},
                )
            )
            if not lock_acquired:
                raise RuntimeError("Outro benchmark de speaking já está em execução.")

            cue_id = await control.scalar(
                select(TranscriptCue.id)
                .join(LessonMedia, TranscriptCue.media_id == LessonMedia.id)
                .join(Lesson, LessonMedia.lesson_id == Lesson.id)
                .where(Lesson.number == 31)
                .limit(1)
            )
            if cue_id is None:
                raise RuntimeError(
                    "Cue da Aula 31 ausente; execute make test-api-prepare."
                )

            async def create_user(label: str) -> int:
                email = f"benchmark41-speaking-{label}-{uuid4().hex}@example.invalid"
                result = await control.execute(
                    text(
                        "INSERT INTO app_user(email,password_hash,display_name) "
                        "VALUES (:email,'!disabled-benchmark!','Benchmark 41') RETURNING id"
                    ),
                    {"email": email},
                )
                user_id = int(result.scalar_one())
                created_users[user_id] = email
                await control.commit()
                return user_id

            async def seed_attempts(user_id: int, size: int) -> float:
                started = time.perf_counter()
                await control.execute(
                    text(
                        "INSERT INTO speaking_attempt("
                        "user_id,transcript_cue_id,duration_ms,self_rating,consented_at,"
                        "status,integrity_state,created_at) "
                        "SELECT :user_id,:cue_id,1000,'confident',"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00','ready','unknown',"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00' "
                        "+ ((g - 1) / 5) * INTERVAL '1 second' "
                        "FROM generate_series(1,:size) AS g"
                    ),
                    {"user_id": user_id, "cue_id": cue_id, "size": size},
                )
                await control.commit()
                return round((time.perf_counter() - started) * 1000, 2)

            users: dict[int, int] = {}
            baseline_insert: dict[int, float] = {}
            for size in SIZES:
                user_id = await create_user(str(size))
                users[size] = user_id
                baseline_insert[size] = await seed_attempts(user_id, size)
            await control.execute(text("ANALYZE speaking_attempt"))
            await control.commit()

            app = create_app()
            tokens = {
                size: criar_token(user_id, "access")[0]
                for size, user_id in users.items()
            }

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://benchmark"
            ) as client:

                async def request(size: int, cursor: str | None = None) -> Response:
                    response = await client.get(
                        "/api/speaking/attempts/page",
                        headers={"Authorization": f"Bearer {tokens[size]}"},
                        params={
                            "course": "voa-level-1",
                            "unit": "31-40",
                            "limit": PAGE_SIZE,
                            **({"cursor": cursor} if cursor else {}),
                        },
                    )
                    if response.status_code != 200:
                        raise RuntimeError(
                            f"Página de speaking recusada: HTTP {response.status_code}."
                        )
                    if int(response.headers[SQL_HEADER]) != 5:
                        raise RuntimeError(
                            "Orçamento SQL de speaking mudou no benchmark."
                        )
                    if int(response.headers[POOL_HEADER]) > 1:
                        raise RuntimeError(
                            "Página de speaking usou mais de um checkout."
                        )
                    if int(response.headers[BYTES_HEADER]) != len(response.content):
                        raise RuntimeError(
                            "Header de payload não corresponde à resposta."
                        )
                    return response

                async def expected_ids(user_id: int) -> list[int]:
                    rows = await control.execute(
                        text(
                            "SELECT id FROM speaking_attempt "
                            "WHERE user_id=:user_id AND status='ready' "
                            "ORDER BY created_at DESC,id DESC"
                        ),
                        {"user_id": user_id},
                    )
                    return list(rows.scalars())

                async def traverse(size: int) -> dict[str, object]:
                    expected = await expected_ids(users[size])
                    received: list[int] = []
                    seen_cursors: set[str] = set()
                    cursor = None
                    pages = 0
                    started = time.perf_counter()
                    while True:
                        body = (await request(size, cursor)).json()
                        received.extend(item["id"] for item in body["items"])
                        pages += 1
                        cursor = body["next_cursor"]
                        if cursor is None:
                            break
                        if cursor in seen_cursors:
                            raise RuntimeError(
                                "Cursor repetido no percurso de speaking."
                            )
                        seen_cursors.add(cursor)
                    if received != expected or len(received) != len(set(received)):
                        raise RuntimeError(
                            "Speaking apresentou lacuna, duplicata ou ordem instável."
                        )
                    return {
                        "items": len(received),
                        "pages": pages,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    }

                async def deep_cursor(size: int) -> str:
                    row = (
                        await control.execute(
                            text(
                                "SELECT created_at,id FROM speaking_attempt "
                                "WHERE user_id=:user_id AND status='ready' "
                                "ORDER BY created_at DESC,id DESC "
                                "OFFSET :offset LIMIT 1"
                            ),
                            {"user_id": users[size], "offset": int(size * 0.90) - 1},
                        )
                    ).one()
                    return encode_time_id_cursor(row.created_at, row.id)

                async def measure(size: int, cursor: str | None) -> dict[str, object]:
                    for _ in range(3):
                        await request(size, cursor)
                    app_ms: list[float] = []
                    wall_ms: list[float] = []
                    payloads: list[int] = []
                    checkouts: list[int] = []
                    for _ in range(samples):
                        started = time.perf_counter()
                        response = await request(size, cursor)
                        wall_ms.append((time.perf_counter() - started) * 1000)
                        app_ms.append(float(response.headers[DURATION_HEADER]))
                        payloads.append(int(response.headers[BYTES_HEADER]))
                        checkouts.append(int(response.headers[POOL_HEADER]))
                    return {
                        "app_ms": distribution(app_ms),
                        "wall_ms": distribution(wall_ms),
                        "payload_bytes": {"min": min(payloads), "max": max(payloads)},
                        "sql_queries": 5,
                        "pool_checkouts_per_request_max": max(checkouts),
                    }

                async def explain(size: int, cursor: str) -> dict[str, object]:
                    boundary = decode_time_id_cursor(cursor)
                    document = await control.scalar(
                        text(
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                            "SELECT sa.id,c.slug,cu.slug,l.number,sa.created_at "
                            "FROM speaking_attempt sa "
                            "JOIN transcript_cue tc ON tc.id=sa.transcript_cue_id "
                            "JOIN lesson_media lm ON lm.id=tc.media_id "
                            "JOIN lesson l ON l.id=lm.lesson_id "
                            "JOIN course c ON c.id=l.course_id "
                            "JOIN course_unit cu ON cu.id=l.unit_id "
                            "WHERE sa.user_id=:user_id AND sa.status='ready' "
                            "AND c.slug='voa-level-1' AND cu.slug='31-40' "
                            "AND (sa.created_at,sa.id) < (:created_at,:row_id) "
                            "ORDER BY sa.created_at DESC,sa.id DESC LIMIT :limit"
                        ),
                        {
                            "user_id": users[size],
                            "created_at": boundary.timestamp,
                            "row_id": boundary.row_id,
                            "limit": PAGE_SIZE + 1,
                        },
                    )
                    return summarize_plan(document)

                cursors = {size: await deep_cursor(size) for size in SIZES}
                for size in SIZES:
                    datasets[str(size)] = {
                        "baseline_insert_ms": baseline_insert[size],
                        "stable_traversal": await traverse(size),
                    }

                async def measurements() -> dict[str, object]:
                    result: dict[str, object] = {}
                    for size in SIZES:
                        result[str(size)] = {
                            "first_page": await measure(size, None),
                            "deep_page_90_percent": await measure(size, cursors[size]),
                            "deep_plan": await explain(size, cursors[size]),
                        }
                    return result

                final_index_present = bool(
                    await control.scalar(
                        text("SELECT to_regclass(:name) IS NOT NULL"),
                        {"name": FINAL_INDEX},
                    )
                )
                report["current_schema"] = await measurements()
                report["candidate_comparison_available"] = not final_index_present

                if not final_index_present:
                    started = time.perf_counter()
                    await control.execute(
                        text(
                            f"CREATE INDEX {CANDIDATE_INDEX} ON speaking_attempt "
                            "(user_id,status,created_at,id)"
                        )
                    )
                    await control.commit()
                    candidate_created = True
                    build_ms = round((time.perf_counter() - started) * 1000, 2)
                    await control.execute(text("ANALYZE speaking_attempt"))
                    await control.commit()
                    size_before = int(
                        await control.scalar(
                            text("SELECT pg_relation_size(to_regclass(:name))"),
                            {"name": CANDIDATE_INDEX},
                        )
                        or 0
                    )
                    write_user = await create_user("write-probe")
                    indexed_insert_ms = await seed_attempts(write_user, 10_000)
                    size_after = int(
                        await control.scalar(
                            text("SELECT pg_relation_size(to_regclass(:name))"),
                            {"name": CANDIDATE_INDEX},
                        )
                        or 0
                    )
                    report["candidate_index"] = {
                        "columns": ["user_id", "status", "created_at", "id"],
                        "build_ms": build_ms,
                        "size_bytes_after_11k_rows": size_before,
                        "size_bytes_after_21k_rows": size_after,
                        "insert_10k_without_index_ms": baseline_insert[10_000],
                        "insert_10k_with_index_ms": indexed_insert_ms,
                    }
                    report["with_candidate"] = await measurements()

                checked_out_max = 0
                sampling = True

                async def sample_pool() -> None:
                    nonlocal checked_out_max
                    while sampling:
                        checked_out_max = max(
                            checked_out_max,
                            int(cast(Any, engine.sync_engine.pool).checkedout()),
                        )
                        await asyncio.sleep(0)

                sampler = asyncio.create_task(sample_pool())
                started = time.perf_counter()
                responses = await asyncio.gather(
                    *(request(10_000, cursors[10_000]) for _ in range(concurrency))
                )
                burst_ms = round((time.perf_counter() - started) * 1000, 2)
                sampling = False
                await sampler
                report["concurrent_burst"] = {
                    "requests": concurrency,
                    "wall_ms": burst_ms,
                    "pool_checked_out_max": checked_out_max,
                    "request_p95_ms": distribution(
                        [
                            float(response.headers[DURATION_HEADER])
                            for response in responses
                        ]
                    )["p95"],
                    "all_status_200": all(
                        response.status_code == 200 for response in responses
                    ),
                }
        finally:
            try:
                if candidate_created:
                    await control.execute(
                        text(f"DROP INDEX IF EXISTS {CANDIDATE_INDEX}")
                    )
                    await control.commit()
                if created_users:
                    result = await control.execute(
                        delete(User).where(
                            User.id.in_(created_users),
                            User.email.in_(created_users.values()),
                        )
                    )
                    await control.commit()
                    if result.rowcount != len(created_users):
                        raise RuntimeError(
                            "Limpeza não removeu exatamente as contas criadas."
                        )
            finally:
                if lock_acquired:
                    await control.execute(
                        text("SELECT pg_advisory_unlock(hashtext(:key))"),
                        {"key": LOCK_KEY},
                    )
                    await control.commit()
                await dispose_engine()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    if not 10 <= args.samples <= 200 or not 2 <= args.concurrency <= 20:
        parser.error("samples deve ficar entre 10 e 200; concurrency entre 2 e 20")

    from app.db.test_safety import UnsafeTestDatabase, configure_test_environment

    try:
        configure_test_environment(os.environ)
        result = asyncio.run(run(args.samples, args.concurrency))
    except UnsafeTestDatabase as error:
        print(f"Benchmark bloqueado: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
