"""Quotation drafts in an isolated ledger, without altering the sale or tax document schema.

Revision ID: e2b6d09c4112
Revises: 71c40f312b01

Only run against disposable CI/test data until staging backup and restore have
been verified. Downgrade drops quotation drafts and permanently loses them.
"""

import sqlalchemy as sa
from alembic import op

revision = "e2b6d09c4112"
down_revision = "71c40f312b01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quotation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_key", sa.String(80), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id"), nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_tax_id", sa.String(13), nullable=True),
        sa.Column("customer_address", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("vat_price_mode", sa.String(9), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("vat", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("note", sa.String(600), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('draft','sent','accepted','declined')"),
        sa.CheckConstraint("vat_price_mode IN ('inclusive','exclusive')"),
        sa.CheckConstraint("subtotal >= 0 AND vat >= 0 AND total >= 0"),
    )
    op.create_table(
        "quotation_line",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("quotation.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("product.id"), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.CheckConstraint("quantity > 0 AND unit_price >= 0"),
    )


def downgrade():
    # DESTRUCTIVE — CI or disposable databases only.
    op.drop_table("quotation_line")
    op.drop_table("quotation")
