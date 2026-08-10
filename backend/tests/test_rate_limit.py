# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Caracterización de rate_limit.py — el reemplazo compartido-entre-workers de
los dicts en memoria de middleware/security.py y routers/auth.py.
"""
import pytest

from rate_limit import increment, is_rate_limited, peek_count, purge_expired
from tests.fakes import FakeRow, FakeSession, WithRowcount


def is_upsert(sql, params):
    return "INSERT INTO rate_limit_counters" in sql


def is_peek(sql, params):
    return "SELECT count FROM rate_limit_counters" in sql


def is_purge(sql, params):
    return "DELETE FROM rate_limit_counters" in sql


@pytest.mark.asyncio
async def test_under_limit_is_not_rate_limited():
    db = FakeSession([(is_upsert, [3])])  # count devuelto tras el incremento
    limited = await is_rate_limited(db, "1.2.3.4:/api/", max_count=10, window_seconds=60)
    assert limited is False


@pytest.mark.asyncio
async def test_exactly_at_limit_is_not_rate_limited():
    db = FakeSession([(is_upsert, [10])])
    limited = await is_rate_limited(db, "1.2.3.4:/api/", max_count=10, window_seconds=60)
    assert limited is False


@pytest.mark.asyncio
async def test_over_limit_is_rate_limited():
    db = FakeSession([(is_upsert, [11])])
    limited = await is_rate_limited(db, "1.2.3.4:/api/", max_count=10, window_seconds=60)
    assert limited is True


@pytest.mark.asyncio
async def test_upsert_uses_correct_key_and_commits():
    db = FakeSession([(is_upsert, [1])])
    await is_rate_limited(db, "acme@example.com", max_count=8, window_seconds=300)
    calls = db.sql_calls_matching("INSERT INTO rate_limit_counters")
    assert len(calls) == 1
    assert calls[0][1]["key"] == "acme@example.com"
    assert db.committed


@pytest.mark.asyncio
async def test_purge_deletes_old_windows_and_returns_count():
    db = FakeSession([(is_purge, WithRowcount([], 42))])
    deleted = await purge_expired(db, max_window_seconds=3600)
    assert deleted == 42
    assert db.committed


@pytest.mark.asyncio
async def test_peek_count_returns_zero_when_no_row_exists():
    db = FakeSession([(is_peek, [])])
    assert await peek_count(db, "new-account@example.com", window_seconds=300) == 0


@pytest.mark.asyncio
async def test_peek_count_does_not_increment_or_commit():
    db = FakeSession([(is_peek, [FakeRow(count=5)])])
    count = await peek_count(db, "acme@example.com", window_seconds=300)
    assert count == 5
    assert not db.sql_calls_matching("INSERT INTO rate_limit_counters")
    assert not db.committed


@pytest.mark.asyncio
async def test_increment_returns_new_count_and_commits():
    db = FakeSession([(is_upsert, [1])])
    count = await increment(db, "acme@example.com", window_seconds=300)
    assert count == 1
    assert db.committed
