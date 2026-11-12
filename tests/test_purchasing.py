"""Synthetic-only supplier purchasing and inventory receiving integration contracts."""

import pytest
from conftest import login, post
from test_concurrency import concurrent_requests

from erp.models import Product, Sale, StockMovement, db


def supplier(client, token, name="Synthetic Water Supplier"):
    r = post(client, token, "/api/suppliers", {"name": name, "tax_id": "0123456789012", "address": "Synthetic site"})
    assert r.status_code == 201
    return r.json["id"]


def purchase(supplier_id, pid, key="synthetic-purchase-order-00001"):
    return {
        "request_key": key,
        "supplier_id": supplier_id,
        "note": "Synthetic water delivery",
        "lines": [{"product_id": pid, "quantity": 4, "unit_cost": "41.50"}],
    }


def test_supplier_permissions_and_validation(client, seeded):
    token, pid, _cid = seeded
    anon = client.application.test_client()
    assert anon.get("/api/suppliers").status_code == 401
    assert anon.get("/api/purchases").status_code == 401
    assert post(client, token, "/api/suppliers", {"name": ""}).status_code == 400
    assert post(client, token, "/api/suppliers", {"name": "A", "tax_id": "invalid"}).status_code == 400
    sid = supplier(client, token)
    assert client.get("/api/suppliers").json["items"][0]["name"] == "Synthetic Water Supplier"
    sales = login(client, "sales")
    assert client.get("/api/suppliers").status_code == 403
    assert post(client, sales, "/api/suppliers", {"name": "Unauthorized"}).status_code == 403
    warehouse = login(client, "warehouse")
    assert client.get("/api/suppliers").status_code == 200
    assert post(client, warehouse, "/api/purchases", purchase(sid, pid)).status_code == 403
    accountant = login(client, "accountant")
    assert client.get("/api/purchases").status_code == 200
    assert post(client, accountant, "/api/suppliers", {"name": "Other vendor"}).status_code == 201


def test_draft_purchase_is_immutable_and_has_no_stock_or_financial_side_effects(seeded, client, app):
    token, pid, _cid = seeded
    sid = supplier(client, token)
    made = post(client, token, "/api/purchases", purchase(sid, pid))
    assert made.status_code == 201
    row = client.get(f"/api/purchases/{made.json['id']}").json
    assert row["number"] == "PO-DRAFT-000001"
    assert row["status"] == "draft"
    assert row["subtotal_cost"] == "166.00"
    assert row["notice"] == "PURCHASE INTAKE - NOT A TAX INVOICE"
    assert row["supplier"]["name"] == "Synthetic Water Supplier"
    assert row["lines"][0]["unit_cost"] == "41.50"
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10
        assert db.session.scalar(db.select(Sale.id)) is None
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 1


def test_purchase_idempotency_and_conflicting_reuse(seeded, client, app):
    token, pid, _cid = seeded
    sid = supplier(client, token)
    body = purchase(sid, pid)
    first = post(client, token, "/api/purchases", body)
    again = post(client, token, "/api/purchases", body)
    changed = post(client, token, "/api/purchases", {**body, "lines": [{**body["lines"][0], "quantity": 5}]})
    assert first.status_code == 201
    assert again.status_code == 200 and again.json["duplicate"] is True
    assert again.json["id"] == first.json["id"]
    assert changed.status_code == 409
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10


