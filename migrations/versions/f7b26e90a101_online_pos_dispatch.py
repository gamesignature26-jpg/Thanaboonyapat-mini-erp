"""Add online POS / wholesale dispatch / expense / payment-method metadata.

Revision ID: f7b26e90a101
Revises: 914000c03a46
"""

import sqlalchemy as sa
from alembic import op

revision = "f7b26e90a101"
down_revision = "914000c03a46"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "online_order",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sale.id"), nullable=False, unique=True),
        sa.Column("idempotency_key", sa.String(80), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(15), nullable=False),
        sa.Column("delivery_mode", sa.String(15), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=True),
        sa.Column("delivery_status", sa.String(25), nullable=False),
        sa.Column("shipping_fee", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount", sa.Numeric(14, 2), nullable=False),
        sa.Column("address", sa.String(1000), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("driver", sa.String(100), nullable=False),
        sa.Column("note", sa.String(600), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('pos','wholesale')"),
        sa.CheckConstraint("delivery_mode IN ('pickup','delivery')"),
        sa.CheckConstraint("shipping_fee >= 0 AND discount >= 0"),
    )
    op.create_table(
        "online_expense",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("description", sa.String(250), nullable=False),
        sa.Column("method", sa.String(15), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0"),
        sa.CheckConstraint("method IN ('cash','transfer')"),
    )
    op.create_table(
        "online_payment_method",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payment.id"), nullable=False, unique=True),
        sa.Column("method", sa.String(15), nullable=False),
        sa.CheckConstraint("method IN ('cash','transfer')"),
    )


def downgrade():
    # Downgrading DESTROYS online-only records. Never downgrade against real data.
    op.drop_table("online_payment_method")
    op.drop_table("online_expense")
    op.drop_table("online_order")
