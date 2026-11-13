"""Staging integration tests. Uses existing synthetic-only fixtures from conftest."""

from io import BytesIO

from conftest import login, post
from openpyxl import Workbook, load_workbook
from PIL import Image
from test_concurrency import concurrent_requests

from erp.extended import CustomerPrice, IssuedDocument, ProductImage
from erp.models import Customer, Product, Sale, SaleLine, db


def make_order(pid, cid, key, method="credit"):
    return {
        "kind": "pos",
        "idempotency_key": key,
        "customer_id": cid,
        "delivery_mode": "pickup",
        "method": method,
        "lines": [{"product_id": pid, "quantity": 2}],
    }


def test_special_prices_are_stored_applied_and_snapshotted(client, app, seeded):
    admin, pid, cid = seeded
    response = post(
        client,
        admin,
        "/api/extended/prices",
        {"product_id": pid, "customer_id": cid, "price": "80.00"},
    )
    assert response.status_code == 200
    assert client.get(f"/api/extended/prices/{cid}").json["items"] == [{"product_id": pid, "price": "80.00"}]
    created = post(client, admin, "/api/online/orders", make_order(pid, cid, "synthetic-special-order-111111111"))
    assert created.status_code == 201
    assert created.json["total"] == "171.20"
    with app.app_context():
        line = db.session.scalar(db.select(SaleLine).where(SaleLine.sale_id == created.json["id"]))
        assert line.price == 80
        assert db.session.query(CustomerPrice).count() == 1
    updated = post(
        client,
        admin,
        "/api/extended/prices",
        {"product_id": pid, "customer_id": cid, "price": "90.00"},
    )
    assert updated.status_code == 200
    assert client.get(f"/sales/{created.json['id']}").json["lines"][0]["price"] == "80.00"
    legacy = post(client, admin, "/sales", {"customer_id": cid, "lines": [{"product_id": pid, "quantity": 1}]})
    assert legacy.json["subtotal"] == "90.00"


def test_stale_pos_quote_keeps_stock_unchanged(client, app, seeded):
    token, pid, cid = seeded
    assert (
        post(
            client, token, "/api/extended/prices", {"product_id": pid, "customer_id": cid, "price": "80.00"}
        ).status_code
        == 200
    )
    order = make_order(pid, cid, "synthetic-quote-race-1")
    assert post(client, token, "/api/online/orders", {**order, "expected_total": "214.00"}).status_code == 409
    with app.app_context():
        assert db.session.get(Product, pid).stock == 10
        assert db.session.scalar(db.select(Sale.id)) is None
    assert post(client, token, "/api/online/orders", {**order, "expected_total": "171.20"}).status_code == 201


def test_online_full_payment_concurrency_and_debtor_filter(client, app, seeded):
    token, pid, cid = seeded
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        import pytest

        pytest.skip("Concurrent payment row locks require PostgreSQL")
    result = post(client, token, "/api/online/orders", make_order(pid, cid, "synthetic-concurrent-online-payment"))
    assert result.status_code == 201
    sid = result.json["id"]
    assert [x["id"] for x in client.get("/api/online/sales?outstanding=1").json["items"]] == [sid]
    path = f"/api/online/sales/{sid}/payments"
    assert concurrent_requests(
        app, path, [{"amount": "214.00", "method": "cash", "reference": f"synthetic-parallel-{i}"} for i in range(2)]
    ) == [201, 409]
    assert client.get("/api/online/sales?outstanding=1").json["items"] == []
    history = client.get(f"/api/extended/sales/{sid}/payments").json
    assert history["balance"] == "0.00" and len(history["payments"]) == 1


def test_warehouse_delivery_omits_financial_fields(client, app, seeded):
    token, pid, cid = seeded
    order = make_order(pid, cid, "synthetic-warehouse-dispatch")
    order["kind"] = "wholesale"
    order["lines"][0]["unit_price"] = "85.00"
    result = post(client, token, "/api/online/orders", order)
    assert result.status_code == 201
    staff = app.test_client()
    login(staff, "warehouse")
    assert staff.get("/api/online/sales").status_code == 403
    assert staff.get("/api/extended/company").status_code == 403
    item = staff.get(f"/api/online/orders/{result.json['id']}").json
    assert not {"total", "paid", "balance", "vat", "discount"} & set(item)
    assert item["lines"] == [{"sku": "TEST-001", "name": "Synthetic item", "quantity": 2}]