def test_receiving_adds_stock_only_once_and_keeps_cost_snapshot(seeded, client, app):
    token, pid, _cid = seeded
    sid = supplier(client, token)
    order = post(client, token, "/api/purchases", purchase(sid, pid))
    order_id = order.json["id"]
    with app.app_context():
        row = db.session.get(Product, pid)
        row.name = "Updated name after PO"
        row.price = 140
        db.session.commit()
    warehouse = login(client, "warehouse")
    note = {"receipt_note": "Counted four sealed packs in synthetic test"}
    first = post(client, warehouse, f"/api/purchases/{order_id}/receive", note)
    second = post(client, warehouse, f"/api/purchases/{order_id}/receive", note)
    changed = post(client, warehouse, f"/api/purchases/{order_id}/receive", {"receipt_note": "Different"})
    assert first.status_code == 200
    assert first.json["status"] == "received" and first.json["duplicate"] is False
    assert second.status_code == 200 and second.json["duplicate"] is True
    assert changed.status_code == 409
    detail = client.get(f"/api/purchases/{order_id}").json
    assert detail["lines"][0]["name"] == "Synthetic item"
    assert detail["lines"][0]["unit_cost"] == "41.50"
    assert detail["received_by"] is not None
    assert detail["received_at"] is not None
    with app.app_context():
        assert db.session.get(Product, pid).stock == 14
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 2
        assert db.session.scalar(db.select(Sale.id)) is None


def test_invalid_purchase_quantities_and_prices_never_move_stock(seeded, client, app):
    token, pid, _cid = seeded
    sid = supplier(client, token)
    base = purchase(sid, pid)
    cases = [
        {**base, "request_key": "short"},
        {**base, "lines": []},
        {**base, "lines": [base["lines"][0], base["lines"][0]]},
        {**base, "lines": [{**base["lines"][0], "quantity": 0}]},
        {**base, "lines": [{**base["lines"][0], "unit_cost": "-3.00"}]},
        {**base, "lines": [{**base["lines"][0], "unit_cost": "12.345"}]},
        {**base, "lines": [{**base["lines"][0], "unit_cost": 3.25}]},
    ]
    assert [post(client, token, "/api/purchases", x).status_code for x in cases] == [400] * 7
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10


def test_purchase_list_page_and_roles(seeded, client):
    token, pid, _cid = seeded
    sid = supplier(client, token)
    for key in ("synthetic-purchasing-one-00001", "synthetic-purchasing-two-00002"):
        assert post(client, token, "/api/purchases", purchase(sid, pid, key)).status_code == 201
    first = client.get("/api/purchases?limit=1").json
    assert len(first["items"]) == 1 and first["next_before"] is not None
    next_page = client.get(f"/api/purchases?limit=1&before={first['next_before']}").json
    assert next_page["items"][0]["id"] != first["items"][0]["id"]
    assert client.get("/api/purchases?limit=0").status_code == 400
    assert client.get("/api/purchases?before=foo").status_code == 400
    assert client.get("/api/suppliers?limit=0").status_code == 400
    assert client.get("/api/purchases/123456").status_code == 404
    login(client, "sales")
    assert client.get("/api/purchases").status_code == 403
    login(client, "warehouse")
    assert client.get("/api/purchases").status_code == 200


def test_purchase_receipt_rejects_bad_request_and_unauthorized_roles(seeded, client, app):
    token, pid, _cid = seeded
    sid = supplier(client, token)
    order = post(client, token, "/api/purchases", purchase(sid, pid)).json["id"]
    assert post(client, token, f"/api/purchases/{order}/receive", {"receipt_note": ""}).status_code == 400
    assert post(client, token, f"/api/purchases/{order}/receive", {"receipt_note": "ok", "extra": 1}).status_code == 400
    sales = login(client, "sales")
    assert post(client, sales, f"/api/purchases/{order}/receive", {"receipt_note": "No"}).status_code == 403
    accountant = login(client, "accountant")
    assert post(client, accountant, f"/api/purchases/{order}/receive", {"receipt_note": "No"}).status_code == 403
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10


def test_postgres_concurrent_receiving_cannot_double_stock(seeded, client, app):
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        pytest.skip("Row locks require PostgreSQL")
    token, pid, _cid = seeded
    sid = supplier(client, token)
    order_id = post(client, token, "/api/purchases", purchase(sid, pid)).json["id"]
    responses = concurrent_requests(
        app,
        f"/api/purchases/{order_id}/receive",
        [
            {"receipt_note": "Synthetic receiving team A"},
            {"receipt_note": "Synthetic receiving team B"},
        ],
    )
    assert responses == [200, 409]
    with app.app_context():
        assert db.session.get(Product, pid).stock == 14
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 2
