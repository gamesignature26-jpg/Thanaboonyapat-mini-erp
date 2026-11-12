"""Add non-posting credit review drafts. Never downgrade outside disposable test DB.

Revision ID: bd8c1a770e21
Revises: 6f9d20c8a7b1
"""

import sqlalchemy as sa
from alembic import op

revision = "bd8c1a770e21"
down_revision = "6f9d20c8a7b1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "credit_note_draft",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_key", sa.String(80), unique=True, nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("return_id", sa.Integer(), sa.ForeignKey("return_intake.id"), unique=True, nullable=False),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sale.id"), nullable=False),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_tax_id", sa.String(13)),
        sa.Column("customer_address", sa.String(1000), nullable=False),
        sa.Column("reason", sa.String(600), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("amount_ex_vat", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("credit_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("original_sale_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("original_sale_paid", sa.Numeric(14, 2), nullable=False),
        sa.Column("returned_lines_snapshot", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("void_reason", sa.String(600)),
        sa.Column("voided_by", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft','void')"),
        sa.CheckConstraint("amount_ex_vat >= 0 AND vat_amount >= 0 AND credit_total > 0"),
        sa.CheckConstraint("credit_total = amount_ex_vat + vat_amount"),
    )


def downgrade():
    # Intentionally destructive; NEVER apply to staging or production data.
    op.drop_table("credit_note_draft")
