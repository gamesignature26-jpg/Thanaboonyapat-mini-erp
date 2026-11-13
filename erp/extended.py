"""Staging-only ERP extensions: staff-priced sales, images, payment history,
company profile, immutable test documents and guarded XLSX transfers.

Feature branch only. Do not issue legally effective documents until approved.
"""

import hashlib
import json
from datetime import UTC, datetime
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, g, render_template, request, send_file
from openpyxl import Workbook, load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import CheckConstraint, UniqueConstraint

from . import data, integer, money, roles, text
from .models import Customer, Payment, Product, Sale, SaleLine, StockMovement, db

bp = Blueprint("erp_extended", __name__)
MAX_IMAGE = 1024 * 1024  # bytes, before normalization
MAX_XLSX = 2 * 1024 * 1024
MAX_ROWS = 1000


CUSTOMER_XLSX_HEADERS = {
    "name": {"name", "customer name", "customer_name", "ชื่อ", "ชื่อลูกค้า", "ชื่อร้าน", "ชื่อร้านค้า", "ลูกค้า"},
    "address": {"address", "customer address", "customer_address", "ที่อยู่", "ที่อยู่ลูกค้า", "ที่อยู่จัดส่ง"},
    "tax_id": {
        "tax id",
        "tax_id",
        "taxid",
        "เลขผู้เสียภาษี",
        "เลขผู้เสียภาษีอากร",
        "เลขประจำตัวผู้เสียภาษี",
        "เลขประจำตัวผู้เสียภาษีอากร",
        "เลขผู้เสียภาษี 13 หลัก",
        "เลขประจำตัวผู้เสียภาษี 13 หลัก",
    },
}


def now():
    return datetime.now(UTC)


class CustomerPrice(db.Model):
    __tablename__ = "customer_price"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.ForeignKey("customer.id"), nullable=False)
    product_id = db.Column(db.ForeignKey("product.id"), nullable=False)
    price = db.Column(db.Numeric(14, 2), nullable=False)
    updated_by = db.Column(db.ForeignKey("user.id"), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_customer_price_positive"),
        UniqueConstraint("customer_id", "product_id", name="uq_customer_price_pair"),
    )


class ProductImage(db.Model):
    __tablename__ = "product_image"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.ForeignKey("product.id"), nullable=False, unique=True)
    image_data = db.Column(db.LargeBinary, nullable=False)
    digest = db.Column(db.String(64), nullable=False)
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)


class CompanyProfile(db.Model):
    __tablename__ = "company_profile"
    id = db.Column(db.Integer, primary_key=True)
    legal_name = db.Column(db.String(200), nullable=False)
    tax_id = db.Column(db.String(13), nullable=False, default="")
    branch = db.Column(db.String(100), nullable=False, default="สำนักงานใหญ่")
    address = db.Column(db.String(1000), nullable=False, default="")
    phone = db.Column(db.String(30), nullable=False, default="")
    receipt_footer = db.Column(db.String(250), nullable=False, default="ขอบคุณที่อุดหนุน")
    default_paper = db.Column(db.String(4), nullable=False, default="a4")


class IssuedDocument(db.Model):
    __tablename__ = "issued_document"
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)
    number = db.Column(db.String(40), unique=True)
    sale_id = db.Column(db.ForeignKey("sale.id"), nullable=False)
    # Two nullable unique columns enforce invoice-per-sale / receipt-per-payment in PostgreSQL and SQLite.
    tax_sale_id = db.Column(db.ForeignKey("sale.id"), unique=True)
    payment_id = db.Column(db.ForeignKey("payment.id"), unique=True)
    snapshot_json = db.Column(db.Text, nullable=False)
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint(
            "(kind = 'tax_invoice' AND tax_sale_id IS NOT NULL AND payment_id IS NULL) "
            "OR (kind = 'receipt' AND tax_sale_id IS NULL AND payment_id IS NOT NULL)",
            name="ck_issued_document_kind_link",
        ),
    )


def _company():
    row = db.session.get(CompanyProfile, 1)
    if row is None:
        row = CompanyProfile(id=1, legal_name="หจก. ธนาบุณยภัทร")
        db.session.add(row)
        db.session.flush()
    return row


def _profile_json(row):
    return {
        k: getattr(row, k)
        for k in ("legal_name", "tax_id", "branch", "address", "phone", "receipt_footer", "default_paper")
    }


def _digits13(value):
    return isinstance(value, str) and len(value) == 13 and value.isascii() and value.isdigit()


