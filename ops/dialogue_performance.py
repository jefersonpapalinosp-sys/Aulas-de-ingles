"""DB-47: histórico e Caderno com 1k/10k turnos, somente no banco descartável.

Não execute junto do pytest: a suíte remove contas de teste. O relatório contém
somente medidas agregadas; as contas sintéticas são removidas no finally.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from ops.notebook_performance import distribution, summarize_plan

PAGE_SIZE = 50
LOCK_KEY = "aulas-ingles:dialogue-performance:v1"


class RouteMetrics(TypedDict):
    http_ms: dict[str, float]
    server_ms: dict[str, float]
    sql_queries_max: int
    response_bytes_max: int


class Traversal(TypedDict):
    rows: int
    pages: int
    exact_order: bool


class Dataset(TypedDict):
    turns: int
    dialogues: int
    notebook_entries: int
    routes: dict[str, RouteMetrics]
    plans: dict[str, dict[str, object]]
    traversal: dict[str, Traversal]
    p95_pass: bool


def page_ids(value: object) -> tuple[list[int], str | None]:
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise ValueError("Página deve conter uma lista de itens.")
    ids: list[int] = []
    for item in value["items"]:
        if not isinstance(item, dict):
            raise ValueError("Item de paginação inválido.")
        identity = item.get("id")
        if not isinstance(identity, int) or isinstance(identity, bool) or identity <= 0:
            raise ValueError("Identidade de paginação inválida.")
        ids.append(identity)
    if "next_cursor" not in value:
        raise ValueError("Cursor de paginação ausente.")
    cursor = value["next_cursor"]
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise ValueError("Cursor de paginação inválido.")
    return ids, cursor


async def run(samples: int) -> dict[str, object]:
    from app.core.config import get_settings
    from app.core.security import criar_token
    from app.db.models import Lesson, User
    from app.db.session import dispose_engine, get_engine
    from app.main import create_app
    from app.pagination import TimeIdCursor, encode_time_id_cursor
    from app.performance import BYTES_HEADER, DURATION_HEADER, POOL_HEADER, SQL_HEADER
    from app.services.dialogue_history import history_query
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import delete, select, text

    settings = get_settings()
    settings.performance_probe_enabled = True
    settings.log_level = "warning"
    engine = get_engine()
    created: dict[int, str] = {}
    locked = False
    datasets: dict[str, Dataset] = {}
    report: dict[str, object] = {
        "contract": "dialogue-performance-v1",
        "samples_per_route": samples,
        "page_size": PAGE_SIZE,
        "target_p95_ms": 100,
        "datasets": datasets,
    }
    try:
        async with engine.connect() as control:
            try:
                locked = bool(
                    await control.scalar(
                        text("SELECT pg_try_advisory_lock(hashtext(:key))"),
                        {"key": LOCK_KEY},
                    )
                )
                if not locked:
                    raise RuntimeError("Outro benchmark de diálogo está em execução.")
                report["postgres"] = await control.scalar(text("SHOW server_version"))
                lesson_id = await control.scalar(
                    select(Lesson.id).where(Lesson.number == 31)
                )
                if lesson_id is None:
                    raise RuntimeError("Execute make test-api-prepare antes do ensaio.")
                async with AsyncClient(
                    transport=ASGITransport(app=create_app()),
                    base_url="http://benchmark",
                ) as client:
                    for size in (1_000, 10_000):
                        email = f"benchmark47-{uuid4().hex}@example.invalid"
                        uid = int(
                            (
                                await control.execute(
                                    text(
                                        "INSERT INTO app_user(email,password_hash,display_name) "
                                        "VALUES (:email,'!disabled-benchmark!','Benchmark 47') "
                                        "RETURNING id"
                                    ),
                                    {"email": email},
                                )
                            ).scalar_one()
                        )
                        created[uid] = email
                        await control.commit()
                        parameters = {
                            "uid": uid,
                            "lesson": lesson_id,
                            "size": size,
                            "dialogues": (size + 11) // 12,
                        }
                        await control.execute(
                            text(
                                """
                            INSERT INTO speaking_dialogue(user_id,lesson_id,operation_key,
                              mode,state,content_version,content_fingerprint,rubric_version,turn_limit,started_at)
                            SELECT :uid,:lesson,
                              md5(CAST(CAST(:uid AS integer) AS text) || ':' || g::text)::uuid,
                              'guided','completed',1,repeat('a',64),'synthetic-db47',12,
                              TIMESTAMPTZ '2026-01-01 00:00:00+00' + ((g-1)/5)*INTERVAL '1 second'
                            FROM generate_series(1,:dialogues) g
                        """
                            ),
                            parameters,
                        )
                        await control.execute(
                            text("""
                            INSERT INTO dialogue_turn(dialogue_id,user_id,position,role,input_kind,
                              state,transcript,partner_text,created_at,completed_at,expires_at)
                            SELECT d.id,:uid,p,'student','text','completed',
                              'Synthetic student turn',
                              'Synthetic partner turn',now(),now(),now()+INTERVAL '30 days'
                            FROM (SELECT id,row_number() OVER (ORDER BY id) AS n
                                  FROM speaking_dialogue WHERE user_id=:uid) d
                            CROSS JOIN generate_series(1,12) p WHERE (d.n-1)*12+p <= :size
                        """),
                            parameters,
                        )
                        await control.execute(
                            text("""
                            INSERT INTO notebook_entry
                              (user_id,lesson_id,kind,content,created_at,updated_at)
                            SELECT :uid,:lesson,'note','Synthetic DB47 note',
                              TIMESTAMPTZ '2026-01-01 00:00:00+00' + ((g-1)/5)*INTERVAL '1 second',
                              TIMESTAMPTZ '2026-01-01 00:00:00+00' + ((g-1)/5)*INTERVAL '1 second'
                            FROM generate_series(1,:size) g
                        """),
                            parameters,
                        )
                        for table in (
                            "speaking_dialogue",
                            "dialogue_turn",
                            "notebook_entry",
                        ):
                            await control.execute(text(f"ANALYZE {table}"))
                        await control.commit()
                        headers = {
                            "Authorization": f"Bearer {criar_token(uid, 'access')[0]}"
                        }
                        measured: dict[str, RouteMetrics] = {}
                        plans: dict[str, dict[str, object]] = {}
                        traversals: dict[str, Traversal] = {}
                        dataset: Dataset = {
                            "turns": size,
                            "dialogues": parameters["dialogues"],
                            "notebook_entries": size,
                            "routes": measured,
                            "plans": plans,
                            "traversal": traversals,
                            "p95_pass": False,
                        }
                        datasets[str(size)] = dataset
                        for name, table, column, route in (
                            (
                                "history",
                                "speaking_dialogue",
                                "started_at",
                                "/api/speaking/dialogues",
                            ),
                            (
                                "notebook",
                                "notebook_entry",
                                "updated_at",
                                "/api/me/notebook/page",
                            ),
                        ):
                            rows = (
                                await control.execute(
                                    text(
                                        f"SELECT id,{column} FROM {table} WHERE user_id=:uid "
                                    f"ORDER BY {column} DESC,id DESC"
                                    ),
                                    {"uid": uid},
                                )
                            ).all()
                            boundary = rows[int(len(rows) * 0.9)]
                            deep = encode_time_id_cursor(boundary[1], boundary[0])
                            for label, cursor in (("first", None), ("deep", deep)):
                                params: dict[str, str | int] = {
                                    "limit": PAGE_SIZE,
                                    **({"cursor": cursor} if cursor else {}),
                                }
                                elapsed, server, counts, payloads = [], [], [], []
                                for i in range(samples + 2):
                                    started = time.perf_counter()
                                    response = await client.get(
                                        route, headers=headers, params=params
                                    )
                                    duration = (time.perf_counter() - started) * 1000
                                    if response.status_code != 200:
                                        raise RuntimeError(
                                            f"{name}: HTTP {response.status_code}"
                                        )
                                    if (
                                        int(response.headers[POOL_HEADER]) > 1
                                        or int(response.headers[SQL_HEADER]) != 2
                                    ):
                                        raise RuntimeError(
                                            "Orçamento de consultas/conexões excedido."
                                        )
                                    if int(response.headers[BYTES_HEADER]) != len(
                                        response.content
                                    ):
                                        raise RuntimeError(
                                            "Payload medido não corresponde à resposta."
                                        )
                                    if i >= 2:
                                        elapsed.append(duration)
                                        server.append(
                                            float(response.headers[DURATION_HEADER])
                                        )
                                        counts.append(int(response.headers[SQL_HEADER]))
                                        payloads.append(len(response.content))
                                measured[f"{name}_{label}"] = {
                                    "http_ms": distribution(elapsed),
                                    "server_ms": distribution(server),
                                    "sql_queries_max": max(counts),
                                    "response_bytes_max": max(payloads),
                                }
                            received: list[int] = []
                            cursor, pages = None, 0
                            while True:
                                response = await client.get(
                                    route,
                                    headers=headers,
                                    params={
                                        "limit": PAGE_SIZE,
                                        **({"cursor": cursor} if cursor else {}),
                                    },
                                )
                                response.raise_for_status()
                                ids, cursor = page_ids(response.json())
                                received.extend(ids)
                                pages += 1
                                if cursor is None:
                                    break
                                if pages > len(rows):
                                    raise RuntimeError("Cursor não progride.")
                            if received != [row[0] for row in rows]:
                                raise RuntimeError(
                                    "Paginação perdeu, duplicou ou misturou registros."
                                )
                            traversals[name] = {
                                "rows": len(received),
                                "pages": pages,
                                "exact_order": True,
                            }
                            if name == "history":
                                query = history_query(
                                    uid,
                                    PAGE_SIZE,
                                    TimeIdCursor(boundary[1], boundary[0]),
                                )
                                compiled = str(
                                    query.compile(
                                        dialect=control.dialect,
                                        compile_kwargs={"literal_binds": True},
                                    )
                                )
                                plan = await control.scalar(
                                    text(
                                        "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) "
                                        + compiled
                                    )
                                )
                            else:
                                plan = await control.scalar(
                                    text("""
                                    EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON)
                                    SELECT n.id,c.slug,c.title,u.slug,l.number,l.title,
                                      n.kind,n.content,n.created_at,n.updated_at
                                    FROM notebook_entry n JOIN lesson l ON n.lesson_id=l.id
                                    JOIN course c ON l.course_id=c.id
                                    JOIN course_unit u ON l.unit_id=u.id
                                    WHERE n.user_id=:uid AND (n.updated_at,n.id)<(:ts,:id)
                                    ORDER BY n.updated_at DESC,n.id DESC LIMIT 51
                                """),
                                    {"uid": uid, "ts": boundary[1], "id": boundary[0]},
                                )
                            plans[name + "_deep"] = summarize_plan(plan)
                        dataset["p95_pass"] = all(
                            m["http_ms"]["p95"] <= 100 for m in measured.values()
                        )
                        actual_turns = await control.scalar(
                            text(
                                "SELECT count(*) FROM dialogue_turn WHERE user_id=:uid"
                            ),
                            {"uid": uid},
                        )
                        if actual_turns != size:
                            raise RuntimeError("Carga de turnos incompleta.")
            finally:
                await control.rollback()
                if created:
                    deleted = await control.execute(
                        delete(User).where(
                            User.id.in_(created), User.email.in_(created.values())
                        )
                    )
                    await control.commit()
                    if deleted.rowcount != len(created):
                        raise RuntimeError("Limpeza das contas sintéticas incompleta.")
                    report["synthetic_accounts_removed"] = deleted.rowcount
                if locked:
                    await control.execute(
                        text("SELECT pg_advisory_unlock(hashtext(:key))"),
                        {"key": LOCK_KEY},
                    )
                    await control.commit()
    finally:
        await dispose_engine()
    report["p95_pass"] = all(d["p95_pass"] for d in datasets.values())
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 10 <= args.samples <= 200:
        parser.error("samples deve ficar entre 10 e 200")
    from app.db.test_safety import UnsafeTestDatabase, configure_test_environment

    try:
        configure_test_environment(os.environ)
        report = asyncio.run(run(args.samples))
    except UnsafeTestDatabase as error:
        print(f"Benchmark bloqueado: {error}", file=sys.stderr)
        raise SystemExit(2) from None
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    if not report["p95_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
