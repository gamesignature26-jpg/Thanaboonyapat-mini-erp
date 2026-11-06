"""Revoke sessions and prevent duplicate sale requests."""

import sqlalchemy as sa
from alembic import op

revision = "c21a_session_sale"
down_revision = "914000c03a46"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user", sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"))
    op.alter_column("user", "session_version", server_default=None)
    op.add_column("sale", sa.Column("request_key", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_sale_request_key", "sale", ["request_key"])


def downgrade():
    op.drop_constraint("uq_sale_request_key", "sale", type_="unique")
    op.drop_column("sale", "request_key")
    op.drop_column("user", "session_version")
