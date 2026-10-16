"""Inventário individual dos cues e decisões humanas, sem reproduzir transcrições."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seed" / "lessons.json"
DECISIONS = ROOT / "docs" / "cue_audit_decisions.json"
VALID_STATUS = {"approved", "rejected"}


def cue_key(lesson: dict[str, Any], media: dict[str, Any], cue: dict[str, Any]) -> str:
    return ":".join(
        (
            str(lesson["course_slug"]),
            f"lesson-{lesson['number']}",
            f"version-{lesson['content_version']}",
            f"media-{media['editorial_key']}",
            f"cue-{cue['editorial_key']}",
        )
    )


def inventory(
    lessons: list[dict[str, Any]], decisions_document: dict[str, Any]
) -> dict[str, Any]:
    if decisions_document.get("schema_version") != 1:
        raise ValueError("Versão do registro de decisões auditivas inválida.")
    decisions = decisions_document.get("decisions")
    if not isinstance(decisions, dict):
        raise TypeError("Registro de decisões auditivas inválido.")

    items: list[dict[str, Any]] = []
    known: set[str] = set()
    for lesson in lessons:
        for media in lesson.get("media", []):
            for cue in media.get("cues", []):
                key = cue_key(lesson, media, cue)
                if key in known:
                    raise ValueError("Identidade de cue duplicada.")
                known.add(key)
                decision = decisions.get(key)
                if decision is not None and (
                    not isinstance(decision, dict)
                    or decision.get("status") not in VALID_STATUS
                    or not decision.get("reviewer")
                    or not decision.get("reviewed_at")
                ):
                    raise ValueError("Decisão auditiva incompleta ou inválida.")
                items.append(
                    {
                        "key": key,
                        "course": lesson["course_slug"],
                        "lesson": lesson["number"],
                        "content_version": lesson["content_version"],
                        "media_position": media["position"],
                        "cue_position": cue["position"],
                        "start_seconds": cue["start_seconds"],
                        "end_seconds": cue["end_seconds"],
                        "status": decision["status"]
                        if decision
                        else "pending_human_listening",
                        "reviewer": decision.get("reviewer") if decision else None,
                        "reviewed_at": decision.get("reviewed_at")
                        if decision
                        else None,
                        "note": decision.get("note") if decision else None,
                    }
                )
    if set(decisions) - known:
        raise ValueError("Registro contém decisão para cue inexistente ou removido.")
    states = Counter(item["status"] for item in items)
    return {
        "schema_version": 1,
        "source": "seed/lessons.json",
        "decision_register": "docs/cue_audit_decisions.json",
        "summary": {"total": len(items), **dict(sorted(states.items()))},
        "items": items,
    }


def load() -> dict[str, Any]:
    lessons = json.loads(SEED.read_text(encoding="utf-8"))
    decisions = json.loads(DECISIONS.read_text(encoding="utf-8"))
    if not isinstance(lessons, list) or not isinstance(decisions, dict):
        raise TypeError("Fontes do inventário auditivo inválidas.")
    return inventory(lessons, decisions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        report = load()
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        print(
            "Inventário auditivo inválido; nenhuma aprovação foi presumida.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(
        json.dumps(
            report["summary"] if args.summary else report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    if args.require_complete and report["summary"].get("pending_human_listening", 0):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