@bp.route("/api/extended/company", methods=["GET", "POST"])
@roles()
def company():
    if request.method == "GET":
        row = db.session.get(CompanyProfile, 1)
        return _profile_json(row) if row else _profile_json(CompanyProfile(legal_name="หจก. ธนาบุณยภัทร"))
    body = data()
    new_name = text(body, "legal_name", 200)
    tax_id = body.get("tax_id", "")
    if not isinstance(tax_id, str) or (tax_id and not _digits13(tax_id)):
        abort(400, "Company tax ID must contain 13 digits")
    values = {
        "legal_name": new_name,
        "tax_id": tax_id,
        "branch": text(body, "branch", 100),
        "address": text(body, "address", 1000),
        "phone": body.get("phone", ""),
        "receipt_footer": body.get("receipt_footer", "ขอบคุณที่อุดหนุน"),
        "default_paper": body.get("default_paper", "a4"),
    }
    if values["default_paper"] not in ("a4", "58"):
        abort(400, "Invalid default paper size")
    for key, maximum in (("phone", 30), ("receipt_footer", 250)):
        if not isinstance(values[key], str) or len(values[key]) > maximum:
            abort(400, f"Invalid {key}")
    row = _company()
    for key, value in values.items():
        setattr(row, key, value.strip() if isinstance(value, str) else value)
    db.session.commit()
    return _profile_json(row)


@bp.get("/api/extended/prices/<int:customer_id>")
@roles("sales", "accountant")
def prices(customer_id):
    db.get_or_404(Customer, customer_id)
    rows = db.session.scalars(db.select(CustomerPrice).where(CustomerPrice.customer_id == customer_id)).all()
    return {"items": [{"product_id": x.product_id, "price": str(x.price)} for x in rows]}


@bp.post("/api/extended/prices")
@roles("sales")
def set_price():
    body = data()
    customer_id, product_id = integer(body.get("customer_id")), integer(body.get("product_id"))
    db.get_or_404(Customer, customer_id)
    db.get_or_404(Product, product_id)
    price = money(body.get("price"))
    if price <= 0:
        abort(400, "Price must be positive")
    row = db.session.scalar(
        db.select(CustomerPrice)
        .where(CustomerPrice.customer_id == customer_id, CustomerPrice.product_id == product_id)
        .with_for_update()
    )
    if row is None:
        row = CustomerPrice(customer_id=customer_id, product_id=product_id)
        db.session.add(row)
    row.price, row.updated_by, row.updated_at = price, g.user.id, now()
    db.session.commit()
    return {"customer_id": customer_id, "product_id": product_id, "price": str(price)}


@bp.delete("/api/extended/prices/<int:customer_id>/<int:product_id>")
@roles("sales")
def remove_price(customer_id, product_id):
    row = db.session.scalar(
        db.select(CustomerPrice).where(CustomerPrice.customer_id == customer_id, CustomerPrice.product_id == product_id)
    )
    if row is None:
        abort(404)
    db.session.delete(row)
    db.session.commit()
    return "", 204


@bp.get("/api/extended/product-images")
@roles("sales", "warehouse", "accountant")
def images_list():
    return {"ids": list(db.session.scalars(db.select(ProductImage.product_id)))}


@bp.route("/api/extended/products/<int:product_id>/image", methods=["GET", "POST"])
@roles("sales", "warehouse", "accountant")
def product_image(product_id):
    db.get_or_404(Product, product_id)
    row = db.session.scalar(db.select(ProductImage).where(ProductImage.product_id == product_id))
    if request.method == "GET":
        if row is None:
            abort(404)
        return send_file(BytesIO(row.image_data), mimetype="image/jpeg", download_name=f"product-{product_id}.jpg")
    if g.user.role not in ("admin", "warehouse"):
        abort(403)
    file = request.files.get("image")
    if file is None:
        abort(400, "Missing image")
    raw = file.stream.read(MAX_IMAGE + 1)
    if not raw or len(raw) > MAX_IMAGE:
        abort(413, "Image must be at most 1 MB")
    try:
        # Decoding normalizes metadata and rejects SVG/scripts and invalid image bytes.
        with Image.open(BytesIO(raw)) as img:
            if img.format not in ("PNG", "JPEG", "WEBP") or img.width * img.height > 8_000_000:
                abort(400, "Unsupported image dimensions or format")
            img.load()
            rgb = img.convert("RGB")
            rgb.thumbnail((1200, 1200))
            buf = BytesIO()
            rgb.save(buf, format="JPEG", quality=80, optimize=True)
            normalized = buf.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        abort(400, "Invalid image")
    if len(normalized) > MAX_IMAGE:
        abort(413, "Normalized image too large")
    if row is None:
        row = ProductImage(product_id=product_id)
        db.session.add(row)
    row.image_data = normalized
    row.digest = hashlib.sha256(normalized).hexdigest()
    row.actor_id = g.user.id
    row.created_at = now()
    db.session.commit()
    return {"product_id": product_id, "image_url": f"/api/extended/products/{product_id}/image"}, 201


