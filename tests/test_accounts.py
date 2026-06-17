import importlib


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("APP_USERNAME", "boss")
    monkeypatch.setenv("APP_PASSWORD", "secret")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    import server.config as cfg
    importlib.reload(cfg)
    import server.accounts as acc
    importlib.reload(acc)
    return acc


def test_password_hash_roundtrip(tmp_path, monkeypatch):
    acc = _fresh(tmp_path, monkeypatch)
    h = acc.hash_password("hunter2")
    assert acc.verify_password("hunter2", h)
    assert not acc.verify_password("wrong", h)


def test_bootstrap_admin_and_caps(tmp_path, monkeypatch):
    acc = _fresh(tmp_path, monkeypatch)
    store = acc.AccountStore()
    boss = store.authenticate("boss", "secret")
    assert boss and boss["role"] == "admin" and boss["protected"]
    # admin has all capabilities implicitly
    assert acc.has_cap(boss, "upload") and acc.has_cap(boss, "manage_users")


def test_member_capabilities_and_protection(tmp_path, monkeypatch):
    acc = _fresh(tmp_path, monkeypatch)
    store = acc.AccountStore()
    m = store.create("amy", "pw", role="member", person="AMY", capabilities=["upload"])
    assert acc.has_cap(m, "upload")
    assert not acc.has_cap(m, "manage_users")
    # public view hides the hash, shows effective caps
    pub = acc.public_view(m)
    assert "password_hash" not in pub and pub["person"] == "AMY"

    # the bootstrap admin cannot be deleted or demoted
    import pytest
    with pytest.raises(ValueError):
        store.delete("boss")
    with pytest.raises(ValueError):
        store.update("boss", role="member")


def test_persistence_across_instances(tmp_path, monkeypatch):
    acc = _fresh(tmp_path, monkeypatch)
    acc.AccountStore().create("amy", "pw", person="AMY")
    # A brand-new store instance (simulating a restart) still has the account.
    again = acc.AccountStore()
    assert again.authenticate("amy", "pw") is not None
