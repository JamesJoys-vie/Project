"""transactions.expires_at (+ index for the expiry job); ledger unique key (transaction_id, type) to allow one refund

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("transactions", sa.Column("expires_at", sa.DateTime, nullable=True))
    op.create_index("ix_transactions_status_expires", "transactions", ["status", "expires_at"])
    # New unique key first: it also serves the FK on transaction_id, so the old single-column one can then be dropped.
    op.create_unique_constraint("uq_ledger_txn_type", "ledger_entries", ["transaction_id", "type"])
    op.drop_index("transaction_id", table_name="ledger_entries")


def downgrade():
    op.create_index("transaction_id", "ledger_entries", ["transaction_id"], unique=True)
    op.drop_constraint("uq_ledger_txn_type", "ledger_entries", type_="unique")
    op.drop_index("ix_transactions_status_expires", table_name="transactions")
    op.drop_column("transactions", "expires_at")
