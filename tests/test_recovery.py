import hashlib
import time

from conftest import login, post
from itsdangerous import URLSafeTimedSerializer

from erp.models import User, db
from erp.recovery import version


def account(app, name):
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == name))
        return user.id, version(user)


def test_staff_recovery_permissions_single_use_and_session_revocation(client, app):
    staff_id, _ = account(app, "sales")
    token = login(client, "sales")
    assert (
        post(client, token, f"/users/{staff_id}/recovery", {"current_password": "synthetic-password-only"}).status_code
        == 403
    )
    owner = app.test_client()
    owner_csrf = login(owner)
    path = f"/users/{staff_id}/recovery"
    assert post(owner, owner_csrf, path, {"current_password": "incorrect"}).status_code == 403
    result = post(owner, owner_csrf, path, {"current_password": "synthetic-password-only"})
    assert result.status_code == 201
    visitor = app.test_client()
    csrf = visitor.get("/auth/csrf").json["csrf_token"]
    body = {
        "username": "sales",
        "token": result.json["token"],
        "password": "new-synthetic-password",
        "confirmation": "new-synthetic-password",
    }
    assert visitor.post("/auth/recover", json=body).status_code == 400
    assert post(visitor, csrf, "/auth/recover", {**body, "token": "forged"}).status_code == 400
    assert post(visitor, csrf, "/auth/recover", {**body, "username": "admin"}).status_code == 400
    assert post(visitor, csrf, "/auth/recover", {**body, "confirmation": "mismatch"}).status_code == 400
    response = post(visitor, csrf, "/auth/recover", body)
    assert response.status_code == 200
    assert client.get("/auth/me").status_code == 401
    csrf = response.json["csrf_token"]
    assert post(visitor, csrf, "/auth/recover", body).status_code == 400
    assert (
        post(visitor, csrf, "/auth/login", {"username": "sales", "password": "new-synthetic-password"}).status_code
        == 200
    )


def test_owner_emergency_recovery_expires_and_is_single_use(client, app, monkeypatch):
    _, password_version = account(app, "admin")
    monkeypatch.setenv("OWNER_RECOVERY_USERNAME", "admin")
    monkeypatch.setenv("OWNER_RECOVERY_TOKEN_HASH", hashlib.sha256(b"synthetic-recovery-code").hexdigest())
    monkeypatch.setenv("OWNER_RECOVERY_PASSWORD_VERSION", password_version)
    monkeypatch.setenv("OWNER_RECOVERY_EXPIRES_AT", str(int(time.time()) - 1))
    csrf = client.get("/auth/csrf").json["csrf_token"]
    body = {
        "username": "admin",
        "token": "synthetic-recovery-code",
        "password": "new-owner-password",
        "confirmation": "new-owner-password",
    }
    assert post(client, csrf, "/auth/recover", body).status_code == 400
    monkeypatch.setenv("OWNER_RECOVERY_EXPIRES_AT", str(int(time.time()) + 900))
    response = post(client, csrf, "/auth/recover", body)
    assert response.status_code == 200
    assert post(client, response.json["csrf_token"], "/auth/recover", body).status_code == 400


def test_expired_signed_link(client, app, monkeypatch):
    uid, password_version = account(app, "sales")
    signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="erp-password-recovery-v1")
    with monkeypatch.context() as old_clock:
        old_clock.setattr("itsdangerous.timed.time.time", lambda: time.time() - 1000)
        # Use a fixed timestamp to avoid recursively invoking the patched clock.
        old_clock.setattr("itsdangerous.timed.time.time", lambda: 1)
        token = signer.dumps({"uid": uid, "version": password_version})
    csrf = client.get("/auth/csrf").json["csrf_token"]
    body = {"username": "sales", "token": token, "password": "new-staff-password", "confirmation": "new-staff-password"}
    assert post(client, csrf, "/auth/recover", body).status_code == 400
