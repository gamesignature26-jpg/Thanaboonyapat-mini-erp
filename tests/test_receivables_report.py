"""Regression coverage for read-only receivables reporting."""

from conftest import login, post


def test_receivables_requires_login(client):
    assert client.get("/api/reports/receivables").status_code == 401


def test_receivables_restricts_warehouse_and_sales(client):
    login(client, "warehouse")
    assert client.get("/api/reports/receivables").status_code == 403
    login(client, "sales")
    assert client.get("/api/reports/receivables").status_code == 403


def test_receivables_reports_partial_and_fully_paid_sales(seeded, client):
    token, pid, cid = seeded
    sale1 = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 2}]})
    sale2 = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]})
    assert sale1.status_code == 201
    assert sale2.status_code == 201
    id1, id2 = sale1.json["id"], sale2.json["id"]
    assert (
        post(
            client, token, f"/sales/{id1}/payments", {"amount": "100.00", "reference": "report-partial-001"}
        ).status_code
        == 201
    )
    assert (
        post(client, token, f"/sales/{id2}/payments", {"amount": "107.00", "reference": "report-full-002"}).status_code
        == 201
    )
    result = client.get("/api/reports/receivables")
    assert result.status_code == 200
    assert result.json["total_outstanding"] == "114.00"
    assert result.json["open_invoices"] == 1
    assert result.json["items"][0]["customer_id"] == cid
    assert result.json["items"][0]["outstanding"] == "114.00"
    assert result.json["items"][0]["unpaid_sales"] == 1


def test_receivables_search_and_empty_results(seeded, client):
    token, pid, cid = seeded
    sale = post(client, token, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]})
    assert sale.status_code == 201
    assert client.get("/api/reports/receivables?q=does-not-exist").json["items"] == []
    assert client.get("/api/reports/receivables?q=Synthetic").json["total_outstanding"] == "107.00"
