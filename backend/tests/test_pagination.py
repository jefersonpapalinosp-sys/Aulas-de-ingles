"""Opaque cursor contract independent from any one history endpoint."""

from datetime import UTC, datetime

import pytest

from app.pagination import InvalidCursor, decode_time_id_cursor, encode_time_id_cursor


def test_time_id_cursor_round_trip_is_opaque_and_normalized() -> None:
    timestamp = datetime(2026, 10, 15, 20, 45, 12, 123456, tzinfo=UTC)

    encoded = encode_time_id_cursor(timestamp, 42)
    decoded = decode_time_id_cursor(encoded)

    assert decoded.timestamp == timestamp
    assert decoded.row_id == 42
    assert "2026" not in encoded


@pytest.mark.parametrize("value", ["", "***", "e30", "e1wiaWQiOjB9", "a" * 257])
def test_time_id_cursor_rejects_invalid_or_unsupported_values(value: str) -> None:
    with pytest.raises(InvalidCursor):
        decode_time_id_cursor(value)
