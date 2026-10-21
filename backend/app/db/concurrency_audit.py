"""Prévia read-only antes da Sprint 38. Só emite regra e contagem, nunca conteúdo."""

import asyncio
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import dispose_engine, get_sessionmaker

STEPS = """'["preparar","assistir","estudar","praticar","revisar"]'::jsonb"""
NAMES = "('preparar','assistir','estudar','praticar','revisar')"
RULES = {
    "study_step": f"SELECT count(*) FROM study_session_progress WHERE current_step NOT IN {NAMES}",
    "step_name": f"SELECT count(*) FROM step_progress WHERE step NOT IN {NAMES}",
    "study_seconds": "SELECT count(*) FROM study_session_progress WHERE total_seconds < 0",
    "study_completed_steps": (
        "SELECT count(*) FROM study_session_progress WHERE jsonb_typeof(completed_steps) "
        f"!= 'array' OR NOT (completed_steps <@ {STEPS})"
    ),
    "review_counters": (
        "SELECT count(*) FROM review_item WHERE interval_days < 0 OR repetitions < 0 "
        "OR lapses < 0 OR ease_factor < 1.3"
    ),
    "notebook_kind": (
        "SELECT count(*) FROM notebook_entry WHERE kind NOT IN "
        "('note','favorite_phrase','personal_example','recurring_error','teacher_question')"
    ),
    "speaking_status": (
        "SELECT count(*) FROM speaking_attempt WHERE status NOT IN ('pending','ready')"
    ),
    "speaking_ready_metadata": (
        "SELECT count(*) FROM speaking_attempt WHERE status='ready' AND "
        "(storage_key IS NULL OR file_size IS NULL OR mime_type IS NULL)"
    ),
    "transcription_owner": (
        "SELECT count(*) FROM transcription_job j JOIN speaking_attempt a "
        "ON a.id=j.speaking_attempt_id WHERE j.user_id != a.user_id"
    ),
    "practice_owner": (
        "SELECT count(*) FROM exercise_attempt a JOIN practice_session_item i "
        "ON i.id=a.practice_session_item_id JOIN practice_session p ON p.id=i.practice_session_id "
        "WHERE a.user_id != p.user_id OR a.exercise_id != i.exercise_id"
    ),
    "review_unknown_source": (
        "SELECT count(*) FROM review_item WHERE source_type NOT IN "
        "('vocab_item','exercise','writing_prompt','transcript_cue','notebook_entry',"
        "'dialogue_turn')"
    ),
    "study_completion_timestamp": (
        "SELECT count(*) FROM study_session_progress WHERE "
        f"(completed_steps @> {STEPS}) != (completed_at IS NOT NULL)"
    ),
    "study_step_consistency": """SELECT count(*) FROM study_session_progress s WHERE EXISTS (
        SELECT 1 FROM jsonb_array_elements_text(CASE WHEN jsonb_typeof(s.completed_steps)='array'
        THEN s.completed_steps ELSE '[]'::jsonb END) step
        WHERE NOT EXISTS (SELECT 1 FROM step_progress p WHERE p.study_session_id=s.id
        AND p.step=step AND p.completed_at IS NOT NULL))
        OR EXISTS (SELECT 1 FROM step_progress p WHERE p.study_session_id=s.id
        AND p.completed_at IS NOT NULL AND NOT (s.completed_steps ? p.step))""",
}

# IDs editoriais não têm proprietário; a anotação é pessoal. Chaves
# polimórficas não admitem FK genérica: reconciliar por tipo sem apagar dados.
for source, table in (
    ("vocab_item", "vocab_item"),
    ("exercise", "exercise"),
    ("writing_prompt", "writing_prompt"),
    ("transcript_cue", "transcript_cue"),
    ("notebook_entry", "notebook_entry"),
    ("dialogue_turn", "dialogue_turn"),
):
    RULES[f"review_source_{source}"] = (
        f"SELECT count(*) FROM review_item r LEFT JOIN {table} s ON s.id=r.source_id "
        f"WHERE r.source_type='{source}' AND (s.id IS NULL"
        + (" OR s.user_id != r.user_id" if source in ("notebook_entry", "dialogue_turn") else "")
        + ")"
    )

RULES["skill_unknown_source"] = (
    "SELECT count(*) FROM skill_evidence WHERE source_type NOT IN "
    "('exercise_attempt','writing_feedback','speaking_attempt','dialogue_turn')"
)
for source in ("exercise_attempt", "writing_feedback", "speaking_attempt", "dialogue_turn"):
    RULES[f"skill_source_{source}"] = (
        f"SELECT count(*) FROM skill_evidence e LEFT JOIN {source} s ON s.id=e.source_id "
        f"WHERE e.source_type='{source}' AND (s.id IS NULL OR s.user_id != e.user_id)"
    )


async def audit(session: AsyncSession) -> dict[str, int]:
    return {
        name: int((await session.execute(text(sql))).scalar_one()) for name, sql in RULES.items()
    }


async def main() -> int:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            report = await audit(session)
            print(json.dumps(report, sort_keys=True))
            return 2 if any(report.values()) else 0
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
