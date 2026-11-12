"""Audited customer-return intake, isolated from tax credit notes and receivables.

Drafts make no stock movement. Warehouse staff may receive physically verified
returns; only resellable returned units increase sellable stock. Sales/payment
balances are never changed by this module.
"""

import hashlib
import json
from datetime import UTC, datetime

from flask import Blueprint, abort, g, request
from sqlalchemy import CheckConstraint, UniqueConstraint, func

from . import data, integer, roles, text
from .models import Product, Sale, SaleLine, StockMovement, db

bp = Blueprint("return_intake", __name__)
NOTICE = "RETURN INTAKE - NOT A TAX CREDIT NOTE"


class ReturnIntake(db.Model):
    __tablename__ = "return_intake"
    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(80), nullable=False, unique=True)
    request_hash = db.Column(db.String(64), nullable=False)
    sale_id = db.Column(db.ForeignKey("sale.id"), nullable=False)
    reason = db.Column(db.String(600), nullable=False)
    status = db.Column(db.String(12), nullable=False, default="draft")
    condition = db.Column(db.String(12))
    inspection_note = db.Column(db.String(600))
    created_by = db.Column(db.ForeignKey("user.id"), nullable=False)
    inspected_by = db.Column(db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    inspected_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('draft','received','rejected')"),
        CheckConstraint("condition IS NULL OR condition IN ('resellable','damaged')"),
    )


class ReturnIntakeLine(db.Model):
    __tablename__ = "return_intake_line"
    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.ForeignKey("return_intake.id"), nullable=False)
    sale_line_id = db.Column(db.ForeignKey("sale_line.id"), nullable=False)
    product_id = db.Column(db.ForeignKey("product.id"), nullable=False)
    sku = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    __table_args__ = (
        CheckConstraint("quantity > 0"),
        UniqueConstraint("return_id", "sale_line_id", name="uq_return_intake_line"),
    )


def _positive_arg(name, default, maximum):
    raw = request.args.get(name)
    if raw is None:
        return default
    if not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= maximum:
        abort(400, f"Invalid {name}")
    return int(raw)


def _lines(return_id):
    return list(
        db.session.scalars(
            db.select(ReturnIntakeLine)
            .where(ReturnIntakeLine.return_id == return_id)
            .order_by(ReturnIntakeLine.sale_line_id)
        )
    )


def _received_counts(line_ids):
    if not line_ids:
        return {}
    query = (
        db.select(ReturnIntakeLine.sale_line_id, func.sum(ReturnIntakeLine.quantity))
        .join(ReturnIntake, ReturnIntake.id == ReturnIntakeLine.return_id)
        .where(
            ReturnIntake.status == "received",
            ReturnIntakeLine.sale_line_id.in_(line_ids),
        )
        .group_by(ReturnIntakeLine.sale_line_id)
    )
    return {line_id: qty for line_id, qty in db.session.execute(query)}


def _summary(row):
    return {
        "id": row.id,
        "number": f"RETURN-DRAFT-{row.id:06d}",
        "sale_id": row.sale_id,
        "reason": row.reason,
        "status": row.status,
        "condition": row.condition,
        "restocked": row.status == "received" and row.condition == "resellable",
        "credit_note_issued": False,
        "created_at": row.created_at.isoformat(),
        "inspected_at": row.inspected_at.isoformat() if row.inspected_at else None,
    }


def _detail(row):
    sale = db.session.get(Sale, row.sale_id)
    return {
        **_summary(row),
        "notice": NOTICE,
        "customer_name": sale.customer_name,
        "inspection_note": row.inspection_note,
        "created_by": row.created_by,
        "inspected_by": row.inspected_by,
        "lines": [
            {
                "sale_line_id": line.sale_line_id,
                "product_id": line.product_id,
                "sku": line.sku,
                "name": line.name,
                "quantity": line.quantity,
            }
            for line in _lines(row.id)
        ],
    }


@bp.get("/api/returns/sales/<int:sale_id>/eligible")
@roles("sales", "warehouse", "accountant")
def eligible(sale_id):
    sale = db.get_or_404(Sale, sale_id)
    lines = list(db.session.scalars(db.select(SaleLine).where(SaleLine.sale_id == sale.id).order_by(SaleLine.id)))
    already = _received_counts([line.id for line in lines])
    return {
        "sale_id": sale.id,
        "customer_name": sale.customer_name,
        "lines": [
            {
                "sale_line_id": line.id,
                "sku": line.sku,
                "name": line.name,
                "sold_quantity": line.quantity,
                "returned_quantity": int(already.get(line.id, 0)),
                "remaining_quantity": line.quantity - int(already.get(line.id, 0)),
            }
            for line in lines
        ],
        "notice": NOTICE,
    }


