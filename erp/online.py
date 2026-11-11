"""Unified POS, wholesale, dispatch, and expense API for the single-company ERP.

Feature branch/staging only. This module intentionally does NOT issue tax invoices,
perform double-entry accounting, or call a real payment gateway.
"""

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, g, render_template, request
from sqlalchemy import CheckConstraint, func

from . import data, integer, money, roles, text
from .extended import CustomerPrice
from .models import Customer, Payment, Product, Sale, SaleLine, StockMovement, db

CENT = Decimal("0.01")
BANGKOK = ZoneInfo("Asia/Bangkok")


class OnlineOrder(db.Model):
    __tablename__ = "online_order"
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.ForeignKey("sale.id"), nullable=False, unique=True)
    idempotency_key = db.Column(db.String(80), nullable=False, unique=True)
    request_hash = db.Column(db.String(64), nullable=False)
    kind = db.Column(db.String(15), nullable=False)
    delivery_mode = db.Column(db.String(15), nullable=False)
    delivery_date = db.Column(db.Date)
    delivery_status = db.Column(db.String(25), nullable=False, default="pending")
    shipping_fee = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    address = db.Column(db.String(1000), nullable=False, default="")
    phone = db.Column(db.String(30), nullable=False, default="")
    driver = db.Column(db.String(100), nullable=False, default="")
    note = db.Column(db.String(600), nullable=False, default="")
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    __table_args__ = (
        CheckConstraint("kind IN ('pos','wholesale')"),
        CheckConstraint("delivery_mode IN ('pickup','delivery')"),
        CheckConstraint("shipping_fee >= 0 AND discount >= 0"),
    )


class OnlineExpense(db.Model):
    __tablename__ = "online_expense"
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(250), nullable=False)
    method = db.Column(db.String(15), nullable=False)
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    __table_args__ = (CheckConstraint("amount > 0"), CheckConstraint("method IN ('cash','transfer')"))


class OnlinePaymentMethod(db.Model):
    __tablename__ = "online_payment_method"
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.ForeignKey("payment.id"), nullable=False, unique=True)
    method = db.Column(db.String(15), nullable=False)
    __table_args__ = (CheckConstraint("method IN ('cash','transfer')"),)


bp = Blueprint("one_online", __name__, static_folder="static/online", static_url_path="/assets/online")


def limited(body, key, maxlen, default=""):
    value = body.get(key, default)
    if not isinstance(value, str) or len(value) > maxlen:
        abort(400, f"Invalid {key}")
    return value.strip()


def payment_method(body):
    value = limited(body, "method", 10, "credit")
    if value not in ("cash", "transfer", "credit"):
        abort(400, "Invalid payment method")
    return value


