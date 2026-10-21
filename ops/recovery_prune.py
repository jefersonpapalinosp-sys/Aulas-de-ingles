"""Poda de pacotes de backup: 7 diários + 4 semanais ISO. Dry-run por padrão.

Relata somente nome, data e tamanho; nunca conteúdo de manifesto.
"""

import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ops.recovery_archive import FORMAT, LEGACY_FORMAT, RecoveryError, require

# create_bundle publica `aulas-<%Y%m%dT%H%M%S%fZ>-<uuid4().hex>` (UTC) e usa
# `.partial-<mesmo id>` como área de captura até a publicação.
STAMP_FORMAT = "%Y%m%dT%H%M%S%fZ"
BUNDLE_RE = re.compile(r"aulas-(?P<stamp>\d{8}T\d{12}Z)-[0-9a-f]{32}")
PARTIAL_PREFIX = ".partial-"
KEEP_DAILY = 7
KEEP_WEEKLY = 4
PARTIAL_GRACE = timedelta(hours=24)
MAX_MANIFEST = 32 * 1024 * 1024


@dataclass(frozen=True)
class Bundle:
    name: str
    stamp: datetime
    size: int


@dataclass(frozen=True)
class Partial:
    name: str
    stamp: datetime
    size: int
    touched: datetime


@dataclass(frozen=True)
class Foreign:
    name: str
    kind: str
    size: int
    note: str


@dataclass(frozen=True)
class PrunePlan:
    root: Path
    now: datetime
    keep_daily: int
    keep_weekly: int
    newest: str
    keep: tuple[tuple[Bundle, tuple[str, ...]], ...]
    remove: tuple[Bundle, ...]
    partials: tuple[Partial, ...]
    foreign: tuple[Foreign, ...]

    def partial_removable(self, partial):
        return self.now - partial.touched >= PARTIAL_GRACE

    def targets(self):
        removable = [p.name for p in self.partials if self.partial_removable(p)]
        return [b.name for b in self.remove] + removable


