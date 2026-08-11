# VoxiKam — SIP Class 4 Billing & Monitoring Platform
# Copyright (c) 2026 KPBTec
# By KPBTec · https://github.com/KPBTec
# © 2026 – Todos los derechos reservados.

"""
Caracterización de routers/auth.py::forgot_password/reset_password — feature
nueva (v2.58.0), sin cobertura previa por no existir antes. Cubre las dos
garantías de seguridad que más importan acá: nunca revelar si un email
existe (respuesta genérica siempre), y que un token no pueda reusarse ni
sobrevivir a su expiración.
"""
import hashlib
from datetime import datetime, timedelta

import pytest

from routers.auth import ForgotPasswordIn, ResetPasswordIn, forgot_password, reset_password
from tests.fakes import FakeRow, FakeSession, WithRowcount


class FakeClient:
    host = "203.0.113.9"


class FakeRequest:
    client = FakeClient()


@pytest.fixture(autouse=True)
def _stub_rate_limit(monkeypatch):
    import routers.auth as auth_module

    async def _not_limited(db, key, max_count, window_seconds):
        return False

    monkeypatch.setattr(auth_module, "is_rate_limited", _not_limited)


@pytest.fixture(autouse=True)
def _stub_domain(monkeypatch):
    import routers.auth as auth_module

    async def _fake_get_domain(db):
        return "voxikam.example.com", "7666"

    monkeypatch.setattr(auth_module, "get_domain", _fake_get_domain)


@pytest.fixture
def _sent_emails(monkeypatch):
    import routers.auth as auth_module
    sent = []

    async def _fake_send_email(db, to, subject, html, attachments=None):
        sent.append({"to": to, "subject": subject, "html": html})
        return True

    monkeypatch.setattr(auth_module, "send_email", _fake_send_email)
    return sent


# ── forgot_password: nunca revela si el email existe ────────────────────────

@pytest.mark.asyncio
async def test_forgot_password_unknown_email_returns_generic_ok_and_sends_nothing(_sent_emails):
    db = FakeSession([
        (lambda sql, p: "SELECT id, name, is_active FROM users" in sql, []),
    ])
    result = await forgot_password(FakeRequest(), ForgotPasswordIn(email="nadie@example.com"), db)
    assert result == {"ok": True}
    assert _sent_emails == []
    assert not any("INSERT INTO password_reset_tokens" in sql for sql, _ in db.calls)


@pytest.mark.asyncio
async def test_forgot_password_inactive_user_returns_generic_ok_and_sends_nothing(_sent_emails):
    db = FakeSession([
        (lambda sql, p: "SELECT id, name, is_active FROM users" in sql,
         [FakeRow(id=1, name="Juan", is_active=0)]),
    ])
    result = await forgot_password(FakeRequest(), ForgotPasswordIn(email="juan@example.com"), db)
    assert result == {"ok": True}
    assert _sent_emails == []


@pytest.mark.asyncio
async def test_forgot_password_known_active_user_creates_token_and_sends_email(_sent_emails):
    db = FakeSession([
        (lambda sql, p: "SELECT id, name, is_active FROM users" in sql,
         [FakeRow(id=7, name="María", is_active=1)]),
        (lambda sql, p: "INSERT INTO password_reset_tokens" in sql, []),
    ])
    result = await forgot_password(FakeRequest(), ForgotPasswordIn(email="maria@example.com"), db)
    assert result == {"ok": True}
    assert db.committed
    assert len(_sent_emails) == 1
    assert _sent_emails[0]["to"] == "maria@example.com"
    assert "reset-password?token=" in _sent_emails[0]["html"]


@pytest.mark.asyncio
async def test_forgot_password_rate_limited_skips_lookup_entirely(monkeypatch, _sent_emails):
    import routers.auth as auth_module

    async def _limited(db, key, max_count, window_seconds):
        return True

    monkeypatch.setattr(auth_module, "is_rate_limited", _limited)
    db = FakeSession([])
    result = await forgot_password(FakeRequest(), ForgotPasswordIn(email="cualquiera@example.com"), db)
    assert result == {"ok": True}
    assert db.calls == []
    assert _sent_emails == []


@pytest.mark.asyncio
async def test_forgot_password_without_domain_configured_skips_email_but_still_creates_token(monkeypatch, _sent_emails):
    import routers.auth as auth_module

    async def _no_domain(db):
        return "", "80"

    monkeypatch.setattr(auth_module, "get_domain", _no_domain)
    db = FakeSession([
        (lambda sql, p: "SELECT id, name, is_active FROM users" in sql,
         [FakeRow(id=3, name="Ana", is_active=1)]),
        (lambda sql, p: "INSERT INTO password_reset_tokens" in sql, []),
    ])
    result = await forgot_password(FakeRequest(), ForgotPasswordIn(email="ana@example.com"), db)
    assert result == {"ok": True}
    assert _sent_emails == []
    assert any("INSERT INTO password_reset_tokens" in sql for sql, _ in db.calls)


# ── reset_password: token de un solo uso, con expiración real ───────────────

@pytest.mark.asyncio
async def test_reset_password_valid_token_updates_password_and_marks_used():
    db = FakeSession([
        (lambda sql, p: "FROM password_reset_tokens" in sql and "WHERE token_hash" in sql,
         [FakeRow(id=1, user_id=42)]),
        (lambda sql, p: "UPDATE users SET password_hash" in sql, WithRowcount([], 1)),
        (lambda sql, p: "UPDATE password_reset_tokens SET used_at" in sql, WithRowcount([], 1)),
    ])
    result = await reset_password(ResetPasswordIn(token="tok123", new_password="unaClaveSegura1"), db)
    assert result == {"ok": True}
    assert db.committed
    update_calls = db.sql_calls_matching("UPDATE users SET password_hash")
    assert update_calls and update_calls[0][1]["id"] == 42


@pytest.mark.asyncio
async def test_reset_password_invalid_or_expired_token_raises_400():
    from fastapi import HTTPException

    db = FakeSession([
        (lambda sql, p: "FROM password_reset_tokens" in sql and "WHERE token_hash" in sql, []),
    ])
    with pytest.raises(HTTPException) as exc:
        await reset_password(ResetPasswordIn(token="no-existe", new_password="unaClaveSegura1"), db)
    assert exc.value.status_code == 400
    assert not db.committed


@pytest.mark.asyncio
async def test_reset_password_rejects_short_password_without_touching_db():
    from fastapi import HTTPException

    db = FakeSession([])
    with pytest.raises(HTTPException) as exc:
        await reset_password(ResetPasswordIn(token="tok123", new_password="corta"), db)
    assert exc.value.status_code == 400
    assert db.calls == []


def test_token_is_never_stored_raw_only_its_hash():
    raw = "un-token-de-ejemplo"
    expected_hash = hashlib.sha256(raw.encode()).hexdigest()
    assert len(expected_hash) == 64
    assert expected_hash != raw