@bp.post("/api/returns")
@roles("sales")
def create_return():
    body = data()
    if set(body) != {"request_key", "sale_id", "lines", "reason"}:
        abort(400, "Expected request_key, sale_id, lines and reason")
    key = text(body, "request_key", 80)
    if len(key) < 16:
        abort(400, "Request key too short")
    fingerprint = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    previous = db.session.scalar(db.select(ReturnIntake).where(ReturnIntake.request_key == key))
    if previous:
        if previous.request_hash != fingerprint:
            abort(409, "Return key reused for different request")
        return {**_summary(previous), "duplicate": True}

    sale_id = integer(body.get("sale_id"))
    sale = db.get_or_404(Sale, sale_id)
    reason = text(body, "reason", 600)
    items = body["lines"]
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        abort(400, "Expected 1-100 return lines")
    quantities = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {"sale_line_id", "quantity"}:
            abort(400, "Invalid return line")
        sale_line_id = integer(item["sale_line_id"])
        quantity = integer(item["quantity"])
        if sale_line_id in quantities:
            abort(400, "Duplicate sale line")
        quantities[sale_line_id] = quantity
    sale_lines = list(
        db.session.scalars(
            db.select(SaleLine).where(SaleLine.sale_id == sale.id, SaleLine.id.in_(quantities)).order_by(SaleLine.id)
        )
    )
    if len(sale_lines) != len(quantities):
        abort(400, "Return line not part of selected sale")
    already = _received_counts(list(quantities))
    if any(quantities[line.id] + int(already.get(line.id, 0)) > line.quantity for line in sale_lines):
        abort(409, "Return quantity exceeds remaining sold quantity")

    row = ReturnIntake(
        request_key=key,
        request_hash=fingerprint,
        sale_id=sale.id,
        reason=reason,
        status="draft",
        created_by=g.user.id,
    )
    db.session.add(row)
    db.session.flush()
    db.session.add_all(
        ReturnIntakeLine(
            return_id=row.id,
            sale_line_id=line.id,
            product_id=line.product_id,
            sku=line.sku,
            name=line.name,
            quantity=quantities[line.id],
        )
        for line in sale_lines
    )
    db.session.commit()
    return {**_summary(row), "duplicate": False}, 201


@bp.get("/api/returns")
@roles("sales", "warehouse", "accountant")
def list_returns():
    limit = _positive_arg("limit", 50, 100)
    before = _positive_arg("before", 0, 1000000000)
    query = db.select(ReturnIntake)
    if before:
        query = query.where(ReturnIntake.id < before)
    rows = list(db.session.scalars(query.order_by(ReturnIntake.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    return {
        "items": [_summary(row) for row in page],
        "next_before": page[-1].id if len(rows) > limit else None,
    }


@bp.get("/api/returns/<int:return_id>")
@roles("sales", "warehouse", "accountant")
def get_return(return_id):
    return _detail(db.get_or_404(ReturnIntake, return_id))


@bp.post("/api/returns/<int:return_id>/inspect")
@roles("warehouse")
def inspect_return(return_id):
    body = data()
    if set(body) != {"condition", "inspection_note"}:
        abort(400, "Expected condition and inspection_note")
    condition = body.get("condition")
    if condition not in ("resellable", "damaged"):
        abort(400, "Condition must be resellable or damaged")
    note = text(body, "inspection_note", 600)
    row = db.session.scalar(db.select(ReturnIntake).where(ReturnIntake.id == return_id).with_for_update())
    if row is None:
        abort(404)
    if row.status == "received":
        if row.condition != condition or row.inspection_note != note:
            abort(409, "Return inspection already finalized with different data")
        return {**_summary(row), "duplicate": True}
    if row.status != "draft":
        abort(409, "Return has already been rejected or processed")

    items = _lines(row.id)
    # Lock sold lines in a stable order so overlapping returns cannot be received twice.
    sold_lines = list(
        db.session.scalars(
            db.select(SaleLine)
            .where(SaleLine.id.in_([item.sale_line_id for item in items]))
            .order_by(SaleLine.id)
            .with_for_update()
        )
    )
    sold = {line.id: line for line in sold_lines}
    received = _received_counts(list(sold))
    if any(
        item.sale_line_id not in sold
        or item.quantity + int(received.get(item.sale_line_id, 0)) > sold[item.sale_line_id].quantity
        for item in items
    ):
        abort(409, "Return quantity now exceeds remaining quantity")

    if condition == "resellable":
        products = list(
            db.session.scalars(
                db.select(Product)
                .where(Product.id.in_([item.product_id for item in items]))
                .order_by(Product.id)
                .with_for_update()
            )
        )
        by_id = {product.id: product for product in products}
        if len(by_id) != len({item.product_id for item in items}):
            abort(409, "Returned product no longer exists")
        for item in items:
            product = by_id[item.product_id]
            if product.stock + item.quantity > 1000000000:
                abort(409, "Stock exceeds maximum")
            product.stock += item.quantity
            db.session.add(
                StockMovement(
                    product_id=item.product_id,
                    delta=item.quantity,
                    reason=f"Customer return received #{row.id}",
                    sale_id=row.sale_id,
                    actor_id=g.user.id,
                )
            )

    row.status = "received"
    row.condition = condition
    row.inspection_note = note
    row.inspected_by = g.user.id
    row.inspected_at = datetime.now(UTC)
    db.session.commit()
    return {**_summary(row), "duplicate": False}


@bp.post("/api/returns/<int:return_id>/reject")
@roles("warehouse")
def reject_return(return_id):
    body = data()
    if set(body) != {"inspection_note"}:
        abort(400, "Expected inspection_note")
    note = text(body, "inspection_note", 600)
    row = db.session.scalar(db.select(ReturnIntake).where(ReturnIntake.id == return_id).with_for_update())
    if row is None:
        abort(404)
    if row.status == "rejected" and row.inspection_note == note:
        return {**_summary(row), "duplicate": True}
    if row.status != "draft":
        abort(409, "Return already finalized")
    row.status = "rejected"
    row.inspection_note = note
    row.inspected_by = g.user.id
    row.inspected_at = datetime.now(UTC)
    db.session.commit()
    return {**_summary(row), "duplicate": False}
