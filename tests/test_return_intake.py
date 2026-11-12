"""Return intake must be audited, inventory-safe, and NEVER auto-create a legal credit note."""

from conftest import login, post

from erp.models import Product, Sale, SaleLine, StockMovement, db


def create_sale(client, token, pid, cid, qty=3):
    sale = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": qty}]})
    assert sale.status_code == 201
    return sale.json["id"]


def return_request(client, token, sale_id, line_id, qty=2, key="synthetic-return-intake-0000001"):
    return post(
        client,
        token,
        "/api/returns",
        {
            "request_key": key,
            "sale_id": sale_id,
            "reason": "Synthetic customer brought sealed packs back",
            "lines": [{"sale_line_id": line_id, "quantity": qty}],
        },
    )


def test_return_draft_does_not_mutate_stock_or_ledger(seeded, client, app):
    token, pid, cid = seeded
    sale_id = create_sale(client, token, pid, cid)
    with app.app_context():
        line_id = db.session.scalar(db.select(SaleLine.id).where(SaleLine.sale_id == sale_id))
    response = return_request(client, token, sale_id, line_id)
    assert response.status_code == 201
    draft = client.get(f"/api/returns/{response.json['id']}")
    assert draft.status_code == 200
    assert draft.json["number"].startswith("RETURN-DRAFT-")
    assert draft.json["status"] == "draft"
    assert draft.json["credit_note_issued"] is False
    assert draft.json["notice"] == "RETURN INTAKE - NOT A TAX CREDIT NOTE"
    assert draft.json["lines"][0]["quantity"] == 2
    assert draft.json["lines"][0]["sku"] == "TEST-001"
    with app.app_context():
        assert db.session.get(Product, pid).stock == 7
        assert db.session.get(Sale, sale_id).total == 321
        assert db.session.get(Sale, sale_id).paid == 0
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 2


def test_return_inspection_restock_once_without_changing_receivables(seeded, client, app):
    token, pid, cid = seeded
    sid = create_sale(client, token, pid, cid)
    with app.app_context():
        line = db.session.scalar(db.select(SaleLine).where(SaleLine.sale_id == sid))
    draft = return_request(client, token, sid, line.id)
    rid = draft.json["id"]
    warehouse = login(client, "warehouse")
    inspect = {"condition": "resellable", "inspection_note": "Sealed bottles counted in test"}
    first = post(client, warehouse, f"/api/returns/{rid}/inspect", inspect)
    assert first.status_code == 200
    assert first.json["status"] == "received"
    assert first.json["restocked"] is True
    second = post(client, warehouse, f"/api/returns/{rid}/inspect", inspect)
    assert second.status_code == 200
    assert second.json["duplicate"] is True
    changed = post(
        client,
        warehouse,
        f"/api/returns/{rid}/inspect",
        {"condition": "damaged", "inspection_note": "Trying to overwrite"},
    )
    assert changed.status_code == 409
    with app.app_context():
        assert db.session.get(Product, pid).stock == 9
        assert db.session.get(Sale, sid).total == 321
        assert db.session.get(Sale, sid).paid == 0
        restock = list(db.session.scalars(db.select(StockMovement).where(StockMovement.delta > 0)))
        assert len(restock) == 2
        assert restock[-1].delta == 2
        assert restock[-1].sale_id == sid


def test_damaged_return_is_received_but_not_restocked(seeded, client, app):
    token, pid, cid = seeded
    sid = create_sale(client, token, pid, cid)
    with app.app_context():
        line_id = db.session.scalar(db.select(SaleLine.id).where(SaleLine.sale_id == sid))
    rid = return_request(client, token, sid, line_id, qty=1).json["id"]
    warehouse = login(client, "warehouse")
    response = post(
        client,
        warehouse,
        f"/api/returns/{rid}/inspect",
        {"condition": "damaged", "inspection_note": "Leaking bottle"},
    )
    assert response.status_code == 200
    assert response.json["restocked"] is False
    with app.app_context():
        assert db.session.get(Product, pid).stock == 7
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 2


def test_return_overlapping_drafts_must_not_overreturn(seeded, client, app):
    token, pid, cid = seeded
    sid = create_sale(client, token, pid, cid)
    with app.app_context():
        line_id = db.session.scalar(db.select(SaleLine.id).where(SaleLine.sale_id == sid))
    a = return_request(client, token, sid, line_id, 2, "synthetic-return-overlap-000001")
    b = return_request(client, token, sid, line_id, 2, "synthetic-return-overlap-000002")
    assert a.status_code == 201 and b.status_code == 201
    warehouse = login(client, "warehouse")
    inspect = {"condition": "resellable", "inspection_note": "Physical inspection complete"}
    assert post(client, warehouse, f"/api/returns/{a.json['id']}/inspect", inspect).status_code == 200
    assert post(client, warehouse, f"/api/returns/{b.json['id']}/inspect", inspect).status_code == 409
    remaining = client.get(f"/api/returns/sales/{sid}/eligible").json
    assert remaining["lines"][0]["returned_quantity"] == 2
    assert remaining["lines"][0]["remaining_quantity"] == 1
    with app.app_context():
        assert db.session.get(Product, pid).stock == 9


