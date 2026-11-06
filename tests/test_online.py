"""Integration tests for the online UI/API using the ERP's existing fake-data fixtures."""

from conftest import login, post

from erp.models import Product, Sale, db
from erp.online import OnlineExpense, OnlineOrder


def order_body(pid, cid, key, kind="pos"):
    body = {
        "idempotency_key": key,
        "kind": kind,
        "customer_id": cid,
        "delivery_mode": "pickup",
        "method": "cash",
        "lines": [{"product_id": pid, "quantity": 2}],
    }
    if kind == "wholesale":
        body.update(
            {
                "method": "credit",
                "delivery_mode": "delivery",
                "address": "Synthetic address",
                "phone": "0000000000",
                "driver": "Synthetic driver",
                "delivery_date": "2026-11-11",
                "lines": [{"product_id": pid, "quantity": 2, "unit_price": "90.00"}],
                "discount": "10.00",
                "shipping_fee": "20.00",
            }
        )
    return body


def test_browser_ui_and_protected_api(client):
    page = client.get("/app")
    assert page.status_code == 200
    assert b"Thanabunyapat One" in page.data
    assert "script-src 'self'" in page.headers["Content-Security-Policy"]
    assert client.get("/api/online/dashboard").status_code == 401
    assert client.get("/assets/online/app.js").status_code == 200


def test_pos_sale_is_atomic_and_idempotent(client, app, seeded):
    token, pid, cid = seeded
    body = order_body(pid, cid, "test-pos-idempotent-1234567890")
    first = post(client, token, "/api/online/orders", body)
    assert first.status_code == 201
    assert first.json["total"] == "214.00"
    assert first.json["duplicate"] is False
    second = post(client, token, "/api/online/orders", body)
    assert second.status_code == 200
    assert second.json["duplicate"] is True
    assert first.json["id"] == second.json["id"]
    modified = {**body, "method": "credit"}
    assert post(client, token, "/api/online/orders", modified).status_code == 409
    with app.app_context():
        assert db.session.get(Product, pid).stock == 8
        assert db.session.get(Sale, first.json["id"]).paid == 214
        assert db.session.query(OnlineOrder).count() == 1
    assert client.get("/api/online/dashboard").json["receivable"] == "0.00"


def test_wholesale_delivery_receivable_payment_and_expense(client, app, seeded):
    token, pid, cid = seeded
    body = order_body(pid, cid, "test-wholesale-key-1234567890", "wholesale")
    sale = post(client, token, "/api/online/orders", body)
    assert sale.status_code == 201
    assert sale.json["total"] == "203.30"
    sid = sale.json["id"]
    dashboard = client.get("/api/online/dashboard").json
    assert dashboard["receivable"] == "203.30"
    assert dashboard["pending_delivery"] == 1
    advance = post(client, token, f"/api/online/orders/{sid}/advance", {})
    assert advance.json["status"] == "packing"
    assert len(client.get("/api/online/orders").json["items"]) == 1
    note = client.get(f"/api/online/orders/{sid}")
    assert note.status_code == 200
    assert note.json["lines"][0]["quantity"] == 2
    assert note.json["shipping_fee"] == "20.00"
    paid = post(
        client,
        token,
        f"/api/online/sales/{sid}/payments",
        {"amount": "100.00", "method": "transfer", "reference": "synthetic-onlinepay-123456"},
    )
    assert paid.status_code == 201
    assert paid.json["balance"] == "103.30"
    assert (
        post(
            client,
            token,
            f"/api/online/sales/{sid}/payments",
            {"amount": "100.00", "method": "transfer", "reference": "synthetic-onlinepay-123456"},
        ).status_code
        == 409
    )
    expense = post(
        client,
        token,
        "/api/online/expenses",
        {"amount": "25.00", "category": "Synthetic fuel", "description": "Test only", "method": "cash"},
    )
    assert expense.status_code == 201
    with app.app_context():
        assert db.session.query(OnlineExpense).count() == 1
        assert db.session.get(Product, pid).stock == 8
    assert client.get("/api/online/dashboard").json["expenses_total"] == "25.00"


def test_online_rejects_invalid_and_unauthorized_actions(client, seeded):
    token, pid, cid = seeded
    body = order_body(pid, cid, "test-invalid-order-key-12345678", "wholesale")
    body["discount"] = "1000.00"
    assert post(client, token, "/api/online/orders", body).status_code == 400
    body["discount"] = "0.00"
    body["lines"][0]["quantity"] = 99999
    assert post(client, token, "/api/online/orders", body).status_code == 409
    sales_token = login(client, "sales")
    assert (
        post(
            client,
            sales_token,
            "/api/online/expenses",
            {"amount": "1.00", "category": "x", "description": "x", "method": "cash"},
        ).status_code
        == 403
    )
    warehouse_token = login(client, "warehouse")
    warehouse_dashboard = client.get("/api/online/dashboard").json
    assert warehouse_dashboard["sales_total"] is None
    assert warehouse_dashboard["expenses_total"] is None
    assert (
        post(
            client, warehouse_token, "/api/online/orders", order_body(pid, cid, "test-denied-idempotent-1234567")
        ).status_code
        == 403
    )
