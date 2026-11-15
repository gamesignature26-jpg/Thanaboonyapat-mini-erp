"""Retain contact details and source metadata from customer XLSX imports.

Revision ID: e4d6b7c8a901
Revises: c3f8a740e921
"""

import sqlalchemy as sa
from alembic import op

revision = "e4d6b7c8a901"
down_revision = "c3f8a740e921"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("customer") as batch_op:
        batch_op.add_column(sa.Column("phone", sa.String(30), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("email", sa.String(255), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("external_code", sa.String(80), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("source_customer_id", sa.String(80), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("note", sa.String(1000), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("import_metadata", sa.Text(), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("customer") as batch_op:
        batch_op.drop_column("import_metadata")
        batch_op.drop_column("note")
        batch_op.drop_column("source_customer_id")
        batch_op.drop_column("external_code")
        batch_op.drop_column("email")
        batch_op.drop_column("phone")
