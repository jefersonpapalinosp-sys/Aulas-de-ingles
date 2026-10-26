"""IA-45: prompt, esquema e saneamento do parceiro de conversa. Testes puros, sem banco."""

import inspect
import json
from pathlib import Path

import pytest

from app.services import dialogue_prompts as dp

SEED = Path(__file__).resolve().parents[2] / "seed" / "lessons.json"


@pytest.fixture(scope="module")
def lesson_31() -> dict[str, object]:
    lessons = json.loads(SEED.read_text(encoding="utf-8"))
    return next(x for x in lessons if x["number"] == 31 and x["course_slug"] == "voa-level-1")


@pytest.fixture(scope="module")
def brief(lesson_31: dict[str, object]) -> dp.LessonBrief:
    return dp.brief_from_seed(lesson_31)


def test_brief_comes_only_from_lesson_content_without_markdown(brief: dp.LessonBrief) -> None:
    assert brief.title == "Take Me Out to the Ball Game"
    assert "ball game" in brief.target_terms and len(brief.target_terms) == 11
    assert any("faster than" in phrase for phrase in brief.phrases)
    assert all("**" not in text for text in (*brief.goals, *brief.phrases, *brief.grammar_examples))
    speakers = {speaker for speaker, _ in brief.script}
    assert {"Anna", "Jonathan"} <= speakers


def test_script_mode_alternates_roles_and_handles_single_speaker(brief: dp.LessonBrief) -> None:
    turns = dp.script_turns(brief)
    assert turns and turns[0]["speaker"] == "Anna" and turns[0]["role"] == "partner"
    assert {turn["role"] for turn in turns} == {"partner", "student"}
    swapped = dp.script_turns(brief, partner_speaker="Jonathan")
    assert next(t for t in swapped if t["speaker"] == "Jonathan")["role"] == "partner"
    single = dp.LessonBrief(
        "voa-level-1", 1, "Solo", (), (), (), (), (), (("Anna", "Hello."), ("Anna", "Bye."))
    )
    assert {turn["role"] for turn in dp.script_turns(single)} == {"repeat"}
    assert dp.script_turns(dp.LessonBrief("c", 1, "t", (), (), (), (), (), ())) == ()


def test_prompt_is_versioned_grounded_in_lesson_and_forbids_grading(brief: dp.LessonBrief) -> None:
    prompt = dp.system_prompt(brief, "guided")
    assert prompt.startswith(f"[{dp.PROMPT_VERSION}]")
    assert "Take Me Out to the Ball Game" in prompt and "ball game" in prompt
    assert "NEVER grade" in prompt and "NEVER comment on pronunciation" in prompt
    assert "NEVER ask for or mention personal data" in prompt
    assert "Answer ONLY with JSON" in prompt
    assert "bring the conversation back" in dp.system_prompt(brief, "free_unit")


def test_turn_payload_has_no_room_for_student_identity(brief: dp.LessonBrief) -> None:
    parameters = inspect.signature(dp.turn_messages).parameters
    assert not {"user", "user_id", "email", "name", "display_name"} & set(parameters)
    messages = dp.turn_messages(
        brief,
        "guided",
        "A taxi is faster than a bus.",
        ["target_terms_missing"],
        history=[("partner", "How do you go to the stadium?"), ("student", "By bus.")],
        requested_terms=["ball game"],
    )
    assert [m["role"] for m in messages] == ["system", "user"]
    user = messages[1]["content"]
    assert "Learner's latest turn (transcribed): A taxi is faster than a bus." in user
    assert "failed_checks: ['target_terms_missing']" in user
    assert "Partner: How do you go to the stadium?" in user
    joined = json.dumps(messages)
    assert "@" not in joined and "http" not in joined.lower()


def test_history_is_bounded(brief: dp.LessonBrief) -> None:
    history = [("student", f"turn {i}") for i in range(20)]
    user = dp.turn_messages(brief, "guided", "x", [], history=history)[1]["content"]
    assert "turn 19" in user and "turn 0" not in user
    assert user.count("Learner: turn") == dp.MAX_HISTORY_TURNS


def test_schema_restricts_hint_codes_to_failed_checks() -> None:
    schema = dp.response_schema(["too_short", "target_terms_missing"])
    codes = schema["properties"]["hints"]["items"]["properties"]["code"]["enum"]
    assert codes == ["target_terms_missing", "too_short"]
    assert schema["properties"]["hints"]["maxItems"] == 2
    assert schema["additionalProperties"] is False
    empty = dp.response_schema([])
    assert empty["properties"]["hints"]["maxItems"] == 0
    assert "grammar_pattern_missing" not in json.dumps(empty)


def test_sanitizer_drops_invented_codes_and_rejects_leaks() -> None:
    failed = ["target_terms_missing"]
    ok = dp.sanitize_provider_output(
        {
            "partner_text": "  Nice!  Do you like   baseball? ",
            "hints": [
                {"code": "target_terms_missing", "message": "Tente usar ball game."},
                {"code": "pronunciation", "message": "inventado"},
                {"code": "too_short", "message": "não reprovado neste turno"},
            ],
            "confidence": 0.9,
        },
        failed,
    )
    assert ok is not None
    assert ok.partner_text == "Nice! Do you like baseball?"
    assert [hint.code for hint in ok.hints] == ["target_terms_missing"]
    assert ok.confidence == 0.9
    assert (
        dp.sanitize_provider_output({"partner_text": "Visit https://x.y", "hints": []}, failed)
        is None
    )
    assert (
        dp.sanitize_provider_output({"partner_text": "Mail me a@b.co", "hints": []}, failed) is None
    )
    assert dp.sanitize_provider_output({"partner_text": "x" * 300, "hints": []}, failed) is None
    assert dp.sanitize_provider_output({"partner_text": "", "hints": []}, failed) is None
    assert dp.sanitize_provider_output("not json", failed) is None
    assert dp.sanitize_provider_output({"hints": []}, failed) is None
    leaky_hint = {
        "partner_text": "Ok.",
        "hints": [{"code": "target_terms_missing", "message": "see http://x"}],
    }
    assert dp.sanitize_provider_output(leaky_hint, failed) is None


def test_sanitizer_uses_conservative_confidence_and_dedupes_hints() -> None:
    result = dp.sanitize_provider_output(
        {
            "partner_text": "Good.",
            "hints": [
                {"code": "too_short", "message": "Fale mais."},
                {"code": "too_short", "message": "Repetido."},
            ],
            "confidence": 7,
        },
        ["too_short"],
    )
    assert result is not None
    assert result.confidence == 0.5
    assert len(result.hints) == 1
    missing = dp.sanitize_provider_output({"partner_text": "Good.", "hints": []}, [])
    assert missing is not None and missing.confidence == 0.5
