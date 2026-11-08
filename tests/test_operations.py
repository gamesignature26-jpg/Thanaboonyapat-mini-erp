import base64
import hashlib
import hmac
import io
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import login, post
from PIL import Image

from erp.models import Product, Sale, db
from erp.online import OnlineOrder
from erp.operations import deliver_weekly, week_bounds
from erp.operations_models import EmailContact


def image_bytes():
    out = io.BytesIO()
    Image.new("RGB", (10, 10), "blue").save(out, "PNG")
    return out.getvalue()


def order(client, token, pid, cid):
    response = post(
        client,
        token,
        "/api/online/orders",
        {
            "kind": "wholesale",
            "customer_id": cid,
            "lines": [{"product_id": pid, "quantity": 2, "unit_price": "100.00"}],
            "method": "credit",
            "delivery_mode": "delivery",
            "address": "Synthetic address",
            "phone": "000",
            "driver": "Driver test",
            "idempotency_key": "synthetic-operation-order",
        },
    )
    assert response.status_code == 201
    return response.json["id"]


def test_evidence_private_csrf_duplicate_and_no_payment(client, seeded, app):
    token, pid, cid = seeded
    sid = order(client, token, pid, cid)
    path = "/api/operations/evidence"
    payload = lambda: {"sale_id": str(sid), "file": (io.BytesIO(image_bytes()), "fake-name.png")}
    assert client.post(path, data=payload()).status_code == 400
    result = client.post(path, data=payload(), headers={"X-CSRFToken": token})
    assert result.status_code == 201
    eid = result.json["id"]
    assert client.post(path, data=payload(), headers={"X-CSRFToken": token}).status_code == 409
    assert (
        client.post(
            path,
            data={"sale_id": str(sid), "file": (io.BytesIO(b'<svg onload="alert(1)">'), "bad.jpg")},
            headers={"X-CSRFToken": token},
        ).status_code
        == 400
    )
    outsider = app.test_client()
    login(outsider, "sales")
    assert outsider.get(f"{path}/{eid}").status_code == 403
    assert outsider.get(path).json["items"] == []
    assert app.test_client().get(f"{path}/{eid}").status_code == 401
    download = client.get(f"{path}/{eid}")
    assert download.headers["Content-Type"] == "application/octet-stream"
    assert "attachment" in download.headers["Content-Disposition"]
    assert post(client, token, f"{path}/{eid}/review", {"status": "accepted"}).status_code == 200
    assert post(client, token, f"{path}/{eid}/review", {"status": "accepted"}).status_code == 409
    with app.app_context():
        assert db.session.get(Sale, sid).paid == 0


def test_payroll_sources_advances_and_permissions(client, seeded, app):
    token, pid, cid = seeded
    sid = order(client, token, pid, cid)
    driver = post(
        client,
        token,
        "/api/operations/drivers",
        {"name": "Driver test", "daily_rate": "500.00", "delivery_rate": "30.00"},
    ).json["id"]
    expense = post(
        client,
        token,
        "/api/online/expenses",
        {"amount": "100.00", "category": "fuel", "description": "Driver paid personally", "method": "cash"},
    ).json["id"]
    day = datetime.now(UTC).date().isoformat()

    def entry(kind, key, **extra):
        return post(
            client,
            token,
            "/api/operations/driver-entries",
            {
                "driver_id": driver,
                "day": day,
                "kind": kind,
                "request_key": "synthetic-entry-" + key,
                "note": "Synthetic approved entry",
                **extra,
            },
        )

    assert entry("day", "work").json["amount"] == "500.00"
    assert entry("day", "duplicate").status_code == 409
    assert entry("advance", "advance", amount="200.00").status_code == 201
    assert entry("advance", "advance", amount="200.00").status_code == 409
    assert entry("reimburse", "fuel", expense_id=expense, amount="999.00").json["amount"] == "100.00"
    assert entry("reimburse", "duplicate-fuel", expense_id=expense).status_code == 409
    assert entry("delivery", "trip", sale_id=sid).status_code == 409
    for _ in range(3):
        assert post(client, token, f"/api/online/orders/{sid}/advance", {}).status_code == 200
    assert entry("delivery", "trip", sale_id=sid).json["amount"] == "30.00"
    assert entry("delivery", "duplicate-trip", sale_id=sid).status_code == 409
    report = client.get("/api/operations/weekly?week=" + day).json
    assert report["payroll"][0]["gross_wages"] == "530.00"
    assert report["payroll"][0]["net_payable"] == "430.00"
    staff = app.test_client()
    login(staff, "warehouse")
    assert staff.get("/api/operations/weekly").status_code == 403
    assert staff.get("/api/operations/drivers").status_code == 403


def test_week_uses_bangkok_monday_boundary(client, seeded, app):
    token, pid, cid = seeded
    sid = order(client, token, pid, cid)
    with app.app_context():
        start = week_bounds("2026-11-08")[1]
        assert start == datetime(2026, 11, 1, 17, tzinfo=UTC)
        sale = db.session.get(Sale, sid)
        sale.created_at = start - timedelta(seconds=1)
        db.session.commit()
    assert client.get("/api/operations/weekly?week=2026-11-08").json["sales_including_vat"] == "0.00"
    with app.app_context():
        sale = db.session.get(Sale, sid)
        sale.created_at = start
        db.session.commit()
    assert client.get("/api/operations/weekly?week=2026-11-08").json["sales_including_vat"] == "214.00"
    assert client.get("/api/operations/weekly?week=invalid").status_code == 400


