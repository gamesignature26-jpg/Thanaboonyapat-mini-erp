"""Synthetic-only credit-review drafts never alter customer or tax ledgers."""

from conftest import login, post

from erp.models import Payment, Product, Sale, StockMovement, db


def received_return(client, seeded, key="synthetic-return-for-credit-00001"):
    token, pid, cid = seeded
    sale = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 2}]})
    assert sale.status_code == 201
    sale_id = sale.json["id"]
    sale_line_id = client.get(f"/api/returns/sales/{sale_id}/eligible").json["lines"][0]["sale_line_id"]
    intake = post(
        client,
        token,
        "/api/returns",
        {
            "request_key": key,
            "sale_id": sale_id,
            "reason": "Synthetic intact pack return",
            "lines": [{"sale_line_id": sale_line_id, "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    warehouse = login(client, "warehouse")
    inspected = post(
        client,
        warehouse,
        f"/api/returns/{intake.json['id']}/inspect",
        {"condition": "resellable", "inspection_note": "Sealed package counted"},
    )
    assert inspected.status_code == 200
    return sale_id, intake.json["id"], pid


def request_body(return_id, key="synthetic-financial-credit-00001"):
    return {
        "request_key": key,
        "return_id": return_id,
        "reason": "Synthetic account review only",
        "amount_ex_vat": "100.00",
        "vat_amount": "7.00",
    }


def test_credit_draft_access_and_no_business_side_effects(seeded, client, app):
    sale_id, return_id, pid = received_return(client, seeded)
    anon = app.test_client()
    assert anon.get("/api/credit-note-drafts").status_code == 401
    login(client, "sales")
    assert client.get("/api/credit-note-drafts").status_code == 403
    assert (
        post(client, login(client, "warehouse"), "/api/credit-note-drafts", request_body(return_id)).status_code == 403
    )
    accountant = login(client, "accountant")
    response = post(client, accountant, "/api/credit-note-drafts", request_body(return_id))
    assert response.status_code == 201
    draft = client.get(f"/api/credit-note-drafts/{response.json['id']}")
    assert draft.status_code == 200
    assert draft.json["number"] == "CREDIT-DRAFT-000001"
    assert draft.json["status"] == "draft"
    assert draft.json["credit_total"] == "107.00"
    assert draft.json["original_sale_total"] == "214.00"
    assert draft.json["original_sale_paid"] == "0.00"
    assert draft.json["current_sale_balance"] == "214.00"
    assert len(draft.json["returned_lines"]) == 1
    assert draft.json["returned_lines"][0]["quantity"] == 1
    assert draft.json["posted_to_receivables"] is False
    assert draft.json["tax_credit_note_issued"] is False
    assert client.get(f"/api/credit-note-drafts/{response.json['id']}/print").status_code == 200
    assert "CREDIT-DRAFT-000001" in client.get(f"/api/credit-note-drafts/{response.json['id']}/print").text
    with app.app_context():
        sale = db.session.get(Sale, sale_id)
        assert sale.total == 214 and sale.paid == 0
        assert db.session.get(Product, pid).stock == 9
        assert db.session.scalar(db.select(db.func.count(Payment.id))) == 0
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 3


def test_credit_draft_key_idempotency_limits_and_void(seeded, client, app):
    sale_id, return_id, _ = received_return(client, seeded)
    token = login(client, "accountant")
    request = request_body(return_id)
    first = post(client, token, "/api/credit-note-drafts", request)
    assert first.status_code == 201
    again = post(client, token, "/api/credit-note-drafts", request)
    assert again.status_code == 200
    assert again.json["id"] == first.json["id"] and again.json["duplicate"]
    assert post(client, token, "/api/credit-note-drafts", {**request, "amount_ex_vat": "99.00"}).status_code == 409
    assert (
        post(
            client,
            token,
            "/api/credit-note-drafts",
            request_body(return_id, "synthetic-another-credit-request-0002"),
        ).status_code
        == 409
    )
    assert post(client, token, "/api/credit-note-drafts", request_body(999999, "synthetic-missing-credit-return-00001")).status_code == 404
    assert post(client, token, "/api/credit-note-drafts", {**request, "request_key": "short"}).status_code == 400
    assert post(client, token, "/api/credit-note-drafts", {**request, "vat_amount": "15.00"}).status_code == 409
    assert post(client, token, "/api/credit-note-drafts", {**request, "request_key": "synthetic-invalid-credit-amount-0001", "amount_ex_vat": "-1.00"}).status_code == 400
    assert client.get("/api/credit-note-drafts?limit=0").status_code == 400
    assert client.get("/api/credit-note-drafts?before=x").status_code == 400

    removed = post(
        client, token, f"/api/credit-note-drafts/{first.json['id']}/void", {"reason": "Synthetic correction"}
    )
    assert removed.status_code == 200 and removed.json["status"] == "void"
    repeat = post(client, token, f"/api/credit-note-drafts/{first.json['id']}/void", {"reason": "Synthetic correction"})
    assert repeat.status_code == 200
    assert (
        post(client, token, f"/api/credit-note-drafts/{first.json['id']}/void", {"reason": "Different"}).status_code
        == 409
    )
    assert client.get("/api/credit-note-drafts").json["items"][0]["status"] == "void"
    with app.app_context():
        assert db.session.get(Sale, sale_id).total == 214


def test_credit_draft_requires_received_return_not_just_request(seeded, client):
    token, pid, cid = seeded
    sale_id = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]}).json[
        "id"
    ]
    line_id = client.get(f"/api/returns/sales/{sale_id}/eligible").json["lines"][0]["sale_line_id"]
    intake = post(
        client,
        token,
        "/api/returns",
        {
            "request_key": "synthetic-uninspected-return-0001",
            "sale_id": sale_id,
            "reason": "Synthetic pending inspection",
            "lines": [{"sale_line_id": line_id, "quantity": 1}],
        },
    )
    assert intake.status_code == 201
    token = login(client, "accountant")
    assert post(client, token, "/api/credit-note-drafts", request_body(intake.json["id"])).status_code == 409