@bp.get("/api/extended/sales/<int:sale_id>/payments")
@roles("sales", "accountant")
def payment_history(sale_id):
    sale = db.get_or_404(Sale, sale_id)
    from .online import OnlinePaymentMethod

    rows = db.session.execute(
        db.select(Payment, OnlinePaymentMethod.method)
        .outerjoin(OnlinePaymentMethod, OnlinePaymentMethod.payment_id == Payment.id)
        .where(Payment.sale_id == sale_id)
        .order_by(Payment.id)
    ).all()
    return {
        "sale_id": sale.id,
        "buyer": {"name": sale.customer_name, "address": sale.customer_address, "tax_id": sale.customer_tax_id or ""},
        "total": str(sale.total),
        "paid": str(sale.paid),
        "balance": str(sale.total - sale.paid),
        "payments": [
            {
                "id": p.id,
                "amount": str(p.amount),
                "method": method or "unknown",
                "reference": p.reference,
                "actor_id": p.actor_id,
                "date": p.created_at.isoformat() if p.created_at else None,
            }
            for p, method in rows
        ],
    }


def _snapshot(sale, company_row, payment=None):
    from .online import OnlineOrder, OnlinePaymentMethod

    info = _profile_json(company_row)
    result = {
        "company": info,
        "sale": {
            "id": sale.id,
            "customer_name": sale.customer_name,
            "customer_tax_id": sale.customer_tax_id or "",
            "customer_address": sale.customer_address,
            "subtotal": str(sale.subtotal),
            "vat_rate": str(sale.vat_rate),
            "vat_price_mode": sale.vat_price_mode,
            "vat": str(sale.vat),
            "total": str(sale.total),
            "lines": [
                {
                    "sku": x.sku,
                    "name": x.name,
                    "quantity": x.quantity,
                    "price": str(x.price),
                    "total": str(x.price * x.quantity),
                }
                for x in db.session.scalars(
                    db.select(SaleLine).where(SaleLine.sale_id == sale.id).order_by(SaleLine.id)
                )
            ],
        },
    }
    order = db.session.scalar(db.select(OnlineOrder).where(OnlineOrder.sale_id == sale.id))
    if order:
        result["order"] = {"discount": str(order.discount), "shipping_fee": str(order.shipping_fee)}
    if payment:
        method = db.session.scalar(
            db.select(OnlinePaymentMethod.method).where(OnlinePaymentMethod.payment_id == payment.id)
        )
        result["payment"] = {
            "id": payment.id,
            "amount": str(payment.amount),
            "method": method or "unknown",
            "reference": payment.reference,
            "date": payment.created_at.isoformat(),
        }
    return result


