"""Multi-sale billing DRAFT tests; never mutate sales, payments, or tax documents."""

from conftest import login, post

from erp.models import Customer, Payment, Product, Sale, StockMovement, db


def sale(client, token, customer_id, product_id, quantity=1):
    response = post(
        client,
        token,
        "/sales",
        {"customer_id": customer_id, "lines": [{"product_id": product_id, "quantity": quantity}]},
    )
    assert response.status_code == 201
    return response.json["id"]


def batch(customer_id, sale_ids, key="synthetic-multi-billing-20261112-001"):
    return {
        "request_key": key,
        "customer_id": customer_id,
        "sale_ids": sale_ids,
        "note": "Synthetic combined monthly billing",
    }


def test_billing_batch_roles_and_csrf(client, seeded):
    token, product_id, customer_id = seeded
    sale_id = sale(client, token, customer_id, product_id)
    anonymous = client.application.test_client()
    assert anonymous.get("/api/billing-batches").status_code == 401
    assert anonymous.get("/api/billing-batches/eligible?customer_id=1").status_code == 401
    warehouse = login(client, "warehouse")
    assert client.get("/api/billing-batches").status_code == 403
    assert post(client, warehouse, "/api/billing-batches", batch(customer_id, [sale_id])).status_code == 403
    sales = login(client, "sales")
    assert client.get("/api/billing-batches").status_code == 200
    assert post(client, sales, "/api/billing-batches", batch(customer_id, [sale_id])).status_code == 403
    accountant = login(client, "accountant")
    assert post(client, accountant, "/api/billing-batches", batch(customer_id, [sale_id])).status_code == 201


def test_batch_snapshots_and_live_balance_do_not_double_receivables(client, seeded, app):
    token, product_id, customer_id = seeded
    first = sale(client, token, customer_id, product_id)
    second = sale(client, token, customer_id, product_id, quantity=2)
    created = post(client, token, "/api/billing-batches", batch(customer_id, [second, first]))
    assert created.status_code == 201
    assert created.json["number"] == "BATCH-DRAFT-000001"
    detail_url = f"/api/billing-batches/{created.json['id']}"
    detail = client.get(detail_url).json
    assert detail["status"] == "draft"
    assert detail["notice"] == "BILLING DRAFT - NOT A TAX INVOICE OR RECEIPT"
    assert detail["customer"]["name"] == "Synthetic customer"
    assert [x["sale_id"] for x in detail["items"]] == [first, second]
    assert detail["snapshot_total"] == "321.00"
    assert detail["current_outstanding"] == "321.00"
    assert detail["items"][0]["outstanding_at_creation"] == "107.00"
    with app.app_context():
        assert db.session.get(Sale, first).paid == 0
        assert db.session.get(Product, product_id).stock == 7
        assert db.session.scalar(db.select(Payment.id)) is None
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 3
    received = post(
        client, token, f"/sales/{first}/payments", {"amount": "50.00", "reference": "synthetic-bill-pay-001"}
    )
    assert received.status_code == 201
    after = client.get(detail_url).json
    assert after["snapshot_total"] == "321.00"
    assert after["current_outstanding"] == "271.00"
    assert after["items"][0]["outstanding_at_creation"] == "107.00"
    assert after["items"][0]["outstanding_now"] == "57.00"


def test_batch_rejects_other_customer_paid_sales_duplicates_and_invalid_keys(client, seeded, app):
    token, product_id, customer_id = seeded
    other = post(client, token, "/customers", {"name": "Other synthetic", "address": "Other"}).json["id"]
    s1 = sale(client, token, customer_id, product_id)
    s2 = sale(client, token, other, product_id)
    assert (
        post(
            client, token, f"/sales/{s1}/payments", {"amount": "107.00", "reference": "synthetic-paid-001"}
        ).status_code
        == 201
    )
    invalid = [
        batch(customer_id, [s2]),
        batch(customer_id, [s1]),
        batch(customer_id, [s2, s1]),
        batch(customer_id, [s2, s2]),
        batch(customer_id, [], "synthetic-empty-batch-key-001"),
        batch(customer_id, [s2], "short"),
    ]
    results = [post(client, token, "/api/billing-batches", request).status_code for request in invalid]
    assert results == [409, 409, 409, 400, 400, 400]
    assert client.get("/api/billing-batches").json["items"] == []


