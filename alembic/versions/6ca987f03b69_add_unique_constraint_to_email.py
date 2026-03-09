"""add unique constraint to email

Revision ID: 6ca987f03b69
Revises: d4f5957ec1a6
Create Date: 2026-03-09 20:05:32.540498

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6ca987f03b69'
down_revision: Union[str, Sequence[str], None] = 'd4f5957ec1a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint to users.email column."""
    op.create_unique_constraint('users_email_key', 'users', ['email'])


def downgrade() -> None:
    """Remove unique constraint from users.email column."""
    op.drop_constraint('users_email_key', 'users', type_='unique')
