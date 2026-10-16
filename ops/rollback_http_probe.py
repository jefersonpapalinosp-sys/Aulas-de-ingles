"""Probe sem autenticação/conteúdo para a imagem anterior no clone DB-42."""

import json
import time
import urllib.error
import urllib.request


def get(path: str):
    with urllib.request.urlopen(
        f"http://rollback-api:8000{path}", timeout=3
    ) as response:
        if response.status != 200:
            raise RuntimeError("HTTP inesperado.")
        return json.load(response)


def main() -> None:
    deadline = time.monotonic() + 60
    while True:
        try:
            health = get("/api/health")
            courses = get("/api/courses")
            if (
                health.get("status") != "ok"
                or not isinstance(courses, list)
                or not courses
            ):
                raise RuntimeError("Aplicação anterior não leu o catálogo.")
            print(
                json.dumps({"verified": True, "health": "ok", "catalog_nonempty": True})
            )
            return
        except (OSError, RuntimeError, ValueError, urllib.error.URLError):
            if time.monotonic() >= deadline:
                raise SystemExit(2) from None
            time.sleep(0.5)


if __name__ == "__main__":
    main()
