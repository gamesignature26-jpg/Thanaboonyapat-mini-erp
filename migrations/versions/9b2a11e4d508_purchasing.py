"""Add suppliers and audit-safe purchase receiving ledgers.

Revision ID: 9b2a11e4d508
Revises: 8ac4b7e0d221

Additive to existing ERP: there are no alterations to historic StockMovement,
Sale, SaleLine, Payment or Product. Downgrade irreversibly deletes purchase records.
"""

import sqlalchemy as sa
from alembic import op

revision = "9b2a11e4d508"
down_revision = "8ac4b7e0d221"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("tax_id", sa.String(13), nullable=True),
        sa.Column("address", sa.String(1000), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "purchase_order",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_key", sa.String(80), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("supplier.id"), nullable=False),
        sa.Column("supplier_name", sa.String(200), nullable=False),
        sa.Column("supplier_tax_id", sa.String(13), nullable=True),
        sa.Column("supplier_address", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("subtotal_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.String(600), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("received_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("receipt_note", sa.String(600), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft','received')"),
        sa.CheckConstraint("subtotal_cost >= 0"),
    )
    op.create_table(
        "purchase_order_line",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_id", sa.Integer(), sa.ForeignKey("purchase_order.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("product.id"), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint("quantity > 0 AND unit_cost > 0"),
        sa.UniqueConstraint("purchase_id", "product_id", name="uq_purchase_order_product"),
    )


def downgrade():
    # Destructive: only run against disposable test databases.
    op.drop_table("purchase_order_line")
    op.drop_table("purchase_order")
    op.drop_table("supplier")
