"""Read-only receivables summary, additive to existing sales/payment workflows.

This report is *not* an ageing report: invoices do not yet track due dates.
"""

from decimal import Decimal

from flask import Blueprint, abort, request
from sqlalchemy import func

from . import roles
from .models import Customer, Sale, db

bp = Blueprint("receivables_report", __name__)


@bp.get("/api/reports/receivables")
@roles("accountant")
def receivables():
    """Summarize outstanding balances by customer without changing the ledger."""
    search = request.args.get("q", "").strip()
    if len(search) > 100:
        abort(400, "Search too long")
    query = (
        db.select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer_name"),
            func.count(Sale.id).label("unpaid_sales"),
            func.sum(Sale.total - Sale.paid).label("outstanding"),
        )
        .join(Sale, Sale.customer_id == Customer.id)
        .where(Sale.paid < Sale.total)
        .group_by(Customer.id, Customer.name)
        .order_by(Customer.name, Customer.id)
    )
    if search:
        query = query.where(Customer.name.ilike(f"%{search}%"))
    groups = list(db.session.execute(query))
    cent = Decimal("0.01")
    grand_total = sum((Decimal(row.outstanding) for row in groups), Decimal(0))
    return {
        "items": [
            {
                "customer_id": row.customer_id,
                "customer_name": row.customer_name,
                "unpaid_sales": row.unpaid_sales,
                "outstanding": str(Decimal(row.outstanding).quantize(cent)),
            }
            for row in groups[:100]
        ],
        "total_outstanding": str(grand_total.quantize(cent)),
        "open_invoices": sum(row.unpaid_sales for row in groups),
        "has_more": len(groups) > 100,
        "note": "ยอดลูกหนี้คงค้างจากการขาย ไม่ใช่รายงานอายุหนี้หรือยอดตามบัญชีแยกประเภท",
    }
