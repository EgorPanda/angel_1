"""vault index tables (v2 vault-sourced notes)

Revision ID: a1b2c3d4e5f6
Revises: 365e95b1cf71
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '365e95b1cf71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('index_notes',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('path', sa.String(length=1024), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=False),
        sa.Column('note_type', sa.String(length=32), nullable=False),
        sa.Column('business', sa.String(length=256), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('importance', sa.String(length=16), nullable=False),
        sa.Column('summary', sa.String(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('file_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('path')
    )
    op.create_index('ix_index_notes_folder', 'index_notes', ['path'], unique=False)
    op.create_index('ix_index_notes_status', 'index_notes', ['status'], unique=False)
    op.create_index('ix_index_notes_title', 'index_notes', ['title'], unique=False)
    op.create_index('ix_index_notes_type', 'index_notes', ['note_type'], unique=False)

    op.create_table('index_tags',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('index_note_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.ForeignKeyConstraint(['index_note_id'], ['index_notes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('index_note_id', 'name', name='uq_index_tag')
    )
    op.create_index('ix_index_tags_name', 'index_tags', ['name'], unique=False)

    op.create_table('index_links',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('source_path', sa.String(length=1024), nullable=False),
        sa.Column('target_path', sa.String(length=1024), nullable=False),
        sa.Column('target_id', sa.Uuid(), nullable=True),
        sa.Column('relation_type', sa.String(length=32), nullable=False),
        sa.Column('label', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['index_notes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_id'], ['index_notes.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', 'target_path', name='uq_index_link')
    )
    op.create_index('ix_index_links_source', 'index_links', ['source_id'], unique=False)
    op.create_index('ix_index_links_target_path', 'index_links', ['target_path'], unique=False)

    op.create_table('index_tasks',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('index_note_id', sa.Uuid(), nullable=False),
        sa.Column('text', sa.String(length=1000), nullable=False),
        sa.Column('done', sa.Boolean(), nullable=False),
        sa.Column('due', sa.DateTime(timezone=True), nullable=True),
        sa.Column('priority', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['index_note_id'], ['index_notes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_index_tasks_done', 'index_tasks', ['done'], unique=False)
    op.create_index('ix_index_tasks_due', 'index_tasks', ['due'], unique=False)
    op.create_index('ix_index_tasks_note', 'index_tasks', ['index_note_id'], unique=False)

    op.create_table('mocs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('folder', sa.String(length=256), nullable=False),
        sa.Column('note_path', sa.String(length=1024), nullable=False),
        sa.Column('structure', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('folder'),
        sa.UniqueConstraint('note_path')
    )

    op.create_table('archive_mocs',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('project_name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('original_folder', sa.String(length=1024), nullable=False),
        sa.Column('restored', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table('sync_state',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.String(), nullable=False),
        sa.Column('indexed_count', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('sync_state')
    op.drop_table('archive_mocs')
    op.drop_table('mocs')
    op.drop_index('ix_index_tasks_note', table_name='index_tasks')
    op.drop_index('ix_index_tasks_due', table_name='index_tasks')
    op.drop_index('ix_index_tasks_done', table_name='index_tasks')
    op.drop_table('index_tasks')
    op.drop_index('ix_index_links_target_path', table_name='index_links')
    op.drop_index('ix_index_links_source', table_name='index_links')
    op.drop_table('index_links')
    op.drop_index('ix_index_tags_name', table_name='index_tags')
    op.drop_table('index_tags')
    op.drop_index('ix_index_notes_type', table_name='index_notes')
    op.drop_index('ix_index_notes_title', table_name='index_notes')
    op.drop_index('ix_index_notes_status', table_name='index_notes')
    op.drop_index('ix_index_notes_folder', table_name='index_notes')
    op.drop_table('index_notes')