"""Delivery ledger, private evidence, verified contacts and integration inbox."""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint

from .models import db


def now():
    return datetime.now(UTC)


class EmailContact(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey("user.id"), nullable=False, unique=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    nonce_hash = db.Column(db.String(64), nullable=False)
    weekly = db.Column(db.Boolean, nullable=False, default=False)


class Evidence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.ForeignKey("sale.id"))
    expense_id = db.Column(db.ForeignKey("online_expense.id"))
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    content = db.Column(db.LargeBinary, nullable=False)
    media_type = db.Column(db.String(30), nullable=False)
    digest = db.Column(db.String(64), nullable=False, unique=True)
    status = db.Column(db.String(15), nullable=False, default="pending")
    reviewer_id = db.Column(db.ForeignKey("user.id"))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint("(sale_id IS NULL) <> (expense_id IS NULL)"),
        CheckConstraint("status IN ('pending','accepted','rejected')"),
    )


class Driver(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    daily_rate = db.Column(db.Numeric(14, 2), nullable=False)
    delivery_rate = db.Column(db.Numeric(14, 2), nullable=False)
    __table_args__ = (CheckConstraint("daily_rate >= 0 AND delivery_rate >= 0"),)


class DriverEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.ForeignKey("driver.id"), nullable=False)
    day = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    note = db.Column(db.String(250), nullable=False)
    # Source links prevent approving the same delivery or expense twice.
    sale_id = db.Column(db.ForeignKey("sale.id"), unique=True)
    expense_id = db.Column(db.ForeignKey("online_expense.id"), unique=True)
    request_key = db.Column(db.String(80), unique=True, nullable=False)
    actor_id = db.Column(db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (
        CheckConstraint("kind IN ('day','delivery','advance','reimburse','bonus')"),
        CheckConstraint("amount >= 0"),
        db.UniqueConstraint("driver_id", "day", "kind", "sale_id", name="driver_source_day"),
    )


class LineSender(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    line_user_id = db.Column(db.String(100), nullable=False, unique=True)
    customer_id = db.Column(db.ForeignKey("customer.id"), nullable=False)
    group_id = db.Column(db.String(100), nullable=False, default="")
    enabled = db.Column(db.Boolean, nullable=False, default=True)


class LineDraft(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(100), nullable=False, unique=True)
    sender_id = db.Column(db.ForeignKey("line_sender.id"), nullable=False)
    customer_id = db.Column(db.ForeignKey("customer.id"), nullable=False)
    lines = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    sale_id = db.Column(db.ForeignKey("sale.id"), unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (CheckConstraint("status IN ('pending','accepted','rejected')"),)


class ReportDelivery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    week = db.Column(db.Date, nullable=False)
    contact_id = db.Column(db.ForeignKey("email_contact.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=now)
    __table_args__ = (db.UniqueConstraint("week", "contact_id", name="weekly_contact"),)