def parse_day(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) != 10:
        abort(400, "Invalid delivery date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        abort(400, "Invalid delivery date")
    if parsed.isoformat() != value:
        abort(400, "Invalid delivery date")
    return parsed


def money_json(x):
    return str(Decimal(x).quantize(CENT))


def serialize_sale(s, order=None):
    result = {
        "id": s.id,
        "date": s.created_at.isoformat() if s.created_at else None,
        "customer": s.customer_name,
        "subtotal": money_json(s.subtotal),
        "vat": money_json(s.vat),
        "vat_price_mode": s.vat_price_mode,
        "total": money_json(s.total),
        "paid": money_json(s.paid),
        "balance": money_json(s.total - s.paid),
        "kind": order.kind if order else "legacy",
        "status": order.delivery_status if order else None,
        "mode": order.delivery_mode if order else None,
        "delivery_date": order.delivery_date.isoformat() if order and order.delivery_date else None,
        "driver": order.driver if order else "",
        "address": order.address if order else "",
        "phone": order.phone if order else "",
    }
    return result


@bp.get("/app")
def app_page():
    return render_template("online.html")


@bp.get("/api/online/config")
@roles("sales", "warehouse", "accountant")
def config():
    return {"vat_rate": str(current_app.config["VAT_RATE"]), "company_name": "ธนาบุณยภัทร"}


@bp.post("/api/online/orders")
@roles("sales")
def create_order(body_override=None, before_commit=None):
    body = data() if body_override is None else body_override
    key = text(body, "idempotency_key", 80)
    request_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if len(key) < 16:
        abort(400, "Idempotency key too short")
    duplicate = db.session.scalar(db.select(OnlineOrder).where(OnlineOrder.idempotency_key == key))
    if duplicate:
        if duplicate.request_hash != request_hash:
            abort(409, "Idempotency key reused with different order")
        return {"id": duplicate.sale_id, "duplicate": True}, 200

    kind = limited(body, "kind", 15)
    if kind not in ("pos", "wholesale"):
        abort(400, "Invalid sale kind")
    vat_price_mode = body.get("vat_price_mode", "exclusive")
    if vat_price_mode not in ("exclusive", "inclusive"):
        abort(400, "Invalid VAT price mode")
    mode = limited(body, "delivery_mode", 15, "pickup")
    if mode not in ("pickup", "delivery"):
        abort(400, "Invalid delivery mode")
    customer = db.session.get(Customer, integer(body.get("customer_id")))
    if customer is None:
        abort(404, "Customer not found")
    lines = body.get("lines")
    if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
        abort(400, "Expected 1-100 lines")
    requested = {}
    for item in lines:
        if not isinstance(item, dict):
            abort(400, "Invalid line")
        pid = integer(item.get("product_id"))
        qty = integer(item.get("quantity"))
        if pid in requested:
            abort(400, "Duplicate product")
        # Wholesale prices are negotiated but must be authorized by a sales-role user.
        offer = money(item["unit_price"]) if kind == "wholesale" and "unit_price" in item else None
        if offer is not None and offer <= 0:
            abort(400, "Unit price must be positive")
        requested[pid] = (qty, offer)
    if kind == "pos" and ("discount" in body or "shipping_fee" in body):
        abort(400, "POS discounts and shipping require wholesale workflow")
    discount = money(body.get("discount", "0.00")) if kind == "wholesale" else Decimal("0.00")
    fee = money(body.get("shipping_fee", "0.00")) if kind == "wholesale" else Decimal("0.00")
    if mode == "pickup" and fee > 0:
        abort(400, "Pickup cannot have shipping fee")
    method = payment_method(body)
    address = limited(body, "address", 1000, customer.address or "")
    phone = limited(body, "phone", 30)
    driver = limited(body, "driver", 100)
    note = limited(body, "note", 600)
    scheduled = parse_day(body.get("delivery_date"))
    if mode == "delivery" and not address:
        abort(400, "Delivery address required")

    # Row-lock products in deterministic ID order to prevent overselling.
    products = list(
        db.session.scalars(db.select(Product).where(Product.id.in_(requested)).order_by(Product.id).with_for_update())
    )
    if len(products) != len(requested):
        abort(404, "Product not found")
    special = {
        x.product_id: x.price
        for x in db.session.scalars(
            db.select(CustomerPrice).where(
                CustomerPrice.customer_id == customer.id,
                CustomerPrice.product_id.in_(requested),
            )
        )
    }
    subtotal = Decimal("0.00")
    for product in products:
        quantity, offered_price = requested[product.id]
        if product.stock < quantity:
            abort(409, f"Insufficient stock for SKU {product.sku}")
        price = special.get(product.id, product.price) if offered_price is None else offered_price
        subtotal += price * quantity
    if discount > subtotal:
        abort(400, "Discount exceeds subtotal")
    entered_total = subtotal - discount + fee
    rate = Decimal(str(current_app.config["VAT_RATE"]))
    if vat_price_mode == "inclusive":
        total = entered_total
        vat = (total * rate / (Decimal(100) + rate)).quantize(CENT, rounding=ROUND_HALF_UP)
        base = total - vat
    else:
        base = entered_total
        vat = (base * rate / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
        total = base + vat
    if "expected_total" in body and money(body["expected_total"]) != total:
        abort(409, "ราคาหรือยอดรวมเปลี่ยน กรุณาตรวจยอดแล้วลองอีกครั้ง")
    if total > Decimal("999999999.99"):
        abort(400, "Total exceeds limit")

    sale = Sale(
        customer_id=customer.id,
        customer_name=customer.name,
        customer_tax_id=customer.tax_id,
        customer_address=customer.address,
        vat_price_mode=vat_price_mode,
        subtotal=base,
        vat_rate=rate,
        vat=vat,
        total=total,
    )
    db.session.add(sale)
    db.session.flush()
    for product in products:
        qty, offer = requested[product.id]
        price = special.get(product.id, product.price) if offer is None else offer
        product.stock -= qty
        db.session.add(
            SaleLine(
                sale_id=sale.id, product_id=product.id, sku=product.sku, name=product.name, quantity=qty, price=price
            )
        )
        db.session.add(
            StockMovement(product_id=product.id, delta=-qty, reason="Online sale", sale_id=sale.id, actor_id=g.user.id)
        )
    order = OnlineOrder(
        sale_id=sale.id,
        idempotency_key=key,
        request_hash=request_hash,
        kind=kind,
        delivery_mode=mode,
        delivery_date=scheduled,
        delivery_status="pending",
        shipping_fee=fee,
        discount=discount,
        address=address,
        phone=phone,
        driver=driver,
        note=note,
        actor_id=g.user.id,
    )
    db.session.add(order)
    if method != "credit" and total > 0:
        payment = Payment(sale_id=sale.id, amount=total, reference=f"auto-{key}", actor_id=g.user.id)
        db.session.add(payment)
        db.session.flush()
        db.session.add(OnlinePaymentMethod(payment_id=payment.id, method=method))
        sale.paid = total
    if before_commit:
        before_commit(sale)
    db.session.commit()
    return {"id": sale.id, "total": money_json(total), "vat": money_json(vat), "duplicate": False}, 201


@bp.get("/api/online/sales")
@roles("sales", "accountant")
def sales_list():
    query = db.select(Sale)
    if request.args.get("outstanding") == "1":
        query = query.where(Sale.paid < Sale.total)
    before = request.args.get("before", type=int)
    if before is not None:
        query = query.where(Sale.id < before)
    rows = list(db.session.scalars(query.order_by(Sale.id.desc()).limit(101)))
    sales = rows[:100]
    orders = (
        {
            o.sale_id: o
            for o in db.session.scalars(db.select(OnlineOrder).where(OnlineOrder.sale_id.in_([s.id for s in sales])))
        }
        if sales
        else {}
    )
    return {
        "items": [serialize_sale(s, orders.get(s.id)) for s in sales],
        "next_before": sales[-1].id if len(rows) > 100 else None,
    }


@bp.get("/api/online/orders")
@roles("sales", "warehouse", "accountant")
def order_list():
    orders = list(
        db.session.scalars(
            db.select(OnlineOrder).where(OnlineOrder.kind == "wholesale").order_by(OnlineOrder.id.desc()).limit(100)
        )
    )
    items = [serialize_sale(db.session.get(Sale, o.sale_id), o) for o in orders]
    if g.user.role == "warehouse":
        for item in items:
            hide_sale_amounts(item)
    return {"items": items}


def hide_sale_amounts(item):
    for key in ("subtotal", "vat", "total", "paid", "balance", "discount", "shipping_fee"):
        item.pop(key, None)
    for line in item.get("lines", ()):
        line.pop("unit_price", None)


@bp.get("/api/online/orders/<int:sale_id>")
@roles("sales", "warehouse", "accountant")
def delivery_note_data(sale_id):
    order = db.session.scalar(db.select(OnlineOrder).where(OnlineOrder.sale_id == sale_id))
    if not order or order.kind != "wholesale":
        abort(404)
    sale = db.get_or_404(Sale, sale_id)
    result = serialize_sale(sale, order)
    result.update(
        {
            "discount": money_json(order.discount),
            "shipping_fee": money_json(order.shipping_fee),
            "note": order.note,
            "lines": [
                {"sku": x.sku, "name": x.name, "quantity": x.quantity, "unit_price": money_json(x.price)}
                for x in db.session.scalars(db.select(SaleLine).where(SaleLine.sale_id == sale_id))
            ],
        }
    )
    if g.user.role == "warehouse":
        hide_sale_amounts(result)
    return result


@bp.post("/api/online/orders/<int:sale_id>/advance")
@roles("sales", "warehouse")
def advance(sale_id):
    order = db.session.scalar(db.select(OnlineOrder).where(OnlineOrder.sale_id == sale_id).with_for_update())
    if not order or order.kind != "wholesale":
        abort(404)
    states = (
        ["pending", "ready", "picked_up"]
        if order.delivery_mode == "pickup"
        else ["pending", "packing", "out_for_delivery", "delivered"]
    )
    if order.delivery_status not in states:
        abort(409, "Invalid status")
    index = states.index(order.delivery_status)
    if index == len(states) - 1:
        abort(409, "Order already completed")
    order.delivery_status = states[index + 1]
    db.session.commit()
    return {"status": order.delivery_status}


@bp.post("/api/online/sales/<int:sale_id>/payments")
@roles("accountant")
def receive_payment(sale_id):
    body = data()
    sale = db.session.get(Sale, sale_id, with_for_update=True)
    if not sale:
        abort(404)
    amount = money(body.get("amount"))
    if amount <= 0 or amount > sale.total - sale.paid:
        abort(409, "Payment exceeds outstanding balance")
    reference = text(body, "reference", 100)
    if len(reference) < 12:
        abort(400, "Reference too short")
    method = limited(body, "method", 10)
    if method not in ("cash", "transfer"):
        abort(400, "Invalid method")
    payment = Payment(sale_id=sale.id, amount=amount, reference=reference, actor_id=g.user.id)
    db.session.add(payment)
    db.session.flush()
    db.session.add(OnlinePaymentMethod(payment_id=payment.id, method=method))
    sale.paid += amount
    db.session.commit()
    return {"balance": money_json(sale.total - sale.paid)}, 201


@bp.route("/api/online/expenses", methods=["GET", "POST"])
@roles("accountant")
def expenses():
    if request.method == "GET":
        items = list(db.session.scalars(db.select(OnlineExpense).order_by(OnlineExpense.id.desc()).limit(100)))
        return {
            "items": [
                {
                    "id": x.id,
                    "date": x.created_at.isoformat(),
                    "amount": money_json(x.amount),
                    "description": x.description,
                    "category": x.category,
                    "method": x.method,
                }
                for x in items
            ]
        }
    body = data()
    amount = money(body.get("amount"))
    if amount <= 0:
        abort(400, "Expense amount must be positive")
    method = limited(body, "method", 10)
    if method not in ("cash", "transfer"):
        abort(400, "Invalid method")
    expense = OnlineExpense(
        amount=amount,
        description=text(body, "description", 250),
        category=text(body, "category", 80),
        method=method,
        actor_id=g.user.id,
    )
    db.session.add(expense)
    db.session.commit()
    return {"id": expense.id}, 201


@bp.get("/api/online/dashboard")
@roles("sales", "warehouse", "accountant")
def dashboard():
    total_sales = db.session.scalar(db.select(func.sum(Sale.total))) or Decimal("0.00")
    total_paid = db.session.scalar(db.select(func.sum(Sale.paid))) or Decimal("0.00")
    inventory = db.session.scalar(db.select(func.sum(Product.stock))) or 0
    if g.user.role == "warehouse":
        # Warehouse staff must not gain financial-report visibility through the new dashboard.
        expenses_sum = None
        total_sales = None
        total_paid = None
    else:
        expenses_sum = db.session.scalar(db.select(func.sum(OnlineExpense.amount))) or Decimal("0.00")
    now = datetime.now(BANGKOK)
    beginning = datetime.combine(now.date(), time.min, tzinfo=BANGKOK).astimezone(UTC)
    today_total = (
        (db.session.scalar(db.select(func.sum(Sale.total)).where(Sale.created_at >= beginning)) or Decimal("0.00"))
        if g.user.role != "warehouse"
        else None
    )
    waiting = (
        db.session.scalar(
            db.select(func.count())
            .select_from(OnlineOrder)
            .where(OnlineOrder.kind == "wholesale", OnlineOrder.delivery_status.notin_(("delivered", "picked_up")))
        )
        or 0
    )
    return {
        "sales_total": money_json(total_sales) if total_sales is not None else None,
        "today_total": money_json(today_total) if today_total is not None else None,
        "receivable": money_json(total_sales - total_paid) if total_sales is not None else None,
        "expenses_total": money_json(expenses_sum) if expenses_sum is not None else None,
        "stock_units": inventory,
        "pending_delivery": waiting,
        "warning": "Sales totals include VAT. Expenses are not a full accounting ledger or profit figure.",
    }


def install_online(app):
    app.register_blueprint(bp)