def configure_mail(app):
    app.config.update(
        SMTP_HOST="smtp.example.test",
        SMTP_USERNAME="synthetic",
        SMTP_PASSWORD="synthetic",
        SMTP_FROM="owner@example.test",
        PUBLIC_BASE_URL="https://erp.example.test",
    )


def test_email_verify_single_use_and_weekly_once(client, app, monkeypatch):
    token = login(client)
    configure_mail(app)
    sent = []
    monkeypatch.setattr("erp.operations.send_mail", lambda *args: sent.append(args))
    body = {"email": "owner@example.test", "current_password": "synthetic-password-only", "weekly": True}
    assert post(client, token, "/api/operations/email", {**body, "current_password": "wrong"}).status_code == 403
    assert post(client, token, "/api/operations/email", body).status_code == 202
    assert client.get("/api/operations/email").json["verified"] is False
    verification = sent[0][2].split("#verify-email=")[1]
    assert post(client, token, "/auth/verify-email", {"token": "fake"}).status_code == 400
    assert post(client, token, "/auth/verify-email", {"token": verification}).status_code == 200
    assert post(client, token, "/auth/verify-email", {"token": verification}).status_code == 400
    with app.app_context():
        assert deliver_weekly("2026-11-02")["sent"] == 1
        assert deliver_weekly("2026-11-02")["sent"] == 0
    assert len(sent) == 2
    assert post(client, token, "/api/operations/email/unsubscribe", {}).status_code == 200
    with app.app_context():
        assert deliver_weekly("2026-11-09")["sent"] == 0
    assert client.post("/internal/weekly-report").status_code == 403


def test_email_provider_failure_and_no_staff_financial_subscription(client, app, monkeypatch):
    token = login(client, "sales")
    body = {"email": "staff@example.test", "current_password": "synthetic-password-only", "weekly": False}
    assert (
        post(client, token, "/api/operations/email", {**body, "email": "other,staff@example.test"}).status_code == 400
    )
    assert post(client, token, "/api/operations/email", body).status_code == 503
    configure_mail(app)
    assert post(client, token, "/api/operations/email", {**body, "weekly": True}).status_code == 403

    def fail(*args):
        raise OSError("Synthetic provider unavailable")

    monkeypatch.setattr("erp.operations.send_mail", fail)
    assert post(client, token, "/api/operations/email", body).status_code == 502
    with app.app_context():
        assert db.session.scalar(db.select(EmailContact.id)) is None


def webhook(client, app, events, bad=False):
    app.config["LINE_CHANNEL_SECRET"] = "synthetic-line-secret"
    raw = json.dumps({"events": events}).encode()
    signature = base64.b64encode(hmac.new(b"synthetic-line-secret", raw, hashlib.sha256).digest()).decode()
    return client.post(
        "/integrations/line/webhook",
        data=raw,
        content_type="application/json",
        headers={"X-Line-Signature": "bad" if bad else signature},
    )


@pytest.mark.parametrize(
    "source", [{"type": "user", "userId": "U-test"}, {"type": "group", "userId": "U-test", "groupId": "G-test"}]
)
def test_line_signature_allowlist_duplicate_and_stock_atomicity(client, seeded, app, source):
    token, pid, cid = seeded
    assert (
        post(
            client,
            token,
            "/api/operations/line-senders",
            {"line_user_id": "U-test", "customer_id": cid, "group_id": "G-test"},
        ).status_code
        == 201
    )
    event = {
        "type": "message",
        "webhookEventId": "synthetic-event-1",
        "source": source,
        "message": {"type": "text", "text": "ORDER TEST-001:2"},
    }
    assert webhook(client, app, [event], bad=True).status_code == 403
    assert (
        webhook(
            client, app, [{**event, "source": {"type": "group", "userId": "U-test", "groupId": "wrong"}}]
        ).status_code
        == 200
    )
    assert client.get("/api/operations/line-drafts").json["items"] == []
    assert webhook(client, app, [event, event]).status_code == 200
    assert webhook(client, app, [event]).status_code == 200
    items = client.get("/api/operations/line-drafts").json["items"]
    assert len(items) == 1
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10
    path = f"/api/operations/line-drafts/{items[0]['id']}/accept"
    body = {"address": "Synthetic address", "phone": "000", "driver": "Driver test", "delivery_date": "2026-11-10"}
    result = post(client, token, path, body)
    assert result.status_code == 201
    assert post(client, token, path, body).status_code == 409
    with app.app_context():
        assert db.session.get(Product, pid).stock == 8
        assert db.session.scalar(db.select(OnlineOrder)).sale_id == result.json["id"]
        assert db.session.get(Sale, result.json["id"]).paid == Decimal(0)


def test_line_insufficient_stock_keeps_draft_pending(client, seeded, app):
    token, _pid, cid = seeded
    post(client, token, "/api/operations/line-senders", {"line_user_id": "U-test", "customer_id": cid})
    event = {
        "type": "message",
        "webhookEventId": "test-insufficient",
        "source": {"type": "user", "userId": "U-test"},
        "message": {"type": "text", "text": "ORDER TEST-001:99"},
    }
    assert webhook(client, app, [event]).status_code == 200
    did = client.get("/api/operations/line-drafts").json["items"][0]["id"]
    result = post(
        client,
        token,
        f"/api/operations/line-drafts/{did}/accept",
        {"address": "Test", "phone": "000", "driver": "Test", "delivery_date": "2026-11-10"},
    )
    assert result.status_code == 409
    assert client.get("/api/operations/line-drafts").json["items"][0]["status"] == "pending"
