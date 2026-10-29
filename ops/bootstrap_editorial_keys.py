"""One-time, explicit seed metadata bootstrap; never part of normal seed/apply.

Run from backend: uv run python ../ops/bootstrap_editorial_keys.py [--apply]
Refuses any already-keyed baseline rather than deriving identity after a reorder.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.editorial_identity import bootstrap_key  # noqa: E402


def record(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Seed record must be a JSON object.")
    # Preserve the original object: the bootstrap adds keys to this exact record.
    return cast(dict[str, object], value)


def record_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise ValueError("Seed collection must be a JSON list.")
    return [record(item) for item in value]


def coordinate(value: object) -> str | int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or (isinstance(value, str) and not value)
    ):
        raise ValueError("Invalid baseline coordinate.")
    return value


def records(
    courses: object, lessons: object
) -> Iterator[tuple[str, dict[str, object], tuple[str | int, ...]]]:
    for course in record_list(courses):
        for unit in record_list(course["units"]):
            for item in record_list(record(unit.get("review") or {}).get("questions", [])):
                yield (
                    "course_review_question",
                    item,
                    tuple(coordinate(v) for v in (course["slug"], unit["slug"], item["position"])),
                )
    for lesson in record_list(lessons):
        parent = (coordinate(lesson["course_slug"]), coordinate(lesson["number"]))
        for field, table in (
            ("exercises", "exercise"),
            ("writing_prompts", "writing_prompt"),
            ("vocab", "vocab_item"),
            ("media", "lesson_media"),
        ):
            for item in record_list(lesson.get(field, [])):
                location = (*parent, coordinate(item["term" if field == "vocab" else "position"]))
                yield table, item, location
                if field == "media":
                    for cue in record_list(item.get("cues", [])):
                        yield "transcript_cue", cue, (*location, coordinate(cue["position"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    paths = [ROOT / "seed/courses.json", ROOT / "seed/lessons.json"]
    documents: tuple[object, object] = (
        json.loads(paths[0].read_text(encoding="utf-8")),
        json.loads(paths[1].read_text(encoding="utf-8")),
    )
    original = deepcopy(documents)
    entries = list(records(*documents))
    if any("editorial_key" in item for _, item, _ in entries):
        raise SystemExit("Baseline already contains keys; preserve them, do not bootstrap again.")
    counts: Counter[str] = Counter()
    seen: set[str] = set()
    for table, item, coordinate in entries:
        key = bootstrap_key(table, *coordinate)
        if key in seen:
            raise SystemExit("Duplicate baseline coordinate; nothing written.")
        seen.add(key)
        item["editorial_key"] = key
        counts[table] += 1
    stripped = deepcopy(documents)
    for _, item, _ in records(*stripped):
        del item["editorial_key"]
    assert stripped == original, "Non-identity content must remain byte-for-value identical"
    digest = hashlib.sha256(
        json.dumps(original, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    if args.apply:
        for path, document in zip(paths, documents, strict=True):
            path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    print(
        json.dumps(
            {"applied": args.apply, "counts": counts, "content_sha256_excluding_keys": digest}
        )
    )


if __name__ == "__main__":
    main()