def test_company_and_customer_price_permissions(client, seeded):
    _owner, pid, cid = seeded
    warehouse = login(client, "warehouse")
    assert client.get(f"/api/extended/prices/{cid}").status_code == 403
    assert (
        post(
            client, warehouse, "/api/extended/prices", {"customer_id": cid, "product_id": pid, "price": "1.00"}
        ).status_code
        == 403
    )
    assert post(client, warehouse, "/api/extended/company", {"legal_name": "wrong"}).status_code == 403
    sales = login(client, "sales")
    assert (
        post(
            client, sales, "/api/extended/prices", {"customer_id": cid, "product_id": pid, "price": "50.00"}
        ).status_code
        == 200
    )
    assert post(client, sales, "/api/extended/company", {"legal_name": "wrong"}).status_code == 403
    assert (
        post(
            client, sales, "/api/extended/prices", {"customer_id": cid, "product_id": pid, "price": "0.00"}
        ).status_code
        == 400
    )


def test_partial_payment_history_and_receipt_per_payment(client, app, seeded):
    owner, pid, cid = seeded
    order = post(client, owner, "/api/online/orders", make_order(pid, cid, "synthetic-payment-order-222222222"))
    sid = order.json["id"]
    assert (
        post(
            client,
            owner,
            f"/api/online/sales/{sid}/payments",
            {"amount": "100.00", "method": "transfer", "reference": "synthetic-transfer-222222"},
        ).status_code
        == 201
    )
    history = client.get(f"/api/extended/sales/{sid}/payments")
    assert history.status_code == 200
    assert history.json["balance"] == "114.00"
    payment_id = history.json["payments"][0]["id"]
    assert history.json["payments"][0]["method"] == "transfer"
    receipt = post(
        client, owner, "/api/extended/documents", {"sale_id": sid, "kind": "receipt", "payment_id": payment_id}
    )
    assert receipt.status_code == 201
    duplicate = post(
        client, owner, "/api/extended/documents", {"sale_id": sid, "kind": "receipt", "payment_id": payment_id}
    )
    assert duplicate.status_code == 200 and duplicate.json["id"] == receipt.json["id"]
    doc_id = receipt.json["id"]
    assert "text/html" in client.get(f"/api/extended/documents/{doc_id}/print?paper=a4").content_type
    assert "ข้อมูลทดสอบ" in client.get(f"/api/extended/documents/{doc_id}/print?paper=58").data.decode()
    with app.app_context():
        assert db.session.query(IssuedDocument).count() == 1


def test_tax_invoice_requires_company_and_customer_details(client, app, seeded):
    owner, pid, cid = seeded
    missing = post(client, owner, "/api/online/orders", make_order(pid, cid, "synthetic-invoice-order-333333333"))
    sid = missing.json["id"]
    assert post(client, owner, "/api/extended/documents", {"kind": "tax_invoice", "sale_id": sid}).status_code == 409
    with app.app_context():
        # Only synthetic identifiers; never use actual taxpayer information in tests.
        buyer = db.session.get(Customer, cid)
        buyer.tax_id = "0123456789012"
        sale = db.session.get(Sale, sid)
        sale.customer_tax_id = buyer.tax_id
        db.session.commit()
    profile = post(
        client,
        owner,
        "/api/extended/company",
        {
            "legal_name": "Synthetic Test Partnership",
            "tax_id": "0123456789012",
            "branch": "Test headquarters",
            "address": "Synthetic test address",
            "phone": "0000000000",
            "receipt_footer": "Internal test only",
            "default_paper": "58",
        },
    )
    assert profile.status_code == 200 and profile.json["default_paper"] == "58"
    payload = {
        "kind": "tax_invoice",
        "sale_id": sid,
        "buyer": {
            "name": "Synthetic Invoice Buyer",
            "address": "Synthetic Invoice Address",
            "tax_id": "0123456789012",
            "branch": "00002",
        },
    }
    invalid = {**payload, "buyer": {**payload["buyer"], "branch": "12"}}
    assert post(client, owner, "/api/extended/documents", invalid).status_code == 400
    issued = post(client, owner, "/api/extended/documents", payload)
    assert issued.status_code == 201
    html = client.get(f"/api/extended/documents/{issued.json['id']}/print?paper=a4").data.decode()
    assert "Synthetic Test Partnership" in html
    assert "Synthetic Invoice Buyer" in html and "Synthetic Invoice Address" in html and "สาขา 00002" in html
    assert "ข้อมูลทดสอบเท่านั้น" in html
    assert post(client, owner, "/api/extended/documents", {"kind": "tax_invoice", "sale_id": sid}).status_code == 200
    assert client.get(f"/api/extended/documents/{issued.json['id']}/print?paper=invalid").status_code == 400
    thermal = f"/api/extended/documents/{issued.json['id']}/thermal"
    assert client.get(thermal).json["snapshot"]["sale"]["customer_branch"] == "00002"
    login(client, "warehouse")
    assert client.get(thermal).status_code == 403


