"""Rollout direcionado: não semear/remover o restante do catálogo."""

from copy import deepcopy

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WritingPrompt
from app.db.writing_update import update_writing_rubrics


async def test_update_preserva_ids_e_dados_pessoais(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    registered = await client.post(
        "/api/auth/register",
        json={
            "email": "rubric-rollout@example.com",
            "password": "senha-bem-grande",
            "display_name": "Rollout",
        },
    )
    assert registered.status_code == 201
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
    prompt = (await client.get("/api/lessons/31")).json()["writing_prompts"][0]
    base = f"/api/writing/prompts/{prompt['id']}"
    payload = {"text": "The bus is cheaper than the train. We should take it."}
    assert (await client.put(base + "/draft", headers=headers, json=payload)).status_code == 200
    assert (await client.post(base + "/versions", headers=headers, json=payload)).status_code == 200
    assert (await client.post(base + "/feedback", headers=headers, json=payload)).status_code == 200
    queries = {
        table: text(f"SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id), '[]') FROM {table} t")
        for table in (
            "app_user",
            "writing_draft",
            "writing_revision",
            "writing_feedback",
            "review_item",
            "skill_evidence",
            "lesson",
            "exercise",
        )
    }
    before = {table: await session.scalar(query) for table, query in queries.items()}
    ids = list((await session.scalars(select(WritingPrompt.id).order_by(WritingPrompt.id))).all())
    for _ in range(2):
        assert await update_writing_rubrics(session) == 82
        assert {table: await session.scalar(query) for table, query in queries.items()} == before
        assert (
            list((await session.scalars(select(WritingPrompt.id).order_by(WritingPrompt.id))).all())
            == ids
        )


async def test_update_recusa_divergencia_antes_de_alterar(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db import writing_update

    seed = deepcopy(writing_update.load_seed())
    seed[0]["writing_prompts"][0]["requirements"][0]["terms"] = ["deliberate mismatch"]
    seed[-1]["writing_prompts"][0]["title"] = "Proposta diferente"
    monkeypatch.setattr(writing_update, "load_seed", lambda: seed)
    before = list(
        (await session.execute(select(WritingPrompt.id, WritingPrompt.requirements))).all()
    )
    with pytest.raises(ValueError, match="Proposta diverge"):
        await update_writing_rubrics(session)
    assert not session.dirty
    assert (
        list((await session.execute(select(WritingPrompt.id, WritingPrompt.requirements))).all())
        == before
    )
