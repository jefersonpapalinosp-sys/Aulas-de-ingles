"""Ensaio sintético do caminho de claim; não usa registros de aluno."""

import json
from statistics import median

from sqlalchemy import text


async def test_partial_queue_index_removes_sort_and_reduces_index_size(session):
    await session.execute(
        text("""
        CREATE TEMP TABLE queue_benchmark ON COMMIT DROP AS
        SELECT n AS id, CASE WHEN n <= 1000 THEN 'queued'
                            WHEN n <= 1100 THEN 'processing' ELSE 'completed' END AS status,
               CASE WHEN n % 2 = 0 THEN 'dialogue' ELSE 'transcription' END AS kind,
               now() - n * interval '1 second' AS next_attempt_at,
               0 AS attempt_count, 3 AS max_attempts, now() + interval '1 day' AS expires_at,
               repeat('x', 100) AS payload
        FROM generate_series(1, 200000) n
    """)
    )
    for name, columns in (
        ("old_kind", "kind, status, next_attempt_at"),
        ("old_status", "status"),
        ("old_next", "next_attempt_at"),
    ):
        await session.execute(text(f"CREATE INDEX {name} ON queue_benchmark ({columns})"))
    await session.execute(text("ANALYZE queue_benchmark"))
    query = """EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
        SELECT * FROM queue_benchmark WHERE status='queued' AND next_attempt_at <= now()
        AND attempt_count < max_attempts AND expires_at > now()
        ORDER BY next_attempt_at, id LIMIT 1 FOR UPDATE SKIP LOCKED"""

    async def measure():
        plans = [(await session.scalar(text(query)))[0] for _ in range(5)]
        return plans[-1]["Plan"], median(p["Execution Time"] for p in plans)

    old_plan, old_ms = await measure()
    old_bytes = await session.scalar(
        text("""
        SELECT sum(pg_relation_size(c.oid)) FROM pg_class c
        WHERE c.relnamespace=pg_my_temp_schema()
          AND c.relname IN ('old_kind','old_status','old_next')
    """)
    )
    await session.execute(
        text("""
        CREATE INDEX new_queue ON queue_benchmark(status,next_attempt_at,id) WHERE status='queued'
    """)
    )
    for name in ("old_kind", "old_status", "old_next"):
        await session.execute(text(f"DROP INDEX {name}"))
    await session.execute(text("ANALYZE queue_benchmark"))
    new_plan, new_ms = await measure()
    new_bytes = await session.scalar(text("SELECT pg_relation_size('new_queue')"))
    assert 'Sort"' in json.dumps(old_plan)
    assert 'Sort"' not in json.dumps(new_plan)
    assert "new_queue" in json.dumps(new_plan)
    assert new_bytes < old_bytes
    print(f"queue benchmark: old={old_ms}ms/{old_bytes}bytes new={new_ms}ms/{new_bytes}bytes")
