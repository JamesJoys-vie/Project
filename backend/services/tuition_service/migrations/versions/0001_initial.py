"""create students, tuitions

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "students",
        sa.Column("student_id", sa.String(20), primary_key=True),
        sa.Column("full_name", sa.String(100), nullable=False),
        mysql_engine="InnoDB",
    )
    op.create_table(
        "tuitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("student_id", sa.String(20), sa.ForeignKey("students.student_id"), nullable=False),
        sa.Column("term", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="UNPAID"),
        sa.Column("reserved_by_txn", sa.String(36), nullable=True),
        sa.Column("reserved_until", sa.DateTime, nullable=True),
        sa.Column("paid_by_txn", sa.String(36), nullable=True, unique=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("student_id", "term", name="uq_tuition_student_term"),
        sa.CheckConstraint("amount > 0", name="ck_tuition_amount_pos"),
        mysql_engine="InnoDB",
    )


def downgrade():
    op.drop_table("tuitions")
    op.drop_table("students")
