"""Cost evidence regression tests: never manufacture gross profit from missing costs."""

from conftest import login, post

from erp.models import Product, Sale, StockMovement, db


def test_cost_evidence_report_requires_accounting_role(client):
    assert client.get("/api/reports/cost-evidence").status_code == 401
    login(client, "sales")
    assert client.get("/api/reports/cost-evidence").status_code == 403
    login(client, "warehouse")
    assert client.get("/api/reports/cost-evidence").status_code == 403
    login(client, "accountant")
    assert client.get("/api/reports/cost-evidence").status_code == 200


def test_receipts_are_evidence_but_not_verified_cogs_or_gross_profit(seeded, client, app):
    token, pid, cid = seeded
    sold = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 2}]})
    assert sold.status_code == 201
    sid = post(client, token, "/api/suppliers", {"name": "Synthetic supplier"}).json["id"]
    purchase = post(
        client,
        token,
        "/api/purchases",
        {
            "request_key": "synthetic-cost-evidence-test-0001",
            "supplier_id": sid,
            "lines": [{"product_id": pid, "quantity": 4, "unit_cost": "41.50"}],
        },
    )
    assert purchase.status_code == 201
    draft = client.get("/api/reports/cost-evidence").json
    assert draft["received_purchase_units"] == 0
    assert draft["received_purchase_cost_ex_vat"] == "0.00"
    assert draft["cogs_ex_vat"] is None
    assert draft["gross_profit_ex_vat"] is None
    assert draft["gross_profit_status"] == "unavailable"

    warehouse = login(client, "warehouse")
    assert (
        post(
            client,
            warehouse,
            f"/api/purchases/{purchase.json['id']}/receive",
            {"receipt_note": "Counted four sealed packs"},
        ).status_code
        == 200
    )
    login(client, "accountant")
    evidence = client.get("/api/reports/cost-evidence")
    assert evidence.status_code == 200
    body = evidence.json
    assert body["received_purchase_units"] == 4
    assert body["received_purchase_cost_ex_vat"] == "166.00"
    assert body["sales_revenue_ex_vat"] == "200.00"
    assert body["cogs_ex_vat"] is None
    assert body["gross_profit_ex_vat"] is None
    assert body["gross_profit_status"] == "unavailable"
    product = body["items"][0]
    assert product["product_id"] == pid
    assert product["stock_units"] == 12
    assert product["received_purchase_units"] == 4
    assert product["unattributed_inbound_units"] == 10
    assert product["stock_movement_reconciles"] is True

    with app.app_context():
        assert db.session.get(Product, pid).stock == 12
        assert db.session.get(Sale, sold.json["id"]).paid == 0
        assert db.session.scalar(db.select(db.func.count(StockMovement.id))) == 3


def test_cost_evidence_detects_stock_movement_drift_and_has_safe_paging(seeded, client, app):
    _token, pid, _ = seeded
    with app.app_context():
        db.session.get(Product, pid).stock += 1  # Synthetic corruption: no matching audit movement.
        db.session.commit()
    result = client.get("/api/reports/cost-evidence?limit=1")
    assert result.status_code == 200
    assert result.json["items"][0]["stock_movement_reconciles"] is False
    assert result.json["items"][0]["unattributed_inbound_units"] == 10
    assert result.json["gross_profit_status"] == "unavailable"
    assert client.get("/api/reports/cost-evidence?limit=0").status_code == 400
    assert client.get("/api/reports/cost-evidence?limit=101").status_code == 400
    assert client.get("/api/reports/cost-evidence?after=x").status_code == 400
