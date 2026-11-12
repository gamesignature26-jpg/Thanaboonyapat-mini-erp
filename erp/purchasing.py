"""Supplier purchase drafts and warehouse receiving, isolated from tax/payment ledgers.

Purchase costs are snapshots for future costing work; there is NO automatic COGS,
purchase VAT, supplier payment, credit note, or posted accounting entry.
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from flask import Blueprint, abort, g, request
from sqlalchemy import CheckConstraint, UniqueConstraint

from . import data, integer, money, roles, text
from .models import Product, StockMovement, db

bp = Blueprint("purchasing", __name__)
NOTICE = "PURCHASE INTAKE - NOT A TAX INVOICE"
MAX_TOTAL = Decimal("999999999.99")


class Supplier(db.Model):
    __tablename__ = "supplier"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    tax_id = db.Column(db.String(13))
    address = db.Column(db.String(1000), nullable=False, default="")
    created_by = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class PurchaseOrder(db.Model):
    __tablename__ = "purchase_order"
    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(80), unique=True, nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    supplier_id = db.Column(db.ForeignKey("supplier.id"), nullable=False)
    supplier_name = db.Column(db.String(200), nullable=False)
    supplier_tax_id = db.Column(db.String(13))
    supplier_address = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(12), nullable=False, default="draft")
    subtotal_cost = db.Column(db.Numeric(14, 2), nullable=False)
    note = db.Column(db.String(600), nullable=False, default="")
    created_by = db.Column(db.ForeignKey("user.id"), nullable=False)
    received_by = db.Column(db.ForeignKey("user.id"))
    receipt_note = db.Column(db.String(600))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    received_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('draft','received')"),
        CheckConstraint("subtotal_cost >= 0"),
    )


class PurchaseOrderLine(db.Model):
    __tablename__ = "purchase_order_line"
    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.ForeignKey("purchase_order.id"), nullable=False)
    product_id = db.Column(db.ForeignKey("product.id"), nullable=False)
    sku = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(db.Numeric(14, 2), nullable=False)
    __table_args__ = (
        CheckConstraint("quantity > 0 AND unit_cost > 0"),
        UniqueConstraint("purchase_id", "product_id", name="uq_purchase_order_product"),
    )


def _amount(value):
    return f"{Decimal(value):.2f}"


def _page_int(name, default, maximum):
    raw = request.args.get(name)
    if raw is None:
        return default
    if not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= maximum:
        abort(400, f"Invalid {name}")
    return int(raw)


def _supplier(row):
    return {
        "id": row.id,
        "name": row.name,
        "tax_id": row.tax_id,
        "address": row.address,
    }


def _summary(row):
    return {
        "id": row.id,
        "number": f"PO-DRAFT-{row.id:06d}",
        "supplier_name": row.supplier_name,
        "status": row.status,
        "subtotal_cost": _amount(row.subtotal_cost),
        "created_at": row.created_at.isoformat(),
        "received_at": row.received_at.isoformat() if row.received_at else None,
        "received_by": row.received_by,
        "notice": NOTICE,
    }


def _detail(row):
    return {
        **_summary(row),
        "supplier": {
            "id": row.supplier_id,
            "name": row.supplier_name,
            "tax_id": row.supplier_tax_id,
            "address": row.supplier_address,
        },
        "note": row.note,
        "created_by": row.created_by,
        "receipt_note": row.receipt_note,
        "lines": [
            {
                "product_id": line.product_id,
                "sku": line.sku,
                "name": line.name,
                "quantity": line.quantity,
                "unit_cost": _amount(line.unit_cost),
                "line_total_cost": _amount(line.quantity * line.unit_cost),
            }
            for line in db.session.scalars(
                db.select(PurchaseOrderLine)
                .where(PurchaseOrderLine.purchase_id == row.id)
                .order_by(PurchaseOrderLine.product_id)
            )
        ],
    }


@bp.get("/api/suppliers")
@roles("warehouse", "accountant")
def suppliers():
    limit = _page_int("limit", 50, 100)
    after = _page_int("after", 0, 1000000000)
    query = db.select(Supplier)
    if after:
        query = query.where(Supplier.id > after)
    rows = list(db.session.scalars(query.order_by(Supplier.id).limit(limit + 1)))
    items = rows[:limit]
    return {
        "items": [_supplier(row) for row in items],
        "next_after": items[-1].id if len(rows) > limit else None,
    }


@bp.post("/api/suppliers")
@roles("accountant")
def create_supplier():
    body = data()
    if set(body) - {"name", "tax_id", "address"}:
        abort(400, "Unknown supplier field")
    name = text(body, "name", 200)
    tax_id = body.get("tax_id")
    if tax_id not in (None, ""):
        if not isinstance(tax_id, str) or len(tax_id) != 13 or not tax_id.isascii() or not tax_id.isdecimal():
            abort(400, "Tax ID must contain 13 ASCII digits")
    else:
        tax_id = None
    address = body.get("address", "")
    if not isinstance(address, str) or len(address) > 1000:
        abort(400, "Invalid supplier address")
    row = Supplier(name=name, tax_id=tax_id, address=address.strip(), created_by=g.user.id)
    db.session.add(row)
    db.session.commit()
    return _supplier(row), 201


@bp.post("/api/purchases")
@roles("accountant")
def create_purchase():
    body = data()
    if set(body) - {"request_key", "supplier_id", "lines", "note"}:
        abort(400, "Unknown purchase field")
    key = text(body, "request_key", 80)
    if len(key) < 16:
        abort(400, "Request key too short")
    fingerprint = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    previous = db.session.scalar(db.select(PurchaseOrder).where(PurchaseOrder.request_key == key))
    if previous:
        if previous.request_hash != fingerprint:
            abort(409, "Purchase request key already used")
        return {**_summary(previous), "duplicate": True}, 200
    supplier_id = integer(body.get("supplier_id"))
    vendor = db.session.get(Supplier, supplier_id)
    if vendor is None:
        abort(404, "Supplier not found")
    note = body.get("note", "")
    if not isinstance(note, str) or len(note) > 600:
        abort(400, "Invalid purchase note")
    lines = body.get("lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        abort(400, "Expected 1-100 purchase lines")
    quantities = {}
    costs = {}
    for line in lines:
        if not isinstance(line, dict) or set(line) != {"product_id", "quantity", "unit_cost"}:
            abort(400, "Invalid purchase line")
        product_id = integer(line["product_id"])
        if product_id in quantities:
            abort(400, "Duplicate product")
        quantities[product_id] = integer(line["quantity"])
        cost = money(line["unit_cost"])
        if cost <= 0:
            abort(400, "Unit cost must be positive")
        costs[product_id] = cost
    products = list(
        db.session.scalars(db.select(Product).where(Product.id.in_(quantities)).order_by(Product.id))
    )
    if len(products) != len(quantities):
        abort(404, "Product not found")
    subtotal = sum((costs[p.id] * quantities[p.id] for p in products), Decimal("0.00"))
    if subtotal > MAX_TOTAL:
        abort(400, "Purchase total too large")
    row = PurchaseOrder(
        request_key=key,
        request_hash=fingerprint,
        supplier_id=vendor.id,
        supplier_name=vendor.name,
        supplier_tax_id=vendor.tax_id,
        supplier_address=vendor.address,
        status="draft",
        subtotal_cost=subtotal,
        note=note.strip(),
        created_by=g.user.id,
    )
    db.session.add(row)
    db.session.flush()
    db.session.add_all(
        PurchaseOrderLine(
            purchase_id=row.id,
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=quantities[product.id],
            unit_cost=costs[product.id],
        )
        for product in products
    )
    db.session.commit()
    return {**_summary(row), "duplicate": False}, 201


@bp.get("/api/purchases")
@roles("warehouse", "accountant")
def purchases_list():
    limit = _page_int("limit", 50, 100)
    before = _page_int("before", 0, 1000000000)
    query = db.select(PurchaseOrder)
    if before:
        query = query.where(PurchaseOrder.id < before)
    rows = list(db.session.scalars(query.order_by(PurchaseOrder.id.desc()).limit(limit + 1)))
    items = rows[:limit]
    return {
        "items": [_summary(row) for row in items],
        "next_before": items[-1].id if len(rows) > limit else None,
    }


@bp.get("/api/purchases/<int:purchase_id>")
@roles("warehouse", "accountant")
def purchase_detail(purchase_id):
    return _detail(db.get_or_404(PurchaseOrder, purchase_id))


@bp.post("/api/purchases/<int:purchase_id>/receive")
@roles("warehouse")
def receive_purchase(purchase_id):
    body = data()
    if set(body) != {"receipt_note"}:
        abort(400, "Expected receipt_note")
    receipt_note = text(body, "receipt_note", 600)
    row = db.session.scalar(
        db.select(PurchaseOrder).where(PurchaseOrder.id == purchase_id).with_for_update()
    )
    if row is None:
        abort(404)
    if row.status == "received":
        if row.receipt_note != receipt_note:
            abort(409, "Purchase already received with different note")
        return {**_summary(row), "duplicate": True}
    if row.status != "draft":
        abort(409, "Purchase cannot be received")
    lines = list(
        db.session.scalars(
            db.select(PurchaseOrderLine)
            .where(PurchaseOrderLine.purchase_id == row.id)
            .order_by(PurchaseOrderLine.product_id)
        )
    )
    if not lines:
        abort(409, "Empty purchase order")
    products = list(
        db.session.scalars(
            db.select(Product)
            .where(Product.id.in_(line.product_id for line in lines))
            .order_by(Product.id)
            .with_for_update()
        )
    )
    by_id = {product.id: product for product in products}
    if len(by_id) != len(lines):
        abort(409, "Product removed since purchase draft")
    for line in lines:
        product = by_id[line.product_id]
        if product.stock + line.quantity > 1000000000:
            abort(409, "Stock exceeds maximum")
        product.stock += line.quantity
        db.session.add(
            StockMovement(
                product_id=product.id,
                delta=line.quantity,
                reason=f"Supplier purchase received #{row.id}",
                actor_id=g.user.id,
            )
        )
    row.status = "received"
    row.receipt_note = receipt_note
    row.received_by = g.user.id
    row.received_at = datetime.now(UTC)
    db.session.commit()
    return {**_summary(row), "duplicate": False}
