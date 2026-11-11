"""Read-only billing previews: never issue a tax invoice or alter a receivable."""

from decimal import Decimal

from flask import Blueprint, abort, render_template, request

from . import roles
from .models import Sale, SaleLine, db

bp = Blueprint("billing_previews", __name__)
CENT = Decimal("0.01")
NOTICE = "BILLING PREVIEW - NOT A TAX INVOICE"


def money(value):
    return str(Decimal(value).quantize(CENT))


def positive_param(name, default, maximum):
    raw = request.args.get(name)
    if raw is None:
        return default
    if not raw.isascii() or not raw.isdecimal() or not 1 <= int(raw) <= maximum:
        abort(400, f"Invalid {name}")
    return int(raw)


def preview_summary(sale):
    return {
        "sale_id": sale.id,
        "number": f"BILL-PREVIEW-{sale.id:06d}",
        "date": sale.created_at.isoformat(),
        "customer_name": sale.customer_name,
        "total": money(sale.total),
        "paid": money(sale.paid),
        "outstanding": money(sale.total - sale.paid),
        "issued": False,
    }


def preview_detail(sale):
    return {
        **preview_summary(sale),
        "notice": NOTICE,
        "customer": {
            "id": sale.customer_id,
            "name": sale.customer_name,
            "tax_id": sale.customer_tax_id,
            "address": sale.customer_address,
        },
        "vat_price_mode": sale.vat_price_mode,
        "subtotal": money(sale.subtotal),
        "vat_rate": money(sale.vat_rate),
        "vat": money(sale.vat),
        "lines": [
            {
                "sku": line.sku,
                "name": line.name,
                "quantity": line.quantity,
                "unit_price": money(line.price),
            }
            for line in db.session.scalars(
                db.select(SaleLine).where(SaleLine.sale_id == sale.id).order_by(SaleLine.id)
            )
        ],
    }


@bp.get("/api/billing-notes")
@roles("sales", "accountant")
def billing_list():
    limit = positive_param("limit", 50, 100)
    before = positive_param("before", 0, 1000000000)
    outstanding = request.args.get("outstanding", "1")
    if outstanding not in ("0", "1"):
        abort(400, "Invalid outstanding filter")
    query = db.select(Sale)
    if outstanding == "1":
        query = query.where(Sale.paid < Sale.total)
    if before:
        query = query.where(Sale.id < before)
    rows = list(db.session.scalars(query.order_by(Sale.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    return {
        "items": [preview_summary(sale) for sale in page],
        "next_before": page[-1].id if len(rows) > limit else None,
        "notice": NOTICE,
    }


@bp.get("/api/billing-notes/<int:sale_id>")
@roles("sales", "accountant")
def billing_detail(sale_id):
    return preview_detail(db.get_or_404(Sale, sale_id))


@bp.get("/api/billing-notes/<int:sale_id>/print")
@roles("sales", "accountant")
def billing_print(sale_id):
    return render_template("billing_preview.html", bill=preview_detail(db.get_or_404(Sale, sale_id)))