def test_return_retries_conflicts_and_reject_path(seeded, client, app):
    token, pid, cid = seeded
    sid = create_sale(client, token, pid, cid)
    with app.app_context():
        line_id = db.session.scalar(db.select(SaleLine.id).where(SaleLine.sale_id == sid))
    first = return_request(client, token, sid, line_id)
    assert first.status_code == 201
    retry = return_request(client, token, sid, line_id)
    assert retry.status_code == 200
    assert retry.json["duplicate"] is True and retry.json["id"] == first.json["id"]
    conflict = return_request(client, token, sid, line_id, 1)
    assert conflict.status_code == 409
    warehouse = login(client, "warehouse")
    rejected = post(
        client,
        warehouse,
        f"/api/returns/{first.json['id']}/reject",
        {"inspection_note": "Customer did not bring goods"},
    )
    assert rejected.status_code == 200
    assert rejected.json["status"] == "rejected"
    assert (
        post(client, warehouse, f"/api/returns/{first.json['id']}/reject", {"inspection_note": "Different"}).status_code
        == 409
    )
    assert (
        post(
            client,
            warehouse,
            f"/api/returns/{first.json['id']}/inspect",
            {"condition": "resellable", "inspection_note": "Late"},
        ).status_code
        == 409
    )


def test_return_validation_roles_and_listing(seeded, client, app):
    token, pid, cid = seeded
    sid = create_sale(client, token, pid, cid)
    with app.app_context():
        line_id = db.session.scalar(db.select(SaleLine.id).where(SaleLine.sale_id == sid))
    assert client.get("/api/returns/sales/99999/eligible").status_code == 404
    bads = [
        {"request_key": "short", "sale_id": sid, "lines": [{"sale_line_id": line_id, "quantity": 1}], "reason": "abc"},
        {
            "request_key": "synthetic-invalid-returns-001",
            "sale_id": sid,
            "lines": [{"sale_line_id": line_id, "quantity": 4}],
            "reason": "abc",
        },
        {
            "request_key": "synthetic-invalid-returns-002",
            "sale_id": sid,
            "lines": [{"sale_line_id": line_id, "quantity": 1}] * 2,
            "reason": "abc",
        },
    ]
    assert [post(client, token, "/api/returns", body).status_code for body in bads] == [400, 409, 400]
    assert client.get("/api/returns").json["items"] == []
    first = return_request(client, token, sid, line_id)
    assert first.status_code == 201
    assert client.get("/api/returns?limit=0").status_code == 400
    assert client.get("/api/returns?before=nope").status_code == 400
    noauth = client.application.test_client()
    assert noauth.get("/api/returns").status_code == 401
    warehouse = login(client, "warehouse")
    assert client.get("/api/returns").status_code == 200
    assert post(client, warehouse, "/api/returns", bads[0]).status_code == 403
    sales = login(client, "sales")
    assert (
        post(
            client,
            sales,
            f"/api/returns/{first.json['id']}/inspect",
            {"condition": "resellable", "inspection_note": "Unauthorized"},
        ).status_code
        == 403
    )
    login(client, "accountant")
    assert client.get("/api/returns").status_code == 200
    assert client.get(f"/api/returns/{first.json['id']}").status_code == 200


def test_return_print_preview_is_private_and_not_a_credit_note(seeded, client, app):
    token, pid, cid = seeded
    sid = create_sale(client, token, pid, cid)
    with app.app_context():
        line_id = db.session.scalar(db.select(SaleLine.id).where(SaleLine.sale_id == sid))
    rid = return_request(client, token, sid, line_id).json["id"]
    path = f"/api/returns/{rid}/print"
    preview = client.get(path)
    assert preview.status_code == 200
    html = preview.get_data(as_text=True)
    assert "ใบรับคืนสินค้าตัวอย่าง" in html
    assert "ไม่ใช่ใบลดหนี้" in html
    assert "Synthetic item" in html
    assert "RETURN-DRAFT-" in html
    assert "ออกใบลดหนี้แล้ว" not in html
    noauth = client.application.test_client()
    assert noauth.get(path).status_code == 401
    login(client, "warehouse")
    assert client.get(path).status_code == 200
