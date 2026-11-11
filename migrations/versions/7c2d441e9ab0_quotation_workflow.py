"""Audit quote statuses and link each accepted quote to at most one existing sale.

Revision ID: 7c2d441e9ab0
Revises: e2b6d09c4112

Additive migration; no existing sale, stock or payment rows are changed.
Downgrade is destructive for quotation events and conversion links: CI only.
"""

import sqlalchemy as sa
from alembic import op

revision = "7c2d441e9ab0"
down_revision = "e2b6d09c4112"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("quotation", sa.Column("sale_id", sa.Integer(), nullable=True))
    op.add_column("quotation", sa.Column("conversion_hash", sa.String(length=64), nullable=True))
    op.create_foreign_key("fk_quotation_sale_id", "quotation", "sale", ["sale_id"], ["id"])
    op.create_unique_constraint("uq_quotation_sale_id", "quotation", ["sale_id"])
    op.create_table(
        "quotation_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quotation_id", sa.Integer(), sa.ForeignKey("quotation.id"), nullable=False),
        sa.Column("from_status", sa.String(length=12), nullable=False),
        sa.Column("to_status", sa.String(length=12), nullable=False),
        sa.Column("note", sa.String(length=600), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("from_status IN ('draft','sent','accepted','declined')"),
        sa.CheckConstraint("to_status IN ('sent','accepted','declined')"),
    )


def downgrade():
    # DESTRUCTIVE: never downgrade real/staging data to 'roll back' an application release.
    op.drop_table("quotation_event")
    op.drop_constraint("uq_quotation_sale_id", "quotation", type_="unique")
    op.drop_constraint("fk_quotation_sale_id", "quotation", type_="foreignkey")
    op.drop_column("quotation", "conversion_hash")
    op.drop_column("quotation", "sale_id")
