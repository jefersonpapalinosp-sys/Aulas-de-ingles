"""Opaque, stable keyset cursors shared by private history endpoints."""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import UTC, datetime

# Teto comum das listagens privadas. As rotas legadas (sem cursor) devolvem no
# máximo uma página e apontam a alternativa paginada neste cabeçalho.
PAGE_LIMIT_MAX = 100
PAGINATED_ALTERNATIVE_HEADER = "X-Paginated-Alternative"


class InvalidCursor(ValueError):
    """The cursor is malformed or belongs to an unsupported contract version."""


@dataclass(frozen=True, slots=True)
class TimeIdCursor:
    timestamp: datetime
    row_id: int


def encode_time_id_cursor(timestamp: datetime, row_id: int) -> str:
    if timestamp.tzinfo is None or row_id < 1:
        raise ValueError("Cursor requires an aware timestamp and positive row id.")
    payload = json.dumps(
        {
            "id": row_id,
            "ts": timestamp.astimezone(UTC).isoformat(timespec="microseconds"),
            "v": 1,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_time_id_cursor(value: str) -> TimeIdCursor:
    if not value or len(value) > 256:
        raise InvalidCursor("invalid cursor")
    try:
        padding = "=" * (-len(value) % 4)
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or set(payload) != {"id", "ts", "v"}:
            raise InvalidCursor("invalid cursor")
        if (
            type(payload["v"]) is not int
            or payload["v"] != 1
            or type(payload["id"]) is not int
            or payload["id"] < 1
        ):
            raise InvalidCursor("invalid cursor")
        if not isinstance(payload["ts"], str):
            raise InvalidCursor("invalid cursor")
        timestamp = datetime.fromisoformat(payload["ts"])
        if timestamp.tzinfo is None:
            raise InvalidCursor("invalid cursor")
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        TypeError,
    ) as error:
        raise InvalidCursor("invalid cursor") from error
    return TimeIdCursor(timestamp.astimezone(UTC), payload["id"])
