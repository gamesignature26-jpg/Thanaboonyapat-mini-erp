"""Auditable multi-sale billing drafts, separate from receipts and tax documents.

A batch snapshots selected open receivables but never posts a payment, adjusts a
sale, changes stock, or creates a legally issued document. Current balances
are independently calculated on every read.
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from flask import Blueprint, abort, g, render_template, request
from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from . import data, integer, roles, text
from .models import Customer, Sale, db

bp = Blueprint("billing_batches", __name__)
NOTICE = "BILLING DRAFT - NOT A TAX INVOICE OR RECEIPT"
MAX_TOTAL = Decimal("999999999.99")


class BillingBatch(db.Model):
    __tablename__ = "billing_batch"
    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(80), unique=True, nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    customer_id = db.Column(db.ForeignKey("customer.id"), nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_tax_id = db.Column(db.String(13))
    customer_address = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(8), nullable=False, default="draft")
    snapshot_total = db.Column(db.Numeric(14, 2), nullable=False)
    note = db.Column(db.String(600), nullable=False, default="")
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    void_reason = db.Column(db.String(600))
    voided_by = db.Column(db.ForeignKey("user.id"))
    voided_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('draft','void')"),
        CheckConstraint("snapshot_total >= 0"),
    )


class BillingBatchLine(db.Model):
    __tablename__ = "billing_batch_line"
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.ForeignKey("billing_batch.id"), nullable=False)
    sale_id = db.Column(db.ForeignKey("sale.id"), nullable=False)
    sale_date = db.Column(db.DateTime(timezone=True), nullable=False)
    sale_total = db.Column(db.Numeric(14, 2), nullable=False)
    paid_at_creation = db.Column(db.Numeric(14, 2), nullable=False)
    outstanding_at_creation = db.Column(db.Numeric(14, 2), nullable=False)
    __table_args__ = (
        UniqueConstraint("batch_id", "sale_id", name="uq_billing_batch_sale"),
        Index("ix_billing_batch_line_sale_id", "sale_id"),
        CheckConstraint("outstanding_at_creation > 0"),
    )


def amount(value):
    return f"{Decimal(value):.2f}"


def param_int(name, default, maximum):
    raw = request.args.get(name)
    if raw is None:
        return default
    if not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= maximum:
        abort(400, f"Invalid {name}")
    return int(raw)


def summary(batch):
    return {
        "id": batch.id,
        "number": f"BATCH-DRAFT-{batch.id:06d}",
        "status": batch.status,
        "customer_id": batch.customer_id,
        "customer_name": batch.customer_name,
        "snapshot_total": amount(batch.snapshot_total),
        "created_at": batch.created_at.isoformat(),
        "notice": NOTICE,
    }


def detail(batch):
    lines = list(
        db.session.scalars(
            db.select(BillingBatchLine).where(BillingBatchLine.batch_id == batch.id).order_by(BillingBatchLine.sale_id)
        )
    )
    sales = {
        sale.id: sale for sale in db.session.scalars(db.select(Sale).where(Sale.id.in_(line.sale_id for line in lines)))
    }
    items = []
    outstanding = Decimal("0.00")
    for line in lines:
        sale = sales[line.sale_id]
        current = sale.total - sale.paid
        outstanding += current
        items.append(
            {
                "sale_id": line.sale_id,
                "sale_date": line.sale_date.isoformat(),
                "sale_total": amount(line.sale_total),
                "paid_at_creation": amount(line.paid_at_creation),
                "outstanding_at_creation": amount(line.outstanding_at_creation),
                "outstanding_now": amount(current),
            }
        )
    return {
        **summary(batch),
        "customer": {
            "id": batch.customer_id,
            "name": batch.customer_name,
            "tax_id": batch.customer_tax_id,
            "address": batch.customer_address,
        },
        "note": batch.note,
        "actor_id": batch.actor_id,
        "items": items,
        "current_outstanding": amount(outstanding),
        "void_reason": batch.void_reason,
        "voided_by": batch.voided_by,
        "voided_at": batch.voided_at.isoformat() if batch.voided_at else None,
    }


@bp.get("/api/billing-batches/eligible")
@roles("sales", "accountant")
def eligible_sales():
    customer_id = param_int("customer_id", 0, 1000000)
    if not customer_id:
        abort(400, "customer_id required")
    customer = db.get_or_404(Customer, customer_id)
    limit = param_int("limit", 50, 100)
    before = param_int("before", 0, 1000000000)
    active_sales = (
        db.select(BillingBatchLine.sale_id)
        .join(BillingBatch, BillingBatch.id == BillingBatchLine.batch_id)
        .where(BillingBatch.status == "draft")
    )
    query = db.select(Sale).where(Sale.customer_id == customer_id, Sale.paid < Sale.total, ~Sale.id.in_(active_sales))
    if before:
        query = query.where(Sale.id < before)
    rows = list(db.session.scalars(query.order_by(Sale.id.desc()).limit(limit + 1)))
    items = rows[:limit]
    return {
        "customer_id": customer.id,
        "customer_name": customer.name,
        "items": [
            {
                "sale_id": row.id,
                "sale_date": row.created_at.isoformat(),
                "total": amount(row.total),
                "paid": amount(row.paid),
                "outstanding": amount(row.total - row.paid),
            }
            for row in items
        ],
        "next_before": items[-1].id if len(rows) > limit else None,
    }


@bp.post("/api/billing-batches")
@roles("accountant")
def create_billing_batch():
    body = data()
    if set(body) != {"request_key", "customer_id", "sale_ids", "note"}:
        abort(400, "Expected request_key, customer_id, sale_ids, note")
    key = text(body, "request_key", 80)
    if len(key) < 16:
        abort(400, "Request key too short")
    fingerprint = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    previous = db.session.scalar(db.select(BillingBatch).where(BillingBatch.request_key == key))
    if previous:
        if previous.request_hash != fingerprint:
            abort(409, "Billing draft request key reused with changed payload")
        return {**summary(previous), "duplicate": True}, 200

    customer_id = integer(body.get("customer_id"))
    customer = db.get_or_404(Customer, customer_id)
    ids = body.get("sale_ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 25:
        abort(400, "Expected 1-25 sale IDs")
    if any(type(value) is not int or value <= 0 or value > 1000000 for value in ids):
        abort(400, "Invalid sale ID")
    if len(set(ids)) != len(ids):
        abort(400, "Duplicate sale ID")
    note = body.get("note")
    if not isinstance(note, str) or len(note) > 600:
        abort(400, "Invalid note")

    # Lock sales in stable order to serialize concurrent billing draft claims.
    sales = list(db.session.scalars(db.select(Sale).where(Sale.id.in_(ids)).order_by(Sale.id).with_for_update()))
    if len(sales) != len(ids):
        abort(404, "Sale not found")
    if any(sale.customer_id != customer_id for sale in sales):
        abort(409, "Billing batches must contain one customer's sales only")
    if any(sale.paid >= sale.total for sale in sales):
        abort(409, "Cannot bill a fully paid sale")

    active = db.session.scalar(
        db.select(BillingBatchLine.sale_id)
        .join(BillingBatch, BillingBatch.id == BillingBatchLine.batch_id)
        .where(BillingBatchLine.sale_id.in_(ids), BillingBatch.status == "draft")
        .limit(1)
    )
    if active is not None:
        abort(409, "Sale already included in an active billing draft")
    total = sum((row.total - row.paid for row in sales), Decimal("0.00"))
    if total <= 0 or total > MAX_TOTAL:
        abort(400, "Invalid billing draft total")

    batch = BillingBatch(
        request_key=key,
        request_hash=fingerprint,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_tax_id=customer.tax_id,
        customer_address=customer.address,
        status="draft",
        snapshot_total=total,
        note=note.strip(),
        actor_id=g.user.id,
    )
    db.session.add(batch)
    db.session.flush()
    db.session.add_all(
        BillingBatchLine(
            batch_id=batch.id,
            sale_id=sale.id,
            sale_date=sale.created_at,
            sale_total=sale.total,
            paid_at_creation=sale.paid,
            outstanding_at_creation=sale.total - sale.paid,
        )
        for sale in sales
    )
    db.session.commit()
    return {**summary(batch), "duplicate": False}, 201


@bp.get("/api/billing-batches")
@roles("sales", "accountant")
def list_billing_batches():
    limit = param_int("limit", 50, 100)
    before = param_int("before", 0, 1000000000)
    query = db.select(BillingBatch)
    if before:
        query = query.where(BillingBatch.id < before)
    rows = list(db.session.scalars(query.order_by(BillingBatch.id.desc()).limit(limit + 1)))
    items = rows[:limit]
    return {
        "items": [summary(row) for row in items],
        "next_before": items[-1].id if len(rows) > limit else None,
    }


@bp.get("/api/billing-batches/<int:batch_id>")
@roles("sales", "accountant")
def billing_batch_detail(batch_id):
    return detail(db.get_or_404(BillingBatch, batch_id))


@bp.get("/api/billing-batches/<int:batch_id>/print")
@roles("sales", "accountant")
def billing_batch_print(batch_id):
    batch = db.get_or_404(BillingBatch, batch_id)
    return render_template("billing_batch_print.html", batch=detail(batch))


@bp.post("/api/billing-batches/<int:batch_id>/void")
@roles("accountant")
def void_billing_batch(batch_id):
    body = data()
    if set(body) != {"reason"}:
        abort(400, "Expected void reason")
    reason = text(body, "reason", 600)
    batch = db.session.scalar(db.select(BillingBatch).where(BillingBatch.id == batch_id).with_for_update())
    if batch is None:
        abort(404)
    if batch.status == "void":
        if batch.void_reason != reason:
            abort(409, "Billing draft already voided with different reason")
        return {**summary(batch), "duplicate": True}
    if batch.status != "draft":
        abort(409, "Cannot void billing draft")
    batch.status = "void"
    batch.void_reason = reason
    batch.voided_by = g.user.id
    batch.voided_at = datetime.now(UTC)
    db.session.commit()
    return {**summary(batch), "duplicate": False}
