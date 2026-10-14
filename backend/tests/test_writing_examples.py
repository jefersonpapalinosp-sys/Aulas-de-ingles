"""Exemplos autorais completos. Passar aqui não é homologação por professor."""

import json
import re
from pathlib import Path

import pytest

from app.db.seed import load_seed
from app.domain.writing import analyze_writing, requirement_passes
from app.domain.writing_rubric import WritingRequirement, normalize_marker

ROOT = Path(__file__).resolve().parents[2] / "seed"
EXAMPLES = {
    f"voa-level-{level}": json.loads((ROOT / f"writing_examples_level_{level}.json").read_text())
    for level in (1, 2)
}
LESSONS = load_seed()
CASES = [
    pytest.param(lesson, id=f"{lesson['course_slug']}-{lesson['number']}") for lesson in LESSONS
]


def test_corpus_cobre_exatamente_o_catalogo_sem_casos_duplicados():
    assert sum(len(examples) for examples in EXAMPLES.values()) == len(LESSONS) == 82
    for course, examples in EXAMPLES.items():
        assert set(examples) == {
            str(lesson["number"]) for lesson in LESSONS if lesson["course_slug"] == course
        }
        assert len(set(examples.values())) == len(examples)


@pytest.mark.parametrize("lesson", CASES)
def test_texto_natural_compatível_e_negativos_discriminantes(lesson):
    prompt = lesson["writing_prompts"][0]
    text = EXAMPLES[lesson["course_slug"]][str(lesson["number"])]
    _, _, checks = analyze_writing(
        text,
        min_words=prompt["min_words"],
        min_sentences=prompt["min_sentences"],
        requirements=prompt["requirements"],
    )
    assert all(c.passed for c in checks), [c.label for c in checks if not c.passed]
    # Remover cada família de evidência do texto real deve reprovar aquele critério.
    for raw in prompt["requirements"]:
        requirement = WritingRequirement.model_validate(raw)
        negative = normalize_marker(text)
        if requirement.kind == "quoted_speech":
            negative = negative.translate(str.maketrans("", "", '"“”'))
        else:
            for term in sorted(requirement.terms, key=len, reverse=True):
                negative = re.sub(re.escape(term).replace(r"\ ", r"\s+"), "", negative)
        assert not requirement_passes(negative, requirement), requirement.label
    # Um texto curto fora da tarefa nunca deve ser anunciado como completo.
    _, _, negative_checks = analyze_writing(
        "The door is open.",
        min_words=prompt["min_words"],
        min_sentences=prompt["min_sentences"],
        requirements=prompt["requirements"],
    )
    assert not all(c.passed for c in negative_checks)
