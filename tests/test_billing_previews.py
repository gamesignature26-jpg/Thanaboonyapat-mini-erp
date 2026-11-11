"""Read-only billing note previews over existing sales (no legal document issuance)."""

from conftest import login, post

from erp.models import Customer, Product, Sale, StockMovement, db


def test_billing_notes_restrict_unauthenticated_and_warehouse(client, seeded):
    token, pid, cid = seeded
    created = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 2}]})
    sid = created.json["id"]
    unauth = client.application.test_client()
    assert unauth.get("/api/billing-notes").status_code == 401
    assert unauth.get(f"/api/billing-notes/{sid}").status_code == 401
    login(client, "warehouse")
    assert client.get("/api/billing-notes").status_code == 403
    assert client.get(f"/api/billing-notes/{sid}/print").status_code == 403
    login(client, "accountant")
    assert client.get("/api/billing-notes").status_code == 200


def test_billing_preview_shows_open_balance_and_payment_updates(seeded, client, app):
    token, pid, cid = seeded
    sale = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 2}]})
    sid = sale.json["id"]
    url = f"/api/billing-notes/{sid}"
    first = client.get(url)
    assert first.status_code == 200
    assert first.json["number"] == f"BILL-PREVIEW-{sid:06d}"
    assert first.json["notice"] == "BILLING PREVIEW - NOT A TAX INVOICE"
    assert first.json["total"] == "214.00"
    assert first.json["paid"] == "0.00"
    assert first.json["outstanding"] == "214.00"
    assert first.json["customer"]["name"] == "Synthetic customer"
    assert first.json["lines"][0]["sku"] == "TEST-001"
    assert first.json["lines"][0]["quantity"] == 2
    assert first.json["issued"] is False
    payment = post(client, token, f"/sales/{sid}/payments", {"amount": "100.00", "reference": "bill-preview-part-001"})
    assert payment.status_code == 201
    assert client.get(url).json["outstanding"] == "114.00"
    with app.app_context():
        assert db.session.get(Product, pid).stock == 8
        assert db.session.scalar(db.select(db.func.count(Sale.id))) == 1
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 2


def test_billing_note_list_filters_and_pages(seeded, client):
    token, pid, cid = seeded
    first = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]})
    second = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]})
    sid1, sid2 = first.json["id"], second.json["id"]
    assert (
        post(client, token, f"/sales/{sid1}/payments", {"amount": "107.00", "reference": "bill-full-001"}).status_code
        == 201
    )
    page = client.get("/api/billing-notes?limit=1").json
    assert [x["sale_id"] for x in page["items"]] == [sid2]
    assert page["next_before"] is None
    all_page = client.get("/api/billing-notes?outstanding=0&limit=1").json
    assert all_page["next_before"] == sid2
    assert client.get(f"/api/billing-notes?outstanding=0&limit=1&before={sid2}").json["items"][0]["sale_id"] == sid1
    assert client.get("/api/billing-notes?limit=0").status_code == 400
    assert client.get("/api/billing-notes?before=nope").status_code == 400
    assert client.get("/api/billing-notes?outstanding=invalid").status_code == 400


def test_billing_previews_use_immutable_sale_snapshots_and_escape_print(seeded, client, app):
    token, pid, cid = seeded
    made = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]})
    sid = made.json["id"]
    with app.app_context():
        db.session.get(Customer, cid).name = "<img src=x onerror=alert(1)>"
        db.session.get(Product, pid).name = "Changed product name"
        db.session.commit()
    detail = client.get(f"/api/billing-notes/{sid}").json
    assert detail["customer"]["name"] == "Synthetic customer"
    assert detail["lines"][0]["name"] == "Synthetic item"
    printed = client.get(f"/api/billing-notes/{sid}/print")
    assert printed.status_code == 200
    html = printed.get_data(as_text=True)
    assert "ใบวางบิลตัวอย่าง" in html
    assert "Synthetic customer" in html
    assert "ไม่ใช่ใบกำกับภาษี" in html
    assert "ไม่ใช่หลักฐานรับเงิน" in html
    assert "<img src=x onerror=alert(1)>" not in html
    assert client.get("/api/billing-notes/99999").status_code == 404
