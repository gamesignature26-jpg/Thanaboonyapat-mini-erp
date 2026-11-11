"""Quotation draft tests — independent of the existing sale/document ledger.

These deliberately fail until the new quotations feature is implemented.
"""

from conftest import login, post

from erp.models import Customer, Product, Sale, StockMovement, db


def quotation(pid, cid, key="synthetic-quotation-idempotency-0001", **overrides):
    return {
        "request_key": key,
        "customer_id": cid,
        "vat_price_mode": "exclusive",
        "lines": [{"product_id": pid, "quantity": 2}],
        **overrides,
    }


def test_quotation_requires_login_and_role(client, seeded):
    _token, pid, cid = seeded
    unauthenticated = client.application.test_client()
    assert unauthenticated.get("/api/quotations").status_code == 401
    assert unauthenticated.post("/api/quotations", json=quotation(pid, cid)).status_code == 401
    warehouse = login(client, "warehouse")
    assert client.get("/api/quotations").status_code == 403
    assert post(client, warehouse, "/api/quotations", quotation(pid, cid)).status_code == 403
    login(client, "accountant")
    assert client.get("/api/quotations").status_code == 200


def test_quotation_does_not_move_stock_create_sale_or_payment(seeded, client, app):
    token, pid, cid = seeded
    created = post(client, token, "/api/quotations", quotation(pid, cid))
    assert created.status_code == 201
    assert created.json["number"].startswith("QT-DRAFT-")
    detail = client.get(f'/api/quotations/{created.json["id"]}')
    assert detail.status_code == 200
    assert detail.json["status"] == "draft"
    assert detail.json["total"] == "214.00"
    assert detail.json["vat"] == "14.00"
    assert detail.json["lines"][0]["name"] == "Synthetic item"
    assert detail.json["notice"] == "QUOTATION DRAFT - NOT A TAX INVOICE"
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10
        assert db.session.scalar(db.select(Sale.id)) is None
        assert db.session.scalar(db.select(StockMovement.id).where(StockMovement.delta < 0)) is None


def test_idempotent_quote_and_conflicting_reuse(seeded, client, app):
    token, pid, cid = seeded
    req = quotation(pid, cid)
    first = post(client, token, "/api/quotations", req)
    second = post(client, token, "/api/quotations", req)
    conflict = post(client, token, "/api/quotations", {**req, "lines": [{"product_id": pid, "quantity": 3}]})
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json["duplicate"] is True
    assert second.json["id"] == first.json["id"]
    assert conflict.status_code == 409
    assert len(client.get("/api/quotations").json["items"]) == 1


def test_quote_snapshots_customer_and_customer_specific_price(seeded, client, app):
    token, pid, cid = seeded
    updated = post(client, token, "/api/extended/prices", {"customer_id": cid, "product_id": pid, "price": "80.00"})
    assert updated.status_code == 200
    made = post(client, token, "/api/quotations", quotation(pid, cid, vat_price_mode="inclusive"))
    assert made.status_code == 201
    detail_url = f'/api/quotations/{made.json["id"]}'
    assert client.get(detail_url).json["total"] == "160.00"
    assert client.get(detail_url).json["lines"][0]["unit_price"] == "80.00"
    with app.app_context():
        db.session.get(Customer, cid).name = "Changed after quotation"
        db.session.get(Product, pid).name = "Changed after quotation"
        db.session.commit()
    detail = client.get(detail_url).json
    assert detail["customer"]["name"] == "Synthetic customer"
    assert detail["lines"][0]["name"] == "Synthetic item"


def test_quote_rejects_invalid_data_without_mutating_stock(seeded, client, app):
    token, pid, cid = seeded
    bad = [
        quotation(pid, cid, request_key="short"),
        quotation(pid, cid, lines=[]),
        quotation(pid, cid, lines=[{"product_id": pid, "quantity": 0}]),
        quotation(pid, cid, lines=[{"product_id": pid, "quantity": 1}] * 2),
        quotation(pid, cid, vat_price_mode="invalid"),
        quotation(pid, cid, expected_total="0.00"),
    ]
    assert [post(client, token, "/api/quotations", row).status_code for row in bad] == [400, 400, 400, 400, 400, 409]
    assert client.get("/api/quotations").json["items"] == []
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10


def test_quote_listing_and_print_preview_are_private(seeded, client):
    token, pid, cid = seeded
    made = post(client, token, "/api/quotations", quotation(pid, cid))
    assert made.status_code == 201
    url = f'/api/quotations/{made.json["id"]}/print'
    page = client.get(url)
    assert page.status_code == 200
    assert "QUOTATION DRAFT" in page.get_data(as_text=True)
    assert "Synthetic customer" in page.get_data(as_text=True)
    assert "ข้อมูลตัวอย่าง" in page.get_data(as_text=True)
    assert client.get("/api/quotations?limit=0").status_code == 400
    assert client.get("/api/quotations?before=abc").status_code == 400
    staff = client.application.test_client()
    login(staff, "warehouse")
    assert staff.get(url).status_code == 403
