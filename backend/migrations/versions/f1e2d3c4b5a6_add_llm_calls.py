"""add llm_calls table

Revision ID: f1e2d3c4b5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-09-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "llm_calls" in inspector.get_table_names():
        return
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("request_messages", sa.JSON(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("response_tool_calls", sa.JSON(), nullable=True),
        sa.Column("response_usage", sa.JSON(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_ts_model", "llm_calls", ["ts", "model"], unique=False)
    op.create_index("ix_llm_ts", "llm_calls", ["ts"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_ts", table_name="llm_calls")
    op.drop_index("ix_llm_ts_model", table_name="llm_calls")
    op.drop_table("llm_calls")