"""Short-lived recovery links; no passwords or recovery tokens are logged."""

import hashlib
import os
import secrets
import time

from flask import abort, session
from flask_wtf.csrf import generate_csrf
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from .models import User, db


def version(user):
    return hashlib.sha256(user.password_hash.encode()).hexdigest()


def install_recovery(app):
    from . import data, g, roles

    signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="erp-password-recovery-v1")
    limiter = app.extensions["erp_limiter"]

    @app.post("/users/<int:user_id>/recovery")
    @roles()
    @limiter.limit("5 per minute")
    def issue_recovery(user_id):
        body = data()
        password = body.get("current_password")
        if (
            not isinstance(password, str)
            or len(password) > 128
            or not check_password_hash(g.user.password_hash, password)
        ):
            abort(403, "กรุณายืนยันรหัสผ่านเจ้าของให้ถูกต้อง")
        user = db.get_or_404(User, user_id)
        if not user.active:
            abort(409, "ต้องอนุมัติบัญชีก่อนออกลิงก์กู้คืน")
        token = signer.dumps({"uid": user.id, "version": version(user)})
        return {"token": token, "username": user.username, "expires_in": 900}, 201

    @app.post("/auth/recover")
    @limiter.limit("5 per minute; 20 per hour")
    def recover():
        body = data()
        token = body.get("token")
        username = body.get("username")
        password = body.get("password")
        if (
            not isinstance(token, str)
            or not 1 <= len(token) <= 2048
            or not isinstance(username, str)
            or len(username) > 80
        ):
            abort(400, "ข้อมูลกู้คืนไม่ถูกต้อง")
        if not isinstance(password, str) or not 12 <= len(password) <= 128 or password != body.get("confirmation"):
            abort(400, "รหัสใหม่ต้องยาว 12–128 ตัวอักษร และยืนยันตรงกัน")
        # Lock the account so two simultaneous uses cannot both succeed.
        user = db.session.scalar(db.select(User).where(User.username == username).with_for_update())
        valid = False
        if user and user.active:
            try:
                payload = signer.loads(token, max_age=900)
                valid = payload.get("uid") == user.id and secrets.compare_digest(
                    payload.get("version", ""), version(user)
                )
            except (BadSignature, AttributeError, TypeError):
                pass
            # Emergency owner access is provisioned by the authenticated operator.
            # It is bound to the current password and expires after 15 minutes.
            expected = os.getenv("OWNER_RECOVERY_TOKEN_HASH", "")
            try:
                expires = int(os.getenv("OWNER_RECOVERY_EXPIRES_AT", "0"))
            except ValueError:
                expires = 0
            emergency = (
                user.role == "admin"
                and user.username == os.getenv("OWNER_RECOVERY_USERNAME")
                and time.time() < expires
                and secrets.compare_digest(os.getenv("OWNER_RECOVERY_PASSWORD_VERSION", ""), version(user))
                and bool(expected)
                and secrets.compare_digest(expected, hashlib.sha256(token.encode()).hexdigest())
            )
            valid = valid or emergency
        if not valid:
            abort(400, "ลิงก์ไม่ถูกต้อง หมดอายุ หรือถูกใช้แล้ว กรุณาขอลิงก์ใหม่")
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        session.clear()
        return {"message": "ตั้งรหัสใหม่แล้ว กรุณาเข้าสู่ระบบ", "csrf_token": generate_csrf()}
