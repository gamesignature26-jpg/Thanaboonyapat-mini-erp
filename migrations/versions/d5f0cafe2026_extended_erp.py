"""Customer prices, company profile, private product pictures and document ledger.

Revision ID: d5f0cafe2026
Revises: b8e41108ops

Do not downgrade against business records: downgrade deletes the new tables.
"""

import sqlalchemy as sa
from alembic import op

revision = "d5f0cafe2026"
down_revision = "b8e41108ops"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "company_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("tax_id", sa.String(13), nullable=False),
        sa.Column("branch", sa.String(100), nullable=False),
        sa.Column("address", sa.String(1000), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("receipt_footer", sa.String(250), nullable=False),
        sa.Column("default_paper", sa.String(4), nullable=False),
    )
    op.create_table(
        "customer_price",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("product.id"), nullable=False),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("price > 0", name="ck_customer_price_positive"),
        sa.UniqueConstraint("customer_id", "product_id", name="uq_customer_price_pair"),
    )
    op.create_table(
        "product_image",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("product.id"), nullable=False, unique=True),
        sa.Column("image_data", sa.LargeBinary(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "issued_document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("number", sa.String(40), nullable=True, unique=True),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sale.id"), nullable=False),
        sa.Column("tax_sale_id", sa.Integer(), sa.ForeignKey("sale.id"), nullable=True, unique=True),
        sa.Column("payment_id", sa.Integer(), sa.ForeignKey("payment.id"), nullable=True, unique=True),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(kind = 'tax_invoice' AND tax_sale_id IS NOT NULL AND payment_id IS NULL) "
            "OR (kind = 'receipt' AND tax_sale_id IS NULL AND payment_id IS NOT NULL)",
            name="ck_issued_document_kind_link",
        ),
    )


def downgrade():
    op.drop_table("issued_document")
    op.drop_table("product_image")
    op.drop_table("customer_price")
    op.drop_table("company_profile")
