"""One-time, explicit seed metadata bootstrap; never part of normal seed/apply.

Run from backend: uv run python ../ops/bootstrap_editorial_keys.py [--apply]
Refuses any already-keyed baseline rather than deriving identity after a reorder.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.editorial_identity import bootstrap_key  # noqa: E402


def records(courses, lessons):
    for course in courses:
        for unit in course["units"]:
            for item in (unit.get("review") or {}).get("questions", []):
                yield (
                    "course_review_question",
                    item,
                    (course["slug"], unit["slug"], item["position"]),
                )
    for lesson in lessons:
        parent = (lesson["course_slug"], lesson["number"])
        for field, table in (
            ("exercises", "exercise"),
            ("writing_prompts", "writing_prompt"),
            ("vocab", "vocab_item"),
            ("media", "lesson_media"),
        ):
            for item in lesson.get(field, []):
                coordinate = (*parent, item["term" if field == "vocab" else "position"])
                yield table, item, coordinate
                if field == "media":
                    for cue in item.get("cues", []):
                        yield "transcript_cue", cue, (*coordinate, cue["position"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    paths = [ROOT / "seed/courses.json", ROOT / "seed/lessons.json"]
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    original = deepcopy(documents)
    entries = list(records(*documents))
    if any("editorial_key" in item for _, item, _ in entries):
        raise SystemExit("Baseline already contains keys; preserve them, do not bootstrap again.")
    counts = Counter()
    seen = set()
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
