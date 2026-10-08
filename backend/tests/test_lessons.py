"""Leitura do conteúdo — contra o Postgres do compose, já semeado."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_lista_as_dez_aulas_em_ordem(client: AsyncClient) -> None:
    r = await client.get("/api/lessons")
    assert r.status_code == 200
    aulas = r.json()
    assert [a["number"] for a in aulas] == list(range(31, 41))
    assert aulas[0]["title"] == "Take Me Out to the Ball Game"
    # O resumo não carrega a aula inteira.
    assert "grammar_blocks" not in aulas[0]


@pytest.mark.asyncio
async def test_aula_31_tem_o_conteudo_esperado(client: AsyncClient) -> None:
    r = await client.get("/api/lessons/31")
    assert r.status_code == 200
    a = r.json()
    assert len(a["grammar_blocks"]) == 3
    assert len(a["phrases"]) == 6
    assert len(a["vocab"]) == 11
    assert len(a["exercises"]) == 9
    assert len(a["goals"]) == 4
    assert all(isinstance(g, str) for g in a["goals"])
    assert len(a["media"]) == 1
    assert len(a["writing_prompts"]) == 1
    assert {source["kind"] for source in a["content_sources"]} == {
        "official",
        "authorial",
    }
    official = next(source for source in a["content_sources"] if source["kind"] == "official")
    assert official["publisher"] == "VOA Learning English"
    assert official["url"] == a["voa_url"]
    assert a["versions"][0]["version"] == 1
    assert a["versions"][0]["status"] == "reviewed"
    assert a["versions"][0]["learning_strategy"] == "visualizar"
    assert a["writing_prompts"][0] == {
        **a["writing_prompts"][0],
        "position": 0,
        "title": "Compare caminhos para o estádio",
        "min_words": 35,
        "min_sentences": 4,
    }
    assert [item["terms"] for item in a["writing_prompts"][0]["requirements"]] == [
        ["than"],
        ["should", "ought"],
    ]
    assert a["media"][0]["kind"] == "conversation_audio"
    assert a["media"][0]["duration_seconds"] == 209
    assert a["media"][0]["source_url"].endswith("81890cf1-5a16-4426-87db-fdb240c750cc_hq.mp3")
    assert a["media"][0]["listening_exercise_position"] == 6
    cues = a["media"][0]["cues"]
    assert len(cues) == 11
    assert [cue["position"] for cue in cues] == list(range(11))
    assert all(cue["start_seconds"] < cue["end_seconds"] for cue in cues)
    listening_choice = next(exercise for exercise in a["exercises"] if exercise["position"] == 6)
    assert a["exercises"][0]["activity_type"] == "gap_fill"
    assert a["exercises"][0]["hint_count"] == 2
    assert listening_choice["activity_type"] == "multiple_choice"
    assert listening_choice["skill"] == "listening"
    assert listening_choice["options"] == ["bus", "taxi", "Metro"]
    assert {exercise["activity_type"] for exercise in a["exercises"]} == {
        "gap_fill",
        "multiple_choice",
        "transformation",
        "dictation",
        "reorder",
    }


@pytest.mark.asyncio
async def test_aula_32_esta_alinhada_ao_plano_oficial(client: AsyncClient) -> None:
    a = (await client.get("/api/lessons/32")).json()

    assert a["grammar_tag"] == "Objetos diretos e indiretos + interjeições"
    assert a["focus_points"] == ["direct object", "indirect object", "interjections"]
    assert a["grammar_blocks"][0]["heading"].startswith("Objeto direto")
    assert a["grammar_blocks"][1]["heading"].startswith("Objeto indireto")
    assert any("woo-hoo" in note["label"] for note in a["pronunciation"])
    assert len(a["exercises"]) == 7
    assert len(a["media"]) == 1
    assert a["media"][0]["duration_seconds"] == 228
    assert len(a["media"][0]["cues"]) == 4
    listening = next(exercise for exercise in a["exercises"] if exercise["skill"] == "listening")
    assert listening["options"] == ["her partner", "her teacher", "her neighbor"]
    assert a["versions"][0]["learning_strategy"] == "monitorar"


@pytest.mark.asyncio
async def test_todas_as_aulas_tem_audio_trechos_e_listening(client: AsyncClient) -> None:
    for number in range(31, 41):
        lesson = (await client.get(f"/api/lessons/{number}")).json()
        assert len(lesson["media"]) == 1
        media = lesson["media"][0]
        assert media["kind"] == "conversation_audio"
        assert media["source_url"].startswith("https://voa-audio.voanews.eu/")
        assert len(media["cues"]) >= 4
        assert all(cue["start_seconds"] < cue["end_seconds"] for cue in media["cues"])
        listening = [
            exercise
            for exercise in lesson["exercises"]
            if exercise["skill"] == "listening"
        ]
        assert listening
        assert media["listening_exercise_position"] in {
            exercise["position"] for exercise in listening
        }


@pytest.mark.asyncio
async def test_aula_inexistente_devolve_404(client: AsyncClient) -> None:
    r = await client.get("/api/lessons/99")
    assert r.status_code == 404
    assert "99" in r.json()["detail"]


@pytest.mark.asyncio
async def test_resposta_certa_nao_vaza_no_contrato(client: AsyncClient) -> None:
    """Na S3 a correção vai para o servidor; o contrato já nasce sem a resposta."""
    r = await client.get("/api/lessons/34")
    assert "answers" not in r.text
    for exercicio in r.json()["exercises"]:
        assert set(exercicio) == {
            "id",
            "position",
            "activity_type",
            "skill",
            "options",
            "prompt",
            "hint",
            "hint_count",
            "explanation",
        }


@pytest.mark.asyncio
async def test_ordem_interna_respeita_position(client: AsyncClient) -> None:
    a = (await client.get("/api/lessons/33")).json()
    assert [e["position"] for e in a["exercises"]] == sorted(e["position"] for e in a["exercises"])
    primeiro = a["grammar_blocks"][0]
    assert primeiro["heading"].startswith("Verbo + -er")


@pytest.mark.asyncio
async def test_bloco_gramatical_traz_cabecalho_e_linhas(client: AsyncClient) -> None:
    bloco = (await client.get("/api/lessons/31")).json()["grammar_blocks"][0]
    assert bloco["table_head"] == ["Adjetivo", "Comparativo", "Frase da aula"]
    assert len(bloco["rows"][0]["cells"]) == len(bloco["table_head"])
    assert bloco["warning"] is not None


@pytest.mark.asyncio
async def test_texto_vem_em_markdown_sem_html(client: AsyncClient) -> None:
    """Contrato de formato: Markdown no banco, nunca HTML cru."""
    corpo = (await client.get("/api/lessons/31")).text
    for tag in ("<b>", "<i>", "<code>", "<span", "&mdash;", "&rarr;"):
        assert tag not in corpo, f"vazou {tag} no payload"
    bloco = (await client.get("/api/lessons/31")).json()["grammar_blocks"][0]
    assert "**" in bloco["rows"][0]["cells"][1]


@pytest.mark.asyncio
async def test_vocabulario_filtra_por_aula(client: AsyncClient) -> None:
    todos = (await client.get("/api/vocab")).json()
    assert len(todos) == 115
    da_40 = (await client.get("/api/vocab?lesson=40")).json()
    assert len(da_40) == 13
    assert {v["lesson_number"] for v in da_40} == {40}
    assert da_40[0]["term"] == "the woods"
    assert da_40[0]["ipa"].startswith("/")


@pytest.mark.asyncio
async def test_vocabulario_de_aula_inexistente_vem_vazio(client: AsyncClient) -> None:
    assert (await client.get("/api/vocab?lesson=99")).json() == []


@pytest.mark.asyncio
async def test_exercicios_do_bloco_inteiro(client: AsyncClient) -> None:
    todos = (await client.get("/api/exercises")).json()
    assert len(todos) == 74
    assert {e["lesson_number"] for e in todos} == set(range(31, 41))
    # Ordenado por aula e depois por posição.
    chaves = [(e["lesson_number"], e["position"]) for e in todos]
    assert chaves == sorted(chaves)
    # A resposta certa continua fora do contrato.
    assert all("answers" not in exercicio for exercicio in todos)


@pytest.mark.asyncio
async def test_exercicios_filtra_por_aula(client: AsyncClient) -> None:
    da_39 = (await client.get("/api/exercises?lesson=39")).json()
    assert len(da_39) == 8
    assert {e["lesson_number"] for e in da_39} == {39}
