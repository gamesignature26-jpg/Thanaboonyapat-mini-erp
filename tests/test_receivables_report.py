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


def test_receivables_page_preserves_totals_and_matches_percent_literally(seeded, client):
    token, pid, cid = seeded
    second = post(client, token, "/customers", {"name": "Buyer_100%", "address": "Synthetic"})
    assert second.status_code == 201
    for customer_id in (cid, second.json["id"]):
        sale = post(
            client, token, "/sales", {"customer_id": customer_id, "lines": [{"product_id": pid, "quantity": 1}]}
        )
        assert sale.status_code == 201

    first = client.get("/api/reports/receivables?limit=1&offset=0")
    assert first.status_code == 200
    assert len(first.json["items"]) == 1
    assert first.json["has_more"] is True
    assert first.json["next_offset"] == 1
    assert first.json["total_outstanding"] == "214.00"
    second_page = client.get("/api/reports/receivables?limit=1&offset=1")
    assert second_page.status_code == 200
    assert len(second_page.json["items"]) == 1
    assert second_page.json["has_more"] is False
    assert second_page.json["next_offset"] is None
    assert second_page.json["total_outstanding"] == "214.00"
    assert first.json["items"][0]["customer_id"] != second_page.json["items"][0]["customer_id"]

    literal_percent = client.get("/api/reports/receivables?q=%")
    assert [x["customer_id"] for x in literal_percent.json["items"]] == [second.json["id"]]
    assert client.get("/api/reports/receivables?limit=0").status_code == 400
    assert client.get("/api/reports/receivables?limit=101").status_code == 400
    assert client.get("/api/reports/receivables?offset=abc").status_code == 400
