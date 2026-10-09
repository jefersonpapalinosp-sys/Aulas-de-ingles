"""Consistência estrutural dos cues de áudio.

Isto **não substitui a escuta humana**: não verifica se o timestamp cai na
fala certa. Pega a classe de erro que a escuta demoraria a achar — cue fora
do áudio, sobreposição e janela curta demais para o texto caber.
"""

from app.db.seed import load_seed

# Fala em inglês passa raramente de 20 caracteres por segundo. Acima deste
# teto o texto não cabe na janela, sinal de que o timestamp está errado.
CARACTERES_POR_SEGUNDO_MAXIMO = 28.0


def _cues_com_contexto():
    for lesson in load_seed():
        for media in lesson.get("media", []):
            yield (
                f"{lesson['course_slug']}/aula {lesson['number']}",
                media.get("duration_seconds"),
                media.get("cues", []),
            )


def test_todo_cue_comeca_antes_de_terminar() -> None:
    problemas = [
        f"{ref} cue {c['position']}: {c['start_seconds']}s não é menor que {c['end_seconds']}s"
        for ref, _, cues in _cues_com_contexto()
        for c in cues
        if c["start_seconds"] >= c["end_seconds"] or c["start_seconds"] < 0
    ]
    assert not problemas, problemas


def test_nenhum_cue_passa_da_duracao_do_audio() -> None:
    problemas = [
        f"{ref} cue {c['position']}: termina em {c['end_seconds']}s, áudio tem {dur}s"
        for ref, dur, cues in _cues_com_contexto()
        if dur
        for c in cues
        if c["end_seconds"] > dur
    ]
    assert not problemas, problemas


def test_cues_nao_se_sobrepoem() -> None:
    """Começar exatamente onde o anterior terminou é adjacência, não sobreposição."""
    problemas = []
    for ref, _, cues in _cues_com_contexto():
        fim_anterior = -1
        for c in sorted(cues, key=lambda x: x["position"]):
            if c["start_seconds"] < fim_anterior:
                problemas.append(
                    f"{ref} cue {c['position']}: começa em {c['start_seconds']}s, "
                    f"mas o anterior só termina em {fim_anterior}s"
                )
            fim_anterior = c["end_seconds"]
    assert not problemas, problemas


def test_o_texto_cabe_na_janela() -> None:
    problemas = []
    for ref, _, cues in _cues_com_contexto():
        for c in cues:
            janela = c["end_seconds"] - c["start_seconds"]
            texto = c.get("text_en", "")
            if janela <= 0 or not texto:
                continue
            cps = len(texto) / janela
            if cps > CARACTERES_POR_SEGUNDO_MAXIMO:
                problemas.append(
                    f"{ref} cue {c['position']}: {len(texto)} caracteres em {janela}s "
                    f"= {cps:.1f} char/s"
                )
    assert not problemas, problemas


def test_todo_cue_tem_traducao() -> None:
    problemas = [
        f"{ref} cue {c['position']}"
        for ref, _, cues in _cues_com_contexto()
        for c in cues
        if not c.get("text_pt")
    ]
    assert not problemas, problemas
