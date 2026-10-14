"""Regressão lexical: evidências de alcance não são modelos de boa redação."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.db.seed import load_seed, validate_writing_prompts
from app.domain.writing import analyze_writing, requirement_passes, rubric_snapshot
from app.domain.writing_rubric import WritingRequirement


def rule(terms: list[str], **kwargs) -> WritingRequirement:
    return WritingRequirement(label="Marcadores", terms=terms, **kwargs)


@pytest.mark.parametrize(
    ("term", "text", "expected"),
    [
        ("are you", "Are you Anna?", True),
        ("are you", "ARE   YOU Anna?", True),
        ("are you", "Are\nyou Anna?", True),
        ("are you", "Are. You are Anna.", False),
        ("are you", "Are, you Anna?", False),
        ("he ", "The teacher is here.", False),
        ("he", "He's ready.", False),
        ("he", "He is ready.", True),
        ("can", "I can't swim.", False),
        ("in", "Inside the inn.", False),
        ("in", "My in-laws are here.", False),
        ("i'll", "I’ll help you.", True),
        (" 'll be ", "I'll be working.", True),
        ("'ll be", "I will be working.", False),
        ("'d better", "You’d better rest.", True),
        ("woo-hoo", "Woo‑hoo!", True),
        ("woo-hoo", "Woo hoo!", False),
        ("ought to", "You ought to rest.", True),
        ("ought to", "You ought, perhaps, to rest.", False),
        ("ought to", "You ought.", False),
        ("too ", "It is too hot.", True),
        ("too", "I took a tool.", False),
        ("yes, it is", "Yes, it is warm.", True),
        ("do you?", "You like it, do you?", True),
        ("a+b", "A+b is a literal marker.", True),
        ("a+b", "Aaab is not a literal marker.", False),
    ],
)
def test_palavra_expressao_limites_e_apostrofos(term: str, text: str, expected: bool) -> None:
    assert requirement_passes(text, rule([term])) is expected


def test_all_exige_todos_e_quantidade_por_termo() -> None:
    required = rule(["he", "she", "they"], match_mode="all")
    assert not requirement_passes("He is ready. He is ready. He is ready.", required)
    assert requirement_passes("He is here. She is here. They are here.", required)
    required = rule(["how much", "how many"], match_mode="all", min_count=2)
    assert not requirement_passes("How much? How much? How many?", required)
    assert requirement_passes("How much? How many? How much? How many?", required)


def test_quantidade_e_diversidade_nao_sao_a_mesma_coisa() -> None:
    repeated = rule(["i am", "i'm"], min_count=3)
    assert not requirement_passes("I am Anna. I'm happy.", repeated)
    assert requirement_passes("I am Anna. I'm happy. I am from Brazil.", repeated)
    distinct = rule(["myself", "yourself", "herself"], min_count=3, count_mode="distinct_terms")
    assert not requirement_passes("Myself, myself, myself.", distinct)
    assert requirement_passes("Myself, yourself, herself.", distinct)


@pytest.mark.parametrize("mode", ["occurrences", "distinct_terms"])
def test_alternativas_sobrepostas_nao_duplicam_evidencia(mode: str) -> None:
    required = rule(["want", "want to"], min_count=2, count_mode=mode)
    assert not requirement_passes("I want to learn.", required)
    assert requirement_passes("I want to learn. I want an answer.", required)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('She said "Hello."', True),
        ("She said “Hello.”", True),
        ('She said "Hello.', False),
        ("She said “Hello.", False),
        ('She said "".', False),
        ("She said “...”", False),
        ('She said "123"', False),
    ],
)
def test_fala_exige_aspas_fechadas_com_palavras(text: str, expected: bool) -> None:
    assert requirement_passes(text, rule([], kind="quoted_speech")) is expected


def test_contrato_antigo_de_aspas_e_adaptado_sem_recalcular_feedbacks() -> None:
    adapted = WritingRequirement.model_validate({"label": "fala", "terms": ['"', "“"]})
    assert adapted.kind == "quoted_speech"
    assert adapted.terms == []


@pytest.mark.parametrize(
    "invalid",
    [
        {"terms": []},
        {"terms": [""]},
        {"terms": [" "]},
        {"terms": ["are you", "ARE YOU "]},
        {"terms": ["!!!"]},
        {"terms": ["a" * 151]},
        {"terms": [1]},
        {"label": " "},
        {"min_count": 0},
        {"min_count": True},
        {"min_count": "2"},
        {"match_mode": "unknown"},
        {"kind": "regex"},
        {"count_mode": "sentences"},
        {"count_mode": "distinct_terms", "min_count": 2},
        {"count_mode": "distinct_terms", "match_mode": "all"},
        {"kind": "quoted_speech"},
        {"typo": "all"},
    ],
)
def test_contrato_recusa_rubrica_invalida(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WritingRequirement.model_validate({"label": "Marcador", "terms": ["hello"], **invalid})


LESSONS = load_seed()
PROMPTS = [
    pytest.param(prompt, id=f"{lesson['course_slug']}-{lesson['number']}-{prompt['position']}")
    for lesson in LESSONS
    for prompt in lesson["writing_prompts"]
]
RULES = [
    pytest.param(raw, id=f"{lesson['course_slug']}-{lesson['number']}-{index}")
    for lesson in LESSONS
    for prompt in lesson["writing_prompts"]
    for index, raw in enumerate(prompt["requirements"])
]


def witness(required: WritingRequirement) -> str:
    """Sonda sintética para alcançabilidade, NÃO uma redação recomendada."""
    if required.kind == "quoted_speech":
        return 'She said "Hello." ' * required.min_count
    terms = required.terms
    if required.match_mode == "all":
        selected = terms * required.min_count
    elif required.count_mode == "distinct_terms":
        selected = terms[: required.min_count]
    else:
        selected = [terms[0]] * required.min_count
    return ". ".join("I" + term if term.startswith("'") else term for term in selected) + "."


@pytest.mark.parametrize("raw", RULES)
def test_cada_criterio_editorial_tem_caso_positivo_e_negativo(raw: dict[str, object]) -> None:
    required = WritingRequirement.model_validate(raw)
    assert requirement_passes(witness(required), required)
    assert not requirement_passes("Zzz.", required)
    if required.min_count > 1:
        fewer = required.model_copy(update={"min_count": required.min_count - 1})
        assert not requirement_passes(witness(fewer), required)
    if required.match_mode == "all" and len(required.terms) > 1:
        missing = required.model_copy(update={"terms": required.terms[:-1]})
        assert not requirement_passes(witness(missing), required)


@pytest.mark.parametrize("prompt", PROMPTS)
def test_todas_as_propostas_sao_alcancaveis_sem_afirmar_gramatica(prompt) -> None:
    positive = " ".join(
        witness(WritingRequirement.model_validate(r)) for r in prompt["requirements"]
    )
    # Tamanho e pontuação são medidos separadamente; a sonda não atesta coerência.
    positive = positive[0].upper() + positive[1:]
    positive += " Example." * max(prompt["min_words"], prompt["min_sentences"])
    _, _, checks = analyze_writing(
        positive,
        min_words=prompt["min_words"],
        min_sentences=prompt["min_sentences"],
        requirements=prompt["requirements"],
    )
    assert all(check.passed for check in checks)
    _, _, negative = analyze_writing(
        "Zzz.",
        min_words=prompt["min_words"],
        min_sentences=prompt["min_sentences"],
        requirements=prompt["requirements"],
    )
    assert not any(check.passed for check in negative if check.code.startswith("requirement_"))


def test_seed_tipado_e_validado_antes_de_persistir() -> None:
    validate_writing_prompts(LESSONS)
    assert len(PROMPTS) == 82
    assert len(RULES) == 247  # 236 originais, 11 desdobramentos de critérios compostos.
    for lesson in LESSONS:
        for prompt in lesson["writing_prompts"]:
            for raw in prompt["requirements"]:
                assert {"kind", "match_mode", "count_mode", "min_count"} <= raw.keys()
    broken = deepcopy(LESSONS[:1])
    broken[0]["writing_prompts"][0]["requirements"][0]["terms"] = [" "]
    with pytest.raises(ValueError, match="Rubrica inválida: voa-level-1/1"):
        validate_writing_prompts(broken)
    broken[0]["writing_prompts"][0]["requirements"] = []
    with pytest.raises(ValueError, match="Rubrica inválida"):
        validate_writing_prompts(broken)


def test_snapshot_tem_hash_estavel_e_muda_quando_muda_a_regra() -> None:
    kwargs = dict(
        title="Title",
        instructions="Write.",
        min_words=10,
        min_sentences=2,
        requirements=[{"label": "Termo", "terms": ["ARE YOU "]}],
    )
    version, snapshot = rubric_snapshot(**kwargs)
    assert len(version) == 71
    assert snapshot["schema_version"] == 2
    assert rubric_snapshot(**kwargs)[0] == version
    normalized = {**kwargs, "requirements": [{"terms": ["are you"], "label": "Termo"}]}
    assert rubric_snapshot(**normalized)[0] == version
    changed = {**kwargs, "requirements": [{"label": "Termo", "terms": ["are you"], "min_count": 2}]}
    assert rubric_snapshot(**changed)[0] != version
    kwargs["requirements"][0]["terms"].append("hello")
    assert snapshot["requirements"][0]["terms"] == ["are you"]
