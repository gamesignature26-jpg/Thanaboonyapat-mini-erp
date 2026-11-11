"""Record whether entered sale prices include VAT."""

import sqlalchemy as sa
from alembic import op

revision = "71c40f312b01"
down_revision = "d5f0cafe2026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sale", sa.Column("vat_price_mode", sa.String(9), nullable=False, server_default="exclusive"))


def downgrade():
    op.drop_column("sale", "vat_price_mode")
