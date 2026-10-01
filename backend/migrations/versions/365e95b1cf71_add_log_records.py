"""add log_records

Revision ID: 365e95b1cf71
Revises: ee9322807de8
Create Date: 2026-09-11 02:14:12.225917

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '365e95b1cf71'
down_revision: Union[str, None] = 'ee9322807de8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "log_records" in inspector.get_table_names():
        return
    op.create_table(
        "log_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("logger", sa.String(length=192), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("exc_text", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("task_id", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_log_level_ts", "log_records", ["level", "ts"], unique=False)
    op.create_index("ix_log_logger_ts", "log_records", ["logger", "ts"], unique=False)
    op.create_index("ix_log_ts", "log_records", ["ts"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_log_ts", table_name="log_records")
    op.drop_index("ix_log_logger_ts", table_name="log_records")
    op.drop_index("ix_log_level_ts", table_name="log_records")
    op.drop_table("log_records")