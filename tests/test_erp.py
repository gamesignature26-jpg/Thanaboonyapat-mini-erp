from decimal import Decimal

import pytest
from conftest import login, post
from sqlalchemy import func

from erp import create_app
from erp.models import Payment, Product, Sale, SaleLine, StockMovement, User, db


def test_configuration_fails_closed():
    with pytest.raises(RuntimeError):
        create_app({"SECRET_KEY": "short"})
    with pytest.raises(RuntimeError):
        create_app({"SECRET_KEY": "x" * 40, "SQLALCHEMY_DATABASE_URI": "sqlite://"})


def test_auth_csrf_and_headers(client):
    assert client.get("/products").status_code == 401
    assert client.post("/auth/login", json={}).status_code == 400
    csrf = client.get("/auth/csrf").json["csrf_token"]
    assert post(client, csrf, "/auth/login", {"username": "absent", "password": "incorrect"}).status_code == 401
    token = login(client)
    assert client.get("/auth/me").json["role"] == "admin"
    assert post(client, token, "/auth/logout", {}).status_code == 204
    assert client.get("/auth/me").status_code == 401
    response = client.get("/health")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "HttpOnly" in client.get("/auth/csrf").headers["Set-Cookie"]


@pytest.mark.parametrize(
    "role,path,body",
    [
        ("sales", "/products", {"sku": "X", "name": "X", "price": "1.00"}),
        ("warehouse", "/customers", {"name": "X", "address": "X"}),
        ("accountant", "/stock/adjustments", {"product_id": 1, "delta": 1, "reason": "X"}),
        ("sales", "/users", {"username": "x", "password": "synthetic-password", "role": "admin"}),
        ("warehouse", "/sales", {"customer_id": 1, "lines": []}),
        ("sales", "/sales/1/payments", {"amount": "1.00", "reference": "X"}),
    ],
)
def test_role_denials(client, role, path, body):
    assert post(client, login(client, role), path, body).status_code == 403


def test_sale_vat_payment_and_snapshots(client, app, seeded):
    token, pid, cid = seeded
    response = post(
        client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 2}], "price": "0.01"}
    )
    assert response.status_code == 201
    assert response.json["subtotal"] == "200.00"
    assert response.json["vat"] == "14.00"
    assert response.json["total"] == "214.00"
    sid = response.json["id"]
    with app.app_context():
        p = db.session.get(Product, pid)
        assert p.stock == 8
        p.name = "Changed name"
        db.session.commit()
    detail = client.get(f"/sales/{sid}").json
    assert detail["lines"][0]["name"] == "Synthetic item"
    response = post(client, token, f"/sales/{sid}/payments", {"amount": "100.00", "reference": "synthetic-ref-1"})
    assert response.json == {"paid": "100.00", "balance": "114.00"}
    assert (
        post(client, token, f"/sales/{sid}/payments", {"amount": "100.00", "reference": "synthetic-ref-1"}).status_code
        == 409
    )
    assert client.get(f"/sales/{sid}").json["paid"] == "100.00"
    assert post(client, token, f"/sales/{sid}/payments", {"amount": "115.00", "reference": "ref-2"}).status_code == 409
    assert (
        post(client, token, f"/sales/{sid}/payments", {"amount": "114.00", "reference": "ref-2"}).json["balance"]
        == "0.00"
    )
    with app.app_context():
        assert db.session.scalar(db.select(func.count()).select_from(Payment)) == 2


def test_insufficient_stock_rolls_back_everything(client, app, seeded):
    token, pid, cid = seeded
    second = post(client, token, "/products", {"sku": "SECOND", "name": "No stock", "price": "1.00"}).json["id"]
    response = post(
        client,
        token,
        "/sales",
        {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 2}, {"product_id": second, "quantity": 1}]},
    )
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10
        for model in (Sale, SaleLine):
            assert db.session.scalar(db.select(func.count()).select_from(model)) == 0
        assert db.session.scalar(db.select(func.count()).select_from(StockMovement)) == 1


@pytest.mark.parametrize("amount", ["-1.00", "NaN", "Infinity", "1.001", "1000000000.00", 100, None, True])
def test_invalid_money(client, seeded, amount):
    token, _, _ = seeded
    assert post(client, token, "/products", {"sku": "BAD", "name": "Bad", "price": amount}).status_code == 400


def test_invalid_quantities_and_duplicate_products(client, seeded):
    token, pid, cid = seeded
    for quantity in (0, -1, True, "1", 1000001):
        assert (
            post(
                client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": quantity}]}
            ).status_code
            == 400
        )
    assert (
        post(
            client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}] * 2}
        ).status_code
        == 400
    )
    assert (
        post(client, token, "/stock/adjustments", {"product_id": pid, "delta": -11, "reason": "Test"}).status_code
        == 409
    )


