"""add persona session time decay and auto-expiring block fields

Adds blocked_until (nullable — replaces the old permanent
is_blocked=True-forever model with an auto-expiring block window) and
last_emotional_update_at (not-null, decay-calculation anchor, deliberately
distinct from updated_at which is bumped on EVERY save() call including
hard-gate/no-mutation turns) to persona_sessions. Both have safe
defaults/nullability, so no data backfill is needed.

Revision ID: ab675d55f475
Revises: ba7a3935bbdb
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ab675d55f475'
down_revision: Union[str, Sequence[str], None] = 'ba7a3935bbdb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('persona_sessions', sa.Column('blocked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('persona_sessions', sa.Column('last_emotional_update_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('persona_sessions', 'last_emotional_update_at')
    op.drop_column('persona_sessions', 'blocked_until')
