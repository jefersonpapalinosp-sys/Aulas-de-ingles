"""Regras determinísticas da orientação de escrita."""

from app.domain.writing import analyze_writing

REQUIREMENTS: list[dict[str, object]] = [
    {"label": "um comparativo com than", "terms": ["than"]},
    {"label": "um conselho com should ou ought to", "terms": ["should", "ought"]},
]


def test_feedback_aponta_o_que_falta_sem_reescrever_o_texto() -> None:
    words, sentences, checks = analyze_writing(
        "bus is fast", min_words=8, min_sentences=2, requirements=REQUIREMENTS
    )

    assert words == 3
    assert sentences == 1
    assert all(check.passed is False for check in checks)
    assert [check.code for check in checks] == [
        "word_count",
        "sentence_count",
        "requirement_0",
        "requirement_1",
        "capitalization",
        "ending_punctuation",
    ]


def test_feedback_aprova_texto_que_atende_aos_criterios() -> None:
    words, sentences, checks = analyze_writing(
        "The train is faster than the bus. Visitors should take the train!",
        min_words=10,
        min_sentences=2,
        requirements=REQUIREMENTS,
    )

    assert words == 12
    assert sentences == 2
    assert all(check.passed for check in checks)
