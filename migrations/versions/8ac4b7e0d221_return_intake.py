"""Add return intake and itemized physical inspection audit, without changing sale ledger.

Revision ID: 8ac4b7e0d221
Revises: 7c2d441e9ab0

Downgrade drops return audit history and is destructive; CI/disposable DB only.
"""

import sqlalchemy as sa
from alembic import op

revision = "8ac4b7e0d221"
down_revision = "7c2d441e9ab0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "return_intake",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_key", sa.String(80), nullable=False, unique=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sale.id"), nullable=False),
        sa.Column("reason", sa.String(600), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("condition", sa.String(12)),
        sa.Column("inspection_note", sa.String(600)),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("inspected_by", sa.Integer(), sa.ForeignKey("user.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inspected_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('draft','received','rejected')"),
        sa.CheckConstraint("condition IS NULL OR condition IN ('resellable','damaged')"),
    )
    op.create_table(
        "return_intake_line",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("return_id", sa.Integer(), sa.ForeignKey("return_intake.id"), nullable=False),
        sa.Column("sale_line_id", sa.Integer(), sa.ForeignKey("sale_line.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("product.id"), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0"),
        sa.UniqueConstraint("return_id", "sale_line_id", name="uq_return_intake_line"),
    )


def downgrade():
    # Destructive. Do not execute on staging or production business data.
    op.drop_table("return_intake_line")
    op.drop_table("return_intake")
