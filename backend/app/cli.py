"""Comandos operacionais da aplicação."""

import asyncio
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from app.core.config import get_settings
from app.db.seed import load_seed_graph, preview_seed, seed_lessons
from app.db.seed_plan import SeedBlocked
from app.db.session import dispose_engine, get_sessionmaker
from app.services.assist_gate import (
    Modality,
    collect_gate_metrics,
    evaluate_gate,
    load_provider_review,
)
from app.services.editorial_archive import REASONS as ARCHIVE_REASONS
from app.services.editorial_archive import archive_unit
from app.services.editorial_audit import preview_editorial_audit
from app.services.editorial_plan import preview_unit_archive
from app.services.editorial_reorder import REASONS as REORDER_REASONS
from app.services.editorial_reorder import apply_editorial_reorder
from app.services.editorial_reorder_plan import preview_editorial_reorder
from app.services.maintenance import SCOPES, heartbeat_age_seconds, retention_batch
from app.services.transcription_queue import run_transcription_worker


async def _seed(*, dry_run: bool = False, path: Path | None = None) -> bool:
    try:
        async with get_sessionmaker()() as session:
            if dry_run:
                report = await preview_seed(session, path)
                print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
                return bool(report["allowed"])
            try:
                total = await seed_lessons(session, path)
            except SeedBlocked as error:
                print(json.dumps(error.report, ensure_ascii=False, indent=2, default=str))
                return False
        print(f"✓ seed aplicado: {total} aulas")
        return True
    finally:
        await dispose_engine()


async def _assist_gate(modality: Modality, review_path: Path) -> bool:
    review = load_provider_review(review_path)
    try:
        async with get_sessionmaker()() as session:
            metrics = await collect_gate_metrics(
                session, modality, provider_name=review.provider_name
            )
    finally:
        await dispose_engine()
    report = evaluate_gate(modality, metrics, review, get_settings())
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return report.approved


async def _worker_health(max_age_seconds: int) -> bool:
    """Healthcheck do container do worker: a batida mais recente é fresca?

    Usa a URL e o papel do próprio processo (as variáveis do container). A saída
    é guardada pelo Docker em `inspect`, por isso só leva idade e veredito: nada
    de DSN, papel, contagens ou conteúdo.
    """
    try:
        age = await heartbeat_age_seconds()
    finally:
        await dispose_engine()
    if age is None:
        print("worker-health: nenhuma batida registrada")
        return False
    fresh = age <= max_age_seconds
    estado = "ok" if fresh else "parada"
    print(f"worker-health: batida há {int(age)}s ({estado}; limite {max_age_seconds}s)")
    return fresh


async def _editorial_plan(course_slug: str, unit_slug: str) -> None:
    try:
        async with get_sessionmaker()() as session:
            report = await preview_unit_archive(session, course_slug, unit_slug)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        await dispose_engine()


async def _editorial_archive(**kwargs: str) -> None:
    try:
        async with get_sessionmaker()() as session:
            receipt = await archive_unit(session, **kwargs)
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    finally:
        await dispose_engine()


async def _editorial_audit() -> None:
    try:
        async with get_sessionmaker()() as session:
            report = await preview_editorial_audit(session)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    finally:
        await dispose_engine()


async def _editorial_reorder_plan(path: Path | None = None) -> None:
    try:
        _, graph = load_seed_graph(path)
        async with get_sessionmaker()() as session:
            report = await preview_editorial_reorder(session, graph)
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    finally:
        await dispose_engine()


async def _editorial_reorder(path: Path | None = None, **kwargs: str) -> None:
    try:
        _, graph = load_seed_graph(path)
        async with get_sessionmaker()() as session:
            receipt = await apply_editorial_reorder(session, graph, **kwargs)
        print(json.dumps(receipt, ensure_ascii=False, indent=2, default=str))
    finally:
        await dispose_engine()


