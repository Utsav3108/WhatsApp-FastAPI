"""add persona admin flags and audit log

Adds is_admin/is_active to personas (admin authz gate + soft-delete flag)
and a new admin_audit_logs table for admin-action attribution (e.g.
persona-session reset-block, persona soft-delete). Both new booleans have
server defaults, so no data backfill is needed.

Revision ID: ba7a3935bbdb
Revises: 31d8311e0009
Create Date: 2026-07-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ba7a3935bbdb'
down_revision: Union[str, Sequence[str], None] = '31d8311e0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('personas', sa.Column('is_admin', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('personas', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))

    op.create_table('admin_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('admin_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('target_type', sa.String(), nullable=False),
        sa.Column('target_id', sa.String(), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['admin_id'], ['personas.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admin_audit_logs_admin_id'), 'admin_audit_logs', ['admin_id'], unique=False)
    op.create_index(op.f('ix_admin_audit_logs_id'), 'admin_audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_admin_audit_logs_target_id'), 'admin_audit_logs', ['target_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_admin_audit_logs_target_id'), table_name='admin_audit_logs')
    op.drop_index(op.f('ix_admin_audit_logs_id'), table_name='admin_audit_logs')
    op.drop_index(op.f('ix_admin_audit_logs_admin_id'), table_name='admin_audit_logs')
    op.drop_table('admin_audit_logs')
    op.drop_column('personas', 'is_active')
    op.drop_column('personas', 'is_admin')
