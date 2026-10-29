"""Checks do turno: puros, sem banco, provedor ou relógio."""

from app.domain.dialogue import (
    MAX_WORDS,
    MIN_WORDS,
    TurnExpectation,
    evaluate,
    failed_codes,
    words,
)


def codes(text: str, **kwargs: tuple[str, ...]) -> tuple[str, ...]:
    return failed_codes(evaluate(text, TurnExpectation(**kwargs)))


def test_turno_sem_expectativa_so_e_medido_por_tamanho() -> None:
    # Um turno de abertura não pede termo nem padrão; cobrar isso sugeriria ao
    # aluno que ele cumpriu — ou deixou de cumprir — algo que não foi pedido.
    checks = evaluate("The train is faster than the bus.", TurnExpectation())
    assert [check.code for check in checks] == ["too_short", "too_long"]
    assert all(check.passed for check in checks)


def test_um_termo_alvo_basta_e_a_ordem_dos_checks_e_fixa() -> None:
    expectation = TurnExpectation(target_terms=("train", "platform"))
    checks = evaluate("I took the train this morning.", expectation)
    assert [check.code for check in checks] == [
        "target_terms_missing",
        "too_short",
        "too_long",
    ]
    assert checks[0].passed and "train" in checks[0].detail
    # A conversa não é lista de palavras obrigatórias: um termo satisfaz.
    assert "platform" not in checks[0].detail


def test_termo_nao_e_encontrado_dentro_de_outra_palavra() -> None:
    # "can" dentro de "cancel" nao pode valer como termo falado, senao o aluno
    # recebe aprovado por uma palavra que nunca disse.
    assert codes("I will cancel the meeting now.", target_terms=("can",)) == (
        "target_terms_missing",
    )
    assert codes("I can go with you today.", target_terms=("can",)) == ()


def test_termo_de_varias_palavras_exige_sequencia_adjacente() -> None:
    assert codes("You ought to take the train.", target_terms=("ought to",)) == ()
    # As duas palavras aparecem, mas separadas: não é o padrão pedido.
    assert codes("You ought, I think, to go.", target_terms=("ought to",)) == (
        "target_terms_missing",
    )


def test_apostrofo_e_caixa_nao_mudam_o_resultado() -> None:
    for fala in ("I don't know the answer.", "I DON’T know the answer.", "i dont know it"):
        assert codes(fala, target_terms=("don't",)) == (), fala


def test_padrao_gramatical_e_avaliado_separado_do_vocabulario() -> None:
    expectation = TurnExpectation(target_terms=("platform",), grammar_patterns=("have you ever",))
    checks = evaluate("Have you ever waited on the platform?", expectation)
    assert failed_codes(checks) == ()
    assert [check.code for check in checks][:2] == [
        "target_terms_missing",
        "grammar_pattern_missing",
    ]
    # Vocabulário cumprido, padrão ausente: só o padrão reprova.
    assert failed_codes(evaluate("The platform was crowded today.", expectation)) == (
        "grammar_pattern_missing",
    )


def test_limites_de_tamanho_nas_fronteiras_exatas() -> None:
    assert codes(" ".join(["word"] * (MIN_WORDS - 1))) == ("too_short",)
    assert codes(" ".join(["word"] * MIN_WORDS)) == ()
    assert codes(" ".join(["word"] * MAX_WORDS)) == ()
    assert codes(" ".join(["word"] * (MAX_WORDS + 1))) == ("too_long",)


def test_silencio_reprova_por_tamanho_e_nao_por_vocabulario_sozinho() -> None:
    # Transcrição vazia é o que o STT devolve quando não houve fala. Reprovar
    # por tamanho é a leitura certa: não há nada a comentar sobre o não dito.
    assert codes("", target_terms=("train",)) == ("target_terms_missing", "too_short")
    assert codes("   ") == ("too_short",)


def test_pontuacao_e_espaco_nao_contam_como_palavra() -> None:
    assert words("Hello,   world! ...") == ["hello", "world"]
    assert words("don't — won't") == ["don't", "won't"]
