"""Laboratorio reproduzivel da paginacao da Revisao no PostgreSQL descartavel.

O processo recusa qualquer alvo diferente de aulas_ingles_test/aulas_test, mantem
um advisory lock durante todo o ensaio e remove somente as contas sinteticas que
acabou de criar. O indice candidato tambem e temporario. Nenhum texto SQL, token ou
conteudo de resposta entra no relatorio agregado.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from collections.abc import Iterable
from typing import Any, cast
from uuid import uuid4

LOCK_KEY = "aulas-ingles:review-performance:v1"
CANDIDATE_INDEX = "ix_review_item_user_status_created_id_bench"
FINAL_INDEX = "ix_review_item_user_status_created_id"
SIZES = (1_000, 10_000)
PAGE_SIZE = 50


def percentile(values: Iterable[float], quantile: float) -> float:
    """Percentil nearest-rank, explicito para manter relatorios comparaveis."""
    ordered = sorted(values)
    if not ordered or not 0 < quantile <= 1:
        raise ValueError("Percentile requires values and 0 < quantile <= 1.")
    return ordered[max(0, math.ceil(len(ordered) * quantile) - 1)]


def distribution(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 2),
        "p50": round(percentile(values, 0.50), 2),
        "p95": round(percentile(values, 0.95), 2),
        "max": round(max(values), 2),
    }


def summarize_plan(plan_document: object) -> dict[str, object]:
    if not isinstance(plan_document, list) or not plan_document:
        raise ValueError("Unexpected EXPLAIN document.")
    document = plan_document[0]
    if not isinstance(document, dict) or not isinstance(document.get("Plan"), dict):
        raise TypeError("Unexpected EXPLAIN plan root.")
    root = document["Plan"]
    node_types: list[str] = []
    indexes: list[str] = []
    shared_hit = 0
    shared_read = 0

    def visit(node: dict[str, object]) -> None:
        nonlocal shared_hit, shared_read
        node_type = node.get("Node Type")
        if isinstance(node_type, str):
            node_types.append(node_type)
        index_name = node.get("Index Name")
        if isinstance(index_name, str):
            indexes.append(index_name)
        hit = node.get("Shared Hit Blocks", 0)
        read = node.get("Shared Read Blocks", 0)
        if isinstance(hit, int):
            shared_hit += hit
        if isinstance(read, int):
            shared_read += read
        children = node.get("Plans", [])
        if isinstance(children, list):
            for child in children:
                if isinstance(child, dict):
                    visit(child)

    visit(root)
    return {
        "planning_ms": round(float(document.get("Planning Time", 0)), 3),
        "execution_ms": round(float(document.get("Execution Time", 0)), 3),
        "root_node": root.get("Node Type"),
        "actual_rows": root.get("Actual Rows"),
        "shared_hit_blocks_sum": shared_hit,
        "shared_read_blocks_sum": shared_read,
        "node_types": node_types,
        "indexes": sorted(set(indexes)),
    }


async def run(samples: int, concurrency: int) -> dict[str, object]:
    # Imports tardios: a guarda configura e valida o alvo antes de criar engine/app.
    from app.core.config import get_settings
    from app.core.security import criar_token
    from app.db.models import Lesson, User
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
        "contract": "review-performance-v1",
        "samples_per_route": samples,
        "page_size": PAGE_SIZE,
        "datasets": datasets,
    }

    async with engine.connect() as control:
        try:
            identity = (
                await control.execute(
                    text(
                        "SELECT current_database(), current_user, "
                        "shobj_description(oid, 'pg_database') "
                        "FROM pg_database WHERE datname = current_database()"
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
                raise RuntimeError("Outro benchmark da Revisao ja esta em execucao.")

            lesson_id = await control.scalar(
                select(Lesson.id).where(Lesson.number == 31).limit(1)
            )
            if lesson_id is None:
                raise RuntimeError(
                    "Seed da Aula 31 ausente; execute make test-api-prepare."
                )

            async def create_user(label: str) -> int:
                email = f"benchmark41-review-{label}-{uuid4().hex}@example.invalid"
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

            async def seed_items(user_id: int, size: int) -> float:
                started = time.perf_counter()
                await control.execute(
                    text(
                        "INSERT INTO review_item("
                        "user_id,lesson_id,item_type,source_type,source_id,source_key,"
                        "skill,prompt,answer,origin_reason,estimated_seconds,status,"
                        "suspended_at,revision,ease_factor,interval_days,repetitions,"
                        "lapses,due_at,created_at) "
                        "SELECT :user_id,:lesson_id,'grammar_error','benchmark',g,"
                        "'benchmark-review:' || g,'grammar',"
                        "'synthetic review prompt ' || g,'synthetic answer',"
                        "'Synthetic performance item.',60,'suspended',"
                        "TIMESTAMPTZ '2026-01-02 00:00:00+00',0,2.5,0,0,0,"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00',"
                        "TIMESTAMPTZ '2026-01-01 00:00:00+00' "
                        "+ ((g - 1) / 5) * INTERVAL '1 second' "
                        "FROM generate_series(1,:size) AS g"
                    ),
                    {"user_id": user_id, "lesson_id": lesson_id, "size": size},
                )
                await control.commit()
                return round((time.perf_counter() - started) * 1000, 2)

            users: dict[int, int] = {}
            baseline_insert: dict[int, float] = {}
            for size in SIZES:
                user_id = await create_user(str(size))
                users[size] = user_id
                baseline_insert[size] = await seed_items(user_id, size)
            await control.execute(text("ANALYZE review_item"))
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
                        "/api/review/items/page",
                        headers={"Authorization": f"Bearer {tokens[size]}"},
                        params={
                            "status": "suspended",
                            "course": "voa-level-1",
                            "unit": "31-40",
                            "limit": PAGE_SIZE,
                            **({"cursor": cursor} if cursor else {}),
                        },
                    )
                    if response.status_code != 200:
                        raise RuntimeError(
                            f"Pagina recusada: HTTP {response.status_code}."
                        )
                    if int(response.headers[SQL_HEADER]) != 2:
                        raise RuntimeError(
                            "Orcamento SQL da pagina mudou durante o benchmark."
                        )
                    if int(response.headers[POOL_HEADER]) > 1:
                        raise RuntimeError(
                            "Uma pagina adquiriu mais de uma conexao do pool."
                        )
                    if int(response.headers[BYTES_HEADER]) != len(response.content):
                        raise RuntimeError(
                            "Header de payload nao corresponde a resposta."
                        )
                    return response

                async def expected_ids(user_id: int) -> list[int]:
                    rows = await control.execute(
                        text(
                            "SELECT id FROM review_item "
                            "WHERE user_id=:user_id AND status='suspended' "
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
                        response = await request(size, cursor)
                        body = response.json()
                        received.extend(item["id"] for item in body["items"])
                        pages += 1
                        cursor = body["next_cursor"]
                        if cursor is None:
                            break
                        if cursor in seen_cursors:
                            raise RuntimeError(
                                "Cursor repetido durante percurso completo."
                            )
                        seen_cursors.add(cursor)
                    if received != expected or len(received) != len(set(received)):
                        raise RuntimeError(
                            "Percurso apresentou lacuna, duplicata ou ordem instavel."
                        )
                    return {
                        "items": len(received),
                        "pages": pages,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    }

                async def deep_cursor(size: int) -> str:
                    offset = int(size * 0.90) - 1
                    row = (
                        await control.execute(
                            text(
                                "SELECT created_at,id FROM review_item "
                                "WHERE user_id=:user_id AND status='suspended' "
                                "ORDER BY created_at DESC,id DESC "
                                "OFFSET :offset LIMIT 1"
                            ),
                            {"user_id": users[size], "offset": offset},
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
                        "sql_queries": 2,
                        "pool_checkouts_per_request_max": max(checkouts),
                    }

                async def explain(size: int, cursor: str) -> dict[str, object]:
                    boundary = decode_time_id_cursor(cursor)
                    document = await control.scalar(
                        text(
                            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                            "SELECT ri.id,c.slug,cu.slug,l.number,ri.created_at "
                            "FROM review_item ri "
                            "JOIN lesson l ON l.id=ri.lesson_id "
                            "JOIN course c ON c.id=l.course_id "
                            "JOIN course_unit cu ON cu.id=l.unit_id "
                            "WHERE ri.user_id=:user_id AND ri.status='suspended' "
                            "AND c.slug='voa-level-1' AND cu.slug='31-40' "
                            "AND (ri.created_at,ri.id) < (:created_at,:row_id) "
                            "ORDER BY ri.created_at DESC,ri.id DESC LIMIT :limit"
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
                            f"CREATE INDEX {CANDIDATE_INDEX} ON review_item "
                            "(user_id,status,created_at,id)"
                        )
                    )
                    await control.commit()
                    candidate_created = True
                    index_build_ms = round((time.perf_counter() - started) * 1000, 2)
                    await control.execute(text("ANALYZE review_item"))
                    await control.commit()
                    index_size_before_write = int(
                        await control.scalar(
                            text("SELECT pg_relation_size(to_regclass(:name))"),
                            {"name": CANDIDATE_INDEX},
                        )
                        or 0
                    )
                    write_probe_user = await create_user("write-probe")
                    indexed_insert_ms = await seed_items(write_probe_user, 10_000)
                    index_size_after_write = int(
                        await control.scalar(
                            text("SELECT pg_relation_size(to_regclass(:name))"),
                            {"name": CANDIDATE_INDEX},
                        )
                        or 0
                    )
                    report["candidate_index"] = {
                        "columns": ["user_id", "status", "created_at", "id"],
                        "build_ms": index_build_ms,
                        "size_bytes_after_11k_rows": index_size_before_write,
                        "size_bytes_after_21k_rows": index_size_after_write,
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
                burst_started = time.perf_counter()
                responses = await asyncio.gather(
                    *(request(10_000, cursors[10_000]) for _ in range(concurrency))
                )
                burst_ms = round((time.perf_counter() - burst_started) * 1000, 2)
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
                            "Limpeza sintetica nao removeu exatamente as contas criadas."
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
