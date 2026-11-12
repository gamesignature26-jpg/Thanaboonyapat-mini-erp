"""Accountant-only, non-posting financial credit-note review drafts.

These are NOT legally issued Thai tax credit notes. They never change Sale,
Payment, StockMovement, customer balances or issued tax document numbers.
"""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

from flask import Blueprint, abort, g, render_template, request
from sqlalchemy import CheckConstraint, func

from . import data, integer, money, roles, text
from .models import Sale, SaleLine, db
from .return_intake import ReturnIntake, ReturnIntakeLine

bp = Blueprint("credit_note_drafts", __name__)
NOTICE = "CREDIT REVIEW DRAFT - NOT ISSUED; NO FINANCIAL/TAX POSTING"
CENT = Decimal("0.01")


class CreditNoteDraft(db.Model):
    __tablename__ = "credit_note_draft"
    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(80), nullable=False, unique=True)
    request_hash = db.Column(db.String(64), nullable=False)
    return_id = db.Column(db.ForeignKey("return_intake.id"), nullable=False, unique=True)
    sale_id = db.Column(db.ForeignKey("sale.id"), nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_tax_id = db.Column(db.String(13))
    customer_address = db.Column(db.String(1000), nullable=False)
    reason = db.Column(db.String(600), nullable=False)
    status = db.Column(db.String(8), nullable=False, default="draft")
    amount_ex_vat = db.Column(db.Numeric(14, 2), nullable=False)
    vat_amount = db.Column(db.Numeric(14, 2), nullable=False)
    credit_total = db.Column(db.Numeric(14, 2), nullable=False)
    original_sale_total = db.Column(db.Numeric(14, 2), nullable=False)
    original_sale_paid = db.Column(db.Numeric(14, 2), nullable=False)
    returned_lines_snapshot = db.Column(db.Text, nullable=False)
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    void_reason = db.Column(db.String(600))
    voided_by = db.Column(db.ForeignKey("user.id"))
    voided_at = db.Column(db.DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('draft','void')"),
        CheckConstraint("amount_ex_vat >= 0 AND vat_amount >= 0 AND credit_total > 0"),
        CheckConstraint("credit_total = amount_ex_vat + vat_amount"),
    )


def _amount(value):
    return str(Decimal(value).quantize(CENT))


def _param_int(name, default, maximum):
    value = request.args.get(name)
    if value is None:
        return default
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= maximum:
        abort(400, f"Invalid {name}")
    return int(value)


def _summary(row):
    return {
        "id": row.id,
        "number": f"CREDIT-DRAFT-{row.id:06d}",
        "status": row.status,
        "return_id": row.return_id,
        "sale_id": row.sale_id,
        "customer_name": row.customer_name,
        "amount_ex_vat": _amount(row.amount_ex_vat),
        "vat_amount": _amount(row.vat_amount),
        "credit_total": _amount(row.credit_total),
        "created_at": row.created_at.isoformat(),
        "notice": NOTICE,
        "posted_to_receivables": False,
        "tax_credit_note_issued": False,
    }


def _detail(row):
    sale = db.session.get(Sale, row.sale_id)
    return {
        **_summary(row),
        "customer_tax_id": row.customer_tax_id,
        "customer_address": row.customer_address,
        "reason": row.reason,
        "original_sale_total": _amount(row.original_sale_total),
        "original_sale_paid": _amount(row.original_sale_paid),
        "current_sale_balance": _amount(sale.total - sale.paid),
        "returned_lines": json.loads(row.returned_lines_snapshot),
        "actor_id": row.actor_id,
        "void_reason": row.void_reason,
        "voided_by": row.voided_by,
        "voided_at": row.voided_at.isoformat() if row.voided_at else None,
        "reconciliation_required": row.status == "draft",
    }


@bp.post("/api/credit-note-drafts")
@roles("accountant")
def create_credit_note_draft():
    body = data()
    if set(body) != {"request_key", "return_id", "reason", "amount_ex_vat", "vat_amount"}:
        abort(400, "Expected request key, received return, reason and manually reviewed amounts")
    key = text(body, "request_key", 80)
    if len(key) < 16:
        abort(400, "Request key too short")
    fingerprint = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    prior = db.session.scalar(db.select(CreditNoteDraft).where(CreditNoteDraft.request_key == key))
    if prior:
        if prior.request_hash != fingerprint:
            abort(409, "Credit request key reused with changed amounts")
        return {**_summary(prior), "duplicate": True}

    return_id = integer(body.get("return_id"))
    intake = db.get_or_404(ReturnIntake, return_id)
    if intake.status != "received":
        abort(409, "Warehouse return must be inspected and received first")

    sale = db.session.get(Sale, intake.sale_id, with_for_update=True)
    if sale is None:
        abort(409, "Original sale unavailable")
    reason = text(body, "reason", 600)
    base = money(body.get("amount_ex_vat"))
    vat = money(body.get("vat_amount"))
    total = base + vat
    if total <= 0 or total > Decimal("999999999.99"):
        abort(400, "Invalid credit amount")
    if db.session.scalar(db.select(CreditNoteDraft.id).where(CreditNoteDraft.return_id == return_id)):
        abort(409, "Return already has a financial review draft; voided drafts remain auditable")
    # Reserve financial *proposal* limits; does not post an actual credit.
    prior_totals = db.session.execute(
        db.select(
            func.coalesce(func.sum(CreditNoteDraft.amount_ex_vat), 0),
            func.coalesce(func.sum(CreditNoteDraft.vat_amount), 0),
        ).where(CreditNoteDraft.sale_id == sale.id, CreditNoteDraft.status == "draft")
    ).one()
    if base + Decimal(prior_totals[0]) > sale.subtotal or vat + Decimal(prior_totals[1]) > sale.vat:
        abort(409, "Proposed credit would exceed remaining sale base or VAT; accountant review required")

    lines = list(
        db.session.scalars(
            db.select(ReturnIntakeLine)
            .where(ReturnIntakeLine.return_id == intake.id)
            .order_by(ReturnIntakeLine.sale_line_id)
        )
    )
    sold = {
        line.id: line
        for line in db.session.scalars(
            db.select(SaleLine).where(SaleLine.sale_id == sale.id, SaleLine.id.in_([x.sale_line_id for x in lines]))
        )
    }
    if not lines or len(sold) != len(lines):
        abort(409, "Return references incomplete original sale lines")
    snapshot = [
        {
            "sale_line_id": line.sale_line_id,
            "sku": line.sku,
            "name": line.name,
            "quantity": line.quantity,
            # Original entered unit prices may be VAT-inclusive and do NOT
            # automatically justify the manually proposed credit amounts.
            "sale_unit_price_entered": _amount(sold[line.sale_line_id].price),
        }
        for line in lines
    ]
    row = CreditNoteDraft(
        request_key=key,
        request_hash=fingerprint,
        return_id=intake.id,
        sale_id=sale.id,
        customer_name=sale.customer_name,
        customer_tax_id=sale.customer_tax_id,
        customer_address=sale.customer_address,
        reason=reason,
        status="draft",
        amount_ex_vat=base,
        vat_amount=vat,
        credit_total=total,
        original_sale_total=sale.total,
        original_sale_paid=sale.paid,
        returned_lines_snapshot=json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        actor_id=g.user.id,
    )
    db.session.add(row)
    db.session.commit()
    return {**_summary(row), "duplicate": False}, 201


@bp.get("/api/credit-note-drafts")
@roles("accountant")
def list_credit_note_drafts():
    limit = _param_int("limit", 50, 100)
    before = _param_int("before", 0, 1000000000)
    query = db.select(CreditNoteDraft)
    if before:
        query = query.where(CreditNoteDraft.id < before)
    entries = list(db.session.scalars(query.order_by(CreditNoteDraft.id.desc()).limit(limit + 1)))
    page = entries[:limit]
    return {
        "items": [_summary(row) for row in page],
        "next_before": page[-1].id if len(entries) > limit else None,
    }


@bp.get("/api/credit-note-drafts/<int:draft_id>")
@roles("accountant")
def get_credit_note_draft(draft_id):
    return _detail(db.get_or_404(CreditNoteDraft, draft_id))


@bp.get("/api/credit-note-drafts/<int:draft_id>/print")
@roles("accountant")
def print_credit_note_draft(draft_id):
    row = db.get_or_404(CreditNoteDraft, draft_id)
    return render_template("credit_note_draft_print.html", draft=_detail(row))


@bp.post("/api/credit-note-drafts/<int:draft_id>/void")
@roles("accountant")
def void_credit_note_draft(draft_id):
    body = data()
    if set(body) != {"reason"}:
        abort(400, "Expected void reason")
    reason = text(body, "reason", 600)
    row = db.session.scalar(db.select(CreditNoteDraft).where(CreditNoteDraft.id == draft_id).with_for_update())
    if row is None:
        abort(404)
    if row.status == "void":
        if row.void_reason != reason:
            abort(409, "Draft previously voided for another reason")
        return _summary(row)
    if row.status != "draft":
        abort(409, "Unknown draft status")
    row.status = "void"
    row.void_reason = reason
    row.voided_by = g.user.id
    row.voided_at = datetime.now(UTC)
    db.session.commit()
    return _summary(row)