def make_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    result = BytesIO()
    wb.save(result)
    result.seek(0)
    return result


def test_excel_import_export_and_formula_rejection(client, app):
    token = login(client)
    f = make_xlsx([("sku", "name", "price"), ("NEW-TEST-1", "Sample product", "12.50")])
    result = client.post(
        "/api/extended/excel/products/import",
        data={"file": (f, "products.xlsx")},
        content_type="multipart/form-data",
        headers={"X-CSRFToken": token},
    )
    assert result.status_code == 201 and result.json["imported"] == 1
    with_stock = make_xlsx([("sku", "name", "price", "stock"), ("NEW-TEST-2", "Stocked item", "5.00", 4)])
    with_stock_result = client.post(
        "/api/extended/excel/products/import",
        data={"file": (with_stock, "with-stock.xlsx")},
        content_type="multipart/form-data",
        headers={"X-CSRFToken": token},
    )
    assert with_stock_result.status_code == 201
    with app.app_context():
        assert db.session.scalar(db.select(Product.stock).where(Product.sku == "NEW-TEST-2")) == 4
    exported = client.get("/api/extended/excel/products")
    assert exported.status_code == 200
    wb = load_workbook(BytesIO(exported.data), read_only=True)
    assert list(wb.active.values)[1][:3] == ("NEW-TEST-1", "Sample product", "12.50")
    wb.close()
    bad = make_xlsx([("sku", "name", "price"), ("=HYPERLINK('x')", "invalid", "1.00")])
    rejected = client.post(
        "/api/extended/excel/products/import",
        data={"file": (bad, "bad.xlsx")},
        content_type="multipart/form-data",
        headers={"X-CSRFToken": token},
    )
    assert rejected.status_code == 400
    with app.app_context():
        assert db.session.query(Product).count() == 2
    staff = login(client, "sales")
    customer_export = client.get("/api/extended/excel/customers")
    assert customer_export.status_code == 200
    customer_book = load_workbook(BytesIO(customer_export.data), read_only=True)
    assert next(iter(customer_book.active.values)) == ("name", "address", "tax_id")
    customer_book.close()
    forbidden = client.post(
        "/api/extended/excel/products/import",
        data={"file": (make_xlsx([("sku", "name", "price")]), "bad.xlsx")},
        content_type="multipart/form-data",
        headers={"X-CSRFToken": staff},
    )
    assert forbidden.status_code == 403


def test_customer_excel_import_accepts_common_thai_headers(client, app):
    token = login(client)
    workbook = make_xlsx(
        [
            ("ชื่อลูกค้า", "ที่อยู่จัดส่ง", "เลขประจำตัวผู้เสียภาษี"),
            ("ร้านทดสอบ ภาษาไทย", "99 ถนนสุขุมวิท สมุทรปราการ", "1234567890123"),
        ]
    )

    result = client.post(
        "/api/extended/excel/customers/import",
        data={"file": (workbook, "customers-th.xlsx")},
        content_type="multipart/form-data",
        headers={"X-CSRFToken": token},
    )

    assert result.status_code == 201
    assert result.json == {"entity": "customers", "imported": 1}
    with app.app_context():
        customer = db.session.scalar(db.select(Customer).where(Customer.name == "ร้านทดสอบ ภาษาไทย"))
        assert customer.address == "99 ถนนสุขุมวิท สมุทรปราการ"
        assert customer.tax_id == "1234567890123"


def test_product_images_owner_or_warehouse_only(client, app, seeded):
    owner, pid, _ = seeded
    image = Image.new("RGB", (80, 50), (128, 128, 128))
    buf = BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    upload = client.post(
        f"/api/extended/products/{pid}/image",
        data={"image": (buf, "synthetic.png")},
        content_type="multipart/form-data",
        headers={"X-CSRFToken": owner},
    )
    assert upload.status_code == 201
    fetched = client.get(f"/api/extended/products/{pid}/image")
    assert fetched.status_code == 200 and fetched.mimetype == "image/jpeg"
    with app.app_context():
        assert db.session.query(ProductImage).count() == 1
    sales = login(client, "sales")
    attempt = client.post(
        f"/api/extended/products/{pid}/image",
        data={"image": (BytesIO(b"bad"), "x.png")},
        content_type="multipart/form-data",
        headers={"X-CSRFToken": sales},
    )
    assert attempt.status_code == 403
