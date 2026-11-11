"""Quotation drafts only. No stock reservation, sale, payment, or tax document issuance."""

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, g, render_template, request
from sqlalchemy import CheckConstraint

from . import data, integer, money, roles, text
from .extended import CustomerPrice
from .models import Customer, Product, SaleLine, db

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
    sale_id = db.Column(db.ForeignKey("sale.id"), unique=True)
    conversion_hash = db.Column(db.String(64))
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


class QuotationEvent(db.Model):
    """Append-only staff record of quotation status changes."""

    __tablename__ = "quotation_event"
    id = db.Column(db.Integer, primary_key=True)
    quotation_id = db.Column(db.ForeignKey("quotation.id"), nullable=False)
    from_status = db.Column(db.String(12), nullable=False)
    to_status = db.Column(db.String(12), nullable=False)
    note = db.Column(db.String(600), nullable=False)
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    __table_args__ = (
        CheckConstraint("from_status IN ('draft','sent','accepted','declined')"),
        CheckConstraint("to_status IN ('sent','accepted','declined')"),
    )


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
        "sale_id": quote.sale_id,
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
        "events": [
            {
                "id": event.id,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "note": event.note,
                "actor_id": event.actor_id,
                "created_at": event.created_at.isoformat(),
            }
            for event in db.session.scalars(
                db.select(QuotationEvent).where(QuotationEvent.quotation_id == quote.id).order_by(QuotationEvent.id)
            )
        ],
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


def bangkok_date():
    return datetime.now(ZoneInfo("Asia/Bangkok")).date()


@bp.post("/api/quotations/<int:quotation_id>/status")
@roles("sales")
def change_quotation_status(quotation_id):
    """Record a staff-reported status; not proof of delivery or customer acceptance."""
    body = data()
    if set(body) != {"status", "note"}:
        abort(400, "Expected status and note")
    requested = body.get("status")
    if requested not in ("sent", "accepted", "declined"):
        abort(400, "Invalid quotation status")
    note = text(body, "note", 600)
    quote = db.session.scalar(db.select(Quotation).where(Quotation.id == quotation_id).with_for_update())
    if quote is None:
        abort(404)
    valid = {"draft": ("sent",), "sent": ("accepted", "declined")}
    if requested not in valid.get(quote.status, ()):
        abort(409, "Invalid quotation status transition")
    if requested == "accepted" and quote.expires_on and quote.expires_on < bangkok_date():
        abort(409, "Quotation expired; create a revised quotation")
    db.session.add(
        QuotationEvent(
            quotation_id=quote.id,
            from_status=quote.status,
            to_status=requested,
            note=note,
            actor_id=g.user.id,
        )
    )
    quote.status = requested
    db.session.commit()
    return detail(quote)


@bp.post("/api/quotations/<int:quotation_id>/convert")
@roles("sales")
def convert_quotation_to_sale(quotation_id):
    """Convert only an accepted, current-price quote using the existing stock-safe sale path."""
    body = data()
    allowed = {"delivery_mode", "delivery_date", "address", "phone", "driver", "note"}
    if set(body) - allowed:
        abort(400, "Unknown conversion field")
    mode = body.get("delivery_mode", "pickup")
    if mode not in ("pickup", "delivery"):
        abort(400, "Invalid delivery mode")
    for field, maximum in (("address", 1000), ("phone", 30), ("driver", 100), ("note", 600)):
        if field in body and (not isinstance(body[field], str) or len(body[field]) > maximum):
            abort(400, f"Invalid {field}")
    if "delivery_date" in body:
        from .online import parse_day

        parse_day(body["delivery_date"])
    if mode == "delivery" and "address" in body and not body["address"].strip():
        abort(400, "Delivery address required")
    fingerprint = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    quote = db.session.scalar(db.select(Quotation).where(Quotation.id == quotation_id).with_for_update())
    if quote is None:
        abort(404)
    if quote.sale_id is not None:
        if fingerprint != quote.conversion_hash:
            abort(409, "Quotation already converted with different delivery data")
        return {"quote_id": quote.id, "sale_id": quote.sale_id, "total": amount(quote.total), "duplicate": True}

    if quote.status != "accepted":
        abort(409, "Quotation must be accepted before converting")
    if quote.expires_on and quote.expires_on < bangkok_date():
        abort(409, "Quotation expired; create a revised quotation")
    if Decimal(str(current_app.config["VAT_RATE"])) != quote.vat_rate:
        abort(409, "VAT rate changed; create a revised quotation")
    address = body.get("address", quote.customer_address)
    if mode == "delivery" and not address.strip():
        abort(400, "Delivery address required")

    source = quote_lines(quote.id)
    if not source:
        abort(409, "Quotation has no product lines")
    order = {
        "idempotency_key": f"quotation-conversion-{quote.id:016d}",
        "kind": "wholesale",
        "customer_id": quote.customer_id,
        "vat_price_mode": quote.vat_price_mode,
        "lines": [{"product_id": line.product_id, "quantity": line.quantity} for line in source],
        "delivery_mode": mode,
        "delivery_date": body.get("delivery_date"),
        "address": address,
        "phone": body.get("phone", ""),
        "driver": body.get("driver", ""),
        "note": body.get("note", ""),
        "method": "credit",
        "discount": "0.00",
        "shipping_fee": "0.00",
        "expected_total": amount(quote.total),
    }

    def bind_to_sale(sale):
        # Existing sale creation has locked product rows and staged stock movement.
        # Reject *any* changed SKU, quantity or unit price before its commit.
        # The global HTTPException handler rolls back the whole transaction.
        db.session.flush()
        sold = list(db.session.scalars(db.select(SaleLine).where(SaleLine.sale_id == sale.id)))
        sold_by_product = {line.product_id: line for line in sold}
        if (
            len(sold) != len(source)
            or sale.total != quote.total
            or sale.vat != quote.vat
            or sale.vat_rate != quote.vat_rate
        ):
            abort(409, "Quotation no longer matches the current sale")
        for line in source:
            current = sold_by_product.get(line.product_id)
            if (
                current is None
                or current.quantity != line.quantity
                or current.price != line.unit_price
                or current.sku != line.sku
                or current.name != line.name
            ):
                abort(409, "Quotation items or prices changed; create a revised quotation")
        quote.sale_id = sale.id
        quote.conversion_hash = fingerprint

    from .online import create_order

    result, _code = create_order(body_override=order, before_commit=bind_to_sale)
    return {
        "quote_id": quote.id,
        "sale_id": result["id"],
        "total": amount(quote.total),
        "duplicate": False,
    }, 201