def test_batch_idempotency_overlap_and_void_release(client, seeded):
    token, product_id, customer_id = seeded
    s1 = sale(client, token, customer_id, product_id)
    body = batch(customer_id, [s1])
    first = post(client, token, "/api/billing-batches", body)
    again = post(client, token, "/api/billing-batches", body)
    changed = post(client, token, "/api/billing-batches", {**body, "note": "Changed"})
    overlap = post(client, token, "/api/billing-batches", batch(customer_id, [s1], "synthetic-bill-new-key-0001"))
    assert first.status_code == 201
    assert again.status_code == 200 and again.json["duplicate"] is True
    assert again.json["id"] == first.json["id"]
    assert changed.status_code == 409
    assert overlap.status_code == 409
    url = f"/api/billing-batches/{first.json['id']}/void"
    assert post(client, token, url, {"reason": ""}).status_code == 400
    voided = post(client, token, url, {"reason": "Customer requests revised grouping"})
    assert voided.status_code == 200
    assert voided.json["status"] == "void"
    assert post(client, token, url, {"reason": "Customer requests revised grouping"}).json["duplicate"] is True
    assert post(client, token, url, {"reason": "Different reason"}).status_code == 409
    retry = post(client, token, "/api/billing-batches", batch(customer_id, [s1], "synthetic-bill-new-key-0001"))
    assert retry.status_code == 201


def test_eligible_list_filters_and_private_print(client, seeded, app):
    token, product_id, customer_id = seeded
    s1 = sale(client, token, customer_id, product_id)
    s2 = sale(client, token, customer_id, product_id)
    eligible = client.get(f"/api/billing-batches/eligible?customer_id={customer_id}").json
    assert [item["sale_id"] for item in eligible["items"]] == [s2, s1]
    assert client.get("/api/billing-batches/eligible?customer_id=nope").status_code == 400
    assert client.get("/api/billing-batches?limit=0").status_code == 400
    assert client.get("/api/billing-batches?before=abc").status_code == 400
    first = post(client, token, "/api/billing-batches", batch(customer_id, [s1]))
    assert first.status_code == 201
    remaining = client.get(f"/api/billing-batches/eligible?customer_id={customer_id}").json
    assert [item["sale_id"] for item in remaining["items"]] == [s2]
    with app.app_context():
        db.session.get(Customer, customer_id).name = "<img src=x onerror=alert(1)>"
        db.session.commit()
    url = f"/api/billing-batches/{first.json['id']}/print"
    printed = client.get(url)
    assert printed.status_code == 200
    html = printed.get_data(as_text=True)
    assert "ใบวางบิลรวม (ร่าง)" in html
    assert "Synthetic customer" in html
    assert "<img src=x onerror=alert(1)>" not in html
    login(client, "warehouse")
    assert client.get(url).status_code == 403


def test_batch_list_pagination_and_void_permissions(client, seeded):
    token, product_id, customer_id = seeded
    sales = [sale(client, token, customer_id, product_id) for _ in range(3)]
    made = [
        post(client, token, "/api/billing-batches", batch(customer_id, [sid], f"synthetic-billing-page-{i:05d}"))
        for i, sid in enumerate(sales)
    ]
    assert all(x.status_code == 201 for x in made)
    page = client.get("/api/billing-batches?limit=2").json
    assert len(page["items"]) == 2
    assert page["next_before"] == made[1].json["id"]
    last = client.get(f"/api/billing-batches?limit=2&before={page['next_before']}").json
    assert len(last["items"]) == 1
    sales_token = login(client, "sales")
    assert (
        post(client, sales_token, f"/api/billing-batches/{made[0].json['id']}/void", {"reason": "No"}).status_code
        == 403
    )
