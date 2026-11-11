"""Quotation drafts only. No stock reservation, sale, payment, or tax document issuance."""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from flask import Blueprint, abort, current_app, g, render_template, request
from sqlalchemy import CheckConstraint

from . import data, integer, money, roles, text
from .extended import CustomerPrice
from .models import Customer, Product, db

bp = Blueprint("quotation_drafts", __name__)
CENT = Decimal("0.01")
NOTICE = "QUOTATION DRAFT - NOT A TAX INVOICE"


class Quotation(db.Model):
    __tablename__ = "quotation"
    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(80), unique=True, nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    customer_id = db.Column(db.ForeignKey("customer.id"), nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_tax_id = db.Column(db.String(13))
    customer_address = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(12), nullable=False, default="draft")
    vat_price_mode = db.Column(db.String(9), nullable=False)
    subtotal = db.Column(db.Numeric(14, 2), nullable=False)
    vat_rate = db.Column(db.Numeric(5, 2), nullable=False)
    vat = db.Column(db.Numeric(14, 2), nullable=False)
    total = db.Column(db.Numeric(14, 2), nullable=False)
    expires_on = db.Column(db.Date)
    note = db.Column(db.String(600), nullable=False, default="")
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    __table_args__ = (
        CheckConstraint("status IN ('draft','sent','accepted','declined')"),
        CheckConstraint("vat_price_mode IN ('inclusive','exclusive')"),
        CheckConstraint("subtotal >= 0 AND vat >= 0 AND total >= 0"),
    )


class QuotationLine(db.Model):
    __tablename__ = "quotation_line"
    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.ForeignKey("quotation.id"), nullable=False)
    product_id = db.Column(db.ForeignKey("product.id"), nullable=False)
    sku = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(14, 2), nullable=False)
    __table_args__ = (CheckConstraint("quantity > 0 AND unit_price >= 0"),)


def amount(value):
    return str(Decimal(value).quantize(CENT))


def positive_param(name, default, maximum):
    value = request.args.get(name)
    if value is None:
        return default
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= maximum:
        abort(400, f"Invalid {name}")
    return int(value)


def quote_lines(qid):
    return list(
        db.session.scalars(db.select(QuotationLine).where(QuotationLine.quotation_id == qid).order_by(QuotationLine.id))
    )


def summary(quote):
    return {
        "id": quote.id,
        "number": f"QT-DRAFT-{quote.id:06d}",
        "status": quote.status,
        "date": quote.created_at.isoformat(),
        "customer_name": quote.customer_name,
        "vat_price_mode": quote.vat_price_mode,
        "subtotal": amount(quote.subtotal),
        "vat": amount(quote.vat),
        "total": amount(quote.total),
        "expires_on": quote.expires_on.isoformat() if quote.expires_on else None,
    }


def detail(quote):
    return {
        **summary(quote),
        "notice": NOTICE,
        "customer": {
            "id": quote.customer_id,
            "name": quote.customer_name,
            "tax_id": quote.customer_tax_id,
            "address": quote.customer_address,
        },
        "vat_rate": amount(quote.vat_rate),
        "note": quote.note,
        "lines": [
            {
                "product_id": x.product_id,
                "sku": x.sku,
                "name": x.name,
                "quantity": x.quantity,
                "unit_price": amount(x.unit_price),
            }
            for x in quote_lines(quote.id)
        ],
    }


