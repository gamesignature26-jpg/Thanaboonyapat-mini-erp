import os

import pytest
from sqlalchemy.engine import make_url
from werkzeug.security import generate_password_hash

from erp import create_app
from erp.models import User, db


@pytest.fixture()
def app():
    uri = os.getenv("TEST_DATABASE_URL", "sqlite://")
    # The PostgreSQL test database must be disposable; never use DATABASE_URL here.
    if uri != "sqlite://" and not (make_url(uri).database or "").endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL database must end with _test; tests erase it")
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "synthetic-test-key-only-32-characters",
            "SQLALCHEMY_DATABASE_URI": uri,
            "RATELIMIT_ENABLED": False,
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
        for role in ("admin", "sales", "warehouse", "accountant"):
            db.session.add(
                User(username=role, password_hash=generate_password_hash("synthetic-password-only"), role=role)
            )
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, role="admin"):
    token = client.get("/auth/csrf").json["csrf_token"]
    response = client.post(
        "/auth/login", json={"username": role, "password": "synthetic-password-only"}, headers={"X-CSRFToken": token}
    )
    assert response.status_code == 200
    return response.json["csrf_token"]


def post(client, token, path, body):
    return client.post(path, json=body, headers={"X-CSRFToken": token})


@pytest.fixture()
def seeded(client):
    token = login(client)
    pid = post(client, token, "/products", {"sku": "TEST-001", "name": "Synthetic item", "price": "100.00"}).json["id"]
    cid = post(client, token, "/customers", {"name": "Synthetic customer", "address": "Test address"}).json["id"]
    assert (
        post(
            client, token, "/stock/adjustments", {"product_id": pid, "delta": 10, "reason": "Test receipt"}
        ).status_code
        == 200
    )
    return token, pid, cid
