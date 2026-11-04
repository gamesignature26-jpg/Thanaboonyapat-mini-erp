from datetime import UTC, datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    __table_args__ = (CheckConstraint("role IN ('admin','sales','warehouse','accountant')"),)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    price = db.Column(db.Numeric(14, 2), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (CheckConstraint("price >= 0"), CheckConstraint("stock >= 0"))


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    tax_id = db.Column(db.String(13))
    address = db.Column(db.String(1000), nullable=False, default="")


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.ForeignKey("customer.id"), nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_tax_id = db.Column(db.String(13))
    customer_address = db.Column(db.String(1000), nullable=False)
    subtotal = db.Column(db.Numeric(14, 2), nullable=False)
    vat_rate = db.Column(db.Numeric(5, 2), nullable=False)
    vat = db.Column(db.Numeric(14, 2), nullable=False)
    total = db.Column(db.Numeric(14, 2), nullable=False)
    paid = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    __table_args__ = (CheckConstraint("paid >= 0 AND paid <= total"),)


class SaleLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.ForeignKey("sale.id"), nullable=False)
    product_id = db.Column(db.ForeignKey("product.id"), nullable=False)
    sku = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Numeric(14, 2), nullable=False)
    __table_args__ = (CheckConstraint("quantity > 0"),)


class StockMovement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.ForeignKey("product.id"), nullable=False)
    delta = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    sale_id = db.Column(db.ForeignKey("sale.id"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.ForeignKey("sale.id"), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    reference = db.Column(db.String(100), unique=True, nullable=False)
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    __table_args__ = (CheckConstraint("amount > 0"),)