@bp.post("/api/extended/documents")
@roles("accountant")
def issue_document():
    body = data()
    kind = body.get("kind")
    if kind not in ("receipt", "tax_invoice"):
        abort(400, "Invalid document kind")
    sale_id = integer(body.get("sale_id"))
    sale = db.session.get(Sale, sale_id, with_for_update=True)
    if sale is None:
        abort(404)
    if kind == "tax_invoice":
        existing = db.session.scalar(db.select(IssuedDocument).where(IssuedDocument.tax_sale_id == sale_id))
    else:
        payment_id = integer(body.get("payment_id"))
        payment = db.session.get(Payment, payment_id)
        if payment is None or payment.sale_id != sale_id:
            abort(404, "Payment does not belong to sale")
        existing = db.session.scalar(db.select(IssuedDocument).where(IssuedDocument.payment_id == payment_id))
    if existing:
        return {"id": existing.id, "number": existing.number, "duplicate": True}, 200
    profile = _company()
    buyer = None
    if kind == "tax_invoice" and "buyer" in body:
        fields = body["buyer"]
        if not isinstance(fields, dict):
            abort(400, "ข้อมูลผู้ซื้อไม่ถูกต้อง")
        buyer = {key: text(fields, key, limit) for key, limit in (("name", 200), ("address", 1000), ("tax_id", 13))}
        branch = fields.get("branch", "")
        if branch not in ("", "00000") and not (
            isinstance(branch, str) and len(branch) == 5 and branch.isascii() and branch.isdecimal()
        ):
            abort(400, "กรอกรหัสสาขา 5 หลัก หรือเว้นว่างหากไม่มีสาขา")
        buyer["branch"] = branch
    if kind == "tax_invoice" and (not _digits13(profile.tax_id) or not profile.address):
        abort(409, "กรอกเลขผู้เสียภาษีและที่อยู่ผู้ขายในเมนูตั้งค่าบริษัทก่อน")
    if kind == "tax_invoice" and (
        not _digits13(buyer["tax_id"] if buyer else sale.customer_tax_id or "")
        or not (buyer["address"] if buyer else sale.customer_address)
    ):
        abort(409, "กรอกชื่อ ที่อยู่ และเลขผู้เสียภาษี 13 หลักของผู้ซื้อให้ครบ")
    snap = _snapshot(sale, profile, payment if kind == "receipt" else None)
    if buyer:
        snap["sale"].update({f"customer_{key}": value for key, value in buyer.items()})
    row = IssuedDocument(
        kind=kind,
        sale_id=sale.id,
        tax_sale_id=sale.id if kind == "tax_invoice" else None,
        payment_id=payment.id if kind == "receipt" else None,
        snapshot_json=json.dumps(snap, ensure_ascii=False, separators=(",", ":")),
        actor_id=g.user.id,
    )
    db.session.add(row)
    db.session.flush()
    row.number = f"{'TAX' if kind == 'tax_invoice' else 'RCT'}-{row.id:08d}"
    db.session.commit()
    return {"id": row.id, "number": row.number, "duplicate": False}, 201


@bp.get("/api/extended/sales/<int:sale_id>/documents")
@roles("sales", "accountant")
def sale_documents(sale_id):
    db.get_or_404(Sale, sale_id)
    rows = db.session.scalars(
        db.select(IssuedDocument).where(IssuedDocument.sale_id == sale_id).order_by(IssuedDocument.id)
    )
    return {"items": [{"id": x.id, "number": x.number, "kind": x.kind, "date": x.issued_at.isoformat()} for x in rows]}


@bp.get("/api/extended/documents/<int:document_id>/thermal")
@roles("sales", "accountant")
def thermal_document(document_id):
    row = db.get_or_404(IssuedDocument, document_id)
    issued = row.issued_at
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    return {
        "number": row.number,
        "kind": row.kind,
        "issued": issued.astimezone(ZoneInfo("Asia/Bangkok")).strftime("%Y-%m-%d %H:%M"),
        "snapshot": json.loads(row.snapshot_json),
    }


@bp.get("/api/extended/documents/<int:document_id>/print")
@roles("sales", "accountant")
def print_document(document_id):
    row = db.get_or_404(IssuedDocument, document_id)
    snapshot = json.loads(row.snapshot_json)
    paper = request.args.get("paper", snapshot["company"].get("default_paper", "a4"))
    if paper not in ("a4", "58"):
        abort(400, "Unsupported paper")
    issued = row.issued_at
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    return render_template(
        "extended_document.html",
        document=row,
        snapshot=snapshot,
        paper=paper,
        issued_local=issued.astimezone(ZoneInfo("Asia/Bangkok")),
    )


def _sanitized(value):
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


@bp.get("/api/extended/excel/<string:entity>")
@roles("sales", "accountant")
def export_excel(entity):
    if entity not in ("products", "customers"):
        abort(404)
    if entity == "products" and g.user.role not in ("admin", "accountant"):
        abort(403)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(title=entity)
    if entity == "products":
        ws.append(("sku", "name", "price", "stock"))
        records = db.session.scalars(db.select(Product).order_by(Product.id).execution_options(yield_per=500))
        for p in records:
            ws.append((_sanitized(p.sku), _sanitized(p.name), str(p.price), p.stock))
    else:
        ws.append(("name", "address", "tax_id"))
        records = db.session.scalars(db.select(Customer).order_by(Customer.id).execution_options(yield_per=500))
        for c in records:
            ws.append((_sanitized(c.name), _sanitized(c.address), _sanitized(c.tax_id or "")))
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name=f"erp-{entity}.xlsx",
        as_attachment=True,
    )


def _cell_string(value, maxlen, required=True):
    if not isinstance(value, str) or len(value) > maxlen or (required and not value.strip()):
        abort(400, "Invalid Excel cell text")
    if value.lstrip().startswith(("=", "+", "-", "@")):
        abort(400, "Formula-like cells are not accepted for import")
    return value.strip()


