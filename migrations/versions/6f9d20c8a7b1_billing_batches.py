"""Create separate multi-sale billing draft ledgers; no changes to sales or payments.

Revision ID: 6f9d20c8a7b1
Revises: 9b2a11e4d508

Downgrade deletes billing drafts; only execute it in disposable test databases.
"""

import sqlalchemy as sa
from alembic import op

revision = "6f9d20c8a7b1"
down_revision = "9b2a11e4d508"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_batch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_key", sa.String(80), unique=True, nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id"), nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_tax_id", sa.String(13)),
        sa.Column("customer_address", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("snapshot_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.String(600), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("void_reason", sa.String(600)),
        sa.Column("voided_by", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft','void')"),
        sa.CheckConstraint("snapshot_total >= 0"),
    )
    op.create_table(
        "billing_batch_line",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("billing_batch.id"), nullable=False),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sale.id"), nullable=False),
        sa.Column("sale_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sale_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_at_creation", sa.Numeric(14, 2), nullable=False),
        sa.Column("outstanding_at_creation", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint("batch_id", "sale_id", name="uq_billing_batch_sale"),
        sa.CheckConstraint("outstanding_at_creation > 0"),
    )
    op.create_index("ix_billing_batch_line_sale_id", "billing_batch_line", ["sale_id"])


def downgrade():
    # Destructive: test database only.
    op.drop_index("ix_billing_batch_line_sale_id", table_name="billing_batch_line")
    op.drop_table("billing_batch_line")
    op.drop_table("billing_batch")
