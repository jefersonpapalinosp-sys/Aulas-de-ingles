"""Benchmark 1k/10k dos três históricos paginados de escrita."""

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

LOCK_KEY = "aulas-ingles:writing-performance:v1"
SYNTHETIC_TITLE = "Benchmark 41 writing prompt "
SIZES = (1_000, 10_000)
PAGE_SIZE = 50
SQL_BUDGET = {"versions": 2, "feedback": 4, "history": 2}
CANDIDATES = {
    "versions": (
        "ix_writing_revision_draft_created_id_bench",
        "writing_revision",
        "(draft_id,created_at,id)",
    ),
    "feedback": (
        "ix_writing_feedback_user_prompt_created_id_bench",
        "writing_feedback",
        "(user_id,prompt_id,created_at,id)",
    ),
    "history": (
        "ix_writing_draft_user_updated_id_bench",
        "writing_draft",
        "(user_id,updated_at,id)",
    ),
}
FINAL_INDEXES = {
    "versions": "ix_writing_revision_draft_created_id",
    "feedback": "ix_writing_feedback_user_prompt_created_id",
    "history": "ix_writing_draft_user_updated_id",
}


async def run(samples: int, concurrency: int) -> dict[str, object]:
    # A guarda configura/valida o alvo antes destes imports criarem a engine.
    from app.core.config import get_settings
    from app.core.security import criar_token
    from app.db.models import Lesson, User, WritingPrompt
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
    candidate_indexes: list[str] = []
    synthetic_prompts_created = 0
    lesson_id: int | None = None
    lock_acquired = False
    datasets: dict[str, object] = {}
    report: dict[str, object] = {
        "contract": "writing-performance-v1",
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
                raise RuntimeError("Outro benchmark de escrita já está em execução.")

            lesson_id = await control.scalar(
                select(Lesson.id).where(Lesson.number == 31).limit(1)
            )
            prompt_id = await control.scalar(
                select(WritingPrompt.id)
                .join(Lesson, WritingPrompt.lesson_id == Lesson.id)
                .where(Lesson.number == 31)
                .limit(1)
            )
            if lesson_id is None or prompt_id is None:
                raise RuntimeError(
                    "Aula/proposta 31 ausente; execute make test-api-prepare."
                )

            await control.execute(
                text(
                    "INSERT INTO writing_prompt("
                    "lesson_id,position,title,instructions,min_words,min_sentences,requirements) "
                    "SELECT :lesson_id,100000+g,:title || g,'Synthetic benchmark prompt.',"
                    "1,1,'[]'::jsonb FROM generate_series(1,10000) AS g"
                ),
                {"lesson_id": lesson_id, "title": SYNTHETIC_TITLE},
            )
            synthetic_prompts_created = 10_000
            await control.commit()

            async def create_user(label: str) -> int:
                email = f"benchmark41-writing-{label}-{uuid4().hex}@example.invalid"
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

            async def create_draft(user_id: int, target_prompt: int) -> int:
                result = await control.execute(
                    text(
                        "INSERT INTO writing_draft(user_id,prompt_id,text,revision,updated_at) "
                        "VALUES (:user_id,:prompt_id,'synthetic draft',0,"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00') RETURNING id"
                    ),
                    {"user_id": user_id, "prompt_id": target_prompt},
                )
                await control.commit()
                return int(result.scalar_one())

            async def seed_history(user_id: int, size: int) -> float:
                started = time.perf_counter()
                await control.execute(
                    text(
                        "INSERT INTO writing_draft(user_id,prompt_id,text,revision,updated_at) "
                        "SELECT :user_id,p.id,'synthetic history draft',0,"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00' "
                        "+ ((row_number() OVER (ORDER BY p.id) - 1) / 5) "
                        "* INTERVAL '1 second' "
                        "FROM writing_prompt p WHERE p.lesson_id=:lesson_id "
                        "AND p.title LIKE :title ORDER BY p.id LIMIT :size"
                    ),
                    {
                        "user_id": user_id,
                        "lesson_id": lesson_id,
                        "title": f"{SYNTHETIC_TITLE}%",
                        "size": size,
                    },
                )
                await control.commit()
                return round((time.perf_counter() - started) * 1000, 2)

            async def seed_versions(draft_id: int, size: int) -> float:
                started = time.perf_counter()
                await control.execute(
                    text(
                        "INSERT INTO writing_revision(draft_id,version,text,created_at) "
                        "SELECT :draft_id,g,'synthetic revision ' || g,"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00' "
                        "+ ((g - 1) / 5) * INTERVAL '1 second' "
                        "FROM generate_series(1,:size) AS g"
                    ),
                    {"draft_id": draft_id, "size": size},
                )
                await control.commit()
                return round((time.perf_counter() - started) * 1000, 2)

            async def seed_feedback(user_id: int, size: int) -> float:
                started = time.perf_counter()
                await control.execute(
                    text(
                        "INSERT INTO writing_feedback("
                        "user_id,prompt_id,text,word_count,sentence_count,ready,checks,"
                        "algorithm_version,analysis_mode,assisted_cost_microusd,created_at) "
                        "SELECT :user_id,:prompt_id,'synthetic feedback text',3,1,true,"
                        "'[]'::jsonb,'legacy-v1','deterministic',0,"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00' "
                        "+ ((g - 1) / 5) * INTERVAL '1 second' "
                        "FROM generate_series(1,:size) AS g"
                    ),
                    {"user_id": user_id, "prompt_id": prompt_id, "size": size},
                )
                await control.commit()
                return round((time.perf_counter() - started) * 1000, 2)

            users: dict[str, dict[int, int]] = {
                kind: {} for kind in ("versions", "feedback", "history")
            }
            baseline_insert: dict[str, dict[int, float]] = {kind: {} for kind in users}
            draft_ids: dict[int, int] = {}
            for size in SIZES:
                history_user = await create_user(f"history-{size}")
                users["history"][size] = history_user
                baseline_insert["history"][size] = await seed_history(
                    history_user, size
                )

                version_user = await create_user(f"versions-{size}")
                users["versions"][size] = version_user
                draft_ids[size] = await create_draft(version_user, prompt_id)
                baseline_insert["versions"][size] = await seed_versions(
                    draft_ids[size], size
                )

                feedback_user = await create_user(f"feedback-{size}")
                users["feedback"][size] = feedback_user
                baseline_insert["feedback"][size] = await seed_feedback(
                    feedback_user, size
                )

            for table in ("writing_draft", "writing_revision", "writing_feedback"):
                await control.execute(text(f"ANALYZE {table}"))
            await control.commit()

            app = create_app()
            tokens = {
                kind: {
                    size: criar_token(user_id, "access")[0]
                    for size, user_id in by_size.items()
                }
                for kind, by_size in users.items()
            }

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://benchmark"
            ) as client:

                async def request(
                    kind: str, size: int, cursor: str | None = None
                ) -> Response:
                    if kind == "versions":
                        path = f"/api/writing/prompts/{prompt_id}/versions"
                        params: dict[str, object] = {"limit": PAGE_SIZE}
                    elif kind == "feedback":
                        path = f"/api/writing/prompts/{prompt_id}/feedback"
                        params = {"limit": PAGE_SIZE}
                    else:
                        path = "/api/writing/history/page"
                        params = {
                            "course": "voa-level-1",
                            "unit": "31-40",
                            "limit": PAGE_SIZE,
                        }
                    if cursor:
                        params["cursor"] = cursor
                    response = await client.get(
                        path,
                        headers={"Authorization": f"Bearer {tokens[kind][size]}"},
                        params=params,
                    )
                    if response.status_code != 200:
                        raise RuntimeError(
                            f"Página {kind} recusada: HTTP {response.status_code}."
                        )
                    if int(response.headers[SQL_HEADER]) != SQL_BUDGET[kind]:
                        raise RuntimeError(f"Orçamento SQL de {kind} mudou.")
                    if int(response.headers[POOL_HEADER]) > 1:
                        raise RuntimeError(f"Página {kind} usou mais de um checkout.")
                    if int(response.headers[BYTES_HEADER]) != len(response.content):
                        raise RuntimeError(
                            "Header de payload não corresponde à resposta."
                        )
                    return response

                async def expected_keys(kind: str, size: int) -> list[int]:
                    if kind == "versions":
                        statement = (
                            "SELECT wr.id FROM writing_revision wr "
                            "JOIN writing_draft wd ON wd.id=wr.draft_id "
                            "WHERE wd.user_id=:user_id AND wd.prompt_id=:prompt_id "
                            "ORDER BY wr.created_at DESC,wr.id DESC"
                        )
                    elif kind == "feedback":
                        statement = (
                            "SELECT id FROM writing_feedback "
                            "WHERE user_id=:user_id AND prompt_id=:prompt_id "
                            "ORDER BY created_at DESC,id DESC"
                        )
                    else:
                        statement = (
                            "SELECT wd.prompt_id FROM writing_draft wd "
                            "JOIN writing_prompt wp ON wp.id=wd.prompt_id "
                            "JOIN lesson l ON l.id=wp.lesson_id "
                            "JOIN course c ON c.id=l.course_id "
                            "JOIN course_unit cu ON cu.id=l.unit_id "
                            "WHERE wd.user_id=:user_id AND c.slug='voa-level-1' "
                            "AND cu.slug='31-40' "
                            "ORDER BY wd.updated_at DESC,wd.id DESC"
                        )
                    rows = await control.execute(
                        text(statement),
                        {
                            "user_id": users[kind][size],
                            "prompt_id": prompt_id,
                        },
                    )
                    return list(rows.scalars())

                async def traverse(kind: str, size: int) -> dict[str, object]:
                    expected = await expected_keys(kind, size)
                    received: list[int] = []
                    seen_cursors: set[str] = set()
                    cursor = None
                    pages = 0
                    started = time.perf_counter()
                    while True:
                        body = (await request(kind, size, cursor)).json()
                        key = "prompt_id" if kind == "history" else "id"
                        received.extend(item[key] for item in body["items"])
                        pages += 1
                        cursor = body["next_cursor"]
                        if cursor is None:
                            break
                        if cursor in seen_cursors:
                            raise RuntimeError(f"Cursor repetido no percurso {kind}.")
                        seen_cursors.add(cursor)
                    if received != expected or len(received) != len(set(received)):
                        raise RuntimeError(
                            f"{kind} apresentou lacuna, duplicata ou ordem instável."
                        )
                    return {
                        "items": len(received),
                        "pages": pages,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    }

                async def deep_cursor(kind: str, size: int) -> str:
                    if kind == "versions":
                        statement = (
                            "SELECT wr.created_at,wr.id FROM writing_revision wr "
                            "JOIN writing_draft wd ON wd.id=wr.draft_id "
                            "WHERE wd.user_id=:user_id AND wd.prompt_id=:prompt_id "
                            "ORDER BY wr.created_at DESC,wr.id DESC "
                            "OFFSET :offset LIMIT 1"
                        )
                        timestamp_key = "created_at"
                    elif kind == "feedback":
                        statement = (
                            "SELECT created_at,id FROM writing_feedback "
                            "WHERE user_id=:user_id AND prompt_id=:prompt_id "
                            "ORDER BY created_at DESC,id DESC OFFSET :offset LIMIT 1"
                        )
                        timestamp_key = "created_at"
                    else:
                        statement = (
                            "SELECT updated_at,id FROM writing_draft "
                            "WHERE user_id=:user_id ORDER BY updated_at DESC,id DESC "
                            "OFFSET :offset LIMIT 1"
                        )
                        timestamp_key = "updated_at"
                    row = (
                        await control.execute(
                            text(statement),
                            {
                                "user_id": users[kind][size],
                                "prompt_id": prompt_id,
                                "offset": int(size * 0.90) - 1,
                            },
                        )
                    ).one()
                    return encode_time_id_cursor(getattr(row, timestamp_key), row.id)

                async def measure(
                    kind: str, size: int, cursor: str | None
                ) -> dict[str, object]:
                    for _ in range(3):
                        await request(kind, size, cursor)
                    app_ms: list[float] = []
                    wall_ms: list[float] = []
                    payloads: list[int] = []
                    checkouts: list[int] = []
                    for _ in range(samples):
                        started = time.perf_counter()
                        response = await request(kind, size, cursor)
                        wall_ms.append((time.perf_counter() - started) * 1000)
                        app_ms.append(float(response.headers[DURATION_HEADER]))
                        payloads.append(int(response.headers[BYTES_HEADER]))
                        checkouts.append(int(response.headers[POOL_HEADER]))
                    return {
                        "app_ms": distribution(app_ms),
                        "wall_ms": distribution(wall_ms),
                        "payload_bytes": {"min": min(payloads), "max": max(payloads)},
                        "sql_queries": SQL_BUDGET[kind],
                        "pool_checkouts_per_request_max": max(checkouts),
                    }

                async def explain(
                    kind: str, size: int, cursor: str
                ) -> dict[str, object]:
                    boundary = decode_time_id_cursor(cursor)
                    if kind == "versions":
                        statement = (
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                            "SELECT wr.id,wr.version,wr.created_at FROM writing_revision wr "
                            "JOIN writing_draft wd ON wd.id=wr.draft_id "
                            "WHERE wd.user_id=:user_id AND wd.prompt_id=:prompt_id "
                            "AND (wr.created_at,wr.id)<(:boundary,:row_id) "
                            "ORDER BY wr.created_at DESC,wr.id DESC LIMIT :limit"
                        )
                    elif kind == "feedback":
                        statement = (
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                            "SELECT wf.id,wf.created_at FROM writing_feedback wf "
                            "WHERE wf.user_id=:user_id AND wf.prompt_id=:prompt_id "
                            "AND (wf.created_at,wf.id)<(:boundary,:row_id) "
                            "ORDER BY wf.created_at DESC,wf.id DESC LIMIT :limit"
                        )
                    else:
                        statement = (
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                            "SELECT wd.id,wp.id,c.slug,cu.slug,l.number,wd.updated_at,"
                            "(SELECT count(wr.id) FROM writing_revision wr "
                            "WHERE wr.draft_id=wd.id),"
                            "(SELECT count(wf.id) FROM writing_feedback wf "
                            "WHERE wf.user_id=wd.user_id AND wf.prompt_id=wp.id) "
                            "FROM writing_draft wd "
                            "JOIN writing_prompt wp ON wp.id=wd.prompt_id "
                            "JOIN lesson l ON l.id=wp.lesson_id "
                            "JOIN course c ON c.id=l.course_id "
                            "JOIN course_unit cu ON cu.id=l.unit_id "
                            "WHERE wd.user_id=:user_id AND c.slug='voa-level-1' "
                            "AND cu.slug='31-40' "
                            "AND (wd.updated_at,wd.id)<(:boundary,:row_id) "
                            "ORDER BY wd.updated_at DESC,wd.id DESC LIMIT :limit"
                        )
                    document = await control.scalar(
                        text(statement),
                        {
                            "user_id": users[kind][size],
                            "prompt_id": prompt_id,
                            "boundary": boundary.timestamp,
                            "row_id": boundary.row_id,
                            "limit": PAGE_SIZE + 1,
                        },
                    )
                    return summarize_plan(document)

                cursors = {
                    kind: {size: await deep_cursor(kind, size) for size in SIZES}
                    for kind in users
                }
                for kind in users:
                    datasets[kind] = {}
                    for size in SIZES:
                        cast(dict[str, object], datasets[kind])[str(size)] = {
                            "baseline_insert_ms": baseline_insert[kind][size],
                            "stable_traversal": await traverse(kind, size),
                        }

                async def measurements() -> dict[str, object]:
                    result: dict[str, object] = {}
                    for kind in users:
                        by_size: dict[str, object] = {}
                        for size in SIZES:
                            by_size[str(size)] = {
                                "first_page": await measure(kind, size, None),
                                "deep_page_90_percent": await measure(
                                    kind, size, cursors[kind][size]
                                ),
                                "deep_plan": await explain(
                                    kind, size, cursors[kind][size]
                                ),
                            }
                        result[kind] = by_size
                    return result

                finals_present = {
                    kind: bool(
                        await control.scalar(
                            text("SELECT to_regclass(:name) IS NOT NULL"),
                            {"name": name},
                        )
                    )
                    for kind, name in FINAL_INDEXES.items()
                }
                report["current_schema"] = await measurements()
                report["final_indexes_present"] = finals_present
                report["candidate_comparison_available"] = not any(
                    finals_present.values()
                )

                if not any(finals_present.values()):
                    builds: dict[str, object] = {}
                    for kind, (name, table_name, columns) in CANDIDATES.items():
                        started = time.perf_counter()
                        await control.execute(
                            text(f"CREATE INDEX {name} ON {table_name} {columns}")
                        )
                        await control.commit()
                        candidate_indexes.append(name)
                        builds[kind] = {
                            "columns": columns.strip("()").split(","),
                            "build_ms": round(
                                (time.perf_counter() - started) * 1000, 2
                            ),
                            "size_bytes_before_write_probe": int(
                                await control.scalar(
                                    text("SELECT pg_relation_size(to_regclass(:name))"),
                                    {"name": name},
                                )
                                or 0
                            ),
                        }
                    for table in (
                        "writing_draft",
                        "writing_revision",
                        "writing_feedback",
                    ):
                        await control.execute(text(f"ANALYZE {table}"))
                    await control.commit()

                    history_write_user = await create_user("history-write-probe")
                    versions_write_user = await create_user("versions-write-probe")
                    feedback_write_user = await create_user("feedback-write-probe")
                    versions_write_draft = await create_draft(
                        versions_write_user, prompt_id
                    )
                    indexed_insert = {
                        "history": await seed_history(history_write_user, 10_000),
                        "versions": await seed_versions(versions_write_draft, 10_000),
                        "feedback": await seed_feedback(feedback_write_user, 10_000),
                    }
                    for kind, (name, _, _) in CANDIDATES.items():
                        cast(dict[str, object], builds[kind]).update(
                            {
                                "size_bytes_after_write_probe": int(
                                    await control.scalar(
                                        text(
                                            "SELECT pg_relation_size(to_regclass(:name))"
                                        ),
                                        {"name": name},
                                    )
                                    or 0
                                ),
                                "insert_10k_without_index_ms": baseline_insert[kind][
                                    10_000
                                ],
                                "insert_10k_with_index_ms": indexed_insert[kind],
                            }
                        )
                    report["candidate_indexes"] = builds
                    report["with_candidates"] = await measurements()

                async def burst(kind: str) -> dict[str, object]:
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
                        *(
                            request(kind, 10_000, cursors[kind][10_000])
                            for _ in range(concurrency)
                        )
                    )
                    elapsed = round((time.perf_counter() - started) * 1000, 2)
                    sampling = False
                    await sampler
                    return {
                        "requests": concurrency,
                        "wall_ms": elapsed,
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

                report["concurrent_bursts"] = {
                    kind: await burst(kind) for kind in users
                }
        finally:
            try:
                for name in reversed(candidate_indexes):
                    await control.execute(text(f"DROP INDEX IF EXISTS {name}"))
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
                            "Limpeza não removeu todas as contas criadas."
                        )
                if synthetic_prompts_created and lesson_id is not None:
                    result = await control.execute(
                        delete(WritingPrompt).where(
                            WritingPrompt.lesson_id == lesson_id,
                            WritingPrompt.position >= 100001,
                            WritingPrompt.position <= 110000,
                            WritingPrompt.title.like(f"{SYNTHETIC_TITLE}%"),
                        )
                    )
                    await control.commit()
                    if result.rowcount != synthetic_prompts_created:
                        raise RuntimeError(
                            "Limpeza não removeu exatamente as propostas sintéticas."
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
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Imprime somente as evidências usadas na decisão de índices.",
    )
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
    if args.summary:
        phases = {
            phase: {
                kind: cast(dict[str, Any], by_size)["10000"]
                for kind, by_size in cast(dict[str, Any], result[phase]).items()
            }
            for phase in ("current_schema", "with_candidates")
            if phase in result
        }
        result = {
            "contract": result["contract"],
            "environment": result["environment"],
            "datasets": result["datasets"],
            "final_indexes_present": result["final_indexes_present"],
            "candidate_comparison_available": result["candidate_comparison_available"],
            "measurements_10k": phases,
            "candidate_indexes": result.get("candidate_indexes"),
            "concurrent_bursts": result["concurrent_bursts"],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