def test_vat_half_up(client, app, seeded):
    token, pid, cid = seeded
    with app.app_context():
        db.session.get(Product, pid).price = Decimal("0.50")
        db.session.commit()
    response = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]})
    assert response.json["vat"] == "0.04"
    assert response.json["total"] == "0.54"


def test_user_creation_and_disabled_account(client, app):
    token = login(client)
    assert post(client, token, "/users", {"username": "new", "password": "short", "role": "admin"}).status_code == 400
    assert (
        post(
            client, token, "/users", {"username": "new", "password": "synthetic-password", "role": "superuser"}
        ).status_code
        == 400
    )
    assert (
        post(
            client, token, "/users", {"username": "new", "password": "synthetic-password", "role": "sales"}
        ).status_code
        == 201
    )
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.username == "new"))
        assert user.password_hash != "synthetic-password"
        admin = db.session.scalar(db.select(User).where(User.username == "admin"))
        admin.active = False
        db.session.commit()
    assert client.get("/auth/me").status_code == 401


def test_public_registration_requires_admin_approval(client, app):
    csrf = client.get("/auth/csrf").json["csrf_token"]
    response = post(client, csrf, "/auth/register", {"username": "pending-sales", "password": "synthetic-password"})
    assert response.status_code == 202
    with app.app_context():
        pending = db.session.scalar(db.select(User).where(User.username == "pending-sales"))
        assert pending.role == "sales"
        assert pending.active is False
        assert pending.password_hash != "synthetic-password"
    csrf = client.get("/auth/csrf").json["csrf_token"]
    assert (
        post(client, csrf, "/auth/login", {"username": "pending-sales", "password": "synthetic-password"}).status_code
        == 401
    )
    token = login(client)
    listed = client.get("/users").json["items"]
    assert any(item["username"] == "pending-sales" and not item["active"] for item in listed)
    assert post(client, token, f"/users/{pending.id}/activate", {}).json["active"] is True
    other = app.test_client()
    other_csrf = other.get("/auth/csrf").json["csrf_token"]
    assert (
        post(
            other, other_csrf, "/auth/login", {"username": "pending-sales", "password": "synthetic-password"}
        ).status_code
        == 200
    )


def test_admin_can_reset_a_staff_password(client, app):
    token = login(client)
    created = post(client, token, "/users", {"username": "reset-me", "password": "synthetic-password", "role": "sales"})
    assert created.status_code == 201
    assert (
        post(client, token, f"/users/{created.json['id']}/password", {"password": "new-synthetic-password"}).status_code
        == 204
    )
    other = app.test_client()
    csrf = other.get("/auth/csrf").json["csrf_token"]
    assert (
        post(other, csrf, "/auth/login", {"username": "reset-me", "password": "new-synthetic-password"}).status_code
        == 200
    )


def test_login_throttling():
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "synthetic-limiter-test-key-only-32-characters",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "RATELIMIT_ENABLED": True,
        }
    )
    with app.app_context():
        db.create_all()
    client = app.test_client()
    token = client.get("/auth/csrf").json["csrf_token"]
    codes = [
        post(client, token, "/auth/login", {"username": "absent", "password": "wrong"}).status_code for _ in range(6)
    ]
    assert codes == [401, 401, 401, 401, 401, 429]


def test_business_roles_can_complete_sale_and_payment(client, seeded):
    _, pid, cid = seeded
    warehouse = login(client, "warehouse")
    assert (
        post(
            client, warehouse, "/stock/adjustments", {"product_id": pid, "delta": 1, "reason": "Synthetic receipt"}
        ).status_code
        == 200
    )
    sales = login(client, "sales")
    sale = post(client, sales, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]})
    assert sale.status_code == 201
    accountant = login(client, "accountant")
    assert (
        post(
            client,
            accountant,
            f"/sales/{sale.json['id']}/payments",
            {"amount": "107.00", "reference": "role-flow-test"},
        ).json["balance"]
        == "0.00"
    )


def test_conflict_and_malformed_input(client, seeded):
    token, _, _ = seeded
    assert (
        post(client, token, "/products", {"sku": "TEST-001", "name": "Duplicate", "price": "1.00"}).status_code == 409
    )
    assert (
        post(client, token, "/customers", {"name": "Test", "address": "Test", "tax_id": "not-a-tax-id"}).status_code
        == 400
    )
    assert post(client, token, "/customers", []).status_code == 400
    assert post(client, token, "/sales", {"customer_id": 999999, "lines": []}).status_code == 404
    assert client.get("/products").status_code == 200
