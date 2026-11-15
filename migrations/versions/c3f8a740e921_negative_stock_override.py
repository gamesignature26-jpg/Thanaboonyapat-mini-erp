"""Permit audited owner-approved negative stock balances.

Revision ID: c3f8a740e921
Revises: bd8c1a770e21

The application still rejects shortages by default.  This removes only the
database-level non-negative constraint so an approved sale can be recorded
with its StockMovement audit trail.
"""

from alembic import op

revision = "c3f8a740e921"
down_revision = "bd8c1a770e21"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table(
        "product", naming_convention={"ck": "%(table_name)s_%(column_0_name)s_check"}
    ) as batch_op:
        batch_op.drop_constraint("product_stock_check", type_="check")


def downgrade():
    with op.batch_alter_table(
        "product", naming_convention={"ck": "%(table_name)s_%(column_0_name)s_check"}
    ) as batch_op:
        batch_op.create_check_constraint("product_stock_check", "stock >= 0")