def parse_stamp(stamp):
    try:
        return datetime.strptime(stamp, STAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        return None


def tree_size(path):
    total = 0
    for current, _dirs, files in os.walk(path):
        for name in files:
            total += os.lstat(os.path.join(current, name)).st_size
    return total


def last_touch(path, stamp):
    moments = [stamp, datetime.fromtimestamp(path.lstat().st_mtime, UTC)]
    moments += [datetime.fromtimestamp(child.lstat().st_mtime, UTC) for child in path.iterdir()]
    return max(moments)


def identity_matches(path):
    """Só confere que o manifesto existe e nomeia este diretório; nada do conteúdo é retido."""
    manifest = path / "manifest.json"
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > MAX_MANIFEST:
        return False
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return (
        isinstance(value, dict)
        and value.get("bundle_id") == path.name
        and value.get("format") in {FORMAT, LEGACY_FORMAT}
    )


def scan(root):
    require(
        root.is_dir() and not root.is_symlink(),
        "Diretório de backups ausente ou é link; poda recusada.",
    )
    bundles, partials, foreign = [], [], []
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        name = entry.name
        if entry.is_symlink():
            foreign.append(Foreign(name, "link", 0, "link não é pacote"))
            continue
        if not entry.is_dir():
            foreign.append(Foreign(name, "arquivo", entry.lstat().st_size, "não é diretório"))
            continue
        if name.startswith(PARTIAL_PREFIX):
            match = BUNDLE_RE.fullmatch(name.removeprefix(PARTIAL_PREFIX))
            stamp = parse_stamp(match["stamp"]) if match else None
            if stamp is None:
                foreign.append(
                    Foreign(name, "diretório", tree_size(entry), "parcial fora do padrão")
                )
                continue
            partials.append(Partial(name, stamp, tree_size(entry), last_touch(entry, stamp)))
            continue
        match = BUNDLE_RE.fullmatch(name)
        stamp = parse_stamp(match["stamp"]) if match else None
        if stamp is None:
            foreign.append(Foreign(name, "diretório", tree_size(entry), "nome fora do padrão"))
            continue
        if not identity_matches(entry):
            foreign.append(
                Foreign(name, "diretório", tree_size(entry), "manifesto ausente ou de outro pacote")
            )
            continue
        bundles.append(Bundle(name, stamp, tree_size(entry)))
    return bundles, partials, foreign


def select(bundles, keep_daily=KEEP_DAILY, keep_weekly=KEEP_WEEKLY):
    """Mais recente sempre; o mais novo de cada um dos últimos `keep_daily` dias civis UTC;
    o mais novo de cada uma das `keep_weekly` semanas ISO anteriores à semana do diário mais antigo.
    """
    ordered = sorted(bundles, key=lambda b: (b.stamp, b.name), reverse=True)
    reasons = {}
    if ordered:
        reasons.setdefault(ordered[0].name, []).append("mais recente")
    days = []
    for bundle in ordered:
        day = bundle.stamp.date()
        if day in days:
            continue
        if len(days) == keep_daily:
            break
        days.append(day)
        reasons.setdefault(bundle.name, []).append("diário")
    oldest_daily_week = days[-1].isocalendar()[:2] if days else None
    weeks = []
    for bundle in ordered:
        week = bundle.stamp.isocalendar()[:2]
        if (oldest_daily_week is not None and week >= oldest_daily_week) or week in weeks:
            continue
        if len(weeks) == keep_weekly:
            break
        weeks.append(week)
        reasons.setdefault(bundle.name, []).append("semanal")
    keep = tuple((b, tuple(reasons[b.name])) for b in ordered if b.name in reasons)
    remove = tuple(b for b in ordered if b.name not in reasons)
    return keep, remove


def plan_prune(root, now=None, keep_daily=KEEP_DAILY, keep_weekly=KEEP_WEEKLY):
    root = Path(root)
    now = now or datetime.now(UTC)
    bundles, partials, foreign = scan(root)
    require(bundles, "Nenhum pacote válido no diretório de backups; poda recusada.")
    keep, remove = select(bundles, keep_daily, keep_weekly)
    return PrunePlan(
        root=root,
        now=now,
        keep_daily=keep_daily,
        keep_weekly=keep_weekly,
        newest=keep[0][0].name,
        keep=keep,
        remove=remove,
        partials=tuple(sorted(partials, key=lambda p: p.stamp, reverse=True)),
        foreign=tuple(foreign),
    )


def confirm_removable(plan, name):
    require(
        BUNDLE_RE.fullmatch(name.removeprefix(PARTIAL_PREFIX)) is not None,
        "Nome fora do padrão de pacote; remoção recusada.",
    )
    require(name != plan.newest, "O pacote mais recente nunca é removido.")
    require(name in plan.targets(), "Item fora do plano; remoção recusada.")
    require(
        plan.root.is_dir() and not plan.root.is_symlink(),
        "Diretório de backups ausente ou é link; remoção recusada.",
    )
    path = plan.root / name
    require(
        not path.is_symlink() and path.is_dir(),
        "Alvo não é diretório regular; remoção recusada.",
    )
    require(
        path.resolve(strict=True).parent == plan.root.resolve(strict=True),
        "Alvo fora do diretório de backups; remoção recusada.",
    )
    return path


def apply_prune(plan):
    removed = []
    for name in plan.targets():
        path = confirm_removable(plan, name)
        try:
            shutil.rmtree(path)
        except OSError as exc:
            raise RecoveryError(
                f"Remoção interrompida em {name} após {len(removed)} remoções; refaça o dry-run."
            ) from exc
        removed.append(name)
    return removed


def human(size):
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _when(moment):
    return f"{moment:%Y-%m-%d %H:%M:%SZ}"


def _age_hours(plan, partial):
    return (plan.now - partial.touched) / timedelta(hours=1)


def render_text(plan, removed):
    mode = "aplicada" if removed is not None else "dry-run"
    lines = [
        f"Poda de {plan.root} ({mode}); referência {plan.now:%Y-%m-%dT%H:%M:%SZ}; "
        f"janela {plan.keep_daily} diários + {plan.keep_weekly} semanais ISO.",
        f"Manter ({len(plan.keep)}):",
        *(
            f"  {b.name}  {_when(b.stamp)}  {human(b.size):>9}  {', '.join(reasons)}"
            for b, reasons in plan.keep
        ),
        f"Remover ({len(plan.remove)}):",
        *(f"  {b.name}  {_when(b.stamp)}  {human(b.size):>9}" for b in plan.remove),
        f"Parciais ({len(plan.partials)}):",
        *(
            f"  {p.name}  {_when(p.stamp)}  {human(p.size):>9}  idade {_age_hours(plan, p):.1f} h  "
            + ("remover" if plan.partial_removable(p) else "protegido (< 24 h)")
            for p in plan.partials
        ),
        f"Fora da política ({len(plan.foreign)}), ignorados:",
        *(f"  {f.name}  {f.kind}  {human(f.size):>9}  {f.note}" for f in plan.foreign),
    ]
    if removed is None:
        lines.append("Nada foi alterado em disco; use --apply para executar este plano.")
    else:
        lines.append(f"Removidos ({len(removed)}): {', '.join(removed) or 'nenhum'}")
    return "\n".join(lines)


def plan_as_dict(plan, removed):
    return {
        "root": str(plan.root),
        "mode": "apply" if removed is not None else "dry-run",
        "now": plan.now.isoformat(),
        "policy": {
            "keep_daily": plan.keep_daily,
            "keep_weekly": plan.keep_weekly,
            "partial_grace_hours": PARTIAL_GRACE / timedelta(hours=1),
        },
        "newest": plan.newest,
        "keep": [
            {"name": b.name, "date": b.stamp.isoformat(), "size": b.size, "reasons": list(r)}
            for b, r in plan.keep
        ],
        "remove": [
            {"name": b.name, "date": b.stamp.isoformat(), "size": b.size} for b in plan.remove
        ],
        "partials": [
            {
                "name": p.name,
                "date": p.stamp.isoformat(),
                "size": p.size,
                "age_hours": round(_age_hours(plan, p), 1),
                "action": "remove" if plan.partial_removable(p) else "protect",
            }
            for p in plan.partials
        ],
        "out_of_policy": [
            {"name": f.name, "kind": f.kind, "size": f.size, "note": f.note} for f in plan.foreign
        ],
        "removed": list(removed or []),
    }


def render_plan(plan, removed=None, as_json=False):
    if as_json:
        return json.dumps(plan_as_dict(plan, removed), ensure_ascii=False, indent=2, sort_keys=True)
    return render_text(plan, removed)