@bp.post("/api/quotations")
@roles("sales")
def create_quotation():
    body = data()
    if set(body) - {"request_key", "customer_id", "vat_price_mode", "lines", "expires_on", "note", "expected_total"}:
        abort(400, "Unknown quotation field")
    key = text(body, "request_key", 80)
    if len(key) < 16:
        abort(400, "Request key too short")
    fingerprint = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    previous = db.session.scalar(db.select(Quotation).where(Quotation.request_key == key))
    if previous:
        if previous.request_hash != fingerprint:
            abort(409, "Quotation request key already used")
        return {**summary(previous), "duplicate": True}, 200

    customer = db.session.get(Customer, integer(body.get("customer_id")))
    if customer is None:
        abort(404, "Customer not found")
    mode = body.get("vat_price_mode", "exclusive")
    if mode not in ("inclusive", "exclusive"):
        abort(400, "Invalid VAT price mode")
    lines = body.get("lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        abort(400, "Expected 1-100 quotation lines")
    requested = {}
    for item in lines:
        if not isinstance(item, dict) or set(item) != {"product_id", "quantity"}:
            abort(400, "Invalid quotation line")
        product_id = integer(item["product_id"])
        quantity = integer(item["quantity"])
        if product_id in requested:
            abort(400, "Duplicate quotation product")
        requested[product_id] = quantity

    expiry = body.get("expires_on")
    if expiry not in (None, ""):
        if not isinstance(expiry, str) or len(expiry) != 10:
            abort(400, "Invalid expiry date")
        try:
            expiry = date.fromisoformat(expiry)
        except ValueError:
            abort(400, "Invalid expiry date")
    else:
        expiry = None
    note = body.get("note", "")
    if not isinstance(note, str) or len(note) > 600:
        abort(400, "Invalid note")

    products = list(db.session.scalars(db.select(Product).where(Product.id.in_(requested)).order_by(Product.id)))
    if len(products) != len(requested):
        abort(404, "Product not found")
    special = {
        row.product_id: row.price
        for row in db.session.scalars(
            db.select(CustomerPrice).where(
                CustomerPrice.customer_id == customer.id,
                CustomerPrice.product_id.in_(requested),
            )
        )
    }
    subtotal_entered = sum((Decimal(special.get(p.id, p.price)) * requested[p.id] for p in products), Decimal(0))
    rate = Decimal(str(current_app.config["VAT_RATE"]))
    if mode == "inclusive":
        total = subtotal_entered
        vat = (total * rate / (Decimal(100) + rate)).quantize(CENT, rounding=ROUND_HALF_UP)
        base = total - vat
    else:
        base = subtotal_entered
        vat = (base * rate / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
        total = base + vat
    if total > Decimal("999999999.99"):
        abort(400, "Total exceeds maximum")
    if "expected_total" in body and money(body["expected_total"]) != total:
        abort(409, "Quotation prices changed")

    quote = Quotation(
        request_key=key,
        request_hash=fingerprint,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_tax_id=customer.tax_id,
        customer_address=customer.address,
        status="draft",
        vat_price_mode=mode,
        subtotal=base,
        vat_rate=rate,
        vat=vat,
        total=total,
        expires_on=expiry,
        note=note.strip(),
        actor_id=g.user.id,
    )
    db.session.add(quote)
    db.session.flush()
    db.session.add_all(
        QuotationLine(
            quotation_id=quote.id,
            product_id=product.id,
            sku=product.sku,
            name=product.name,
            quantity=requested[product.id],
            unit_price=special.get(product.id, product.price),
        )
        for product in products
    )
    db.session.commit()
    return {**summary(quote), "duplicate": False}, 201


@bp.get("/api/quotations")
@roles("sales", "accountant")
def list_quotations():
    limit = positive_param("limit", 50, 100)
    before = positive_param("before", 0, 1000000000)
    query = db.select(Quotation)
    if before:
        query = query.where(Quotation.id < before)
    rows = list(db.session.scalars(query.order_by(Quotation.id.desc()).limit(limit + 1)))
    items = rows[:limit]
    return {
        "items": [summary(quote) for quote in items],
        "next_before": items[-1].id if len(rows) > limit else None,
    }


@bp.get("/api/quotations/<int:quotation_id>")
@roles("sales", "accountant")
def quotation_detail(quotation_id):
    return detail(db.get_or_404(Quotation, quotation_id))


@bp.get("/api/quotations/<int:quotation_id>/print")
@roles("sales", "accountant")
def quotation_print(quotation_id):
    quote = db.get_or_404(Quotation, quotation_id)
    return render_template("quotation_print.html", quote=detail(quote))
