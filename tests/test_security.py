"""Tests for the security primitives: login throttle (F1) and TOTP (F2)."""

import importlib
import time

from server.security import (
    LoginThrottle,
    generate_totp_secret,
    verify_totp,
    totp_uri,
    _hotp,
)


# ---- F1: login throttle ---------------------------------------------------
def test_throttle_locks_after_limit():
    t = LoginThrottle(max_attempts=3, lockout_seconds=100)
    assert t.retry_after("amy") == 0
    assert t.record_failure("amy") == 0      # 1
    assert t.record_failure("amy") == 0      # 2
    assert t.record_failure("amy") == 100    # 3 -> locked
    assert t.retry_after("amy") > 0


def test_throttle_reset_clears():
    t = LoginThrottle(max_attempts=2, lockout_seconds=100)
    t.record_failure("bob")
    t.record_failure("bob")
    assert t.retry_after("bob") > 0
    t.reset("bob")
    assert t.retry_after("bob") == 0


def test_throttle_lapses(monkeypatch):
    t = LoginThrottle(max_attempts=2, lockout_seconds=5)
    base = [1000.0]
    monkeypatch.setattr(t, "_now", lambda: base[0])
    t.record_failure("z")            # 1
    t.record_failure("z")            # 2 -> locked until 1005
    assert t.retry_after("z") > 0
    base[0] = 1006.0                 # lockout has lapsed
    assert t.retry_after("z") == 0
    # state was cleared: a fresh failure starts the count over (no immediate lock)
    assert t.record_failure("z") == 0


def test_separate_keys_independent():
    t = LoginThrottle(max_attempts=1, lockout_seconds=100)
    t.record_failure("a")
    assert t.retry_after("a") > 0
    assert t.retry_after("b") == 0


# ---- F2: TOTP -------------------------------------------------------------
def test_totp_roundtrip():
    secret = generate_totp_secret()
    counter = int(time.time() // 30)
    code = _hotp(secret, counter)
    assert verify_totp(secret, code)
    assert len(code) == 6 and code.isdigit()


def test_totp_rejects_wrong_code():
    secret = generate_totp_secret()
    far = _hotp(secret, int(time.time() // 30) + 1000)  # out of drift window
    assert not verify_totp(secret, far)
    assert not verify_totp(secret, "")
    assert not verify_totp(secret, "abc")
    assert not verify_totp("", "123456")


def test_totp_drift_window():
    secret = generate_totp_secret()
    counter = int(time.time() // 30)
    # code from the previous step still accepted within window=1
    assert verify_totp(secret, _hotp(secret, counter - 1))
    # but two steps away is rejected
    assert not verify_totp(secret, _hotp(secret, counter - 5))


def test_totp_uri_shape():
    uri = totp_uri("ABC234", "amy", issuer="fastmodel")
    assert uri.startswith("otpauth://totp/")
    assert "secret=ABC234" in uri and "issuer=fastmodel" in uri


# ---- account integration: reset codes + totp enable/disable ---------------
def _fresh_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_USERNAME", "boss")
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import server.config as cfg
    importlib.reload(cfg)
    import server.security as sec
    importlib.reload(sec)
    import server.accounts as acc
    importlib.reload(acc)
    return acc


def test_reset_code_flow(tmp_path, monkeypatch):
    acc = _fresh_accounts(tmp_path, monkeypatch)
    store = acc.AccountStore()
    store.create("amy", "oldpw", role="member")
    code = store.issue_reset_code("amy")
    assert code and len(code) == 8
    # wrong code rejected
    import pytest
    with pytest.raises(ValueError):
        store.redeem_reset("amy", "ZZZZZZZZ", "newpw")
    # right code works, and old password no longer authenticates
    store.redeem_reset("amy", code, "newpw")
    assert store.authenticate("amy", "newpw")
    assert not store.authenticate("amy", "oldpw")
    # code is one-time
    with pytest.raises(ValueError):
        store.redeem_reset("amy", code, "another")
    # public view no longer shows a pending reset
    assert acc.public_view(store.get("amy"))["reset_pending"] is False


def test_reset_code_expiry(tmp_path, monkeypatch):
    acc = _fresh_accounts(tmp_path, monkeypatch)
    acc.RESET_CODE_TTL_SECONDS = -1  # already expired
    store = acc.AccountStore()
    store.create("amy", "oldpw", role="member")
    code = store.issue_reset_code("amy")
    import pytest
    with pytest.raises(ValueError):
        store.redeem_reset("amy", code, "newpw")


def test_totp_enable_disable(tmp_path, monkeypatch):
    acc = _fresh_accounts(tmp_path, monkeypatch)
    store = acc.AccountStore()
    store.create("amy", "pw", role="member")
    assert acc.public_view(store.get("amy"))["totp_enabled"] is False

    info = store.begin_totp("amy")
    assert "secret" in info and info["otpauth_uri"].startswith("otpauth://")
    # not enabled until confirmed
    assert store.get("amy").get("totp_enabled") in (False, None)

    import pytest
    far = _hotp(info["secret"], int(time.time() // 30) + 1000)  # out of window
    with pytest.raises(ValueError):
        store.enable_totp("amy", far)

    good = _hotp(info["secret"], int(time.time() // 30))
    store.enable_totp("amy", good)
    user = store.get("amy")
    assert user["totp_enabled"] and store.verify_totp_code(user, good)

    store.disable_totp("amy")
    assert store.get("amy")["totp_enabled"] is False
    assert "totp_secret" not in store.get("amy")
