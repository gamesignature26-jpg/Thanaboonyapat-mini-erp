"""Read-only cost provenance diagnostics, explicitly NOT an inventory valuation.

Received supplier costs prove what was entered for a receipt, NOT which
specific packs were sold. Historical stock, manual adjustments, returns,
purchase freight and cost-at-sale are unvalued until a controlled cost ledger
and independently reconciled opening balance exist.
"""

from decimal import Decimal

from flask import Blueprint, abort, request
from sqlalchemy import case, func

from . import roles
from .models import Product, Sale, StockMovement, db
from .purchasing import PurchaseOrder, PurchaseOrderLine

bp = Blueprint("cost_evidence", __name__)
CENT = Decimal("0.01")


def _page_int(name, default, maximum):
    value = request.args.get(name)
    if value is None:
        return default
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= maximum:
        abort(400, f"Invalid {name}")
    return int(value)


def _money(value):
    return str(Decimal(value or 0).quantize(CENT))


@bp.get("/api/reports/cost-evidence")
@roles("accountant")
def cost_evidence():
    """Show traceable cost *inputs* but withhold uncertified COGS/profit."""
    limit = _page_int("limit", 50, 100)
    after = _page_int("after", 0, 1000000000)
    products = list(
        db.session.scalars(db.select(Product).where(Product.id > after).order_by(Product.id).limit(limit + 1))
    )
    page = products[:limit]

    receipts = db.session.execute(
        db.select(
            PurchaseOrderLine.product_id,
            func.sum(PurchaseOrderLine.quantity),
            func.sum(PurchaseOrderLine.quantity * PurchaseOrderLine.unit_cost),
        )
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_id)
        .where(PurchaseOrder.status == "received")
        .group_by(PurchaseOrderLine.product_id)
    ).all()
    receipt_by_product = {int(pid): (int(qty), Decimal(value)) for pid, qty, value in receipts}

    movements = db.session.execute(
        db.select(
            StockMovement.product_id,
            func.sum(StockMovement.delta),
            func.sum(case((StockMovement.delta > 0, StockMovement.delta), else_=0)),
        ).group_by(StockMovement.product_id)
    ).all()
    movement_by_product = {int(pid): (int(net), int(inbound)) for pid, net, inbound in movements}

    items = []
    for product in page:
        quantity, input_cost = receipt_by_product.get(product.id, (0, Decimal("0.00")))
        net_movement, inbound_movement = movement_by_product.get(product.id, (0, 0))
        items.append(
            {
                "product_id": product.id,
                "sku": product.sku,
                "name": product.name,
                "stock_units": product.stock,
                "received_purchase_units": quantity,
                "received_purchase_cost_ex_vat": _money(input_cost),
                # Only a discrepancy indicator, NOT an estimate of the value
                # of stock-on-hand or an allocation of which units were sold.
                "unattributed_inbound_units": max(0, inbound_movement - quantity),
                "stock_movement_reconciles": product.stock == net_movement,
                "cost_status": "unverified",
            }
        )

    return {
        "items": items,
        "next_after": page[-1].id if len(products) > limit else None,
        "received_purchase_units": sum(qty for qty, _cost in receipt_by_product.values()),
        "received_purchase_cost_ex_vat": _money(
            sum((cost for _qty, cost in receipt_by_product.values()), Decimal("0.00"))
        ),
        "sales_revenue_ex_vat": _money(db.session.scalar(db.select(func.sum(Sale.subtotal)))),
        "cogs_ex_vat": None,
        "gross_profit_ex_vat": None,
        "gross_profit_status": "unavailable",
        "notice": (
            "รายการต้นทุนซื้อที่รับเข้าเป็นเพียงหลักฐานราคา ไม่ใช่มูลค่าสินค้าคงเหลือ "
            "ต้นทุนขาย หรือกำไรขั้นต้น ต้องตรวจสอบต้นทุนยกมา การปรับปรุงสต็อก "
            "การรับคืน และบันทึกต้นทุน ณ วันขายก่อน"
        ),
    }
