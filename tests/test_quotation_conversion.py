"""Quotation state changes and explicit quote-to-sale conversion (synthetic fixtures)."""

from datetime import date, timedelta

from conftest import login, post

from erp.models import Product, Sale, StockMovement, db
from erp.quotations import Quotation


def quote_body(pid, cid, key):
    return {
        "request_key": key,
        "customer_id": cid,
        "vat_price_mode": "exclusive",
        "lines": [{"product_id": pid, "quantity": 2}],
    }


def make_accepted(client, token, pid, cid, key="synthetic-conversion-quote-000001"):
    created = post(client, token, "/api/quotations", quote_body(pid, cid, key))
    assert created.status_code == 201
    qid = created.json["id"]
    sent = post(client, token, f"/api/quotations/{qid}/status", {"status": "sent", "note": "Sent by email"})
    assert sent.status_code == 200
    accepted = post(
        client, token, f"/api/quotations/{qid}/status", {"status": "accepted", "note": "Buyer confirmed by phone"}
    )
    assert accepted.status_code == 200
    return qid


def test_status_transitions_keep_audit_trail_and_reject_invalid_moves(seeded, client, app):
    token, pid, cid = seeded
    created = post(client, token, "/api/quotations", quote_body(pid, cid, "synthetic-status-test-000001"))
    qid = created.json["id"]
    url = f"/api/quotations/{qid}/status"
    assert post(client, token, url, {"status": "accepted", "note": "No send yet"}).status_code == 409
    assert post(client, token, url, {"status": "sent", "note": "Emailed customer"}).status_code == 200
    assert post(client, token, url, {"status": "sent", "note": "Duplicate"}).status_code == 409
    assert post(client, token, url, {"status": "accepted", "note": ""}).status_code == 400
    assert post(client, token, url, {"status": "accepted", "note": "Customer confirmed"}).status_code == 200
    assert post(client, token, url, {"status": "declined", "note": "Reversing accepted"}).status_code == 409
    details = client.get(f"/api/quotations/{qid}").json
    assert details["status"] == "accepted"
    assert [e["to_status"] for e in details["events"]] == ["sent", "accepted"]
    assert [e["from_status"] for e in details["events"]] == ["draft", "sent"]
    assert all(e["actor_id"] > 0 and e["created_at"] for e in details["events"])
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10
        assert db.session.scalar(db.select(Sale.id)) is None


def test_permissions_for_quotation_transitions(seeded, client, app):
    token, pid, cid = seeded
    qid = post(client, token, "/api/quotations", quote_body(pid, cid, "synthetic-role-test-000001")).json["id"]
    accountant = login(client, "accountant")
    assert (
        post(client, accountant, f"/api/quotations/{qid}/status", {"status": "sent", "note": "No"}).status_code == 403
    )
    warehouse = login(client, "warehouse")
    assert post(client, warehouse, f"/api/quotations/{qid}/status", {"status": "sent", "note": "No"}).status_code == 403


def test_conversion_creates_one_credit_sale_and_moves_stock_once(seeded, client, app):
    token, pid, cid = seeded
    qid = make_accepted(client, token, pid, cid)
    endpoint = f"/api/quotations/{qid}/convert"
    payload = {
        "delivery_mode": "delivery",
        "address": "Synthetic warehouse delivery address",
        "phone": "0000000000",
        "driver": "Synthetic driver",
    }
    first = post(client, token, endpoint, payload)
    assert first.status_code == 201
    assert first.json["quote_id"] == qid
    assert first.json["total"] == "214.00"
    sale_id = first.json["sale_id"]
    second = post(client, token, endpoint, payload)
    assert second.status_code == 200
    assert second.json["sale_id"] == sale_id and second.json["duplicate"] is True
    with app.app_context():
        assert db.session.get(Product, pid).stock == 8
        sale = db.session.get(Sale, sale_id)
        assert sale.customer_id == cid and str(sale.total) == "214.00"
        assert str(sale.paid) == "0.00"
        assert db.session.scalar(db.select(db.func.count(Sale.id))) == 1
        assert db.session.scalar(db.select(db.func.count(StockMovement.id).where(StockMovement.delta < 0))) == 1
        quote = db.session.get(Quotation, qid)
        assert quote.sale_id == sale_id


def test_conversion_rejects_changed_price_and_insufficient_stock_without_partial_sale(seeded, client, app):
    token, pid, cid = seeded
    qid = make_accepted(client, token, pid, cid)
    endpoint = f"/api/quotations/{qid}/convert"
    with app.app_context():
        product = db.session.get(Product, pid)
        product.price = 110
        db.session.commit()
    assert post(client, token, endpoint, {}).status_code == 409
    with app.app_context():
        assert db.session.scalar(db.select(Sale.id)) is None
        assert db.session.get(Product, pid).stock == 10
        product = db.session.get(Product, pid)
        product.price = 100
        product.stock = 1
        db.session.commit()
    assert post(client, token, endpoint, {}).status_code == 409
    with app.app_context():
        assert db.session.scalar(db.select(Sale.id)) is None
        assert db.session.get(Quotation, qid).sale_id is None


def test_only_accepted_and_unexpired_quotations_can_be_converted(seeded, client, app):
    token, pid, cid = seeded
    unsent = post(client, token, "/api/quotations", quote_body(pid, cid, "synthetic-unsent-test-000001")).json["id"]
    assert post(client, token, f"/api/quotations/{unsent}/convert", {}).status_code == 409
    qid = make_accepted(client, token, pid, cid, "synthetic-expired-test-000001")
    with app.app_context():
        db.session.get(Quotation, qid).expires_on = date.today() - timedelta(days=1)
        db.session.commit()
    assert post(client, token, f"/api/quotations/{qid}/convert", {}).status_code == 409


def test_invalid_convert_payload_does_not_modify_stock(seeded, client, app):
    token, pid, cid = seeded
    qid = make_accepted(client, token, pid, cid)
    endpoint = f"/api/quotations/{qid}/convert"
    invalid = [
        {"delivery_mode": "unknown"},
        {"delivery_mode": "delivery", "address": ""},
        {"unexpected_field": True},
        {"delivery_mode": "pickup", "shipping_fee": "100.00"},
    ]
    assert all(post(client, token, endpoint, body).status_code == 400 for body in invalid)
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10
        assert db.session.scalar(db.select(Sale.id)) is None


def test_stale_customer_specific_price_rejected_even_if_total_might_match(seeded, client, app):
    token, pid, cid = seeded
    change = post(client, token, "/api/extended/prices", {"customer_id": cid, "product_id": pid, "price": "80.00"})
    assert change.status_code == 200
    qid = make_accepted(client, token, pid, cid, "synthetic-specialprice-quote-00001")
    change = post(client, token, "/api/extended/prices", {"customer_id": cid, "product_id": pid, "price": "90.00"})
    assert change.status_code == 200
    assert post(client, token, f"/api/quotations/{qid}/convert", {}).status_code == 409