def _customer_header_positions(header):
    """Return canonical customer columns for supported Thai/English XLSX templates."""
    if not isinstance(header, tuple) or len(header) != 3:
        return None
    normalized = []
    for value in header:
        if not isinstance(value, str):
            return None
        normalized.append(" ".join(value.lstrip("\ufeff").replace("_", " ").replace("-", " ").split()).casefold())
    positions = {}
    for index, value in enumerate(normalized):
        matches = [field for field, aliases in CUSTOMER_XLSX_HEADERS.items() if value in aliases]
        if len(matches) != 1 or matches[0] in positions:
            return None
        positions[matches[0]] = index
    return positions if set(positions) == {"name", "address", "tax_id"} else None


@bp.post("/api/extended/excel/<string:entity>/import")
@roles()
def import_excel(entity):
    if entity not in ("products", "customers"):
        abort(404)
    file = request.files.get("file")
    if file is None or not file.filename.lower().endswith(".xlsx"):
        abort(400, "An .xlsx file is required")
    payload = file.stream.read(MAX_XLSX + 1)
    if len(payload) > MAX_XLSX:
        abort(413, "Excel upload exceeds 2 MB")
    try:
        with ZipFile(BytesIO(payload)) as archive:
            entries = archive.infolist()
            if len(entries) > 128 or sum(entry.file_size for entry in entries) > 16 * 1024 * 1024:
                abort(413, "Expanded Excel file exceeds limits")
        wb = load_workbook(BytesIO(payload), read_only=True, data_only=False, keep_links=False)
    except (BadZipFile, InvalidFileException, ValueError, OSError, KeyError, EOFError):
        abort(400, "Invalid Excel file")
    try:
        if len(wb.sheetnames) != 1:
            abort(400, "Upload exactly one worksheet")
        ws = wb.active
        if (ws.max_column or 0) > 4 or (ws.max_row or 0) > MAX_ROWS + 1:
            abort(413, "Excel worksheet exceeds row or column limits")
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None)
        accepted = (("sku", "name", "price"), ("sku", "name", "price", "stock"))
        customer_positions = _customer_header_positions(tuple(header)) if header is not None else None
        if (
            header is None
            or (entity == "products" and tuple(header) not in accepted)
            or (entity == "customers" and customer_positions is None)
        ):
            abort(400, f"Unexpected XLSX headers for {entity}")
        stock_column = entity == "products" and len(header) == 4
        added = 0
        seen = set()
        for i, values in enumerate(rows, 2):
            if i > MAX_ROWS + 1:
                abort(413, "Only 1000 data rows allowed")
            if not values or all(v is None for v in values):
                continue
            if len(values) != len(header) or any(isinstance(v, str) and v.startswith("=") for v in values):
                abort(400, f"Invalid row {i}")
            if entity == "products":
                sku, name = _cell_string(values[0], 80), _cell_string(values[1], 200)
                if sku in seen or db.session.scalar(db.select(Product.id).where(Product.sku == sku)):
                    abort(409, f"Duplicate SKU at row {i}")
                seen.add(sku)
                price = money(str(values[2]))
                opening_stock = values[3] if stock_column else 0
                if type(opening_stock) is not int or opening_stock < 0 or opening_stock > 1_000_000:
                    abort(400, f"Invalid opening stock at row {i}")
                product = Product(sku=sku, name=name, price=price, stock=opening_stock)
                db.session.add(product)
                if opening_stock:
                    db.session.flush()
                    db.session.add(
                        StockMovement(
                            product_id=product.id,
                            delta=opening_stock,
                            reason="Excel opening stock (synthetic/staging)",
                            actor_id=g.user.id,
                        )
                    )
            else:
                name = _cell_string(values[customer_positions["name"]], 200)
                address = _cell_string(values[customer_positions["address"]], 1000)
                tax_id = values[customer_positions["tax_id"]] or None
                if tax_id is not None and not _digits13(tax_id):
                    abort(400, f"Invalid customer tax ID at row {i}: preserve as text")
                key = (name, address, tax_id)
                if key in seen:
                    abort(409, f"Duplicate customer at row {i}")
                seen.add(key)
                exists = db.session.scalar(
                    db.select(Customer.id).where(
                        Customer.name == name, Customer.address == address, Customer.tax_id == tax_id
                    )
                )
                if exists:
                    abort(409, f"Customer already exists at row {i}")
                db.session.add(Customer(name=name, address=address, tax_id=tax_id))
            added += 1
        if added == 0:
            abort(400, "No rows to import")
        db.session.commit()
    finally:
        wb.close()
    return {"imported": added, "entity": entity}, 201


def install_extended(app):
    app.register_blueprint(bp)