def main_com_argumentos(argumentos: list[str]) -> None:
    """Separado de main() para o teste poder chamar sem mexer em sys.argv."""
    comando = argumentos[0] if argumentos else ""
    if comando == "seed":
        import argparse

        parser = argparse.ArgumentParser(prog="seed")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--file", type=Path)
        args = parser.parse_args(argumentos[1:])
        try:
            allowed = asyncio.run(_seed(dry_run=args.dry_run, path=args.file))
        except (ValueError, KeyError, TypeError, OSError):
            print(
                "Pacote de seed inválido ou inacessível; nenhuma carga concluída.", file=sys.stderr
            )
            raise SystemExit(2) from None
        except DBAPIError:
            print(
                "Seed não concluído: banco ocupado, indisponível ou contrato incompatível. "
                "Verifique o ambiente/permissões e repita a prévia.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
        if not allowed:
            raise SystemExit(1)
    elif comando == "editorial-plan":
        import argparse

        parser = argparse.ArgumentParser(prog="editorial-plan")
        parser.add_argument("--course", required=True)
        parser.add_argument("--unit", required=True)
        args = parser.parse_args(argumentos[1:])
        try:
            asyncio.run(_editorial_plan(args.course, args.unit))
        except ValueError as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(2) from None
        except (DBAPIError, TimeoutError):
            print("Prévia indisponível; confira banco, schema e permissões.", file=sys.stderr)
            raise SystemExit(1) from None
    elif comando == "editorial-archive":
        import argparse

        parser = argparse.ArgumentParser(prog="editorial-archive")
        parser.add_argument("--course", dest="course_slug", required=True)
        parser.add_argument("--unit", dest="unit_slug", required=True)
        parser.add_argument("--catalog-sha256", dest="expected_catalog_sha256", required=True)
        parser.add_argument("--operation-key", required=True)
        parser.add_argument("--operator", dest="operator_label", required=True)
        parser.add_argument("--reason", dest="reason_code", choices=ARCHIVE_REASONS, required=True)
        parser.add_argument("--confirm-database", required=True)
        parser.add_argument("--apply", action="store_true", required=True)
        archive_args = vars(parser.parse_args(argumentos[1:]))
        archive_args.pop("apply")
        try:
            asyncio.run(_editorial_archive(**archive_args))
        except ValueError as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(2) from None
        except (DBAPIError, TimeoutError):
            print(
                "Arquivamento não confirmado. Repita a mesma operação/chave para conferir "
                "o recibo; não execute SQL manual.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
    elif comando == "editorial-audit":
        import argparse

        parser = argparse.ArgumentParser(prog="editorial-audit")
        parser.parse_args(argumentos[1:])
        try:
            asyncio.run(_editorial_audit())
        except (ValueError, KeyError, TypeError, OSError):
            print(
                "Auditoria editorial inválida ou incompleta; nenhuma alteração foi feita.",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        except (DBAPIError, TimeoutError):
            print(
                "Auditoria editorial indisponível; nenhuma alteração foi feita.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
    elif comando == "editorial-reorder-plan":
        import argparse

        parser = argparse.ArgumentParser(prog="editorial-reorder-plan")
        parser.add_argument("--file", type=Path)
        args = parser.parse_args(argumentos[1:])
        try:
            asyncio.run(_editorial_reorder_plan(args.file))
        except (ValueError, KeyError, TypeError, OSError) as error:
            print(f"Prévia de reordenação inválida: {error}", file=sys.stderr)
            raise SystemExit(2) from None
        except (DBAPIError, TimeoutError):
            print(
                "Prévia de reordenação indisponível; nenhuma alteração foi feita.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
    elif comando == "editorial-reorder":
        import argparse

        parser = argparse.ArgumentParser(prog="editorial-reorder")
        parser.add_argument("--file", type=Path)
        parser.add_argument("--plan-sha256", dest="expected_plan_sha256", required=True)
        parser.add_argument("--operation-key", required=True)
        parser.add_argument("--operator", dest="operator_label", required=True)
        parser.add_argument("--reason", dest="reason_code", choices=REORDER_REASONS, required=True)
        parser.add_argument("--confirm-database", required=True)
        parser.add_argument("--apply", action="store_true", required=True)
        reorder_args = vars(parser.parse_args(argumentos[1:]))
        path = reorder_args.pop("file")
        reorder_args.pop("apply")
        try:
            asyncio.run(_editorial_reorder(path, **reorder_args))
        except (ValueError, KeyError, TypeError, OSError) as error:
            print(str(error), file=sys.stderr)
            raise SystemExit(2) from None
        except (DBAPIError, TimeoutError, RuntimeError):
            print(
                "Reordenação não confirmada. Repita a mesma operação/chave para conferir "
                "o recibo; não execute SQL manual.",
                file=sys.stderr,
            )
            raise SystemExit(1) from None
    elif comando == "writing-rubrics":
        print(
            "Comando desativado: as rubricas divergentes exigem versionamento e homologação. "
            "Use editorial-audit para a análise somente leitura.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    elif comando == "assist-gate":
        try:
            modality_index = argumentos.index("--modality") + 1
            review_index = argumentos.index("--review-file") + 1
            modality = argumentos[modality_index]
            review_path = Path(argumentos[review_index])
        except (ValueError, IndexError):
            print(
                "uso: python -m app.cli assist-gate --modality "
                "transcription|writing|conversation --review-file caminho.json",
                file=sys.stderr,
            )
            raise SystemExit(2) from None
        # O mapa valida e tipa de uma vez: um nome fora do conjunto não compila.
        modalidades: dict[str, Modality] = {
            "transcription": "transcription",
            "writing": "writing",
            "conversation": "conversation",
        }
        escolhida = modalidades.get(modality)
        if escolhida is None:
            print(
                "modalidade inválida: use transcription, writing ou conversation", file=sys.stderr
            )
            raise SystemExit(2)
        try:
            approved = asyncio.run(_assist_gate(escolhida, review_path))
        except (OSError, ValueError) as error:
            print(f"manifesto inválido: {error}", file=sys.stderr)
            raise SystemExit(2) from None
        if not approved:
            raise SystemExit(1)
    elif comando == "assist-worker":
        from app.core.logging import configurar

        configurar(get_settings().log_level)
        asyncio.run(run_transcription_worker(once="--once" in argumentos[1:]))
    elif comando == "worker-health":
        import argparse

        parser = argparse.ArgumentParser(prog="worker-health")
        parser.add_argument("--max-age-seconds", type=int, default=60)
        args = parser.parse_args(argumentos[1:])
        if args.max_age_seconds < 1:
            parser.error("--max-age-seconds deve ser um inteiro >= 1")
        try:
            fresh = asyncio.run(_worker_health(args.max_age_seconds))
        except (SQLAlchemyError, OSError, TimeoutError, RuntimeError):
            # 2 = não deu para perguntar ao banco (conexão, papel, timeout).
            # Sem a exceção na saída: ela pode carregar host, papel ou SQL.
            print("worker-health: banco inacessível", file=sys.stderr)
            raise SystemExit(2) from None
        if not fresh:
            raise SystemExit(1)
    elif comando == "retention":
        import argparse

        parser = argparse.ArgumentParser(prog="retention")
        parser.add_argument("--scope", choices=SCOPES, required=True)
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirm-database")
        args = parser.parse_args(argumentos[1:])
        asyncio.run(_retention(args.scope, args.limit, args.apply, args.confirm_database))
    else:
        print(
            "uso: python -m app.cli seed | editorial-audit | editorial-plan | "
            "editorial-reorder-plan | editorial-reorder | editorial-archive | assist-gate | "
            "assist-worker [--once] | worker-health [--max-age-seconds N] | retention",
            file=sys.stderr,
        )
        raise SystemExit(2)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    main_com_argumentos(sys.argv[1:])


async def _retention(scope: str, limit: int, apply: bool, confirm_database: str | None) -> None:
    try:
        async with get_sessionmaker()() as session:
            database = await session.scalar(select(func.current_database()))
        if apply and confirm_database != database:
            raise ValueError("Confirme o banco antes de aplicar retenção.")
        count = await retention_batch(scope, apply=apply, limit=limit)
        print(json.dumps({"scope": scope, "limit": limit, "dry_run": not apply, "count": count}))
    finally:
        await dispose_engine()


if __name__ == "__main__":
    main()
