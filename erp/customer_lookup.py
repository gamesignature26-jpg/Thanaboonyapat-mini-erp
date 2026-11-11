"""Additive customer lookup and purchase history for POS and wholesale.

Read-only APIs: no changes to existing customer, sale or payment routes.
"""

from decimal import Decimal

from flask import Blueprint, abort, request
from sqlalchemy import func, or_

from . import roles
from .models import Customer, Sale, db

bp = Blueprint("customer_lookup", __name__)
CENT = Decimal("0.01")


def _money(value):
    return str(Decimal(value or 0).quantize(CENT))


def _positive_query_int(name, default, maximum):
    raw = request.args.get(name)
    if raw is None:
        return default
    if not raw.isascii() or not raw.isdecimal():
        abort(400, f"Invalid {name}")
    value = int(raw)
    if value < 1 or value > maximum:
        abort(400, f"Invalid {name}")
    return value


@bp.get("/api/customers/lookup")
@roles("sales", "accountant")
def lookup_customers():
    phrase = request.args.get("q", "").strip()
    if len(phrase) > 100:
        abort(400, "Search too long")
    limit = _positive_query_int("limit", 30, 100)
    after = _positive_query_int("after", 0, 1000000000)
    query = db.select(Customer).where(Customer.id > after)
    if phrase:
        # Literal substring match: '%' and '_' in user input are not SQL wildcards.
        pattern = "%" + phrase.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(
            or_(
                Customer.name.ilike(pattern, escape="\\"),
                Customer.tax_id.ilike(pattern, escape="\\"),
            )
        )
    customers = list(db.session.scalars(query.order_by(Customer.id).limit(limit + 1)))
    page = customers[:limit]
    return {
        "items": [{"id": c.id, "name": c.name, "tax_id": c.tax_id, "address": c.address} for c in page],
        "next_after": page[-1].id if len(customers) > limit else None,
    }


@bp.get("/api/customers/<int:customer_id>/history")
@roles("sales", "accountant")
def customer_history(customer_id):
    customer = db.get_or_404(Customer, customer_id)
    limit = _positive_query_int("limit", 30, 100)
    before = _positive_query_int("before", 0, 1000000000)
    totals = db.session.execute(
        db.select(
            func.coalesce(func.sum(Sale.total), 0),
            func.coalesce(func.sum(Sale.paid), 0),
            func.count(Sale.id),
        ).where(Sale.customer_id == customer_id)
    ).one()
    query = db.select(Sale).where(Sale.customer_id == customer_id)
    if before:
        query = query.where(Sale.id < before)
    rows = list(db.session.scalars(query.order_by(Sale.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    total, paid, sale_count = totals
    return {
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "tax_id": customer.tax_id,
            "address": customer.address,
        },
        "summary": {
            "total_sales": _money(total),
            "total_paid": _money(paid),
            "outstanding": _money(Decimal(total) - Decimal(paid)),
            "sale_count": sale_count,
        },
        "items": [
            {
                "id": s.id,
                "date": s.created_at.isoformat(),
                "total": _money(s.total),
                "paid": _money(s.paid),
                "balance": _money(s.total - s.paid),
            }
            for s in page
        ],
        "next_before": page[-1].id if len(rows) > limit else None,
    }
